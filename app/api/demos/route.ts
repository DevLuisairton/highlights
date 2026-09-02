import { createWriteStream } from "node:fs";
import { Readable } from "node:stream";
import { pipeline } from "node:stream/promises";
import type { NextRequest } from "next/server";
import { createJob, failJob } from "@/lib/jobs";
import { startWorker } from "@/lib/worker";

export const runtime = "nodejs";
// Sem cache e sem limite de tempo de resposta pro streaming do upload.
export const dynamic = "force-dynamic";
export const maxDuration = 300;

const MAX_BYTES = 600 * 1024 * 1024; // 600 MB — demo de CS2 raramente passa disso

/**
 * POST /api/demos  (multipart/form-data, campo "file")
 * Faz streaming do .dem pro disco, cria o job e dispara o worker Python.
 * Responde na hora com { jobId } — o processamento é assíncrono.
 */
export async function POST(request: NextRequest) {
  const contentType = request.headers.get("content-type") || "";
  if (!contentType.includes("multipart/form-data")) {
    return Response.json(
      { error: "Envie multipart/form-data com o campo 'file'." },
      { status: 400 },
    );
  }

  let form: FormData;
  try {
    form = await request.formData();
  } catch {
    return Response.json({ error: "Upload inválido." }, { status: 400 });
  }

  const file = form.get("file");
  if (!(file instanceof File)) {
    return Response.json(
      { error: "Campo 'file' ausente ou inválido." },
      { status: 400 },
    );
  }
  if (!file.name.toLowerCase().endsWith(".dem")) {
    return Response.json(
      { error: "O arquivo precisa ter extensão .dem (demo de CS2)." },
      { status: 400 },
    );
  }
  if (file.size > MAX_BYTES) {
    return Response.json(
      { error: `Arquivo muito grande (máx. ${MAX_BYTES / 1024 / 1024} MB).` },
      { status: 413 },
    );
  }

  const { jobId, demoPath } = await createJob(file.name);

  try {
    await pipeline(
      Readable.fromWeb(file.stream() as import("stream/web").ReadableStream),
      createWriteStream(demoPath),
    );
  } catch (err) {
    await failJob(jobId, "Falha ao salvar o arquivo enviado.");
    console.error("upload demo:", err);
    return Response.json(
      { error: "Falha ao salvar o arquivo enviado." },
      { status: 500 },
    );
  }

  startWorker(jobId);

  return Response.json({ jobId }, { status: 202 });
}
