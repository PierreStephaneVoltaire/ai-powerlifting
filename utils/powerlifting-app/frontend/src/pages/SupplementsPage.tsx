import { useState, useEffect, useMemo } from 'react'
import { Plus, X, Trash2, Edit2, Save } from 'lucide-react'
import {
  Stack, Group, Text, Button, Paper, Badge, SimpleGrid,
  TextInput, Textarea, Select, ActionIcon, Accordion, Table,
} from '@mantine/core'
import { useProgramStore } from '@/store/programStore'
import { useUiStore } from '@/store/uiStore'
import { useAuth } from '@/auth/AuthProvider'
import type { SupplementPhase, Supplement } from '@powerlifting/types'

export default function SupplementsPage() {
  const { readOnly } = useAuth()
  const { program, updateSupplementPhases } = useProgramStore()
  const { pushToast } = useUiStore()
  const [phases, setPhases] = useState<SupplementPhase[]>([])
  const [hasChanges, setHasChanges] = useState(false)
  const [expandedPhase, setExpandedPhase] = useState<number | null>(null)
  const [editingPhase, setEditingPhase] = useState<number | null>(null)
  const [block, setBlock] = useState('current')

  const availableBlocks = useMemo(() => {
    if (!program) return ['current']
    const blocks = new Set<string>()
    for (const s of program.sessions) blocks.add(s.block ?? 'current')
    return Array.from(blocks).sort()
  }, [program])

  const blockWeeks = useMemo(() => {
    if (!program) return []
    const weeks = new Set<number>()
    for (const s of program.sessions) {
      if ((s.block ?? 'current') === block) weeks.add(s.week_number)
    }
    return Array.from(weeks).sort((a, b) => a - b)
  }, [program, block])

  const filteredPhases = useMemo(
    () => phases.filter(p => (p.block ?? 'current') === block),
    [phases, block]
  )

  useEffect(() => {
    if (program?.supplement_phases) {
      setPhases(program.supplement_phases)
    }
  }, [program])

  function updatePhase(index: number, updates: Partial<SupplementPhase>) {
    setPhases((prev) => {
      const newPhases = [...prev]
      newPhases[index] = { ...newPhases[index], ...updates }
      return newPhases
    })
    setHasChanges(true)
  }

  function updateItem(phaseIndex: number, itemIndex: number, updates: Partial<Supplement & { notes?: string }>) {
    setPhases((prev) => {
      const newPhases = [...prev]
      const items = [...newPhases[phaseIndex].items]
      items[itemIndex] = { ...items[itemIndex], ...updates }
      newPhases[phaseIndex] = { ...newPhases[phaseIndex], items }
      return newPhases
    })
    setHasChanges(true)
  }

  function addItem(phaseIndex: number) {
    setPhases((prev) => {
      const newPhases = [...prev]
      const items = [...newPhases[phaseIndex].items, { name: '', dose: '' }]
      newPhases[phaseIndex] = { ...newPhases[phaseIndex], items }
      return newPhases
    })
    setHasChanges(true)
  }

  function removeItem(phaseIndex: number, itemIndex: number) {
    setPhases((prev) => {
      const newPhases = [...prev]
      const items = newPhases[phaseIndex].items.filter((_, i) => i !== itemIndex)
      newPhases[phaseIndex] = { ...newPhases[phaseIndex], items }
      return newPhases
    })
    setHasChanges(true)
  }

  function addPhase() {
    const maxPhase = phases.reduce((max, p) => Math.max(max, p.phase), 0)
    setPhases((prev) => [
      ...prev,
      {
        phase: maxPhase + 1,
        phase_name: `Phase ${maxPhase + 1}`,
        notes: '',
        items: [],
        block: block,
      },
    ])
    setHasChanges(true)
  }

  function removePhase(index: number) {
    if (!confirm('Delete this phase?')) return
    setPhases((prev) => prev.filter((_, i) => i !== index))
    setHasChanges(true)
  }

  function updateProtocolKey(phaseIndex: number, key: string, value: string) {
    setPhases((prev) => {
      const newPhases = [...prev]
      const protocol = { ...(newPhases[phaseIndex].peak_week_protocol || {}), [key]: value }
      newPhases[phaseIndex] = { ...newPhases[phaseIndex], peak_week_protocol: protocol }
      return newPhases
    })
    setHasChanges(true)
  }

  function addProtocolKey(phaseIndex: number) {
    const key = prompt('Enter protocol key name:')
    if (!key) return
    updateProtocolKey(phaseIndex, key, '')
  }

  function removeProtocolKey(phaseIndex: number, key: string) {
    setPhases((prev) => {
      const newPhases = [...prev]
      const protocol = { ...(newPhases[phaseIndex].peak_week_protocol || {}) }
      delete protocol[key]
      newPhases[phaseIndex] = { ...newPhases[phaseIndex], peak_week_protocol: protocol }
      return newPhases
    })
    setHasChanges(true)
  }

  async function handleSave() {
    try {
      const sortedPhases = [...phases].sort((a, b) => a.phase - b.phase)
      await updateSupplementPhases(sortedPhases)
      setHasChanges(false)
      pushToast({ message: 'Supplement phases saved', type: 'success' })
    } catch (err) {
      pushToast({ message: 'Failed to save supplement phases', type: 'error' })
    }
  }

  const weekSelectData = [
    { value: '', label: '\u2014' },
    ...blockWeeks.map(w => ({ value: String(w), label: `W${w}` })),
  ]

  const sortedFilteredPhases = [...filteredPhases].sort((a, b) => a.phase - b.phase)

  return (
    <Stack gap="md" className="if-mock-page">
      <Group justify="space-between" className="if-mock-header">
        <Stack gap={0}>
          <h1 className="if-mock-title">Supplements</h1>
          <div className="if-mock-subtitle">Manage supplement phases and peak week protocols.</div>
        </Stack>
        <Group gap="sm">
          <Select
            value={block}
            onChange={(v) => setBlock(v ?? 'current')}
            data={availableBlocks.map((b) => ({
              value: b,
              label: b === 'current' ? 'Current Block' : b,
            }))}
            size="sm"
            w={160}
          />
          {hasChanges && (
            <Button
              leftSection={<Save size={16} />}
              onClick={handleSave}
              disabled={readOnly}
            >
              Save
            </Button>
          )}
          <Button
            variant="default"
            leftSection={<Plus size={16} />}
            onClick={addPhase}
            disabled={readOnly}
          >
            Add Phase
          </Button>
        </Group>
      </Group>

      {/* Phase Cards */}
      {sortedFilteredPhases.length > 0 ? (
        <Accordion variant="separated" className="if-mock-accordion">
          {sortedFilteredPhases.map((phase) => {
            const originalIndex = phases.findIndex((p) => p.phase === phase.phase)

            return (
              <Accordion.Item key={phase.phase} value={`phase-${phase.phase}`}>
                <Accordion.Control>
                  <Group gap="sm" wrap="nowrap">
                    <Text size="sm" c="dimmed" fw={500}>
                      Phase {phase.phase}
                    </Text>
                    {editingPhase === phase.phase ? (
                      <TextInput
                        value={phase.phase_name}
                        onChange={(e) => updatePhase(originalIndex, { phase_name: e.currentTarget.value })}
                        onBlur={() => setEditingPhase(null)}
                        onKeyDown={(e) => e.key === 'Enter' && setEditingPhase(null)}
                        size="sm"
                        w={200}
                        onClick={(e) => e.stopPropagation()}
                        disabled={readOnly}
                      />
                    ) : (
                      <Group
                        gap={4}
                        onClick={(e) => {
                          e.stopPropagation()
                          if (readOnly) return
                          setEditingPhase(phase.phase)
                        }}
                        style={{ cursor: readOnly ? 'default' : 'text' }}
                      >
                        <Text fw={500}>{phase.phase_name}</Text>
                        <Edit2 size={12} style={{ color: 'var(--mantine-color-dimmed)' }} />
                      </Group>
                    )}
                    <Badge variant="light" size="sm">
                      {phase.items.length} items
                    </Badge>
                    {(phase.start_week != null || phase.end_week != null) && (
                      <Badge variant="light" size="sm">
                        {`W${phase.start_week ?? '?'}\u2013W${phase.end_week ?? '?'}`}
                      </Badge>
                    )}
                  </Group>
                </Accordion.Control>

                <Accordion.Panel>
                  <Stack gap="md">
                    {/* Week Range */}
                    <Group gap="md">
                      <Group gap="sm">
                        <Text size="sm" c="dimmed">Start Week</Text>
                        <Select
                          value={phase.start_week != null ? String(phase.start_week) : ''}
                          onChange={(v) => updatePhase(originalIndex, {
                            start_week: v ? Number(v) : undefined,
                          })}
                          data={weekSelectData}
                          size="sm"
                          w={100}
                          disabled={readOnly}
                        />
                      </Group>
                      <Text c="dimmed">{'\u2192'}</Text>
                      <Group gap="sm">
                        <Text size="sm" c="dimmed">End Week</Text>
                        <Select
                          value={phase.end_week != null ? String(phase.end_week) : ''}
                          onChange={(v) => updatePhase(originalIndex, {
                            end_week: v ? Number(v) : undefined,
                          })}
                          data={weekSelectData}
                          size="sm"
                          w={100}
                          disabled={readOnly}
                        />
                      </Group>
                    </Group>

                    {/* Phase Notes */}
                    <Textarea
                      label="Phase Notes"
                      value={phase.notes}
                      onChange={(e) => updatePhase(originalIndex, { notes: e.currentTarget.value })}
                      minRows={2}
                      autosize
                      placeholder="Notes about this phase..."
                      disabled={readOnly}
                    />

                    {/* Supplements Table */}
                    <Stack gap="xs">
                      <Group justify="space-between">
                        <Text size="sm" c="dimmed">Supplements</Text>
                        <Button
                          variant="default"
                          size="xs"
                          leftSection={<Plus size={12} />}
                          onClick={() => addItem(originalIndex)}
                          disabled={readOnly}
                        >
                          Add Item
                        </Button>
                      </Group>

                      {phase.items.length > 0 ? (
                        <Table striped highlightOnHover>
                          <Table.Thead>
                            <Table.Tr>
                              <Table.Th w="40%">Name</Table.Th>
                              <Table.Th w="20%">Dose</Table.Th>
                              <Table.Th>Notes</Table.Th>
                              <Table.Th w={40} />
                            </Table.Tr>
                          </Table.Thead>
                          <Table.Tbody>
                            {phase.items.map((item, itemIndex) => (
                              <Table.Tr key={itemIndex}>
                                <Table.Td>
                                  <TextInput
                                    value={item.name}
                                    onChange={(e) =>
                                      updateItem(originalIndex, itemIndex, { name: e.currentTarget.value })
                                    }
                                    size="xs"
                                    disabled={readOnly}
                                  />
                                </Table.Td>
                                <Table.Td>
                                  <TextInput
                                    value={item.dose}
                                    onChange={(e) =>
                                      updateItem(originalIndex, itemIndex, { dose: e.currentTarget.value })
                                    }
                                    size="xs"
                                    disabled={readOnly}
                                  />
                                </Table.Td>
                                <Table.Td>
                                  <Textarea
                                    value={item.notes || ''}
                                    onChange={(e) =>
                                      updateItem(originalIndex, itemIndex, { notes: e.currentTarget.value })
                                    }
                                    placeholder="Optional"
                                    minRows={1}
                                    autosize
                                    size="xs"
                                    disabled={readOnly}
                                  />
                                </Table.Td>
                                <Table.Td>
                                  <ActionIcon
                                    variant="subtle"
                                    color="red"
                                    size="sm"
                                    onClick={() => removeItem(originalIndex, itemIndex)}
                                    disabled={readOnly}
                                  >
                                    <Trash2 size={14} />
                                  </ActionIcon>
                                </Table.Td>
                              </Table.Tr>
                            ))}
                          </Table.Tbody>
                        </Table>
                      ) : (
                        <Text size="sm" c="dimmed" ta="center" py="md">
                          No supplements in this phase
                        </Text>
                      )}
                    </Stack>

                    {/* Peak Week Protocol */}
                    <Stack gap="xs">
                      <Group justify="space-between">
                        <Text size="sm" c="dimmed">Peak Week Protocol</Text>
                        <Button
                          variant="default"
                          size="xs"
                          leftSection={<Plus size={12} />}
                          onClick={() => addProtocolKey(originalIndex)}
                          disabled={readOnly}
                        >
                          Add Field
                        </Button>
                      </Group>

                      {phase.peak_week_protocol && Object.keys(phase.peak_week_protocol).length > 0 ? (
                        <Stack gap="xs">
                          {Object.entries(phase.peak_week_protocol).map(([key, value]) => (
                            <Group key={key} gap="sm">
                              <Text size="sm" c="dimmed" w={130}>{key}:</Text>
                              <TextInput
                                value={value}
                                onChange={(e) => updateProtocolKey(originalIndex, key, e.currentTarget.value)}
                                style={{ flex: 1 }}
                                size="sm"
                                disabled={readOnly}
                              />
                              <ActionIcon
                                variant="subtle"
                                color="red"
                                size="sm"
                                onClick={() => removeProtocolKey(originalIndex, key)}
                                disabled={readOnly}
                              >
                                <X size={14} />
                              </ActionIcon>
                            </Group>
                          ))}
                        </Stack>
                      ) : (
                        <Text size="sm" c="dimmed" py="xs">
                          No peak week protocol defined
                        </Text>
                      )}
                    </Stack>

                    {/* Delete Phase */}
                    <Group justify="flex-end" pt="sm">
                      <Button
                        variant="light"
                        color="red"
                        size="sm"
                        leftSection={<Trash2 size={14} />}
                        onClick={() => removePhase(originalIndex)}
                        disabled={readOnly}
                      >
                        Delete Phase
                      </Button>
                    </Group>
                  </Stack>
                </Accordion.Panel>
              </Accordion.Item>
            )
          })}
        </Accordion>
      ) : (
        <Group justify="center" py={48}>
          <Text c="dimmed">No supplement phases defined. Click "Add Phase" to get started.</Text>
        </Group>
      )}
    </Stack>
  )
}
