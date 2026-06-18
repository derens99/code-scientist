# Code Scientist UI Design

## Purpose

Build a polished local web workbench for Code Scientist using Next.js and Mantine. The UI should make the existing deterministic research engine feel like an interactive product: users can start bounded research runs, inspect active or completed run outputs, compare ranked hypotheses, read reviews and lineage, and open the generated report.

The first version should stay local, auditable, and aligned with the current Python MVP. It should not introduce external LLM calls, remote deployment assumptions, or claims of measured improvement beyond the persisted run evidence.

## Current Project Context

The repository is currently a Python package with:

- `uv`-managed project metadata in `pyproject.toml`.
- CLI entry points in `src/code_scientist/cli.py`.
- Run orchestration in `src/code_scientist/supervisor.py`.
- Structured run state in `src/code_scientist/models.py`.
- Markdown report rendering in `src/code_scientist/reporting.py`.
- Example persisted runs under `runs/demo` and `runs/demo-final`.

There is no existing web scaffold. The UI can therefore be added as a new app without disrupting the Python package.

## Considered Approaches

### Recommended: Next.js Workbench With Local Route Handlers

Create a `web/` Next.js app with Mantine and TypeScript. Next.js route handlers provide local API endpoints for listing runs, reading run state, reading reports, and starting new runs by spawning the existing `uv run code-scientist run ...` CLI.

Trade-offs:

- Pros: one local web server, simple setup, no separate Python web backend, uses the real CLI path, easy to verify against existing `runs/*/state.json`.
- Cons: job progress is initially coarse because the current Python supervisor writes final state at completion rather than streaming per-step events.

This is the recommended approach because it turns the MVP into a real local tool while keeping the backend surface small and faithful to existing code.

### Alternative: Static Report Viewer First

Create a Mantine viewer that only reads existing `runs/*/state.json` and `report.md` files.

Trade-offs:

- Pros: smaller first cut, lower process-management risk.
- Cons: does not satisfy the workbench goal because users still need the CLI to create useful data.

### Alternative: Separate Python API Server

Add FastAPI or another Python web API that wraps `run_research_cycle`, then point Next.js at that API.

Trade-offs:

- Pros: Python-native API boundary and future streaming support.
- Cons: adds another server, dependency group, and operational surface before the product needs it.

This should be deferred until the research engine needs long-running streaming events, cancellation, or multi-user concerns.

## Product Shape

The UI is a workbench, not a landing page. The first screen should be the actual tool:

- A left setup rail for starting a new run.
- A main results area for the selected run.
- A right or lower detail area for report, reviews, lineage, and safety status.
- A run selector that can load existing runs from `runs/`.

The design should feel like a focused research operations console: dense, readable, calm, and fast to scan. It should avoid marketing-page composition, oversized hero content, decorative cards, and single-hue theming.

## Core Views

### Run Setup

Controls:

- Objective text area.
- Cycles number input.
- Max hypotheses number input.
- Max matches number input.
- Output run name input with a generated default.
- Start button with loading state.

Behavior:

- Validate that the objective is non-empty.
- Clamp numeric values to conservative local bounds.
- Disable duplicate submission while a run is starting.
- After successful run creation, select the new run and refresh the run list.

### Run Browser

Controls and content:

- Select existing run by directory name.
- Show objective, safety decision, counts for hypotheses/reviews/matches/meta-reviews.
- Show report availability and state path.
- Refresh button.

Behavior:

- Load `runs/*/state.json` and optional `report.md`.
- Sort runs by modified time descending.
- Preserve selection when refreshing if the run still exists.

### Leaderboard

Content:

- Ranked hypotheses with title, Elo, status, origin, and parent count.
- Compact visual Elo indicator.
- Claim and test-plan summary.
- Metrics as small tags.

Behavior:

- Selecting a hypothesis opens its detail panel.
- The top-ranked item is selected by default.
- Elo must be labeled as a proxy auto-evaluation signal.

### Hypothesis Detail

Content:

- Claim, rationale, assumptions, evidence refs, test plan, risks.
- Review decision, criteria scores, strengths, weaknesses, and safety notes when available.
- Parent lineage if the item was evolved from earlier hypotheses.

Behavior:

- Missing sections are shown as empty states rather than breaking layout.
- Parent IDs are cross-linked when the parent exists in the loaded run state.

### Tournament And Meta-Review

Content:

- Match list with hypothesis A, hypothesis B, winner, rationale, and Elo before/after.
- Meta-review common weaknesses, safety concerns, missing evidence themes, promising directions, and prompt feedback.

