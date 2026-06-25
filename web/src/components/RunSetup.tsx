"use client";

import { useMemo, useState } from "react";
import { Alert, Button, Group, NumberInput, Select, Stack, Switch, Text, TextInput, Textarea, Tooltip } from "@mantine/core";
import { AlertTriangle, Play } from "lucide-react";
import { startRun } from "@/lib/client";

type RunSetupProps = {
  onRunCreated: (runId: string) => void;
  onError: (message: string) => void;
};

export function RunSetup({ onRunCreated, onError }: RunSetupProps) {
  const [objective, setObjective] = useState("Find testable ideas that could improve LLM coding agents");
  const [cycles, setCycles] = useState(1);
  const [maxHypotheses, setMaxHypotheses] = useState(6);
  const [maxMatches, setMaxMatches] = useState(4);
  const [runName, setRunName] = useState("ui-demo");
  const [provider, setProvider] = useState<"deterministic" | "anthropic">("deterministic");
  const [continuous, setContinuous] = useState(false);
  const [intervalSeconds, setIntervalSeconds] = useState(60);
  const [maxWallMinutes, setMaxWallMinutes] = useState(120);
  const [goalBriefPaths, setGoalBriefPaths] = useState("");
  const [safetyPolicyPaths, setSafetyPolicyPaths] = useState("");
  const [evidencePaths, setEvidencePaths] = useState("");
  const [evidenceIndexPaths, setEvidenceIndexPaths] = useState("");
  const [repoSearchPaths, setRepoSearchPaths] = useState("");
  const [webEvidenceUrls, setWebEvidenceUrls] = useState("");
  const [webCrawlDepth, setWebCrawlDepth] = useState(0);
  const [webSearchQueries, setWebSearchQueries] = useState("");
  const [webSearchFetch, setWebSearchFetch] = useState(false);
  const [webSearchCrawlDepth, setWebSearchCrawlDepth] = useState(0);
  const [literatureSearchQueries, setLiteratureSearchQueries] = useState("");
  const [literatureFullText, setLiteratureFullText] = useState(false);
  const [capabilityEvaluationPaths, setCapabilityEvaluationPaths] = useState("");
  const [preferenceReviewPaths, setPreferenceReviewPaths] = useState("");
  const [prospectiveEvaluationPaths, setProspectiveEvaluationPaths] = useState("");
  const [feedbackLoopEvaluationPaths, setFeedbackLoopEvaluationPaths] = useState("");
  const [feedbackLoopReviewPaths, setFeedbackLoopReviewPaths] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const sanitizedPreview = useMemo(() => previewRunName(runName), [runName]);

  async function submitRun() {
    if (!objective.trim()) {
      onError("Objective is required.");
      return;
    }

    setSubmitting(true);
    try {
      const { run } = await startRun({
        objective,
        cycles,
        maxHypotheses,
        maxMatches,
        provider,
        continuous,
        intervalSeconds,
        maxWallMinutes,
        goalBriefPaths: toPathList(goalBriefPaths),
        safetyPolicyPaths: toPathList(safetyPolicyPaths),
        evidencePaths: toPathList(evidencePaths),
        evidenceIndexPaths: toPathList(evidenceIndexPaths),
        repoSearchPaths: toPathList(repoSearchPaths),
        webEvidenceUrls: toPathList(webEvidenceUrls),
        webCrawlDepth,
        webSearchQueries: toPathList(webSearchQueries),
        webSearchFetch,
        webSearchCrawlDepth,
        literatureSearchQueries: toPathList(literatureSearchQueries),
        literatureFullText,
        capabilityEvaluationPaths: toPathList(capabilityEvaluationPaths),
        preferenceReviewPaths: toPathList(preferenceReviewPaths),
        prospectiveEvaluationPaths: toPathList(prospectiveEvaluationPaths),
        feedbackLoopEvaluationPaths: toPathList(feedbackLoopEvaluationPaths),
        feedbackLoopReviewPaths: toPathList(feedbackLoopReviewPaths),
        runName
      });
      onRunCreated(run.id);
    } catch (error) {
      onError(error instanceof Error ? error.message : "Unable to start run.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Stack gap="sm">
      <Stack gap={4}>
        <Text fw={700} size="sm">
          New research run
        </Text>
        <Text size="xs" c="dimmed">
          Runs execute locally through the existing `uv` CLI and write to `runs/`.
        </Text>
      </Stack>

      <Textarea
        label="Objective"
        autosize
        minRows={4}
        maxRows={8}
        value={objective}
        onChange={(event) => setObjective(event.currentTarget.value)}
      />

      <TextInput
        label="Run name"
        value={runName}
        onChange={(event) => setRunName(event.currentTarget.value)}
        description={`Output: runs/${sanitizedPreview}`}
      />

      <Select
        label="Provider"
        value={provider}
        onChange={(value) => setProvider(value === "anthropic" ? "anthropic" : "deterministic")}
        data={[
          { value: "deterministic", label: "Deterministic" },
          { value: "anthropic", label: "Anthropic" }
        ]}
      />

      <Group grow align="flex-start">
        <NumberInput
          label="Cycles"
          min={1}
          max={5}
          value={cycles}
          onChange={(value) => setCycles(toNumber(value, 1))}
        />
        <NumberInput
          label="Matches"
          min={0}
          max={40}
          value={maxMatches}
          onChange={(value) => setMaxMatches(toNumber(value, 4))}
        />
      </Group>

      <NumberInput
        label="Max hypotheses"
        min={2}
        max={20}
        value={maxHypotheses}
        onChange={(value) => setMaxHypotheses(toNumber(value, 6))}
      />

      <Textarea
        label="Goal brief paths"
        autosize
        minRows={2}
        maxRows={5}
        value={goalBriefPaths}
        onChange={(event) => setGoalBriefPaths(event.currentTarget.value)}
      />

      <Textarea
        label="Safety policy paths"
        autosize
        minRows={2}
        maxRows={5}
        value={safetyPolicyPaths}
        onChange={(event) => setSafetyPolicyPaths(event.currentTarget.value)}
      />

      <Textarea
        label="Evidence paths"
        autosize
        minRows={2}
        maxRows={5}
        value={evidencePaths}
        onChange={(event) => setEvidencePaths(event.currentTarget.value)}
      />

      <Textarea
        label="Evidence index paths"
        autosize
        minRows={2}
        maxRows={5}
        value={evidenceIndexPaths}
        onChange={(event) => setEvidenceIndexPaths(event.currentTarget.value)}
      />

      <Textarea
        label="Repository search paths"
        autosize
        minRows={2}
        maxRows={5}
        value={repoSearchPaths}
        onChange={(event) => setRepoSearchPaths(event.currentTarget.value)}
      />

      <Textarea
        label="Web evidence URLs"
        autosize
        minRows={2}
        maxRows={5}
        value={webEvidenceUrls}
        onChange={(event) => setWebEvidenceUrls(event.currentTarget.value)}
      />

      <NumberInput
        label="Web crawl depth"
        min={0}
        max={2}
        value={webCrawlDepth}
        onChange={(value) => setWebCrawlDepth(toNumber(value, 0))}
      />

      <Textarea
        label="Web search queries"
        autosize
        minRows={2}
        maxRows={5}
        value={webSearchQueries}
        onChange={(event) => setWebSearchQueries(event.currentTarget.value)}
      />

      <Switch
        label="Fetch web search result pages"
        checked={webSearchFetch}
        onChange={(event) => setWebSearchFetch(event.currentTarget.checked)}
      />

      <NumberInput
        label="Web search crawl depth"
        min={0}
        max={2}
        value={webSearchCrawlDepth}
        onChange={(value) => setWebSearchCrawlDepth(toNumber(value, 0))}
      />

      <Textarea
        label="Literature search queries"
        autosize
        minRows={2}
        maxRows={5}
        value={literatureSearchQueries}
        onChange={(event) => setLiteratureSearchQueries(event.currentTarget.value)}
      />

      <Switch
        label="Fetch literature full text"
        checked={literatureFullText}
        onChange={(event) => setLiteratureFullText(event.currentTarget.checked)}
      />

      <Textarea
        label="Capability evaluation fixtures"
        autosize
        minRows={2}
        maxRows={5}
        value={capabilityEvaluationPaths}
        onChange={(event) => setCapabilityEvaluationPaths(event.currentTarget.value)}
      />

      <Textarea
        label="Preference-review fixtures"
        autosize
        minRows={2}
        maxRows={5}
        value={preferenceReviewPaths}
        onChange={(event) => setPreferenceReviewPaths(event.currentTarget.value)}
      />

      <Textarea
        label="Prospective evaluation fixtures"
        autosize
        minRows={2}
        maxRows={5}
        value={prospectiveEvaluationPaths}
        onChange={(event) => setProspectiveEvaluationPaths(event.currentTarget.value)}
      />

      <Textarea
        label="Feedback-loop evaluation fixtures"
        autosize
        minRows={2}
        maxRows={5}
        value={feedbackLoopEvaluationPaths}
        onChange={(event) => setFeedbackLoopEvaluationPaths(event.currentTarget.value)}
      />

      <Textarea
        label="Feedback-loop blind review fixtures"
        autosize
        minRows={2}
        maxRows={5}
        value={feedbackLoopReviewPaths}
        onChange={(event) => setFeedbackLoopReviewPaths(event.currentTarget.value)}
      />

      <Switch
        label="Continuous"
        checked={continuous}
        onChange={(event) => setContinuous(event.currentTarget.checked)}
      />

      {continuous ? (
        <Group grow align="flex-start">
          <NumberInput
            label="Interval seconds"
            min={1}
            max={3600}
            value={intervalSeconds}
            onChange={(value) => setIntervalSeconds(toNumber(value, 60))}
          />
          <NumberInput
            label="Max wall minutes"
            min={1}
            max={1440}
            value={maxWallMinutes}
            onChange={(value) => setMaxWallMinutes(toNumber(value, 120))}
          />
        </Group>
      ) : null}

      <Alert color="yellow" variant="light" icon={<AlertTriangle size={16} />}>
        <Text size="xs">
          Generated hypotheses are candidates. Elo is a proxy auto-evaluation signal, not proof of improvement.
        </Text>
      </Alert>

      <Tooltip label="Start a bounded local research run">
        <Button leftSection={<Play size={16} />} loading={submitting} onClick={submitRun}>
          {continuous ? "Start continuous run" : "Start run"}
        </Button>
      </Tooltip>
    </Stack>
  );
}

function toNumber(value: string | number, fallback: number) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function toPathList(value: string) {
  return value
    .split(/[\n,]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function previewRunName(value: string) {
  return (
    value
      .trim()
      .toLowerCase()
      .replace(/[/\\]+/g, " ")
      .replace(/^\.+/, "")
      .replace(/[^a-z0-9._-]+/g, "-")
      .replace(/^-+|-+$/g, "")
      .slice(0, 80) || "ui-run"
  );
}
