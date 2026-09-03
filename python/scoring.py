"""Motor de highlights: agrupa as kills de cada jogador em sequências,
pontua cada sequência e monta o relatório final agrupado por jogador.
"""

from __future__ import annotations

import re

import config


def _slug(name: str) -> str:
    s = re.sub(r"[^A-Za-z0-9_-]+", "_", _display_name(name)).strip("_")
    return s or "player"


def _valid_steamid(sid: str) -> bool:
    """steamId64 de conta individual do CS2."""
    return bool(sid) and sid.isdigit() and len(sid) == 17 and sid.startswith("7656119")


def _round_number(rounds: list[dict], tick: int) -> int:
    """Número 1-based do round que contém `tick` (por faixa de tick)."""
    for i, r in enumerate(rounds):
        if r.get("startTick", 0) <= tick <= r.get("endTick", 0):
            return i + 1
    return sum(1 for r in rounds if r.get("endTick", 0) < tick) + 1


# Selos que a GamersClub/torneios grudam no nick e que a maioria das fontes
# não renderiza: números/letras circulados, símbolos/dingbats, © ® ™, emoji.
_BADGE_CLASS = (
    "©®™"          # © ® ™
    "①-⓿"              # enclosed alphanumerics ① .. ⓿
    "☀-➿"              # misc symbols + dingbats  ★ ☆ ✓ ✗ ...
    "⬀-⯿"              # stars/arrows extras
    "\U0001f000-\U0001faff"      # emoji
)
_BADGE_RE = re.compile(f"^[\\s{_BADGE_CLASS}]+|[\\s{_BADGE_CLASS}]+$")


def _display_name(name: str) -> str:
    """Tira os selos do começo/fim do nick, mantendo o nome de verdade."""
    cleaned = _BADGE_RE.sub("", name or "").strip()
    return cleaned or (name or "").strip() or "?"


def _round_for_tick(rounds: list[dict], tick: int) -> dict | None:
    """Round que contém `tick` (casado por faixa startTick..endTick, não por
    número — a numeração de round_end e de total_rounds_played nem sempre
    bate). Cai no round mais próximo se nada contiver exatamente."""
    for r in rounds:
        if r.get("startTick", 0) <= tick <= r.get("endTick", 0):
            return r
    nearest, best = None, None
    for r in rounds:
        d = abs(r.get("endTick", 0) - tick)
        if best is None or d < best:
            best, nearest = d, r
    return nearest


def _round_bounds(rounds: list[dict], tick: int) -> tuple[int, int]:
    r = _round_for_tick(rounds, tick)
    if not r:
        return 0, 0
    return r.get("startTick", 0), r.get("endTick", 0) or 0


def group_sequences(
    kills: list[dict],
    tickrate: int,
    gap_seconds: float,
) -> list[list[dict]]:
    """Kills de UM jogador -> sequências = RAJADAS de kills próximas no tempo
    (estilo Highlights da Gamers Club).

    Uma sequência é uma corrida de kills onde cada uma está a no máximo
    `gap_seconds` da anterior, no mesmo round. NÃO junta o round inteiro:
    um "4K" com as mortes espalhadas por 100s vira várias sequências curtas
    (a maioria de 1 kill, filtradas depois), e o que sobra é a rajada de
    verdade — que aí sim dá pra gravar completa.
    """
    if not kills:
        return []
    by_round: dict[int, list[dict]] = {}
    for k in kills:
        by_round.setdefault(k["round"], []).append(k)

    gap_ticks = gap_seconds * tickrate
    seqs: list[list[dict]] = []
    for rnd in sorted(by_round):
        rk = sorted(by_round[rnd], key=lambda x: x["tick"])
        cur = [rk[0]]
        for k in rk[1:]:
            if (k["tick"] - cur[-1]["tick"]) <= gap_ticks:
                cur.append(k)
            else:
                seqs.append(cur)
                cur = [k]
        seqs.append(cur)
    return seqs


