"use client";

import { useState } from "react";
import { Badge, Button, Group, Paper, ScrollArea, Stack, Tabs, Text, TextInput, Title } from "@mantine/core";
import { Activity, Brain, Database, FileText, GitMerge, Sparkles } from "lucide-react";
import type {
  AgentToolCall,
  AgentTrace,
  BenchmarkResult,
  CapabilityEvaluation,
  ContextSnapshot,
  FeedbackLoopEvaluation,
  GoalRevision,
  Hypothesis,
  Match,
  MetaReview,
  ProximityEdge,
  ProspectiveEvaluation,
  ResearchOverview,
  ResearchOutputArtifact,
  ResearchPlanConfig,
  RetrievalMemoryRecord,
  SafetyEvaluationResult,
  ScalingCurvePoint,
  Task,
  ToolBudgetState,
  UserFeedback
} from "@/lib/types";

type RunInsightsProps = {
  matches: Match[];
  metaReviews: MetaReview[];
  hypotheses: Hypothesis[];
  plan?: ResearchPlanConfig | null;
  proximityEdges?: ProximityEdge[];
  contextSnapshots?: ContextSnapshot[];
  benchmarkResults?: BenchmarkResult[];
  capabilityEvaluations?: CapabilityEvaluation[];
  prospectiveEvaluations?: ProspectiveEvaluation[];
  scalingCurve?: ScalingCurvePoint[];
  safetyEvaluations?: SafetyEvaluationResult[];
  feedbackLoopEvaluations?: FeedbackLoopEvaluation[];
  researchOutputArtifacts?: ResearchOutputArtifact[];
  researchOverview?: ResearchOverview | null;
  agentTraces?: AgentTrace[];
  retrievalMemory?: RetrievalMemoryRecord[];
  toolBudget?: ToolBudgetState | null;
  agentToolCalls?: AgentToolCall[];
  taskQueue?: Task[];
  userFeedback?: UserFeedback[];
  goalRevisions?: GoalRevision[];
  onProximityOverride?: (edge: ProximityEdge, decision: "merge" | "preserve") => void;
  onProximityClusterOverride?: (clusterId: string, decision: "merge" | "preserve") => void;
  onProximityClusterAssignment?: (edge: ProximityEdge, clusterId: string) => void;
  proximityOverrideLoading?: boolean;
  defaultTab?: string;
  report: string;
};

type ProximityClusterSummary = {
  clusterId: string;
  edgeCount: number;
  hypothesisCount: number;
  topSimilarity: number;
  mergeCount: number;
  preserveCount: number;
};

type ProximityGraphNode = {
  id: string;
  title: string;
  degree: number;
  strongestSimilarity: number;
  clusters: string[];
  mergeCount: number;
  preserveCount: number;
  neighbors: ProximityGraphNeighbor[];
};

type ProximityGraphNeighbor = {
  id: string;
  title: string;
  similarity: number;
  clusterId: string;
  method: string;
  edge: ProximityEdge;
};

type SchedulerDecisionView = {
  rank: number;
  score: number;
  candidateCount: number;
  poolSize: number;
  cycle?: number;
  signals: string[];
};

