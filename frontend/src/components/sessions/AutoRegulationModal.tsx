import { useEffect, useMemo, useState } from 'react'
import { Alert, Badge, Button, Checkbox, Group, Modal, SegmentedControl, Stack, Text, Textarea } from '@mantine/core'
import { Bot, Send, Wand2 } from 'lucide-react'
import type { Exercise, Session } from '@powerlifting/types'
import { requestAutoRegulation, type AutoRegulationResponse } from '@/api/client'

type AutoRegulationMode = 'change_exercise' | 'change_weight'

interface AutoRegulationModalProps {
  opened: boolean
  onClose: () => void
  version: string
  session: Session
  sessionIndex: number
  exerciseIndex: number | null
  onApply: (proposedExercises: Exercise[], reasoningNote: string) => void | Promise<void>
}

const TOGGLES: Array<{ key: string; label: string }> = [
  { key: 'equipment_unavailable', label: 'Equipment unavailable' },
  { key: 'limited_time', label: 'Limited time' },
  { key: 'fatigue', label: 'Fatigue' },
  { key: 'pain_or_injury', label: 'Pain or injury' },
  { key: 'too_easy', label: 'Too easy' },
  { key: 'too_hard', label: 'Too hard' },
  { key: 'technique_breakdown', label: 'Technique breakdown' },
]

export default function AutoRegulationModal({
  opened,
  onClose,
  version,
  session,
  sessionIndex,
  exerciseIndex,
  onApply,
}: AutoRegulationModalProps) {
  const [mode, setMode] = useState<AutoRegulationMode>('change_weight')
  const [toggles, setToggles] = useState<Record<string, boolean>>({})
  const [message, setMessage] = useState('')
  const [conversation, setConversation] = useState<Array<{ role: 'user' | 'assistant'; content: string }>>([])
  const [response, setResponse] = useState<AutoRegulationResponse | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState('')

  const exercise = exerciseIndex !== null ? session.exercises[exerciseIndex] : null
  const activeToggleCount = useMemo(() => Object.values(toggles).filter(Boolean).length, [toggles])

  useEffect(() => {
    if (opened) {
      setMode('change_weight')
      setToggles({})
      setMessage('')
      setConversation([])
      setResponse(null)
      setError('')
    }
  }, [opened, session.id, session.date, exerciseIndex])

  const updateToggle = (key: string, checked: boolean) => {
    setToggles((prev) => ({ ...prev, [key]: checked }))
  }

  const send = async () => {
    if (exerciseIndex === null) return
    setIsLoading(true)
    setError('')
    const nextConversation = message.trim()
      ? [...conversation, { role: 'user' as const, content: message.trim() }]
      : conversation
    try {
      const result = await requestAutoRegulation(version, session.date, sessionIndex, {
        session,
        exerciseIndex,
        mode,
        toggles,
        userMessage: message.trim(),
        conversation,
      })
      setConversation([
        ...nextConversation,
        { role: 'assistant', content: result.message },
      ])
      setResponse(result)
      setMessage('')
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setIsLoading(false)
    }
  }

  const apply = async () => {
    if (!response?.proposed_exercises) return
    setIsLoading(true)
    setError('')
    try {
      await onApply(response.proposed_exercises, response.reasoning_note || response.reasoning)
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <Modal opened={opened} onClose={onClose} title="Auto-regulation" size="lg" centered>
      <Stack gap="md">
        {exercise && (
          <Group gap="xs">
            <Text fw={600}>{exercise.name || 'Exercise'}</Text>
            <Badge variant="light">{exercise.sets}x{exercise.reps}</Badge>
            {exercise.kg !== null && exercise.kg !== undefined && <Badge variant="light">{exercise.kg} kg</Badge>}
            {activeToggleCount > 0 && <Badge variant="light" color="orange">{activeToggleCount}</Badge>}
          </Group>
        )}
        {error && <Alert color="red" variant="light">{error}</Alert>}
        <SegmentedControl
          value={mode}
          onChange={(value) => setMode(value as AutoRegulationMode)}
          data={[
            { label: 'Change weight', value: 'change_weight' },
            { label: 'Change exercise', value: 'change_exercise' },
          ]}
        />
        <Stack gap={6}>
          {TOGGLES.map((toggle) => (
            <Checkbox
              key={toggle.key}
              label={toggle.label}
              checked={Boolean(toggles[toggle.key])}
              onChange={(event) => updateToggle(toggle.key, event.currentTarget.checked)}
            />
          ))}
        </Stack>
        {conversation.length > 0 && (
          <Stack gap="xs">
            {conversation.map((entry, index) => (
              <Alert
                key={`${entry.role}-${index}`}
                color={entry.role === 'assistant' ? 'blue' : 'gray'}
                variant="light"
                icon={entry.role === 'assistant' ? <Bot size={16} /> : undefined}
              >
                {entry.content}
              </Alert>
            ))}
          </Stack>
        )}
        {response?.follow_up_questions?.length ? (
          <Alert color="yellow" variant="light">
            <Stack gap={4}>
              {response.follow_up_questions.map((question) => (
                <Text key={question} size="sm">{question}</Text>
              ))}
            </Stack>
          </Alert>
        ) : null}
        {response?.status === 'ready' && response.diff.length > 0 && (
          <Alert color="green" variant="light">
            <Stack gap={4}>
              {response.diff.map((line) => (
                <Text key={line} size="sm">{line}</Text>
              ))}
            </Stack>
          </Alert>
        )}
        {response?.status === 'denied' && (
          <Alert color="orange" variant="light">{response.message}</Alert>
        )}
        <Textarea
          label="Context"
          value={message}
          onChange={(event) => setMessage(event.currentTarget.value)}
          autosize
          minRows={3}
        />
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>Cancel</Button>
          <Button variant="light" leftSection={<Send size={16} />} loading={isLoading} onClick={send}>
            Send
          </Button>
          <Button
            leftSection={<Wand2 size={16} />}
            disabled={response?.status !== 'ready' || !response.proposed_exercises}
            onClick={apply}
          >
            Apply
          </Button>
        </Group>
      </Stack>
    </Modal>
  )
}
