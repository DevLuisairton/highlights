import { spawn } from "node:child_process";
import { closeSync, openSync } from "node:fs";
import path from "node:path";
import { PYTHON_BIN, PYTHON_DIR, jobDir } from "@/lib/paths";

/**
 * Dispara `python main.py run-job --job-id <id>` como processo DESTACADO:
 * o worker vive além do ciclo da request HTTP (um job leva minutos — abre o
 * CS2, roda o ffmpeg) e reporta progresso escrevendo em
 * python/state/jobs/<id>/status.json, que as rotas leem depois.
 *
 * stdout/stderr do worker vão pra python/state/jobs/<id>/worker.log — útil
 * pra depurar sem poluir o console do Next.
 */
export function startWorker(jobId: string): void {
  const logPath = path.join(jobDir(jobId), "worker.log");
  const out = openSync(logPath, "a");

  const child = spawn(
    /* turbopackIgnore: true */ PYTHON_BIN,
    ["-X", "utf8", "main.py", "run-job", "--job-id", jobId],
    {
      cwd: PYTHON_DIR,
      detached: true,
      stdio: ["ignore", out, out],
      env: { ...process.env },
    },
  );

  // O filho já herdou o fd — o Next fecha a cópia dele. Sem isso, o processo
  // do Next segura o handle de worker.log aberto pra sempre e no Windows a
  // pasta do job não pode ser apagada (delete / TTL falham).
  closeSync(out);

  // unref(): o processo do Next não fica preso esperando o worker terminar.
  child.unref();
}
