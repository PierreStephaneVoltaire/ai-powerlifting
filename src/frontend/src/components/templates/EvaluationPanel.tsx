import React from 'react'
import { Card, Text, Stack, Group, Badge, List, Button, Loader, Textarea } from '@mantine/core'
import { AiTemplateEvaluation } from '@powerlifting/types'
import { evaluateTemplate } from '../../api/client'

interface Props {
  sk: string
  evaluation?: AiTemplateEvaluation | null
  programContext?: string
  onRefresh: () => void
  readOnly?: boolean
}

export const EvaluationPanel: React.FC<Props> = ({ sk, evaluation, programContext = '', onRefresh, readOnly = false }) => {
  const [loading, setLoading] = React.useState(false)
  const [context, setContext] = React.useState(programContext)

  React.useEffect(() => setContext(programContext), [programContext])

  const contextField = (
    <Textarea
      label="Program context"
      description="What this program is meant to do, so the analysis judges it against your intent"
      placeholder="e.g. Overreaching peak; squat, bench and deadlift each progress on their own schedule"
      value={context}
      onChange={(event) => setContext(event.currentTarget.value)}
      autosize
      minRows={2}
      maxLength={4000}
      disabled={readOnly || loading}
    />
  )

  const handleEvaluate = async () => {
    if (readOnly) return
    setLoading(true)
    try {
      await evaluateTemplate(sk, context)
      onRefresh()
    } catch (err) {
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  if (!evaluation && !loading) {
    return (
      <Card withBorder padding="lg" radius="md">
        <Stack gap="md">
          {contextField}
          <Text c="dimmed" ta="center">No evaluation available yet.</Text>
          <Button onClick={handleEvaluate} disabled={readOnly}>Generate AI Evaluation</Button>
        </Stack>
      </Card>
    )
  }

  if (loading) {
    return (
      <Card withBorder padding="lg" radius="md">
        <Stack align="center" gap="md">
          <Loader />
          <Text>AI is analyzing the program...</Text>
        </Stack>
      </Card>
    )
  }

  return (
    <Card withBorder padding="lg" radius="md">
      <Stack gap="md">
        <Group justify="space-between">
          <Text fw={700} size="lg">AI Evaluation</Text>
          <Badge color={evaluation?.stance === 'Recommended' ? 'green' : 'yellow'} size="lg">
            {evaluation?.stance || 'N/A'}
          </Badge>
        </Group>

        <Text size="sm">{evaluation?.summary}</Text>

        <Group grow align="flex-start">
          <Stack gap="xs">
            <Text fw={600} size="sm" c="green">Strengths</Text>
            <List size="xs">
              {evaluation?.strengths.map((s, i) => <List.Item key={i}>{s}</List.Item>)}
            </List>
          </Stack>
          <Stack gap="xs">
            <Text fw={600} size="sm" c="red">Weaknesses</Text>
            <List size="xs">
              {evaluation?.weaknesses.map((s, i) => <List.Item key={i}>{s}</List.Item>)}
            </List>
          </Stack>
        </Group>

        <Stack gap="xs">
          <Text fw={600} size="sm" c="blue">Suggestions</Text>
          <List size="xs">
            {evaluation?.suggestions.map((s, i) => (
              <List.Item key={i}>{s.rationale}</List.Item>
            ))}
          </List>
        </Stack>

        {contextField}
        <Button variant="subtle" size="xs" onClick={handleEvaluate} loading={loading} disabled={readOnly}>
          Re-evaluate
        </Button>
      </Stack>
    </Card>
  )
}
