"use client";

import { FormEvent, useMemo, useState } from "react";
import { Badge, Button, Group, Paper, SimpleGrid, Stack, Text, Textarea, Title } from "@mantine/core";
import { Paperclip } from "lucide-react";
import type { SourceAttachmentPayload } from "@/lib/client";
import type { Evidence, EvidenceSafetyFinding } from "@/lib/types";

export function SourceAttachmentPanel({
  submitting,
  evidence = [],
  evidenceSafetyFindings = [],
  onSourceAttachment
}: {
  submitting: boolean;
  evidence?: Evidence[];
  evidenceSafetyFindings?: EvidenceSafetyFinding[];
  onSourceAttachment: (payload: SourceAttachmentPayload) => Promise<void>;
}) {
  const [evidencePaths, setEvidencePaths] = useState("");
  const [evidenceIndexPaths, setEvidenceIndexPaths] = useState("");
  const hasPaths = useMemo(
    () => toPathList(evidencePaths).length > 0 || toPathList(evidenceIndexPaths).length > 0,
    [evidenceIndexPaths, evidencePaths]
  );
  const rejectedFindings = evidenceSafetyFindings.filter((finding) => !finding.allowed);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!hasPaths) {
      return;
    }
    await onSourceAttachment({
      evidencePaths: toPathList(evidencePaths),
      evidenceIndexPaths: toPathList(evidenceIndexPaths)
    });
  }

  return (
    <Paper component="form" onSubmit={handleSubmit} p="md" withBorder radius="sm">
      <Stack gap="sm">
        <Group justify="space-between" align="center" wrap="nowrap">
          <Title order={3}>Source attachments</Title>
        </Group>
        {evidence.length || rejectedFindings.length ? (
          <Stack gap="xs">
            <Group justify="space-between" align="center">
              <Title order={4}>Source inventory</Title>
              <Group gap={6}>
                <Badge color="green" variant="light">
                  {evidence.length} accepted
                </Badge>
                {rejectedFindings.length ? (
                  <Badge color="red" variant="light">
                    {rejectedFindings.length} rejected
                  </Badge>
                ) : null}
              </Group>
            </Group>
            {evidence.slice(0, 5).map((item) => (
              <Stack key={item.id} gap={2}>
                <Text size="sm" fw={600}>
                  {item.source}
                </Text>
                <Text size="xs" c="dimmed">
                  {item.kind}; {item.id}
                </Text>
              </Stack>
            ))}
            {rejectedFindings.length ? (
              <Stack gap={4}>
                <Text size="sm" fw={700}>
                  Rejected attachments
                </Text>
                {rejectedFindings.slice(0, 5).map((finding) => (
                  <Stack key={finding.id} gap={2}>
                    <Text size="sm">{finding.source}</Text>
                    <Text size="xs" c="dimmed">
                      {finding.flags.join(", ") || "no flags"}; {finding.reason}
                    </Text>
                  </Stack>
                ))}
              </Stack>
            ) : null}
          </Stack>
        ) : null}
        <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="sm">
          <Textarea
            label="Evidence paths"
            value={evidencePaths}
            onChange={(event) => setEvidencePaths(event.currentTarget.value)}
            minRows={2}
            autosize
          />
          <Textarea
            label="Evidence indexes"
            value={evidenceIndexPaths}
            onChange={(event) => setEvidenceIndexPaths(event.currentTarget.value)}
            minRows={2}
            autosize
          />
        </SimpleGrid>
        <Group justify="flex-end">
          <Button type="submit" leftSection={<Paperclip size={16} />} loading={submitting} disabled={!hasPaths}>
            Attach sources
          </Button>
        </Group>
      </Stack>
    </Paper>
  );
}

function toPathList(value: string) {
  return value
    .split(/[\n,]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}
