# Code Scientist UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a polished local Next.js and Mantine workbench for starting Code Scientist runs and inspecting persisted research output.

**Architecture:** Add a new `web/` Next.js App Router project. Route handlers in the Next.js app read `runs/*` files and invoke the existing Python CLI through `uv run code-scientist run`, keeping the Python package unchanged. The UI renders a dense research workbench with a setup rail, run selector, leaderboard, hypothesis detail, tournament/meta-review tabs, and report view.

**Tech Stack:** Next.js, React, TypeScript, Mantine, lucide-react, Node child process APIs, existing Python `uv` CLI.

---

## File Structure

- Create `web/package.json`: scripts and dependencies.
- Create `web/next.config.ts`: minimal Next.js config.
- Create `web/tsconfig.json`: TypeScript config for Next.js.
- Create `web/src/app/layout.tsx`: Mantine provider and global shell metadata.
- Create `web/src/app/page.tsx`: client-side workbench composition.
- Create `web/src/app/api/runs/route.ts`: list persisted runs.
- Create `web/src/app/api/runs/[runId]/route.ts`: return parsed run state.
- Create `web/src/app/api/runs/[runId]/report/route.ts`: return report markdown.
- Create `web/src/app/api/runs/start/route.ts`: validate and start a new local run.
- Create `web/src/components/Workbench.tsx`: main interactive UI.
- Create `web/src/components/RunSetup.tsx`: run creation form.
- Create `web/src/components/RunOverview.tsx`: selected run summary.
- Create `web/src/components/HypothesisLeaderboard.tsx`: ranked hypothesis list.
- Create `web/src/components/HypothesisDetail.tsx`: selected hypothesis detail and review.
- Create `web/src/components/RunInsights.tsx`: matches, meta-review, and report tabs.
- Create `web/src/lib/codeScientist.ts`: server-side filesystem and CLI helpers.
- Create `web/src/lib/types.ts`: TypeScript types mirroring Python `RunState`.
- Create `web/src/lib/client.ts`: client fetch helpers.
- Create `web/src/styles/theme.ts`: Mantine theme.
- Create `web/src/app/globals.css`: layout and responsive CSS.

## Task 1: Scaffold The Web App

**Files:**
- Create: `web/package.json`
- Create: `web/next.config.ts`
- Create: `web/tsconfig.json`
- Create: `web/src/app/layout.tsx`
- Create: `web/src/styles/theme.ts`
- Create: `web/src/app/globals.css`

- [ ] **Step 1: Create package metadata and scripts**

Create `web/package.json`:

```json
{
  "name": "code-scientist-web",
  "version": "0.1.0",
  "private": true,
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "start": "next start",
    "lint": "next lint",
    "typecheck": "tsc --noEmit"
  },
  "dependencies": {
    "@mantine/core": "^8.0.0",
    "@mantine/hooks": "^8.0.0",
    "@tabler/icons-react": "^3.0.0",
    "lucide-react": "^0.468.0",
    "next": "^15.0.0",
    "react": "^19.0.0",
    "react-dom": "^19.0.0"
  },
  "devDependencies": {
    "@types/node": "^22.0.0",
    "@types/react": "^19.0.0",
    "@types/react-dom": "^19.0.0",
    "eslint": "^9.0.0",
    "eslint-config-next": "^15.0.0",
    "typescript": "^5.0.0"
  }
}
```

- [ ] **Step 2: Add Next.js and TypeScript config**

Create `web/next.config.ts`:

```ts
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
};

export default nextConfig;
```

Create `web/tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "ES2017",
    "lib": ["dom", "dom.iterable", "esnext"],
    "allowJs": false,
    "skipLibCheck": true,
    "strict": true,
    "noEmit": true,
    "esModuleInterop": true,
    "module": "esnext",
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "jsx": "preserve",
    "incremental": true,
    "plugins": [{ "name": "next" }],
    "paths": { "@/*": ["./src/*"] }
  },
  "include": ["next-env.d.ts", "**/*.ts", "**/*.tsx", ".next/types/**/*.ts"],
  "exclude": ["node_modules"]
}
```

- [ ] **Step 3: Add the Mantine theme and app layout**

Create `web/src/styles/theme.ts`:

