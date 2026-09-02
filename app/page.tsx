import { DemoUploader } from "@/components/DemoUploader";
import { JobList } from "@/components/JobList";

export const dynamic = "force-dynamic";

export default function HomePage() {
  return (
    <div className="flex flex-col gap-8">
      <section>
        <h1 className="mb-1 text-xl font-semibold">Enviar demo</h1>
        <p className="mb-4 text-sm text-[var(--muted)]">
          Arraste um arquivo <code>.dem</code> de CS2 (baixado da GamersClub, da
          FACEIT ou do próprio cliente). A automação detecta as melhores
          sequências de cada jogador da partida.
        </p>
        <DemoUploader />
      </section>

      <section>
        <h2 className="mb-3 text-lg font-semibold">Jobs</h2>
        <JobList />
      </section>
    </div>
  );
}
