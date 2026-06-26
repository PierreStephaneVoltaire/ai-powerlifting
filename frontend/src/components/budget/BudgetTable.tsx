import { useMemo, useState } from 'react'
import { useMediaQuery } from '@mantine/hooks'
import {
  ActionIcon, Box, Button, Group, MultiSelect, Paper, Stack, Switch, Table, Text, UnstyledButton,
} from '@mantine/core'
import { Plus, Filter as FilterIcon } from 'lucide-react'
import type { BudgetItem, BudgetCategory, BudgetPriorityTier, BudgetRecurrence } from '@powerlifting/types'
import { PRIORITY_ORDER, makeBlankItem, nextPriority, todayIso } from './types'
import { CATEGORY_OPTIONS, RECURRENCE_OPTIONS } from './budgetConstants'
import ExpenseRow from './ExpenseRow'
import { getMediaUrl } from '@/utils/media'

export interface BudgetTableProps {
  items: BudgetItem[]
  readOnly: boolean
  currency: string
  compOptions: { value: string; label: string }[]
  onAdd: (item: BudgetItem) => void
  onUpdate: (id: string, patch: Partial<BudgetItem>) => void
  onRemove: (id: string) => void
  onPhotoUpload?: (itemId: string, file: File) => void
  onPhotoDelete?: (itemId: string) => void
}

interface FilterState {
  categories: BudgetCategory[]
  priorities: BudgetPriorityTier[]
  recurrences: BudgetRecurrence[]
  compLinkedOnly: boolean
  showPurchased: boolean
}

const DEFAULT_FILTERS: FilterState = {
  categories: [], priorities: [], recurrences: [], compLinkedOnly: false, showPurchased: true,
}

