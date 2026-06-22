import { NextResponse } from "next/server";
import { listRuns } from "@/lib/codeScientist";

export const runtime = "nodejs";

export async function GET() {
  return NextResponse.json({ runs: await listRuns() });
}
