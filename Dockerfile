# syntax=docker/dockerfile:1
#
# Imagem com Node (build/runtime do Next.js) + Python (parsing do demo e
# geração do VDM) + ffmpeg. ATENÇÃO: a etapa de GRAVAÇÃO (abrir o CS2 e
# capturar os clipes) NÃO roda neste container — precisa de desktop Windows
# + GPU. Em Docker, use RECORDER_ENABLED=0 (só detecção + VDM).
#
# Estágios base/deps/builder/pydeps só produzem artefatos copiados pro
# estágio `runner` — só a imagem final (a partir de `runner`) é executada.
# nosemgrep: dockerfile.security.missing-user.missing-user
FROM node:20-slim AS base
RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-venv python3-pip ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# ---- dependências JS ----
# nosemgrep: dockerfile.security.missing-user.missing-user
FROM base AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

# ---- build do Next.js ----
# nosemgrep: dockerfile.security.missing-user.missing-user
FROM base AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

# ---- dependências Python num venv ----
# nosemgrep: dockerfile.security.missing-user.missing-user
FROM base AS pydeps
WORKDIR /app
COPY python/requirements.txt ./python/requirements.txt
RUN python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir -r python/requirements.txt

# ---- imagem final ----
FROM base AS runner
WORKDIR /app
ENV NODE_ENV=production \
    PORT=3000 \
    PYTHON_BIN=python \
    PYTHON_DIR=/app/python \
    STATE_DIR=/app/python/state \
    RECORDER_ENABLED=0 \
    PATH="/opt/venv/bin:$PATH" \
    TZ=America/Sao_Paulo

RUN groupadd --system --gid 1001 nodejs \
    && useradd --system --uid 1001 --gid nodejs nextjs

COPY --from=pydeps /opt/venv /opt/venv
COPY python ./python
COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static

# state/jobs recebe escrita em runtime e é um volume persistente (ver
# docker-compose.yml). .next/cache é escrito pelo Next em runtime.
RUN mkdir -p /app/python/state/jobs /app/.next/cache \
    && chown -R nextjs:nodejs /app/python /app/.next

USER nextjs
EXPOSE 3000
CMD ["node", "server.js"]
