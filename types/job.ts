/**
 * Espelha o schema escrito por python/main.py em
 * python/state/jobs/<id>/status.json e highlights.json.
 * Qualquer mudança aqui precisa acompanhar o lado Python.
 */

export type JobStage =
  | "queued"
  | "parsing"
  | "scoring"
  | "awaiting-selection"
  | "vdm"
  | "recording"
  | "editing"
  | "done"
  | "error";

export interface JobStatus {
  jobId: string;
  stage: JobStage;
  /** 0..100 dentro da etapa atual. */
  progress: number;
  /** Mensagem curta de progresso pra UI. */
  message: string;
  /** Nome original do arquivo .dem enviado. */
  demoName: string;
  createdAt: string;
  updatedAt: string;
  /** Preenchido a partir de parsing. */
  map?: string;
  matchScore?: string;
  playersCount?: number;
  highlightsCount?: number;
  /** Só quando stage === "error". */
  error?: string;
  /** true quando RECORDER_ENABLED=0: o job termina em "vdm". */
  detectionOnly?: boolean;
  /** Nomes dos arquivos gerados em montage/ (Fase 3). */
  montageOutputs?: string[];
}

export interface HighlightTag {
  label: string;
}

export interface Highlight {
  /** id sequencial DENTRO do jogador (1..N). */
  id: number;
  /** id sequencial NA PARTIDA inteira (1..N), por round+tick. */
  globalId?: number;
  score: number;
  /** total_rounds_played na 1ª kill (0-based, back-compat). */
  round: number;
  /** número do round 1-based, casado por tick — é o "Round N". */
  roundNumber: number;
  tickStart: number;
  tickEnd: number;
  /** Segundos desde o início do demo (tickStart / tickrate). */
  timeStart: number;
  timeEnd: number;
  /** Ex.: ["ACE", "3HS", "1v3", "wallbang"] */
  tags: string[];
  killCount: number;
  /** ── vínculo obrigatório evento → jogador → POV ── */
  steamId64: string;
  accountId: number;
  /** account id da fonte de vídeo — DEVE ser === accountId. */
  povAccountId: number;
  playerName: string;
  team: "CT" | "TERRORIST" | "UNKNOWN";
  /** false = steamId64/accountId inválido → não grava (evita POV errado). */
  povValid: boolean;
  /** slug do jogador (só na lista plana report.highlights). */
  player?: string;
  playerDisplayName?: string;
  kills?: {
    tick: number;
    victim: string;
    weapon: string;
    headshot: boolean;
    noscope: boolean;
    penetrated: number;
  }[];
}

export interface PlayerHighlights {
  steamId64: string;
  /** account id de 32 bits (steamId64 - 76561197960265728), usado no VDM. */
  accountId: number;
  /** nick cru do demo (pode ter selos/emoji que não renderizam). */
  name: string;
  /** nick sem os selos da GamersClub — usar na UI. */
  displayName: string;
  /** nome sanitizado ([A-Za-z0-9_-]) — usado nos nomes de arquivo/pasta. */
  slug: string;
  team: "CT" | "TERRORIST" | "UNKNOWN";
  avatar?: string;
  stats: {
    kills: number;
    deaths: number;
    assists: number;
    headshotPct: number;
  };
  totalScore: number;
  highlights: Highlight[];
}

export interface HighlightsReport {
  jobId: string;
  map: string;
  matchScore: string;
  tickrate: number;
  players: PlayerHighlights[];
  /** Lista PLANA de highlights independentes (Partida → Highlight 1..N),
   * ordenada por round e tick. Mesmos objetos de players[].highlights. */
  highlights: Highlight[];
  /** Ranking geral por totalScore, referências por steamId64. */
  ranking: { steamId64: string; name: string; totalScore: number }[];
}

/** Corpo do POST /api/jobs/[jobId]/selection (modo review). */
export interface SelectionPayload {
  /** Mapa steamId64 -> lista de highlight ids a manter. */
  keep: Record<string, number[]>;
}

/** Uma entrada de clips.json — um clipe gravado (ou a gravar). */
export interface ClipInfo {
  file: string;
  stem: string;
  /** slug do jogador (pasta em clips/). */
  player: string;
  playerName: string;
  steamId64: string;
  accountId: number;
  /** === accountId. POV do vídeo. */
  povAccountId: number;
  team: "CT" | "TERRORIST" | "UNKNOWN";
  /** 1..N por jogador, na ordem de tick (é o `n` do endpoint de download). */
  index: number;
  highlightId: number;
  /** 1..N na partida inteira, ordenado por round+tick. */
  globalId: number;
  score: number;
  tags: string[];
  round: number;
  roundNumber: number;
  tickStart: number;
  tickEnd: number;
}
