import { useEffect, useState } from 'react'
import { Center, Group, Loader, Modal, ScrollArea, Stack, Text } from '@mantine/core'
import { CheckCircle2, XCircle } from 'lucide-react'
import type { ExerciseHistoryEntry } from '@powerlifting/types'
import { fetchExerciseHistory } from '@/api/client'
import { useSettingsStore } from '@/store/settingsStore'
import { toDisplayUnit } from '@/utils/units'

interface ExerciseHistoryModalProps {
  opened: boolean
  onClose: () => void
  exerciseName: string
  excludeSessionId?: string
}

export default function ExerciseHistoryModal({
  opened,
  onClose,
  exerciseName,
  excludeSessionId,
}: ExerciseHistoryModalProps) {
  const unit = useSettingsStore((s) => s.unit)
  const [entries, setEntries] = useState<ExerciseHistoryEntry[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const trimmed = exerciseName.trim()
    if (!opened || !trimmed) {
      setEntries([])
      setLoading(false)
      setError(null)
      return
    }
    let active = true
    setLoading(true)
    setError(null)
    fetchExerciseHistory(trimmed, excludeSessionId)
      .then((data) => {
        if (!active) return
        setEntries(data)
        setLoading(false)
      })
      .catch((err) => {
        if (!active) return
        setError(err instanceof Error ? err.message : 'Failed to load history')
        setLoading(false)
      })
    return () => {
      active = false
    }
  }, [opened, exerciseName, excludeSessionId])

  return (
    <Modal
      opened={opened}
      onClose={onClose}
      title={`${exerciseName} History`}
      size="md"
      centered
      data-testid="exercise-history-modal"
    >
      <ScrollArea.Autosize mah={420}>
        {loading ? (
          <Center py="lg">
            <Loader size="sm" />
          </Center>
        ) : error ? (
          <Text size="sm" c="red" py="sm">
            {error}
          </Text>
        ) : entries.length === 0 ? (
          <Text size="sm" c="dimmed" py="sm">
            No previous sets in this block.
          </Text>
        ) : (
          <Stack gap="xs">
            {entries.map((entry, idx) => (
              <Group
                key={`${entry.date}-${entry.status}-${idx}`}
                wrap="nowrap"
                justify="space-between"
                gap="xs"
                style={{ whiteSpace: 'nowrap' }}
              >
                <Group wrap="nowrap" gap="xs">
                  <Text size="xs" c="dimmed" ff="monospace">
                    {entry.date}
                  </Text>
                  <Text size="sm" fw={500}>
                    {`${entry.sets}×${entry.reps ?? '?'}`}
                  </Text>
                  <Text size="sm">
                    {entry.kg !== null ? `${toDisplayUnit(entry.kg, unit)}${unit}` : '—'}
                  </Text>
                </Group>
                <span
                  className={entry.status === 'failed' ? 'if-set-dot if-set-dot-failed' : 'if-set-dot if-set-dot-completed'}
                  style={{ width: 20, height: 20, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}
                  aria-label={entry.status}
                >
                  {entry.status === 'failed' ? <XCircle size={13} /> : <CheckCircle2 size={13} />}
                </span>
              </Group>
            ))}
          </Stack>
        )}
      </ScrollArea.Autosize>
    </Modal>
  )
}
