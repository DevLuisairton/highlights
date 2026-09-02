"""Testes do motor de highlights (não dependem do demoparser2)."""

from __future__ import annotations

import config
import scoring
import vdmgen


def _kill(tick, rnd, atk, vic, atk_team="CT", vic_team="TERRORIST", **extra):
    base = {
        "tick": tick,
        "round": rnd,
        "attacker": atk,
        "attackerName": atk,
        "attackerTeam": atk_team,
        "victim": vic,
        "victimTeam": vic_team,
        "assister": None,
        "weapon": "ak47",
        "headshot": False,
        "penetrated": 0,
        "noscope": False,
        "thrusmoke": False,
        "attackerblind": False,
        "distance": 500.0,
    }
    base.update(extra)
    return base


def _parsed(kills, rounds, players):
    return {
        "map": "de_mirage",
        "tickrate": 64,
        "matchScore": "13-11",
        "players": players,
        "kills": kills,
        "rounds": rounds,
    }


def test_agrupa_por_jogador_e_pontua_multikill(monkeypatch):
    monkeypatch.setattr(config, "SCORE_MIN", 6.0)
    monkeypatch.setattr(config, "PER_PLAYER_TOP_N", 10)
    monkeypatch.setattr(config, "SEQUENCE_GAP_SECONDS", 8.0)

    kills = [
        _kill(1000, 1, "A", "t1", headshot=True),
        _kill(1050, 1, "A", "t2", headshot=True),
        _kill(1100, 1, "A", "t3"),
        _kill(1200, 1, "B", "t4"),   # 1 kill só -> vira o "melhor lance" de B
        _kill(1400, 2, "C", "t5"),   # C jogou mas... (ver stats abaixo)
    ]
    rounds = [{"round": 1, "endTick": 1300, "startTick": 0, "winner": "TERRORIST"}]
    players = {
        "A": {"steamId64": "A", "name": "A", "team": "CT", "accountId": 111,
              "stats": {"kills": 3, "deaths": 0, "assists": 0, "headshotPct": 67}},
        "B": {"steamId64": "B", "name": "B", "team": "CT", "accountId": 222,
              "stats": {"kills": 1, "deaths": 0, "assists": 0, "headshotPct": 0}},
        "Z": {"steamId64": "Z", "name": "Z", "team": "CT", "accountId": 333,
              "stats": {"kills": 0, "deaths": 5, "assists": 0, "headshotPct": 0}},
    }

    report = scoring.build_report("job", _parsed(kills, rounds, players))

    names = sorted(p["name"] for p in report["players"])
    # A e B entram (tiveram kills); Z (0 kills) é ignorado.
    assert names == ["A", "B"]
    b = next(p for p in report["players"] if p["name"] == "B")
    assert len(b["highlights"]) == 1  # melhor lance mesmo abaixo do SCORE_MIN

    a = next(p for p in report["players"] if p["name"] == "A")
    assert len(a["highlights"]) == 1
    hl = a["highlights"][0]
    assert hl["killCount"] == 3
    assert "3K" in hl["tags"]
    assert "2HS" in hl["tags"]
    # 3*kill(1.0) + 2*headshot(0.5) + multikill["3"](3.0) + 2*fast_kill(0.75)
    # (kills a 50 ticks = 0.78s uma da outra) = 8.5
    assert hl["score"] == 8.5
    assert report["ranking"][0]["name"] == "A"


def test_sequencias_quebram_por_gap():
    # 2 kills no round -> abaixo do ROUND_MERGE_MIN_KILLS, subdivide por gap
    kills = [
        _kill(1000, 1, "A", "t1"),
        _kill(1100, 1, "A", "t2"),   # +1.56s -> mesma sequência
        _kill(1000, 2, "A", "t3"),   # outro round
        _kill(1600, 2, "A", "t4"),   # +9.4s -> nova sequência
    ]
    seqs = scoring.group_sequences(kills, 64, 5.0)
    assert [len(s) for s in seqs] == [2, 1, 1]


def test_round_de_3k_vira_uma_sequencia_mesmo_espalhado():
    # 4 kills no mesmo round, longe uma da outra -> 1 sequência só
    kills = [
        _kill(1000, 7, "A", "t1"),
        _kill(1800, 7, "A", "t2"),
        _kill(2600, 7, "A", "t3"),
        _kill(3400, 7, "A", "t4"),
    ]
    seqs = scoring.group_sequences(kills, 64, 8.0)
    assert len(seqs) == 1
    assert len(seqs[0]) == 4


