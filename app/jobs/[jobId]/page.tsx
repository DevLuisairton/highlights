import Link from "next/link";
import { notFound } from "next/navigation";
import { JobView } from "@/components/JobView";
import { isValidJobId, readJobStatus } from "@/lib/jobs";

export const dynamic = "force-dynamic";

export default async function JobPage({
  params,
}: {
  params: Promise<{ jobId: string }>;
}) {
  const { jobId } = await params;
  if (!isValidJobId(jobId)) notFound();
  const status = await readJobStatus(jobId);
  if (!status) notFound();

  return (
    <div className="flex flex-col gap-6">
      <Link
        href="/"
        className="text-sm text-[var(--accent-2)] hover:underline"
      >
        ← voltar
      </Link>
      <JobView jobId={jobId} initialStage={status.stage} />
    </div>
  );
}
