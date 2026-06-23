import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { Plus, Save, Target, Trash2 } from 'lucide-react'
import {
  Accordion,
  Alert,
  Badge,
  Button,
  Group,
  MultiSelect,
  NumberInput,
  Paper,
  Select,
  SimpleGrid,
  Stack,
  Text,
  Textarea,
  Title,
} from '@mantine/core'
import { DatePickerInput } from '@mantine/dates'
import * as api from '@/api/client'
import {
  AGE_CATEGORY_OPTIONS,
  GOAL_PRIORITY_OPTIONS,
  GOAL_TYPE_OPTIONS,
  TARGET_COMPETITION_STATUSES,
  type AgeCategory,
  type AthleteGoal,
  type FederationStandardEntry,
  type GoalPriority,
  type GoalType,
  type MasterFederation,
  type UserCompetition,
} from '@powerlifting/types'
import { useProgramStore } from '@/store/programStore'
import { useCompetitionsStore } from '@/store/competitionsStore'
import { useUiStore } from '@/store/uiStore'
import { useAuth } from '@/auth/AuthProvider'

const WEIGHT_CLASS_PRESETS: ReadonlyArray<{ value: string; label: string }> = [
  { value: '53', label: '53 kg (women)' },
  { value: '57', label: '57 kg' },
  { value: '59', label: '59 kg' },
  { value: '63', label: '63 kg' },
  { value: '66', label: '66 kg' },
  { value: '69', label: '69 kg' },
  { value: '72', label: '72 kg' },
  { value: '74', label: '74 kg' },
  { value: '76', label: '76 kg' },
  { value: '83', label: '83 kg' },
  { value: '84', label: '84 kg' },
  { value: '93', label: '93 kg' },
  { value: '105', label: '105 kg' },
  { value: '120', label: '120 kg' },
  { value: '120+', label: '120+ kg' },
]

function newGoalId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  return `goal-${Date.now().toString(36)}-${Math.floor(Math.random() * 1e9).toString(36)}`
}

function makeGoal(): AthleteGoal {
  return {
    id: newGoalId(),
    title: 'New Goal',
    goal_type: 'hit_total',
    priority: 'secondary',
  }
}

function goalTypeLabel(type: GoalType): string {
  return GOAL_TYPE_OPTIONS.find((o) => o.value === type)?.label ?? type
}

function priorityColor(priority: GoalPriority): string {
  if (priority === 'primary') return 'red'
  if (priority === 'secondary') return 'blue'
  return 'gray'
}

function competitionLabel(comp: UserCompetition): string {
  const venue = [comp.venue_city, comp.venue_state, comp.venue_country].filter(Boolean).join(', ')
  const dateLabel = comp.start_date || ''
  return `${comp.name} • ${dateLabel}${venue ? ` • ${venue}` : ''}`
}