```ts
import { createTheme, rem } from "@mantine/core";

export const theme = createTheme({
  primaryColor: "blue",
  defaultRadius: "sm",
  fontFamily:
    "Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif",
  headings: {
    fontFamily:
      "Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif",
    sizes: {
      h1: { fontSize: rem(26), lineHeight: "1.2" },
      h2: { fontSize: rem(20), lineHeight: "1.25" },
      h3: { fontSize: rem(16), lineHeight: "1.3" }
    }
  }
});
```

Create `web/src/app/layout.tsx`:

```tsx
import "@mantine/core/styles.css";
import "./globals.css";

import type { Metadata } from "next";
import { ColorSchemeScript, MantineProvider } from "@mantine/core";
import { theme } from "@/styles/theme";

export const metadata: Metadata = {
  title: "Code Scientist Workbench",
  description: "Local research workbench for Code Scientist runs"
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head>
        <ColorSchemeScript defaultColorScheme="light" />
      </head>
      <body>
        <MantineProvider theme={theme} defaultColorScheme="light">
          {children}
        </MantineProvider>
      </body>
    </html>
  );
}
```

- [ ] **Step 4: Add global workbench CSS**

Create `web/src/app/globals.css`:

```css
:root {
  color-scheme: light;
  background: #f5f7fb;
}

* {
  box-sizing: border-box;
}

html,
body {
  min-height: 100%;
  margin: 0;
}

body {
  background: #f5f7fb;
  color: #1f2937;
}

button,
input,
textarea {
  font: inherit;
}
```

- [ ] **Step 5: Install dependencies**

Run:

```bash
cd web && npm install
```

Expected: dependencies install and `web/package-lock.json` is created.

- [ ] **Step 6: Run typecheck**

Run:

```bash
cd web && npm run typecheck
```

Expected: PASS.

- [ ] **Step 7: Commit scaffold**

```bash
git add web/package.json web/package-lock.json web/next.config.ts web/tsconfig.json web/src/app/layout.tsx web/src/styles/theme.ts web/src/app/globals.css
git commit -m "chore: scaffold code scientist web app"
```

## Task 2: Add Run State Types And Server Helpers

**Files:**
- Create: `web/src/lib/types.ts`
- Create: `web/src/lib/codeScientist.ts`

- [ ] **Step 1: Define TypeScript run-state types**

Create `web/src/lib/types.ts`:

```ts
export type ResearchGoal = {
  id: string;
  objective: string;
  domain: string;
  preferences: string[];
  constraints: string[];
  metrics: string[];
  safety_notes: string[];
};

export type TestPlan = {
  experiment: string;
  metrics: string[];
  success_condition: string;
};

export type Hypothesis = {
  id: string;
  title: string;
  claim: string;
  rationale: string;
  assumptions: string[];
  evidence_refs: string[];
  test_plan: TestPlan;
  risks: string[];
  origin: string;
  parent_ids: string[];
  elo: number;
  status: string;
};

export type Review = {
  id: string;
  hypothesis_id: string;
  decision: string;
  scores: Record<string, number>;
  strengths: string[];
  weaknesses: string[];
  safety_notes: string[];
};

export type Match = {
  id: string;
  hypothesis_a: string;
  hypothesis_b: string;
  winner: string;
  rationale: string;
  elo_before: Record<string, number>;
  elo_after: Record<string, number>;
};

export type MetaReview = {
  id: string;
  common_weaknesses: string[];
  safety_concerns: string[];
  missing_evidence: string[];
  promising_directions: string[];
  prompt_feedback: string[];
};

export type SafetyDecision = {
  allowed: boolean;
  reason: string;
  flags: string[];
};

export type RunState = {
  goal: ResearchGoal;
  evidence: unknown[];
  hypotheses: Hypothesis[];
  reviews: Review[];
  matches: Match[];
  meta_reviews: MetaReview[];
  safety: SafetyDecision | null;
};

export type RunSummary = {
  id: string;
  objective: string;
  statePath: string;
  reportPath: string | null;
  updatedAt: string;
  hypothesisCount: number;
  reviewCount: number;
  matchCount: number;
  safetyAllowed: boolean | null;
  readable: boolean;
  error?: string;
};
```

- [ ] **Step 2: Implement safe filesystem and CLI helpers**

Create `web/src/lib/codeScientist.ts`:

