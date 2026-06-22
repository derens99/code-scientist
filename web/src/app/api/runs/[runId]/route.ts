import { NextResponse } from "next/server";
import { readRunState } from "@/lib/codeScientist";

export const runtime = "nodejs";

export async function GET(_request: Request, { params }: { params: Promise<{ runId: string }> }) {
  try {
    const { runId } = await params;
    return NextResponse.json({ state: await readRunState(runId) });
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Unable to read run" },
      { status: 404 }
    );
  }
}
