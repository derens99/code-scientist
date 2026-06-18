"use client";

import { Badge, Divider, Group, List, Paper, SimpleGrid, Stack, Text, Title } from "@mantine/core";
import { GitBranch, ListChecks } from "lucide-react";
import type { Hypothesis, Review } from "@/lib/types";

type HypothesisDetailProps = {
  hypothesis: Hypothesis | null;
  review: Review | null;
  parents: Hypothesis[];
};

export function HypothesisDetail({ hypothesis, review, parents }: HypothesisDetailProps) {
  if (!hypothesis) {
    return (
      <Paper p="md" withBorder radius="sm" h="100%">
        <Title order={2}>Hypothesis detail</Title>
        <Text c="dimmed" size="sm" mt="sm">
          Select a hypothesis to inspect its assumptions, risks, review, and lineage.
        </Text>
      </Paper>
    );
  }

  return (
    <Paper p="md" withBorder radius="sm" h="100%">
      <Stack gap="md">
        <Group justify="space-between" align="flex-start">
          <Stack gap={4}>
            <Title order={2}>{hypothesis.title}</Title>
            <Group gap={6}>
              <Badge color="blue" variant="light">
                Elo {hypothesis.elo.toFixed(1)}
              </Badge>
              <Badge color="gray" variant="outline">
                {hypothesis.status}
              </Badge>
              {hypothesis.parent_ids.length ? (
                <Badge color="teal" variant="light" leftSection={<GitBranch size={12} />}>
                  evolved
                </Badge>
              ) : null}
            </Group>
          </Stack>
        </Group>

        <Section title="Claim">{hypothesis.claim}</Section>
        <Section title="Rationale">{hypothesis.rationale}</Section>

        <SimpleGrid cols={{ base: 1, md: 2 }} spacing="md">
          <ListSection title="Assumptions" items={hypothesis.assumptions} />
          <ListSection title="Risks" items={hypothesis.risks} />
        </SimpleGrid>

        <Paper p="sm" bg="#fbfcfe" withBorder radius="sm">
          <Group gap="xs" mb={4}>
            <ListChecks size={16} />
            <Text fw={700} size="sm">
              Test plan
            </Text>
          </Group>
          <Text size="sm">{hypothesis.test_plan.experiment}</Text>
          <Text size="xs" c="dimmed" mt={4}>
            Success: {hypothesis.test_plan.success_condition}
          </Text>
          <Group gap={6} mt="xs">
            {hypothesis.test_plan.metrics.map((metric) => (
              <Badge key={metric} size="xs" variant="outline">
                {metric}
              </Badge>
            ))}
          </Group>
        </Paper>

        <Divider />

        <Stack gap="xs">
          <Title order={3}>Review</Title>
          {review ? (
            <>
              <Group gap={6}>
                <Badge color={review.decision === "accept" ? "green" : "red"} variant="light">
                  {review.decision}
                </Badge>
                {Object.entries(review.scores).map(([key, value]) => (
                  <Badge key={key} color="gray" variant="outline">
                    {key}: {value}
                  </Badge>
                ))}
              </Group>
              <SimpleGrid cols={{ base: 1, md: 2 }} spacing="sm">
                <ListSection title="Strengths" items={review.strengths} />
                <ListSection title="Weaknesses" items={review.weaknesses} />
              </SimpleGrid>
              <ListSection title="Safety notes" items={review.safety_notes} />
            </>
          ) : (
            <Text size="sm" c="dimmed">
              No review found for this hypothesis.
            </Text>
          )}
        </Stack>

        {parents.length ? (
          <Stack gap="xs">
            <Title order={3}>Lineage</Title>
            <List size="sm">
              {parents.map((parent) => (
                <List.Item key={parent.id}>{parent.title}</List.Item>
              ))}
            </List>
          </Stack>
        ) : null}
      </Stack>
    </Paper>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <Stack gap={3}>
      <Text fw={700} size="sm">
        {title}
      </Text>
      <Text size="sm" c="dimmed">
        {children}
      </Text>
    </Stack>
  );
}

function ListSection({ title, items }: { title: string; items: string[] }) {
  return (
    <Stack gap={4}>
      <Text fw={700} size="sm">
        {title}
      </Text>
      {items.length ? (
        <List size="sm" spacing={4}>
          {items.map((item) => (
            <List.Item key={item}>{item}</List.Item>
          ))}
        </List>
      ) : (
        <Text size="sm" c="dimmed">
          None recorded.
        </Text>
      )}
    </Stack>
  );
}
