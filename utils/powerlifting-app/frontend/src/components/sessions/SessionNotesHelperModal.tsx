import { useEffect, useState } from 'react'
import { Alert, Button, Group, Modal, Stack, Textarea } from '@mantine/core'
import { Wand2 } from 'lucide-react'
import type { Session } from '@powerlifting/types'
import { draftSessionNotes } from '@/api/client'

interface SessionNotesHelperModalProps {
  opened: boolean
  onClose: () => void
  version: string
  session: Session
  sessionIndex: number
  onInsert: (notes: string) => void
}

const emptyAnswers = {
  overall: '',
  technique: '',
  failedSets: '',
  skippedWork: '',
  rpeMismatch: '',
  plannedVsExecuted: '',
  freeText: '',
}

export default function SessionNotesHelperModal({
  opened,
  onClose,
  version,
  session,
  sessionIndex,
  onInsert,
}: SessionNotesHelperModalProps) {
  const [answers, setAnswers] = useState(emptyAnswers)
  const [draft, setDraft] = useState('')
  const [error, setError] = useState('')
  const [isGenerating, setIsGenerating] = useState(false)

  useEffect(() => {
    if (opened) {
      setAnswers(emptyAnswers)
      setDraft('')
      setError('')
    }
  }, [opened, session.id, session.date])

  const updateAnswer = (field: keyof typeof emptyAnswers, value: string) => {
    setAnswers((prev) => ({ ...prev, [field]: value }))
  }

  const generateDraft = async () => {
    setIsGenerating(true)
    setError('')
    try {
      const result = await draftSessionNotes(version, session.date, sessionIndex, {
        session,
        answers,
      })
      setDraft(result.notes)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setIsGenerating(false)
    }
  }

  const insertDraft = () => {
    onInsert(draft)
    onClose()
  }

  return (
    <Modal opened={opened} onClose={onClose} title="Help write session notes" size="lg" centered>
      <Stack gap="sm">
        {error && <Alert color="red" variant="light">{error}</Alert>}
        <Textarea
          label="Overall"
          value={answers.overall}
          onChange={(event) => updateAnswer('overall', event.currentTarget.value)}
          autosize
          minRows={2}
        />
        <Textarea
          label="Technique consistency"
          value={answers.technique}
          onChange={(event) => updateAnswer('technique', event.currentTarget.value)}
          autosize
          minRows={2}
        />
        <Textarea
          label="Failed sets or RPE"
          value={answers.failedSets}
          onChange={(event) => updateAnswer('failedSets', event.currentTarget.value)}
          autosize
          minRows={2}
        />
        <Textarea
          label="Skipped or missed work"
          value={answers.skippedWork}
          onChange={(event) => updateAnswer('skippedWork', event.currentTarget.value)}
          autosize
          minRows={2}
        />
        <Textarea
          label="Load mismatch"
          value={answers.rpeMismatch}
          onChange={(event) => updateAnswer('rpeMismatch', event.currentTarget.value)}
          autosize
          minRows={2}
        />
        <Textarea
          label="Planned vs executed"
          value={answers.plannedVsExecuted}
          onChange={(event) => updateAnswer('plannedVsExecuted', event.currentTarget.value)}
          autosize
          minRows={2}
        />
        <Textarea
          label="Other"
          value={answers.freeText}
          onChange={(event) => updateAnswer('freeText', event.currentTarget.value)}
          autosize
          minRows={2}
        />
        {draft && (
          <Textarea
            label="Draft"
            value={draft}
            onChange={(event) => setDraft(event.currentTarget.value)}
            autosize
            minRows={4}
          />
        )}
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>Cancel</Button>
          <Button variant="light" leftSection={<Wand2 size={16} />} loading={isGenerating} onClick={generateDraft}>
            Draft Notes
          </Button>
          <Button disabled={!draft.trim()} onClick={insertDraft}>
            Insert
          </Button>
        </Group>
      </Stack>
    </Modal>
  )
}
