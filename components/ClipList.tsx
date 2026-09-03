"use client";

import { useState } from "react";
import type { ClipInfo } from "@/types/job";

const TEAM = { CT: "CT", TERRORIST: "TR", UNKNOWN: "?" } as const;

/**
 * Partida → Highlight 1..N. Cada highlight é um vídeo independente, no POV
 * do jogador responsável pela jogada (mesmo estilo dos Highlights da
 * Gamers Club). Nunca junta jogadas diferentes num vídeo só.
 */
export function ClipList({
  jobId,
  clips,
}: {
  jobId: string;
  clips: ClipInfo[];
}) {
  if (!clips.length) return null;
  const ordered = clips
    .slice()
    .sort((a, b) => a.globalId - b.globalId || a.tickStart - b.tickStart);

  return (
    <div className="flex flex-col gap-3">
      <h3 className="text-sm font-semibold">
        Highlights da partida ({ordered.length}) — um vídeo por jogada
      </h3>
      <div className="grid gap-3 sm:grid-cols-2">
        {ordered.map((c) => (
          <ClipCard key={c.stem} jobId={jobId} clip={c} />
        ))}
      </div>
    </div>
  );
}

function ClipCard({ jobId, clip }: { jobId: string; clip: ClipInfo }) {
  const [show, setShow] = useState(false);
  const src = `/api/jobs/${jobId}/download/clip?player=${encodeURIComponent(
    clip.player,
  )}&n=${clip.index}`;
  const dur = Math.max(1, Math.round(clip.tickEnd - clip.tickStart) / 64);

  return (
    <div className="flex flex-col gap-2 rounded-lg border border-[var(--border)] bg-[var(--panel)] p-3">
      <div className="flex items-center gap-2 text-sm">
        <span className="rounded bg-[var(--panel-2)] px-1.5 py-0.5 text-xs tabular-nums text-[var(--muted)]">
          #{clip.globalId}
        </span>
        <span className="tabular-nums text-[var(--muted)]">
          Round {clip.roundNumber}
        </span>
        <span
          className={`rounded px-1.5 py-0.5 text-xs ${
            clip.team === "CT"
              ? "bg-[#2a3a55] text-[var(--accent-2)]"
              : "bg-[#4a3a1e] text-[var(--accent)]"
          }`}
        >
          {TEAM[clip.team]}
        </span>
        <span className="ml-auto font-medium text-[var(--accent)]">
          {clip.score.toFixed(1)}
        </span>
      </div>

      <div className="flex flex-wrap items-center gap-1.5">
        <span className="text-sm font-medium">{clip.playerName}</span>
        {clip.tags.map((t) => (
          <span
            key={t}
            className="rounded bg-[var(--panel-2)] px-1.5 py-0.5 text-xs text-[var(--muted)]"
          >
            {t}
          </span>
        ))}
        <span className="text-xs text-[var(--muted)]">· {dur}s</span>
      </div>

      {show ? (
        <video
          src={`${src}&inline=1`}
          controls
          autoPlay
          preload="metadata"
          className="w-full rounded bg-black"
          style={{ aspectRatio: "16 / 9" }}
        />
      ) : (
        <button
          onClick={() => setShow(true)}
          className="flex aspect-video w-full items-center justify-center rounded bg-black/60 text-sm text-[var(--muted)] hover:text-[var(--text)]"
        >
          ▶ POV de {clip.playerName}
        </button>
      )}

      <a
        href={src}
        className="self-start rounded border border-[var(--border)] px-2.5 py-1 text-xs hover:border-[var(--accent-2)]"
      >
        baixar highlight #{clip.globalId}
      </a>
    </div>
  );
}
