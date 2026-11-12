import { useState, useEffect, useMemo } from 'react'
import { Plus, Trash2, Edit2, Save, ChevronDown, ChevronUp, CopyPlus } from 'lucide-react'
import {
  Stack, Group, Text, Button,
  TextInput, Textarea, Select, ActionIcon,
} from '@mantine/core'
import { useProgramStore } from '@/store/programStore'
import { useUiStore } from '@/store/uiStore'
import { useAuth } from '@/auth/AuthProvider'
import type { SupplementPhase, Supplement } from '@powerlifting/types'
import { currentBlockId, recordBlock } from '@/utils/blockScope'

export default function SupplementsPage() {
  const { readOnly } = useAuth()
  const { program, updateSupplementPhases } = useProgramStore()
  const { pushToast } = useUiStore()
  const [phases, setPhases] = useState<SupplementPhase[]>([])
  const [hasChanges, setHasChanges] = useState(false)
  const [expandedPhase, setExpandedPhase] = useState<number | null>(null)
  const [editingPhase, setEditingPhase] = useState<number | null>(null)
  const [block, setBlock] = useState(() => currentBlockId(program))

  const availableBlocks = useMemo(() => {
    const ids = (program?.meta?.blocks ?? []).map((item) => item.id).filter(Boolean)
    return ids.length ? ids : [currentBlockId(program)]
  }, [program])

  const blockWeeks = useMemo(() => {
    if (!program) return []
    const weeks = new Set<number>()
    for (const s of program.sessions) {
      if (recordBlock(s, 'sessions', program) === block) weeks.add(s.week_number)
    }
    return Array.from(weeks).sort((a, b) => a - b)
  }, [program, block])

  const filteredPhases = useMemo(
    () => phases.filter(p => recordBlock(p, 'supplement_phases', program) === block),
    [phases, block, program]
  )

  useEffect(() => {
    setBlock(currentBlockId(program))
  }, [program?.meta?.current_block_id])

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
        block_id: block,
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

  function addSupplement() {
    const target = [...filteredPhases].sort((a, b) => b.phase - a.phase)[0]
    if (target) {
      addItem(phases.indexOf(target))
      setExpandedPhase(target.phase)
      return
    }
    const nextPhase = phases.reduce((max, p) => Math.max(max, p.phase), 0) + 1
    setPhases((prev) => [...prev, { phase: nextPhase, phase_name: 'Supplements', notes: '', items: [{ name: '', dose: '' }], block_id: block }])
    setExpandedPhase(nextPhase)
    setHasChanges(true)
  }

  const previousPhase = useMemo(() => {
    const earlier = phases.filter((p) => recordBlock(p, 'supplement_phases', program) !== block && p.items.length > 0)
    return earlier.sort((a, b) => b.phase - a.phase)[0]
  }, [phases, block, program])

  function carryOver() {
    if (!previousPhase) return
    const nextPhase = phases.reduce((max, p) => Math.max(max, p.phase), 0) + 1
    setPhases((prev) => [...prev, { phase: nextPhase, phase_name: previousPhase.phase_name, notes: previousPhase.notes, items: previousPhase.items.map((item) => ({ ...item })), block_id: block }])
    setExpandedPhase(nextPhase)
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
          <div className="if-mock-subtitle">What you are taking this block, with dose and notes.</div>
        </Stack>
        <Group gap="sm">
          <Select
            value={block}
            onChange={(v) => setBlock(v ?? currentBlockId(program))}
            data={availableBlocks.map((b) => ({
              value: b,
              label: b === currentBlockId(program) ? 'Current Block' : (program?.meta?.blocks ?? []).find((item) => item.id === b)?.name || b,
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
            leftSection={<Plus size={16} />}
            onClick={addSupplement}
            disabled={readOnly}
          >
            Add supplement
          </Button>
          <Button
            variant="subtle"
            leftSection={<Plus size={16} />}
            onClick={addPhase}
            disabled={readOnly}
          >
            New phase
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
                        placeholder="Why you are running this stack, how it is going..."
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
        <Stack align="center" py={48} gap="sm">
          <Text c="dimmed">No supplements logged for this block yet.</Text>
          <Group gap="sm">
            <Button leftSection={<Plus size={16} />} onClick={addSupplement} disabled={readOnly}>Add supplement</Button>
            {previousPhase && (
              <Button variant="default" leftSection={<CopyPlus size={16} />} onClick={carryOver} disabled={readOnly}>
                Carry over {previousPhase.items.length} from {previousPhase.phase_name}
              </Button>
            )}
          </Group>
        </Stack>
      )}
    </Stack>
  )
}
