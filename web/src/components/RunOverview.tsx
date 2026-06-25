"use client";

import { Badge, Group, Paper, SimpleGrid, Stack, Text, ThemeIcon, Title } from "@mantine/core";
import { Activity, FileText, ListChecks, ShieldCheck, ShieldX, Trophy } from "lucide-react";
import type { RunState, RunSummary, Task } from "@/lib/types";

type RunOverviewProps = {
  summary: RunSummary | null;
  state: RunState;
};

export function RunOverview({ summary, state }: RunOverviewProps) {
  const safetyAllowed = state.safety?.allowed ?? null;
  const runStatus = state.run_status ?? summary?.runStatus ?? "completed";
  const taskStatusSummary = formatTaskStatusCounts(state.task_queue ?? []);

  return (
    <Paper p="md" withBorder radius="sm">
      <Group align="flex-start" justify="space-between" gap="md">
        <Stack gap={6} maw={920}>
          <Group gap="xs">
            <ThemeIcon color="blue" variant="light" size="sm">
              <Trophy size={15} />
            </ThemeIcon>
            <Text size="xs" c="dimmed" tt="uppercase" fw={700}>
              Selected run
            </Text>
          </Group>
          <Title order={1}>{state.goal.objective}</Title>
          <Text size="sm" c="dimmed">
            Local deterministic research output. Hypotheses are ranked candidates and must be validated with
            benchmark evidence before any improvement claim.
          </Text>
        </Stack>
        <Badge
          color={safetyAllowed === false ? "red" : safetyAllowed === true ? "green" : "gray"}
          leftSection={safetyAllowed === false ? <ShieldX size={13} /> : <ShieldCheck size={13} />}
          variant="light"
        >
          {safetyAllowed === false ? "Blocked" : safetyAllowed === true ? "Allowed" : "No safety record"}
        </Badge>
      </Group>

      <SimpleGrid cols={{ base: 2, md: 6 }} spacing="sm" mt="md">
        <Metric label="Status" value={runStatus} icon={<Activity size={16} />} />
        <Metric label="Hypotheses" value={state.hypotheses.length} icon={<Trophy size={16} />} />
        <Metric label="Reviews" value={state.reviews.length} icon={<FileText size={16} />} />
        <Metric label="Matches" value={state.matches.length} icon={<Activity size={16} />} />
        <Metric label="Tasks" value={taskStatusSummary} icon={<ListChecks size={16} />} />
        <Metric
          label="Updated"
          value={summary ? new Date(summary.updatedAt).toLocaleString() : "Loaded"}
          icon={<FileText size={16} />}
        />
      </SimpleGrid>

      {state.safety ? (
        <Text size="xs" c="dimmed" mt="sm">
          Safety: {state.safety.reason}
        </Text>
      ) : null}
    </Paper>
  );
}

const TASK_STATUS_ORDER = ["queued", "running", "completed", "failed", "deferred"];

function formatTaskStatusCounts(tasks: Task[]) {
  if (!tasks.length) {
    return "0";
  }
  const counts = tasks.reduce<Record<string, number>>((acc, task) => {
    acc[task.status] = (acc[task.status] ?? 0) + 1;
    return acc;
  }, {});
  const unknownStatuses = Object.keys(counts)
    .filter((status) => !TASK_STATUS_ORDER.includes(status))
    .sort();
  return [...TASK_STATUS_ORDER, ...unknownStatuses]
    .filter((status) => counts[status])
    .map((status) => `${status}=${counts[status]}`)
    .join(" ");
}

function Metric({ label, value, icon }: { label: string; value: string | number; icon: React.ReactNode }) {
  return (
    <Paper p="sm" withBorder radius="sm" bg="#fbfcfe">
      <Group gap="xs" wrap="nowrap" align="flex-start">
        <ThemeIcon variant="light" color="blue" size="sm">
          {icon}
        </ThemeIcon>
        <Stack gap={0} style={{ minWidth: 0 }}>
          <Text size="xs" c="dimmed">
            {label}
          </Text>
          <Text fw={700} size="sm" style={{ overflowWrap: "anywhere" }}>
            {value}
          </Text>
        </Stack>
      </Group>
    </Paper>
  );
}
