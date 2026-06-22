import { NextResponse } from "next/server";
import { clampInteger, sanitizeRunName, startRun } from "@/lib/codeScientist";

export const runtime = "nodejs";

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const run = await startRun({
      objective: String(body.objective ?? ""),
      cycles: clampInteger(body.cycles, 1, 5, 1),
      maxHypotheses: clampInteger(body.maxHypotheses, 2, 20, 6),
      maxMatches: clampInteger(body.maxMatches, 0, 40, 4),
      runName: sanitizeRunName(String(body.runName ?? ""))
    });
    return NextResponse.json({ run });
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Unable to start run" },
      { status: 400 }
    );
  }
}
