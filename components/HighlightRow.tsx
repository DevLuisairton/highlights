"use client";

import type { Highlight } from "@/types/job";

const TAG_COLOR: Record<string, string> = {
  ACE: "bg-[var(--accent)] text-black",
  "4K": "bg-[var(--accent)] text-black",
  "3K": "bg-[var(--accent-2)] text-black",
  clutch: "bg-[var(--good)] text-black",
};

function tagClass(tag: string): string {
  if (tag.startsWith("1v")) return TAG_COLOR.clutch;
  return TAG_COLOR[tag] ?? "bg-[var(--panel-2)] text-[var(--muted)]";
}

export function HighlightRow({
  h,
  selectable,
  checked,
  onToggle,
}: {
  h: Highlight;
  selectable: boolean;
  checked: boolean;
  onToggle: () => void;
}) {
  const dur = Math.round(h.timeEnd - h.timeStart);
  return (
    <li className="flex items-center gap-3 border-t border-[var(--border)] px-4 py-2.5 text-sm first:border-t-0">
      {selectable && (
        <input
          type="checkbox"
          checked={checked}
          onChange={onToggle}
          className="size-4 accent-[var(--accent)]"
        />
      )}
      <span className="w-14 shrink-0 tabular-nums text-[var(--muted)]">
        R{h.round}
      </span>
      <span className="w-16 shrink-0 tabular-nums text-[var(--muted)]">
        {dur}s
      </span>
      <span className="w-10 shrink-0 tabular-nums font-medium text-[var(--accent)]">
        {h.score.toFixed(1)}
      </span>
      <div className="flex flex-1 flex-wrap gap-1">
        {h.tags.map((t) => (
          <span
            key={t}
            className={`rounded px-1.5 py-0.5 text-xs font-medium ${tagClass(t)}`}
          >
            {t}
          </span>
        ))}
      </div>
      <span className="shrink-0 text-xs text-[var(--muted)]">
        {h.killCount} kills
      </span>
    </li>
  );
}
