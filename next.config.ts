import type { NextConfig } from "next";

// Mesmo padrão do projeto de referência (planilha-automatizada): CSP restritiva
// como segunda linha contra XSS, standalone pra imagem Docker enxuta, e o
// header X-Powered-By desligado.
const isDev = process.env.NODE_ENV !== "production";
const CSP = [
  "default-src 'self'",
  `script-src 'self' 'unsafe-inline'${isDev ? " 'unsafe-eval'" : ""}`,
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: https://avatars.steamstatic.com https://avatars.akamai.steamstatic.com",
  `connect-src 'self'${isDev ? " ws:" : ""}`,
  "media-src 'self' blob:",
  "frame-ancestors 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "object-src 'none'",
].join("; ");

const nextConfig: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
  // python/state/ é dado em runtime (uploads .dem, worker.log, clips, vídeos)
  // — nunca deve entrar no rastreamento de arquivos do build. Sem isto, um
  // worker.log momentaneamente travado pelo worker faz o build inteiro
  // abortar ("Acesso negado" ao hashear o arquivo).
  outputFileTracingExcludes: {
    "*": ["./python/state/**", "./python/.venv/**"],
  },
  // Uploads de .dem passam de 100 MB — o limite padrão de 1 MB do body parser
  // das Server Actions não se aplica a Route Handlers (que usam streaming),
  // mas deixamos explícito o teto pra Server Actions caso alguém adicione uma.
  experimental: {
    serverActions: { bodySizeLimit: "512mb" },
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Frame-Options", value: "DENY" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "Content-Security-Policy", value: CSP },
        ],
      },
    ];
  },
};

export default nextConfig;
