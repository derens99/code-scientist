import { NextResponse } from "next/server";
import { applyProximityOverride } from "@/lib/codeScientist";
import { assertTrustedMutationRequest, mutationErrorStatus } from "@/lib/requestSecurity";

export const runtime = "nodejs";

export async function POST(request: Request, { params }: { params: Promise<{ runId: string }> }) {
  try {
    assertTrustedMutationRequest(request);
    const { runId } = await params;
    const body = await request.json();
    const state = await applyProximityOverride(runId, {
      source: String(body.source ?? ""),
      target: String(body.target ?? ""),
      decision: String(body.decision ?? "") as "merge" | "preserve",
      clusterId: String(body.clusterId ?? ""),
      reason: String(body.reason ?? "")
    });
    return NextResponse.json({ state });
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Unable to update proximity decision" },
      { status: mutationErrorStatus(error) }
    );
  }
}
