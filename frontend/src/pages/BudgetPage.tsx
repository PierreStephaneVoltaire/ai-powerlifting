import { useEffect, useMemo, useState, useCallback } from 'react'
import { Link } from 'react-router-dom'
import { useDropzone } from 'react-dropzone'
import { Wallet, Plus, Trash2, Save, Camera, AlertTriangle, CheckCircle2, CalendarClock, Sparkles, Loader2 } from 'lucide-react'
import {
  ActionIcon,
  Badge,
  Box,
  Button,
  Card,
  Container,
  FileButton,
  Group,
  Image as MantineImage,
  NumberInput,
  Paper,
  Progress,
  Select,
  SimpleGrid,
  Stack,
  Switch,
  Table,
  Tabs,
  Text,
  TextInput,
  Textarea,
  Timeline,
  Title,
  Tooltip,
} from '@mantine/core'
import { useUiStore } from '@/store/uiStore'
import { useAuth } from '@/auth/AuthProvider'
import { useBudgetStore } from '@/store/budgetStore'
import { useCompetitionsStore } from '@/store/competitionsStore'
import { useFederationStore } from '@/store/federationStore'
import { fetchFederations, putBudget as apiPutBudget, uploadBudgetItemPhoto, deleteBudgetItemPhoto, fetchBudgetTimeline } from '@/api/client'
import { getMediaUrl } from '@/utils/media'
import ReadOnlyBanner from '@/components/shared/ReadOnlyBanner'
import type {
  BudgetItem,
  BudgetCategory,
  BudgetPriority,
  BudgetRecurrence,
  EquipmentCondition,
  TrainingPriority,
  BudgetTimeline as BudgetTimelineType,
  MasterFederation,
  UserCompetition,
  BudgetConfig,
} from '@powerlifting/types'
import {
  BUDGET_CATEGORY_OPTIONS,
  BUDGET_PRIORITY_OPTIONS,
  BUDGET_RECURRENCE_OPTIONS,
  EQUIPMENT_CONDITION_OPTIONS,
  TRAINING_PRIORITY_OPTIONS,
} from '@powerlifting/types'

function newItemId(): string {
  return `item-${Date.now().toString(36)}-${Math.floor(Math.random() * 1e9).toString(36)}`
}

function makeBlankItem(category: BudgetCategory): BudgetItem {
  const now = new Date().toISOString()
  return {
    id: newItemId(),
    name: '',
    category,
    cost: 0,
    recurrence: category === 'gym_membership' || category === 'supplement' ? 'monthly' : 'one_time',
    priority: 'optional',
    purchased: false,
    created_at: now,
    updated_at: now,
  }
}