```ts
import { spawn } from "node:child_process";
import { readdir, readFile, stat } from "node:fs/promises";
import path from "node:path";
import type { RunState, RunSummary } from "./types";

export type StartRunInput = {
  objective: string;
  cycles: number;
  maxHypotheses: number;
  maxMatches: number;
  runName: string;
};

export function repoRoot() {
  return process.env.CODE_SCIENTIST_ROOT
    ? path.resolve(process.env.CODE_SCIENTIST_ROOT)
    : path.resolve(process.cwd(), "..");
}

export function runsRoot() {
  return path.join(repoRoot(), "runs");
}

export function sanitizeRunName(value: string) {
  const cleaned = value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9._-]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 80);
  return cleaned || `ui-run-${Date.now()}`;
}

export function clampInteger(value: unknown, min: number, max: number, fallback: number) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) {
    return fallback;
  }
  return Math.min(max, Math.max(min, Math.trunc(parsed)));
}

export async function readRunState(runId: string): Promise<RunState> {
  const safeId = sanitizeRunName(runId);
  if (safeId !== runId) {
    throw new Error("Invalid run id.");
  }
  const statePath = path.join(runsRoot(), safeId, "state.json");
  return JSON.parse(await readFile(statePath, "utf8")) as RunState;
}

export async function readRunReport(runId: string) {
  const safeId = sanitizeRunName(runId);
  if (safeId !== runId) {
    throw new Error("Invalid run id.");
  }
  return readFile(path.join(runsRoot(), safeId, "report.md"), "utf8");
}

export async function listRuns(): Promise<RunSummary[]> {
  let entries: string[] = [];
  try {
    entries = await readdir(runsRoot());
  } catch {
    return [];
  }

  const summaries = await Promise.all(entries.map(readRunSummary));
  return summaries
    .filter((summary): summary is RunSummary => summary !== null)
    .sort((left, right) => right.updatedAt.localeCompare(left.updatedAt));
}

async function readRunSummary(runId: string): Promise<RunSummary | null> {
  if (sanitizeRunName(runId) !== runId) {
    return null;
  }

  const runDir = path.join(runsRoot(), runId);
  const statePath = path.join(runDir, "state.json");
  const reportPath = path.join(runDir, "report.md");

  try {
    const state = JSON.parse(await readFile(statePath, "utf8")) as RunState;
    const stateStats = await stat(statePath);
    let hasReport = false;
    try {
      await stat(reportPath);
      hasReport = true;
    } catch {
      hasReport = false;
    }
    return {
      id: runId,
      objective: state.goal.objective,
      statePath,
      reportPath: hasReport ? reportPath : null,
      updatedAt: stateStats.mtime.toISOString(),
      hypothesisCount: state.hypotheses.length,
      reviewCount: state.reviews.length,
      matchCount: state.matches.length,
      safetyAllowed: state.safety?.allowed ?? null,
      readable: true
    };
  } catch (error) {
    return {
      id: runId,
      objective: "Unreadable run state",
      statePath,
      reportPath: null,
      updatedAt: new Date(0).toISOString(),
      hypothesisCount: 0,
      reviewCount: 0,
      matchCount: 0,
      safetyAllowed: null,
      readable: false,
      error: error instanceof Error ? error.message : "Unable to read run"
    };
  }
}

export async function startRun(input: StartRunInput): Promise<RunSummary> {
  const objective = input.objective.trim();
  if (!objective) {
    throw new Error("Objective is required.");
  }

  const runName = sanitizeRunName(input.runName);
  const outDir = path.join("runs", runName);
  await runUv([
    "run",
    "code-scientist",
    "run",
    objective,
    "--cycles",
    String(input.cycles),
    "--max-hypotheses",
    String(input.maxHypotheses),
    "--max-matches",
    String(input.maxMatches),
    "--out",
    outDir
  ]);

  const summary = await readRunSummary(runName);
  if (!summary) {
    throw new Error("Run finished but no readable summary was found.");
  }
  return summary;
}

function runUv(args: string[]) {
  return new Promise<void>((resolve, reject) => {
    const child = spawn("uv", args, {
      cwd: repoRoot(),
      stdio: ["ignore", "pipe", "pipe"]
    });

    let stderr = "";
    child.stderr.on("data", (chunk) => {
      stderr += String(chunk);
    });
    child.on("error", reject);
    child.on("close", (code) => {
      if (code === 0) {
        resolve();
        return;
      }
      reject(new Error(stderr.trim() || `uv exited with code ${code}`));
    });
  });
}
```

