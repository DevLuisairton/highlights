"""Geração do arquivo .vdm (Valve Demo Metafile).

O CS2 ainda lê VDM: um arquivo com o mesmo nome-base do .dem, na mesma
pasta, com ações que o player de demo executa em ticks específicos.

A partir de TODOS os highlights selecionados (de todos os jogadores),
ordenados por tick, o VDM:
  1. no começo: `con_timestamp 1` + limpa HUD + marcador de sessão;
  2. pula pro 1º highlight (SkipAhead);
  3. em cada highlight: trava a câmera no dono (spec_lock_to_accountid) e,
     se `include_recording`, dispara a gravação conforme o backend:
       - screen : `echo` de marcadores no console.log (recorte via ffmpeg);
       - native : `startmovie <clip> h264` / `endmovie`;
       - hlae   : `mirv_streams record start` / `end`;
  4. pula pro highlight seguinte;
  5. no fim: marcador de sessão + `quit`.

Sem `include_recording` o VDM vira um "tour" dos melhores momentos pra
assistir no CS2.
"""

from __future__ import annotations

import re

#: token dos marcadores escritos no console.log (backend screen).
MARKER = "HILLIGHTS"


def _slug(name: str) -> str:
    s = re.sub(r"[^A-Za-z0-9_-]+", "_", name).strip("_")
    return s or "player"


def _flatten(report: dict, keep: dict[str, list[int]] | None) -> list[dict]:
    """Highlights de todos os jogadores, com metadados do dono, ordenados
    por tickStart. `keep` (modo review) filtra por id de highlight."""
    items: list[dict] = []
    for p in report["players"]:
        allowed = keep.get(p["steamId64"]) if keep else None
        for h in p["highlights"]:
            if allowed is not None and h["id"] not in allowed:
                continue
            items.append(
                {
                    "steamId64": p["steamId64"],
                    "accountId": p["accountId"],
                    "playerName": p.get("displayName") or p["name"],
                    "playerSlug": p.get("slug") or _slug(p["name"]),
                    "team": p.get("team", "UNKNOWN"),
                    "highlightId": h["id"],
                    "score": h["score"],
                    "tags": h.get("tags", []),
                    "round": h["round"],
                    "tickStart": h["tickStart"],
                    "tickEnd": h["tickEnd"],
                }
            )
    items.sort(key=lambda x: x["tickStart"])
    return items


def build_vdm(
    report: dict,
    keep: dict[str, list[int]] | None = None,
    include_recording: bool = False,
    backend: str = "screen",
    fps: int = 60,
) -> tuple[str, list[dict]]:
    """Retorna (conteúdo_do_vdm, lista_de_clipes).

    clips: [{file, player, playerName, steamId64, index, highlightId,
             score, tags, round, tickStart, tickEnd}] — usada pela gravação
    (mapear marcador -> arquivo) e pela montagem (ordem por score, labels).
    """
    hls = _flatten(report, keep)
    actions: list[str] = []
    clips: list[dict] = []
    idx = 0

    def add(factory: str, name: str, starttick: int, extra: dict[str, str]) -> None:
        nonlocal idx
        idx += 1
        body = [
            f'\t\tfactory "{factory}"',
            f'\t\tname "{name}"',
            f'\t\tstarttick "{starttick}"',
        ]
        for k, v in extra.items():
            body.append(f'\t\t{k} "{v}"')
        actions.append('\t"%d"\n\t{\n%s\n\t}' % (idx, "\n".join(body)))

    if not hls:
        return "demoactions\n{\n}\n", clips

    # 1) setup no início da reprodução
    if include_recording:
        setup = [
            "con_timestamp 1",
            "cl_draw_only_deathnotices 1" if backend == "screen" else "cl_drawhud 1",
            f"host_framerate {fps}" if backend in ("native", "hlae") else "",
            f"echo {MARKER}|SESSION|START",
        ]
        add(
            "PlayCommands",
            "setup",
            48,
            {"commands": "; ".join(c for c in setup if c)},
        )

    # 2) pula do começo pro primeiro highlight
    add("SkipAhead", "skip_intro", 64, {"skiptotick": str(hls[0]["tickStart"])})

    per_player_count: dict[str, int] = {}
    for i, h in enumerate(hls):
        n = per_player_count.get(h["playerSlug"], 0) + 1
        per_player_count[h["playerSlug"]] = n
        clip_stem = f"clip_{h['playerSlug']}_{n:02d}"

        start_cmds = ["spec_mode 4", f"spec_lock_to_accountid {h['accountId']}"]
        end_cmds: list[str] = []
        if include_recording:
            if backend == "hlae":
                start_cmds.append("mirv_streams record start")
                end_cmds.append("mirv_streams record end")
            elif backend == "native":
                start_cmds.append(f"startmovie {clip_stem} h264")
                end_cmds.append("endmovie")
            else:  # screen
                start_cmds.append(f"echo {MARKER}|{clip_stem}|START")
                end_cmds.append(f"echo {MARKER}|{clip_stem}|END")

        add(
            "PlayCommands",
            f"hl_{i + 1}_start",
            h["tickStart"],
            {"commands": "; ".join(start_cmds)},
        )
        if end_cmds:
            add(
                "PlayCommands",
                f"hl_{i + 1}_stop",
                h["tickEnd"],
                {"commands": "; ".join(end_cmds)},
            )

        # pula pro próximo highlight
        if i + 1 < len(hls):
            add(
                "SkipAhead",
                f"skip_{i + 1}",
                h["tickEnd"] + 1,
                {"skiptotick": str(hls[i + 1]["tickStart"])},
            )

        clips.append(
            {
                "file": f"{clip_stem}.mp4",
                "stem": clip_stem,
                "player": h["playerSlug"],
                "playerName": h["playerName"],
                "steamId64": h["steamId64"],
                "accountId": h["accountId"],
                "team": h["team"],
                "index": n,
                "highlightId": h["highlightId"],
                "score": h["score"],
                "tags": h["tags"],
                "round": h["round"],
                "tickStart": h["tickStart"],
                "tickEnd": h["tickEnd"],
            }
        )

    # 5) encerra o CS2 depois do último clipe (só quando gravando)
    if include_recording:
        add(
            "PlayCommands",
            "finish",
            hls[-1]["tickEnd"] + int(2 * fps),
            {"commands": f"echo {MARKER}|SESSION|END; quit"},
        )

    content = "demoactions\n{\n" + "\n".join(actions) + "\n}\n"
    return content, clips
