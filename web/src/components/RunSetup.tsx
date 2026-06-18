"use client";

import { useMemo, useState } from "react";
import { Alert, Button, Group, NumberInput, Stack, Text, TextInput, Textarea, Tooltip } from "@mantine/core";
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

      <Alert color="yellow" variant="light" icon={<AlertTriangle size={16} />}>
        <Text size="xs">
          Generated hypotheses are candidates. Elo is a proxy auto-evaluation signal, not proof of improvement.
        </Text>
      </Alert>

      <Tooltip label="Start a bounded local research run">
        <Button leftSection={<Play size={16} />} loading={submitting} onClick={submitRun}>
          Start run
        </Button>
      </Tooltip>
    </Stack>
  );
}

function toNumber(value: string | number, fallback: number) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
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
