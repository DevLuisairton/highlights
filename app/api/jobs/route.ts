import { listJobs } from "@/lib/jobs";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/** GET /api/jobs — lista todos os jobs, mais recentes primeiro. */
export async function GET() {
  const jobs = await listJobs();
  return Response.json({ jobs }, { headers: { "Cache-Control": "no-store" } });
}