export default function BudgetTable({
  items, readOnly, currency, compOptions, onAdd, onUpdate, onRemove, onPhotoUpload, onPhotoDelete,
}: BudgetTableProps) {
  const isMobile = useMediaQuery('(max-width: 768px)') ?? false
  const [filters, setFilters] = useState<FilterState>(DEFAULT_FILTERS)
  const [filtersOpen, setFiltersOpen] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [newItemIds, setNewItemIds] = useState<Set<string>>(new Set())

  const activeFilterCount =
    filters.categories.length + filters.priorities.length + filters.recurrences.length +
    (filters.compLinkedOnly ? 1 : 0) + (filters.showPurchased ? 0 : 1)

  const filtered = useMemo(() => {
    return items
      .filter((it) => {
        if (filters.categories.length && !filters.categories.includes(it.category)) return false
        if (filters.priorities.length && !filters.priorities.includes(it.priority_tier)) return false
        if (filters.recurrences.length && !filters.recurrences.includes(it.recurrence)) return false
        if (filters.compLinkedOnly && !it.comp_linked) return false
        if (!filters.showPurchased && it.purchased) return false
        return true
      })
      .sort((a, b) => {
        const p = PRIORITY_ORDER[a.priority_tier] - PRIORITY_ORDER[b.priority_tier]
        if (p !== 0) return p
        return (a.start_date ?? '').localeCompare(b.start_date ?? '')
      })
  }, [items, filters])

  const handleAdd = () => {
    const blank = makeBlankItem('other')
    onAdd(blank)
    setEditingId(blank.id)
    setNewItemIds((prev) => new Set(prev).add(blank.id))
  }

  const handleCyclePriority = (id: string, current: BudgetPriorityTier) => {
    onUpdate(id, { priority_tier: nextPriority(current) })
  }

  const handleTogglePurchased = (id: string, purchased: boolean) => {
    const item = items.find((it) => it.id === id)
    onUpdate(id, {
      purchased,
      purchased_date: purchased ? (item?.purchased_date ?? todayIso()) : null,
    })
  }

  const handleSaveEdit = (id: string) => {
    setEditingId(null)
    setNewItemIds((prev) => { const n = new Set(prev); n.delete(id); return n })
  }

  const handleCancelEdit = (id: string, isNew: boolean) => {
    setEditingId(null)
    if (isNew) onRemove(id)
    setNewItemIds((prev) => { const n = new Set(prev); n.delete(id); return n })
  }

  const photoUrlFor = (item: BudgetItem) => getMediaUrl(item.photo_s3_key)

  const categoryFilterData = CATEGORY_OPTIONS.map((o) => ({ value: o.value, label: o.label }))
  const priorityFilterData = [
    { value: 'MANDATORY', label: 'Mandatory' },
    { value: 'IMPORTANT', label: 'Important' },
    { value: 'OPTIONAL', label: 'Optional' },
  ]
  const recurrenceFilterData = RECURRENCE_OPTIONS.map((o) => ({ value: o.value, label: o.label }))

  const rowProps = (item: BudgetItem) => ({
    key: item.id,
    item,
    readOnly,
    currency,
    compOptions,
    isEditing: editingId === item.id,
    isNew: newItemIds.has(item.id),
    onStartEdit: () => setEditingId(item.id),
    onCancelEdit: () => handleCancelEdit(item.id, newItemIds.has(item.id)),
    onSave: () => handleSaveEdit(item.id),
    onChange: (patch: Partial<BudgetItem>) => onUpdate(item.id, patch),
    onCyclePriority: () => handleCyclePriority(item.id, item.priority_tier),
    onTogglePurchased: (p: boolean) => handleTogglePurchased(item.id, p),
    onDelete: () => onRemove(item.id),
    onPhotoUpload: onPhotoUpload ? (f: File) => onPhotoUpload(item.id, f) : undefined,
    onPhotoDelete: onPhotoDelete ? () => onPhotoDelete(item.id) : undefined,
    photoUrl: photoUrlFor(item),
  })

  return (
    <Stack gap="md" style={{ position: 'relative' }}>
      <Group justify="space-between" align="center" wrap="wrap" gap="sm">
        <Text fw={600}>Expenses ({filtered.length})</Text>
        {!readOnly && !isMobile && (
          <Button leftSection={<Plus size={16} />} onClick={handleAdd} size="sm">
            Add expense
          </Button>
        )}
      </Group>

      {isMobile ? (
        <Group gap="xs" align="center">
          <UnstyledButton
            onClick={() => setFiltersOpen((o) => !o)}
            style={{
              display: 'flex', alignItems: 'center', gap: 6, padding: '6px 10px',
              border: '1px solid var(--mantine-color-gray-3)', borderRadius: 'var(--mantine-radius-sm)',
              background: activeFilterCount > 0 ? 'var(--mantine-color-blue-0)' : undefined,
            }}
          >
            <FilterIcon size={14} />
            <Text size="xs">Filter</Text>
            {activeFilterCount > 0 && (
              <Box component="span" style={{ background: 'var(--mantine-color-blue-6)', color: 'white', borderRadius: 8, padding: '0 6px', fontSize: 11, lineHeight: '16px' }}>
                {activeFilterCount}
              </Box>
            )}
          </UnstyledButton>
          {filtersOpen && (
            <Stack gap="xs" style={{ width: '100%' }} pt="xs">
              <FilterBar
                filters={filters}
                setFilters={setFilters}
                categoryFilterData={categoryFilterData}
                priorityFilterData={priorityFilterData}
                recurrenceFilterData={recurrenceFilterData}
              />
            </Stack>
          )}
        </Group>
      ) : (
        <Paper withBorder p="sm" radius="md">
          <FilterBar
            filters={filters}
            setFilters={setFilters}
            categoryFilterData={categoryFilterData}
            priorityFilterData={priorityFilterData}
            recurrenceFilterData={recurrenceFilterData}
          />
        </Paper>
      )}

      {filtered.length === 0 && items.length === 0 ? (
        <Paper withBorder p="xl" radius="md" ta="center">
          <Stack gap="xs" align="center">
            <Text c="dimmed">No expenses yet.</Text>
            {!readOnly && (
              <Button variant="light" leftSection={<Plus size={16} />} onClick={handleAdd}>
                Add your first expense
              </Button>
            )}
          </Stack>
        </Paper>
      ) : filtered.length === 0 ? (
        <Paper withBorder p="xl" radius="md" ta="center">
          <Text c="dimmed">No items match the current filters.</Text>
        </Paper>
      ) : isMobile ? (
        <Stack gap={0}>
          {filtered.map((item) => <ExpenseRow {...rowProps(item)} isMobile />)}
        </Stack>
      ) : (
        <Table verticalSpacing="xs" horizontalSpacing="sm" highlightOnHover>
          <Table.Thead>
            <Table.Tr>
              <Table.Th style={{ width: 28 }}></Table.Th>
              <Table.Th style={{ width: 90 }}>Priority</Table.Th>
              <Table.Th style={{ width: 36 }}>Cat</Table.Th>
              <Table.Th>Name</Table.Th>
              <Table.Th style={{ width: 28 }}>Rec</Table.Th>
              <Table.Th ta="right">Cost</Table.Th>
              <Table.Th>Date/Period</Table.Th>
              <Table.Th style={{ width: 28 }}>Comp</Table.Th>
              <Table.Th style={{ width: 40 }}>✓</Table.Th>
              <Table.Th style={{ width: 40 }}></Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {filtered.map((item) => <ExpenseRow {...rowProps(item)} isMobile={false} />)}
          </Table.Tbody>
        </Table>
      )}

      {!readOnly && isMobile && (
        <ActionIcon
          variant="filled"
          color="brand"
          size="lg"
          radius="xl"
          onClick={handleAdd}
          aria-label="Add expense"
          style={{ position: 'fixed', bottom: 24, right: 16, width: 56, height: 56, zIndex: 1000, boxShadow: '0 4px 12px rgba(0,0,0,0.2)' }}
        >
          <Plus size={24} />
        </ActionIcon>
      )}
    </Stack>
  )
}

