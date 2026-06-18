"use client";

import { Badge, Group, Paper, SimpleGrid, Stack, Text, ThemeIcon, Title } from "@mantine/core";
import { Activity, FileText, ShieldCheck, ShieldX, Trophy } from "lucide-react";
import type { RunState, RunSummary } from "@/lib/types";

type RunOverviewProps = {
  summary: RunSummary | null;
  state: RunState;
};

export function RunOverview({ summary, state }: RunOverviewProps) {
  const safetyAllowed = state.safety?.allowed ?? null;

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

      <SimpleGrid cols={{ base: 2, md: 4 }} spacing="sm" mt="md">
        <Metric label="Hypotheses" value={state.hypotheses.length} icon={<Trophy size={16} />} />
        <Metric label="Reviews" value={state.reviews.length} icon={<FileText size={16} />} />
        <Metric label="Matches" value={state.matches.length} icon={<Activity size={16} />} />
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

function Metric({ label, value, icon }: { label: string; value: string | number; icon: React.ReactNode }) {
  return (
    <Paper p="sm" withBorder radius="sm" bg="#fbfcfe">
      <Group gap="xs" wrap="nowrap">
        <ThemeIcon variant="light" color="blue" size="sm">
          {icon}
        </ThemeIcon>
        <Stack gap={0}>
          <Text size="xs" c="dimmed">
            {label}
          </Text>
          <Text fw={700} size="sm">
            {value}
          </Text>
        </Stack>
      </Group>
    </Paper>
  );
}
