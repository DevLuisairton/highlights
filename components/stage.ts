import type { JobStage } from "@/types/job";

export const STAGE_LABEL: Record<JobStage, string> = {
  queued: "Na fila",
  parsing: "Lendo demo",
  scoring: "Pontuando",
  "awaiting-selection": "Aguardando seleção",
  vdm: "Gerando VDM",
  recording: "Gravando",
  editing: "Montando",
  done: "Concluído",
  error: "Erro",
};

/** Ordem das etapas pra desenhar a barra de progresso do job. */
export const STAGE_ORDER: JobStage[] = [
  "queued",
  "parsing",
  "scoring",
  "awaiting-selection",
  "vdm",
  "recording",
  "editing",
  "done",
];
