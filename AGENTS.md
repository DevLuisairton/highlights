# Notas para agentes / contribuidores

Arquitetura **monolito** no mesmo padrão do projeto `planilha-automatizada`:
um único app Next.js (App Router) que delega o trabalho pesado a um CLI
Python em `python/`, invocado via `child_process.spawn`. Sem pastas
`frontend/` / `backend/` separadas.

## Regras

- **stdout do Python = JSON puro** (consumido pelo Next). Logs de progresso
  vão para **stderr** (acabam em `python/state/jobs/<id>/worker.log`).
- O progresso de um job é o arquivo `python/state/jobs/<id>/status.json` —
  escrito só pelo Python (troca atômica em `jobstate.write_status`), lido
  pelo Next (`lib/jobs.ts`) e transmitido por SSE em
  `/api/jobs/[id]/events`.
- `types/job.ts` espelha o schema de `status.json` e `highlights.json`.
  Mudou um lado, muda o outro.
- Chamadas curtas ao Python passam por `lib/python-runner.ts` (fila +
  dedupe). O job longo roda destacado via `lib/worker.ts`
  (`spawn(..., { detached: true }).unref()`).
- Caminhos de download são resolvidos **dentro** de `jobDir(jobId)` e
  validados contra path traversal.

## Rodar

```
npm install
python -m venv python/.venv && python/.venv/Scripts/pip install -r python/requirements.txt
npm run dev          # http://localhost:3000
```

Testes: `npm test` (Vitest) e `python -m pytest` (da raiz).

## Fases

1. ✅ parsing + score + VDM + UI (roda sem CS2)
2. ✅ `python/recorder.py` — **console TCP do CS2** (`-netconport`): sobe o
   CS2, conecta um socket e manda `demo_gototick` / `spec_lock_to_accountid`
   por lance; a tela é capturada com ffmpeg (`ddagrab`/`gdigrab`) e recortada
   pelos tempos medidos em `time.time()`. O CS2 ignora `PlayCommands` de VDM,
   então VDM só serve pro "tour" em modo detecção.
3. ✅ `python/montage.py` — ffmpeg: normaliza, lower-third, concat, trilha.
   `final_<slug>.mp4` por jogador + `final_partida.mp4`.

## Modelo de highlight (referência: Highlights da Gamers Club)

Cada highlight é uma **jogada independente** — 1 sequência de kills de 1
jogador em 1 round. `scoring.group_sequences` opera sobre as kills de UM
jogador só, então nunca mistura jogadores; um round pode ter N highlights.
`build_report` devolve `report["highlights"]` (lista PLANA, ordenada por
`roundNumber` + `tickStart`, com `globalId` 1..N) além de `players[]`.

Vínculo obrigatório evento → jogador → POV: cada highlight carrega
`steamId64` / `accountId` / `povAccountId` (=== `accountId`) / `team` /
`roundNumber` / `kills[]` / `povValid`. `povValid = steamId64 de 17 díg.
começando 7656119 e accountId > 0`. `vdmgen.build_vdm` e `recorder.record`
**pulam** clipes com `povValid=false` ou `accountId<=0` — melhor não gerar
do que gravar POV errado. O recorder trava a câmera com
`spec_autodirector 0; spec_mode 4; spec_lock_to_accountid <acc>;
spec_player_by_accountid <acc>` enquanto PAUSADO, e reforça a cada ~4s
durante o clipe.

## Seleção de jogadores (obrigatória antes de gravar)

Com `RECORDER_ENABLED=1` e `REVIEW_MODE=1` (padrão), o `run-job` pausa em
`stage="awaiting-selection"` após a pontuação. O painel
(`PlayerHighlights.tsx`) mostra checkbox por jogador / por lance, **nada
marcado por padrão**. `POST /api/jobs/[id]/selection` grava
`selection.json` (`{keep: {steamId64: [highlightId...]}}`), o worker sai do
`wait_for_selection` e só grava o que foi marcado. `vdmgen.build_vdm(...,
keep=...)` é quem filtra; `keep[sid]=[]` exclui o jogador, chave ausente =
inclui tudo (então o front sempre manda todos os steamId64).

Ordem dos nomes de arquivo: `_slug(name)` (`[A-Za-z0-9_-]`) é a fonte —
pasta dos clipes, `final_<slug>.mp4`, e o campo `slug` em highlights.json.
`clips.json` (escrito por recorder/gen-vdm) mapeia clipe → jogador → score.