def detect_clutches(
    kills: list[dict],
    rounds: list[dict],
) -> dict[tuple[str, int], int]:
    """Retorna {(steamid, round): n_inimigos} para clutches vencidos 1vN.

    Heurística por round (assume 5v5 no início): percorre as kills em ordem
    de tick, mantém quantos vivos por lado. Quando um lado cai para 1,
    guarda quantos inimigos estavam vivos naquele instante (o "N" do 1vN);
    o sobrevivente é o 1º atacante desse lado, ainda vivo, dali em diante.
    Marca o clutch só se esse lado venceu o round e N >= 2.
    """
    result: dict[tuple[str, int], int] = {}

    by_round: dict[int, list[dict]] = {}
    for k in kills:
        by_round.setdefault(k["round"], []).append(k)

    for rnd, rk in by_round.items():
        rk = sorted(rk, key=lambda x: x["tick"])
        # vencedor casado pelo tick da última kill (numeração de round não
        # bate entre round_end e total_rounds_played)
        wr = _round_for_tick(rounds, rk[-1]["tick"])
        winner = wr["winner"] if wr else "UNKNOWN"

        alive = {"CT": 5, "TERRORIST": 5}
        dead: set[str] = set()
        pending: dict[str, int] = {}   # time -> inimigos vivos ao cair pra 1
        clutcher: dict[str, str] = {}  # time -> steamid do sobrevivente

        for k in rk:
            vteam = k["victimTeam"]
            if vteam in alive and k["victim"] and k["victim"] not in dead:
                alive[vteam] -= 1
                dead.add(k["victim"])

            for team in ("CT", "TERRORIST"):
                enemy = "TERRORIST" if team == "CT" else "CT"
                if alive[team] == 1 and team not in pending:
                    pending[team] = max(alive[enemy], 0)

            atk_team = k["attackerTeam"]
            if (
                atk_team in pending
                and atk_team not in clutcher
                and k["attacker"]
                and k["attacker"] not in dead
            ):
                clutcher[atk_team] = k["attacker"]

        if winner in clutcher and pending.get(winner, 0) >= 2:
            result[(clutcher[winner], rnd)] = pending[winner]

    return result


def score_sequence(
    seq: list[dict],
    tickrate: int,
    rounds: list[dict],
    cfg: dict,
    clutch_n: int = 0,
) -> tuple[float, list[str], int]:
    w = cfg["weights"]
    mk = cfg["multikill"]
    n = len(seq)
    score = n * w["kill"]
    tags: list[str] = []

    hs = sum(1 for k in seq if k["headshot"])
    wallbangs = sum(1 for k in seq if k["penetrated"] > 0)
    noscopes = sum(1 for k in seq if k["noscope"])
    knives = sum(1 for k in seq if "knife" in k["weapon"] or "bayonet" in k["weapon"])
    smokes = sum(1 for k in seq if k["thrusmoke"])
    blinds = sum(1 for k in seq if k["attackerblind"])
    longs = sum(1 for k in seq if k["distance"] >= cfg["long_range_units"])

    score += hs * w["headshot"]
    score += wallbangs * w["wallbang"]
    score += noscopes * w["noscope"]
    score += knives * w["knife"]
    score += smokes * w["smoke"]
    score += blinds * w["blind"]
    score += longs * w["long_range"]

    # kills rápidas em sequência
    fast = 0
    for a, b in zip(seq, seq[1:]):
        if (b["tick"] - a["tick"]) / tickrate <= cfg["fast_kill_seconds"]:
            fast += 1
    score += fast * w["fast_kill"]

    # multikill
    if n >= 2:
        score += mk.get(str(min(n, 5)), 0.0)
        tags.append("ACE" if n >= 5 else f"{n}K")

    airborne = sum(1 for k in seq if k.get("airborne"))
    score += airborne * w.get("airborne", 1.5)

    # round-win kill: última kill da sequência é a última do round e o time ganhou
    last = seq[-1]
    r = _round_for_tick(rounds, last["tick"])
    round_kills = _all_round_kills.get(last["round"], [])
    if r and round_kills:
        last_of_round = max(round_kills, key=lambda k: k["tick"])
        if last_of_round["tick"] == last["tick"] and r["winner"] == last["attackerTeam"]:
            score += w["round_win_kill"]
            tags.append("RWK")

    if clutch_n >= 2:
        score += clutch_n * cfg["clutch_per_enemy"]
        tags.append(f"1v{clutch_n}")

    if hs >= 2:
        tags.append(f"{hs}HS")
    if airborne:
        tags.append("airborne")
    if wallbangs:
        tags.append("wallbang")
    if noscopes:
        tags.append("noscope")
    if knives:
        tags.append("knife")
    if smokes:
        tags.append("smoke")
    if blinds:
        tags.append("blind")
    if longs:
        tags.append("longrange")

    return round(score, 2), tags, n


# preenchido por build_report antes de pontuar (evita recomputar por sequência)
_all_round_kills: dict[int, list[dict]] = {}


