import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Save, Plus, Trash2, RotateCcw, ChevronDown } from 'lucide-react'
import {
  Accordion,
  ActionIcon,
  Badge,
  Button,
  Card,
  Collapse,
  Group,
  NumberInput,
  Paper,
  Select,
  SimpleGrid,
  Stack,
  Switch,
  Table,
  Text,
  TextInput,
  Title,
  Tooltip,
  UnstyledButton,
} from '@mantine/core'
import { useMediaQuery } from '@mantine/hooks'
import { useUiStore } from '@/store/uiStore'
import { useAuth } from '@/auth/AuthProvider'
import { fetchFederations, updateFederation, FederationUpdatePayload } from '@/api/client'
import {
  AGE_CATEGORY_OPTIONS,
  AGE_CATEGORY_ORDER,
  DEFAULT_FEDERATION_DISPLAY_OPTIONS,
  FEDERATION_LEVEL_OPTIONS,
  type AgeCategory,
  type FederationDisplayOptions,
  type FederationLevel,
  type FederationSex,
  type FederationStandard,
  type FederationStandardEntry,
  type MasterFederation,
} from '@powerlifting/types'
import {
  defaultWeightClassesForSex,
  newEntryId,
} from '@/utils/weightClasses'

const STATUS_OPTIONS = [
  { value: 'active', label: 'Active' },
  { value: 'archived', label: 'Archived' },
]

const UNIT_OPTIONS = [
  { value: 'kg', label: 'Kilograms' },
  { value: 'dots', label: 'DOTS' },
]

const SEX_OPTIONS: ReadonlyArray<{ value: FederationSex; label: string }> = [
  { value: 'male', label: 'Male' },
  { value: 'female', label: 'Female' },
]

function federationStatusColor(status: MasterFederation['status']): string {
  return status === 'active' ? 'blue' : 'gray'
}

