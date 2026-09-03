import type { NextRequest } from "next/server";
import {
  deleteJob,
  isValidJobId,
  readClips,
  readHighlights,
  readJobStatus,
} from "@/lib/jobs";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * GET /api/jobs/[jobId] — status do job + relatório de highlights por
 * jogador (quando já existe).
 */
export async function GET(
  _req: NextRequest,
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

  const [highlights, clips] = await Promise.all([
    readHighlights(jobId),
    readClips(jobId),
  ]);
  return Response.json(
    { status, highlights, clips },
    { headers: { "Cache-Control": "no-store" } },
  );
}

/** DELETE /api/jobs/[jobId] — remove o job e todos os artefatos. */
export async function DELETE(
  _req: NextRequest,
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
  await deleteJob(jobId);
  return Response.json({ ok: true });
}