interface FilterBarProps {
  filters: FilterState
  setFilters: (f: FilterState) => void
  categoryFilterData: { value: string; label: string }[]
  priorityFilterData: { value: string; label: string }[]
  recurrenceFilterData: { value: string; label: string }[]
}

function FilterBar({ filters, setFilters, categoryFilterData, priorityFilterData, recurrenceFilterData }: FilterBarProps) {
  return (
    <Group gap="sm" wrap="wrap" align="flex-end">
      <MultiSelect
        label="Category"
        size="xs"
        placeholder="All"
        value={filters.categories}
        onChange={(v) => setFilters({ ...filters, categories: v as BudgetCategory[] })}
        data={categoryFilterData}
        clearable
        searchable
        style={{ minWidth: 140, flex: '1 1 140px' }}
      />
      <MultiSelect
        label="Priority"
        size="xs"
        placeholder="All"
        value={filters.priorities}
        onChange={(v) => setFilters({ ...filters, priorities: v as BudgetPriorityTier[] })}
        data={priorityFilterData}
        clearable
        style={{ minWidth: 120, flex: '1 1 120px' }}
      />
      <MultiSelect
        label="Recurrence"
        size="xs"
        placeholder="All"
        value={filters.recurrences}
        onChange={(v) => setFilters({ ...filters, recurrences: v as BudgetRecurrence[] })}
        data={recurrenceFilterData}
        clearable
        style={{ minWidth: 120, flex: '1 1 120px' }}
      />
      <Switch
        label="Comp-linked only"
        size="xs"
        checked={filters.compLinkedOnly}
        onChange={(e) => setFilters({ ...filters, compLinkedOnly: e.currentTarget.checked })}
      />
      <Switch
        label="Show purchased"
        size="xs"
        checked={filters.showPurchased}
        onChange={(e) => setFilters({ ...filters, showPurchased: e.currentTarget.checked })}
      />
    </Group>
  )
}