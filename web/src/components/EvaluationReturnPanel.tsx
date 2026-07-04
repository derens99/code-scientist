"use client";

import { FormEvent, useMemo, useState } from "react";
import { Badge, Button, Group, Paper, SimpleGrid, Stack, Text, Textarea, Title } from "@mantine/core";
import { Upload } from "lucide-react";
import type { EvaluationReturnPayload } from "@/lib/client";
import type { CapabilityEvaluation, FeedbackLoopEvaluation, ProspectiveEvaluation } from "@/lib/types";

export function EvaluationReturnPanel({
  submitting,
  capabilityEvaluations = [],
  prospectiveEvaluations = [],
  feedbackLoopEvaluations = [],
  onEvaluationReturn
}: {
  submitting: boolean;
  capabilityEvaluations?: CapabilityEvaluation[];
  prospectiveEvaluations?: ProspectiveEvaluation[];
  feedbackLoopEvaluations?: FeedbackLoopEvaluation[];
  onEvaluationReturn: (payload: EvaluationReturnPayload) => Promise<void>;
}) {
  const [capabilityEvaluationPaths, setCapabilityEvaluationPaths] = useState("");
  const [capabilityReviewPaths, setCapabilityReviewPaths] = useState("");
  const [preferenceReviewPaths, setPreferenceReviewPaths] = useState("");
  const [prospectiveEvaluationPaths, setProspectiveEvaluationPaths] = useState("");
  const [feedbackLoopEvaluationPaths, setFeedbackLoopEvaluationPaths] = useState("");
  const [feedbackLoopReviewPaths, setFeedbackLoopReviewPaths] = useState("");

  const hasPaths = useMemo(
    () =>
      [
        capabilityEvaluationPaths,
        capabilityReviewPaths,
        preferenceReviewPaths,
        prospectiveEvaluationPaths,
        feedbackLoopEvaluationPaths,
        feedbackLoopReviewPaths
      ].some((value) => toPathList(value).length > 0),
    [
      capabilityEvaluationPaths,
      capabilityReviewPaths,
      preferenceReviewPaths,
      prospectiveEvaluationPaths,
      feedbackLoopEvaluationPaths,
      feedbackLoopReviewPaths
    ]
  );
  const hasReturnInventory =
    capabilityEvaluations.length > 0 ||
    prospectiveEvaluations.length > 0 ||
    feedbackLoopEvaluations.length > 0;

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!hasPaths) {
      return;
    }
    await onEvaluationReturn({
      capabilityEvaluationPaths: toPathList(capabilityEvaluationPaths),
      capabilityReviewPaths: toPathList(capabilityReviewPaths),
      preferenceReviewPaths: toPathList(preferenceReviewPaths),
      prospectiveEvaluationPaths: toPathList(prospectiveEvaluationPaths),
      feedbackLoopEvaluationPaths: toPathList(feedbackLoopEvaluationPaths),
      feedbackLoopReviewPaths: toPathList(feedbackLoopReviewPaths)
    });
  }

  return (
    <Paper component="form" onSubmit={handleSubmit} p="md" withBorder radius="sm">
      <Stack gap="sm">
        <Group justify="space-between" align="center" wrap="nowrap">
          <Title order={3}>Returned evaluation packets</Title>
        </Group>
        {hasReturnInventory ? (
          <Stack gap="xs">
            <Group justify="space-between" align="center">
              <Title order={4}>Return inventory</Title>
              <Group gap={6}>
                <Badge color="blue" variant="light">
                  {countLabel(capabilityEvaluations.length, "capability")}
                </Badge>
                <Badge color="green" variant="light">
                  {countLabel(prospectiveEvaluations.length, "prospective")}
                </Badge>
                <Badge color="teal" variant="light">
                  {countLabel(feedbackLoopEvaluations.length, "feedback-loop")}
                </Badge>
              </Group>
            </Group>
            {capabilityEvaluations.slice(0, 3).map((evaluation) => (
              <Text key={evaluation.id} size="sm" c="dimmed">
                {evaluation.baseline_name}: {evaluation.summary}
              </Text>
            ))}
            {prospectiveEvaluations.slice(0, 3).map((evaluation) => (
              <Text key={evaluation.id} size="sm" c="dimmed">
                {evaluation.hypothesis_id}: {evaluation.measurement_status ?? "proxy"} via{" "}
                {evaluation.measurement_source ?? "proxy"}
              </Text>
            ))}
            {feedbackLoopEvaluations.slice(0, 3).map((evaluation) => (
              <Text key={evaluation.id} size="sm" c="dimmed">
                {evaluation.source_meta_review_id}: {evaluation.measurement_status ?? "proxy"} via{" "}
                {evaluation.measurement_source ?? "proxy"}
              </Text>
            ))}
          </Stack>
        ) : null}
        <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="sm">
          <Textarea
            label="Capability fixtures"
            value={capabilityEvaluationPaths}
            onChange={(event) => setCapabilityEvaluationPaths(event.currentTarget.value)}
            minRows={2}
            autosize
          />
          <Textarea
            label="Capability reviews"
            value={capabilityReviewPaths}
            onChange={(event) => setCapabilityReviewPaths(event.currentTarget.value)}
            minRows={2}
            autosize
          />
          <Textarea
            label="Preference reviews"
            value={preferenceReviewPaths}
            onChange={(event) => setPreferenceReviewPaths(event.currentTarget.value)}
            minRows={2}
            autosize
          />
          <Textarea
            label="Prospective validations"
            value={prospectiveEvaluationPaths}
            onChange={(event) => setProspectiveEvaluationPaths(event.currentTarget.value)}
            minRows={2}
            autosize
          />
          <Textarea
            label="Feedback-loop measurements"
            value={feedbackLoopEvaluationPaths}
            onChange={(event) => setFeedbackLoopEvaluationPaths(event.currentTarget.value)}
            minRows={2}
            autosize
          />
          <Textarea
            label="Feedback-loop reviews"
            value={feedbackLoopReviewPaths}
            onChange={(event) => setFeedbackLoopReviewPaths(event.currentTarget.value)}
            minRows={2}
            autosize
          />
        </SimpleGrid>
        <Group justify="flex-end">
          <Button type="submit" leftSection={<Upload size={16} />} loading={submitting} disabled={!hasPaths}>
            Attach returns
          </Button>
        </Group>
      </Stack>
    </Paper>
  );
}

function countLabel(count: number, label: string) {
  return `${count} ${label}`;
}

function toPathList(value: string) {
  return value
    .split(/[\n,]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}
