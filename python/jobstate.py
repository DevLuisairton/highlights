"""Leitura/escrita do status.json de um job — fonte de verdade do progresso
que as rotas Next leem (via SSE em /api/jobs/[id]/events).
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import config


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def job_dir(job_id: str) -> Path:
    return config.JOBS_DIR / job_id


def status_path(job_id: str) -> Path:
    return job_dir(job_id) / "status.json"


def read_status(job_id: str) -> dict:
    return json.loads(status_path(job_id).read_text("utf-8"))


def write_status(job_id: str, status: dict) -> None:
    status["updatedAt"] = _now()
    p = status_path(job_id)
    tmp = p.with_suffix(f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(status, ensure_ascii=False, indent=2), "utf-8")
    # troca atômica — mas no Windows o os.replace falha com WinError 5 se
    # outro processo (o Next lendo via SSE) tiver o alvo aberto naquele
    # instante. Tenta de novo por ~3s; em último caso escreve direto.
    for i in range(30):
        try:
            os.replace(tmp, p)
            return
        except PermissionError:
            time.sleep(0.1)
    try:
        p.write_text(json.dumps(status, ensure_ascii=False, indent=2), "utf-8")
    finally:
        tmp.unlink(missing_ok=True)


def update(job_id: str, **fields) -> dict:
    status = read_status(job_id)
    status.update(fields)
    write_status(job_id, status)
    return status


def set_stage(
    job_id: str,
    stage: str,
    message: str,
    progress: float = 0.0,
) -> None:
    """Atualiza etapa + mensagem e loga uma linha no stderr (worker.log)."""
    update(job_id, stage=stage, message=message, progress=round(progress, 1))
    print(f"[{stage}] {message}", file=sys.stderr, flush=True)


def fail(job_id: str, error: str) -> None:
    update(job_id, stage="error", error=error, message=error, progress=0)
    print(f"[error] {error}", file=sys.stderr, flush=True)


def wait_for_selection(job_id: str, timeout_seconds: int = 3600) -> dict | None:
    """Poll em selection.json enquanto o job estiver em 'awaiting-selection'.
    Retorna o payload {keep: {...}} ou None se estourar o timeout."""
    target = job_dir(job_id) / "selection.json"
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if target.exists():
            try:
                return json.loads(target.read_text("utf-8"))
            except ValueError:
                pass
        time.sleep(1.0)
    return None
