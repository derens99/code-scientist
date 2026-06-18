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
import { AlertTriangle, Database, FlaskConical, RefreshCw } from "lucide-react";
import { fetchRunReport, fetchRuns, fetchRunState } from "@/lib/client";
import type { Hypothesis, RunState, RunSummary } from "@/lib/types";
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

  async function handleRunCreated(runId: string) {
    await loadRuns(runId);
    setSelectedRunId(runId);
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
                <HypothesisDetail hypothesis={selectedHypothesis} review={selectedReview} parents={parentHypotheses} />
              </Box>
              <RunInsights
                matches={state.matches}
                metaReviews={state.meta_reviews}
                hypotheses={state.hypotheses}
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
