"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import type { JobStatus } from "@/types/job";
import { STAGE_LABEL } from "@/components/stage";

export function JobList() {
  const [jobs, setJobs] = useState<JobStatus[] | null>(null);
  const [deleting, setDeleting] = useState<Set<string>>(new Set());

  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const r = await fetch("/api/jobs", { cache: "no-store" });
        const { jobs } = (await r.json()) as { jobs: JobStatus[] };
        if (alive) setJobs(jobs);
      } catch {
        if (alive) setJobs([]);
      }
    };
    load();
    const t = setInterval(load, 3000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, []);

  const remove = async (jobId: string, name: string) => {
    if (!confirm(`Excluir o job "${name}" e todos os arquivos dele?`)) return;
    setDeleting((s) => new Set(s).add(jobId));
    try {
      const r = await fetch(`/api/jobs/${jobId}`, { method: "DELETE" });
      if (r.ok) {
        setJobs((prev) => (prev ? prev.filter((j) => j.jobId !== jobId) : prev));
      }
    } finally {
      setDeleting((s) => {
        const n = new Set(s);
        n.delete(jobId);
        return n;
      });
    }
  };

  if (jobs === null) {
    return <p className="text-sm text-[var(--muted)]">Carregando…</p>;
  }
  if (jobs.length === 0) {
    return (
      <p className="text-sm text-[var(--muted)]">
        Nenhum job ainda. Envie um demo acima.
      </p>
    );
  }

  return (
    <ul className="flex flex-col gap-2">
      {jobs.map((j) => {
        const busy = deleting.has(j.jobId);
        return (
          <li key={j.jobId} className="group relative">
            <Link
              href={`/jobs/${j.jobId}`}
              className={`flex items-center justify-between rounded-lg border border-[var(--border)] bg-[var(--panel)] py-3 pl-4 pr-12 hover:border-[var(--accent-2)] ${
                busy ? "pointer-events-none opacity-50" : ""
              }`}
            >
              <div className="min-w-0">
                <p className="truncate text-sm font-medium">{j.demoName}</p>
                <p className="text-xs text-[var(--muted)]">
                  {j.map ? `${j.map} · ` : ""}
                  {new Date(j.createdAt).toLocaleString("pt-BR")}
                </p>
              </div>
              <div className="flex items-center gap-3 pl-4">
                {typeof j.highlightsCount === "number" && (
                  <span className="text-xs text-[var(--muted)]">
                    {j.highlightsCount} lances
                  </span>
                )}
                <StageBadge stage={j.stage} />
              </div>
            </Link>

            <button
              type="button"
              aria-label="Excluir job"
              title="Excluir job"
              disabled={busy}
              onClick={() => remove(j.jobId, j.demoName)}
              className="absolute right-2 top-1/2 -translate-y-1/2 rounded-md px-2 py-1 text-sm text-[var(--muted)] opacity-0 transition hover:bg-[var(--panel-2)] hover:text-[var(--bad)] focus:opacity-100 group-hover:opacity-100 disabled:opacity-40"
            >
              {busy ? "…" : "✕"}
            </button>
          </li>
        );
      })}
    </ul>
  );
}

function StageBadge({ stage }: { stage: JobStatus["stage"] }) {
  const color =
    stage === "done"
      ? "text-[var(--good)] border-[var(--good)]"
      : stage === "error"
        ? "text-[var(--bad)] border-[var(--bad)]"
        : "text-[var(--accent)] border-[var(--accent)]";
  return (
    <span className={`rounded-full border px-2 py-0.5 text-xs ${color}`}>
      {STAGE_LABEL[stage]}
    </span>
  );
}
