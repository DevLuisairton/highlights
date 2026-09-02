import { spawn } from "node:child_process";
import { PYTHON_BIN, PYTHON_DIR } from "@/lib/paths";

/**
 * Mesmo runner do projeto de referência (planilha-automatizada): roda
 * `python -X utf8 main.py <args>` a partir de PYTHON_DIR, com teto de
 * processos simultâneos (fila FIFO) e dedupe de chamadas idênticas
 * in-flight.
 *
 * Usado só nas chamadas CURTAS e síncronas (listar jobs, re-gerar o VDM
 * depois de uma seleção). O job longo — parsing/gravação/montagem — roda
 * destacado via lib/worker.ts e reporta progresso pelo status.json.
 */

export interface PythonResult {
  code: number;
  stdout: string;
  stderr: string;
}

const MAX_CONCURRENT_PYTHON = Number(process.env.MAX_CONCURRENT_PYTHON) || 4;
let activeCount = 0;
const waitQueue: Array<() => void> = [];

function acquireSlot(): Promise<void> {
  if (activeCount < MAX_CONCURRENT_PYTHON) {
    activeCount++;
    return Promise.resolve();
  }
  return new Promise((resolve) => waitQueue.push(resolve));
}

function releaseSlot(): void {
  const next = waitQueue.shift();
  if (next) {
    next();
  } else {
    activeCount--;
  }
}

function spawnPython(args: string[]): Promise<PythonResult> {
  return new Promise((resolve, reject) => {
    const child = spawn(
      /* turbopackIgnore: true */ PYTHON_BIN,
      ["-X", "utf8", "main.py", ...args],
      { cwd: PYTHON_DIR },
    );
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (c) => (stdout += c.toString("utf-8")));
    child.stderr.on("data", (c) => (stderr += c.toString("utf-8")));
    child.on("error", reject);
    child.on("close", (code) => resolve({ code: code ?? 1, stdout, stderr }));
  });
}

const inFlight = new Map<string, Promise<PythonResult>>();

export function runPython(args: string[]): Promise<PythonResult> {
  const key = JSON.stringify(args);
  const existing = inFlight.get(key);
  if (existing) return existing;

  const promise = (async () => {
    try {
      await acquireSlot();
      try {
        return await spawnPython(args);
      } finally {
        releaseSlot();
      }
    } finally {
      inFlight.delete(key);
    }
  })();

  inFlight.set(key, promise);
  return promise;
}