function federationId(fed: MasterFederation): string {
  if (typeof fed.sk === 'string' && fed.sk.length > 0) {
    const suffix = fed.sk.replace(/^FED#/, '')
    if (suffix) return suffix
  }
  const pk = typeof fed.pk === 'string' && fed.pk.length > 0 ? fed.pk : 'fed'
  const name = typeof fed.name === 'string' && fed.name.trim().length > 0
    ? fed.name.trim()
    : 'unnamed'
  const skPart = typeof fed.sk === 'string' && fed.sk.length > 0 ? fed.sk : 'no-sk'
  return `${pk}::${skPart}::${name}`
}

function isOperator(mapped_pk: string, readOnly: boolean): boolean {
  return mapped_pk === 'operator' && !readOnly
}

function sortYears(years: string[]): string[] {
  return [...years].sort((a, b) => Number(a) - Number(b))
}

function buildEmptyStandard(): FederationStandard {
  return {
    start_date: '',
    end_date: '',
    entries: [],
  }
}

function levelRank(level: FederationLevel | undefined): number {
  if (level === 'national') return 0
  if (level === 'regional') return 1
  return 2
}

function sexRank(sex: FederationSex | undefined): number {
  if (sex === 'male') return 0
  if (sex === 'female') return 1
  return 2
}

function ageRank(age: AgeCategory | undefined): number {
  if (!age) return 99
  return AGE_CATEGORY_ORDER[age]
}

function sortEntries(entries: FederationStandardEntry[]): FederationStandardEntry[] {
  return [...entries].sort((a, b) => {
    const lr = levelRank(a.level) - levelRank(b.level)
    if (lr !== 0) return lr
    const sr = sexRank(a.sex) - sexRank(b.sex)
    if (sr !== 0) return sr
    const ar = ageRank(a.age_class) - ageRank(b.age_class)
    if (ar !== 0) return ar
    const aw = a.weight_class ?? ''
    const bw = b.weight_class ?? ''
    const an = Number(aw)
    const bn = Number(bw)
    if (Number.isFinite(an) && Number.isFinite(bn) && aw !== '' && bw !== '') {
      if (an !== bn) return an - bn
    } else if (aw !== bw) {
      return aw.localeCompare(bw)
    }
    const ac = a.category ?? ''
    const bc = b.category ?? ''
    if (ac !== bc) return ac.localeCompare(bc)
    return a.qualifying_total - b.qualifying_total
  })
}

function entrySummary(entry: FederationStandardEntry, options: FederationDisplayOptions): string {
  const parts: string[] = []
  if (entry.level) parts.push(entry.level === 'national' ? 'National' : 'Regional')
  if (options.show_sex && entry.sex) parts.push(entry.sex === 'male' ? 'M' : 'F')
  if (options.show_age_class && entry.age_class) {
    const label = AGE_CATEGORY_OPTIONS.find((o) => o.value === entry.age_class)?.label
    if (label) parts.push(label)
  }
  if (options.show_weight_class && entry.weight_class) parts.push(`${entry.weight_class} kg`)
  if (options.show_category && entry.category) parts.push(entry.category)
  return parts.join(' · ') || 'Any'
}

function resolveDisplayOptions(
  pending: FederationUpdatePayload['display_options'],
  fallback: FederationDisplayOptions | undefined,
): FederationDisplayOptions {
  return {
    ...DEFAULT_FEDERATION_DISPLAY_OPTIONS,
    ...(fallback ?? {}),
    ...(pending ?? {}),
  }
}

function defaultEntryFor(sex: FederationSex, weightClass: string): FederationStandardEntry {
  return {
    id: newEntryId(),
    sex,
    weight_class: weightClass,
    qualifying_total: 0,
  }
}

export default function FederationsPage() {
  const { mapped_pk, readOnly } = useAuth()
  const { pushToast } = useUiStore()
  const [federations, setFederations] = useState<MasterFederation[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [pending, setPending] = useState<Record<string, FederationUpdatePayload>>({})
  const [saving, setSaving] = useState<string | null>(null)

  const canEdit = isOperator(mapped_pk, readOnly)

  useEffect(() => {
    fetchFederations()
      .then((feds) => { setFederations(feds); setIsLoading(false) })
      .catch(() => { setIsLoading(false) })
  }, [])

  function setPatch(id: string, patch: Partial<FederationUpdatePayload>) {
    setPending((prev) => ({
      ...prev,
      [id]: { ...prev[id], ...patch },
    }))
  }

  function getField<K extends keyof FederationUpdatePayload>(
    fed: MasterFederation, key: K,
  ): FederationUpdatePayload[K] | undefined {
    return pending[federationId(fed)]?.[key]
  }

  function getStandards(fed: MasterFederation): Record<string, FederationStandard> {
    const fromPending = pending[federationId(fed)]?.standards
    if (fromPending) return fromPending
    return fed.standards
  }

  function updateStandards(
    id: string,
    updater: (current: Record<string, FederationStandard>) => Record<string, FederationStandard>,
  ) {
    const fed = federations.find((f) => federationId(f) === id)
    if (!fed) return
    setPatch(id, { standards: updater(getStandards(fed)) })
  }

  function addYear(id: string) {
    updateStandards(id, (current) => {
      const sorted = sortYears(Object.keys(current ?? {}))
      const next: Record<string, FederationStandard> = { ...current }
      const newYear = sorted.length === 0
        ? new Date().getFullYear()
        : Number(sorted[sorted.length - 1]) + 1
      const yearKey = String(newYear)
      if (!next[yearKey]) {
        next[yearKey] = {
          start_date: `${yearKey}-01-01`,
          end_date: `${yearKey}-12-31`,
          // Start the year with no entries; the operator can hit "Add IPF
          // weight class set" to seed kg brackets, or click "Add standard"
          // for one-off DOTS / category entries.
          entries: [],
        }
      }
      return next
    })
  }

  function removeYear(id: string, year: string) {
    updateStandards(id, (current) => {
      const next = { ...current }
      delete next[year]
      return next
    })
  }

  function updateYearField(
    id: string, year: string, key: 'start_date' | 'end_date', value: string,
  ) {
    updateStandards(id, (current) => {
      const next = { ...current }
      const std = next[year] ?? buildEmptyStandard()
      next[year] = { ...std, [key]: value }
      return next
    })
  }

  function resetYearToDefaults(id: string, year: string) {
    updateStandards(id, (current) => {
      const next = { ...current }
      const std = next[year] ?? buildEmptyStandard()
      next[year] = {
        start_date: std.start_date || `${year}-01-01`,
        end_date: std.end_date || `${year}-12-31`,
        entries: [],
      }
      return next
    })
  }

  function addStandard(id: string, year: string) {
    updateStandards(id, (current) => {
      const next = { ...current }
      const std = next[year] ?? buildEmptyStandard()
      const entry: FederationStandardEntry = {
        id: newEntryId(),
        qualifying_total: 0,
      }
      next[year] = { ...std, entries: [...std.entries, entry] }
      return next
    })
  }

  function addIpfWeightClassSet(id: string, year: string) {
    updateStandards(id, (current) => {
      const next = { ...current }
      const std = next[year] ?? buildEmptyStandard()
      const used = new Set(std.entries.map((e) => `${e.sex ?? ''}::${e.weight_class ?? ''}`))
      const additions: FederationStandardEntry[] = []
      for (const sex of ['male', 'female'] as const) {
        for (const wc of defaultWeightClassesForSex(sex)) {
          const key = `${sex}::${String(wc)}`
          if (used.has(key)) continue
          additions.push(defaultEntryFor(sex, String(wc)))
        }
      }
      if (additions.length === 0) return current
      next[year] = { ...std, entries: [...std.entries, ...additions] }
      return next
    })
  }

  function updateEntry(
    id: string, year: string, entryId: string, patch: Partial<FederationStandardEntry>,
  ) {
    updateStandards(id, (current) => {
      const next = { ...current }
      const std = next[year]
      if (!std) return current
      next[year] = {
        ...std,
        entries: std.entries.map((e) => (e.id === entryId ? { ...e, ...patch } : e)),
      }
      return next
    })
  }

  function removeEntry(id: string, year: string, entryId: string) {
    updateStandards(id, (current) => {
      const next = { ...current }
      const std = next[year]
      if (!std) return current
      next[year] = { ...std, entries: std.entries.filter((e) => e.id !== entryId) }
      return next
    })
  }

  async function handleSave(fed: MasterFederation) {
    const id = federationId(fed)
    const patch = pending[id]
    if (!patch) return
    setSaving(id)
    try {
      // Always sort at save time. No interactive drag-to-reorder — the user
      // just types in the field they care about and we sort on persist.
      const sortedPatch: FederationUpdatePayload = { ...patch }
      if (sortedPatch.standards) {
        const next: Record<string, FederationStandard> = {}
        for (const year of sortYears(Object.keys(sortedPatch.standards ?? {}))) {
          const std = sortedPatch.standards[year]
          next[year] = {
            ...std,
            entries: sortEntries(std.entries ?? []),
          }
        }
        sortedPatch.standards = next
      }
      await updateFederation(id, sortedPatch)
      const fresh = await fetchFederations()
      setFederations(fresh)
      setPending((prev) => {
        const out = { ...prev }
        delete out[id]
        return out
      })
      pushToast({ message: 'Federation updated', type: 'success' })
    } catch {
      pushToast({ message: 'Failed to save federation', type: 'error' })
    } finally {
      setSaving(null)
    }
  }
  return (
    <Stack gap="md">
      <Group justify="space-between">
        <Stack gap={0}>
          <Group gap="xs">
            <Text component={Link} to="/designer" size="sm" c="dimmed" style={{ textDecoration: 'none' }}>Designer</Text>
            <Text c="dimmed">/</Text>
            <Title order={2}>Federations</Title>
          </Group>
          <Text c="dimmed" size="sm" mt={4}>
            Federations are shared globally across all users. Standards are sorted on save — just edit the fields and click Save.
          </Text>
        </Stack>
      </Group>

      {isLoading ? (
        <Paper withBorder p="xl">
          <Group justify="center">
            <Text c="dimmed">Loading federations...</Text>
          </Group>
        </Paper>
      ) : federations.length === 0 ? (
        <Paper withBorder p="lg">
          <Text size="sm" c="dimmed">No federations found.</Text>
        </Paper>
      ) : (
        <Accordion variant="separated">
          {federations.map((fed) => (
            <FederationAccordionItem
              key={federationId(fed)}
              fed={fed}
              canEdit={canEdit}
              hasChanges={pending[federationId(fed)] !== undefined}
              saving={saving === federationId(fed)}
              pendingName={getField(fed, 'name')}
              pendingAbbrev={getField(fed, 'abbreviation')}
              pendingRegion={getField(fed, 'region')}
              pendingWebsite={getField(fed, 'website_url')}
              pendingStatus={getField(fed, 'status')}
              pendingHasStd={getField(fed, 'has_standards')}
              pendingUnit={getField(fed, 'standard_unit')}
              pendingDisplayOptions={getField(fed, 'display_options')}
              standards={getStandards(fed)}
              onPatch={(patch) => setPatch(federationId(fed), patch)}
              onAddYear={() => addYear(federationId(fed))}
              onRemoveYear={(y) => removeYear(federationId(fed), y)}
              onResetYear={(y) => resetYearToDefaults(federationId(fed), y)}
              onUpdateYearField={(y, k, v) => updateYearField(federationId(fed), y, k, v)}
              onAddStandard={(y) => addStandard(federationId(fed), y)}
              onAddIpfWeightClassSet={(y) => addIpfWeightClassSet(federationId(fed), y)}
              onUpdateEntry={(y, entryId, patch) => updateEntry(federationId(fed), y, entryId, patch)}
              onRemoveEntry={(y, entryId) => removeEntry(federationId(fed), y, entryId)}
              onSave={() => handleSave(fed)}
            />
          ))}
        </Accordion>
      )}
    </Stack>
  )
}

interface FederationAccordionItemProps {
  fed: MasterFederation
  canEdit: boolean
  hasChanges: boolean
  saving: boolean
  pendingName: FederationUpdatePayload['name']
  pendingAbbrev: FederationUpdatePayload['abbreviation']
  pendingRegion: FederationUpdatePayload['region']
  pendingWebsite: FederationUpdatePayload['website_url']
  pendingStatus: FederationUpdatePayload['status']
  pendingHasStd: FederationUpdatePayload['has_standards']
  pendingUnit: FederationUpdatePayload['standard_unit']
  pendingDisplayOptions: FederationUpdatePayload['display_options']
  standards: Record<string, FederationStandard>
  onPatch: (patch: Partial<FederationUpdatePayload>) => void
  onAddYear: () => void
  onRemoveYear: (year: string) => void
  onResetYear: (year: string) => void
  onUpdateYearField: (year: string, key: 'start_date' | 'end_date', value: string) => void
  onAddStandard: (year: string) => void
  onAddIpfWeightClassSet: (year: string) => void
  onUpdateEntry: (year: string, entryId: string, patch: Partial<FederationStandardEntry>) => void
  onRemoveEntry: (year: string, entryId: string) => void
  onSave: () => void
}

function FederationAccordionItem(props: FederationAccordionItemProps) {
  const {
    fed, canEdit, hasChanges, saving,
    pendingName, pendingAbbrev, pendingRegion, pendingWebsite, pendingStatus, pendingHasStd, pendingUnit,
    pendingDisplayOptions,
    standards, onPatch,
    onAddYear, onRemoveYear, onResetYear, onUpdateYearField,
    onAddStandard, onAddIpfWeightClassSet, onUpdateEntry, onRemoveEntry,
    onSave,
  } = props

  const id = federationId(fed)
  const name = pendingName ?? fed.name
  const abbreviation = pendingAbbrev !== undefined ? pendingAbbrev : fed.abbreviation
  const region = pendingRegion !== undefined ? pendingRegion : fed.region
  const website = pendingWebsite !== undefined ? pendingWebsite : fed.website_url
  const status = pendingStatus ?? fed.status
  const hasStandards = pendingHasStd ?? fed.has_standards
  const standardUnit = pendingUnit !== undefined ? pendingUnit : fed.standard_unit
  const displayOptions = resolveDisplayOptions(pendingDisplayOptions, fed.display_options)
  const yearKeys = sortYears(Object.keys(standards ?? {}))

  return (
    <Accordion.Item value={id}>
      <Accordion.Control>
        <Group gap="sm" wrap="nowrap">
          <Badge variant="light" color={federationStatusColor(status)}>
            {status}
          </Badge>
          <Stack gap={0}>
            <Text fw={500}>{abbreviation || name}</Text>
            <Text size="xs" c="dimmed">{name}</Text>
          </Stack>
          {hasChanges && (
            <Badge variant="filled" color="yellow" size="sm">Unsaved</Badge>
          )}
        </Group>
      </Accordion.Control>
      <Accordion.Panel>
        <Stack gap="md">
          <SimpleGrid cols={{ base: 1, sm: 2, lg: 4 }}>
            <TextInput
              label="Name"
              value={name}
              onChange={(e) => onPatch({ name: e.currentTarget.value })}
              disabled={!canEdit}
            />
            <TextInput
              label="Abbreviation"
              value={abbreviation || ''}
              onChange={(e) => onPatch({ abbreviation: e.currentTarget.value || null })}
              disabled={!canEdit}
            />
            <TextInput
              label="Region"
              description="ISO country code (e.g. US, GB, CA) or 'global'"
              value={region || ''}
              onChange={(e) => onPatch({ region: e.currentTarget.value || null })}
              disabled={!canEdit}
            />
            <Select
              label="Status"
              data={STATUS_OPTIONS}
              value={status}
              onChange={(v) => v && onPatch({ status: v as 'active' | 'archived' })}
              disabled={!canEdit}
            />
          </SimpleGrid>
          <TextInput
            label="Website"
            value={website || ''}
            onChange={(e) => onPatch({ website_url: e.currentTarget.value || null })}
            disabled={!canEdit}
          />

          <Group gap="lg" align="end">
            <Switch
              label="Has qualifying standards"
              checked={hasStandards}
              onChange={(e) => {
                const next = e.currentTarget.checked
                onPatch({
                  has_standards: next,
                  standard_unit: next ? (standardUnit || 'kg') : null,
                  standards: next ? standards : {},
                })
              }}
              disabled={!canEdit}
            />
            {hasStandards && (
              <Select
                label="Standard unit"
                data={UNIT_OPTIONS}
                value={standardUnit || 'kg'}
                onChange={(v) => v && onPatch({ standard_unit: v as 'kg' | 'dots' })}
                disabled={!canEdit}
              />
            )}
          </Group>

          {hasStandards && (
            <Stack gap={4}>
              <Text size="xs" c="dimmed">Visible columns</Text>
              <Group gap="lg" wrap="wrap">
                <Switch
                  size="xs"
                  label="Sex"
                  checked={displayOptions.show_sex}
                  onChange={(e) => onPatch({ display_options: { ...displayOptions, show_sex: e.currentTarget.checked } })}
                  disabled={!canEdit}
                />
                <Switch
                  size="xs"
                  label="Age class"
                  checked={displayOptions.show_age_class}
                  onChange={(e) => onPatch({ display_options: { ...displayOptions, show_age_class: e.currentTarget.checked } })}
                  disabled={!canEdit}
                />
                <Switch
                  size="xs"
                  label="Weight class"
                  checked={displayOptions.show_weight_class}
                  onChange={(e) => onPatch({ display_options: { ...displayOptions, show_weight_class: e.currentTarget.checked } })}
                  disabled={!canEdit}
                />
                <Switch
                  size="xs"
                  label="Category"
                  checked={displayOptions.show_category}
                  onChange={(e) => onPatch({ display_options: { ...displayOptions, show_category: e.currentTarget.checked } })}
                  disabled={!canEdit}
                />
              </Group>
            </Stack>
          )}

          {hasStandards && (
            <Stack gap="sm">
              <Group justify="space-between">
                <Text fw={500} size="sm">Qualifying standards</Text>
                {canEdit && (
                  <Button size="xs" variant="light" leftSection={<Plus size={14} />} onClick={onAddYear}>
                    Add year
                  </Button>
                )}
              </Group>

              {yearKeys.length === 0 ? (
                <Text size="sm" c="dimmed">No years defined.</Text>
              ) : (
                yearKeys.map((year) => (
                  <YearEditor
                    key={year}
                    year={year}
                    standard={standards[year]}
                    canEdit={canEdit}
                    displayOptions={displayOptions}
                    onRemove={() => onRemoveYear(year)}
                    onReset={() => onResetYear(year)}
                    onUpdateField={(k, v) => onUpdateYearField(year, k, v)}
                    onAddStandard={() => onAddStandard(year)}
                    onAddIpfWeightClassSet={() => onAddIpfWeightClassSet(year)}
                    onUpdateEntry={(entryId, patch) => onUpdateEntry(year, entryId, patch)}
                    onRemoveEntry={(entryId) => onRemoveEntry(year, entryId)}
                  />
                ))
              )}
            </Stack>
          )}

          {canEdit && (
            <Group justify="flex-end">
              <Button
                leftSection={<Save size={16} />}
                onClick={onSave}
                disabled={!hasChanges || saving}
              >
                {saving ? 'Saving...' : 'Save'}
              </Button>
            </Group>
          )}
        </Stack>
      </Accordion.Panel>
    </Accordion.Item>
  )
}

interface YearEditorProps {
  year: string
  standard: FederationStandard
  canEdit: boolean
  displayOptions: FederationDisplayOptions
  onRemove: () => void
  onReset: () => void
  onUpdateField: (key: 'start_date' | 'end_date', value: string) => void
  onAddStandard: () => void
  onAddIpfWeightClassSet: () => void
  onUpdateEntry: (entryId: string, patch: Partial<FederationStandardEntry>) => void
  onRemoveEntry: (entryId: string) => void
}

function YearEditor(props: YearEditorProps) {
  const {
    year, standard, canEdit, displayOptions,
    onRemove, onReset, onUpdateField,
    onAddStandard, onAddIpfWeightClassSet, onUpdateEntry, onRemoveEntry,
  } = props

  const entries = standard.entries ?? []

  return (
    <Paper withBorder p="sm">
      <Group justify="space-between" mb="xs">
        <Text fw={500}>{year}</Text>
        {canEdit && (
          <Group gap="xs">
            <Tooltip label="Clear every standard row in this year">
              <Button
                size="xs"
                variant="subtle"
                leftSection={<RotateCcw size={12} />}
                onClick={onReset}
              >
                Clear year
              </Button>
            </Tooltip>
            <ActionIcon
              variant="subtle"
              color="red"
              onClick={onRemove}
              aria-label={`Remove year ${year}`}
            >
              <Trash2 size={16} />
            </ActionIcon>
          </Group>
        )}
      </Group>
      <SimpleGrid cols={{ base: 1, sm: 2 }}>
        <TextInput
          label="Start date"
          type="date"
          value={standard.start_date}
          onChange={(e) => onUpdateField('start_date', e.currentTarget.value)}
          disabled={!canEdit}
        />
        <TextInput
          label="End date"
          type="date"
          value={standard.end_date}
          onChange={(e) => onUpdateField('end_date', e.currentTarget.value)}
          disabled={!canEdit}
        />
      </SimpleGrid>

      {canEdit && (
        <Group mt="sm" gap="xs">
          <Button
            size="xs"
            variant="light"
            leftSection={<Plus size={12} />}
            onClick={onAddStandard}
          >
            Add standard
          </Button>
          <Button
            size="xs"
            variant="light"
            onClick={onAddIpfWeightClassSet}
            title="Seed one row per default IPF weight class for both male and female"
          >
            Add IPF weight class set
          </Button>
        </Group>
      )}

      <EntriesEditor
        entries={entries}
        canEdit={canEdit}
        displayOptions={displayOptions}
        onUpdate={onUpdateEntry}
        onRemove={onRemoveEntry}
      />
    </Paper>
  )
}

interface EntriesEditorProps {
  entries: FederationStandardEntry[]
  canEdit: boolean
  displayOptions: FederationDisplayOptions
  onUpdate: (entryId: string, patch: Partial<FederationStandardEntry>) => void
  onRemove: (entryId: string) => void
}

function EntriesEditor(props: EntriesEditorProps) {
  const { entries, canEdit, displayOptions, onUpdate, onRemove } = props
  const isMobile = useMediaQuery('(max-width: 768px)')
  const [expanded, setExpanded] = useState<string | null>(null)

  if (entries.length === 0) {
    return (
      <Text size="sm" c="dimmed" mt="sm">
        No standards yet. Use the buttons above to add a single standard or seed the IPF weight class set.
      </Text>
    )
  }

  if (isMobile) {
    return (
      <Stack gap="xs" mt="sm">
        {entries.map((entry) => (
          <EntryCard
            key={entry.id}
            entry={entry}
            canEdit={canEdit}
            displayOptions={displayOptions}
            isExpanded={expanded === entry.id}
            onToggle={() => setExpanded(expanded === entry.id ? null : entry.id)}
            onUpdate={(patch) => onUpdate(entry.id, patch)}
            onRemove={() => onRemove(entry.id)}
          />
        ))}
      </Stack>
    )
  }

  return (
    <Table.ScrollContainer
      minWidth={120 + [displayOptions.show_sex, displayOptions.show_age_class, displayOptions.show_weight_class, displayOptions.show_category].filter(Boolean).length * 110}
      mt="sm"
    >
      <Table withTableBorder withColumnBorders striped highlightOnHover>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>Level</Table.Th>
            {displayOptions.show_sex && <Table.Th>Sex</Table.Th>}
            {displayOptions.show_age_class && <Table.Th>Age</Table.Th>}
            {displayOptions.show_weight_class && <Table.Th>Weight class</Table.Th>}
            {displayOptions.show_category && <Table.Th>Category</Table.Th>}
            <Table.Th>Total</Table.Th>
            {canEdit && <Table.Th style={{ width: 40 }}></Table.Th>}
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {entries.map((entry) => (
            <EntryTableRow
              key={entry.id}
              entry={entry}
              canEdit={canEdit}
              displayOptions={displayOptions}
              onUpdate={(patch) => onUpdate(entry.id, patch)}
              onRemove={() => onRemove(entry.id)}
            />
          ))}
        </Table.Tbody>
      </Table>
    </Table.ScrollContainer>
  )
}

interface EntryTableRowProps {
  entry: FederationStandardEntry
  canEdit: boolean
  displayOptions: FederationDisplayOptions
  onUpdate: (patch: Partial<FederationStandardEntry>) => void
  onRemove: () => void
}

function EntryTableRow(props: EntryTableRowProps) {
  const { entry, canEdit, displayOptions, onUpdate, onRemove } = props
  return (
    <Table.Tr>
      <Table.Td>
        <Select
          size="xs"
          data={[
            { value: '', label: 'Any' },
            ...FEDERATION_LEVEL_OPTIONS,
          ]}
          value={entry.level ?? ''}
          onChange={(v) => onUpdate({ level: (v || undefined) as FederationLevel | undefined })}
          disabled={!canEdit}
        />
      </Table.Td>
      {displayOptions.show_sex && (
        <Table.Td>
          <Select
            size="xs"
            data={[
              { value: '', label: 'Any' },
              ...SEX_OPTIONS,
            ]}
            value={entry.sex ?? ''}
            onChange={(v) => onUpdate({ sex: (v || undefined) as FederationSex | undefined })}
            disabled={!canEdit}
          />
        </Table.Td>
      )}
      {displayOptions.show_age_class && (
        <Table.Td>
          <Select
            size="xs"
            data={[
              { value: '', label: 'Any' },
              ...AGE_CATEGORY_OPTIONS.map((o) => ({ value: o.value, label: o.label })),
            ]}
            value={entry.age_class ?? ''}
            onChange={(v) => onUpdate({ age_class: (v || undefined) as AgeCategory | undefined })}
            disabled={!canEdit}
          />
        </Table.Td>
      )}
      {displayOptions.show_weight_class && (
        <Table.Td>
          <TextInput
            size="xs"
            value={entry.weight_class ?? ''}
            onChange={(e) => onUpdate({ weight_class: e.currentTarget.value || undefined })}
            disabled={!canEdit}
            placeholder="any"
          />
        </Table.Td>
      )}
      {displayOptions.show_category && (
        <Table.Td>
          <TextInput
            size="xs"
            value={entry.category ?? ''}
            onChange={(e) => onUpdate({ category: e.currentTarget.value || undefined })}
            disabled={!canEdit}
            placeholder="beginner, elite…"
          />
        </Table.Td>
      )}
      <Table.Td>
        <NumberInput
          size="xs"
          min={0}
          step={0.5}
          value={entry.qualifying_total}
          onChange={(v) => onUpdate({ qualifying_total: typeof v === 'number' ? v : (v === '' ? 0 : Number(v) || 0) })}
          disabled={!canEdit}
        />
      </Table.Td>
      {canEdit && (
        <Table.Td>
          <ActionIcon
            variant="subtle"
            color="red"
            onClick={onRemove}
            aria-label="Remove standard"
          >
            <Trash2 size={14} />
          </ActionIcon>
        </Table.Td>
      )}
    </Table.Tr>
  )
}

interface EntryCardProps {
  entry: FederationStandardEntry
  canEdit: boolean
  displayOptions: FederationDisplayOptions
  isExpanded: boolean
  onToggle: () => void
  onUpdate: (patch: Partial<FederationStandardEntry>) => void
  onRemove: () => void
}

function EntryCard(props: EntryCardProps) {
  const { entry, canEdit, displayOptions, isExpanded, onToggle, onUpdate, onRemove } = props
  const summary = entrySummary(entry, displayOptions)
  return (
    <Card withBorder padding={0}>
      <UnstyledButton
        w="100%"
        p="sm"
        onClick={onToggle}
        aria-expanded={isExpanded}
        aria-controls={`entry-card-${entry.id}`}
      >
        <Group justify="space-between" wrap="nowrap">
          <Group gap="xs" wrap="nowrap">
            <Text fw={600}>{summary}</Text>
            <Text size="sm" c="dimmed">· Total: {entry.qualifying_total}</Text>
          </Group>
          <Group gap="xs" wrap="nowrap">
            {canEdit && (
              <ActionIcon
                variant="subtle"
                color="red"
                onClick={(e) => {
                  e.stopPropagation()
                  onRemove()
                }}
                aria-label="Remove standard"
              >
                <Trash2 size={14} />
              </ActionIcon>
            )}
            <ChevronDown
              size={16}
              style={{
                transform: isExpanded ? 'rotate(180deg)' : 'rotate(0deg)',
                transition: 'transform 150ms ease',
              }}
            />
          </Group>
        </Group>
      </UnstyledButton>
      <Collapse expanded={isExpanded}>
        <Stack gap="xs" p="sm" pt={0} id={`entry-card-${entry.id}`}>
          <Select
            label="Level"
            size="xs"
            data={[
              { value: '', label: 'Any' },
              ...FEDERATION_LEVEL_OPTIONS,
            ]}
            value={entry.level ?? ''}
            onChange={(v) => onUpdate({ level: (v || undefined) as FederationLevel | undefined })}
            disabled={!canEdit}
          />
          {displayOptions.show_sex && (
            <Select
              label="Sex"
              size="xs"
              data={[
                { value: '', label: 'Any' },
                ...SEX_OPTIONS,
              ]}
              value={entry.sex ?? ''}
              onChange={(v) => onUpdate({ sex: (v || undefined) as FederationSex | undefined })}
              disabled={!canEdit}
            />
          )}
          {displayOptions.show_age_class && (
            <Select
              label="Age category"
              size="xs"
              data={[
                { value: '', label: 'Any' },
                ...AGE_CATEGORY_OPTIONS.map((o) => ({ value: o.value, label: o.label })),
              ]}
              value={entry.age_class ?? ''}
              onChange={(v) => onUpdate({ age_class: (v || undefined) as AgeCategory | undefined })}
              disabled={!canEdit}
            />
          )}
          {displayOptions.show_weight_class && (
            <TextInput
              label="Weight class"
              size="xs"
              value={entry.weight_class ?? ''}
              onChange={(e) => onUpdate({ weight_class: e.currentTarget.value || undefined })}
              disabled={!canEdit}
              placeholder="any"
            />
          )}
          {displayOptions.show_category && (
            <TextInput
              label="Category"
              size="xs"
              value={entry.category ?? ''}
              onChange={(e) => onUpdate({ category: e.currentTarget.value || undefined })}
              disabled={!canEdit}
              placeholder="beginner, elite…"
            />
          )}
          <NumberInput
            label="Qualifying total"
            size="xs"
            min={0}
            step={0.5}
            value={entry.qualifying_total}
            onChange={(v) => onUpdate({ qualifying_total: typeof v === 'number' ? v : (v === '' ? 0 : Number(v) || 0) })}
            disabled={!canEdit}
          />
        </Stack>
      </Collapse>
    </Card>
  )
}
