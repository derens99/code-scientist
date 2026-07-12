import { NextResponse } from "next/server";
import { updateRunGuidance } from "@/lib/codeScientist";
import { assertTrustedMutationRequest, mutationErrorStatus } from "@/lib/requestSecurity";

export const runtime = "nodejs";

export async function POST(request: Request, { params }: { params: Promise<{ runId: string }> }) {
  try {
    assertTrustedMutationRequest(request);
    const { runId } = await params;
    const body = await request.json();
    const state = await updateRunGuidance(runId, {
      objective: String(body.objective ?? ""),
      preferences: toStringList(body.preferences),
      constraints: toStringList(body.constraints),
      metrics: toStringList(body.metrics),
      safetyNotes: toStringList(body.safetyNotes),
      allowedSources: toStringList(body.allowedSources),
      allowedTools: toStringList(body.allowedTools),
      outputFormats: toStringList(body.outputFormats),
      terminationCriteria: toStringList(body.terminationCriteria),
      followUpDirection: String(body.followUpDirection ?? "")
    });
    return NextResponse.json({ state });
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Unable to update guidance" },
      { status: mutationErrorStatus(error) }
    );
  }
}

function toStringList(value: unknown) {
  return Array.isArray(value) ? value.map(String) : [];
}
