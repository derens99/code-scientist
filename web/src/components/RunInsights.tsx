"use client";

import { Badge, Group, Paper, ScrollArea, Stack, Tabs, Text, Title } from "@mantine/core";
import { Activity, Brain, Database, FileText } from "lucide-react";
import type { ContextSnapshot, Hypothesis, Match, MetaReview, ProximityEdge, ResearchPlanConfig } from "@/lib/types";

type RunInsightsProps = {
  matches: Match[];
  metaReviews: MetaReview[];
  hypotheses: Hypothesis[];
  plan?: ResearchPlanConfig | null;
  proximityEdges?: ProximityEdge[];
  contextSnapshots?: ContextSnapshot[];
  report: string;
};

export function RunInsights({
  matches,
  metaReviews,
  hypotheses,
  plan,
  proximityEdges = [],
  contextSnapshots = [],
  report
}: RunInsightsProps) {
  const byId = new Map(hypotheses.map((hypothesis) => [hypothesis.id, hypothesis]));

  return (
    <Paper p="md" withBorder radius="sm">
      <Tabs defaultValue="matches" keepMounted={false}>
        <Tabs.List>
          <Tabs.Tab value="matches" leftSection={<Activity size={15} />}>
            Matches
          </Tabs.Tab>
          <Tabs.Tab value="meta" leftSection={<Brain size={15} />}>
            Meta-review
          </Tabs.Tab>
          <Tabs.Tab value="plan" leftSection={<Database size={15} />}>
            Plan
          </Tabs.Tab>
          <Tabs.Tab value="report" leftSection={<FileText size={15} />}>
            Report
          </Tabs.Tab>
        </Tabs.List>

        <Tabs.Panel value="matches" pt="md">
          <Stack gap="sm">
            {matches.length ? (
              matches.map((match) => (
                <Paper key={match.id} p="sm" withBorder radius="sm" bg="#fbfcfe">
                  <Group justify="space-between" gap="sm" align="flex-start">
                    <Stack gap={4}>
                      <Text fw={700} size="sm">
                        {titleFor(byId, match.hypothesis_a)} vs {titleFor(byId, match.hypothesis_b)}
                      </Text>
                      <Text size="sm" c="dimmed">
                        {match.rationale}
                      </Text>
                    </Stack>
                    <Badge color="green" variant="light">
                      Winner: {titleFor(byId, match.winner)}
                    </Badge>
                  </Group>
                </Paper>
              ))
            ) : (
              <EmptyText>No tournament matches recorded for this run.</EmptyText>
            )}
          </Stack>
        </Tabs.Panel>

        <Tabs.Panel value="meta" pt="md">
          <Stack gap="md">
            {metaReviews.length ? (
              metaReviews.map((meta) => <MetaReviewPanel key={meta.id} meta={meta} />)
            ) : (
              <EmptyText>No meta-review recorded for this run.</EmptyText>
            )}
          </Stack>
        </Tabs.Panel>

        <Tabs.Panel value="plan" pt="md">
          <PlanContextPanel
            plan={plan}
            contextSnapshots={contextSnapshots}
            proximityEdges={proximityEdges}
            hypotheses={byId}
          />
        </Tabs.Panel>

        <Tabs.Panel value="report" pt="md">
          {report ? (
            <ScrollArea h={420} offsetScrollbars>
              <Text component="pre" size="sm" style={{ whiteSpace: "pre-wrap", margin: 0, lineHeight: 1.55 }}>
                {report}
              </Text>
            </ScrollArea>
          ) : (
            <EmptyText>No report.md found for this run.</EmptyText>
          )}
        </Tabs.Panel>
      </Tabs>
    </Paper>
  );
}

function PlanContextPanel({
  plan,
  contextSnapshots,
  proximityEdges,
  hypotheses
}: {
  plan?: ResearchPlanConfig | null;
  contextSnapshots: ContextSnapshot[];
  proximityEdges: ProximityEdge[];
  hypotheses: Map<string, Hypothesis>;
}) {
  const latest = contextSnapshots.at(-1);
  return (
    <Stack gap="md">
      {plan ? (
        <Stack gap="xs">
          <Title order={3}>Research plan</Title>
          <InsightGroup label="Evaluation criteria" items={plan.evaluation_criteria} color="blue" />
          <InsightGroup label="Generation methods" items={plan.generation_methods} color="teal" />
          <InsightGroup label="Review types" items={plan.review_types} color="gray" />
          <InsightGroup label="Evolution strategies" items={plan.evolution_strategies} color="green" />
        </Stack>
      ) : (
        <EmptyText>No research plan configuration recorded for this run.</EmptyText>
      )}

      {latest ? (
        <Stack gap="xs">
          <Title order={3}>Context memory</Title>
          <Group gap={6}>
            <Badge variant="light">Cycle {latest.cycle}</Badge>
            <Badge variant="light">{latest.accepted_total} accepted</Badge>
            <Badge variant="light">{latest.match_total} matches</Badge>
            <Badge variant="light">{latest.proximity_edge_count} proximity edges</Badge>
          </Group>
          <InsightGroup label="Next actions" items={latest.next_actions} color="yellow" />
        </Stack>
      ) : (
        <EmptyText>No context memory snapshots recorded for this run.</EmptyText>
      )}

      <Stack gap="xs">
        <Title order={3}>Proximity graph</Title>
        {proximityEdges.length ? (
          proximityEdges.slice(0, 5).map((edge) => (
            <Text key={`${edge.source}:${edge.target}`} size="sm" c="dimmed">
              {titleFor(hypotheses, edge.source)} vs {titleFor(hypotheses, edge.target)}:{" "}
              {edge.similarity.toFixed(3)}
            </Text>
          ))
        ) : (
          <EmptyText>No proximity edges recorded for this run.</EmptyText>
        )}
      </Stack>
    </Stack>
  );
}

function MetaReviewPanel({ meta }: { meta: MetaReview }) {
  return (
    <Paper p="sm" withBorder radius="sm" bg="#fbfcfe">
      <Title order={3} mb="xs">
        Meta-review
      </Title>
      <InsightGroup label="Common weaknesses" items={meta.common_weaknesses} color="yellow" />
      <InsightGroup label="Safety concerns" items={meta.safety_concerns} color="red" />
      <InsightGroup label="Missing evidence" items={meta.missing_evidence} color="gray" />
      <InsightGroup label="Promising directions" items={meta.promising_directions} color="blue" />
      <InsightGroup label="Prompt feedback" items={meta.prompt_feedback} color="teal" />
    </Paper>
  );
}

function InsightGroup({ label, items, color }: { label: string; items: string[]; color: string }) {
  return (
    <Stack gap={4} mb="sm">
      <Text fw={700} size="sm">
        {label}
      </Text>
      <Group gap={6}>
        {items.length ? (
          items.map((item) => (
            <Badge key={item} color={color} variant="light">
              {item}
            </Badge>
          ))
        ) : (
          <Text size="sm" c="dimmed">
            None recorded.
          </Text>
        )}
      </Group>
    </Stack>
  );
}

function EmptyText({ children }: { children: React.ReactNode }) {
  return (
    <Text size="sm" c="dimmed">
      {children}
    </Text>
  );
}

function titleFor(hypotheses: Map<string, Hypothesis>, id: string) {
  return hypotheses.get(id)?.title ?? id;
}
