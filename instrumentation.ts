/**
 * Hook do Next no boot. Sem lógica aqui: a limpeza de jobs antigos (TTL)
 * acontece de forma oportunista em lib/jobs.ts::listJobs() (a rota /api/jobs
 * é chamada de poucos em poucos segundos pela UI).
 *
 * Antes o housekeeping vivia num instrumentation.node.ts que fazia
 * `readdir(python/state/jobs)` — o Turbopack passava a rastrear a árvore
 * inteira de python/state/ pro bundle e o build quebrava se um worker.log
 * estivesse momentaneamente travado pelo worker.
 */
export function register() {}
