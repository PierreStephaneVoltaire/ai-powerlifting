import { useEffect, useState } from 'react'
import { ArrowDown, ArrowUp, Trash2 } from 'lucide-react'
import {
  Modal, Stack, Group, Button, TextInput, Select, Autocomplete, ActionIcon, Text, Divider, SegmentedControl,
} from '@mantine/core'
import type { TemplateSession, TemplateExercise, GlossaryExercise } from '@powerlifting/types'
import DraftNumberInput from '@/components/sessions/DraftNumberInput'
import { changePrescription, prescriptionMode, type PrescriptionMode } from '@/utils/prescriptionUnit'

interface Props {
  session: TemplateSession | null
  glossary: GlossaryExercise[]
  onSave: (session: TemplateSession) => void
  onClose: () => void
  disabled?: boolean
}

const LOAD_TYPE_OPTIONS = [
  { value: 'rpe', label: 'RPE' },
  { value: 'percentage', label: '%' },
  { value: 'absolute', label: 'kg' },
  { value: 'unresolvable', label: 'N/A' },
]

function blankExercise(): TemplateExercise {
  return { name: '', sets: 3, reps: 5, load_type: 'rpe', load_value: 8, rpe_target: 8, notes: '' }
}

export function TemplateSessionModal({ session, glossary, onSave, onClose, disabled }: Props) {
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
          onChange={(e) => { const raw = e.currentTarget.value; setEditing(s => s ? { ...s, label: raw } : s) }}
          disabled={disabled}
        />
        <Group gap="xs" grow>
          <TextInput
            type="number"
            label="Week Number"
            value={editing.week_number}
            onChange={(e) => { const raw = e.currentTarget.value; setEditing(s => s ? { ...s, week_number: Number(raw) || 1 } : s) }}
            disabled={disabled}
          />
          <TextInput
            label="Day of Week"
            value={editing.day_of_week}
            onChange={(e) => { const raw = e.currentTarget.value; setEditing(s => s ? { ...s, day_of_week: raw } : s) }}
            disabled={disabled}
          />
          <TextInput
            type="number"
            label="Day Index"
            value={editing.day_index}
            onChange={(e) => { const raw = e.currentTarget.value; setEditing(s => s ? { ...s, day_index: Number(raw) } : s) }}
            disabled={disabled}
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
                  disabled={disabled}
                />
                <Group gap={2} wrap="nowrap" style={{ marginBottom: 1 }}>
                  <ActionIcon
                    variant="subtle"
                    onClick={() => moveExercise(i, -1)}
                    disabled={i === 0 || disabled}
                    title="Move exercise up"
                    aria-label="Move exercise up"
                  >
                    <ArrowUp size={16} />
                  </ActionIcon>
                  <ActionIcon
                    variant="subtle"
                    onClick={() => moveExercise(i, 1)}
                    disabled={i === editing.exercises.length - 1 || disabled}
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
                    disabled={disabled}
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
                  disabled={disabled}
                />
                <Stack gap={4} style={{ flex: 1 }}>
                  <Text size="sm" fw={500}>Prescription</Text>
                  <SegmentedControl
                    value={prescriptionMode(ex)}
                    data={[{ label: 'Reps', value: 'reps' }, { label: 'AMRAP', value: 'amrap' }, { label: 'Minutes', value: 'minutes' }, { label: 'Seconds', value: 'seconds' }]}
                    onChange={(value) => {
                      const next = value as PrescriptionMode
                      const timed = next === 'minutes' || next === 'seconds'
                      updateExercise(i, {
                        ...changePrescription(ex, next),
                        ...(timed && ex.load_type === 'unresolvable' ? { load_type: 'duration' } : {}),
                        ...(!timed && ex.load_type === 'duration' ? { load_type: 'rpe', load_value: 8, rpe_target: 8 } : {}),
                      })
                    }}
                    disabled={disabled}
                    size="xs"
                  />
                  {prescriptionMode(ex) !== 'amrap' ? (
                    <DraftNumberInput
                      label={prescriptionMode(ex) === 'reps' ? 'Reps' : prescriptionMode(ex) === 'minutes' ? 'Minutes' : 'Seconds'}
                      value={ex.reps == null && ex.duration_minutes == null ? null : Number(ex.reps ?? ex.duration_minutes)}
                      isValid={(value) => value > 0 && (prescriptionMode(ex) !== 'reps' || Number.isInteger(value))}
                      nullable={false}
                      commitOnlyValid
                      preservePrecision
                      onValueChange={(value) => value != null && updateExercise(i, { reps: value, duration_minutes: undefined, rep_unit: prescriptionMode(ex) === 'seconds' ? 'seconds' : prescriptionMode(ex) === 'minutes' ? 'minutes' : 'reps' })}
                      disabled={disabled}
                    />
                  ) : <Text size="sm">As many reps as possible</Text>}
                </Stack>
                <Select
                  label="Load Type"
                  value={ex.load_type}
                  onChange={(v) => {
                    const mode = (v as TemplateExercise['load_type']) ?? 'rpe'
                    const target = mode === 'rpe' ? ex.rpe_target ?? 8 : null
                    updateExercise(i, { load_type: mode, rpe_target: target, load_value: target })
                  }}
                  data={prescriptionMode(ex) === 'minutes' || prescriptionMode(ex) === 'seconds' ? [...LOAD_TYPE_OPTIONS, { value: 'duration', label: 'Duration' }] : LOAD_TYPE_OPTIONS}
                  allowDeselect={false}
                  disabled={disabled}
                />
                {ex.load_type === 'rpe' && (
                  <TextInput
                    type="number"
                    label="RPE Target"
                    value={ex.rpe_target ?? ''}
                    onChange={(e) => {
                      const rpe = e.currentTarget.value === '' ? null : Number(e.currentTarget.value)
                      updateExercise(i, { rpe_target: rpe, load_value: rpe })
                    }}
                    step={0.5}
                    disabled={disabled}
                  />
                )}
                {(ex.load_type === 'absolute' || ex.load_type === 'percentage') && (
                  <TextInput
                    type="number"
                    label={ex.load_type === 'absolute' ? 'Load (kg)' : 'Load (%)'}
                    value={ex.load_value ?? ''}
                    onChange={(e) => updateExercise(i, { load_value: e.currentTarget.value === '' ? null : Number(e.currentTarget.value) })}
                    disabled={disabled}
                  />
                )}
              </Group>

              <TextInput
                label="Notes"
                value={ex.notes}
                onChange={(e) => updateExercise(i, { notes: e.currentTarget.value })}
                disabled={disabled}
              />
            </Stack>
          ))}
        </Stack>

        <Button variant="light" onClick={addExercise} disabled={disabled}>Add Exercise</Button>

        <Group justify="flex-end" gap="xs">
          <Button variant="default" onClick={onClose}>Cancel</Button>
          <Button onClick={handleSave} disabled={disabled}>Save Session</Button>
        </Group>
      </Stack>
    </Modal>
  )
}
