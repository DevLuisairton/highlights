# hillights

Envie um `.dem` de CS2 e receba os **melhores lances separados por
jogador**, estilo GamersClub / Allstar.gg.

Arquitetura **monolito** no mesmo padrão do projeto de referência
`planilha-automatizada`: um único app **Next.js** (App Router) que delega
o trabalho pesado a um **CLI Python** em `python/`, chamado via
`child_process.spawn`. Sem pastas `frontend/` / `backend/` separadas.

```
Next.js (porta 3000)                 python/main.py (CLI)
├─ POST /api/demos      ─ upload ──► run-job --job-id <id>
│                                     ├─ parsing   (demoparser2 → events.json)
├─ GET  /api/jobs/[id]/events (SSE)   ├─ scoring   (pesos → highlights.json, por jogador)
│   ◄── status.json ◄────────────────┤─ [review]  (pausa p/ seleção no painel)
├─ GET  /api/jobs/[id]                ├─ vdm       (partida.vdm)
└─ GET  /api/jobs/[id]/download/…     ├─ [recording]  Fase 2 — abre o CS2, grava clipes
                                      └─ [editing]    Fase 3 — ffmpeg monta final_<player>.mp4
```

## Estado atual

| Fase | O quê | Status |
|------|-------|--------|
| **1** | parsing + pontuação + `partida.vdm` + painel web | ✅ pronto |
| **2** | gravação dos clipes no CS2 via `-netconport` (`python/recorder.py`) | ✅ pronto |
| **3** | montagem com ffmpeg (`python/montage.py`) | ✅ pronto |

Com `RECORDER_ENABLED=0` (padrão) o job termina na Fase 1: você baixa o
`partida.vdm`, põe junto do `.dem` na pasta `csgo/` do CS2 e dá
`playdemo` — o VDM pula direto pros melhores lances de cada jogador.

### Fases 2 e 3 (gerar os vídeos) — máquina com CS2

No `.env`: `RECORDER_ENABLED=1`, `CS2_EXE`, `CS2_DEMOS_DIR` (a pasta
`.../game/csgo`), `RECORD_RESOLUTION` = a do seu monitor. Deixe o **Steam
aberto e logado** (CS2 fechado).

Fluxo: `parsing → scoring →` **`awaiting-selection`** `→ recording → editing
→ done`.

1. Após a pontuação o job **pausa** no painel. Você marca **quais jogadores
   / lances** quer (nada marcado por padrão — evita vídeo gigante) e clica
   "Gerar vídeos". Pra gravar todo mundo automático: `REVIEW_MODE=0`.
2. O worker sobe o CS2 com `-netconport`, conecta um socket TCP e comanda
   `demo_gototick <tick>; spec_mode 4; spec_lock_to_accountid <id>` lance a
   lance. O CS2 **ignora `PlayCommands` de VDM**, por isso o controle é pelo
   console, não pelo VDM.
3. A tela é capturada com ffmpeg (`RECORD_CAPTURE=ddagrab`, GPU; ou
   `gdigrab`) e recortada pelos tempos medidos → `clips/<slug>/clip_NN.mp4`.
4. A Fase 3 monta `montage/final_<slug>.mp4` por jogador + `final_partida.mp4`
   (normaliza resolução/fps, lower-third com nome + tags, trilha de
   `MONTAGE_MUSIC` por baixo).

- **Som do jogo:** a captura de tela é muda. Pra ter áudio, instale um
  loopback e aponte `RECORD_AUDIO_DEVICE` (ex.: `virtual-audio-capturer` do
  *screen-capture-recorder*, ou *VB-Audio Cable*). Sem isso só a música entra.
- `python main.py doctor` (na pasta `python/`) checa CS2 / ffmpeg.
- **Não mexa na máquina durante a gravação** se usar `gdigrab` (tela toda);
  `ddagrab` e `gdigrab-window` capturam só a janela do jogo.

## Rodar em desenvolvimento

```bash
npm install

# venv Python com o demoparser2
python -m venv python/.venv
python/.venv/Scripts/pip install -r python/requirements.txt   # Windows
# .venv/bin/pip install -r python/requirements.txt            # Linux/Mac

cp .env.example .env      # ajuste PYTHON_BIN (ver abaixo)
npm run dev               # http://localhost:3000
```

