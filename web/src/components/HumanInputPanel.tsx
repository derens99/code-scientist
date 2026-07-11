"use client";

import { FormEvent, useEffect, useState } from "react";
import { Button, Group, Paper, Select, Slider, Stack, Switch, Tabs, Textarea, TextInput, Title } from "@mantine/core";
import { ClipboardCheck, FlaskConical, MessageSquarePlus, Settings2, ShieldCheck } from "lucide-react";
import type {
  ManualHypothesisPayload,
  ManualReviewPayload,
  RunCommandPayload,
  RunGuidancePayload,
  UserFeedbackPayload
} from "@/lib/client";
import type { Hypothesis } from "@/lib/types";

type HumanInputPanelProps = {
  goalId: string;
  goalObjective: string;
  selectedHypothesis: Hypothesis | null;
  submitting: boolean;
  goalPreferences: string[];
  goalConstraints: string[];
  goalMetrics: string[];
  goalSafetyNotes: string[];
  allowedSources: string[];
  allowedTools: string[];
  outputFormats: string[];
  terminationCriteria: string[];
  onFeedback: (payload: UserFeedbackPayload) => Promise<void>;
  onManualHypothesis: (payload: ManualHypothesisPayload) => Promise<void>;
  onManualReview: (payload: ManualReviewPayload) => Promise<void>;
  onVerificationMark: (payload: UserFeedbackPayload) => Promise<void>;
  onGuidance: (payload: RunGuidancePayload) => Promise<void>;
  onCommand: (payload: RunCommandPayload) => Promise<void>;
};

