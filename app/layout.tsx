import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "hillights — highlights de CS2 a partir de .dem",
  description:
    "Envie um .dem de CS2 e receba os melhores lances separados por jogador, estilo GamersClub.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="pt-BR">
      <body className="min-h-screen">
        <header className="border-b border-[var(--border)] bg-[var(--panel)]">
          <div className="mx-auto flex max-w-5xl items-center gap-3 px-6 py-4">
            <span className="text-lg font-bold tracking-tight">
              <span className="text-[var(--accent)]">hi</span>llights
            </span>
            <span className="text-xs text-[var(--muted)]">
              highlights de CS2 por jogador
            </span>
          </div>
        </header>
        <main className="mx-auto max-w-5xl px-6 py-8">{children}</main>
      </body>
    </html>
  );
}