- [ ] **Step 3: Run typecheck**

Run:

```bash
cd web && npm run typecheck
```

Expected: PASS.

- [ ] **Step 4: Commit helpers**

```bash
git add web/src/lib/types.ts web/src/lib/codeScientist.ts
git commit -m "feat: add code scientist run helpers"
```

## Task 3: Add Local API Routes

**Files:**
- Create: `web/src/app/api/runs/route.ts`
- Create: `web/src/app/api/runs/[runId]/route.ts`
- Create: `web/src/app/api/runs/[runId]/report/route.ts`
- Create: `web/src/app/api/runs/start/route.ts`

- [ ] **Step 1: Add run-list route**

Create `web/src/app/api/runs/route.ts`:

```ts
import { NextResponse } from "next/server";
import { listRuns } from "@/lib/codeScientist";

export async function GET() {
  return NextResponse.json({ runs: await listRuns() });
}
```

- [ ] **Step 2: Add run-state route**

Create `web/src/app/api/runs/[runId]/route.ts`:

```ts
import { NextResponse } from "next/server";
import { readRunState } from "@/lib/codeScientist";

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ runId: string }> }
) {
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
```

- [ ] **Step 3: Add report route**

Create `web/src/app/api/runs/[runId]/report/route.ts`:

```ts
import { NextResponse } from "next/server";
import { readRunReport } from "@/lib/codeScientist";

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ runId: string }> }
) {
  try {
    const { runId } = await params;
    return new NextResponse(await readRunReport(runId), {
      headers: { "content-type": "text/markdown; charset=utf-8" }
    });
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Unable to read report" },
      { status: 404 }
    );
  }
}
```

- [ ] **Step 4: Add start-run route**

Create `web/src/app/api/runs/start/route.ts`:

```ts
import { NextResponse } from "next/server";
import { clampInteger, sanitizeRunName, startRun } from "@/lib/codeScientist";

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const summary = await startRun({
      objective: String(body.objective ?? ""),
      cycles: clampInteger(body.cycles, 1, 5, 1),
      maxHypotheses: clampInteger(body.maxHypotheses, 2, 20, 6),
      maxMatches: clampInteger(body.maxMatches, 0, 40, 4),
      runName: sanitizeRunName(String(body.runName ?? ""))
    });
    return NextResponse.json({ run: summary });
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Unable to start run" },
      { status: 400 }
    );
  }
}
```

- [ ] **Step 5: Run typecheck**

Run:

```bash
cd web && npm run typecheck
```

Expected: PASS.

- [ ] **Step 6: Commit API routes**

```bash
git add web/src/app/api
git commit -m "feat: expose local run api"
```

## Task 4: Add Client Fetch Helpers And Workbench Page

**Files:**
- Create: `web/src/lib/client.ts`
- Create: `web/src/app/page.tsx`

- [ ] **Step 1: Add client API helpers**

Create `web/src/lib/client.ts`:

```ts
import type { RunState, RunSummary } from "./types";

export type StartRunPayload = {
  objective: string;
  cycles: number;
  maxHypotheses: number;
  maxMatches: number;
  runName: string;
};

async function parseJson<T>(response: Response): Promise<T> {
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error ?? "Request failed");
  }
  return payload as T;
}

export async function fetchRuns() {
  return parseJson<{ runs: RunSummary[] }>(await fetch("/api/runs", { cache: "no-store" }));
}

export async function fetchRunState(runId: string) {
  return parseJson<{ state: RunState }>(await fetch(`/api/runs/${encodeURIComponent(runId)}`, { cache: "no-store" }));
}

export async function fetchRunReport(runId: string) {
  const response = await fetch(`/api/runs/${encodeURIComponent(runId)}/report`, { cache: "no-store" });
  if (!response.ok) {
    return "";
  }
  return response.text();
}

export async function startRun(payload: StartRunPayload) {
  return parseJson<{ run: RunSummary }>(
    await fetch("/api/runs/start", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload)
    })
  );
}
```

- [ ] **Step 2: Add page entry point**

Create `web/src/app/page.tsx`:

```tsx
import { Workbench } from "@/components/Workbench";

export default function Home() {
  return <Workbench />;
}
```

