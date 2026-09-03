"""Leitura centralizada de configuração (env + state/config.json).

Mesmo papel do python/config.py do projeto de referência: um único ponto
que lê variáveis de ambiente e expõe constantes tipadas para o resto do
código. Os pesos de pontuação ficam num JSON editável em
state/config.json (com defaults embutidos, então funciona sem o arquivo).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

try:  # opcional — só pra rodar o CLI fora do Next
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    def load_dotenv(*_a, **_k):  # type: ignore
        return False

PYTHON_DIR = Path(__file__).resolve().parent
REPO_ROOT = PYTHON_DIR.parent
load_dotenv(REPO_ROOT / ".env")


def _path(env_name: str, default: Path) -> Path:
    raw = os.environ.get(env_name)
    if not raw:
        return default
    p = Path(raw)
    return p if p.is_absolute() else (REPO_ROOT / p).resolve()


def _float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, "1" if default else "0").strip() == "1"


STATE_DIR = _path("STATE_DIR", PYTHON_DIR / "state")
JOBS_DIR = STATE_DIR / "jobs"
ASSETS_DIR = PYTHON_DIR / "assets"

# ─── detecção ──────────────────────────────────────────────────────────────
# Filtro PRIMÁRIO de sequência. Não zera um jogador que teve kills — se
# nenhuma sequência passar, o melhor lance dele entra assim mesmo
# (ver scoring.build_report).
SCORE_MIN = _float("SCORE_MIN", 3.0)
PER_PLAYER_TOP_N = _int("PER_PLAYER_TOP_N", 5)
CLIP_PREROLL_SECONDS = _float("CLIP_PREROLL_SECONDS", 4.0)
CLIP_POSTROLL_SECONDS = _float("CLIP_POSTROLL_SECONDS", 3.0)
# Teto de duração do clipe. Só corta o PRÉ-roll se estourar — nunca a parte
# com as kills. Com o agrupamento por rajada raramente é atingido.
MAX_CLIP_SECONDS = _float("MAX_CLIP_SECONDS", 40.0)
# Gap máx. entre kills pra contarem como a MESMA rajada (2K/3K/4K/ACE).
SEQUENCE_GAP_SECONDS = _float("SEQUENCE_GAP_SECONDS", 10.0)
# Pausa o job após a pontuação pra você escolher jogadores/lances no painel
# antes de gravar. Ligado por padrão quando RECORDER_ENABLED=1 (senão os
# vídeos ficam enormes). REVIEW_MODE=0 força gravar todo mundo.
REVIEW_MODE = _bool("REVIEW_MODE", True)
# Fallback quando o header do demo não traz tickrate.
DEFAULT_TICKRATE = _int("DEMO_TICKRATE", 64)

# ─── gravação (Fases 2/3) ─────────────────────────────────────────────────
RECORDER_ENABLED = _bool("RECORDER_ENABLED", False)
# screen = CS2 controlado pelo console (-netconport) + captura de tela via
#          ffmpeg. É o único backend implementado.
RECORDER_BACKEND = os.environ.get("RECORDER_BACKEND", "screen").strip() or "screen"
# Porta do console TCP do CS2 (-netconport). O recorder conecta nela pra
# mandar demo_gototick / spec_lock_to_accountid.
NETCON_PORT = _int("NETCON_PORT", 29999)
NETCON_CONNECT_TIMEOUT = _int("NETCON_CONNECT_TIMEOUT", 180)
# Segundos de reprodução normal do demo antes do 1º demo_gototick — evita o
# crash "CopyNewEntity: invalid class index ... out of range 0" (tabelas de
# entidade ainda não prontas).
RECORD_DEMO_WARMUP = _int("RECORD_DEMO_WARMUP", 20)
# ddagrab (Desktop Duplication, GPU — robusto em captura longa) |
# gdigrab (compatível, captura a tela toda) |
# gdigrab-window (captura só a janela "Counter-Strike 2")
RECORD_CAPTURE = os.environ.get("RECORD_CAPTURE", "ddagrab").strip() or "ddagrab"
CS2_EXE = os.environ.get("CS2_EXE", "").strip()
CS2_DEMOS_DIR = os.environ.get("CS2_DEMOS_DIR", "").strip()
HLAE_EXE = os.environ.get("HLAE_EXE", "").strip()
FFMPEG_BIN = os.environ.get("FFMPEG_BIN", "ffmpeg").strip() or "ffmpeg"
# Resolução/fps da gravação de tela.
RECORD_RESOLUTION = os.environ.get("RECORD_RESOLUTION", "1920x1080").strip()
RECORD_FPS = _int("RECORD_FPS", 60)
# Corte de segurança: mata o CS2 se a reprodução passar disso (segundos).
RECORD_TIMEOUT = _int("RECORD_TIMEOUT", 1800)
# Opcional: dispositivo dshow pra capturar o áudio do jogo (backend screen).
RECORD_AUDIO_DEVICE = os.environ.get("RECORD_AUDIO_DEVICE", "").strip()
# Folga (segundos) adicionada antes/depois de cada lance ao recortar — o
# con_timestamp do CS2 tem resolução de 1s.
RECORD_CUT_PAD = _float("RECORD_CUT_PAD", 2.0)

# ─── montagem (Fase 3) ────────────────────────────────────────────────────
# Junta TODOS os lances num único final_partida.mp4. Desligado por padrão —
# o produto principal é 1 vídeo independente por lance (clips/<jogador>/).
MONTAGE_COMBINED = _bool("MONTAGE_COMBINED", False)
MONTAGE_RESOLUTION = os.environ.get("MONTAGE_RESOLUTION", "1920x1080").strip()
MONTAGE_FPS = _int("MONTAGE_FPS", 60)
MONTAGE_MUSIC = _path("MONTAGE_MUSIC", ASSETS_DIR / "music.mp3")


# ─── pesos de pontuação ───────────────────────────────────────────────────
DEFAULT_WEIGHTS: dict[str, float] = {
    "kill": 1.0,
    "headshot": 0.5,
    "wallbang": 1.5,
    "noscope": 2.0,
    "knife": 3.0,
    "smoke": 1.0,
    "blind": 1.0,
    "airborne": 1.5,
    "long_range": 1.0,
    "fast_kill": 0.75,
    "round_win_kill": 1.0,
}
DEFAULT_MULTIKILL: dict[str, float] = {"2": 1.0, "3": 3.0, "4": 6.0, "5": 12.0}
DEFAULT_CLUTCH_PER_ENEMY = 3.0
LONG_RANGE_UNITS = 1900.0
FAST_KILL_SECONDS = 1.2


def load_weights() -> dict:
    """DEFAULT_* mesclado com state/config.json, se existir."""
    cfg = {
        "weights": dict(DEFAULT_WEIGHTS),
        "multikill": dict(DEFAULT_MULTIKILL),
        "clutch_per_enemy": DEFAULT_CLUTCH_PER_ENEMY,
        "long_range_units": LONG_RANGE_UNITS,
        "fast_kill_seconds": FAST_KILL_SECONDS,
    }
    path = STATE_DIR / "config.json"
    if path.exists():
        try:
            user = json.loads(path.read_text("utf-8"))
        except (OSError, ValueError):
            return cfg
        for k in ("weights", "multikill"):
            if isinstance(user.get(k), dict):
                cfg[k].update({str(kk): float(vv) for kk, vv in user[k].items()})
        for k in ("clutch_per_enemy", "long_range_units", "fast_kill_seconds"):
            if k in user:
                cfg[k] = float(user[k])
    return cfg