export function HumanInputPanel({
  goalId,
  goalObjective,
  selectedHypothesis,
  submitting,
  goalPreferences,
  goalConstraints,
  goalMetrics,
  goalSafetyNotes,
  allowedSources,
  allowedTools,
  outputFormats,
  terminationCriteria,
  onFeedback,
  onManualHypothesis,
  onManualReview,
  onVerificationMark,
  onGuidance,
  onCommand
}: HumanInputPanelProps) {
  const [feedbackKind, setFeedbackKind] = useState("preference");
  const [feedbackInfluence, setFeedbackInfluence] = useState("scheduler_boost");
  const [feedbackContent, setFeedbackContent] = useState("");
  const [title, setTitle] = useState("");
  const [claim, setClaim] = useState("");
  const [rationale, setRationale] = useState("");
  const [assumptions, setAssumptions] = useState("");
  const [evidenceRefs, setEvidenceRefs] = useState("");
  const [experiment, setExperiment] = useState("");
  const [metrics, setMetrics] = useState("pass_rate");
  const [successCondition, setSuccessCondition] = useState("");
  const [risks, setRisks] = useState("");
  const [decision, setDecision] = useState<ManualReviewPayload["decision"]>("revise");
  const [strengths, setStrengths] = useState("");
  const [weaknesses, setWeaknesses] = useState("");
  const [safetyNotes, setSafetyNotes] = useState("");
  const [findings, setFindings] = useState("");
  const [reviewEvidenceRefs, setReviewEvidenceRefs] = useState("");
  const [confidence, setConfidence] = useState(0.6);
  const [requiresRevision, setRequiresRevision] = useState(true);
  const [objectiveRevision, setObjectiveRevision] = useState(goalObjective);
  const [preferences, setPreferences] = useState(goalPreferences.join("\n"));
  const [constraints, setConstraints] = useState(goalConstraints.join("\n"));
  const [sourceSelection, setSourceSelection] = useState(allowedSources.join(", "));
  const [metricSelection, setMetricSelection] = useState(goalMetrics.join(", "));
  const [safetySelection, setSafetySelection] = useState(goalSafetyNotes.join("\n"));
  const [toolSelection, setToolSelection] = useState(allowedTools.join(", "));
  const [formatSelection, setFormatSelection] = useState(outputFormats.join(", "));
  const [terminationSelection, setTerminationSelection] = useState(terminationCriteria.join("\n"));
  const [followUpDirection, setFollowUpDirection] = useState("");
  const [command, setCommand] = useState("");

  useEffect(() => {
    setObjectiveRevision(goalObjective);
    setPreferences(goalPreferences.join("\n"));
    setConstraints(goalConstraints.join("\n"));
    setSourceSelection(allowedSources.join(", "));
    setMetricSelection(goalMetrics.join(", "));
    setSafetySelection(goalSafetyNotes.join("\n"));
    setToolSelection(allowedTools.join(", "));
    setFormatSelection(outputFormats.join(", "));
    setTerminationSelection(terminationCriteria.join("\n"));
  }, [
    allowedSources,
    allowedTools,
    goalConstraints,
    goalMetrics,
    goalObjective,
    goalPreferences,
    goalSafetyNotes,
    outputFormats,
    terminationCriteria
  ]);

  const feedbackKindValue = selectedHypothesis ? feedbackKind : "goal_refinement";
  const feedbackKindOptions = selectedHypothesis
    ? [
        { value: "preference", label: "Preference" },
        { value: "preference_ranking", label: "Preference ranking" },
        { value: "verification_request", label: "Verification" },
        { value: "constraint", label: "Constraint" }
      ]
    : [
        { value: "goal_refinement", label: "Goal refinement" },
        { value: "constraint", label: "Constraint" },
        { value: "preference", label: "Preference" }
      ];

  async function submitFeedback(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const targetId = selectedHypothesis?.id ?? goalId;
    if (!targetId) {
      return;
    }
    await onFeedback({
      targetId,
      kind: feedbackKindValue,
      influence: feedbackInfluence,
      content: feedbackContent
    });
    setFeedbackContent("");
  }

  async function submitHypothesis(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await onManualHypothesis({
      title,
      claim,
      rationale,
      assumptions: toList(assumptions),
      evidenceRefs: toList(evidenceRefs),
      experiment,
      metrics: toList(metrics),
      successCondition,
      risks: toList(risks)
    });
    setTitle("");
    setClaim("");
    setRationale("");
    setAssumptions("");
    setEvidenceRefs("");
    setExperiment("");
    setMetrics("pass_rate");
    setSuccessCondition("");
    setRisks("");
  }

  async function submitReview(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedHypothesis) {
      return;
    }
    await onManualReview({
      hypothesisId: selectedHypothesis.id,
      decision,
      strengths: toList(strengths),
      weaknesses: toList(weaknesses),
      safetyNotes: toList(safetyNotes),
      findings: toList(findings),
      evidenceRefs: toList(reviewEvidenceRefs),
      confidence,
      requiresRevision
    });
    setStrengths("");
    setWeaknesses("");
    setSafetyNotes("");
    setFindings("");
    setReviewEvidenceRefs("");
  }

  async function submitGuidance(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await onGuidance({
      objective: objectiveRevision,
      preferences: toList(preferences),
      constraints: toList(constraints),
      metrics: toList(metricSelection),
      safetyNotes: toList(safetySelection),
      allowedSources: toList(sourceSelection),
      allowedTools: toList(toolSelection),
      outputFormats: toList(formatSelection),
      terminationCriteria: toList(terminationSelection),
      followUpDirection
    });
    setFollowUpDirection("");
  }

  async function submitCommand(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await onCommand({ command });
    setCommand("");
  }

  async function markForVerification() {
    if (!selectedHypothesis) {
      return;
    }
    await onVerificationMark({
      targetId: selectedHypothesis.id,
      kind: "verification_request",
      influence: "scheduler_boost",
      content: `Mark ${selectedHypothesis.title} for deeper verification.`
    });
  }

  return (
    <Paper p="md" withBorder radius="sm">
      <Stack gap="md">
        <Group justify="space-between" align="center">
          <Title order={2}>Human input</Title>
          <Button
            size="xs"
            variant="light"
            leftSection={<ShieldCheck size={14} />}
            disabled={!selectedHypothesis}
            loading={submitting}
            onClick={() => void markForVerification()}
          >
            Mark for verification
          </Button>
        </Group>

        <Tabs defaultValue="feedback" keepMounted keepMountedMode="display-none">
          <Tabs.List>
            <Tabs.Tab value="feedback" leftSection={<MessageSquarePlus size={14} />}>
              Feedback
            </Tabs.Tab>
            <Tabs.Tab value="hypothesis" leftSection={<FlaskConical size={14} />}>
              Hypothesis
            </Tabs.Tab>
            <Tabs.Tab value="review" leftSection={<ClipboardCheck size={14} />}>
              Review
            </Tabs.Tab>
            <Tabs.Tab value="guidance" leftSection={<Settings2 size={14} />}>
              Guidance
            </Tabs.Tab>
            <Tabs.Tab value="command" leftSection={<MessageSquarePlus size={14} />}>
              Command
            </Tabs.Tab>
          </Tabs.List>

          <Tabs.Panel value="feedback" pt="md">
            <form onSubmit={(event) => void submitFeedback(event)}>
              <Stack gap="sm">
                <Textarea
                  label="Research objective"
                  value={objectiveRevision}
                  onChange={(event) => setObjectiveRevision(event.currentTarget.value)}
                  autosize
                  minRows={2}
                />
                <Group grow align="flex-start">
                  <Select
                    label="Kind"
                    value={feedbackKindValue}
                    onChange={(value) => setFeedbackKind(value ?? "preference")}
                    data={feedbackKindOptions}
                  />
                  <Select
                    label="Influence"
                    value={feedbackInfluence}
                    onChange={(value) => setFeedbackInfluence(value ?? "scheduler_boost")}
                    data={[
                      { value: "scheduler_boost", label: "Boost" },
                      { value: "informational", label: "Informational" },
                      { value: "scheduler_penalty", label: "Penalty" }
                    ]}
                  />
                </Group>
                <Textarea
                  label="Feedback"
                  value={feedbackContent}
                  onChange={(event) => setFeedbackContent(event.currentTarget.value)}
                  autosize
                  minRows={2}
                />
                <Button
                  type="submit"
                  leftSection={<MessageSquarePlus size={16} />}
                  disabled={!feedbackContent.trim()}
                  loading={submitting}
                >
                  {selectedHypothesis ? "Add feedback" : "Add goal refinement"}
                </Button>
              </Stack>
            </form>
          </Tabs.Panel>

          <Tabs.Panel value="hypothesis" pt="md">
            <form onSubmit={(event) => void submitHypothesis(event)}>
              <Stack gap="sm">
                <TextInput label="Title" value={title} onChange={(event) => setTitle(event.currentTarget.value)} />
                <Textarea label="Claim" value={claim} onChange={(event) => setClaim(event.currentTarget.value)} autosize minRows={2} />
                <Textarea label="Rationale" value={rationale} onChange={(event) => setRationale(event.currentTarget.value)} autosize minRows={2} />
                <Group grow align="flex-start">
                  <Textarea label="Assumptions" value={assumptions} onChange={(event) => setAssumptions(event.currentTarget.value)} autosize minRows={2} />
                  <Textarea label="Risks" value={risks} onChange={(event) => setRisks(event.currentTarget.value)} autosize minRows={2} />
                </Group>
                <TextInput label="Evidence refs" value={evidenceRefs} onChange={(event) => setEvidenceRefs(event.currentTarget.value)} />
                <Textarea label="Test experiment" value={experiment} onChange={(event) => setExperiment(event.currentTarget.value)} autosize minRows={2} />
                <Group grow align="flex-start">
                  <TextInput label="Metrics" value={metrics} onChange={(event) => setMetrics(event.currentTarget.value)} />
                  <Textarea label="Success condition" value={successCondition} onChange={(event) => setSuccessCondition(event.currentTarget.value)} autosize minRows={2} />
                </Group>
                <Button
                  type="submit"
                  leftSection={<FlaskConical size={16} />}
                  disabled={!title.trim() || !claim.trim() || !rationale.trim() || !experiment.trim() || !successCondition.trim()}
                  loading={submitting}
                >
                  Add hypothesis
                </Button>
              </Stack>
            </form>
          </Tabs.Panel>

          <Tabs.Panel value="review" pt="md">
            <form onSubmit={(event) => void submitReview(event)}>
              <Stack gap="sm">
                <Select
                  label="Decision"
                  value={decision}
                  onChange={(value) => setDecision((value as ManualReviewPayload["decision"]) ?? "revise")}
                  data={[
                    { value: "accept", label: "Accept" },
                    { value: "revise", label: "Revise" },
                    { value: "reject", label: "Reject" }
                  ]}
                />
                <Group grow align="flex-start">
                  <Textarea label="Strengths" value={strengths} onChange={(event) => setStrengths(event.currentTarget.value)} autosize minRows={2} />
                  <Textarea label="Weaknesses" value={weaknesses} onChange={(event) => setWeaknesses(event.currentTarget.value)} autosize minRows={2} />
                </Group>
                <Textarea label="Findings" value={findings} onChange={(event) => setFindings(event.currentTarget.value)} autosize minRows={2} />
                <Group grow align="flex-start">
                  <TextInput label="Evidence refs" value={reviewEvidenceRefs} onChange={(event) => setReviewEvidenceRefs(event.currentTarget.value)} />
                  <Textarea label="Safety notes" value={safetyNotes} onChange={(event) => setSafetyNotes(event.currentTarget.value)} autosize minRows={2} />
                </Group>
                <Slider
                  label={(value) => `Confidence ${value.toFixed(2)}`}
                  value={confidence}
                  min={0}
                  max={1}
                  step={0.05}
                  onChange={setConfidence}
                />
                <Switch
                  label="Requires revision"
                  checked={requiresRevision}
                  onChange={(event) => setRequiresRevision(event.currentTarget.checked)}
                />
                <Button
                  type="submit"
                  leftSection={<ClipboardCheck size={16} />}
                  disabled={!selectedHypothesis}
                  loading={submitting}
                >
                  Add review
                </Button>
              </Stack>
            </form>
          </Tabs.Panel>

          <Tabs.Panel value="guidance" pt="md">
            <form onSubmit={(event) => void submitGuidance(event)}>
              <Stack gap="sm">
                <Textarea
                  label="Preferences"
                  value={preferences}
                  onChange={(event) => setPreferences(event.currentTarget.value)}
                  autosize
                  minRows={2}
                />
                <Textarea
                  label="Constraints"
                  value={constraints}
                  onChange={(event) => setConstraints(event.currentTarget.value)}
                  autosize
                  minRows={2}
                />
                <TextInput
                  label="Allowed sources"
                  value={sourceSelection}
                  onChange={(event) => setSourceSelection(event.currentTarget.value)}
                />
                <TextInput
                  label="Metrics"
                  value={metricSelection}
                  onChange={(event) => setMetricSelection(event.currentTarget.value)}
                />
                <Textarea
                  label="Safety notes"
                  value={safetySelection}
                  onChange={(event) => setSafetySelection(event.currentTarget.value)}
                  autosize
                  minRows={2}
                />
                <TextInput
                  label="Allowed tools"
                  value={toolSelection}
                  onChange={(event) => setToolSelection(event.currentTarget.value)}
                />
                <TextInput
                  label="Output formats"
                  value={formatSelection}
                  onChange={(event) => setFormatSelection(event.currentTarget.value)}
                />
                <Textarea
                  label="Termination criteria"
                  value={terminationSelection}
                  onChange={(event) => setTerminationSelection(event.currentTarget.value)}
                  autosize
                  minRows={2}
                />
                <Textarea
                  label="Follow-up direction"
                  value={followUpDirection}
                  onChange={(event) => setFollowUpDirection(event.currentTarget.value)}
                  autosize
                  minRows={2}
                />
                <Button
                  type="submit"
                  leftSection={<Settings2 size={16} />}
                  disabled={!objectiveRevision.trim()}
                  loading={submitting}
                >
                  Update guidance
                </Button>
              </Stack>
            </form>
          </Tabs.Panel>

          <Tabs.Panel value="command" pt="md">
            <form onSubmit={(event) => void submitCommand(event)}>
              <Stack gap="sm">
                <Textarea
                  label="Command"
                  value={command}
                  onChange={(event) => setCommand(event.currentTarget.value)}
                  autosize
                  minRows={3}
                />
                <Button
                  type="submit"
                  leftSection={<MessageSquarePlus size={16} />}
                  disabled={!command.trim()}
                  loading={submitting}
                >
                  Run command
                </Button>
              </Stack>
            </form>
          </Tabs.Panel>
        </Tabs>
      </Stack>
    </Paper>
  );
}

function toList(value: string) {
  return value
    .split(/[\n,]/)
    .map((item) => item.trim())
    .filter(Boolean);
}