- [ ] **Step 3: Run typecheck**

Run:

```bash
cd web && npm run typecheck
```

Expected: FAIL until `Workbench` exists.

- [ ] **Step 4: Commit client boundary after Task 5 adds `Workbench`**

Do not commit this task separately. Include these files in the Task 5 UI commit.

## Task 5: Build The Mantine Workbench UI

**Files:**
- Create: `web/src/components/Workbench.tsx`
- Create: `web/src/components/RunSetup.tsx`
- Create: `web/src/components/RunOverview.tsx`
- Create: `web/src/components/HypothesisLeaderboard.tsx`
- Create: `web/src/components/HypothesisDetail.tsx`
- Create: `web/src/components/RunInsights.tsx`

- [ ] **Step 1: Implement the run setup form**

Create `web/src/components/RunSetup.tsx` with a client component that accepts `onRunCreated(runId)` and `onError(message)`. Use Mantine `Textarea`, `TextInput`, `NumberInput`, and a `Button` with a `Play` icon. Default values: objective `"Find testable ideas that could improve LLM coding agents"`, cycles `1`, max hypotheses `6`, max matches `4`, and run name `ui-demo`.

- [ ] **Step 2: Implement the run overview**

Create `web/src/components/RunOverview.tsx`. Render the selected run objective, safety badge, hypothesis count, review count, match count, updated time, and state/report paths. Use an amber badge or callout for the "Elo is a proxy, not ground truth" warning.

- [ ] **Step 3: Implement the leaderboard**

Create `web/src/components/HypothesisLeaderboard.tsx`. Render a scrollable Mantine table or list of hypotheses sorted by Elo descending. Each row shows rank, title, Elo, origin, status, and metrics. Selecting a row calls `onSelect(hypothesis.id)`.

- [ ] **Step 4: Implement hypothesis detail**

Create `web/src/components/HypothesisDetail.tsx`. Render claim, rationale, assumptions, risks, test plan, review scores, strengths, weaknesses, safety notes, and parent lineage. Resolve parent IDs into titles when possible.

- [ ] **Step 5: Implement insights tabs**

Create `web/src/components/RunInsights.tsx`. Use Mantine `Tabs` for matches, meta-review, and report. The matches tab lists winner and Elo before/after. The meta-review tab shows common weaknesses, safety concerns, missing evidence, promising directions, and prompt feedback. The report tab renders Markdown-like text with readable spacing using `pre-wrap`.

- [ ] **Step 6: Implement the main workbench**

Create `web/src/components/Workbench.tsx`. Use Mantine `AppShell`, a left navbar for `RunSetup` and run selection, and a main grid for `RunOverview`, `HypothesisLeaderboard`, `HypothesisDetail`, and `RunInsights`. On mount, load runs, select the newest readable run, fetch its state and report, and keep refresh/start actions wired to the API helpers.

- [ ] **Step 7: Run typecheck**

Run:

```bash
cd web && npm run typecheck
```

Expected: PASS.

- [ ] **Step 8: Commit the UI**

```bash
git add web/src/app/page.tsx web/src/lib/client.ts web/src/components
git commit -m "feat: build code scientist workbench ui"
```

## Task 6: Build, Run, And Verify

**Files:**
- Modify only if verification exposes a defect.

- [ ] **Step 1: Run Python tests**

Run:

```bash
uv run pytest -q
```

Expected: PASS.

- [ ] **Step 2: Run web typecheck**

Run:

```bash
cd web && npm run typecheck
```

Expected: PASS.

- [ ] **Step 3: Run web build**

Run:

```bash
cd web && npm run build
```

Expected: PASS.

- [ ] **Step 4: Start the dev server**

Run:

```bash
cd web && npm run dev
```

Expected: Next.js serves the UI on a localhost URL.

- [ ] **Step 5: Manually verify the workbench**

Open the local URL and verify:

- Existing `runs/demo-final` appears in the selector.
- The leaderboard renders ranked hypotheses.
- Selecting a hypothesis updates the detail panel.
- Matches, meta-review, and report tabs show real run data.
- Starting a new run creates a directory under `runs/` and selects it.

- [ ] **Step 6: Final status check**

Run:

```bash
git status --short
```

Expected: only intentional generated artifacts remain unstaged, or the tree is clean aside from pre-existing local files.
