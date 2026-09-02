import { writeFile } from "node:fs/promises";
import path from "node:path";
import type { NextRequest } from "next/server";
import { isValidJobId, readJobStatus } from "@/lib/jobs";
import { jobDir } from "@/lib/paths";
import type { SelectionPayload } from "@/types/job";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * POST /api/jobs/[jobId]/selection  (modo review, REVIEW_MODE=1)
 * Grava selection.json na pasta do job. O worker Python está em polling
 * nesse arquivo enquanto o stage for "awaiting-selection"; ao encontrá-lo,
 * segue pra geração do VDM só com os highlights marcados.
 */
export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ jobId: string }> },
) {
  const { jobId } = await params;
  if (!isValidJobId(jobId)) {
    return Response.json({ error: "jobId inválido." }, { status: 400 });
  }

  const status = await readJobStatus(jobId);
  if (!status) {
    return Response.json({ error: "Job não encontrado." }, { status: 404 });
  }
  if (status.stage !== "awaiting-selection") {
    return Response.json(
      { error: `Job não está aguardando seleção (stage atual: ${status.stage}).` },
      { status: 409 },
    );
  }

  let body: SelectionPayload;
  try {
    body = (await request.json()) as SelectionPayload;
  } catch {
    return Response.json({ error: "JSON inválido." }, { status: 400 });
  }
  if (!body || typeof body.keep !== "object" || body.keep === null) {
    return Response.json(
      { error: "Formato esperado: { keep: { <steamId64>: number[] } }" },
      { status: 400 },
    );
  }

  await writeFile(
    path.join(jobDir(jobId), "selection.json"),
    JSON.stringify(body, null, 2),
    "utf-8",
  );

  return Response.json({ ok: true });
}
