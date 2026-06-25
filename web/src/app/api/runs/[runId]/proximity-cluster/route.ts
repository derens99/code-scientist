import { NextResponse } from "next/server";
import { applyProximityClusterOverride } from "@/lib/codeScientist";

export const runtime = "nodejs";

export async function POST(request: Request, { params }: { params: Promise<{ runId: string }> }) {
  try {
    const { runId } = await params;
    const body = await request.json();
    const state = await applyProximityClusterOverride(runId, {
      clusterId: String(body.clusterId ?? ""),
      decision: String(body.decision ?? "") as "merge" | "preserve",
      reason: String(body.reason ?? "")
    });
    return NextResponse.json({ state });
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Unable to update proximity cluster" },
      { status: 400 }
    );
  }
}
