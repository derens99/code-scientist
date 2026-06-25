"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ActionIcon,
  Alert,
  AppShell,
  Badge,
  Box,
  Button,
  Divider,
  Group,
  LoadingOverlay,
  Paper,
  ScrollArea,
  Select,
  Stack,
  Text,
  ThemeIcon,
  Title,
  Tooltip
} from "@mantine/core";
import { useMediaQuery } from "@mantine/hooks";
import { AlertTriangle, Database, FlaskConical, PauseCircle, PlayCircle, RefreshCw, Square } from "lucide-react";
import {
  controlRun,
  fetchRunReport,
  fetchRuns,
  fetchRunState,
  submitManualHypothesis,
  submitManualReview,
  submitProximityClusterOverride,
  submitProximityOverride,
  submitRunCommand,
  submitRunGuidance,
  submitUserFeedback
} from "@/lib/client";
import type {
  ManualHypothesisPayload,
  ManualReviewPayload,
  RunCommandPayload,
  RunGuidancePayload,
  UserFeedbackPayload
} from "@/lib/client";
import type { Hypothesis, ProximityEdge, RunState, RunSummary } from "@/lib/types";
import { HumanInputPanel } from "./HumanInputPanel";
import { HypothesisDetail } from "./HypothesisDetail";
import { HypothesisLeaderboard } from "./HypothesisLeaderboard";
import { RunInsights } from "./RunInsights";
import { RunOverview } from "./RunOverview";
import { RunSetup } from "./RunSetup";

