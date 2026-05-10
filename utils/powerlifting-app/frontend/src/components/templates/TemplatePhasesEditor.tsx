import { useState } from 'react'
import { Plus, Edit2, Trash2, Save } from 'lucide-react'
import {
  Stack, Group, Title, Text, Paper, Box, Button, ActionIcon,
  Modal, TextInput, Textarea, SimpleGrid,
} from '@mantine/core'
import type { TemplatePhase } from '@powerlifting/types'

interface Props {
  phases: TemplatePhase[]
  onChange: (phases: TemplatePhase[]) => void
}

const EMPTY_FORM: Partial<TemplatePhase> = {
  name: '',
  week_start: 1,
  week_end: 4,
  target_rpe_min: undefined,
  target_rpe_max: undefined,
  intent: '',
}

export function TemplatePhasesEditor({ phases, onChange }: Props) {
  const [phaseForm, setPhaseForm] = useState<Partial<TemplatePhase>>(EMPTY_FORM)
  const [editingIndex, setEditingIndex] = useState<number>(-1)
  const [isNew, setIsNew] = useState(false)

  function openPhaseEditor(phase?: TemplatePhase, index?: number) {
    if (phase && index !== undefined) {
      setPhaseForm({ ...phase })
      setEditingIndex(index)
      setIsNew(false)
    } else {
      const nextStart = phases.length ? Math.max(...phases.map(p => p.week_end)) + 1 : 1
      setPhaseForm({ ...EMPTY_FORM, week_start: nextStart, week_end: nextStart + 3 })
      setEditingIndex(-1)
      setIsNew(true)
    }
  }

  function closePhaseEditor() {
    setEditingIndex(-1)
    setIsNew(false)
  }

  function savePhase() {
    const phaseData: TemplatePhase = {
      name: phaseForm.name || 'Unnamed',
      week_start: phaseForm.week_start || 1,
      week_end: phaseForm.week_end || 4,
      target_rpe_min: phaseForm.target_rpe_min,
      target_rpe_max: phaseForm.target_rpe_max,
      intent: phaseForm.intent || '',
    }
    const updated = [...phases]
    if (editingIndex >= 0) {
      updated[editingIndex] = phaseData
    } else {
      updated.push(phaseData)
    }
    updated.sort((a, b) => a.week_start - b.week_start)
    onChange(updated)
    closePhaseEditor()
  }

  function deletePhase(name: string) {
    if (!confirm(`Delete phase "${name}"?`)) return
    onChange(phases.filter(p => p.name !== name))
  }

  return (
    <Stack gap="md">
      <Group justify="flex-end">
        <Button size="sm" leftSection={<Plus size={16} />} onClick={() => openPhaseEditor()}>
          Add Phase
        </Button>
      </Group>

      {phases.length > 0 ? (
        <Stack gap="sm">
          {phases.map((phase, i) => (
            <Paper key={phase.name} withBorder p="md">
              <Group justify="space-between" wrap="nowrap">
                <Box style={{ flex: 1, minWidth: 0 }}>
                  <Text fw={500}>{phase.name}</Text>
                  <Text size="sm" c="dimmed">
                    W{phase.week_start} - W{phase.week_end}
                    {phase.target_rpe_min != null && phase.target_rpe_max != null && (
                      <> &middot; RPE {phase.target_rpe_min}-{phase.target_rpe_max}</>
                    )}
                  </Text>
                  {phase.intent && (
                    <Text size="sm" c="dimmed" mt={4}>{phase.intent}</Text>
                  )}
                </Box>
                <Group gap="xs" wrap="nowrap">
                  <ActionIcon variant="subtle" onClick={() => openPhaseEditor(phase, i)}>
                    <Edit2 size={16} />
                  </ActionIcon>
                  <ActionIcon variant="subtle" color="red" onClick={() => deletePhase(phase.name)}>
                    <Trash2 size={16} />
                  </ActionIcon>
                </Group>
              </Group>
            </Paper>
          ))}
        </Stack>
      ) : (
        <Box ta="center" py={32}>
          <Text c="dimmed">No phases defined. Click &quot;Add Phase&quot; to get started.</Text>
        </Box>
      )}

      <Modal
        opened={isNew || editingIndex >= 0}
        onClose={closePhaseEditor}
        title={isNew ? 'Add Phase' : 'Edit Phase'}
        centered
      >
        <Stack gap="md">
          <Box>
            <Text size="sm" c="dimmed" mb={4}>Name</Text>
            <TextInput
              value={phaseForm.name || ''}
              onChange={(e) => { const val = e.currentTarget.value; setPhaseForm(p => ({ ...p, name: val })) }}
              size="sm"
            />
          </Box>

          <SimpleGrid cols={2} spacing="md">
            <Box>
              <Text size="sm" c="dimmed" mb={4}>Week Start</Text>
              <TextInput
                type="number"
                value={phaseForm.week_start || 1}
                onChange={(e) => setPhaseForm(p => ({ ...p, week_start: Number(e.currentTarget.value) || 1 }))}
                size="sm"
              />
            </Box>
            <Box>
              <Text size="sm" c="dimmed" mb={4}>Week End</Text>
              <TextInput
                type="number"
                value={phaseForm.week_end || 4}
                onChange={(e) => setPhaseForm(p => ({ ...p, week_end: Number(e.currentTarget.value) || 1 }))}
                size="sm"
              />
            </Box>
          </SimpleGrid>

          <SimpleGrid cols={2} spacing="md">
            <Box>
              <Text size="sm" c="dimmed" mb={4}>RPE Min</Text>
              <TextInput
                type="number"
                value={phaseForm.target_rpe_min ?? ''}
                onChange={(e) => setPhaseForm(p => ({ ...p, target_rpe_min: e.currentTarget.value === '' ? undefined : Number(e.currentTarget.value) }))}
                size="sm"
                step={0.5}
              />
            </Box>
            <Box>
              <Text size="sm" c="dimmed" mb={4}>RPE Max</Text>
              <TextInput
                type="number"
                value={phaseForm.target_rpe_max ?? ''}
                onChange={(e) => setPhaseForm(p => ({ ...p, target_rpe_max: e.currentTarget.value === '' ? undefined : Number(e.currentTarget.value) }))}
                size="sm"
                step={0.5}
              />
            </Box>
          </SimpleGrid>

          <Box>
            <Text size="sm" c="dimmed" mb={4}>Intent</Text>
            <Textarea
              value={phaseForm.intent || ''}
              onChange={(e) => { const val = e.currentTarget.value; setPhaseForm(p => ({ ...p, intent: val })) }}
              autosize
              minRows={2}
              size="sm"
            />
          </Box>

          <Group justify="flex-end" gap="xs">
            <Button variant="default" onClick={closePhaseEditor}>Cancel</Button>
            <Button leftSection={<Save size={16} />} onClick={savePhase}>
              {isNew ? 'Add' : 'Update'} Phase
            </Button>
          </Group>
        </Stack>
      </Modal>
    </Stack>
  )
}
