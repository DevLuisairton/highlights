import { randomUUID } from "node:crypto";
import { mkdir, readFile, readdir, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import { JOBS_DIR, jobDir, jobStatusPath } from "@/lib/paths";
import type { HighlightsReport, JobStatus } from "@/types/job";

/** Lê o status.json de um job. `null` se o job não existe. */
export async function readJobStatus(jobId: string): Promise<JobStatus | null> {
  try {
    const raw = await readFile(jobStatusPath(jobId), "utf-8");
    return JSON.parse(raw) as JobStatus;
  } catch {
    return null;
  }
}

/** Lê o highlights.json de um job (só existe depois da etapa de scoring). */
export async function readHighlights(
  jobId: string,
): Promise<HighlightsReport | null> {
  try {
    const raw = await readFile(
      path.join(jobDir(jobId), "highlights.json"),
      "utf-8",
    );
    return JSON.parse(raw) as HighlightsReport;
  } catch {
    return null;
  }
}

const TTL_MS = (Number(process.env.JOB_TTL_HOURS) || 72) * 3_600_000;

/** Lista todos os jobs, mais recentes primeiro. Aproveita pra apagar os que
 * passaram do TTL (housekeeping oportunista — /api/jobs é chamada a cada
 * poucos segundos pela UI). */
export async function listJobs(): Promise<JobStatus[]> {
  let ids: string[];
  try {
    ids = await readdir(JOBS_DIR);
  } catch {
    return [];
  }
  const jobs = await Promise.all(
    ids
      .filter((id) => !id.startsWith("."))
      .map((id) => readJobStatus(id)),
  );
  const now = Date.now();
  const alive: JobStatus[] = [];
  for (const j of jobs) {
    if (!j) continue;
    if (now - new Date(j.createdAt).getTime() > TTL_MS) {
      void deleteJob(j.jobId).catch(() => {});
    } else {
      alive.push(j);
    }
  }
  return alive.sort((a, b) => b.createdAt.localeCompare(a.createdAt));
}

/**
 * Cria a pasta do job e grava um status.json inicial. Retorna o id e o
 * caminho onde o arquivo .dem deve ser salvo (o caller faz o streaming).
 */
export async function createJob(demoName: string): Promise<{
  jobId: string;
  demoPath: string;
}> {
  const jobId = randomUUID();
  const dir = jobDir(jobId);
  await mkdir(path.join(dir, "uploads"), { recursive: true });

  const now = new Date().toISOString();
  const status: JobStatus = {
    jobId,
    stage: "queued",
    progress: 0,
    message: "Job criado, aguardando processamento.",
    demoName,
    createdAt: now,
    updatedAt: now,
  };
  await writeFile(jobStatusPath(jobId), JSON.stringify(status, null, 2), "utf-8");

  // Nome fixo no disco (o original fica no status.json). Simplifica o lado
  // Python e evita problemas com acento / espaço no nome do arquivo.
  return { jobId, demoPath: path.join(dir, "uploads", "partida.dem") };
}

/** Marca um job como erro (usado quando o próprio Node falha antes do worker). */
export async function failJob(jobId: string, error: string): Promise<void> {
  const status = await readJobStatus(jobId);
  if (!status) return;
  status.stage = "error";
  status.error = error;
  status.message = error;
  status.updatedAt = new Date().toISOString();
  await writeFile(jobStatusPath(jobId), JSON.stringify(status, null, 2), "utf-8");
}

/** Remove um job e todos os seus artefatos. */
export async function deleteJob(jobId: string): Promise<void> {
  await rm(jobDir(jobId), { recursive: true, force: true });
}

/** Valida o formato do id (UUID v4) antes de tocar no filesystem. */
export function isValidJobId(id: string): boolean {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(
    id,
  );
}
