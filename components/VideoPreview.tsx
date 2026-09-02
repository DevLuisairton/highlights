"use client";

import { useMemo, useState } from "react";
import type { HighlightsReport } from "@/types/job";

type Item = { key: string; label: string; url: string };

export function VideoPreview({
  jobId,
  report,
  montageOutputs,
}: {
  jobId: string;
  report: HighlightsReport;
  montageOutputs: string[];
}) {
  const base = `/api/jobs/${jobId}/download`;

  const items = useMemo<Item[]>(() => {
    const list: Item[] = [];
    if (montageOutputs.includes("final_partida.mp4")) {
      list.push({
        key: "combined",
        label: "★ Partida (top geral)",
        url: `${base}/combined?inline=1`,
      });
    }
    for (const p of report.players) {
      const file = `final_${p.slug}.mp4`;
      if (montageOutputs.includes(file)) {
        list.push({
          key: p.slug,
          label: `${p.displayName || p.name} (${p.highlights.length})`,
          url: `${base}/final?player=${encodeURIComponent(p.slug)}&inline=1`,
        });
      }
    }
    return list;
  }, [base, report.players, montageOutputs]);

  const [active, setActive] = useState(0);

  if (items.length === 0) return null;
  const current = items[Math.min(active, items.length - 1)];

  return (
    <div className="flex flex-col gap-3 rounded-xl border border-[var(--border)] bg-[var(--panel)] p-4">
      <div className="flex flex-wrap gap-1.5">
        {items.map((it, i) => (
          <button
            key={it.key}
            onClick={() => setActive(i)}
            className={`rounded px-2.5 py-1 text-xs ${
              i === active
                ? "bg-[var(--accent)] text-black"
                : "bg-[var(--panel-2)] text-[var(--muted)] hover:text-[var(--text)]"
            }`}
          >
            {it.label}
          </button>
        ))}
      </div>

      <video
        key={current.url}
        src={current.url}
        controls
        preload="metadata"
        className="w-full rounded-lg bg-black"
        style={{ aspectRatio: "16 / 9" }}
      />

      <a
        href={current.url.replace("&inline=1", "").replace("?inline=1", "")}
        className="self-start rounded-lg border border-[var(--border)] px-3 py-1.5 text-sm hover:border-[var(--accent-2)]"
      >
        baixar {current.key === "combined" ? "final_partida.mp4" : `final_${current.key}.mp4`}
      </a>
    </div>
  );
}
