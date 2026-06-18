"use client";

import { Badge, Group, Paper, Progress, ScrollArea, Stack, Table, Text, Title } from "@mantine/core";
import { Trophy } from "lucide-react";
import type { Hypothesis } from "@/lib/types";

type HypothesisLeaderboardProps = {
  hypotheses: Hypothesis[];
  selectedId: string | null;
  onSelect: (id: string) => void;
};

export function HypothesisLeaderboard({ hypotheses, selectedId, onSelect }: HypothesisLeaderboardProps) {
  const ranked = [...hypotheses].sort((left, right) => right.elo - left.elo);
  const elos = ranked.map((item) => item.elo);
  const min = Math.min(...elos, 1100);
  const max = Math.max(...elos, 1300);

  return (
    <Paper p="md" withBorder radius="sm" h="100%">
      <Group justify="space-between" mb="sm">
        <Stack gap={2}>
          <Title order={2}>Leaderboard</Title>
          <Text size="xs" c="dimmed">
            Elo is an internal proxy signal.
          </Text>
        </Stack>
        <Badge leftSection={<Trophy size={13} />} color="blue" variant="light">
          {ranked.length} ideas
        </Badge>
      </Group>

      <ScrollArea h={520} offsetScrollbars>
        <Table verticalSpacing="sm" highlightOnHover>
          <Table.Tbody>
            {ranked.map((hypothesis, index) => {
              const selected = hypothesis.id === selectedId;
              const value = max === min ? 50 : ((hypothesis.elo - min) / (max - min)) * 100;
              return (
                <Table.Tr
                  key={hypothesis.id}
                  onClick={() => onSelect(hypothesis.id)}
                  bg={selected ? "blue.0" : undefined}
                  style={{ cursor: "pointer" }}
                >
                  <Table.Td w={42}>
                    <Text fw={800} c={selected ? "blue.7" : "dimmed"}>
                      {index + 1}
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    <Stack gap={5}>
                      <Group justify="space-between" gap="xs" wrap="nowrap">
                        <Text fw={700} size="sm" lineClamp={2}>
                          {hypothesis.title}
                        </Text>
                        <Badge color={hypothesis.origin === "evolution" ? "teal" : "gray"} variant="light">
                          {hypothesis.origin}
                        </Badge>
                      </Group>
                      <Text size="xs" c="dimmed" lineClamp={2}>
                        {hypothesis.claim}
                      </Text>
                      <Group gap={6}>
                        <Text size="xs" fw={700}>
                          {hypothesis.elo.toFixed(1)}
                        </Text>
                        <Progress value={value} size="xs" w={120} color="blue" />
                        {hypothesis.test_plan.metrics.slice(0, 3).map((metric) => (
                          <Badge key={metric} size="xs" color="gray" variant="outline">
                            {metric}
                          </Badge>
                        ))}
                      </Group>
                    </Stack>
                  </Table.Td>
                </Table.Tr>
              );
            })}
          </Table.Tbody>
        </Table>
      </ScrollArea>
    </Paper>
  );
}
