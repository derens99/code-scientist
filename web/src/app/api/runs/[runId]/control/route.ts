import { NextResponse } from "next/server";
import { writeRunControl } from "@/lib/codeScientist";
import { assertTrustedMutationRequest, mutationErrorStatus } from "@/lib/requestSecurity";

export const runtime = "nodejs";

export async function POST(request: Request, { params }: { params: Promise<{ runId: string }> }) {
  try {
    assertTrustedMutationRequest(request);
    const { runId } = await params;
    const body = await request.json();
    const action = String(body.action ?? "");
    if (action !== "pause" && action !== "resume" && action !== "stop") {
      throw new Error("Control action must be pause, resume, or stop.");
    }
    await writeRunControl(runId, action);
    return NextResponse.json({ ok: true });
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Unable to control run" },
      { status: mutationErrorStatus(error) }
    );
  }
}
