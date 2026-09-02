"use client";

import type { HighlightsReport, JobStage } from "@/types/job";

export function DownloadBar({
  jobId,
  report,
  stage,
  detectionOnly,
  montageOutputs,
}: {
  jobId: string;
  report: HighlightsReport;
  stage: JobStage;
  detectionOnly: boolean;
  montageOutputs: string[];
}) {
  const base = `/api/jobs/${jobId}/download`;
  const hasVdm =
    stage === "vdm" ||
    stage === "recording" ||
    stage === "editing" ||
    stage === "done";
  const hasCombined = montageOutputs.includes("final_partida.mp4");
  const perPlayer = report.players
    .filter((p) => p.highlights.length > 0)
    .map((p) => ({ p, file: `final_${p.slug}.mp4` }))
    .filter(({ file }) => montageOutputs.includes(file));

  return (
    <div className="flex flex-col gap-3 rounded-xl border border-[var(--border)] bg-[var(--panel)] p-4">
      <div className="flex flex-wrap gap-2">
        <a
          href={`${base}/highlights`}
          className="rounded-lg border border-[var(--border)] px-3 py-1.5 text-sm hover:border-[var(--accent-2)]"
        >
          highlights.json
        </a>
        {hasVdm && (
          <a
            href={`${base}/vdm`}
            className="rounded-lg border border-[var(--border)] px-3 py-1.5 text-sm hover:border-[var(--accent-2)]"
          >
            partida.vdm
          </a>
        )}
        {hasCombined && (
          <a
            href={`${base}/combined`}
            className="rounded-lg bg-[var(--accent)] px-3 py-1.5 text-sm font-medium text-black"
          >
            final_partida.mp4
          </a>
        )}
      </div>

      {detectionOnly && stage === "done" && (
        <p className="text-xs text-[var(--muted)]">
          Este job rodou em modo <strong>só detecção</strong> (RECORDER_ENABLED=0).
          Baixe o <code>partida.vdm</code>, coloque junto do <code>.dem</code> na
          pasta <code>csgo/</code> do CS2 e dê <code>playdemo</code> — ele pula
          direto pros melhores lances.
        </p>
      )}

      {perPlayer.length > 0 && (
        <div className="flex flex-col gap-1.5">
          <p className="text-xs text-[var(--muted)]">Montagem por jogador:</p>
          <div className="flex flex-wrap gap-2">
            {perPlayer.map(({ p }) => (
              <a
                key={p.steamId64}
                href={`${base}/final?player=${encodeURIComponent(p.slug)}`}
                className="rounded-lg border border-[var(--border)] px-3 py-1.5 text-sm hover:border-[var(--accent-2)]"
              >
                final_{p.slug}.mp4
              </a>
            ))}
          </div>
        </div>
      )}

      {stage === "editing" && (
        <p className="text-xs text-[var(--muted)]">Montando os vídeos com ffmpeg…</p>
      )}
    </div>
  );
}
