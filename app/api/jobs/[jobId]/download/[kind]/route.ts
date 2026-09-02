import { createReadStream } from "node:fs";
import { readFile, stat } from "node:fs/promises";
import path from "node:path";
import { Readable } from "node:stream";
import type { NextRequest } from "next/server";
import { isValidJobId } from "@/lib/jobs";
import { jobDir } from "@/lib/paths";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * GET /api/jobs/[jobId]/download/[kind]
 *   kind = highlights            → highlights.json
 *   kind = vdm                   → partida.vdm
 *   kind = clip?player=X&n=1     → clips/<X>/clip_01.mp4        (Fase 2)
 *   kind = final?player=X        → montage/final_<X>.mp4        (Fase 3)
 *   kind = combined              → montage/final_partida.mp4    (Fase 3)
 *
 * Todos os caminhos são resolvidos DENTRO da pasta do job e verificados
 * contra path traversal (o resultado precisa continuar sob jobDir).
 */
export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ jobId: string; kind: string }> },
) {
  const { jobId, kind } = await params;
  if (!isValidJobId(jobId)) {
    return Response.json({ error: "jobId inválido." }, { status: 400 });
  }

  const base = jobDir(jobId);
  const sp = request.nextUrl.searchParams;
  const player = sp.get("player") || "";
  const n = sp.get("n") || "";

  let rel: string;
  let contentType: string;
  let downloadName: string;

  switch (kind) {
    case "highlights":
      rel = "highlights.json";
      contentType = "application/json";
      downloadName = "highlights.json";
      break;
    case "vdm":
      rel = "partida.vdm";
      contentType = "text/plain; charset=utf-8";
      downloadName = "partida.vdm";
      break;
    case "clip": {
      if (!safeSegment(player) || !/^\d{1,3}$/.test(n)) {
        return Response.json({ error: "Parâmetros player/n inválidos." }, { status: 400 });
      }
      const file = `clip_${n.padStart(2, "0")}.mp4`;
      rel = path.join("clips", player, file);
      contentType = "video/mp4";
      downloadName = `${player}_${file}`;
      break;
    }
    case "final":
      if (!safeSegment(player)) {
        return Response.json({ error: "Parâmetro player inválido." }, { status: 400 });
      }
      rel = path.join("montage", `final_${player}.mp4`);
      contentType = "video/mp4";
      downloadName = `final_${player}.mp4`;
      break;
    case "combined":
      rel = path.join("montage", "final_partida.mp4");
      contentType = "video/mp4";
      downloadName = "final_partida.mp4";
      break;
    default:
      return Response.json({ error: "kind desconhecido." }, { status: 400 });
  }

  const baseAbs = path.resolve(base);
  const abs = path.resolve(baseAbs, rel);
  if (abs !== baseAbs && !abs.startsWith(baseAbs + path.sep)) {
    return Response.json({ error: "Caminho inválido." }, { status: 400 });
  }

  let size: number;
  try {
    size = (await stat(/* turbopackIgnore: true */ abs)).size;
  } catch {
    return Response.json(
      { error: "Arquivo ainda não disponível para este job." },
      { status: 404 },
    );
  }

  // JSON pequeno: responde direto. Vídeo: streaming.
  if (kind === "highlights" || kind === "vdm") {
    const buf = await readFile(/* turbopackIgnore: true */ abs);
    return new Response(new Uint8Array(buf), {
      headers: {
        "Content-Type": contentType,
        "Content-Disposition": `attachment; filename="${downloadName}"`,
      },
    });
  }

  // ?inline=1 → toca no <video> da página em vez de baixar. Nesse modo
  // atendemos Range requests (206) pra o seek funcionar.
  const inline = sp.get("inline") === "1";
  const disposition = inline
    ? `inline; filename="${downloadName}"`
    : `attachment; filename="${downloadName}"`;

  const rangeHeader = request.headers.get("range");
  if (inline && rangeHeader && /^bytes=\d*-\d*$/.test(rangeHeader)) {
    const [rawStart, rawEnd] = rangeHeader.replace("bytes=", "").split("-");
    const start = rawStart ? parseInt(rawStart, 10) : 0;
    const end = rawEnd ? parseInt(rawEnd, 10) : size - 1;
    if (
      Number.isNaN(start) ||
      Number.isNaN(end) ||
      start > end ||
      start >= size
    ) {
      return new Response("Range inválido", {
        status: 416,
        headers: { "Content-Range": `bytes */${size}` },
      });
    }
    const clampedEnd = Math.min(end, size - 1);
    const chunk = createReadStream(/* turbopackIgnore: true */ abs, {
      start,
      end: clampedEnd,
    });
    return new Response(Readable.toWeb(chunk) as ReadableStream, {
      status: 206,
      headers: {
        "Content-Type": contentType,
        "Content-Range": `bytes ${start}-${clampedEnd}/${size}`,
        "Accept-Ranges": "bytes",
        "Content-Length": String(clampedEnd - start + 1),
        "Content-Disposition": disposition,
        "Cache-Control": "no-store",
      },
    });
  }

  const nodeStream = createReadStream(/* turbopackIgnore: true */ abs);
  return new Response(Readable.toWeb(nodeStream) as ReadableStream, {
    headers: {
      "Content-Type": contentType,
      "Content-Length": String(size),
      "Accept-Ranges": "bytes",
      "Content-Disposition": disposition,
      "Cache-Control": "no-store",
    },
  });
}

/** Um segmento de caminho seguro (sem separadores, sem "..", sem nulos). */
function safeSegment(s: string): boolean {
  return (
    s.length > 0 &&
    s.length <= 128 &&
    !s.includes("/") &&
    !s.includes("\\") &&
    !s.includes("..") &&
    !s.includes("\0")
  );
}
