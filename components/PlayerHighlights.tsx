"use client";

import { useMemo, useState } from "react";
import { HighlightRow } from "@/components/HighlightRow";
import type { HighlightsReport, JobStage } from "@/types/job";

export function PlayerHighlights({
  jobId,
  report,
  stage,
}: {
  jobId: string;
  report: HighlightsReport;
  stage: JobStage;
}) {
  const review = stage === "awaiting-selection";

  const [open, setOpen] = useState<string | null>(
    review ? null : report.players[0]?.steamId64 ?? null,
  );
  const [teamFilter, setTeamFilter] = useState<"all" | "CT" | "TERRORIST">("all");
  // seleção: steamId64 -> Set de highlight ids. Padrão: NADA marcado — o
  // usuário escolhe quem quer para não gerar vídeo gigante.
  const [keep, setKeep] = useState<Record<string, Set<number>>>(() => {
    const init: Record<string, Set<number>> = {};
    for (const p of report.players) init[p.steamId64] = new Set();
    return init;
  });
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  const players = useMemo(
    () =>
      report.players
        .filter((p) => teamFilter === "all" || p.team === teamFilter)
        .filter((p) => p.highlights.length > 0),
    [report.players, teamFilter],
  );

  const totalSelected = Object.values(keep).reduce((n, s) => n + s.size, 0);
  const playersSelected = Object.values(keep).filter((s) => s.size > 0).length;

  const toggleHighlight = (sid: string, id: number) => {
    setKeep((prev) => {
      const next = { ...prev, [sid]: new Set(prev[sid]) };
      next[sid].has(id) ? next[sid].delete(id) : next[sid].add(id);
      return next;
    });
  };

  const togglePlayer = (sid: string) => {
    setKeep((prev) => {
      const p = report.players.find((x) => x.steamId64 === sid);
      if (!p) return prev;
      const all = p.highlights.map((h) => h.id);
      const has = prev[sid].size > 0;
      return { ...prev, [sid]: new Set(has ? [] : all) };
    });
  };

  const setAll = (on: boolean) => {
    setKeep(() => {
      const next: Record<string, Set<number>> = {};
      for (const p of report.players) {
        next[p.steamId64] = new Set(on ? p.highlights.map((h) => h.id) : []);
      }
      return next;
    });
  };

  const submit = async () => {
    setSubmitting(true);
    const payload = {
      keep: Object.fromEntries(
        Object.entries(keep).map(([sid, s]) => [sid, [...s]]),
      ),
    };
    const r = await fetch(`/api/jobs/${jobId}/selection`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    setSubmitting(false);
    if (r.ok) setSubmitted(true);
  };

  return (
    <div className="flex flex-col gap-3">
      {review && (
        <div className="sticky top-2 z-10 rounded-xl border border-[var(--accent)] bg-[var(--panel)] p-4">
          {submitted ? (
            <p className="text-sm text-[var(--good)]">
              Seleção enviada — {playersSelected} jogador(es), {totalSelected}{" "}
              lance(s). O job seguiu para a gravação.
            </p>
          ) : (
            <>
              <p className="mb-2 text-sm font-medium">
                Escolha de quem gerar os vídeos
              </p>
              <p className="mb-3 text-xs text-[var(--muted)]">
                Marque a caixa do jogador (pega todos os lances dele) ou abra e
                marque lances específicos. Só o que estiver marcado vai virar
                vídeo.
              </p>
              <div className="flex flex-wrap items-center gap-2">
                <button
                  onClick={() => setAll(true)}
                  className="rounded bg-[var(--panel-2)] px-2 py-1 text-xs hover:text-[var(--text)]"
                >
                  marcar todos
                </button>
                <button
                  onClick={() => setAll(false)}
                  className="rounded bg-[var(--panel-2)] px-2 py-1 text-xs hover:text-[var(--text)]"
                >
                  limpar
                </button>
                <span className="text-xs text-[var(--muted)]">
                  {playersSelected} jogador(es) · {totalSelected} lance(s)
                </span>
                <button
                  onClick={submit}
                  disabled={submitting || totalSelected === 0}
                  className="ml-auto rounded-lg bg-[var(--accent)] px-4 py-2 text-sm font-medium text-black disabled:opacity-50"
                >
                  {submitting ? "Enviando…" : "Gerar vídeos"}
                </button>
              </div>
            </>
          )}
        </div>
      )}

      <div className="flex items-center gap-2 text-xs">
        <span className="text-[var(--muted)]">Time:</span>
        {(["all", "CT", "TERRORIST"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTeamFilter(t)}
            className={`rounded px-2 py-1 ${
              teamFilter === t
                ? "bg-[var(--accent)] text-black"
                : "bg-[var(--panel-2)] text-[var(--muted)]"
            }`}
          >
            {t === "all" ? "todos" : t}
          </button>
        ))}
      </div>

      {players.map((p) => {
        const isOpen = open === p.steamId64;
        const sel = keep[p.steamId64]?.size ?? 0;
        return (
          <div
            key={p.steamId64}
            className={`overflow-hidden rounded-xl border bg-[var(--panel)] ${
              review && sel > 0
                ? "border-[var(--accent)]"
                : "border-[var(--border)]"
            }`}
          >
            <div className="flex w-full items-center gap-3 px-4 py-3">
              {review && (
                <input
                  type="checkbox"
                  checked={sel > 0}
                  onChange={() => togglePlayer(p.steamId64)}
                  className="size-4 accent-[var(--accent)]"
                  title="marcar/desmarcar o jogador inteiro"
                />
              )}
              <button
                onClick={() => setOpen(isOpen ? null : p.steamId64)}
                className="flex flex-1 items-center gap-3 text-left"
              >
                <span className="text-[var(--muted)]">{isOpen ? "▾" : "▸"}</span>
                <span className="font-medium">{p.displayName || p.name}</span>
                <span
                  className={`rounded px-1.5 py-0.5 text-xs ${
                    p.team === "CT"
                      ? "bg-[#2a3a55] text-[var(--accent-2)]"
                      : "bg-[#4a3a1e] text-[var(--accent)]"
                  }`}
                >
                  {p.team === "CT" ? "CT" : p.team === "TERRORIST" ? "TR" : "?"}
                </span>
                <span className="ml-auto text-xs text-[var(--muted)]">
                  {review && sel > 0 ? `${sel}/` : ""}
                  {p.highlights.length} lances · score{" "}
                  {p.totalScore.toFixed(1)} · {p.stats.kills}/{p.stats.deaths}/
                  {p.stats.assists} · {p.stats.headshotPct}% HS
                </span>
              </button>
            </div>

            {isOpen && (
              <ul>
                {p.highlights.map((h) => (
                  <HighlightRow
                    key={h.id}
                    h={h}
                    selectable={review && !submitted}
                    checked={keep[p.steamId64]?.has(h.id) ?? false}
                    onToggle={() => toggleHighlight(p.steamId64, h.id)}
                  />
                ))}
              </ul>
            )}
          </div>
        );
      })}
    </div>
  );
}
