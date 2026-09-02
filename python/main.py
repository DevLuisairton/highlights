"""CLI unificado do hillights.

Subcomandos
-----------
run-job    --job-id <id>
    Orquestra o pipeline inteiro de um job (parsing -> scoring ->
    [review] -> vdm -> [recording] -> [editing]), escrevendo o progresso
    em state/jobs/<id>/status.json. É o que lib/worker.ts dispara.

parse-demo --demo <path> [--out <dir>]
    Só o parsing. Escreve events.json em <dir> (ou imprime resumo).

score      --events <path> --job-id <id> [--out <dir>]
    Só a pontuação. Lê events.json, escreve highlights.json.

gen-vdm    --job-dir <dir> [--selection <path>] [--record]
    Só a geração do .vdm a partir do highlights.json do job.

list-jobs
    Imprime o status.json de todos os jobs (JSON array no stdout).

doctor
    Diagnostica o ambiente de gravação (CS2 / HLAE / ffmpeg).

Convenção: stdout = JSON puro (consumido pelo Next). Logs de progresso
vão pro stderr.
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path

import config
import jobstate
import parsing
import scoring
import vdmgen


def _out(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False), flush=True)


# ─────────────────────────────────────────────────────────────────────────
def cmd_parse_demo(args) -> int:
    parsed = parsing.parse_demo(args.demo)
    if args.out:
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        (out / "events.json").write_text(
            json.dumps(parsed, ensure_ascii=False, indent=2), "utf-8"
        )
    _out(
        {
            "map": parsed["map"],
            "tickrate": parsed["tickrate"],
            "players": len(parsed["players"]),
            "kills": len(parsed["kills"]),
            "rounds": len(parsed["rounds"]),
        }
    )
    return 0


def cmd_score(args) -> int:
    parsed = json.loads(Path(args.events).read_text("utf-8"))
    report = scoring.build_report(args.job_id, parsed)
    out = Path(args.out) if args.out else Path(args.events).parent
    out.mkdir(parents=True, exist_ok=True)
    (out / "highlights.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), "utf-8"
    )
    _out(
        {
            "players": len(report["players"]),
            "highlights": sum(len(p["highlights"]) for p in report["players"]),
        }
    )
    return 0


def cmd_gen_vdm(args) -> int:
    job_path = Path(args.job_dir)
    report = json.loads((job_path / "highlights.json").read_text("utf-8"))
    keep = None
    if args.selection:
        keep = json.loads(Path(args.selection).read_text("utf-8")).get("keep")
    content, clips = vdmgen.build_vdm(
        report,
        keep=keep,
        include_recording=args.record,
        backend=config.RECORDER_BACKEND,
        fps=config.MONTAGE_FPS,
    )
    (job_path / "partida.vdm").write_text(content, "utf-8")
    (job_path / "clips.json").write_text(
        json.dumps(clips, ensure_ascii=False, indent=2), "utf-8"
    )
    _out({"vdm": "partida.vdm", "clips": len(clips)})
    return 0


def cmd_list_jobs(_args) -> int:
    jobs = []
    if config.JOBS_DIR.is_dir():
        for d in config.JOBS_DIR.iterdir():
            sp = d / "status.json"
            if sp.is_file():
                try:
                    jobs.append(json.loads(sp.read_text("utf-8")))
                except ValueError:
                    pass
    jobs.sort(key=lambda j: j.get("createdAt", ""), reverse=True)
    _out(jobs)
    return 0


def cmd_doctor(_args) -> int:
    import recorder

    _out(
        {
            "recorderEnabled": config.RECORDER_ENABLED,
            "backend": config.RECORDER_BACKEND,
            "cs2Exe": config.CS2_EXE,
            "cs2DemosDir": config.CS2_DEMOS_DIR,
            "problems": recorder.preflight(),
        }
    )
    return 0


# ─────────────────────────────────────────────────────────────────────────
def cmd_run_job(args) -> int:
    job_id = args.job_id
    job_path = jobstate.job_dir(job_id)
    demo_path = job_path / "uploads" / "partida.dem"

    try:
        if not demo_path.is_file():
            jobstate.fail(job_id, "Arquivo do demo não encontrado.")
            return 1

        # 1) PARSING
        jobstate.set_stage(job_id, "parsing", "Lendo o demo…", 0)

        def on_progress(pct: float, msg: str) -> None:
            jobstate.update(
                job_id, stage="parsing", message=msg, progress=round(pct, 1)
            )

        parsed = parsing.parse_demo(demo_path, on_progress)
        (job_path / "events.json").write_text(
            json.dumps(parsed, ensure_ascii=False, indent=2), "utf-8"
        )

        # 2) SCORING
        jobstate.set_stage(job_id, "scoring", "Pontuando os lances…", 40)
        report = scoring.build_report(job_id, parsed)
        (job_path / "highlights.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), "utf-8"
        )
        n_hl = sum(len(p["highlights"]) for p in report["players"])
        jobstate.update(
            job_id,
            map=report["map"],
            matchScore=report["matchScore"],
            playersCount=len(report["players"]),
            highlightsCount=n_hl,
        )

        # 3) SELEÇÃO — pausa pra escolher jogadores/lances antes de gravar
        #    (só quando vai gravar; em modo detecção sai tudo).
        keep = None
        if config.REVIEW_MODE and config.RECORDER_ENABLED and n_hl > 0:
            jobstate.set_stage(
                job_id,
                "awaiting-selection",
                "Escolha os jogadores/lances no painel para gerar os vídeos.",
                50,
            )
            sel = jobstate.wait_for_selection(job_id)
            if sel is None:
                jobstate.fail(job_id, "Timeout aguardando a seleção no painel.")
                return 1
            keep = sel.get("keep")

        # 4) VDM
        jobstate.set_stage(job_id, "vdm", "Gerando o arquivo .vdm…", 60)
        content, clips = vdmgen.build_vdm(
            report,
            keep=keep,
            include_recording=config.RECORDER_ENABLED,
            backend=config.RECORDER_BACKEND,
            fps=config.RECORD_FPS,
        )
        (job_path / "partida.vdm").write_text(content, "utf-8")
        (job_path / "clips.json").write_text(
            json.dumps(clips, ensure_ascii=False, indent=2), "utf-8"
        )

        if not config.RECORDER_ENABLED:
            jobstate.update(
                job_id,
                stage="done",
                message=(
                    f"{n_hl} lances detectados em {len(report['players'])} "
                    "jogadores. VDM pronto (modo só detecção)."
                ),
                progress=100,
                detectionOnly=True,
            )
            _out({"jobId": job_id, "stage": "done", "highlights": n_hl})
            return 0

        # 5) RECORDING (Fase 2) — recorder regenera o VDM pro backend e
        #    reescreve clips.json com o mapeamento final.
        import recorder

        jobstate.set_stage(job_id, "recording", "Gravando os clipes no CS2…", 70)
        recorder.record(job_id, job_path, report, clips)

        # 6) EDITING (Fase 3)
        import montage

        jobstate.set_stage(job_id, "editing", "Montando os vídeos…", 90)
        outputs = montage.build(job_id, job_path, report)
        jobstate.update(job_id, montageOutputs=outputs)

        jobstate.update(
            job_id,
            stage="done",
            message="Montagem concluída.",
            progress=100,
            detectionOnly=False,
        )
        _out({"jobId": job_id, "stage": "done", "highlights": n_hl})
        return 0

    except Exception as e:  # noqa: BLE001 — topo do worker, tem que capturar tudo
        traceback.print_exc()
        jobstate.fail(job_id, f"{type(e).__name__}: {e}")
        return 1


# ─────────────────────────────────────────────────────────────────────────
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="hillights")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("run-job")
    s.add_argument("--job-id", required=True)
    s.set_defaults(func=cmd_run_job)

    s = sub.add_parser("parse-demo")
    s.add_argument("--demo", required=True)
    s.add_argument("--out")
    s.set_defaults(func=cmd_parse_demo)

    s = sub.add_parser("score")
    s.add_argument("--events", required=True)
    s.add_argument("--job-id", default="cli")
    s.add_argument("--out")
    s.set_defaults(func=cmd_score)

    s = sub.add_parser("gen-vdm")
    s.add_argument("--job-dir", required=True)
    s.add_argument("--selection")
    s.add_argument("--record", action="store_true")
    s.set_defaults(func=cmd_gen_vdm)

    s = sub.add_parser("list-jobs")
    s.set_defaults(func=cmd_list_jobs)

    s = sub.add_parser("doctor")
    s.set_defaults(func=cmd_doctor)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
