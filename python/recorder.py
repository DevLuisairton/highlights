"""Fase 2 — gravação dos clipes, dirigida pelo console do CS2.

O CS2 (Source 2) só executa `SkipAhead` de um VDM — ignora `PlayCommands`.
Então NÃO dá pra travar a câmera / marcar cortes por VDM. Aqui a gente
sobe o CS2 com `-netconport <porta>`, conecta um socket TCP e comanda:

    demo_pause
    demo_gototick <tickStart>
    spec_mode 4 ; spec_lock_to_accountid <accountId>
    demo_resume        (deixa correr pela duração do lance)
    ...próximo lance...
    disconnect ; quit

Como o Python controla o relógio, os cortes são feitos por
`time.time()` medido a cada START/END — sem depender de con_timestamp.
A tela é capturada com ffmpeg (ddagrab/gdigrab) durante toda a sessão e
recortada no fim.
"""

from __future__ import annotations

import json
import re
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import config
import jobstate
import vdmgen


def _log(msg: str) -> None:
    print(f"[recorder] {msg}", file=sys.stderr, flush=True)


# ─── preflight ───────────────────────────────────────────────────────────
def preflight() -> list[str]:
    problems: list[str] = []
    if not config.RECORDER_ENABLED:
        problems.append("RECORDER_ENABLED=0")
    if not config.CS2_EXE or not Path(config.CS2_EXE).exists():
        problems.append(f"CS2_EXE inválido: {config.CS2_EXE!r}")
    demos = Path(config.CS2_DEMOS_DIR) if config.CS2_DEMOS_DIR else None
    if not demos or not demos.is_dir():
        problems.append(f"CS2_DEMOS_DIR inválido: {config.CS2_DEMOS_DIR!r}")
    if not shutil.which(config.FFMPEG_BIN):
        problems.append(f"ffmpeg não encontrado: {config.FFMPEG_BIN!r}")
    return problems


# ─── console TCP do CS2 (-netconport) ────────────────────────────────────
class NetCon:
    def __init__(self, port: int):
        self.port = port
        self.sock: socket.socket | None = None
        self._buf = ""
        self._console = ""
        self._console_seen = 0

    def _open_once(self) -> bool:
        try:
            s = socket.create_connection(("127.0.0.1", self.port), timeout=5)
            s.setblocking(False)
            self.sock = s
            return True
        except OSError:
            self.sock = None
            return False

    def connect(self, timeout_s: int) -> None:
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            if self._open_once():
                _log(f"conectado ao console do CS2 (porta {self.port})")
                return
            time.sleep(2.0)
        raise RuntimeError(
            f"não consegui conectar no -netconport {self.port} em {timeout_s}s"
        )

    def _reconnect(self) -> bool:
        """O CS2 derruba o netcon em toda troca de estado (menu -> demo).
        Tenta reabrir por até ~30s."""
        self.close()
        for _ in range(15):
            if self._open_once():
                _log("netcon reconectado")
                return True
            time.sleep(2.0)
        return False

    def send(self, *cmds: str) -> None:
        payload = ("".join(c.rstrip("\n") + "\n" for c in cmds)).encode("utf-8")
        for attempt in range(2):
            if self.sock is None and not self._reconnect():
                raise RuntimeError("netcon caiu e não reconectou")
            try:
                self.sock.sendall(payload)  # type: ignore[union-attr]
                return
            except OSError as e:  # ConnectionReset etc — CS2 trocou de estado
                _log(f"send falhou ({e}); reconectando")
                self.sock = None
                if attempt == 1:
                    raise

    def drain(self) -> str:
        if self.sock is None:
            return ""
        out = []
        try:
            while True:
                chunk = self.sock.recv(65536)
                if not chunk:
                    self.sock = None
                    break
                out.append(chunk.decode("utf-8", "replace"))
        except BlockingIOError:
            pass
        except OSError:
            self.sock = None
        text = "".join(out)
        self._buf += text
        self._console += text
        if len(self._buf) > 400_000:  # não deixa o buffer crescer sem limite
            self._buf = self._buf[-200_000:]
        return text

    def echo_console(self, prefix: str = "cs2") -> None:
        """Joga o que o CS2 mandou desde a última chamada no stderr
        (worker.log) — sem isso é impossível depurar POV / gototick."""
        self.drain()
        new = self._console[self._console_seen:]
        self._console_seen = len(self._console)
        for line in new.splitlines():
            s = line.strip()
            if s:
                print(f"  [{prefix}] {s}", file=sys.stderr, flush=True)

    def wait_for(self, needle: str, timeout_s: float, reconnect: bool = True) -> bool:
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            self.drain()
            if needle in self._buf:
                self._buf = self._buf[self._buf.rfind(needle) + len(needle):]
                return True
            if self.sock is None and reconnect:
                self._reconnect()
            time.sleep(0.2)
        return False

    def close(self) -> None:
        if self.sock:
            try:
                self.sock.close()
            except OSError:
                pass
            self.sock = None


