import type { NextRequest } from "next/server";
import { isValidJobId, readJobStatus } from "@/lib/jobs";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * GET /api/jobs/[jobId]/events — SSE. Faz polling do status.json a cada
 * segundo e empurra pro cliente quando muda. Fecha o stream quando o job
 * chega em "done" ou "error".
 *
 * Poderia ser fs.watch, mas o polling de 1s é simples, robusto entre
 * plataformas e o custo (ler um JSON de <10 KB) é irrelevante.
 */
export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ jobId: string }> },
) {
  const { jobId } = await params;
  if (!isValidJobId(jobId)) {
    return new Response("jobId inválido", { status: 400 });
  }

  const encoder = new TextEncoder();
  let closed = false;

  const stream = new ReadableStream({
    async start(controller) {
      const send = (data: unknown) => {
        if (closed) return;
        controller.enqueue(encoder.encode(`data: ${JSON.stringify(data)}\n\n`));
      };

      let lastSerialized = "";
      const tick = async () => {
        if (closed) return;
        const status = await readJobStatus(jobId);
        if (!status) {
          send({ error: "Job não encontrado." });
          finish();
          return;
        }
        const serialized = JSON.stringify(status);
        if (serialized !== lastSerialized) {
          lastSerialized = serialized;
          send(status);
        }
        if (status.stage === "done" || status.stage === "error") {
          finish();
          return;
        }
        timer = setTimeout(tick, 1000);
      };

      let timer: ReturnType<typeof setTimeout>;
      const finish = () => {
        if (closed) return;
        closed = true;
        clearTimeout(timer);
        try {
          controller.close();
        } catch {
          /* já fechado */
        }
      };

      // Primeiro envio imediato.
      await tick();
    },
    cancel() {
      closed = true;
    },
  });

  return new Response(stream, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
    },
  });
}
