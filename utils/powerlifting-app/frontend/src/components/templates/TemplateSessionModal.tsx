import { useEffect, useState } from 'react'
import { ArrowDown, ArrowUp, Trash2 } from 'lucide-react'
import {
  Modal, Stack, Group, Button, TextInput, Select, Autocomplete, ActionIcon, Text, Divider,
} from '@mantine/core'
import type { TemplateSession, TemplateExercise, GlossaryExercise } from '@powerlifting/types'

interface Props {
  session: TemplateSession | null
  glossary: GlossaryExercise[]
  onSave: (session: TemplateSession) => void
  onClose: () => void
}

const LOAD_TYPE_OPTIONS = [
  { value: 'rpe', label: 'RPE' },
  { value: 'percentage', label: '%' },
  { value: 'absolute', label: 'kg' },
  { value: 'unresolvable', label: 'N/A' },
]

function blankExercise(): TemplateExercise {
  return { name: '', sets: 3, reps: 5, load_type: 'rpe', load_value: null, rpe_target: 8, notes: '', glossary_id: undefined }
}

export function TemplateSessionModal({ session, glossary, onSave, onClose }: Props) {
  const [editing, setEditing] = useState<TemplateSession | null>(null)

  useEffect(() => {
    if (session) {
      setEditing({ ...session, exercises: session.exercises.map(ex => ({ ...ex })) })
    } else {
      setEditing(null)
    }
  }, [session])

  if (!editing) return null

  const glossaryNames = Array.from(new Set(glossary.map(g => g.name)))

  function updateExercise(index: number, patch: Partial<TemplateExercise>) {
    setEditing(s => {
      if (!s) return s
      const exercises = s.exercises.map((ex, i) => i === index ? { ...ex, ...patch } : ex)
      return { ...s, exercises }
    })
  }

  function handleExerciseNameChange(index: number, value: string) {
    const match = glossary.find(g => g.name === value)
    updateExercise(index, { name: value, glossary_id: match ? match.id : undefined })
  }

  function addExercise() {
    setEditing(s => s ? { ...s, exercises: [...s.exercises, blankExercise()] } : s)
  }

  function removeExercise(index: number) {
    setEditing(s => s ? { ...s, exercises: s.exercises.filter((_, i) => i !== index) } : s)
  }

  function moveExercise(index: number, direction: -1 | 1) {
    setEditing(s => {
      if (!s) return s
      const nextIndex = index + direction
      if (nextIndex < 0 || nextIndex >= s.exercises.length) return s
      const exercises = [...s.exercises]
      const [exercise] = exercises.splice(index, 1)
      exercises.splice(nextIndex, 0, exercise)
      return { ...s, exercises }
    })
  }

  function handleSave() {
    if (editing) onSave(editing)
  }

  return (
    <Modal
      opened={session !== null}
      onClose={onClose}
      title="Edit Session"
      centered
      size="lg"
      styles={{
        content: {
          maxHeight: 'calc(var(--app-viewport-height, 100dvh) - 32px)',
          display: 'flex',
          flexDirection: 'column',
        },
        body: {
          flex: 1,
          minHeight: 0,
          overflowY: 'auto',
          overscrollBehavior: 'contain',
          paddingBottom: 'calc(var(--mantine-spacing-md) + env(safe-area-inset-bottom, 0px))',
        },
      }}
    >
      <Stack gap="md">
        <TextInput
          label="Label"
          value={editing.label}
          onChange={(e) => setEditing(s => s ? { ...s, label: e.currentTarget.value } : s)}
        />
        <Group gap="xs" grow>
          <TextInput
            type="number"
            label="Week Number"
            value={editing.week_number}
            onChange={(e) => setEditing(s => s ? { ...s, week_number: Number(e.currentTarget.value) || 1 } : s)}
          />
          <TextInput
            label="Day of Week"
            value={editing.day_of_week}
            onChange={(e) => setEditing(s => s ? { ...s, day_of_week: e.currentTarget.value } : s)}
          />
          <TextInput
            type="number"
            label="Day Index"
            value={editing.day_index}
            onChange={(e) => setEditing(s => s ? { ...s, day_index: Number(e.currentTarget.value) } : s)}
          />
        </Group>


        <Divider />

        <Text fw={500}>Exercises</Text>

        <Stack gap="sm">
          {editing.exercises.map((ex, i) => (
            <Stack key={i} gap="xs" style={{ border: '1px solid var(--mantine-color-default-border)', borderRadius: 8, padding: 12 }}>
              <Group gap="xs" align="flex-end">
                <Autocomplete
                  label="Exercise"
                  value={ex.name}
                  data={glossaryNames}
                  onChange={(val) => handleExerciseNameChange(i, val)}
                  style={{ flex: 1 }}
                />
                <Group gap={2} wrap="nowrap" style={{ marginBottom: 1 }}>
                  <ActionIcon
                    variant="subtle"
                    onClick={() => moveExercise(i, -1)}
                    disabled={i === 0}
                    title="Move exercise up"
                    aria-label="Move exercise up"
                  >
                    <ArrowUp size={16} />
                  </ActionIcon>
                  <ActionIcon
                    variant="subtle"
                    onClick={() => moveExercise(i, 1)}
                    disabled={i === editing.exercises.length - 1}
                    title="Move exercise down"
                    aria-label="Move exercise down"
                  >
                    <ArrowDown size={16} />
                  </ActionIcon>
                  <ActionIcon
                    variant="subtle"
                    color="red"
                    onClick={() => removeExercise(i)}
                    title="Remove exercise"
                    aria-label="Remove exercise"
                  >
                    <Trash2 size={16} />
                  </ActionIcon>
                </Group>
              </Group>

              <Group gap="xs" grow>
                <TextInput
                  type="number"
                  label="Sets"
                  value={ex.sets}
                  onChange={(e) => updateExercise(i, { sets: Number(e.currentTarget.value) || 1 })}
                />
                <TextInput
                  type="number"
                  label="Reps"
                  value={ex.reps}
                  onChange={(e) => updateExercise(i, { reps: Number(e.currentTarget.value) || 1 })}
                />
                <Select
                  label="Load Type"
                  value={ex.load_type}
                  onChange={(v) => updateExercise(i, { load_type: (v as TemplateExercise['load_type']) ?? 'rpe' })}
                  data={LOAD_TYPE_OPTIONS}
                  allowDeselect={false}
                />
                {ex.load_type === 'rpe' && (
                  <TextInput
                    type="number"
                    label="RPE Target"
                    value={ex.rpe_target ?? ''}
                    onChange={(e) => updateExercise(i, { rpe_target: e.currentTarget.value === '' ? null : Number(e.currentTarget.value) })}
                    step={0.5}
                  />
                )}
                {(ex.load_type === 'absolute' || ex.load_type === 'percentage') && (
                  <TextInput
                    type="number"
                    label={ex.load_type === 'absolute' ? 'Load (kg)' : 'Load (%)'}
                    value={ex.load_value ?? ''}
                    onChange={(e) => updateExercise(i, { load_value: e.currentTarget.value === '' ? null : Number(e.currentTarget.value) })}
                  />
                )}
              </Group>

              <TextInput
                label="Notes"
                value={ex.notes}
                onChange={(e) => updateExercise(i, { notes: e.currentTarget.value })}
              />
            </Stack>
          ))}
        </Stack>

        <Button variant="light" onClick={addExercise}>Add Exercise</Button>

        <Group justify="flex-end" gap="xs">
          <Button variant="default" onClick={onClose}>Cancel</Button>
          <Button onClick={handleSave}>Save Session</Button>
        </Group>
      </Stack>
    </Modal>
  )
}