# ─── captura de tela ─────────────────────────────────────────────────────
_LOOPBACK_RE = re.compile(
    r"stereo mix|mixagem est|cable output|virtual-audio-capturer|what u hear|"
    r"wave out mix|loopback|voicemeeter out",
    re.I,
)


def _resolve_audio_device() -> str | None:
    """RECORD_AUDIO_DEVICE: vazio -> sem áudio; 'auto' -> procura um device
    de loopback nos dshow; qualquer outra coisa -> usa como nome literal."""
    dev = config.RECORD_AUDIO_DEVICE.strip()
    if not dev:
        return None
    if dev.lower() != "auto":
        return dev
    try:
        r = subprocess.run(
            [config.FFMPEG_BIN, "-hide_banner", "-list_devices", "true",
             "-f", "dshow", "-i", "dummy"],
            capture_output=True, text=True, timeout=20,
        )
    except Exception as e:  # noqa: BLE001
        _log(f"áudio: não listei dispositivos ({e})")
        return None
    for line in r.stderr.splitlines():
        m = re.search(r'"([^"]+)"\s*\(audio\)', line)
        if m and _LOOPBACK_RE.search(m.group(1)):
            _log(f"áudio: usando loopback '{m.group(1)}'")
            return m.group(1)
    _log("áudio: nenhum dispositivo de loopback. Clipes sem som do jogo — "
         "habilite 'Mixagem estéreo' no Windows (Som > Gravação > Mostrar "
         "dispositivos desativados) ou instale o VB-Audio Cable, e ponha o "
         "nome em RECORD_AUDIO_DEVICE.")
    return None