function federationKey(fed: MasterFederation): string {
  if (typeof fed.sk === 'string' && fed.sk.length > 0) {
    const suffix = fed.sk.replace(/^FED#/, '')
    if (suffix) return suffix
  }
  return fed.pk || fed.name
}

function federationsToOptions(federations: MasterFederation[]): Array<{ value: string; label: string }> {
  return federations
    .filter((f) => f.status === 'active')
    .map((f) => ({
      value: federationKey(f),
      label: f.abbreviation ? `${f.abbreviation} • ${f.name}` : f.name,
    }))
}

function findFederationByKey(federations: MasterFederation[], key: string): MasterFederation | null {
  return federations.find((f) => federationKey(f) === key) ?? null
}

function findFederationStandard(
  fed: MasterFederation | null,
  weightClassKg: number | null | undefined,
  ageClass: AgeCategory,
): FederationStandardEntry | null {
  if (!fed || !fed.has_standards) return null
  for (const year of Object.keys(fed.standards)) {
    const standard = fed.standards[year]
    const entries = standard.entries ?? []
    const targetWc = weightClassKg ? String(weightClassKg) : null
    const matches = entries.find((entry) => {
      if (entry.age_class && entry.age_class !== ageClass) return false
      if (targetWc && entry.weight_class !== targetWc) return false
      return true
    })
    if (matches) return matches
  }
  return null
}

function findFederationStandardsForClasses(
  fed: MasterFederation | null,
  weightClassesKg: number[],
  ageClass: AgeCategory,
): FederationStandardEntry[] {
  if (!fed || !fed.has_standards) return []
  const out: FederationStandardEntry[] = []
  for (const wc of weightClassesKg) {
    const entry = findFederationStandard(fed, wc, ageClass)
    if (entry) out.push(entry)
  }
  return out
}

export default function GoalsPage() {
  const { readOnly, age_class: authAgeClass, ranking_country, ranking_region } = useAuth()
  const { updateGoals } = useProgramStore()
  const { pushToast } = useUiStore()
  const { competitions, loadAll: loadCompetitions } = useCompetitionsStore()
  const [goals, setGoals] = useState<AthleteGoal[]>([])
  const [hasChanges, setHasChanges] = useState(false)
  const [federations, setFederations] = useState<MasterFederation[]>([])
  const [loadingFederations, setLoadingFederations] = useState(false)

  const effectiveAgeClass: AgeCategory = authAgeClass || 'open'

  useEffect(() => {
    let cancelled = false
    api.fetchGoals()
      .then((rows) => {
        if (cancelled) return
        setGoals(rows)
        setHasChanges(false)
      })
      .catch(() => {
        if (!cancelled) setGoals([])
      })
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    loadCompetitions({ country: ranking_country ?? undefined, state: ranking_region ?? undefined })
  }, [loadCompetitions, ranking_country, ranking_region])

  useEffect(() => {
    let cancelled = false
    setLoadingFederations(true)
    api.fetchFederations({ country: ranking_country ?? undefined })
      .then((rows) => {
        if (cancelled) return
        setFederations(rows)
      })
      .catch(() => {
        if (!cancelled) setFederations([])
      })
      .finally(() => {
        if (!cancelled) setLoadingFederations(false)
      })
    return () => {
      cancelled = true
    }
  }, [ranking_country])

  const targetableCompetitions = useMemo(() => {
    return [...competitions]
      .filter((c) => (TARGET_COMPETITION_STATUSES as ReadonlyArray<string>).includes(c.user_status))
      .sort((a, b) => (a.start_date || '').localeCompare(b.start_date || ''))
  }, [competitions])

  const competitionOptions = useMemo(() => {
    return targetableCompetitions.map((c) => ({
      value: c.master_id,
      label: competitionLabel(c),
    }))
  }, [targetableCompetitions])

  const federationOptions = useMemo(() => federationsToOptions(federations), [federations])

  function updateGoal(goalId: string, patch: Partial<AthleteGoal>) {
    setGoals((current) => current.map((g) => (g.id === goalId ? { ...g, ...patch } : g)))
    setHasChanges(true)
  }

  function addGoal() {
    setGoals((current) => [...current, makeGoal()])
    setHasChanges(true)
  }

  function removeGoal(goalId: string) {
    setGoals((current) => current.filter((g) => g.id !== goalId))
    setHasChanges(true)
  }

  async function handleSave() {
    try {
      await api.updateGoals(goals)
      await updateGoals(goals)
      setHasChanges(false)
      pushToast({ message: 'Goals saved', type: 'success' })
    } catch {
      pushToast({ message: 'Failed to save goals', type: 'error' })
    }
  }

  function changeGoalType(goalId: string, nextType: GoalType) {
    setGoals((current) => current.map((g) => {
      if (g.id !== goalId) return g
      const next: AthleteGoal = { id: g.id, title: g.title, goal_type: nextType, priority: g.priority }
      if (nextType === 'qualify_for_federation') {
        next.age_class = g.age_class ?? effectiveAgeClass
        next.target_weight_class_kg = g.target_weight_class_kg
        next.target_federation_ids = g.target_federation_ids
      } else if (nextType === 'hit_total' || nextType === 'conservative_pr') {
        next.target_total_kg = g.target_total_kg
        next.target_weight_class_kg = g.target_weight_class_kg
      } else if (nextType === 'peak_for_meet' || nextType === 'competition_exposure') {
        next.target_competition_ids = g.target_competition_ids
      } else if (nextType === 'improve_dots') {
        next.target_dots = g.target_dots
      } else if (nextType === 'improve_ipf_gl') {
        next.target_ipf_gl = g.target_ipf_gl
      } else if (nextType === 'custom') {
        next.notes = g.notes
      }
      next.target_date = g.target_date
      return next
    }))
    setHasChanges(true)
  }

  return (
    <Stack gap="md">
      <Group justify="space-between">
        <Stack gap={0}>
          <Group gap="xs">
            <Text component={Link} to="/designer" size="sm" c="dimmed" style={{ textDecoration: 'none' }}>
              Designer
            </Text>
            <Text c="dimmed">/</Text>
            <Title order={2}>Goals</Title>
          </Group>
          <Text c="dimmed" size="sm" mt={4}>
            Formalize what this block is trying to accomplish so the analysis can evaluate the right target.
          </Text>
        </Stack>
        <Group gap="sm">
          {hasChanges && (
            <Button leftSection={<Save size={16} />} onClick={handleSave} disabled={readOnly}>
              Save
            </Button>
          )}
          <Button variant="default" leftSection={<Plus size={16} />} onClick={addGoal} disabled={readOnly}>
            Add Goal
          </Button>
        </Group>
      </Group>

      <Paper withBorder p="md">
        <Text size="sm" c="dimmed">
          Each goal shows only the fields that matter for its type. Target competitions are limited to ones you have marked as optional, confirmed, completed, or skipped. Federation lookups use the country and state from your ranking settings and your IPF age class.
        </Text>
        {readOnly && (
          <Text size="sm" mt="xs" c="dimmed">
            You are browsing as a guest. Fields are read-only.
          </Text>
        )}
      </Paper>

      {goals.length === 0 ? (
        <Paper withBorder p="xl">
          <Stack gap="xs" align="center">
            <Target size={20} />
            <Text fw={500}>No explicit goals yet</Text>
            <Text size="sm" c="dimmed" ta="center">
              Add a goal to set a target for analysis. Custom goals are just free-form notes.
            </Text>
          </Stack>
        </Paper>
      ) : (
        <Accordion variant="separated">
          {goals.map((goal) => (
            <Accordion.Item key={goal.id} value={goal.id}>
              <Accordion.Control>
                <Group gap="sm" wrap="nowrap">
                  <Badge color={priorityColor(goal.priority)} variant="light">
                    {goal.priority}
                  </Badge>
                  <Stack gap={0}>
                    <Text fw={500}>{goal.title || 'Untitled goal'}</Text>
                    <Text size="xs" c="dimmed">{goalTypeLabel(goal.goal_type)}</Text>
                  </Stack>
                </Group>
              </Accordion.Control>
              <Accordion.Panel>
                <Stack gap="md">
                  <SimpleGrid cols={{ base: 1, sm: 2, lg: 4 }}>
                    <Textarea
                      label="Title"
                      value={goal.title}
                      onChange={(event) => updateGoal(goal.id, { title: event.currentTarget.value })}
                      disabled={readOnly}
                      autosize
                      minRows={1}
                      maxRows={2}
                    />
                    <Select
                      label="Goal Type"
                      data={GOAL_TYPE_OPTIONS.map((o) => ({ value: o.value, label: o.label }))}
                      value={goal.goal_type}
                      onChange={(value) => value && changeGoalType(goal.id, value as GoalType)}
                      disabled={readOnly}
                    />
                    <Select
                      label="Priority"
                      data={GOAL_PRIORITY_OPTIONS.map((o) => ({ value: o.value, label: o.label }))}
                      value={goal.priority}
                      onChange={(value) => value && updateGoal(goal.id, { priority: value as GoalPriority })}
                      disabled={readOnly}
                    />
                    <DatePickerInput
                      clearable
                      label="Target Date"
                      value={goal.target_date ? new Date(goal.target_date) : null}
                      onChange={(value) => {
                        if (!value) {
                          updateGoal(goal.id, { target_date: undefined })
                          return
                        }
                        const raw = value as Date | string
                        const date = typeof raw === 'string' ? new Date(raw) : raw
                        if (!Number.isNaN(date.getTime())) {
                          updateGoal(goal.id, { target_date: date.toISOString().slice(0, 10) })
                        }
                      }}
                      disabled={readOnly}
                    />
                  </SimpleGrid>

                  {(goal.goal_type === 'hit_total' || goal.goal_type === 'conservative_pr') && (
                    <SimpleGrid cols={{ base: 1, sm: 2 }}>
                      <NumberInput
                        label="Target Total (kg)"
                        value={goal.target_total_kg ?? ''}
                        onChange={(value) => updateGoal(goal.id, { target_total_kg: typeof value === 'number' ? value : undefined })}
                        min={0}
                        step={0.5}
                        disabled={readOnly}
                      />
                      <MultiSelect
                        label="Target Weight Classes (kg)"
                        data={WEIGHT_CLASS_PRESETS.map((o) => ({ value: o.value, label: o.label }))}
                        value={(goal.target_weight_class_kg ?? []).map((w) => String(w))}
                        onChange={(value) => updateGoal(goal.id, { target_weight_class_kg: value.map(Number).filter((n) => Number.isFinite(n) && n > 0) })}
                        searchable
                        clearable
                        disabled={readOnly}
                      />
                    </SimpleGrid>
                  )}

                  <MultiSelect
                    label="Target Competitions"
                    description="Optional, completed, or skipped only. Same country/state filter as the competitions page."
                    data={competitionOptions}
                    value={goal.target_competition_ids ?? []}
                    onChange={(value) => updateGoal(goal.id, { target_competition_ids: value })}
                    searchable
                    clearable
                    disabled={readOnly}
                    nothingFoundMessage={targetableCompetitions.length === 0 ? 'No competitions match your country and state filter.' : 'No matches'}
                  />

                  {goal.goal_type === 'improve_dots' && (
                    <NumberInput
                      label="Target DOTS"
                      value={goal.target_dots ?? ''}
                      onChange={(value) => updateGoal(goal.id, { target_dots: typeof value === 'number' ? value : undefined })}
                      min={0}
                      step={0.1}
                      decimalScale={2}
                      disabled={readOnly}
                    />
                  )}

                  {goal.goal_type === 'improve_ipf_gl' && (
                    <NumberInput
                      label="Target IPF GL"
                      value={goal.target_ipf_gl ?? ''}
                      onChange={(value) => updateGoal(goal.id, { target_ipf_gl: typeof value === 'number' ? value : undefined })}
                      min={0}
                      step={0.1}
                      decimalScale={2}
                      disabled={readOnly}
                    />
                  )}

                  {goal.goal_type === 'qualify_for_federation' && (
                    <QualifyForFederationFields
                      goal={goal}
                      federations={federations}
                      ageClass={effectiveAgeClass}
                      updateGoal={updateGoal}
                      disabled={readOnly}
                    />
                  )}

                  {goal.goal_type === 'custom' ? (
                    <Textarea
                      label="Notes"
                      description="The notes are the whole definition of a custom goal."
                      value={goal.notes ?? ''}
                      onChange={(event) => updateGoal(goal.id, { notes: event.currentTarget.value })}
                      autosize
                      minRows={3}
                      disabled={readOnly}
                    />
                  ) : (
                    <Textarea
                      label="Notes"
                      value={goal.notes ?? ''}
                      onChange={(event) => updateGoal(goal.id, { notes: event.currentTarget.value })}
                      autosize
                      minRows={2}
                      disabled={readOnly}
                    />
                  )}

                  <Group justify="space-between">
                    <Text size="xs" c="dimmed">
                      Saving writes the goal to your user partition so analytics and exports pick it up.
                    </Text>
                    <Button
                      color="red"
                      variant="light"
                      leftSection={<Trash2 size={14} />}
                      onClick={() => removeGoal(goal.id)}
                      disabled={readOnly}
                    >
                      Delete
                    </Button>
                  </Group>
                </Stack>
              </Accordion.Panel>
            </Accordion.Item>
          ))}
        </Accordion>
      )}
    </Stack>
  )
}

interface QualifyForFederationFieldsProps {
  goal: AthleteGoal
  federations: MasterFederation[]
  ageClass: AgeCategory
  updateGoal: (goalId: string, patch: Partial<AthleteGoal>) => void
  disabled: boolean
}

function QualifyForFederationFields({
  goal,
  federations,
  ageClass,
  updateGoal,
  disabled,
}: QualifyForFederationFieldsProps) {
  const selectedKeys = goal.target_federation_ids ?? []
  const wcs = goal.target_weight_class_kg ?? []
  const selectedFeds = selectedKeys
    .map((key) => findFederationByKey(federations, key))
    .filter((f): f is MasterFederation => f !== null)

  const ageClassValue = goal.age_class ?? ageClass
  const standardsByFed = selectedFeds.map((fed) => ({
    fed,
    entries: findFederationStandardsForClasses(fed, wcs, ageClassValue),
  }))

  return (
    <Stack gap="sm">
      <MultiSelect
        label="Federations"
        description="Multi-select. Filtered by your ranking country; 'global' federations are always included."
        data={federationsToOptions(federations)}
        value={selectedKeys}
        onChange={(value) => updateGoal(goal.id, { target_federation_ids: value })}
        searchable
        clearable
        disabled={disabled}
        nothingFoundMessage={federations.length === 0 ? 'No federations match your country filter.' : 'No matches'}
      />
      <SimpleGrid cols={{ base: 1, sm: 2 }}>
        <MultiSelect
          label="Weight Classes (kg)"
          data={WEIGHT_CLASS_PRESETS.map((o) => ({ value: o.value, label: o.label }))}
          value={wcs.map((w) => String(w))}
          onChange={(value) => updateGoal(goal.id, { target_weight_class_kg: value.map(Number).filter((n) => Number.isFinite(n) && n > 0) })}
          searchable
          clearable
          disabled={disabled}
        />
        <Select
          label="Age Class"
          data={AGE_CATEGORY_OPTIONS.map((o) => ({ value: o.value, label: o.label }))}
          value={goal.age_class ?? ageClass}
          onChange={(value) => updateGoal(goal.id, { age_class: (value as AgeCategory) ?? 'open' })}
          disabled={disabled}
        />
      </SimpleGrid>
      {selectedFeds.length > 0 && wcs.length > 0 && (
        <Stack gap="xs">
          {standardsByFed.map(({ fed, entries }) => (
            <Paper key={federationKey(fed)} withBorder p="sm">
              <Text size="sm" fw={500}>
                {fed.abbreviation ? `${fed.abbreviation} • ${fed.name}` : fed.name}
              </Text>
              {entries.length > 0 ? (
                <Stack gap={4} mt={4}>
                  {entries.map((entry) => (
                    <Text key={entry.id} size="xs" c="dimmed">
                      {entry.weight_class ? `${entry.weight_class} kg: ` : ''}
                      <Text span fw={700}>{entry.qualifying_total} {fed.standard_unit ?? 'kg'}</Text>
                      {entry.age_class ? ` (${entry.age_class})` : ''}
                    </Text>
                  ))}
                </Stack>
              ) : (
                <Text size="xs" c="dimmed" mt={4}>
                  No matching standard in the library for the chosen weight classes and age class yet.
                </Text>
              )}
            </Paper>
          ))}
        </Stack>
      )}
      {selectedFeds.length === 0 && (
        <Alert color="blue" variant="light" p="sm">
          Pick at least one federation and a weight class to see the qualifying standards pulled from the federation library.
        </Alert>
      )}
    </Stack>
  )
}