`PYTHON_BIN` no `.env` deve ser **`python`** (resolvido no PATH, se o
`pip install` foi no Python global) **ou um caminho absoluto** para o
Python do venv, por exemplo:

```
PYTHON_BIN=D:/.../hillights estilo gamersclub/python/.venv/Scripts/python.exe
```

## Testes

```bash
npm test                 # Vitest (lib/ + __tests__/)
python -m pytest         # motor de highlights (da raiz do repo)
```

## Como a detecção funciona

1. **parsing** (`python/parsing.py`) — `demoparser2` extrai `player_death`
   e `round_end`: atacante, vítima, time, arma, headshot, wallbang,
   noscope, através de fumaça, cego, distância, tick e round.
2. **agrupamento** (`python/scoring.py`) — as kills de cada jogador viram
   *sequências*. Se o jogador fez 3+ kills num round, o round inteiro dele
   é uma sequência só (o "round de 4K", mesmo com as mortes espalhadas);
   nos demais rounds, subdivide por gap de `SEQUENCE_GAP_SECONDS`.
3. **pontuação** — cada sequência recebe um score (pesos em
   `python/state/config.json`, editável a quente):
   - base por kill, bônus de headshot, wallbang, noscope, faca, fumaça,
     cego, no ar, longa distância, kills rápidas em sequência;
   - multikill (2K/3K/4K/ACE);
   - clutch 1vN vencido (heurística por round);
   - kill que fecha o round vencido (RWK).
4. **corte** — janela do clipe = 1ª kill − `CLIP_PREROLL_SECONDS` até a
   última + `CLIP_POSTROLL_SECONDS`, presa aos limites do round.
5. **saída** — `highlights.json` com **todo jogador que teve ≥1 kill**
   (0 kills é ignorado), ordenados por score total, cada um com seus top
   `PER_PLAYER_TOP_N` lances e tags (`ACE`, `1v3`, `3HS`, `wallbang`…).
   `SCORE_MIN` é filtro primário mas nunca zera um jogador com kills — se
   nada passar, entra o melhor lance dele mesmo assim.

Todos os parâmetros estão no `.env` (ver `.env.example`).

## Docker (só detecção)

A gravação no CS2 **não roda em container** (precisa de desktop + GPU).
Em Docker o app faz parsing + score + VDM:

```bash
cp .env.example .env      # defina SITE_ADDRESS (domínio, ou "localhost")
docker compose up --build
```

Caddy expõe HTTPS nas portas 80/443 e faz proxy pro `web:3000`; os jobs
persistem no volume `hillights-jobs`.

## Estrutura

```
app/
  page.tsx                     upload + lista de jobs
  jobs/[jobId]/page.tsx        progresso ao vivo, lances por jogador, downloads
  api/demos/route.ts           POST — streaming do .dem, cria job, dispara worker
  api/jobs/route.ts            GET  — lista
  api/jobs/[jobId]/route.ts    GET status + highlights · DELETE
  api/jobs/[jobId]/events/…    GET  — SSE do status.json
  api/jobs/[jobId]/selection/… POST — modo review
  api/jobs/[jobId]/download/[kind]/…  highlights.json | vdm | clip | final | combined
components/                    DemoUploader, JobList, JobView, JobProgress,
                               PlayerHighlights, HighlightRow, DownloadBar
lib/
  paths.ts                     PYTHON_BIN / PYTHON_DIR / STATE_DIR / JOBS_DIR
  python-runner.ts             spawn com fila + dedupe (chamadas curtas)
  worker.ts                    dispara run-job destacado (job longo)
  jobs.ts                      criar / ler / listar / apagar jobs
instrumentation.ts + .node.ts  housekeeping (TTL dos jobs)
types/job.ts                   schema espelhado de status.json / highlights.json
python/
  main.py                      CLI: run-job | parse-demo | score | gen-vdm | list-jobs | doctor
  config.py                    env + state/config.json (pesos)
  jobstate.py                  status.json (escrita atômica) + espera da seleção
  parsing.py                   demoparser2 → dict de eventos
  scoring.py                   agrupamento + pontuação + clutch
  vdmgen.py                    highlights → partida.vdm
  recorder.py                  Fase 2 (esqueleto)
  montage.py                   Fase 3 (esqueleto)
  state/config.json            pesos da pontuação
  state/jobs/<id>/             status.json, uploads/partida.dem, events.json,
                               highlights.json, partida.vdm, clips/, montage/
```