def _start_capture(dest: Path) -> subprocess.Popen:
    fps = config.RECORD_FPS
    mode = config.RECORD_CAPTURE
    w, h = config.RECORD_RESOLUTION.split("x")
    ff = config.FFMPEG_BIN
    audio = _resolve_audio_device()

    # sem -nostdin: paramos mandando "q" pelo stdin pra o mp4 finalizar
    # direito (terminate() no Windows é kill duro e corrompe o arquivo).
    args = [ff, "-y"]
    # 1) entrada de áudio (índice 0, se houver)
    if audio:
        args += ["-f", "dshow", "-i", f"audio={audio}"]

    # 2) entrada de vídeo — draw_mouse=0 / -draw_mouse 0 tira o cursor do SO
    if mode == "ddagrab":
        args += [
            "-init_hw_device", "d3d11va",
            "-filter_complex",
            f"ddagrab=output_idx=0:framerate={fps}:draw_mouse=0,"
            f"hwdownload,format=bgra[v]",
        ]
        vmap = "[v]"
    elif mode == "gdigrab-window":
        args += [
            "-f", "gdigrab", "-framerate", str(fps), "-draw_mouse", "0",
            "-i", "title=Counter-Strike 2",
        ]
        vmap = f"{1 if audio else 0}:v"
    else:  # gdigrab (tela toda)
        args += [
            "-f", "gdigrab", "-framerate", str(fps), "-draw_mouse", "0",
            "-video_size", f"{w}x{h}", "-i", "desktop",
        ]
        vmap = f"{1 if audio else 0}:v"

    args += ["-map", vmap]
    if audio:
        args += ["-map", "0:a", "-c:a", "aac", "-ar", "48000"]
    args += [
        "-c:v", "libx264", "-preset", "ultrafast", "-qp", "18",
        "-pix_fmt", "yuv420p", str(dest),
    ]

    _log("captura: " + " ".join(args))
    return subprocess.Popen(
        args, stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def _stop_capture(proc: subprocess.Popen) -> None:
    """Para o ffmpeg com 'q' pra ele finalizar/moov o mp4."""
    try:
        if proc.stdin:
            proc.stdin.write(b"q")
            proc.stdin.flush()
            proc.stdin.close()
        proc.wait(timeout=20)
    except Exception:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def _cut(src: Path, start: float, end: float, dest: Path) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    start = max(0.0, start)
    dur = max(0.5, end - start)
    args = [
        config.FFMPEG_BIN, "-y", "-ss", f"{start:.3f}", "-i", str(src),
        "-t", f"{dur:.3f}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "aac", "-movflags", "+faststart", str(dest),
    ]
    r = subprocess.run(args, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    if r.returncode != 0:
        _log(f"cut falhou ({dest.name}): {r.stderr.decode('utf-8','replace')[-300:]}")
        return False
    return True


# ─── orquestração ────────────────────────────────────────────────────────
def record(job_id: str, job_path: Path, report: dict, clips: list[dict]) -> None:
    problems = preflight()
    if problems:
        raise RuntimeError("Gravação não pode rodar: " + "; ".join(problems))

    tickrate = report.get("tickrate", 64)
    demos_dir = Path(config.CS2_DEMOS_DIR)
    stem = f"hillights_{job_id[:8]}"

    # aplica a seleção (jogadores/lances) e reescreve clips.json
    sel = job_path / "selection.json"
    keep = None
    if sel.exists():
        keep = json.loads(sel.read_text("utf-8")).get("keep")
    _, clips = vdmgen.build_vdm(
        report, keep=keep, include_recording=False, fps=config.RECORD_FPS
    )
    (job_path / "clips.json").write_text(
        json.dumps(clips, ensure_ascii=False, indent=2), "utf-8"
    )
    if not clips:
        raise RuntimeError(
            "Nenhum lance selecionado. Escolha ao menos um jogador no painel."
        )
    _log(f"{len(clips)} lances a gravar "
         f"({len({c['player'] for c in clips})} jogadores)")

    staged_dem = demos_dir / f"{stem}.dem"
    shutil.copy(job_path / "uploads" / "partida.dem", staged_dem)

    port = config.NETCON_PORT
    con = NetCon(port)
    proc = None
    ff = None
    settle = 2.5  # tempo (pausado) pra mundo/câmera assentarem após o gototick

    try:
        w, h = config.RECORD_RESOLUTION.split("x")
        # SEM +playdemo aqui: o CS2 derruba o netcon na transição menu->demo.
        # A gente conecta no menu e manda o playdemo pelo próprio console,
        # com reconexão automática.
        args = [
            config.CS2_EXE, "-insecure", "-novid",
            "-netconport", str(port),
            "-w", w, "-h", h, "-windowed",
        ]
        _log("subindo CS2: " + " ".join(args))
        jobstate.update(job_id, stage="recording",
                        message="Abrindo o CS2…", progress=71)
        proc = subprocess.Popen(args)

        con.connect(config.NETCON_CONNECT_TIMEOUT)
        con.send("echo hillights_menu")
        con.wait_for("hillights_menu", 90)

        jobstate.update(job_id, stage="recording",
                        message="Carregando o demo no CS2…", progress=72)
        con.send(f"playdemo {stem}")
        # o CS2 troca de estado (netcon cai e reconecta). Espera o demo tocar.
        ok = con.wait_for("playing demo from", 180)
        if not ok:
            con.wait_for("Playing Demo", 30)
        # NÃO pausar / pular agora: as tabelas de classe/entidade do demo só
        # ficam prontas depois de alguns segundos de reprodução normal —
        # pular antes disso = "CopyNewEntity: invalid class index ... out of
        # range 0". Deixa correr.
        time.sleep(config.RECORD_DEMO_WARMUP)

        # HUD de frag movie + trava de espectador. NUNCA pausamos o demo:
        # deixamos rodar em 1x e só damos demo_gototick pra cada lance
        # (pausar + resume estava falhando e congelando o clipe).
        for cmd in (
            "sv_cheats 1",
            "demo_timescale 1",
            "spec_autodirector 0",          # CS2 não troca de jogador sozinho
            "cl_draw_only_deathnotices 1",
            "cl_deathnotices_time 0.001",
            "spec_hud 0",
            "spec_show_xray 0",
            "cl_showfps 0",
            "cl_showpos 0",
            "sv_showimpacts 0",
            "cl_hud_telemetry_frametime_show 0",
            "cl_hud_telemetry_net_show 0",
        ):
            con.send(cmd)
        time.sleep(0.5)
        con.echo_console("setup")

        def lock(acc: int) -> None:
            con.send("spec_autodirector 0")
            con.send("spec_mode 4")
            con.send(f"spec_lock_to_accountid {acc}")
            con.send(f"spec_player_by_accountid {acc}")

        # trava no 1º jogador já aqui (o alvo é sempre o mesmo por job hoje)
        first_acc = int(clips[0].get("povAccountId") or clips[0].get("accountId") or 0)
        if first_acc > 0:
            lock(first_acc)
        con.echo_console("lock0")

        n = len(clips)
        done = 0
        for i, c in enumerate(clips):
            acc = int(c.get("povAccountId") or c.get("accountId") or 0)
            sid = str(c.get("steamId64") or "")
            if acc <= 0 or not (sid.isdigit() and len(sid) == 17):
                _log(f"PULANDO {c['stem']}: POV inválido "
                     f"(accountId={acc}, steamId64={sid!r})")
                continue

            r = c.get("roundNumber", c.get("round"))
            jobstate.update(
                job_id, stage="recording",
                message=f"Gravando lance {i + 1}/{n} — {c['playerName']} (R{r})",
                progress=73 + 16 * i / n,
            )
            _log(f"clipe {c['stem']}: {c['playerName']} team={c.get('team')} "
                 f"R{r} acc={acc} ticks {c['tickStart']}..{c['tickEnd']} "
                 f"({round((c['tickEnd']-c['tickStart'])/tickrate,1)}s)")

            # 1) pula pro início do lance com o demo TOCANDO (não pausado)
            con.send(f"demo_gototick {c['tickStart']}")
            got_skip = con.wait_for("Demo Skipping", 8)
            if got_skip:
                con.wait_for("Skipping finished", 25) or con.wait_for("finished", 5)
            else:
                time.sleep(3.0)   # jump pequeno / sem log
            lock(acc)
            time.sleep(settle)    # mundo assenta, câmera trava
            con.echo_console(f"hl{i+1}-seek")

            # 2) grava exatamente a janela do lance (demo já está em 1x)
            dest = job_path / "clips" / c["player"] / f"clip_{c['index']:02d}.mp4"
            dest.parent.mkdir(parents=True, exist_ok=True)
            ff = _start_capture(dest)
            time.sleep(1.2)
            lock(acc)

            dur = max(3.0, (c["tickEnd"] - c["tickStart"]) / tickrate)
            slept = 0.0
            while slept < dur:
                step = min(3.0, dur - slept)
                time.sleep(step)
                slept += step
                con.send(f"spec_lock_to_accountid {acc}")

            _stop_capture(ff)
            ff = None
            con.echo_console(f"hl{i+1}-done")
            if dest.exists() and dest.stat().st_size > 20_000:
                done += 1
            else:
                _log(f"clipe {c['stem']} saiu vazio/curto")

        con.send("disconnect")
        con.send("quit")
        time.sleep(1.5)

        if done == 0:
            raise RuntimeError(
                "Nenhum clipe gerado — verifique se o CS2 abriu e o "
                f"-netconport {port} respondeu (worker.log)."
            )
        _log(f"{done}/{n} clipes gravados")

    finally:
        con.close()
        if ff:
            _stop_capture(ff)
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
        try:
            staged_dem.unlink()
        except OSError:
            pass
