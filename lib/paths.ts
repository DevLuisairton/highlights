import path from "node:path";

const CWD = process.cwd();

/** Resolve pra absoluto a partir da raiz do repo (aceita caminho já absoluto). */
function abs(p: string): string {
  return path.isAbsolute(p) ? p : path.join(CWD, p);
}

/** Pasta do CLI Python (`python/main.py`). Sempre absoluta. */
export const PYTHON_DIR = process.env.PYTHON_DIR
  ? abs(process.env.PYTHON_DIR)
  : path.join(CWD, "python");

/**
 * Executável do Python. Use um nome simples ("python", resolvido no PATH)
 * OU um caminho ABSOLUTO (ex.: o do venv). Caminho relativo não serve — o
 * spawn roda com `cwd: PYTHON_DIR` e resolveria errado.
 */
export const PYTHON_BIN = process.env.PYTHON_BIN || "python";

/**
 * Raiz do estado em disco (SEMPRE absoluta). Em produção é um volume Docker
 * persistente (ver docker-compose.yml). O `.env` pode trazer um caminho
 * relativo (`./python/state`) — resolvemos aqui, senão as rotas de download
 * comparam absoluto vs relativo e rejeitam tudo ("Caminho inválido").
 */
export const STATE_DIR = process.env.STATE_DIR
  ? abs(process.env.STATE_DIR)
  : path.join(PYTHON_DIR, "state");

/** Pasta que guarda um subdiretório por job. */
export const JOBS_DIR = path.join(STATE_DIR, "jobs");

/** Caminho absoluto da pasta de um job. */
export function jobDir(jobId: string): string {
  return path.join(JOBS_DIR, jobId);
}

/** Caminho do status.json de um job (fonte de verdade do progresso). */
export function jobStatusPath(jobId: string): string {
  return path.join(jobDir(jobId), "status.json");
}