export function Workbench() {
  const wideLayout = useMediaQuery("(min-width: 1120px)");
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [state, setState] = useState<RunState | null>(null);
  const [report, setReport] = useState("");
  const [selectedHypothesisId, setSelectedHypothesisId] = useState<string | null>(null);
  const [loadingRuns, setLoadingRuns] = useState(true);
  const [loadingState, setLoadingState] = useState(false);
  const [controlling, setControlling] = useState(false);
  const [submittingHumanInput, setSubmittingHumanInput] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const selectedSummary = useMemo(
    () => runs.find((run) => run.id === selectedRunId) ?? null,
    [runs, selectedRunId]
  );

  const selectedHypothesis = useMemo(() => {
    if (!state) {
      return null;
    }
    const ranked = [...state.hypotheses].sort((left, right) => right.elo - left.elo);
    return ranked.find((hypothesis) => hypothesis.id === selectedHypothesisId) ?? ranked[0] ?? null;
  }, [selectedHypothesisId, state]);

  const selectedReview = useMemo(() => {
    if (!selectedHypothesis || !state) {
      return null;
    }
    return state.reviews.find((review) => review.hypothesis_id === selectedHypothesis.id) ?? null;
  }, [selectedHypothesis, state]);

  const parentHypotheses = useMemo(() => {
    if (!selectedHypothesis || !state) {
      return [];
    }
    return selectedHypothesis.parent_ids
      .map((id) => state.hypotheses.find((hypothesis) => hypothesis.id === id))
      .filter((hypothesis): hypothesis is Hypothesis => Boolean(hypothesis));
  }, [selectedHypothesis, state]);

  const runStatus = state?.run_status ?? selectedSummary?.runStatus ?? "completed";

  const runOptions = useMemo(
    () =>
      runs.map((run) => ({
        value: run.id,
        label: `${run.id}${run.readable ? "" : " (unreadable)"}`,
        disabled: !run.readable
      })),
    [runs]
  );

  const loadRuns = useCallback(async (preferredRunId?: string) => {
    setLoadingRuns(true);
    setError(null);
    try {
      const payload = await fetchRuns();
      setRuns(payload.runs);
      const nextSelection =
        preferredRunId ??
        selectedRunId ??
        payload.runs.find((run) => run.readable)?.id ??
        null;
      setSelectedRunId(nextSelection);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Unable to load runs.");
    } finally {
      setLoadingRuns(false);
    }
  }, [selectedRunId]);

  const loadRunState = useCallback(async (runId: string) => {
    setLoadingState(true);
    setError(null);
    try {
      const [statePayload, reportText] = await Promise.all([fetchRunState(runId), fetchRunReport(runId)]);
      setState(statePayload.state);
      setReport(reportText);
      const topHypothesis = [...statePayload.state.hypotheses].sort((left, right) => right.elo - left.elo)[0];
      setSelectedHypothesisId(topHypothesis?.id ?? null);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Unable to load run state.");
      setState(null);
      setReport("");
      setSelectedHypothesisId(null);
    } finally {
      setLoadingState(false);
    }
  }, []);

  useEffect(() => {
    void loadRuns();
  }, [loadRuns]);

  useEffect(() => {
    if (selectedRunId) {
      void loadRunState(selectedRunId);
    }
  }, [loadRunState, selectedRunId]);

  useEffect(() => {
    if (!selectedRunId || (runStatus !== "running" && runStatus !== "paused")) {
      return undefined;
    }
    const timer = window.setInterval(() => {
      void loadRunState(selectedRunId);
      void loadRuns(selectedRunId);
    }, 5000);
    return () => window.clearInterval(timer);
  }, [loadRunState, loadRuns, runStatus, selectedRunId]);

  async function handleRunCreated(runId: string) {
    await loadRuns(runId);
    setSelectedRunId(runId);
  }

  async function handleControl(action: "pause" | "resume" | "stop") {
    if (!selectedRunId) {
      return;
    }
    setControlling(true);
    setError(null);
    try {
      await controlRun(selectedRunId, action);
      await loadRunState(selectedRunId);
      await loadRuns(selectedRunId);
    } catch (controlError) {
      setError(controlError instanceof Error ? controlError.message : "Unable to control run.");
    } finally {
      setControlling(false);
    }
  }

  async function saveHumanInput(
    action: () => Promise<{ state: RunState }>,
    selectHypothesis?: (state: RunState) => string | null
  ) {
    if (!selectedRunId) {
      return;
    }
    setSubmittingHumanInput(true);
    setError(null);
    try {
      const payload = await action();
      setState(payload.state);
      const nextSelected = selectHypothesis?.(payload.state) ?? selectedHypothesisId;
      if (nextSelected) {
        setSelectedHypothesisId(nextSelected);
      }
      await loadRuns(selectedRunId);
    } catch (inputError) {
      setError(inputError instanceof Error ? inputError.message : "Unable to save human input.");
    } finally {
      setSubmittingHumanInput(false);
    }
  }

  async function handleFeedback(payload: UserFeedbackPayload) {
    if (!selectedRunId) {
      return;
    }
    await saveHumanInput(() => submitUserFeedback(selectedRunId, payload));
  }

  async function handleManualHypothesis(payload: ManualHypothesisPayload) {
    if (!selectedRunId) {
      return;
    }
    const existingIds = new Set(state?.hypotheses.map((hypothesis) => hypothesis.id) ?? []);
    await saveHumanInput(
      () => submitManualHypothesis(selectedRunId, payload),
      (updated) => updated.hypotheses.find((hypothesis) => !existingIds.has(hypothesis.id))?.id ?? null
    );
  }

  async function handleManualReview(payload: ManualReviewPayload) {
    if (!selectedRunId) {
      return;
    }
    await saveHumanInput(() => submitManualReview(selectedRunId, payload));
  }

  async function handleGuidance(payload: RunGuidancePayload) {
    if (!selectedRunId) {
      return;
    }
    await saveHumanInput(() => submitRunGuidance(selectedRunId, payload));
  }

  async function handleCommand(payload: RunCommandPayload) {
    if (!selectedRunId) {
      return;
    }
    await saveHumanInput(() => submitRunCommand(selectedRunId, payload));
  }

  async function handleProximityOverride(edge: ProximityEdge, decision: "merge" | "preserve") {
    if (!selectedRunId) {
      return;
    }
    await saveHumanInput(() =>
      submitProximityOverride(selectedRunId, {
        source: edge.source,
        target: edge.target,
        decision,
        clusterId: edge.cluster_id ?? `manual-${edge.source}-${edge.target}`,
        reason:
          decision === "merge"
            ? "Scientist marked this edge for merge/deduplication."
            : "Scientist preserved this edge as a diversity candidate."
      })
    );
  }

  async function handleProximityClusterOverride(clusterId: string, decision: "merge" | "preserve") {
    if (!selectedRunId) {
      return;
    }
    await saveHumanInput(() =>
      submitProximityClusterOverride(selectedRunId, {
        clusterId,
        decision,
        reason:
          decision === "merge"
            ? "Scientist marked this cluster for merge/deduplication."
            : "Scientist preserved this cluster as a diversity candidate."
      })
    );
  }

  async function handleProximityClusterAssignment(edge: ProximityEdge, clusterId: string) {
    if (!selectedRunId || !clusterId.trim()) {
      return;
    }
    await saveHumanInput(() =>
      submitRunCommand(selectedRunId, {
        command: `cluster ${edge.source} ${edge.target} as ${clusterId.trim()}`
      })
    );
  }

  return (
    <AppShell
      header={{ height: 64 }}
      navbar={{ width: 380, breakpoint: "md" }}
      padding="md"
      styles={{
        main: { background: "#f5f7fb" },
        navbar: { background: "#ffffff" },
        header: { background: "#ffffff" }
      }}
    >
      <AppShell.Header>
        <Group h="100%" px="md" justify="space-between" wrap="nowrap">
          <Group gap="sm" wrap="nowrap">
            <ThemeIcon color="blue" variant="light" size="lg">
              <FlaskConical size={20} />
            </ThemeIcon>
            <Box>
              <Title order={1}>Code Scientist Workbench</Title>
              <Text size="xs" c="dimmed">
                Local research runs, ranked hypotheses, reviews, lineage, and reports.
              </Text>
            </Box>
          </Group>
          <Group gap="xs" wrap="nowrap">
            <Badge color="gray" variant="outline">
              Local only
            </Badge>
            <Tooltip label="Refresh runs">
              <ActionIcon variant="light" onClick={() => void loadRuns()} loading={loadingRuns}>
                <RefreshCw size={16} />
              </ActionIcon>
            </Tooltip>
          </Group>
        </Group>
      </AppShell.Header>

      <AppShell.Navbar p="md">
        <ScrollArea offsetScrollbars>
          <Stack gap="md">
            <RunSetup onRunCreated={handleRunCreated} onError={setError} />
            <Divider />
            <Stack gap="xs">
              <Group gap="xs">
                <Database size={16} />
                <Text fw={700} size="sm">
                  Existing runs
                </Text>
              </Group>
              <Select
                value={selectedRunId}
                onChange={setSelectedRunId}
                data={runOptions}
                placeholder={loadingRuns ? "Loading runs..." : "Select a run"}
                searchable
                nothingFoundMessage="No runs found"
              />
              <Button
                variant="light"
                leftSection={<RefreshCw size={16} />}
                loading={loadingRuns}
                onClick={() => void loadRuns()}
              >
                Refresh list
              </Button>
              {selectedSummary ? (
                <Paper p="sm" withBorder radius="sm" bg="#fbfcfe">
                  <Text size="xs" c="dimmed">
                    State
                  </Text>
                  <Text size="xs" lineClamp={2}>
                    {selectedSummary.statePath}
                  </Text>
                  <Text size="xs" c="dimmed" mt={6}>
                    Report
                  </Text>
                  <Text size="xs" lineClamp={2}>
                    {selectedSummary.reportPath ?? "No report.md"}
                  </Text>
                </Paper>
              ) : null}
            </Stack>
          </Stack>
        </ScrollArea>
      </AppShell.Navbar>

      <AppShell.Main>
        <Box pos="relative" mih="calc(100vh - 96px)">
          <LoadingOverlay visible={loadingState} zIndex={1000} overlayProps={{ blur: 1 }} />
          {error ? (
            <Alert mb="md" color="red" variant="light" icon={<AlertTriangle size={16} />} withCloseButton onClose={() => setError(null)}>
              {error}
            </Alert>
          ) : null}

          {state ? (
            <Stack gap="md">
              <RunOverview summary={selectedSummary} state={state} />
              <RunControls status={runStatus} loading={controlling} onControl={handleControl} />
              <Box
                style={{
                  display: "grid",
                  gridTemplateColumns: wideLayout
                    ? "minmax(320px, 0.95fr) minmax(360px, 1.05fr)"
                    : "minmax(0, 1fr)",
                  gap: "var(--mantine-spacing-md)",
                  alignItems: "start"
                }}
              >
                <HypothesisLeaderboard
                  hypotheses={state.hypotheses}
                  selectedId={selectedHypothesis?.id ?? null}
                  onSelect={setSelectedHypothesisId}
                />
                <Stack gap="md">
                  <HypothesisDetail hypothesis={selectedHypothesis} review={selectedReview} parents={parentHypotheses} />
                  <HumanInputPanel
                    selectedHypothesis={selectedHypothesis}
                    submitting={submittingHumanInput}
                    goalPreferences={state.goal.preferences}
                    goalConstraints={state.goal.constraints}
                    allowedSources={state.plan?.allowed_sources ?? []}
                    onFeedback={handleFeedback}
                    onManualHypothesis={handleManualHypothesis}
                    onManualReview={handleManualReview}
                    onVerificationMark={handleFeedback}
                    onGuidance={handleGuidance}
                    onCommand={handleCommand}
                  />
                </Stack>
              </Box>
              <RunInsights
                matches={state.matches}
                metaReviews={state.meta_reviews}
                hypotheses={state.hypotheses}
                plan={state.plan}
                proximityEdges={state.proximity_edges}
                contextSnapshots={state.context_snapshots}
                benchmarkResults={state.benchmark_results}
                capabilityEvaluations={state.capability_evaluations}
                prospectiveEvaluations={state.prospective_evaluations}
                scalingCurve={state.scaling_curve}
                safetyEvaluations={state.safety_evaluations}
                feedbackLoopEvaluations={state.feedback_loop_evaluations}
                researchOutputArtifacts={state.research_output_artifacts}
                researchOverview={state.research_overview}
                agentTraces={state.agent_traces}
                retrievalMemory={state.retrieval_memory}
                userFeedback={state.user_feedback}
                onProximityOverride={handleProximityOverride}
                onProximityClusterOverride={handleProximityClusterOverride}
                onProximityClusterAssignment={handleProximityClusterAssignment}
                proximityOverrideLoading={submittingHumanInput}
                report={report}
              />
            </Stack>
          ) : (
            <EmptyWorkbench loading={loadingRuns || loadingState} />
          )}
        </Box>
      </AppShell.Main>
    </AppShell>
  );
}

