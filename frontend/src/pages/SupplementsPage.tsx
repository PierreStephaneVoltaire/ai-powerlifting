import { useState, useEffect, useMemo } from 'react'
import { Plus, X, Trash2, Edit2, Save, ChevronDown, ChevronUp } from 'lucide-react'
import {
  Stack, Group, Text, Button,
  TextInput, Textarea, Select, ActionIcon,
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
    } else {
      setPhases([])
    }
  }, [program])

  useEffect(() => {
    if (filteredPhases.length === 0) {
      setExpandedPhase(null)
      return
    }

    setExpandedPhase((current) => {
      if (current != null && filteredPhases.some((phase) => phase.phase === current)) return current
      return [...filteredPhases].sort((a, b) => a.phase - b.phase)[0]?.phase ?? null
    })
  }, [block, filteredPhases])

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
    const nextPhase = maxPhase + 1
    setPhases((prev) => [
      ...prev,
      {
        phase: nextPhase,
        phase_name: `Phase ${nextPhase}`,
        notes: '',
        items: [],
        block: block,
      },
    ])
    setExpandedPhase(nextPhase)
    setEditingPhase(nextPhase)
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

  const phaseWeekLabel = (phase: SupplementPhase) => {
    if (phase.start_week == null && phase.end_week == null) return 'W?'
    return `W${phase.start_week ?? '?'}\u2013W${phase.end_week ?? '?'}`
  }

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

      {sortedFilteredPhases.length > 0 ? (
        <div>
          {sortedFilteredPhases.map((phase) => {
            const originalIndex = phases.indexOf(phase)
            const isOpen = expandedPhase === phase.phase
            const weekLabel = phaseWeekLabel(phase)

            return (
              <div className="if-supp-phase-card" key={`${phase.block ?? 'current'}-${phase.phase}-${originalIndex}`}>
                <button
                  type="button"
                  className="if-supp-phase-header"
                  onClick={() => setExpandedPhase(isOpen ? null : phase.phase)}
                >
                  <span className="if-supp-phase-number">Phase {phase.phase}</span>
                  <span className="if-supp-phase-title">
                    {editingPhase === phase.phase ? (
                      <TextInput
                        value={phase.phase_name}
                        onChange={(e) => updatePhase(originalIndex, { phase_name: e.currentTarget.value })}
                        onBlur={() => setEditingPhase(null)}
                        onKeyDown={(e) => e.key === 'Enter' && setEditingPhase(null)}
                        size="xs"
                        style={{ width: 'min(260px, 100%)' }}
                        onClick={(e) => e.stopPropagation()}
                        disabled={readOnly}
                      />
                    ) : (
                      <span
                        onClick={(e) => {
                          e.stopPropagation()
                          if (readOnly) return
                          setEditingPhase(phase.phase)
                        }}
                        style={{ alignItems: 'center', cursor: readOnly ? 'default' : 'text', display: 'inline-flex', gap: 5, minWidth: 0 }}
                      >
                        <span style={{ minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{phase.phase_name}</span>
                        <Edit2 size={12} style={{ color: 'var(--color-text-secondary)', flexShrink: 0 }} />
                      </span>
                    )}
                  </span>
                  <span className="if-supp-count-pill">{phase.items.length} items</span>
                  <span className="if-supp-week-pill">{weekLabel}</span>
                  {isOpen ? <ChevronUp size={14} style={{ color: 'var(--color-text-secondary)', flexShrink: 0 }} /> : <ChevronDown size={14} style={{ color: 'var(--color-text-secondary)', flexShrink: 0 }} />}
                </button>

                {isOpen && (
                  <div className="if-supp-phase-inner">
                    <div className="if-supp-section">
                      <Group gap="md" wrap="wrap">
                        <Group gap={6} wrap="nowrap">
                          <Text size="sm" c="dimmed">Start</Text>
                        <Select
                          value={phase.start_week != null ? String(phase.start_week) : ''}
                          onChange={(v) => updatePhase(originalIndex, {
                            start_week: v ? Number(v) : undefined,
                          })}
                          data={weekSelectData}
                          size="xs"
                          w={74}
                          disabled={readOnly}
                        />
                        </Group>
                        <Text c="dimmed">{'\u2192'}</Text>
                        <Group gap={6} wrap="nowrap">
                          <Text size="sm" c="dimmed">End</Text>
                        <Select
                          value={phase.end_week != null ? String(phase.end_week) : ''}
                          onChange={(v) => updatePhase(originalIndex, {
                            end_week: v ? Number(v) : undefined,
                          })}
                          data={weekSelectData}
                          size="xs"
                          w={74}
                          disabled={readOnly}
                        />
                        </Group>
                      </Group>
                    </div>

                    <div className="if-supp-section">
                      <div className="if-small-label">Phase notes</div>
                      <Textarea
                        value={phase.notes}
                        onChange={(e) => updatePhase(originalIndex, { notes: e.currentTarget.value })}
                        minRows={2}
                        autosize
                        placeholder="Protocol intent, notes for AI context..."
                        disabled={readOnly}
                      />
                    </div>

                    <div className="if-supp-table-header">
                      <span className="if-supp-table-label">Name</span>
                      <span className="if-supp-table-label">Dose</span>
                      <span className="if-supp-table-label">Notes</span>
                      <Button
                        variant="default"
                        size="compact-xs"
                        leftSection={<Plus size={11} />}
                        onClick={() => addItem(originalIndex)}
                        disabled={readOnly}
                        style={{ justifySelf: 'end' }}
                      >
                        Add
                      </Button>
                    </div>

                    {phase.items.length > 0 ? phase.items.map((item, itemIndex) => (
                      <div className="if-supp-table-row" key={itemIndex}>
                        <TextInput
                          value={item.name}
                          onChange={(e) =>
                            updateItem(originalIndex, itemIndex, { name: e.currentTarget.value })
                          }
                          placeholder="Supplement name"
                          size="xs"
                          disabled={readOnly}
                        />
                        <TextInput
                          value={item.dose}
                          onChange={(e) =>
                            updateItem(originalIndex, itemIndex, { dose: e.currentTarget.value })
                          }
                          placeholder="e.g. 5g/day"
                          size="xs"
                          disabled={readOnly}
                          styles={{ input: { fontFamily: 'var(--font-mono)' } }}
                        />
                        <TextInput
                          value={item.notes || ''}
                          onChange={(e) =>
                            updateItem(originalIndex, itemIndex, { notes: e.currentTarget.value })
                          }
                          placeholder="Notes or observations..."
                          size="xs"
                          disabled={readOnly}
                          classNames={{ input: 'if-supp-note-input' }}
                        />
                        <ActionIcon
                          variant="subtle"
                          color="red"
                          size="sm"
                          onClick={() => removeItem(originalIndex, itemIndex)}
                          disabled={readOnly}
                          aria-label="Remove supplement"
                        >
                          <Trash2 size={14} />
                        </ActionIcon>
                      </div>
                    )) : (
                      <Text size="sm" c="dimmed" py="md" px={16}>
                        No supplements added yet.
                      </Text>
                    )}

                    <div className="if-supp-section" style={{ borderTop: '0.5px solid var(--color-border-tertiary)' }}>
                      <Group justify="space-between" mb={8}>
                        <div className="if-small-label" style={{ marginBottom: 0 }}>Peak week protocol</div>
                        <Button
                          variant="default"
                          size="compact-xs"
                          leftSection={<Plus size={11} />}
                          onClick={() => addProtocolKey(originalIndex)}
                          disabled={readOnly}
                        >
                          Add field
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
                        <Text size="sm" c="dimmed">
                          No peak week protocol defined
                        </Text>
                      )}
                    </div>

                    <div className="if-supp-footer">
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
                    </div>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      ) : (
        <Group justify="center" py={48}>
          <Text c="dimmed">No supplement phases defined. Click "Add Phase" to get started.</Text>
        </Group>
      )}
    </Stack>
  )
}