def build_report(job_id: str, parsed: dict) -> dict:
    cfg = config.load_weights()
    tickrate = parsed["tickrate"]
    kills = parsed["kills"]
    rounds = parsed["rounds"]

    global _all_round_kills
    _all_round_kills = {}
    for k in kills:
        _all_round_kills.setdefault(k["round"], []).append(k)

    clutches = detect_clutches(kills, rounds)
    demo_end = max((k["tick"] for k in kills), default=0) + tickrate * 10

    players_out: list[dict] = []
    for sid, pl in parsed["players"].items():
        pk = [k for k in kills if k["attacker"] == sid]
        if not pk:
            continue
        seqs = group_sequences(pk, tickrate, config.SEQUENCE_GAP_SECONDS)

        acc = pl.get("accountId", 0)
        team = pl.get("team", "UNKNOWN")
        pov_valid = _valid_steamid(sid) and acc > 0

        candidates: list[dict] = []
        for seq in seqs:
            rnd = seq[0]["round"]
            cn = clutches.get((sid, rnd), 0)
            score, tags, kc = score_sequence(seq, tickrate, rounds, cfg, cn)

            first_t = seq[0]["tick"]
            last_t = seq[-1]["tick"]
            start_tick, end_tick = _round_bounds(rounds, last_t)

            # janela = preroll antes da 1ª kill .. postroll depois da última.
            clip_end = last_t + round(config.CLIP_POSTROLL_SECONDS * tickrate)
            if end_tick:
                clip_end = min(clip_end, end_tick + round(2.0 * tickrate))
            clip_end = min(clip_end, demo_end)

            clip_start = max(
                start_tick,
                first_t - round(config.CLIP_PREROLL_SECONDS * tickrate),
            )
            # teto só pra casos patológicos — corta o PRÉ-roll, jamais a
            # parte com as kills (first_t..last_t continua inteira).
            max_ticks = round(config.MAX_CLIP_SECONDS * tickrate)
            if clip_end - clip_start > max_ticks:
                clip_start = max(
                    start_tick,
                    min(first_t - round(1.0 * tickrate), clip_end - max_ticks),
                )

            candidates.append(
                {
                    "id": 0,
                    "score": score,
                    # round (0-based do total_rounds_played, back-compat) +
                    # roundNumber (1-based, casado por tick — é o "Round N").
                    "round": rnd,
                    "roundNumber": _round_number(rounds, first_t),
                    "tickStart": clip_start,
                    "tickEnd": clip_end,
                    "timeStart": round(clip_start / tickrate, 2),
                    "timeEnd": round(clip_end / tickrate, 2),
                    "tags": tags,
                    "killCount": kc,
                    # ── vínculo obrigatório evento -> jogador -> POV ──
                    "steamId64": sid,
                    "accountId": acc,
                    "povAccountId": acc,   # POV == jogador do evento
                    "playerName": _display_name(pl["name"]),
                    "team": team,
                    "povValid": pov_valid,
                    "kills": [
                        {
                            "tick": k["tick"],
                            "victim": k["victim"],
                            "weapon": k["weapon"],
                            "headshot": k["headshot"],
                            "noscope": k["noscope"],
                            "penetrated": k["penetrated"],
                        }
                        for k in seq
                    ],
                }
            )

        candidates.sort(key=lambda h: h["score"], reverse=True)

        # Regra: todo jogador com >=1 kill entra. SCORE_MIN e "multikill"
        # são filtro PRIMÁRIO; se isso zerar um jogador que teve kills,
        # cai pro melhor lance dele mesmo assim (nunca some da lista).
        primary = [
            h
            for h in candidates
            if h["score"] >= config.SCORE_MIN or h["killCount"] >= 2
        ]
        highlights = (primary or candidates[:1])[: config.PER_PLAYER_TOP_N]
        for i, h in enumerate(highlights, 1):
            h["id"] = i
        if not highlights:
            continue

        total = round(sum(h["score"] for h in highlights), 2)
        players_out.append(
            {
                "steamId64": sid,
                "accountId": pl.get("accountId", 0),
                "name": pl["name"],
                "displayName": _display_name(pl["name"]),
                "slug": _slug(pl["name"]),
                "team": pl.get("team", "UNKNOWN"),
                "stats": pl.get(
                    "stats",
                    {"kills": 0, "deaths": 0, "assists": 0, "headshotPct": 0},
                ),
                "totalScore": total,
                "highlights": highlights,
            }
        )

    players_out.sort(key=lambda p: p["totalScore"], reverse=True)
    ranking = [
        {"steamId64": p["steamId64"], "name": p["name"], "totalScore": p["totalScore"]}
        for p in players_out
    ]

    # ── lista PLANA de highlights independentes (Partida -> Highlight 1..N) ──
    # Mesmos objetos que estão em players[].highlights (referência), então
    # globalId/player valem nos dois lugares.
    flat: list[dict] = []
    for p in players_out:
        for h in p["highlights"]:
            h["player"] = p["slug"]          # slug -> pasta/arquivo do clipe
            h["playerDisplayName"] = p["displayName"]
            flat.append(h)
    flat.sort(key=lambda h: (h["roundNumber"], h["tickStart"]))
    for i, h in enumerate(flat, 1):
        h["globalId"] = i

    return {
        "jobId": job_id,
        "map": parsed["map"],
        "matchScore": parsed["matchScore"],
        "tickrate": tickrate,
        "players": players_out,
        "highlights": flat,
        "ranking": ranking,
    }
