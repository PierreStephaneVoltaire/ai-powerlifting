import { useEffect, useState } from 'react'
import { Center, Loader, Modal, ScrollArea, Stack, Text } from '@mantine/core'
import type { ExercisePRRecord } from '@powerlifting/types'
import { fetchExercisePRs } from '@/api/client'
import { useSettingsStore } from '@/store/settingsStore'
import { toDisplayUnit } from '@/utils/units'

interface ExercisePRsModalProps {
  opened: boolean
  onClose: () => void
  exerciseName: string
}

export default function ExercisePRsModal({
  opened,
  onClose,
  exerciseName,
}: ExercisePRsModalProps) {
  const unit = useSettingsStore((s) => s.unit)
  const [records, setRecords] = useState<ExercisePRRecord[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const trimmed = exerciseName.trim()
    if (!opened || !trimmed) {
      setRecords([])
      setLoading(false)
      setError(null)
      return
    }
    let active = true
    setLoading(true)
    setError(null)
    fetchExercisePRs(trimmed)
      .then((data) => {
        if (!active) return
        setRecords(data)
        setLoading(false)
      })
      .catch((err) => {
        if (!active) return
        setError(err instanceof Error ? err.message : 'Failed to load PRs')
        setLoading(false)
      })
    return () => {
      active = false
    }
  }, [opened, exerciseName])

  return (
    <Modal
      opened={opened}
      onClose={onClose}
      title={`${exerciseName} PRs`}
      size="md"
      centered
      data-testid="exercise-prs-modal"
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
        ) : records.length === 0 ? (
          <Text size="sm" c="dimmed" py="sm">
            No PRs in this block.
          </Text>
        ) : (
          <Stack gap="xs">
            {records.map((record) => (
              <Text
                key={record.reps}
                size="sm"
                style={{ whiteSpace: 'nowrap' }}
              >
                {`${record.reps} × ${toDisplayUnit(record.kg, unit)}${unit} - ${record.date}`}
              </Text>
            ))}
          </Stack>
        )}
      </ScrollArea.Autosize>
    </Modal>
  )
}