export function RunInsights({
  matches,
  metaReviews,
  hypotheses,
  plan,
  proximityEdges = [],
  contextSnapshots = [],
  benchmarkResults = [],
  capabilityEvaluations = [],
  prospectiveEvaluations = [],
  scalingCurve = [],
  safetyEvaluations = [],
  feedbackLoopEvaluations = [],
  researchOutputArtifacts = [],
  researchOverview = null,
  agentTraces = [],
  retrievalMemory = [],
  toolBudget = null,
  agentToolCalls = [],
  taskQueue = [],
  userFeedback = [],
  goalRevisions = [],
  onProximityOverride,
  onProximityClusterOverride,
  onProximityClusterAssignment,
  proximityOverrideLoading = false,
  defaultTab = "overview",
  report
}: RunInsightsProps) {
  const byId = new Map(hypotheses.map((hypothesis) => [hypothesis.id, hypothesis]));

  return (
    <Paper p="md" withBorder radius="sm">
      <Tabs defaultValue={defaultTab} keepMounted={false}>
        <Tabs.List>
          <Tabs.Tab value="overview" leftSection={<Brain size={15} />}>
            Overview
          </Tabs.Tab>
          <Tabs.Tab value="matches" leftSection={<Activity size={15} />}>
            Matches
          </Tabs.Tab>
          <Tabs.Tab value="meta" leftSection={<Brain size={15} />}>
            Meta-review
          </Tabs.Tab>
          <Tabs.Tab value="plan" leftSection={<Database size={15} />}>
            Plan
          </Tabs.Tab>
          <Tabs.Tab value="benchmarks" leftSection={<Activity size={15} />}>
            Benchmarks
          </Tabs.Tab>
          <Tabs.Tab value="report" leftSection={<FileText size={15} />}>
            Report
          </Tabs.Tab>
        </Tabs.List>

        <Tabs.Panel value="overview" pt="md">
          <OverviewPanel
            overview={researchOverview}
            researchOutputArtifacts={researchOutputArtifacts}
            agentTraces={agentTraces}
            hypotheses={byId}
          />
        </Tabs.Panel>

        <Tabs.Panel value="matches" pt="md">
          <Stack gap="sm">
            {matches.length ? (
              matches.map((match) => (
                <MatchPanel key={match.id} match={match} hypotheses={byId} userFeedback={userFeedback} />
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
            retrievalMemory={retrievalMemory}
            toolBudget={toolBudget}
            agentToolCalls={agentToolCalls}
            taskQueue={taskQueue}
            goalRevisions={goalRevisions}
            proximityEdges={proximityEdges}
            hypotheses={byId}
            onProximityOverride={onProximityOverride}
            onProximityClusterOverride={onProximityClusterOverride}
            onProximityClusterAssignment={onProximityClusterAssignment}
            proximityOverrideLoading={proximityOverrideLoading}
          />
        </Tabs.Panel>

        <Tabs.Panel value="benchmarks" pt="md">
          <BenchmarkPanel
            benchmarkResults={benchmarkResults}
            capabilityEvaluations={capabilityEvaluations}
            prospectiveEvaluations={prospectiveEvaluations}
            scalingCurve={scalingCurve}
            safetyEvaluations={safetyEvaluations}
            feedbackLoopEvaluations={feedbackLoopEvaluations}
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

function MatchPanel({
  match,
  hypotheses,
  userFeedback
}: {
  match: Match;
  hypotheses: Map<string, Hypothesis>;
  userFeedback: UserFeedback[];
}) {
  const humanInfluence = humanInfluenceForMatch(match, userFeedback);
  return (
    <Paper p="sm" withBorder radius="sm" bg="#fbfcfe">
      <Group justify="space-between" gap="sm" align="flex-start">
        <Stack gap={4}>
          <Text fw={700} size="sm">
            {titleFor(hypotheses, match.hypothesis_a)} vs {titleFor(hypotheses, match.hypothesis_b)}
          </Text>
          <Text size="sm" c="dimmed">
            {match.rationale}
          </Text>
          <Group gap={6}>
            <Badge color="gray" variant="light">
              {match.comparison_mode ?? "heuristic_pairwise"}
            </Badge>
            <Badge color="yellow" variant="light">
              Uncertainty {formatMetric(match.uncertainty ?? 0)}
            </Badge>
            {match.judge_trace?.includes("position_stable=") ? (
              <Badge
                color={match.judge_trace.includes("position_stable=false") ? "red" : "green"}
                variant="light"
              >
                {match.judge_trace.includes("position_stable=false")
                  ? "Order disagreement"
                  : "Order stable"}
              </Badge>
            ) : null}
          </Group>
          {match.review_refs?.length ? (
            <Text size="xs" c="dimmed">
              Reviews: {match.review_refs.join(", ")}
            </Text>
          ) : null}
          {match.evidence_refs?.length ? (
            <Text size="xs" c="dimmed">
              Evidence: {match.evidence_refs.join(", ")}
            </Text>
          ) : null}
          {humanInfluence.length ? (
            <Stack gap={2}>
              <Text fw={700} size="xs">
                Human influence
              </Text>
              {humanInfluence.map((item) => (
                <Text key={item} size="xs" c="dimmed">
                  {item}
                </Text>
              ))}
            </Stack>
          ) : null}
          {match.judge_trace ? (
            <Text size="xs" c="dimmed">
              {match.judge_trace}
            </Text>
          ) : null}
          {match.debate_transcript?.length ? (
            <Stack gap={2}>
              <Text fw={700} size="xs">
                Debate transcript
              </Text>
              {match.debate_transcript.map((line) => (
                <Text key={line} size="xs" c="dimmed">
                  {line}
                </Text>
              ))}
            </Stack>
          ) : null}
        </Stack>
        <Badge color="green" variant="light">
          {match.outcome === "tie" ? "Tie" : `Winner: ${titleFor(hypotheses, match.winner)}`}
        </Badge>
      </Group>
    </Paper>
  );
}

function BenchmarkPanel({
  benchmarkResults,
  capabilityEvaluations,
  prospectiveEvaluations,
  scalingCurve,
  safetyEvaluations,
  feedbackLoopEvaluations
}: {
  benchmarkResults: BenchmarkResult[];
  capabilityEvaluations: CapabilityEvaluation[];
  prospectiveEvaluations: ProspectiveEvaluation[];
  scalingCurve: ScalingCurvePoint[];
  safetyEvaluations: SafetyEvaluationResult[];
  feedbackLoopEvaluations: FeedbackLoopEvaluation[];
}) {
  const hasEvaluation =
    benchmarkResults.length ||
    capabilityEvaluations.length ||
    prospectiveEvaluations.length ||
    scalingCurve.length ||
    safetyEvaluations.length ||
    feedbackLoopEvaluations.length;
  const studySummary = summarizeCapabilityStudy(
    capabilityEvaluations,
    scalingCurve,
    prospectiveEvaluations,
    feedbackLoopEvaluations
  );
  return (
    <Stack gap="sm">
      {!hasEvaluation ? (
        <EmptyText>No benchmark results recorded for this run.</EmptyText>
      ) : null}

      {hasEvaluation ? (
        <Paper p="sm" withBorder radius="sm" bg="#f7fbff">
          <Group justify="space-between" align="flex-start" gap="sm">
            <Stack gap={4}>
              <Text fw={700} size="sm">
                Capability study summary
              </Text>
              <Text size="sm" c="dimmed">
                Win rate {formatFixedMetric(studySummary.baselineWinRate)}; Mean delta{" "}
                {formatFixedDelta(studySummary.meanScoreDelta)}; 95% CI [
                {formatFixedDelta(studySummary.scoreDeltaCiLow)}, {formatFixedDelta(studySummary.scoreDeltaCiHigh)}];
                Sign-test p {formatFixedMetric(studySummary.baselineWinSignTestPValue)}; Scaling trend{" "}
                {formatFixedDelta(studySummary.scalingDeltaTrend)}; Prospective success{" "}
                {formatFixedMetric(studySummary.prospectiveSuccessRate)}; Feedback-loop positive{" "}
                {formatFixedMetric(studySummary.feedbackLoopPositiveRate)}; Feedback-loop mean delta{" "}
                {formatFixedDelta(studySummary.feedbackLoopMeanDelta)}
              </Text>
              <Text size="xs" c="dimmed">
                {studySummary.evaluationCount} baseline evaluations; {studySummary.scalingPointCount} scaling
                points; {studySummary.prospectiveCount} prospective records;{" "}
                {studySummary.feedbackLoopMeasurementCount} feedback-loop measurements
              </Text>
            </Stack>
            <Badge color={studySummary.baselineWinRate >= 0.5 ? "green" : "yellow"} variant="light">
              Study
            </Badge>
          </Group>
        </Paper>
      ) : null}

      {benchmarkResults.map((result) => (
        <Paper key={result.id} p="sm" withBorder radius="sm" bg="#fbfcfe">
          <Group justify="space-between" align="flex-start" gap="sm">
            <Stack gap={4}>
              <Text fw={700} size="sm">
                {result.name}
              </Text>
              <Text size="xs" c="dimmed">
                {result.source}
              </Text>
            </Stack>
            <Badge color={result.success ? "green" : "yellow"} variant="light">
              {result.success ? "Passed" : "Needs review"}
            </Badge>
          </Group>
          <Stack gap={4} mt="xs">
            {Object.keys(result.candidate_metrics)
              .sort()
              .map((metric) => (
                <Text key={metric} size="sm" c="dimmed">
                  {metric}: baseline {formatMetric(result.baseline_metrics[metric])}, candidate{" "}
                  {formatMetric(result.candidate_metrics[metric])}, delta{" "}
                  {formatDelta(result.deltas[metric])}
                </Text>
              ))}
          </Stack>
        </Paper>
      ))}

      {capabilityEvaluations.map((evaluation) => (
        <Paper key={evaluation.id} p="sm" withBorder radius="sm" bg="#fbfcfe">
          <Group justify="space-between" align="flex-start" gap="sm">
            <Stack gap={4}>
              <Text fw={700} size="sm">
                {evaluation.baseline_name}
              </Text>
              <Text size="sm" c="dimmed">
                {evaluation.summary}
              </Text>
              <Text size="xs" c="dimmed">
                Top hypothesis: {evaluation.top_hypothesis_id}
              </Text>
              <Text size="xs" c="dimmed">
                Elo-human {formatMetric(evaluation.elo_human_correlation)}; Elo-benchmark{" "}
                {formatMetric(evaluation.elo_benchmark_correlation)}
              </Text>
              {evaluation.human_preference_judgment_count ? (
                <Text size="xs" c="dimmed">
                  Human preferences {evaluation.human_preference_judgment_count}; Code Scientist win rate{" "}
                  {formatMetric(evaluation.human_preference_win_rate ?? 0)}
                </Text>
              ) : null}
            </Stack>
            <Badge color={evaluation.beats_baseline ? "green" : "yellow"} variant="light">
              {evaluation.beats_baseline ? "Beats baseline" : "Below baseline"}
            </Badge>
          </Group>
        </Paper>
      ))}

      {prospectiveEvaluations.map((evaluation) => (
        <Paper key={evaluation.id} p="sm" withBorder radius="sm" bg="#fbfcfe">
          <Group justify="space-between" align="flex-start" gap="sm">
            <Stack gap={4}>
              <Text fw={700} size="sm">
                Prospective: {evaluation.hypothesis_id}
              </Text>
              <Text size="xs" c="dimmed">
                {evaluation.implementation_refs.join(", ") || "No implementation refs"}
              </Text>
              <Text size="xs" c="dimmed">
                {evaluation.measurement_status ?? "proxy"} via {evaluation.measurement_source ?? "proxy"}
              </Text>
              {Object.keys(evaluation.baseline_metrics)
                .sort()
                .map((metric) => {
                  const measured = evaluation.measured_metrics[metric];
                  return (
                    <Text key={metric} size="sm" c="dimmed">
                      {metric}: baseline {formatMetric(evaluation.baseline_metrics[metric])}
                      {measured === undefined
                        ? "; no measurement"
                        : `, measured ${formatMetric(measured)}, delta ${formatDelta(evaluation.deltas[metric])}`}
                    </Text>
                  );
                })}
            </Stack>
            <Badge color={evaluation.success ? "green" : "yellow"} variant="light">
              {evaluation.status}
            </Badge>
          </Group>
        </Paper>
      ))}

      {scalingCurve.map((point) => (
        <Paper key={point.id} p="sm" withBorder radius="sm" bg="#fbfcfe">
          <Text fw={700} size="sm">
            Scaling: {point.label}
          </Text>
          <Text size="sm" c="dimmed">
            cycles {point.cycles}, tasks {point.task_count}, tool budget {point.tool_budget}; baseline{" "}
            {formatMetric(point.baseline_score)}, Code Scientist {formatMetric(point.code_scientist_score)},
            delta {formatDelta(point.delta)}
          </Text>
        </Paper>
      ))}

      {safetyEvaluations.map((evaluation) => (
        <Paper key={evaluation.id} p="sm" withBorder radius="sm" bg="#fbfcfe">
          <Group justify="space-between" align="flex-start" gap="sm">
            <Stack gap={4}>
              <Text fw={700} size="sm">
                Safety: {evaluation.suite_name}
              </Text>
              <Text size="sm" c="dimmed">
                {evaluation.passed_count}/{evaluation.case_count} cases passed; pass rate{" "}
                {formatMetric(evaluation.pass_rate)}
              </Text>
              <Text size="xs" c="dimmed">
                Failed cases: {evaluation.failed_case_ids.join(", ") || "none"}
              </Text>
              {evaluation.topic_results ? (
                <Text size="xs" c="dimmed">
                  Base {formatMetric(evaluation.base_pass_rate ?? 0)}; variants{" "}
                  {formatMetric(evaluation.variant_pass_rate ?? 0)}; degradation{" "}
                  {formatMetric(evaluation.degradation_rate ?? 0)}. Topics:{" "}
                  {Object.entries(evaluation.topic_results)
                    .map(([topic, result]) => `${topic} ${result.passed_count}/${result.case_count}`)
                    .join(", ")}
                </Text>
              ) : null}
            </Stack>
            <Badge color={evaluation.failed_count ? "red" : "green"} variant="light">
              {evaluation.failed_count ? "Failures" : "Passed"}
            </Badge>
          </Group>
        </Paper>
      ))}

      {feedbackLoopEvaluations.map((evaluation) => (
        <Paper key={evaluation.id} p="sm" withBorder radius="sm" bg="#fbfcfe">
          <Group justify="space-between" align="flex-start" gap="sm">
            <Stack gap={4}>
              <Text fw={700} size="sm">
                Feedback loop: {evaluation.source_meta_review_id}
              </Text>
              <Text size="sm" c="dimmed">
                {evaluation.adopted_feedback_count}/{evaluation.feedback_item_count} feedback items adopted;
                adoption rate {formatMetric(evaluation.adoption_rate)}
              </Text>
              <Text size="xs" c="dimmed">
                Agents: {evaluation.feedback_agents.join(", ") || "none"}
              </Text>
              <Text size="xs" c="dimmed">
                {(evaluation.measurement_status ?? "proxy")} via {evaluation.measurement_source ?? "proxy"}
              </Text>
              {Object.keys(evaluation.baseline_quality)
                .sort()
                .map((metric) => {
                  const observed = evaluation.observed_quality[metric];
                  return (
                    <Text key={metric} size="xs" c="dimmed">
                      {metric}: baseline {formatMetric(evaluation.baseline_quality[metric])}
                      {observed === undefined
                        ? "; no observation"
                        : `, observed ${formatMetric(observed)}, delta ${formatDelta(evaluation.deltas[metric])}`}
                    </Text>
                  );
                })}
              {evaluation.summary ? (
                <Text size="xs" c="dimmed">
                  {evaluation.summary}
                </Text>
              ) : null}
            </Stack>
            <Badge color={evaluation.adoption_rate >= 0.75 ? "green" : "yellow"} variant="light">
              Feedback
            </Badge>
          </Group>
        </Paper>
      ))}
    </Stack>
  );
}

function OverviewPanel({
  overview,
  researchOutputArtifacts,
  agentTraces,
  hypotheses
}: {
  overview?: ResearchOverview | null;
  researchOutputArtifacts: ResearchOutputArtifact[];
  agentTraces: AgentTrace[];
  hypotheses: Map<string, Hypothesis>;
}) {
  const recentTraces = agentTraces.slice(-8).reverse();
  return (
    <Stack gap="md">
      {overview ? (
        <Stack gap="xs">
          <Title order={3}>Research overview</Title>
          <Text size="sm" c="dimmed">
            {overview.summary}
          </Text>
          <InsightGroup
            label="Top hypotheses"
            items={overview.top_hypothesis_ids.map((id) => titleFor(hypotheses, id))}
            color="green"
          />
          <InsightGroup label="Promising directions" items={overview.promising_directions} color="blue" />
          <InsightGroup label="Next experiments" items={overview.next_experiments} color="teal" />
          <InsightGroup label="Limitations" items={overview.limitations} color="yellow" />
        </Stack>
      ) : (
        <EmptyText>No first-class research overview recorded for this run.</EmptyText>
      )}

      {researchOutputArtifacts.length ? (
        <Stack gap="xs">
          <Title order={3}>Research outputs</Title>
          {researchOutputArtifacts.map((artifact) => (
            <Paper key={artifact.id} p="sm" withBorder radius="sm" bg="#fbfcfe">
              <Stack gap={4}>
                <Group justify="space-between" align="flex-start" gap="sm">
                  <Text fw={700} size="sm">
                    {artifact.title}
                  </Text>
                  <Badge color="blue" variant="light">
                    {artifact.output_type}
                  </Badge>
                </Group>
                <Text size="sm" c="dimmed">
                  {artifact.summary}
                </Text>
                {artifact.contact_targets.length ? (
                  <Text size="xs" c="dimmed">
                    Contacts: {artifact.contact_targets.join(", ")}
                  </Text>
                ) : null}
                {Object.entries(artifact.sections).map(([section, content]) => (
                  <Text key={section} size="xs" c="dimmed">
                    {section}: {content}
                  </Text>
                ))}
              </Stack>
            </Paper>
          ))}
        </Stack>
      ) : null}

      <Stack gap="xs">
        <Title order={3}>Agent trace log</Title>
        {recentTraces.length ? (
          recentTraces.map((trace) => (
            <Paper key={trace.id} p="sm" withBorder radius="sm" bg="#fbfcfe">
              <Group justify="space-between" gap="xs" align="flex-start">
                <Stack gap={4}>
                  <Text fw={700} size="sm">
                    Cycle {trace.cycle}: {trace.agent}.{trace.action}
                  </Text>
                  {trace.notes ? (
                    <Text size="sm" c="dimmed">
                      {trace.notes}
                    </Text>
                  ) : null}
                  {trace.output_refs.length ? (
                    <Text size="xs" c="dimmed">
                      Outputs: {trace.output_refs.join(", ")}
                    </Text>
                  ) : null}
                  {trace.task_id ? (
                    <Text size="xs" c="dimmed">
                      Task: {trace.task_id}
                    </Text>
                  ) : null}
                  {trace.scratchpad?.length ? (
                    <Text size="xs" c="dimmed">
                      Scratchpad: {trace.scratchpad.slice(0, 3).join(" | ")}
                      {trace.scratchpad.length > 3 ? ` +${trace.scratchpad.length - 3}` : ""}
                    </Text>
                  ) : null}
                  {trace.llm_interactions?.length ? (
                    <Text size="xs" c="dimmed">
                      LLM calls:{" "}
                      {trace.llm_interactions
                        .slice(0, 3)
                        .map((interaction) => interaction.turn)
                        .join(", ")}
                      {trace.llm_interactions.length > 3 ? ` +${trace.llm_interactions.length - 3}` : ""}
                    </Text>
                  ) : null}
                  {trace.tool_calls?.length ? (
                    <Text size="xs" c="dimmed">
                      Tool calls:{" "}
                      {trace.tool_calls
                        .slice(0, 3)
                        .map((toolCall) => toolCall.tool_name)
                        .join(", ")}
                      {trace.tool_calls.length > 3 ? ` +${trace.tool_calls.length - 3}` : ""}
                    </Text>
                  ) : null}
                </Stack>
                <Badge color={trace.status === "completed" ? "green" : "yellow"} variant="light">
                  {trace.status}
                </Badge>
              </Group>
            </Paper>
          ))
        ) : (
          <EmptyText>No agent traces recorded for this run.</EmptyText>
        )}
      </Stack>
    </Stack>
  );
}

function PlanContextPanel({
  plan,
  contextSnapshots,
  retrievalMemory,
  toolBudget,
  agentToolCalls,
  taskQueue,
  goalRevisions,
  proximityEdges,
  hypotheses,
  onProximityOverride,
  onProximityClusterOverride,
  onProximityClusterAssignment,
  proximityOverrideLoading
}: {
  plan?: ResearchPlanConfig | null;
  contextSnapshots: ContextSnapshot[];
  retrievalMemory: RetrievalMemoryRecord[];
  toolBudget: ToolBudgetState | null;
  agentToolCalls: AgentToolCall[];
  taskQueue: Task[];
  goalRevisions: GoalRevision[];
  proximityEdges: ProximityEdge[];
  hypotheses: Map<string, Hypothesis>;
  onProximityOverride?: (edge: ProximityEdge, decision: "merge" | "preserve") => void;
  onProximityClusterOverride?: (clusterId: string, decision: "merge" | "preserve") => void;
  onProximityClusterAssignment?: (edge: ProximityEdge, clusterId: string) => void;
  proximityOverrideLoading: boolean;
}) {
  const [clusterDrafts, setClusterDrafts] = useState<Record<string, string>>({});
  const latest = contextSnapshots.at(-1);
  const schedulerDecisions = taskQueue
    .map((task) => ({ task, decision: readSchedulerDecision(task) }))
    .filter((item): item is { task: Task; decision: SchedulerDecisionView } => item.decision !== null)
    .sort((left, right) => {
      const leftCycle = left.decision.cycle ?? 0;
      const rightCycle = right.decision.cycle ?? 0;
      if (leftCycle !== rightCycle) {
        return rightCycle - leftCycle;
      }
      return left.decision.rank - right.decision.rank;
    });
  const clusterSummaries = summarizeProximityClusters(proximityEdges);
  const graphNodes = summarizeProximityGraph(proximityEdges, hypotheses);
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

      {goalRevisions.length ? (
        <Stack gap="xs">
          <Title order={3}>Goal revision history</Title>
          {goalRevisions.map((revision) => (
            <Paper key={revision.id} p="xs" withBorder radius="sm" bg="#fbfcfe">
              <Stack gap={3}>
                <Group justify="space-between" gap="xs">
                  <Text size="sm" fw={700}>Revision {revision.revision}</Text>
                  <Badge color={revision.approval_status === "approved" ? "green" : "red"} variant="light">
                    {revision.approval_status}
                  </Badge>
                </Group>
                <Text size="xs" c="dimmed">
                  {revision.prior_goal_id} to {revision.new_goal_id}; {revision.affected_task_ids.length} queued tasks affected
                </Text>
                {revision.user_message ? <Text size="sm">{revision.user_message}</Text> : null}
                {!revision.safety.allowed ? <Text size="xs" c="red">{revision.safety.reason}</Text> : null}
              </Stack>
            </Paper>
          ))}
        </Stack>
      ) : null}

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

      {retrievalMemory.length ? (
        <Stack gap="xs">
          <Group gap={6}>
            <Badge variant="light">{retrievalMemory.length} retrieval records</Badge>
            <Badge variant="light">
              {new Set(retrievalMemory.map((record) => record.agent || "unassigned")).size} agents
            </Badge>
          </Group>
          {retrievalMemory.slice(-5).map((record) => (
            <Paper key={record.id} p="xs" withBorder radius="sm" bg="#fbfcfe">
              <Stack gap={2}>
                <Text size="sm" fw={700}>
                  {record.agent || "unassigned"} - {record.retrieval_method}
                </Text>
                <Text size="xs" c="dimmed">
                  {record.query}
                </Text>
                {record.evidence_refs.length ? (
                  <Text size="xs" c="dimmed">
                    Evidence: {record.evidence_refs.slice(0, 5).join(", ")}
                  </Text>
                ) : null}
              </Stack>
            </Paper>
          ))}
        </Stack>
      ) : null}

      {toolBudget ? (
        <Stack gap="xs">
          <Title order={3}>Agent tool budget</Title>
          <Group gap={6}>
            <Badge variant="light">{toolBudget.used} used</Badge>
            <Badge variant="light">{Math.max(toolBudget.limit - toolBudget.used, 0)} remaining</Badge>
            <Badge color={toolBudget.used >= toolBudget.limit ? "red" : "green"} variant="light">
              limit {toolBudget.limit}
            </Badge>
          </Group>
          {agentToolCalls.slice(-5).map((call) => (
            <Paper key={call.id} p="xs" withBorder radius="sm" bg="#fbfcfe">
              <Stack gap={2}>
                <Group gap={6}>
                  <Text size="sm" fw={700}>{call.agent} - {call.tool}</Text>
                  <Badge size="xs" color={call.status === "completed" ? "green" : "yellow"}>
                    {call.status}
                  </Badge>
                </Group>
                <Text size="xs" c="dimmed">
                  {call.source_ref ? `Source ref: ${call.source_ref}` : call.query}
                </Text>
                <Text size="xs" c="dimmed">
                  Budget {call.budget_before} to {call.budget_after}; new evidence {call.evidence_refs.length}
                </Text>
              </Stack>
            </Paper>
          ))}
        </Stack>
      ) : null}

      {schedulerDecisions.length ? (
        <Stack gap="xs">
          <Title order={3}>Scheduler decisions</Title>
          {schedulerDecisions.slice(0, 6).map(({ task, decision }) => (
            <Paper
              key={`${task.id}:${decision.rank}:${decision.cycle ?? "none"}`}
              p="xs"
              withBorder
              radius="sm"
              bg="#fbfcfe"
            >
              <Stack gap={4}>
                <Group justify="space-between" gap="xs" align="flex-start">
                  <Text fw={700} size="sm">
                    {task.kind}
                  </Text>
                  <Group gap={6}>
                    <Badge variant="light">rank {decision.rank}</Badge>
                    <Badge color="gray" variant="light">
                      score {formatMetric(decision.score)}
                    </Badge>
                    <Badge variant="outline">
                      {decision.candidateCount} candidates
                    </Badge>
                    <Badge variant="outline">
                      pool {decision.poolSize}
                    </Badge>
                  </Group>
                </Group>
                {decision.signals.length ? (
                  <Group gap={4}>
                    {decision.signals.slice(0, 8).map((signal) => (
                      <Badge key={`${task.id}:${signal}`} color="teal" variant="light">
                        {signal}
                      </Badge>
                    ))}
                  </Group>
                ) : null}
              </Stack>
            </Paper>
          ))}
        </Stack>
      ) : null}

      <Stack gap="xs">
        <Title order={3}>Proximity graph</Title>
        {proximityEdges.length ? (
          <>
            {graphNodes.length ? (
              <Stack gap={4}>
                <Text fw={700} size="sm">
                  Graph neighborhoods
                </Text>
                {graphNodes.slice(0, 6).map((node) => (
                  <Paper key={node.id} p="xs" withBorder radius="sm" bg="#fbfcfe">
                    <Stack gap={4}>
                      <Group justify="space-between" gap="xs" align="flex-start">
                        <Stack gap={2}>
                          <Text fw={700} size="sm">
                            {node.title}
                          </Text>
                          <Text size="xs" c="dimmed">
                            Clusters: {node.clusters.join(", ")}
                          </Text>
                        </Stack>
                        <Group gap={6}>
                          <Badge variant="outline">Degree {node.degree}</Badge>
                          <Badge color="gray" variant="light">
                            Strongest {node.strongestSimilarity.toFixed(3)}
                          </Badge>
                          {node.mergeCount || node.preserveCount ? (
                            <Badge color="teal" variant="light">
                              merge {node.mergeCount}; preserve {node.preserveCount}
                            </Badge>
                          ) : null}
                        </Group>
                      </Group>
                      {node.neighbors.slice(0, 4).map((neighbor) => (
                        <Group key={`${node.id}:${neighbor.id}:${neighbor.clusterId}`} gap={6} align="center">
                          <Text size="xs" c="dimmed">
                            Neighbor: {neighbor.title}; {neighbor.clusterId}; {neighbor.method};{" "}
                            {neighbor.similarity.toFixed(3)}
                          </Text>
                          {onProximityClusterAssignment ? (
                            <ClusterAssignmentControl
                              edge={neighbor.edge}
                              edgeKey={proximityPairKey(neighbor.edge.source, neighbor.edge.target)}
                              nodeTitle={node.title}
                              neighborTitle={neighbor.title}
                              clusterDrafts={clusterDrafts}
                              setClusterDrafts={setClusterDrafts}
                              loading={proximityOverrideLoading}
                              onAssign={onProximityClusterAssignment}
                            />
                          ) : null}
                          {onProximityOverride ? (
                            <>
                              <Button
                                size="xs"
                                variant="light"
                                leftSection={<GitMerge size={12} />}
                                loading={proximityOverrideLoading}
                                onClick={() => onProximityOverride(neighbor.edge, "merge")}
                              >
                                Merge edge
                              </Button>
                              <Button
                                size="xs"
                                color="teal"
                                variant="light"
                                leftSection={<Sparkles size={12} />}
                                loading={proximityOverrideLoading}
                                onClick={() => onProximityOverride(neighbor.edge, "preserve")}
                              >
                                Preserve edge
                              </Button>
                            </>
                          ) : null}
                        </Group>
                      ))}
                    </Stack>
                  </Paper>
                ))}
              </Stack>
            ) : null}
            {clusterSummaries.length ? (
              <Stack gap={4}>
                <Text fw={700} size="sm">
                  Cluster overview
                </Text>
                {clusterSummaries.slice(0, 5).map((summary) => (
                  <Group key={summary.clusterId} gap={6}>
                    <Badge color="blue" variant="light">
                      {summary.clusterId}
                    </Badge>
                    <Badge variant="outline">
                      {summary.edgeCount} {summary.edgeCount === 1 ? "edge" : "edges"}
                    </Badge>
                    <Badge variant="outline">
                      {summary.hypothesisCount} {summary.hypothesisCount === 1 ? "hypothesis" : "hypotheses"}
                    </Badge>
                    <Badge color="gray" variant="light">
                      top {summary.topSimilarity.toFixed(3)}
                    </Badge>
                    {summary.mergeCount || summary.preserveCount ? (
                      <Badge color="teal" variant="light">
                        merge {summary.mergeCount}; preserve {summary.preserveCount}
                      </Badge>
                    ) : null}
                    {onProximityClusterOverride ? (
                      <>
                        <Button
                          size="xs"
                          variant="light"
                          leftSection={<GitMerge size={12} />}
                          loading={proximityOverrideLoading}
                          onClick={() => onProximityClusterOverride(summary.clusterId, "merge")}
                        >
                          Merge cluster
                        </Button>
                        <Button
                          size="xs"
                          color="teal"
                          variant="light"
                          leftSection={<Sparkles size={12} />}
                          loading={proximityOverrideLoading}
                          onClick={() => onProximityClusterOverride(summary.clusterId, "preserve")}
                        >
                          Preserve cluster
                        </Button>
                      </>
                    ) : null}
                  </Group>
                ))}
              </Stack>
            ) : null}
            {proximityEdges.slice(0, 5).map((edge) => (
              <Stack key={`${edge.source}:${edge.target}`} gap={2}>
                <Text size="sm" c="dimmed">
                  {titleFor(hypotheses, edge.source)} vs {titleFor(hypotheses, edge.target)}:{" "}
                  {edge.similarity.toFixed(3)}
                </Text>
                <Text size="xs" c="dimmed">
                  {edge.method ?? "lexical_token_overlap"}; {edge.cluster_id ?? "unclustered"}
                  {edge.reason ? `; ${edge.reason}` : ""}
                </Text>
                {edge.evidence_refs?.length ? (
                  <Text size="xs" c="dimmed">
                    Evidence: {edge.evidence_refs.join(", ")}
                  </Text>
                ) : null}
                {edge.deduplication_action ? (
                  <Text size="xs" c="dimmed">
                    Deduplication: {edge.deduplication_action}
                  </Text>
                ) : null}
                {edge.diversity_action ? (
                  <Text size="xs" c="dimmed">
                    Diversity: {edge.diversity_action}
                  </Text>
                ) : null}
                {onProximityOverride ? (
                  <Group gap={6} mt={4}>
                    <Button
                      size="xs"
                      variant="light"
                      leftSection={<GitMerge size={12} />}
                      loading={proximityOverrideLoading}
                      onClick={() => onProximityOverride(edge, "merge")}
                    >
                      Merge
                    </Button>
                    <Button
                      size="xs"
                      color="teal"
                      variant="light"
                      leftSection={<Sparkles size={12} />}
                      loading={proximityOverrideLoading}
                      onClick={() => onProximityOverride(edge, "preserve")}
                    >
                      Preserve
                    </Button>
                  </Group>
                ) : null}
                {edge.exploration_trace?.length ? (
                  <Stack gap={1}>
                    <Text size="xs" fw={700} c="dimmed">
                      Proximity trace
                    </Text>
                    {edge.exploration_trace.map((line) => (
                      <Text key={line} size="xs" c="dimmed">
                        {line}
                      </Text>
                    ))}
                  </Stack>
                ) : null}
              </Stack>
            ))}
          </>
        ) : (
          <EmptyText>No proximity edges recorded for this run.</EmptyText>
        )}
      </Stack>
    </Stack>
  );
}

function ClusterAssignmentControl({
  edge,
  edgeKey,
  nodeTitle,
  neighborTitle,
  clusterDrafts,
  setClusterDrafts,
  loading,
  onAssign
}: {
  edge: ProximityEdge;
  edgeKey: string;
  nodeTitle: string;
  neighborTitle: string;
  clusterDrafts: Record<string, string>;
  setClusterDrafts: (drafts: Record<string, string>) => void;
  loading: boolean;
  onAssign: (edge: ProximityEdge, clusterId: string) => void;
}) {
  const draftValue = clusterDrafts[edgeKey] ?? "";
  const trimmed = draftValue.trim();
  return (
    <>
      <TextInput
        size="xs"
        w={180}
        aria-label={`Cluster id for ${nodeTitle} and ${neighborTitle}`}
        placeholder="Cluster id"
        value={draftValue}
        onChange={(event) =>
          setClusterDrafts({
            ...clusterDrafts,
            [edgeKey]: event.currentTarget.value
          })
        }
      />
      <Button
        size="xs"
        variant="light"
        leftSection={<Database size={12} />}
        loading={loading}
        disabled={!trimmed}
        onClick={() => onAssign(edge, trimmed)}
      >
        Assign cluster
      </Button>
    </>
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
      <InsightGroup label="Agent feedback" items={agentFeedbackItems(meta.agent_feedback)} color="indigo" />
    </Paper>
  );
}

function agentFeedbackItems(agentFeedback: Record<string, string[]> | undefined): string[] {
  if (!agentFeedback) {
    return [];
  }
  return Object.keys(agentFeedback)
    .sort()
    .flatMap((agent) => agentFeedback[agent].filter(Boolean).map((item) => `${agent}: ${item}`));
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

function proximityPairKey(source: string, target: string) {
  return [source, target].sort().join(":");
}

function summarizeProximityClusters(edges: ProximityEdge[]): ProximityClusterSummary[] {
  const clusters = new Map<
    string,
    {
      hypothesisIds: Set<string>;
      edgeCount: number;
      topSimilarity: number;
      mergeCount: number;
      preserveCount: number;
    }
  >();
  for (const edge of edges) {
    const clusterId = edge.cluster_id ?? "unclustered";
    const summary =
      clusters.get(clusterId) ??
      {
        hypothesisIds: new Set<string>(),
        edgeCount: 0,
        topSimilarity: 0,
        mergeCount: 0,
        preserveCount: 0
      };
    summary.hypothesisIds.add(edge.source);
    summary.hypothesisIds.add(edge.target);
    summary.edgeCount += 1;
    summary.topSimilarity = Math.max(summary.topSimilarity, edge.similarity);
    if (edge.deduplication_action) {
      summary.mergeCount += 1;
    }
    if (edge.diversity_action === "preserve_as_diversity_candidate") {
      summary.preserveCount += 1;
    }
    clusters.set(clusterId, summary);
  }
  return [...clusters.entries()]
    .map(([clusterId, summary]) => ({
      clusterId,
      edgeCount: summary.edgeCount,
      hypothesisCount: summary.hypothesisIds.size,
      topSimilarity: summary.topSimilarity,
      mergeCount: summary.mergeCount,
      preserveCount: summary.preserveCount
    }))
    .sort((left, right) => right.topSimilarity - left.topSimilarity || left.clusterId.localeCompare(right.clusterId));
}

function summarizeProximityGraph(
  edges: ProximityEdge[],
  hypotheses: Map<string, Hypothesis>
): ProximityGraphNode[] {
  const nodes = new Map<
    string,
    {
      id: string;
      title: string;
      clusters: Set<string>;
      mergeCount: number;
      preserveCount: number;
      strongestSimilarity: number;
      neighbors: ProximityGraphNeighbor[];
    }
  >();

  function ensureNode(id: string) {
    const existing = nodes.get(id);
    if (existing) {
      return existing;
    }
    const node = {
      id,
      title: titleFor(hypotheses, id),
      clusters: new Set<string>(),
      mergeCount: 0,
      preserveCount: 0,
      strongestSimilarity: 0,
      neighbors: []
    };
    nodes.set(id, node);
    return node;
  }

  for (const edge of edges) {
    const clusterId = edge.cluster_id ?? "unclustered";
    const method = edge.method ?? "lexical_token_overlap";
    const source = ensureNode(edge.source);
    const target = ensureNode(edge.target);

    for (const node of [source, target]) {
      node.clusters.add(clusterId);
      node.strongestSimilarity = Math.max(node.strongestSimilarity, edge.similarity);
      if (edge.deduplication_action) {
        node.mergeCount += 1;
      }
      if (edge.diversity_action === "preserve_as_diversity_candidate") {
        node.preserveCount += 1;
      }
    }

    source.neighbors.push({
      id: edge.target,
      title: titleFor(hypotheses, edge.target),
      similarity: edge.similarity,
      clusterId,
      method,
      edge
    });
    target.neighbors.push({
      id: edge.source,
      title: titleFor(hypotheses, edge.source),
      similarity: edge.similarity,
      clusterId,
      method,
      edge
    });
  }

  return [...nodes.values()]
    .map((node) => ({
      id: node.id,
      title: node.title,
      degree: node.neighbors.length,
      strongestSimilarity: node.strongestSimilarity,
      clusters: [...node.clusters].sort(),
      mergeCount: node.mergeCount,
      preserveCount: node.preserveCount,
      neighbors: node.neighbors.sort(
        (left, right) => right.similarity - left.similarity || left.title.localeCompare(right.title)
      )
    }))
    .sort(
      (left, right) =>
        right.degree - left.degree ||
        right.strongestSimilarity - left.strongestSimilarity ||
        left.title.localeCompare(right.title)
    );
}

function readSchedulerDecision(task: Task): SchedulerDecisionView | null {
  const raw = task.worker_state?.scheduler_decision;
  if (!isRecord(raw)) {
    return null;
  }
  const rank = numericField(raw.rank);
  const score = numericField(raw.score) ?? task.priority;
  if (rank === null) {
    return null;
  }
  return {
    rank,
    score,
    candidateCount: numericField(raw.candidate_count) ?? 0,
    poolSize: numericField(raw.pool_size) ?? 0,
    cycle: numericField(raw.cycle) ?? undefined,
    signals: Array.isArray(raw.signals)
      ? raw.signals.filter((signal): signal is string => typeof signal === "string")
      : []
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function numericField(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function humanInfluenceForMatch(match: Match, userFeedback: UserFeedback[]) {
  const influence: string[] = [];
  const traceParts = (match.judge_trace ?? "").split(";").map((part) => part.trim());
  const manualSignal = traceParts.find((part) => part.includes("manual_review"));
  if (manualSignal) {
    influence.push(manualSignal);
  }
  for (const feedback of userFeedback) {
    if (feedback.kind !== "preference_ranking") {
      continue;
    }
    const content = feedback.content.toLowerCase();
    const mentionsMatch =
      content.includes(match.hypothesis_a.toLowerCase()) ||
      content.includes(match.hypothesis_b.toLowerCase()) ||
      feedback.target_id === match.hypothesis_a ||
      feedback.target_id === match.hypothesis_b;
    if (mentionsMatch) {
      influence.push(`${feedback.kind}: ${feedback.content}`);
    }
  }
  return influence;
}

function formatMetric(value: number) {
  return Number.isInteger(value) ? value.toString() : value.toFixed(3).replace(/0+$/, "").replace(/\.$/, "");
}

function formatDelta(value: number) {
  return `${value >= 0 ? "+" : ""}${formatMetric(value)}`;
}

function formatFixedMetric(value: number) {
  return value.toFixed(3);
}

function formatFixedDelta(value: number) {
  return `${value >= 0 ? "+" : ""}${value.toFixed(3)}`;
}

function summarizeCapabilityStudy(
  capabilityEvaluations: CapabilityEvaluation[],
  scalingCurve: ScalingCurvePoint[],
  prospectiveEvaluations: ProspectiveEvaluation[],
  feedbackLoopEvaluations: FeedbackLoopEvaluation[]
) {
  const evaluationCount = capabilityEvaluations.length;
  const baselineWinRate = rate(
    capabilityEvaluations.filter((evaluation) => evaluation.beats_baseline).length,
    evaluationCount
  );
  const meanScoreDelta = mean(
    capabilityEvaluations.map((evaluation) => evaluation.code_scientist_score - evaluation.baseline_score)
  );
  const scoreDeltas = capabilityEvaluations.map(
    (evaluation) => evaluation.code_scientist_score - evaluation.baseline_score
  );
  const scoreDeltaStddev = sampleStddev(scoreDeltas);
  const scoreDeltaStandardError = standardError(scoreDeltas);
  const scoreDeltaCiLow = scoreDeltas.length ? round3(meanScoreDelta - 1.96 * scoreDeltaStandardError) : 0;
  const scoreDeltaCiHigh = scoreDeltas.length ? round3(meanScoreDelta + 1.96 * scoreDeltaStandardError) : 0;
  const scoreDeltaEffectSize = scoreDeltaStddev > 0 ? round3(meanScoreDelta / scoreDeltaStddev) : 0;
  const baselineWinSignTestPValue = signTestPValue(scoreDeltas);
  const orderedScaling = [...scalingCurve].sort((left, right) => {
    if (left.cycles !== right.cycles) return left.cycles - right.cycles;
    if (left.task_count !== right.task_count) return left.task_count - right.task_count;
    return left.tool_budget - right.tool_budget;
  });
  const scalingDeltaTrend =
    orderedScaling.length >= 2 ? round3(orderedScaling[orderedScaling.length - 1].delta - orderedScaling[0].delta) : 0;
  const prospectiveCount = prospectiveEvaluations.length;
  const prospectiveSuccessRate = rate(
    prospectiveEvaluations.filter((evaluation) => evaluation.success).length,
    prospectiveCount
  );
  const measuredFeedbackLoops = feedbackLoopEvaluations.filter(
    (evaluation) =>
      (evaluation.measurement_status ?? "proxy") === "measured" &&
      (evaluation.measurement_source ?? "proxy") !== "proxy" &&
      Object.keys(evaluation.deltas).length > 0
  );
  const feedbackLoopMeasurementCount = measuredFeedbackLoops.length;
  const feedbackLoopMeanDelta = mean(measuredFeedbackLoops.flatMap((evaluation) => Object.values(evaluation.deltas)));
  const feedbackLoopPositiveRate = rate(
    measuredFeedbackLoops.filter((evaluation) => mean(Object.values(evaluation.deltas)) > 0).length,
    feedbackLoopMeasurementCount
  );
  return {
    evaluationCount,
    baselineWinRate,
    meanScoreDelta,
    scoreDeltaCount: scoreDeltas.length,
    scoreDeltaStddev: round3(scoreDeltaStddev),
    scoreDeltaStandardError: round3(scoreDeltaStandardError),
    scoreDeltaCiLow,
    scoreDeltaCiHigh,
    scoreDeltaEffectSize,
    baselineWinSignTestPValue,
    scalingPointCount: orderedScaling.length,
    scalingDeltaTrend,
    prospectiveCount,
    prospectiveSuccessRate,
    feedbackLoopMeasurementCount,
    feedbackLoopPositiveRate,
    feedbackLoopMeanDelta
  };
}

function rate(numerator: number, denominator: number) {
  return denominator > 0 ? round3(numerator / denominator) : 0;
}

function mean(values: number[]) {
  return values.length ? round3(values.reduce((total, value) => total + value, 0) / values.length) : 0;
}

function sampleStddev(values: number[]) {
  if (values.length < 2) return 0;
  const average = values.reduce((total, value) => total + value, 0) / values.length;
  const variance =
    values.reduce((total, value) => total + (value - average) ** 2, 0) / (values.length - 1);
  return Math.sqrt(variance);
}

function standardError(values: number[]) {
  return values.length >= 2 ? sampleStddev(values) / Math.sqrt(values.length) : 0;
}

function signTestPValue(values: number[]) {
  const nonTies = values.filter((value) => value !== 0);
  const total = nonTies.length;
  if (!total) return 1;
  const wins = nonTies.filter((value) => value > 0).length;
  const tail = Math.min(wins, total - wins);
  let probability = 0;
  for (let successes = 0; successes <= tail; successes += 1) {
    probability += combination(total, successes) / 2 ** total;
  }
  return round3(Math.min(1, 2 * probability));
}

function combination(total: number, choose: number) {
  if (choose < 0 || choose > total) return 0;
  const smallerChoose = Math.min(choose, total - choose);
  let result = 1;
  for (let index = 1; index <= smallerChoose; index += 1) {
    result = (result * (total - smallerChoose + index)) / index;
  }
  return result;
}

function round3(value: number) {
  return Math.round(value * 1000) / 1000;
}
