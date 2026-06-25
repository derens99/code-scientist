import { NextResponse } from "next/server";
import { applyRunCommand } from "@/lib/codeScientist";

export const runtime = "nodejs";

export async function POST(request: Request, { params }: { params: Promise<{ runId: string }> }) {
  try {
    const { runId } = await params;
    const body = await request.json();
    const state = await applyRunCommand(runId, {
      command: String(body.command ?? "")
    });
    return NextResponse.json({ state });
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Unable to apply command" },
      { status: 400 }
    );
  }
}
