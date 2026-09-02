"use client";

import type { JobStatus } from "@/types/job";
import { STAGE_LABEL, STAGE_ORDER } from "@/components/stage";

export function JobProgress({ status }: { status: JobStatus | null }) {
  if (!status) {
    return <p className="text-sm text-[var(--muted)]">Conectando…</p>;
  }

  const currentIdx = STAGE_ORDER.indexOf(
    status.stage === "done" ? "done" : status.stage,
  );

  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--panel)] p-4">
      <div className="mb-3 flex items-center justify-between">
        <p className="text-sm font-medium">{status.demoName}</p>
        <p className="text-xs text-[var(--muted)]">{STAGE_LABEL[status.stage]}</p>
      </div>

      <ol className="flex flex-wrap gap-1">
        {STAGE_ORDER.filter(
          (s) => s !== "awaiting-selection" || status.stage === "awaiting-selection",
        ).map((s) => {
          const idx = STAGE_ORDER.indexOf(s);
          const state =
            status.stage === "error"
              ? idx <= currentIdx
                ? "done"
                : "todo"
              : idx < currentIdx
                ? "done"
                : idx === currentIdx
                  ? "active"
                  : "todo";
          return (
            <li
              key={s}
              className={`rounded px-2 py-1 text-xs ${
                state === "done"
                  ? "bg-[var(--panel-2)] text-[var(--good)]"
                  : state === "active"
                    ? "bg-[var(--accent)] text-black"
                    : "bg-[var(--panel-2)] text-[var(--muted)]"
              }`}
            >
              {STAGE_LABEL[s]}
            </li>
          );
        })}
      </ol>

      {status.stage !== "done" && status.stage !== "error" && (
        <div className="mt-3">
          <div className="h-1.5 w-full overflow-hidden rounded bg-[var(--panel-2)]">
            <div
              className="h-full bg-[var(--accent-2)] transition-[width]"
              style={{ width: `${Math.max(4, status.progress)}%` }}
            />
          </div>
          <p className="mt-1.5 text-xs text-[var(--muted)]">{status.message}</p>
        </div>
      )}
    </div>
  );
}
