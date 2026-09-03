"use client";

import { useEffect, useState } from "react";
import { JobProgress } from "@/components/JobProgress";
import { PlayerHighlights } from "@/components/PlayerHighlights";
import { DownloadBar } from "@/components/DownloadBar";
import { VideoPreview } from "@/components/VideoPreview";
import { ClipList } from "@/components/ClipList";
import type {
  ClipInfo,
  HighlightsReport,
  JobStage,
  JobStatus,
} from "@/types/job";

export function JobView({
  jobId,
  initialStage,
}: {
  jobId: string;
  initialStage: JobStage;
}) {
  const [status, setStatus] = useState<JobStatus | null>(null);
  const [report, setReport] = useState<HighlightsReport | null>(null);
  const [clips, setClips] = useState<ClipInfo[]>([]);

  // SSE do progresso.
  useEffect(() => {
    const es = new EventSource(`/api/jobs/${jobId}/events`);
    es.onmessage = (e) => {
      const data = JSON.parse(e.data) as JobStatus & { error?: string };
      if (!data.jobId) return;
      setStatus(data);
      if (data.stage === "done" || data.stage === "error") es.close();
    };
    es.onerror = () => es.close();
    return () => es.close();
  }, [jobId]);

  // Carrega o relatório de highlights quando ele já deve existir.
  useEffect(() => {
    const stage = status?.stage ?? initialStage;
    const ready =
      stage === "scoring" ||
      stage === "awaiting-selection" ||
      stage === "vdm" ||
      stage === "recording" ||
      stage === "editing" ||
      stage === "done";
    if (!ready) return;

    let alive = true;
    const load = async () => {
      const r = await fetch(`/api/jobs/${jobId}`, { cache: "no-store" });
      if (!r.ok) return;
      const { highlights, clips } = (await r.json()) as {
        highlights: HighlightsReport | null;
        clips: ClipInfo[] | null;
      };
      if (!alive) return;
      if (highlights) setReport(highlights);
      if (clips) setClips(clips);
    };
    load();
    return () => {
      alive = false;
    };
  }, [jobId, status?.stage, initialStage]);

  return (
    <div className="flex flex-col gap-6">
      <JobProgress status={status} />

      {status?.stage === "error" && (
        <div className="rounded-lg border border-[var(--bad)] bg-[var(--panel)] p-4 text-sm text-[var(--bad)]">
          {status.error || status.message}
        </div>
      )}

      {report && (
        <>
          <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1 text-sm text-[var(--muted)]">
            <span>
              <strong className="text-[var(--text)]">{report.map}</strong>
            </span>
            <span>placar {report.matchScore}</span>
            <span>tickrate {report.tickrate}</span>
            <span>{report.players.length} jogadores</span>
          </div>

          {clips.length > 0 &&
            (status?.stage ?? initialStage) === "done" && (
              <ClipList jobId={jobId} clips={clips} />
            )}

          {(status?.montageOutputs?.length ?? 0) > 0 && (
            <VideoPreview
              jobId={jobId}
              report={report}
              montageOutputs={status?.montageOutputs ?? []}
            />
          )}

          <PlayerHighlights
            jobId={jobId}
            report={report}
            stage={status?.stage ?? initialStage}
          />

          <DownloadBar
            jobId={jobId}
            report={report}
            stage={status?.stage ?? initialStage}
            detectionOnly={status?.detectionOnly ?? false}
            montageOutputs={status?.montageOutputs ?? []}
          />
        </>
      )}
    </div>
  );
}