def test_clutch_detectado():
    # 2 CTs e 2 Ts já morreram; sobra o A (CT) contra 3 Ts; A mata os 3;
    # CT vence -> clutch 1v3.
    kills = [
        _kill(800, 5, "t1", "b2", atk_team="TERRORIST", vic_team="CT"),
        _kill(820, 5, "t2", "b3", atk_team="TERRORIST", vic_team="CT"),
        _kill(850, 5, "b4", "t1", atk_team="CT", vic_team="TERRORIST"),
        _kill(870, 5, "b5", "t2", atk_team="CT", vic_team="TERRORIST"),
        _kill(900, 5, "t3", "b4", atk_team="TERRORIST", vic_team="CT"),
        _kill(950, 5, "t3", "b5", atk_team="TERRORIST", vic_team="CT"),
        _kill(1000, 5, "A", "t3", atk_team="CT", vic_team="TERRORIST"),
        _kill(1050, 5, "A", "t4", atk_team="CT", vic_team="TERRORIST"),
        _kill(1100, 5, "A", "t5", atk_team="CT", vic_team="TERRORIST"),
    ]
    rounds = [{"round": 5, "endTick": 1200, "startTick": 0, "winner": "CT"}]
    got = scoring.detect_clutches(kills, rounds)
    assert got.get(("A", 5)) == 3


def test_vdm_ticks_crescentes_e_contagem_de_clipes():
    report = {
        "players": [
            {
                "steamId64": "A", "accountId": 111, "name": "Player One",
                "team": "CT", "totalScore": 10,
                "highlights": [
                    {"id": 1, "score": 7, "round": 1, "tickStart": 1000,
                     "tickEnd": 1400, "timeStart": 0, "timeEnd": 0,
                     "tags": ["3K"], "killCount": 3},
                ],
            },
            {
                "steamId64": "B", "accountId": 222, "name": "Player Two",
                "team": "TERRORIST", "totalScore": 6,
                "highlights": [
                    {"id": 1, "score": 6, "round": 2, "tickStart": 3000,
                     "tickEnd": 3300, "timeStart": 0, "timeEnd": 0,
                     "tags": ["2K"], "killCount": 2},
                ],
            },
        ],
    }
    content, clips = vdmgen.build_vdm(report)
    assert content.startswith("demoactions")
    assert len(clips) == 2
    assert clips[0]["stem"] == "clip_Player_One_01"
    assert clips[0]["playerName"] == "Player One"
    assert clips[0]["accountId"] == 111
    assert clips[0]["score"] == 7
    # ordenados por tickStart
    assert [c["tickStart"] for c in clips] == sorted(c["tickStart"] for c in clips)

    ticks = [
        int(line.split('"')[1])
        for line in content.splitlines()
        if "starttick" in line
    ]
    assert ticks == sorted(ticks)


def test_selecao_de_jogador_filtra_os_clipes():
    report = {
        "players": [
            {
                "steamId64": "A", "accountId": 111, "name": "AAA", "team": "CT",
                "highlights": [
                    {"id": 1, "score": 9, "round": 1, "tickStart": 100,
                     "tickEnd": 200, "tags": ["3K"], "killCount": 3},
                    {"id": 2, "score": 4, "round": 3, "tickStart": 900,
                     "tickEnd": 950, "tags": ["2K"], "killCount": 2},
                ],
            },
            {
                "steamId64": "B", "accountId": 222, "name": "BBB", "team": "T",
                "highlights": [
                    {"id": 1, "score": 6, "round": 2, "tickStart": 400,
                     "tickEnd": 480, "tags": ["2K"], "killCount": 2},
                ],
            },
        ],
    }
    # só o jogador A, só o highlight 1
    _, clips = vdmgen.build_vdm(report, keep={"A": [1], "B": []})
    assert [c["steamId64"] for c in clips] == ["A"]
    assert [c["highlightId"] for c in clips] == [1]

    # sem keep = todos
    _, all_clips = vdmgen.build_vdm(report)
    assert len(all_clips) == 3
