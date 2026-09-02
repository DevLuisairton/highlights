"""Camada de parsing: .dem de CS2 -> dict de eventos normalizados.

Usa demoparser2 (core em Rust). Notas de campo (confirmadas contra demos
reais de CS2, set/2026):

- `player_death` NÃO traz o time do atacante/vítima por padrão. É preciso
  pedir via `player=["team_name"]`, que adiciona `attacker_team_name` e
  `user_team_name` (valores "CT" / "TERRORIST").
- Colunas ausentes vêm como NaN (float) — vira o texto "nan" se convertido
  direto. `_clean` trata NaN/"nan"/"none"/"" como vazio.
- `round_end.winner` é "CT" / "T" (maiúsculo), com uma 1ª linha espúria
  (tick=1, winner=NaN). `round_end.round` existe e é usado pros limites.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import Any, Callable

STEAMID64_BASE = 76561197960265728

ProgressCb = Callable[[float, str], None]


def _log(msg: str) -> None:
    print(f"[parsing] {msg}", file=sys.stderr, flush=True)


def _records(df: Any) -> list[dict]:
    if df is None:
        return []
    try:
        if getattr(df, "empty", False):
            return []
        return df.to_dict("records")
    except Exception:  # pragma: no cover
        try:
            return list(df)
        except Exception:
            return []


def _is_missing(v: Any) -> bool:
    if v is None:
        return True
    if isinstance(v, float) and math.isnan(v):
        return True
    if isinstance(v, str) and v.strip().lower() in ("", "nan", "none", "null"):
        return True
    return False


def _clean(v: Any) -> str:
    """String limpa ('' quando ausente/NaN)."""
    return "" if _is_missing(v) else str(v).strip()


def _first(d: dict, *keys: str, default=None):
    for k in keys:
        if k in d and not _is_missing(d[k]):
            return d[k]
    return default


def _team(value: Any) -> str:
    """Normaliza time -> 'CT' | 'TERRORIST' | 'UNKNOWN' (qualquer forma/caixa)."""
    if _is_missing(value):
        return "UNKNOWN"
    s = str(value).strip().upper()
    if s in ("CT", "3", "COUNTER-TERRORIST", "COUNTERTERRORIST", "CTS"):
        return "CT"
    if s in ("T", "TERRORIST", "TERRORISTS", "2"):
        return "TERRORIST"
    return "UNKNOWN"


def _to_int(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _account_id(steamid64: Any) -> int:
    sid = _to_int(steamid64, 0)
    return sid - STEAMID64_BASE if sid > STEAMID64_BASE else 0


def _parse_deaths(parser: Any) -> list[dict]:
    """Tenta variantes de argumentos até uma trazer as mortes (com time)."""
    variants = [
        dict(player=["team_name", "team_num"],
             other=["total_rounds_played", "is_warmup_period"]),
        dict(player=["team_name"],
             other=["total_rounds_played", "is_warmup_period"]),
        dict(player=["team_name"], other=["total_rounds_played"]),
        dict(other=["total_rounds_played", "is_warmup_period"]),
        dict(other=["total_rounds_played"]),
        dict(),
    ]
    for kw in variants:
        try:
            rows = _records(parser.parse_event("player_death", **kw))
        except Exception as e:
            _log(f"player_death {kw}: {e}")
            continue
        if rows:
            has_team = any(
                not _is_missing(r.get("attacker_team_name"))
                or not _is_missing(r.get("attacker_team_num"))
                for r in rows[:20]
            )
            _log(f"player_death ok ({len(rows)} linhas, time={'sim' if has_team else 'não'})")
            return rows
    return []


def parse_demo(demo_path: str | Path, progress: ProgressCb | None = None) -> dict:
    from demoparser2 import DemoParser

    demo_path = str(demo_path)
    p = progress or (lambda _pct, _msg: None)

    p(5, "abrindo demo")
    parser = DemoParser(demo_path)
    failures = 0

    header: dict = {}
    try:
        header = parser.parse_header() or {}
    except Exception as e:  # pragma: no cover
        failures += 1
        _log(f"parse_header falhou: {e}")
    map_name = str(_first(header, "map_name", "map", default="desconhecido"))

    tickrate = 64
    try:
        ticks = float(header.get("playback_ticks", 0))
        secs = float(header.get("playback_time", 0))
        if ticks > 0 and secs > 0:
            tickrate = round(ticks / secs)
    except (TypeError, ValueError):
        pass
    if tickrate <= 0:
        tickrate = 64

    p(20, "lendo mortes")
    deaths_raw = _parse_deaths(parser)
    if not deaths_raw:
        failures += 1

    kills: list[dict] = []
    players: dict[str, dict] = {}

    for row in deaths_raw:
        if _first(row, "is_warmup_period", default=False):
            continue
        atk_sid = _clean(_first(row, "attacker_steamid"))
        vic_sid = _clean(_first(row, "user_steamid", "victim_steamid"))
        if not atk_sid or atk_sid == "0" or atk_sid == vic_sid:
            continue  # suicídio / dano de mundo — não vira highlight

        atk_name = _clean(_first(row, "attacker_name")) or "?"
        vic_name = _clean(_first(row, "user_name", "victim_name")) or "?"
        atk_team = _team(
            _first(row, "attacker_team_name", "attacker_team", "attacker_team_num")
        )
        vic_team = _team(
            _first(row, "user_team_name", "victim_team", "user_team_num")
        )

        pl = players.setdefault(
            atk_sid, {"steamId64": atk_sid, "name": atk_name, "team": atk_team}
        )
        pl["name"] = atk_name
        if atk_team != "UNKNOWN":
            pl["team"] = atk_team
        if vic_sid and vic_sid != "0":
            vp = players.setdefault(
                vic_sid, {"steamId64": vic_sid, "name": vic_name, "team": vic_team}
            )
            if vic_team != "UNKNOWN":
                vp["team"] = vic_team

        assister_sid = _clean(_first(row, "assister_steamid"))

        kills.append(
            {
                "tick": _to_int(_first(row, "tick", default=0)),
                "round": _to_int(_first(row, "total_rounds_played", default=0)),
                "attacker": atk_sid,
                "attackerName": atk_name,
                "attackerTeam": atk_team,
                "victim": vic_sid,
                "victimTeam": vic_team,
                "assister": assister_sid or None,
                "weapon": _clean(_first(row, "weapon")),
                "headshot": bool(_first(row, "headshot", default=False)),
                "penetrated": _to_int(_first(row, "penetrated", default=0)),
                "noscope": bool(_first(row, "noscope", default=False)),
                "thrusmoke": bool(_first(row, "thrusmoke", "through_smoke", default=False)),
                "attackerblind": bool(_first(row, "attackerblind", "attacker_blind", default=False)),
                "airborne": bool(_first(row, "attackerinair", "attacker_in_air", default=False)),
                "distance": float(_first(row, "distance", default=0.0) or 0.0),
            }
        )

    kills.sort(key=lambda k: k["tick"])
    p(60, "lendo rounds")

    rounds: list[dict] = []
    try:
        seen: set[int] = set()
        for row in _records(parser.parse_event("round_end")):
            winner = _team(_first(row, "winner"))
            end_tick = _to_int(_first(row, "tick", default=0))
            rnum = _to_int(_first(row, "round", "total_rounds_played", default=len(rounds)))
            if end_tick <= 1 or winner == "UNKNOWN":
                continue  # linha espúria (tick=1, winner=NaN)
            if rnum in seen:
                continue
            seen.add(rnum)
            rounds.append({"round": rnum, "endTick": end_tick, "winner": winner})
    except Exception as e:
        failures += 1
        _log(f"parse_event(round_end) falhou: {e}")
    rounds.sort(key=lambda r: r["endTick"])
    for i, r in enumerate(rounds):
        r["startTick"] = rounds[i - 1]["endTick"] if i > 0 else 0

    if failures >= 2 and not kills and not rounds:
        raise ValueError(
            "Não foi possível ler o demo (arquivo inválido, corrompido ou "
            "não é um .dem de CS2 / Source 2)."
        )

    p(80, "consolidando jogadores")

    for sid, pl in players.items():
        k = [x for x in kills if x["attacker"] == sid]
        d = [x for x in kills if x["victim"] == sid]
        a = [x for x in kills if x["assister"] == sid]
        hs = sum(1 for x in k if x["headshot"])
        pl["accountId"] = _account_id(sid)
        pl["stats"] = {
            "kills": len(k),
            "deaths": len(d),
            "assists": len(a),
            "headshotPct": round(100 * hs / len(k)) if k else 0,
        }

    ct_wins = sum(1 for r in rounds if r["winner"] == "CT")
    t_wins = sum(1 for r in rounds if r["winner"] == "TERRORIST")
    match_score = "?" if ct_wins + t_wins == 0 else f"{max(ct_wins, t_wins)}-{min(ct_wins, t_wins)}"

    p(100, "parsing concluído")

    return {
        "map": map_name,
        "tickrate": tickrate,
        "matchScore": match_score,
        "players": players,
        "kills": kills,
        "rounds": rounds,
    }
