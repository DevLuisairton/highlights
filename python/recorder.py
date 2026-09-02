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
        if len(self._buf) > 400_000:  # não deixa o buffer crescer sem limite
            self._buf = self._buf[-200_000:]
        return text

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
def _start_capture(dest: Path) -> subprocess.Popen:
    fps = config.RECORD_FPS
    mode = config.RECORD_CAPTURE
    w, h = config.RECORD_RESOLUTION.split("x")
    ff = config.FFMPEG_BIN

    if mode == "ddagrab":
        args = [
            ff, "-y", "-nostdin",
            "-init_hw_device", "d3d11va",
            "-filter_complex",
            f"ddagrab=output_idx=0:framerate={fps},hwdownload,format=bgra",
            "-c:v", "libx264", "-preset", "ultrafast", "-qp", "18",
            "-pix_fmt", "yuv420p", str(dest),
        ]
    elif mode == "gdigrab-window":
        args = [
            ff, "-y", "-nostdin",
            "-f", "gdigrab", "-framerate", str(fps),
            "-i", "title=Counter-Strike 2",
            "-c:v", "libx264", "-preset", "ultrafast", "-qp", "18",
            "-pix_fmt", "yuv420p", str(dest),
        ]
    else:  # gdigrab (tela toda)
        args = [
            ff, "-y", "-nostdin",
            "-f", "gdigrab", "-framerate", str(fps),
            "-video_size", f"{w}x{h}", "-i", "desktop",
            "-c:v", "libx264", "-preset", "ultrafast", "-qp", "18",
            "-pix_fmt", "yuv420p", str(dest),
        ]

    dev = config.RECORD_AUDIO_DEVICE
    if dev:
        args[args.index(str(dest)):args.index(str(dest))] = [
            "-f", "dshow", "-i", f"audio={dev}", "-c:a", "aac", "-ar", "48000",
        ]

    _log("captura: " + " ".join(args))
    return subprocess.Popen(
        args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )


def _stop_capture(proc: subprocess.Popen) -> None:
    proc.terminate()
    try:
        proc.wait(timeout=15)
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

    recording = job_path / "recording.mkv"
    port = config.NETCON_PORT
    con = NetCon(port)
    proc = None
    ff = None
    pre = config.CLIP_PREROLL_SECONDS
    post = config.CLIP_POSTROLL_SECONDS
    settle = 1.5  # tempo pra câmera assentar após o gototick

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

        # HUD limpo (sem sv_cheats / demo_timescale — mexem no estado do demo)
        con.send("cl_draw_only_deathnotices 1")
        con.send("spec_show_xray 0")
        con.send("cl_showfps 0")

        jobstate.update(job_id, stage="recording",
                        message="Gravando os lances…", progress=73)
        ff = _start_capture(recording)
        time.sleep(1.5)
        t0 = time.time()

        segments: list[tuple[dict, float, float]] = []
        n = len(clips)
        for i, c in enumerate(clips):
            con.send(f"demo_gototick {c['tickStart']}")
            # o gototick "pula" processando pacotes — espera terminar
            con.wait_for("Skipping finished", 30)
            con.send("spec_mode 4")
            con.send(f"spec_lock_to_accountid {c['accountId']}")
            time.sleep(settle)
            seg_start = time.time() - t0

            # o demo segue tocando sozinho pela duração do lance
            dur = max(2.0, (c["tickEnd"] - c["tickStart"]) / tickrate)
            time.sleep(dur)
            seg_end = time.time() - t0
            segments.append((c, seg_start, seg_end))
            jobstate.update(
                job_id, stage="recording",
                message=f"Gravando… lance {i + 1}/{n} ({c['playerName']})",
                progress=73 + 12 * (i + 1) / n,
            )

        con.send("disconnect", "quit")
        time.sleep(2.0)
        _stop_capture(ff)
        ff = None

        # recorta
        jobstate.update(job_id, stage="recording",
                        message="Recortando os clipes…", progress=86)
        done = 0
        for c, s, e in segments:
            dest = job_path / "clips" / c["player"] / f"clip_{c['index']:02d}.mp4"
            if _cut(recording, s - pre, e + post, dest):
                done += 1
        if done == 0:
            raise RuntimeError(
                "Nenhum clipe gerado — verifique se o CS2 abriu e o "
                f"-netconport {port} respondeu (worker.log)."
            )
        _log(f"{done}/{len(segments)} clipes recortados")

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