Behavior:

- Keep this information scannable in tabs or segmented sections so it does not crowd the leaderboard.

### Report

Content:

- Render the generated `report.md` as formatted Markdown or a readable plaintext fallback.
- Include a direct copy/download action only if it is locally available.

Behavior:

- The report should stay visibly separate from generated claims by repeating the limitation that hypotheses are candidates and Elo is not ground truth.

## Architecture

### File Layout

Add a new `web/` app:

```text
web/
  package.json
  next.config.ts
  tsconfig.json
  src/app/layout.tsx
  src/app/page.tsx
  src/app/api/runs/route.ts
  src/app/api/runs/[runId]/route.ts
  src/app/api/runs/[runId]/report/route.ts
  src/app/api/runs/start/route.ts
  src/components/
  src/lib/
  src/styles/
```

### API Boundary

The Next.js route handlers should expose:

- `GET /api/runs`: list runs with metadata.
- `GET /api/runs/:runId`: return parsed `state.json`.
- `GET /api/runs/:runId/report`: return `report.md` when present.
- `POST /api/runs/start`: validate input, create a safe output directory under `runs/`, invoke `uv run code-scientist run ...`, and return the new run metadata.

The route handlers should treat the repository root as the project root. Because the Next.js process runs from `web/`, resolve the repo root with `path.resolve(process.cwd(), "..")`, with an override via `CODE_SCIENTIST_ROOT` for tests or unusual launches.

### Process Boundary

The first version can run jobs synchronously through the API request because the deterministic MVP is short-running. The UI should still show an in-progress state and avoid implying streaming progress.

The implementation should use Node's child process APIs with argument arrays, not shell-string concatenation. Run names must be sanitized to prevent path traversal and unsafe output locations.

### Data Types

Define TypeScript types that mirror `RunState`, `ResearchGoal`, `Hypothesis`, `Review`, `Match`, `MetaReview`, `SafetyDecision`, and `TestPlan`. Keep them close to the Python model names so future schema changes are easy to track.

## UI Design System

Use Mantine for the component system and layout primitives:

- `AppShell` for the workbench frame.
- `Tabs` for leaderboard, matches, meta-review, and report sections.
- `Table`, `ScrollArea`, `Badge`, `Progress`, `SegmentedControl`, `NumberInput`, `Textarea`, `Button`, `ActionIcon`, and `Tooltip` for controls.
- Lucide icons for refresh, run, report, warning, leaderboard, and copy/download actions.

Visual direction:

- Light default theme with restrained contrast.
- Use several functional colors: green for allowed safety, red for blocked safety, blue for selected state, amber for proxy/evidence warnings, and neutral grays for structure.
- Avoid a one-note purple/blue gradient look.
- Keep cards only for repeated entities or detail panes; do not nest cards inside cards.
- Use stable heights, grid tracks, and scroll regions so lists and details do not jump as content changes.

## Error Handling

Handle these cases explicitly:

- No runs exist: show an empty workbench state with the run form ready.
- State JSON is missing or invalid: show the affected run as unreadable and continue listing other runs.
- Report is missing: show a report-empty state.
- CLI run fails: show stderr or a concise failure message in the run setup area.
- Unsafe or empty run names: sanitize automatically and show the resolved output name.
- Safety decision is blocked: show the state and do not present blocked output as normal research success.

## Testing And Verification

Add web-level verification:

- Type check with `npm run typecheck`.
- Lint with `npm run lint` if configured by the scaffold.
- Build with `npm run build`.
- Add focused tests for run-name sanitization and API data shaping if the app test stack is added.

End-to-end manual verification:

- Start the app with `npm run dev`.
- Load existing `runs/demo-final`.
- Start a new run from the UI.
- Confirm the new run appears in the selector.
- Confirm leaderboard, details, matches/meta-review, and report render from real persisted files.

Keep Python verification intact:

- Run `uv run pytest -q` after changes that touch Python code.
- Do not introduce Python package dependency management outside `uv`.

## Out Of Scope For This UI Pass

- Real-time per-agent streaming.
- Cancellation and background job queues.
- Multi-user auth.
- Remote deployment.
- Editing or applying generated hypotheses as source-code patches.
- External model/search adapters.

## Open Decisions Resolved For Implementation

- Build the UI as a `web/` Next.js app.
- Use Mantine as the component library.
- Use local Next.js route handlers as the first API boundary.
- Support both starting new runs and viewing existing `runs/*` outputs.
- Keep the UI honest about safety and evidence limits.