function RunControls({
  status,
  loading,
  onControl
}: {
  status: string;
  loading: boolean;
  onControl: (action: "pause" | "resume" | "stop") => void;
}) {
  const active = status === "running" || status === "paused";
  return (
    <Paper p="sm" withBorder radius="sm">
      <Group gap="xs" justify="space-between">
        <Group gap="xs">
          <Badge color={status === "running" ? "green" : status === "paused" ? "yellow" : "gray"} variant="light">
            {status}
          </Badge>
        </Group>
        <Group gap="xs">
          <Button
            size="xs"
            variant="light"
            leftSection={<PauseCircle size={14} />}
            disabled={status !== "running"}
            loading={loading && status === "running"}
            onClick={() => onControl("pause")}
          >
            Pause
          </Button>
          <Button
            size="xs"
            variant="light"
            leftSection={<PlayCircle size={14} />}
            disabled={status !== "paused"}
            loading={loading && status === "paused"}
            onClick={() => onControl("resume")}
          >
            Resume
          </Button>
          <Button
            size="xs"
            color="red"
            variant="light"
            leftSection={<Square size={14} />}
            disabled={!active}
            loading={loading && active}
            onClick={() => onControl("stop")}
          >
            Stop
          </Button>
        </Group>
      </Group>
    </Paper>
  );
}

function EmptyWorkbench({ loading }: { loading: boolean }) {
  return (
    <Paper p="xl" withBorder radius="sm">
      <Stack gap="xs" align="flex-start">
        <ThemeIcon color="blue" variant="light" size="lg">
          <FlaskConical size={20} />
        </ThemeIcon>
        <Title order={2}>{loading ? "Loading runs" : "No readable run selected"}</Title>
        <Text c="dimmed" size="sm" maw={620}>
          Start a new local research run from the left rail or select an existing run from `runs/`.
        </Text>
      </Stack>
    </Paper>
  );
}
