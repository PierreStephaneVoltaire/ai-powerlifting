import { useState, useMemo } from 'react'
import { Link } from 'react-router-dom'
import { Plus, Edit2, Trash2, X, Save, ExternalLink } from 'lucide-react'
import { useProgramStore } from '@/store/programStore'
import { useAuth } from '@/auth/AuthProvider'
import { useUiStore } from '@/store/uiStore'
import { phaseColor } from '@/utils/phases'
import {
  Paper, Text, Group, Stack, SimpleGrid, Button, ActionIcon,
  TextInput, Textarea, Modal, Box, Select,
} from '@mantine/core'
import type { Phase } from '@powerlifting/types'

const DEFAULT_BLOCK = 'current'

export default function DesignerPhases() {
  const { readOnly } = useAuth()
  const { program, updatePhases } = useProgramStore()
  const { pushToast } = useUiStore()

  const allPhases = program?.phases || []
  const [selectedBlock, setSelectedBlock] = useState<string>(DEFAULT_BLOCK)

  const blockOptions = useMemo(() => {
    const blocks = new Set<string>([DEFAULT_BLOCK])
    for (const p of allPhases) blocks.add(p.block ?? DEFAULT_BLOCK)
    for (const s of program?.sessions ?? []) blocks.add(s.block ?? DEFAULT_BLOCK)
    return Array.from(blocks).map(b => ({ value: b, label: b }))
  }, [allPhases, program?.sessions])

  const phases = useMemo(
    () => allPhases.filter(p => (p.block ?? DEFAULT_BLOCK) === selectedBlock),
    [allPhases, selectedBlock]
  )

  const [editingPhase, setEditingPhase] = useState<Phase | null>(null)
  const [editingPhaseIndex, setEditingPhaseIndex] = useState<number>(-1)
  const [isNewPhase, setIsNewPhase] = useState(false)
  const [phaseForm, setPhaseForm] = useState<Partial<Phase>>({
    name: '',
    intent: '',
    start_week: 1,
    end_week: 4,
    target_rpe_min: 6,
    target_rpe_max: 8,
    days_per_week: 4,
    notes: '',
  })

  const totalWeeks = useMemo(() => {
    if (!phases.length) return 12
    return Math.max(...phases.map(p => p.end_week))
  }, [phases])

  function openPhaseEditor(phase?: Phase, index?: number) {
    if (phase && index !== undefined) {
      setEditingPhase(phase)
      setEditingPhaseIndex(index)
      setIsNewPhase(false)
      setPhaseForm({ ...phase })
    } else {
      setEditingPhase(null)
      setEditingPhaseIndex(-1)
      setIsNewPhase(true)
      setPhaseForm({
        name: '',
        intent: '',
        start_week: totalWeeks + 1,
        end_week: totalWeeks + 4,
        target_rpe_min: 6,
        target_rpe_max: 8,
        days_per_week: 4,
        notes: '',
      })
    }
  }

  function closePhaseEditor() {
    setEditingPhase(null)
    setEditingPhaseIndex(-1)
    setIsNewPhase(false)
  }

  async function savePhase() {
    const updatedPhases = [...phases]
    const phaseData: Phase = {
      name: phaseForm.name || 'Unnamed',
      intent: phaseForm.intent || '',
      start_week: phaseForm.start_week || 1,
      end_week: phaseForm.end_week || 4,
      target_rpe_min: phaseForm.target_rpe_min,
      target_rpe_max: phaseForm.target_rpe_max,
      days_per_week: phaseForm.days_per_week,
      notes: phaseForm.notes,
      block: selectedBlock,
    }

    const overlaps = updatedPhases.some((phase, idx) => {
      if (idx === editingPhaseIndex) return false
      return !(phaseData.end_week < phase.start_week || phaseData.start_week > phase.end_week)
    })

    if (overlaps) {
      pushToast({ message: 'Phase weeks overlap another phase', type: 'error' })
      return
    }

    if (editingPhaseIndex >= 0) {
      updatedPhases[editingPhaseIndex] = phaseData
    } else {
      updatedPhases.push(phaseData)
    }

    updatedPhases.sort((a, b) => a.start_week - b.start_week)

    await updatePhases(updatedPhases, selectedBlock)
    closePhaseEditor()
  }

  async function deletePhase(name: string) {
    if (!confirm(`Delete phase "${name}"?`)) return
    const updatedPhases = phases.filter(p => p.name !== name)
    await updatePhases(updatedPhases, selectedBlock)
  }

  return (
    <Stack gap="md" className="if-mock-page">
      <Group justify="space-between" className="if-mock-header">
        <Group gap="xs">
          <Text component={Link} to="/designer" size="sm" c="dimmed" style={{ textDecoration: 'none' }}>
            Designer
          </Text>
          <Text c="dimmed">/</Text>
          <h1 className="if-mock-title">Phase Design</h1>
        </Group>
        <Group gap="xs">
          <Select
            size="sm"
            value={selectedBlock}
            onChange={(v) => setSelectedBlock(v || DEFAULT_BLOCK)}
            data={blockOptions}
            allowDeselect={false}
            style={{ width: 160 }}
            aria-label="Block"
          />
          <Button
            size="sm"
            leftSection={<Plus size={16} />}
            onClick={() => openPhaseEditor()}
            disabled={readOnly}
          >
            Add Phase
          </Button>
        </Group>
      </Group>

      {phases.length > 0 ? (
        <Stack gap="sm">
          {phases.map((phase, i) => (
            <Paper key={phase.name} withBorder p={0} className="if-card">
              <Box p="14px 16px">
              <Group justify="space-between" wrap="nowrap">
                <Box style={{ background: phaseColor(phase, phases), borderRadius: '50%', flexShrink: 0, height: 10, marginTop: 6, width: 10 }} />
                <Box style={{ flex: 1, minWidth: 0 }}>
                  <Text fw={500}>{phase.name}</Text>
                  <Text size="sm" c="dimmed">
                    W{phase.start_week} - W{phase.end_week}
                    {phase.target_rpe_min && phase.target_rpe_max && (
                      <> &middot; RPE {phase.target_rpe_min}-{phase.target_rpe_max}</>
                    )}
                    {phase.days_per_week && <> &middot; {phase.days_per_week}x/week</>}
                  </Text>
                  {phase.intent && (
                    <Text size="sm" c="dimmed" mt={4}>{phase.intent}</Text>
                  )}
                </Box>
                <Group gap="xs" wrap="nowrap">
                  <Button
                    component={Link}
                    to={`/designer/sessions?week=${phase.start_week}`}
                    variant="light"
                    size="xs"
                    leftSection={<ExternalLink size={12} />}
                  >
                    Sessions
                  </Button>
                  <ActionIcon
                    variant="subtle"
                    onClick={() => openPhaseEditor(phase, i)}
                    disabled={readOnly}
                  >
                    <Edit2 size={16} />
                  </ActionIcon>
                  <ActionIcon
                    variant="subtle"
                    color="red"
                    onClick={() => deletePhase(phase.name)}
                    disabled={readOnly}
                  >
                    <Trash2 size={16} />
                  </ActionIcon>
                </Group>
                </Group>
              </Box>
            </Paper>
          ))}
        </Stack>
      ) : (
        <Box ta="center" py={48}>
          <Text c="dimmed">No phases defined. Click &quot;Add Phase&quot; to get started.</Text>
        </Box>
      )}

      {/* Phase Editor Modal */}
      <Modal
        opened={editingPhase !== null || isNewPhase}
        onClose={closePhaseEditor}
        title={isNewPhase ? 'Add Phase' : 'Edit Phase'}
        centered
      >
        <Stack gap="md">
          <Box>
            <Text size="sm" c="dimmed" mb={4}>Name</Text>
            <TextInput
              value={phaseForm.name || ''}
              onChange={(e) => {
                const val = e.currentTarget.value;
                setPhaseForm(p => ({ ...p, name: val }));
              }}
              size="sm"
              disabled={readOnly}
            />
          </Box>

          <SimpleGrid cols={2} spacing="md">
            <Box>
              <Text size="sm" c="dimmed" mb={4}>Start Week</Text>
              <TextInput
                type="number"
                value={phaseForm.start_week || 1}
                onChange={(e) => setPhaseForm(p => ({ ...p, start_week: Number(e.currentTarget.value) }))}
                size="sm"
                disabled={readOnly}
              />
            </Box>
            <Box>
              <Text size="sm" c="dimmed" mb={4}>End Week</Text>
              <TextInput
                type="number"
                value={phaseForm.end_week || 4}
                onChange={(e) => setPhaseForm(p => ({ ...p, end_week: Number(e.currentTarget.value) }))}
                size="sm"
                disabled={readOnly}
              />
            </Box>
          </SimpleGrid>

          <Box>
            <Text size="sm" c="dimmed" mb={4}>Intent</Text>
            <Textarea
              value={phaseForm.intent || ''}
              onChange={(e) => {
                const val = e.currentTarget.value;
                setPhaseForm(p => ({ ...p, intent: val }));
              }}
              autosize
              minRows={2}
              size="sm"
              disabled={readOnly}
            />
          </Box>

          <SimpleGrid cols={3} spacing="md">
            <Box>
              <Text size="sm" c="dimmed" mb={4}>RPE Min</Text>
              <TextInput
                type="number"
                value={phaseForm.target_rpe_min ?? ''}
                onChange={(e) => setPhaseForm(p => ({ ...p, target_rpe_min: e.currentTarget.value === '' ? undefined : Number(e.currentTarget.value) }))}
                size="sm"
                step={0.5}
                disabled={readOnly}
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
                disabled={readOnly}
              />
            </Box>
            <Box>
              <Text size="sm" c="dimmed" mb={4}>Days/Wk</Text>
              <TextInput
                type="number"
                value={phaseForm.days_per_week ?? ''}
                onChange={(e) => setPhaseForm(p => ({ ...p, days_per_week: e.currentTarget.value === '' ? undefined : Number(e.currentTarget.value) }))}
                size="sm"
                disabled={readOnly}
              />
            </Box>
          </SimpleGrid>

          <Box>
            <Text size="sm" c="dimmed" mb={4}>Notes</Text>
            <Textarea
              value={phaseForm.notes || ''}
              onChange={(e) => {
                const val = e.currentTarget.value;
                setPhaseForm(p => ({ ...p, notes: val }));
              }}
              autosize
              minRows={2}
              size="sm"
              disabled={readOnly}
            />
          </Box>

          <Group justify="flex-end" gap="xs">
            <Button variant="default" onClick={closePhaseEditor}>
              Cancel
            </Button>
            <Button
              leftSection={<Save size={16} />}
              onClick={savePhase}
              disabled={readOnly}
            >
              {isNewPhase ? 'Add' : 'Update'} Phase
            </Button>
          </Group>
        </Stack>
      </Modal>
    </Stack>
  )
}