function monthKey(date: Date): string {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`
}

function monthLabel(key: string): string {
  const [y, m] = key.split('-').map(Number)
  if (!y || !m) return key
  return new Date(y, m - 1, 1).toLocaleDateString(undefined, { month: 'short', year: 'numeric' })
}

function priorityColor(p: BudgetPriority): string {
  return p === 'buy_now' ? 'red' : p === 'buy_later' ? 'orange' : p === 'optional' ? 'blue' : 'gray'
}

function conditionColor(c: EquipmentCondition | undefined): string {
  return c === 'good' ? 'green' : c === 'worn' ? 'yellow' : c === 'needs_replacement' ? 'red' : 'gray'
}

function monthCostForItem(item: BudgetItem, month: string): number {
  if (item.purchased) return 0
  const start = item.start_month
  if (item.recurrence === 'one_time') {
    if (!start) return 0
    return start === month ? item.cost : 0
  }
  if (item.recurrence === 'monthly') {
    if (!start) return item.cost
    return start <= month ? item.cost : 0
  }
  if (item.recurrence === 'multi_month') {
    if (!start) return item.cost
    const months = item.months ?? 1
    const startMs = new Date(start + '-01').getTime()
    const curMs = new Date(month + '-01').getTime()
    const endMs = new Date(start + '-01')
    endMs.setMonth(endMs.getMonth() + months)
    return curMs >= startMs && curMs < endMs.getTime() ? item.cost : 0
  }
  return 0
}

function buildMonths(items: BudgetItem[], count: number): string[] {
  const today = new Date()
  const months: string[] = []
  const minStart = items.map((i) => i.start_month).filter(Boolean).sort()[0]
  let base = new Date(today.getFullYear(), today.getMonth(), 1)
  if (minStart) {
    const [y, m] = minStart.split('-').map(Number)
    const start = new Date(y, m - 1, 1)
    if (start.getTime() < base.getTime()) base = start
  }
  for (let i = 0; i < count; i++) {
    months.push(monthKey(base))
    base = new Date(base.getFullYear(), base.getMonth() + 1, 1)
  }
  return months
}

function spentByMonth(items: BudgetItem[]): Map<string, number> {
  const map = new Map<string, number>()
  for (const it of items) {
    if (!it.purchased) continue
    const key = (it.purchased_date ?? it.start_month ?? '').slice(0, 7)
    if (!key) continue
    map.set(key, (map.get(key) ?? 0) + it.cost)
  }
  return map
}

export default function BudgetPage() {
  const { readOnly } = useAuth()
  const { pushToast } = useUiStore()
  const { config, items, isLoading, loaded, load, save } = useBudgetStore()
  const { competitions, loadAll: loadCompetitions } = useCompetitionsStore()
  const { library, loadLibrary, saveLibrary } = useFederationStore()

  const [draftItems, setDraftItems] = useState<BudgetItem[]>([])
  const [draftConfig, setDraftConfig] = useState<BudgetConfig>(config)
  const [dirty, setDirty] = useState(false)
  const [saving, setSaving] = useState(false)
  const [masterFeds, setMasterFeds] = useState<MasterFederation[]>([])
  const [timeline, setTimeline] = useState<BudgetTimelineType | null>(null)
  const [timelineLoading, setTimelineLoading] = useState(false)

  useEffect(() => { load() }, [load])
  useEffect(() => { loadCompetitions().catch(() => {}) }, [loadCompetitions])
  useEffect(() => { loadLibrary().catch(() => {}) }, [loadLibrary])
  useEffect(() => {
    let cancelled = false
    fetchFederations().then((feds) => { if (!cancelled) setMasterFeds(feds) }).catch(() => {})
    return () => { cancelled = true }
  }, [])

  useEffect(() => {
    setDraftItems(items)
    setDraftConfig(config)
    setDirty(false)
  }, [items, config])

  const upcomingComps = useMemo<UserCompetition[]>(() => {
    const today = new Date().toISOString().slice(0, 10)
    return competitions
      .filter((c) => c.user_status !== 'completed' && c.user_status !== 'skipped' && (c.start_date ?? '') >= today)
      .sort((a, b) => a.start_date.localeCompare(b.start_date))
  }, [competitions])

  const compOptions = useMemo(() => [
    { value: '', label: 'None' },
    ...upcomingComps.map((c) => ({ value: c.master_id, label: `${c.name} (${c.start_date})` })),
  ], [upcomingComps])

  const months = useMemo(() => buildMonths(draftItems, 6), [draftItems])
  const spentMap = useMemo(() => spentByMonth(draftItems), [draftItems])

  const monthlyRows = useMemo(() => months.map((m) => {
    const due = draftItems.reduce((sum, it) => sum + monthCostForItem(it, m), 0)
    const spent = spentMap.get(m) ?? 0
    const remaining = config.monthly_budget - due
    return { month: m, due, spent, remaining }
  }), [months, draftItems, spentMap, config.monthly_budget])

  const totalRecurring = useMemo(() =>
    draftItems
      .filter((it) => (it.recurrence === 'monthly' || it.recurrence === 'multi_month') && !it.purchased)
      .reduce((sum, it) => sum + it.cost, 0),
    [draftItems])

  const updateItem = useCallback((id: string, patch: Partial<BudgetItem>) => {
    setDraftItems((prev) => prev.map((it) => (it.id === id ? { ...it, ...patch, updated_at: new Date().toISOString() } : it)))
    setDirty(true)
  }, [])

  const addItem = useCallback((category: BudgetCategory) => {
    setDraftItems((prev) => [...prev, makeBlankItem(category)])
    setDirty(true)
  }, [])

  const removeItem = useCallback((id: string) => {
    setDraftItems((prev) => prev.filter((it) => it.id !== id))
    setDirty(true)
  }, [])

  const handleSave = async () => {
    setSaving(true)
    try {
      await save({ config: draftConfig, items: draftItems })
      pushToast({ message: 'Budget saved', type: 'success' })
      setDirty(false)
    } catch {
      pushToast({ message: 'Failed to save budget', type: 'error' })
    } finally {
      setSaving(false)
    }
  }

  const handlePhotoUpload = async (itemId: string, file: File) => {
    try {
      const { photo_s3_key } = await uploadBudgetItemPhoto(itemId, file)
      useBudgetStore.getState().setItemPhoto(itemId, photo_s3_key)
      setDraftItems((prev) => prev.map((it) => (it.id === itemId ? { ...it, photo_s3_key, photo_url: null } : it)))
      pushToast({ message: 'Photo uploaded', type: 'success' })
    } catch {
      pushToast({ message: 'Photo upload failed', type: 'error' })
    }
  }

  const handlePhotoDelete = async (itemId: string) => {
    try {
      await deleteBudgetItemPhoto(itemId)
      useBudgetStore.getState().setItemPhoto(itemId, null)
      setDraftItems((prev) => prev.map((it) => (it.id === itemId ? { ...it, photo_s3_key: null, photo_url: null } : it)))
      pushToast({ message: 'Photo removed', type: 'success' })
    } catch {
      pushToast({ message: 'Failed to remove photo', type: 'error' })
    }
  }

  const handleTimeline = async () => {
    setTimelineLoading(true)
    try {
      const result = await fetchBudgetTimeline({ config: draftConfig, items: draftItems })
      setTimeline(result)
    } catch {
      pushToast({ message: 'Failed to generate timeline', type: 'error' })
    } finally {
      setTimelineLoading(false)
    }
  }

  const fedMembershipCoverage = useMemo(() => {
    const map = new Map<string, string[]>()
    for (const fed of masterFeds) {
      const group = fed.membership_group ?? []
      if (group.length > 0) {
        const key = [...group].sort().join('|')
        map.set(key, group)
      }
    }
    return Array.from(map.values())
  }, [masterFeds])

  return (
    <Container size="xl" pb={40}>
      <ReadOnlyBanner />
      <Stack gap="md">
        <Group justify="space-between" align="flex-end">
          <Stack gap={2}>
            <Group gap="sm">
              <Wallet size={26} />
              <Title order={2}>Budget</Title>
            </Group>
            <Text size="sm" c="dimmed">Monthly budget, recurring costs, equipment condition, and a priority timeline driven by your competitions.</Text>
          </Stack>
          <Group gap="sm">
            <Tooltip label={dirty ? 'You have unsaved changes' : ''}>
              <Button
                leftSection={<Save size={16} />}
                onClick={handleSave}
                loading={saving}
                disabled={readOnly || !dirty}
              >
                Save
              </Button>
            </Tooltip>
          </Group>
        </Group>

        <Tabs defaultValue="overview">
          <Tabs.List>
            <Tabs.Tab value="overview">Overview</Tabs.Tab>
            <Tabs.Tab value="items">Items</Tabs.Tab>
            <Tabs.Tab value="federations">Federation memberships</Tabs.Tab>
            <Tabs.Tab value="timeline">Priority timeline</Tabs.Tab>
          </Tabs.List>

          <Tabs.Panel value="overview" pt="md">
            <OverviewTab
              config={draftConfig}
              monthlyRows={monthlyRows}
              totalRecurring={totalRecurring}
              itemsCount={draftItems.length}
              overdueCount={monthlyRows.filter((r) => r.due > draftConfig.monthly_budget && draftConfig.monthly_budget > 0).length}
              readOnly={readOnly}
              onConfigChange={(c) => { setDraftConfig(c); setDirty(true) }}
              months={months}
            />
          </Tabs.Panel>

          <Tabs.Panel value="items" pt="md">
            <ItemsTab
              items={draftItems}
              readOnly={readOnly}
              compOptions={compOptions}
              onUpdate={updateItem}
              onAdd={addItem}
              onRemove={removeItem}
              onPhotoUpload={handlePhotoUpload}
              onPhotoDelete={handlePhotoDelete}
            />
          </Tabs.Panel>

          <Tabs.Panel value="federations" pt="md">
            <FederationTab
              masterFeds={masterFeds}
              library={library}
              readOnly={readOnly}
              coverageGroups={fedMembershipCoverage}
              onPay={(fedId, paid, cost, paidDate) => {
                if (!library) return
                const nextFeds = library.federations.map((f) =>
                  f.id === fedId ? { ...f, membership_paid: paid, membership_cost: cost, membership_paid_date: paidDate } : f,
                )
                saveLibrary({ ...library, federations: nextFeds }).catch(() => pushToast({ message: 'Failed to save federation', type: 'error' }))
              }}
            />
          </Tabs.Panel>

          <Tabs.Panel value="timeline" pt="md">
            <TimelineTab
              timeline={timeline}
              loading={timelineLoading}
              readOnly={readOnly}
              onGenerate={handleTimeline}
              comps={upcomingComps}
            />
          </Tabs.Panel>
        </Tabs>
      </Stack>
    </Container>
  )
}

interface OverviewTabProps {
  config: BudgetConfig
  monthlyRows: { month: string; due: number; spent: number; remaining: number }[]
  totalRecurring: number
  itemsCount: number
  overdueCount: number
  readOnly: boolean
  onConfigChange: (c: BudgetConfig) => void
  months: string[]
}

function OverviewTab({ config, monthlyRows, totalRecurring, itemsCount, overdueCount, readOnly, onConfigChange, months }: OverviewTabProps) {
  const overBudget = config.monthly_budget > 0 && totalRecurring > config.monthly_budget
  return (
    <Stack gap="md">
      <SimpleGrid cols={{ base: 1, sm: 2, md: 4 }}>
        <Paper withBorder p="md" radius="md">
          <Text size="xs" c="dimmed">Monthly budget</Text>
          <NumberInput
            mt={4}
            value={config.monthly_budget}
            onChange={(v) => onConfigChange({ ...config, monthly_budget: typeof v === 'number' ? v : 0 })}
            min={0}
            disabled={readOnly}
            leftSection={<Text size="xs" c="dimmed">$</Text>}
            decimalScale={2}
            hideControls
          />
          <Select
            mt={6}
            size="xs"
            value={config.currency}
            onChange={(v) => onConfigChange({ ...config, currency: v ?? 'CAD' })}
            data={['CAD', 'USD', 'EUR', 'GBP', 'AUD']}
            disabled={readOnly}
          />
        </Paper>
        <Paper withBorder p="md" radius="md">
          <Text size="xs" c="dimmed">Recurring / month</Text>
          <Text fw={700} size="xl" mt={4}>${totalRecurring.toFixed(2)}</Text>
          {overBudget && (
            <Badge color="red" variant="light" mt={6} leftSection={<AlertTriangle size={12} />}>Over monthly cap</Badge>
          )}
        </Paper>
        <Paper withBorder p="md" radius="md">
          <Text size="xs" c="dimmed">Items tracked</Text>
          <Text fw={700} size="xl" mt={4}>{itemsCount}</Text>
        </Paper>
        <Paper withBorder p="md" radius="md">
          <Text size="xs" c="dimmed">Months over cap</Text>
          <Text fw={700} size="xl" mt={4}>{overdueCount}</Text>
        </Paper>
      </SimpleGrid>

      <Paper withBorder p="md" radius="md">
        <Group justify="space-between" mb="sm">
          <Text fw={600}>Budget vs due — next {months.length} months</Text>
          {config.monthly_budget > 0 && (
            <Text size="xs" c="dimmed">cap ${config.monthly_budget.toFixed(2)}/mo</Text>
          )}
        </Group>
        <Table>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Month</Table.Th>
              <Table.Th ta="right">Due</Table.Th>
              <Table.Th ta="right">Spent</Table.Th>
              <Table.Th>Adherence</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {monthlyRows.map((r) => {
              const pct = config.monthly_budget > 0 ? Math.min(100, (r.due / config.monthly_budget) * 100) : 0
              const over = config.monthly_budget > 0 && r.due > config.monthly_budget
              return (
                <Table.Tr key={r.month}>
                  <Table.Td>{monthLabel(r.month)}</Table.Td>
                  <Table.Td ta="right">${r.due.toFixed(2)}</Table.Td>
                  <Table.Td ta="right">${r.spent.toFixed(2)}</Table.Td>
                  <Table.Td>
                    <Group gap="xs">
                      <Progress value={pct} size="sm" color={over ? 'red' : 'green'} style={{ flex: 1 }} />
                      {over ? (
                        <Badge color="red" variant="light" size="xs">Over</Badge>
                      ) : r.due > 0 ? (
                        <Badge color="green" variant="light" size="xs" leftSection={<CheckCircle2 size={10} />}>Under</Badge>
                      ) : (
                        <Badge color="gray" variant="light" size="xs">—</Badge>
                      )}
                    </Group>
                  </Table.Td>
                </Table.Tr>
              )
            })}
          </Table.Tbody>
        </Table>
      </Paper>
    </Stack>
  )
}

interface ItemsTabProps {
  items: BudgetItem[]
  readOnly: boolean
  compOptions: { value: string; label: string }[]
  onUpdate: (id: string, patch: Partial<BudgetItem>) => void
  onAdd: (category: BudgetCategory) => void
  onRemove: (id: string) => void
  onPhotoUpload: (itemId: string, file: File) => void
  onPhotoDelete: (itemId: string) => void
}

function ItemsTab({ items, readOnly, compOptions, onUpdate, onAdd, onRemove, onPhotoUpload, onPhotoDelete }: ItemsTabProps) {
  return (
    <Stack gap="md">
      <Group>
        {BUDGET_CATEGORY_OPTIONS.map((c) => (
          <Button key={c.value} variant="light" size="sm" leftSection={<Plus size={14} />} onClick={() => onAdd(c.value)} disabled={readOnly}>
            Add {c.label}
          </Button>
        ))}
      </Group>

      {items.length === 0 ? (
        <Paper withBorder p="xl" radius="md">
          <Text c="dimmed" ta="center">No budget items yet. Add equipment, supplements, memberships, or competition costs above.</Text>
        </Paper>
      ) : (
        <Stack gap="sm">
          {items.map((item) => (
            <ItemCard
              key={item.id}
              item={item}
              readOnly={readOnly}
              compOptions={compOptions}
              onUpdate={onUpdate}
              onRemove={onRemove}
              onPhotoUpload={onPhotoUpload}
              onPhotoDelete={onPhotoDelete}
            />
          ))}
        </Stack>
      )}
    </Stack>
  )
}

interface ItemCardProps {
  item: BudgetItem
  readOnly: boolean
  compOptions: { value: string; label: string }[]
  onUpdate: (id: string, patch: Partial<BudgetItem>) => void
  onRemove: (id: string) => void
  onPhotoUpload: (itemId: string, file: File) => void
  onPhotoDelete: (itemId: string) => void
}

function ItemCard({ item, readOnly, compOptions, onUpdate, onRemove, onPhotoUpload, onPhotoDelete }: ItemCardProps) {
  const photoUrl = getMediaUrl(item.photo_s3_key)
  const isEquipment = item.category === 'equipment'
  return (
    <Card withBorder radius="md" padding="md">
      <Group align="flex-start" gap="md" wrap="nowrap">
        <PhotoSlot
          photoUrl={photoUrl}
          readOnly={readOnly}
          onUpload={(file) => onPhotoUpload(item.id, file)}
          onDelete={() => onPhotoDelete(item.id)}
        />
        <Stack gap="xs" style={{ flex: 1, minWidth: 0 }}>
          <Group justify="space-between" gap="sm" wrap="nowrap">
            <TextInput
              placeholder="Item name"
              value={item.name}
              onChange={(e) => onUpdate(item.id, { name: e.currentTarget.value })}
              disabled={readOnly}
              style={{ flex: 1 }}
            />
            <Group gap={6}>
              <Badge color={priorityColor(item.priority)} variant="light">{item.priority.replace('_', ' ')}</Badge>
              <ActionIcon color="red" variant="subtle" onClick={() => onRemove(item.id)} disabled={readOnly} aria-label="Remove item">
                <Trash2 size={16} />
              </ActionIcon>
            </Group>
          </Group>

          <SimpleGrid cols={{ base: 2, sm: 3, md: 4 }} spacing="xs">
            <Select label="Category" size="xs" value={item.category} data={BUDGET_CATEGORY_OPTIONS.map((o) => ({ value: o.value, label: o.label }))} onChange={(v) => onUpdate(item.id, { category: (v as BudgetCategory) ?? 'equipment' })} disabled={readOnly} />
            <Select label="Priority" size="xs" value={item.priority} data={BUDGET_PRIORITY_OPTIONS.map((o) => ({ value: o.value, label: o.label }))} onChange={(v) => onUpdate(item.id, { priority: (v as BudgetPriority) ?? 'optional' })} disabled={readOnly} />
            <Select label="Recurrence" size="xs" value={item.recurrence} data={BUDGET_RECURRENCE_OPTIONS.map((o) => ({ value: o.value, label: o.label }))} onChange={(v) => onUpdate(item.id, { recurrence: (v as BudgetRecurrence) ?? 'one_time' })} disabled={readOnly} />
            <NumberInput label="Cost" size="xs" value={item.cost} onChange={(v) => onUpdate(item.id, { cost: typeof v === 'number' ? v : 0 })} min={0} decimalScale={2} hideControls disabled={readOnly} />
          </SimpleGrid>

          <SimpleGrid cols={{ base: 2, sm: 3, md: 4 }} spacing="xs">
            <TextInput
              label={item.recurrence === 'one_time' ? 'Purchase month' : 'Start month'}
              size="xs"
              placeholder="YYYY-MM"
              value={item.start_month ?? ''}
              onChange={(e) => {
                const v = e.currentTarget.value.trim()
                onUpdate(item.id, { start_month: /^\d{4}-\d{2}$/.test(v) ? v : v ? undefined : undefined })
              }}
              disabled={readOnly}
            />
            {item.recurrence === 'multi_month' && (
              <NumberInput label="Months" size="xs" value={item.months ?? 1} onChange={(v) => onUpdate(item.id, { months: typeof v === 'number' ? v : 1 })} min={1} max={24} disabled={readOnly} />
            )}
            <Select label="For competition" size="xs" value={item.comp_master_id ?? ''} data={compOptions} onChange={(v) => onUpdate(item.id, { comp_master_id: v || undefined })} disabled={readOnly} />
            <Select label="Training priority" size="xs" value={item.training_priority ?? ''} data={[{ value: '', label: '—' }, ...TRAINING_PRIORITY_OPTIONS.map((o) => ({ value: o.value, label: o.label }))]} onChange={(v) => onUpdate(item.id, { training_priority: (v as TrainingPriority) || undefined })} disabled={readOnly} />
          </SimpleGrid>

          {isEquipment && (
            <SimpleGrid cols={{ base: 2, sm: 3 }} spacing="xs">
              <Select label="Condition" size="xs" value={item.equipment_condition ?? 'unknown'} data={EQUIPMENT_CONDITION_OPTIONS.map((o) => ({ value: o.value, label: o.label }))} onChange={(v) => onUpdate(item.id, { equipment_condition: (v as EquipmentCondition) ?? 'unknown' })} disabled={readOnly} />
              <Switch label="Comp-legal" checked={item.equipment_comp_legal ?? false} onChange={(e) => onUpdate(item.id, { equipment_comp_legal: e.currentTarget.checked })} disabled={readOnly} />
            </SimpleGrid>
          )}

          <Group gap="md">
            <Switch
              label="Needed for comp day"
              checked={item.needed_for_comp_day ?? false}
              onChange={(e) => onUpdate(item.id, { needed_for_comp_day: e.currentTarget.checked })}
              disabled={readOnly}
            />
            <Switch
              label="Purchased"
              checked={item.purchased ?? false}
              onChange={(e) => onUpdate(item.id, { purchased: e.currentTarget.checked, purchased_date: e.currentTarget.checked ? new Date().toISOString().slice(0, 10) : null })}
              disabled={readOnly}
            />
          </Group>

          <Textarea label="Notes" size="xs" value={item.notes ?? ''} onChange={(e) => onUpdate(item.id, { notes: e.currentTarget.value })} disabled={readOnly} autosize minRows={1} />
        </Stack>
      </Group>
    </Card>
  )
}

interface PhotoSlotProps {
  photoUrl: string
  readOnly: boolean
  onUpload: (file: File) => void
  onDelete: () => void
}

function PhotoSlot({ photoUrl, readOnly, onUpload, onDelete }: PhotoSlotProps) {
  const { getRootProps, getInputProps, open } = useDropzone({
    multiple: false,
    accept: { 'image/*': [] },
    disabled: readOnly,
    noClick: true,
    onDrop: (files) => { if (files[0]) onUpload(files[0]) },
  })

  return (
    <Box {...getRootProps()} style={{ width: 96, height: 96, flexShrink: 0 }}>
      <input {...getInputProps()} />
      {photoUrl ? (
        <Stack gap={4} align="center">
          <MantineImage src={photoUrl} w={96} h={96} fit="cover" radius="md" />
          {!readOnly && (
            <Group gap={4}>
              <FileButton onChange={(f) => f && onUpload(f)} accept="image/*">
                {(props) => (<ActionIcon {...props} variant="subtle" size="sm" aria-label="Replace photo">
                    <Camera size={14} />
                  </ActionIcon>
                )}
              </FileButton>
              <ActionIcon variant="subtle" color="red" size="sm" onClick={onDelete} aria-label="Remove photo">
                <Trash2 size={14} />
              </ActionIcon>
            </Group>
          )}
        </Stack>
      ) : (
        <Paper withBorder radius="md" w={96} h={96} style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: readOnly ? 'default' : 'pointer' }} onClick={() => !readOnly && open()}>
          <Stack align="center" gap={2}>
            <Camera size={20} />
            <Text size="xs" c="dimmed">Photo</Text>
          </Stack>
        </Paper>
      )}
    </Box>
  )
}

interface FederationTabProps {
  masterFeds: MasterFederation[]
  library: import('@powerlifting/types').FederationLibrary | null
  readOnly: boolean
  coverageGroups: string[][]
  onPay: (fedId: string, paid: boolean, cost: number | null, paidDate: string | null) => void
}

function FederationTab({ masterFeds, library, readOnly, coverageGroups, onPay }: FederationTabProps) {
  const userFeds = library?.federations ?? []
  const fedsWithMeta = useMemo(() => {
    return masterFeds
      .filter((f) => f.status === 'active')
      .map((f) => {
        const userCopy = userFeds.find((u) => u.abbreviation === f.abbreviation || u.name === f.name)
        return { master: f, user: userCopy }
      })
      .filter((x) => x.user)
  }, [masterFeds, userFeds])

  if (!library) {
    return <Text c="dimmed">Loading federations…</Text>
  }

  if (fedsWithMeta.length === 0) {
    return (
      <Paper withBorder p="xl" radius="md">
        <Stack align="center" gap="xs">
          <Text c="dimmed">No federations in your library yet.</Text>
          <Button component={Link} to="/designer/federations" variant="light" size="sm">Manage federations</Button>
        </Stack>
      </Paper>
    )
  }

  return (
    <Stack gap="md">
      {coverageGroups.length > 0 && (
        <Paper withBorder p="sm" radius="md" bg="var(--mantine-color-blue-0)">
          <Text size="sm" fw={500}>Shared memberships</Text>
          <Text size="xs" c="dimmed" mt={2}>Paying one of these covers the others marked as the same membership:</Text>
          <Stack gap={4} mt={6}>
            {coverageGroups.map((group, i) => (
              <Group key={i} gap="xs">
                {group.map((abbr) => (
                  <Badge key={abbr} variant="light" color="blue">{abbr}</Badge>
                ))}
              </Group>
            ))}
          </Stack>
        </Paper>
      )}

      <Table>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>Federation</Table.Th>
            <Table.Th>Parent</Table.Th>
            <Table.Th>Covers</Table.Th>
            <Table.Th>Cost</Table.Th>
            <Table.Th>Paid</Table.Th>
            <Table.Th>Paid date</Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {fedsWithMeta.map(({ master, user }) => {
            if (!user) return null
            const covers = master.membership_group ?? []
            return (
              <Table.Tr key={user.id}>
                <Table.Td>{master.abbreviation ?? master.name}</Table.Td>
                <Table.Td>{master.parent_federation_abbr ?? '—'}</Table.Td>
                <Table.Td>{covers.length ? covers.join(', ') : '—'}</Table.Td>
                <Table.Td>
                  <NumberInput
                    size="xs"
                    value={user.membership_cost ?? 0}
                    onChange={(v) => onPay(user.id, user.membership_paid ?? false, typeof v === 'number' ? v : 0, user.membership_paid_date ?? null)}
                    disabled={readOnly}
                    min={0}
                    decimalScale={2}
                    hideControls
                    w={90}
                  />
                </Table.Td>
                <Table.Td>
                  <Switch
                    checked={user.membership_paid ?? false}
                    onChange={(e) => onPay(user.id, e.currentTarget.checked, user.membership_cost ?? 0, e.currentTarget.checked ? new Date().toISOString().slice(0, 10) : null)}
                    disabled={readOnly}
                  />
                </Table.Td>
                <Table.Td>{user.membership_paid_date ?? '—'}</Table.Td>
              </Table.Tr>
            )
          })}
        </Table.Tbody>
      </Table>

      <Text size="xs" c="dimmed">Federation membership cost & paid status are saved automatically.
    </Text>
    </Stack>
  )
}

interface TimelineTabProps {
  timeline: BudgetTimelineType | null
  loading: boolean
  readOnly: boolean
  onGenerate: () => void
  comps: UserCompetition[]
}

function TimelineTab({ timeline, loading, readOnly, onGenerate, comps }: TimelineTabProps) {
  return (
    <Stack gap="md">
      <Group justify="space-between">
        <Stack gap={2}>
          <Text fw={600}>AI priority timeline</Text>
          <Text size="xs" c="dimmed">Suggests when to buy each item to stay under your monthly cap, prioritising confirmed competitions.</Text>
        </Stack>
        <Button leftSection={loading ? <Loader2 size={16} /> : <Sparkles size={16} />} onClick={onGenerate} loading={loading} disabled={readOnly}>
          Generate timeline
        </Button>
      </Group>

      {comps.length > 0 && (
        <Paper withBorder p="sm" radius="md">
          <Text size="xs" c="dimmed" mb={4}>Competitions driving prioritisation:</Text>
          <Group gap="xs">
            {comps.map((c) => (
              <Badge key={c.master_id} variant="light" color={c.user_status === 'confirmed' ? 'green' : 'gray'} leftSection={<CalendarClock size={10} />}>
                {c.name} · {c.start_date}
              </Badge>
            ))}
          </Group>
        </Paper>
      )}

      {!timeline && !loading && (
        <Paper withBorder p="xl" radius="md">
          <Text c="dimmed" ta="center">No timeline generated yet. Click "Generate timeline" to plan purchases around your budget and competitions.</Text>
        </Paper>
      )}

      {timeline && (
        <Stack gap="md">
          {timeline.notes.length > 0 && (
            <Paper withBorder p="sm" radius="md">
              <Stack gap={4}>
                {timeline.notes.map((n, i) => (
                  <Text key={i} size="sm">• {n}</Text>
                ))}
              </Stack>
            </Paper>
          )}
          {timeline.months.map((m) => (
            <Paper key={m.month} withBorder p="md" radius="md">
              <Group justify="space-between" mb="sm">
                <Text fw={600}>{monthLabel(m.month)}</Text>
                <Group gap="xs">
                  <Text size="xs" c="dimmed">due ${m.due.toFixed(2)}</Text>
                  <Text size="xs" c="dimmed">cap ${m.budget.toFixed(2)}</Text>
                  <Badge color={m.due <= m.budget ? 'green' : 'red'} variant="light" size="xs">
                    {m.due <= m.budget ? 'Under' : 'Over'}
                  </Badge>
                </Group>
              </Group>
              <Timeline bulletSize={20} lineWidth={1}>
                {m.entries.map((e, i) => (
                  <Timeline.Item key={e.item_id + i} title={e.name} bullet={<Badge color={priorityColor(e.priority)} variant="light" size="xs">{e.cost.toFixed(0)}</Badge>}>
                    <Group gap="xs">
                      <Badge color={priorityColor(e.priority)} variant="light" size="xs">{e.priority.replace('_', ' ')}</Badge>
                      <Text size="xs" c="dimmed">{e.category.replace('_', ' ')}</Text>
                    </Group>
                    <Text size="xs" c="dimmed" mt={2}>{e.reason}</Text>
                  </Timeline.Item>
                ))}
              </Timeline>
            </Paper>
          ))}
        </Stack>
      )}
    </Stack>
  )
}
