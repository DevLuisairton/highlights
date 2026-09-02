"""Fase 3 — montagem com ffmpeg.

A partir de clips/<player>/clip_NN.mp4 + clips.json:
  - final_<player>.mp4  : os lances do jogador, na ordem de score;
  - final_partida.mp4   : o top geral (se MONTAGE_COMBINED=1).

Cada clipe é normalizado (resolução/fps/SAR fixos, faixa de áudio sempre
presente — silêncio se a captura não teve som) e ganha um lower-third com
o nome do jogador + tags nos primeiros segundos. Depois concatena e, se
houver MONTAGE_MUSIC, mistura a trilha por baixo.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import config

_FONT_CANDIDATES = [
    Path("C:/Windows/Fonts/arialbd.ttf"),
    Path("C:/Windows/Fonts/arial.ttf"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
]


def _log(msg: str) -> None:
    print(f"[montage] {msg}", file=sys.stderr, flush=True)


def _font() -> str | None:
    for f in _FONT_CANDIDATES:
        if f.exists():
            return str(f)
    return None


def _esc_filter_path(p: str) -> str:
    """Escapa um caminho pra usar dentro de um filtro ffmpeg (Windows: o
    ':' do drive vira '\\:', barras invertidas viram '/')."""
    return p.replace("\\", "/").replace(":", "\\:")


def _esc_text(s: str) -> str:
    return (
        s.replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "\u2019")
        .replace("%", "\\%")
    )


def _run(args: list[str]) -> bool:
    r = subprocess.run(args, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    if r.returncode != 0:
        _log("ffmpeg falhou: " + r.stderr.decode("utf-8", "replace")[-400:])
        return False
    return True


def _has_audio(path: Path) -> bool:
    try:
        r = subprocess.run(
            [
                "ffprobe", "-v", "error", "-select_streams", "a",
                "-show_entries", "stream=index", "-of", "csv=p=0", str(path),
            ],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
        )
        return bool(r.stdout.strip())
    except FileNotFoundError:
        return True  # sem ffprobe: assume que tem


def _normalize(src: Path, dst: Path, label: str) -> bool:
    w, h = config.MONTAGE_RESOLUTION.split("x")
    fps = config.MONTAGE_FPS
    vf = (
        f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
        f"pad={w}:{h}:-1:-1:color=black,setsar=1,fps={fps},format=yuv420p"
    )
    font = _font()
    if font and label:
        vf += (
            f",drawtext=fontfile='{_esc_filter_path(font)}':text='{_esc_text(label)}':"
            f"x=48:y=h-96:fontsize=34:fontcolor=white:box=1:boxcolor=black@0.55:"
            f"boxborderw=14:enable='lt(t,3.5)'"
        )

    common = [
        config.FFMPEG_BIN, "-y",
        "-i", str(src),
    ]
    if _has_audio(src):
        args = common + [
            "-vf", vf,
            "-af", "aresample=48000,aformat=channel_layouts=stereo",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-c:a", "aac", "-ar", "48000",
            "-video_track_timescale", "90000",
            str(dst),
        ]
    else:
        args = common + [
            "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
            "-vf", vf,
            "-map", "0:v", "-map", "1:a", "-shortest",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-c:a", "aac", "-ar", "48000",
            "-video_track_timescale", "90000",
            str(dst),
        ]
    return _run(args)


def _concat(parts: list[Path], dst: Path) -> bool:
    lst = dst.with_suffix(".txt")
    lst.write_text(
        "".join(f"file '{p.as_posix()}'\n" for p in parts), "utf-8"
    )
    ok = _run(
        [
            config.FFMPEG_BIN, "-y", "-f", "concat", "-safe", "0",
            "-i", str(lst), "-c", "copy", "-movflags", "+faststart", str(dst),
        ]
    )
    lst.unlink(missing_ok=True)
    return ok


def _add_music(src: Path, dst: Path) -> bool:
    music = config.MONTAGE_MUSIC
    if not music or not Path(music).exists():
        # sem trilha: só renomeia/copia
        return _run(
            [config.FFMPEG_BIN, "-y", "-i", str(src), "-c", "copy",
             "-movflags", "+faststart", str(dst)]
        )
    return _run(
        [
            config.FFMPEG_BIN, "-y",
            "-i", str(src),
            "-stream_loop", "-1", "-i", str(music),
            "-filter_complex",
            "[1:a]volume=-15dB[bg];"
            "[0:a][bg]amix=inputs=2:duration=first:dropout_transition=0,"
            "dynaudnorm[a]",
            "-map", "0:v", "-map", "[a]",
            "-c:v", "copy", "-c:a", "aac", "-shortest",
            "-movflags", "+faststart", str(dst),
        ]
    )


def _label(c: dict) -> str:
    tags = " · ".join(c.get("tags", [])[:4])
    name = c.get("playerName", c.get("player", ""))
    return f"{name}  —  {tags}" if tags else name


def _assemble(clips: list[dict], clips_root: Path, out: Path, work: Path) -> bool:
    """clips já na ordem desejada. Retorna True se gerou `out`."""
    norm_parts: list[Path] = []
    for i, c in enumerate(clips):
        src = clips_root / c["player"]
        # aceita clip_NN.mp4 ou clip_NN.<ext>
        matches = sorted(src.glob(f"clip_{c['index']:02d}.*"))
        if not matches:
            _log(f"clipe ausente: {src}/clip_{c['index']:02d}.* — pulando")
            continue
        dst = work / f"norm_{out.stem}_{i:03d}.mp4"
        if _normalize(matches[0], dst, _label(c)):
            norm_parts.append(dst)
    if not norm_parts:
        return False

    concat_tmp = work / f"concat_{out.stem}.mp4"
    if not _concat(norm_parts, concat_tmp):
        return False
    out.parent.mkdir(parents=True, exist_ok=True)
    ok = _add_music(concat_tmp, out)
    for p in norm_parts + [concat_tmp]:
        p.unlink(missing_ok=True)
    return ok


def build(job_id: str, job_path: Path, report: dict) -> list[str]:
    clips_json = job_path / "clips.json"
    if not clips_json.exists():
        raise RuntimeError("clips.json não encontrado (a gravação rodou?).")
    clips: list[dict] = json.loads(clips_json.read_text("utf-8"))
    clips_root = job_path / "clips"
    montage_dir = job_path / "montage"
    montage_dir.mkdir(parents=True, exist_ok=True)
    outputs: list[str] = []

    with tempfile.TemporaryDirectory(prefix="hl_montage_") as td:
        work = Path(td)

        # por jogador (ordem: melhor score primeiro)
        by_player: dict[str, list[dict]] = {}
        for c in clips:
            by_player.setdefault(c["player"], []).append(c)
        for slug, cs in by_player.items():
            cs_sorted = sorted(cs, key=lambda c: c.get("score", 0), reverse=True)
            out = montage_dir / f"final_{slug}.mp4"
            if _assemble(cs_sorted, clips_root, out, work):
                outputs.append(out.name)
                _log(f"ok: {out.name} ({len(cs_sorted)} clipes)")

        # montagem combinada da partida
        if config.MONTAGE_COMBINED and clips:
            top = sorted(clips, key=lambda c: c.get("score", 0), reverse=True)[:24]
            out = montage_dir / "final_partida.mp4"
            if _assemble(top, clips_root, out, work):
                outputs.append(out.name)
                _log(f"ok: {out.name} ({len(top)} clipes)")

    if not outputs:
        raise RuntimeError("Montagem não gerou nenhum arquivo.")
    return outputs
