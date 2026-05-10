import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { Plus, Save, Target, Trash2 } from 'lucide-react'
import {
  Accordion,
  Badge,
  Button,
  Group,
  MultiSelect,
  Paper,
  Select,
  SimpleGrid,
  Stack,
  Text,
  TextInput,
  Textarea,
  Title,
} from '@mantine/core'
import { DatePickerInput } from '@mantine/dates'
import type {
  AthleteGoal,
  AttemptStrategyMode,
  FederationLibrary,
  GoalPriority,
  GoalType,
  QualificationStandard,
  RiskTolerance,
} from '@powerlifting/types'
import { useProgramStore } from '@/store/programStore'
import { useFederationStore } from '@/store/federationStore'
import { useUiStore } from '@/store/uiStore'
import { useSettingsStore } from '@/store/settingsStore'

const GOAL_TYPE_OPTIONS: Array<{ value: GoalType; label: string }> = [
  { value: 'hit_total', label: 'Hit Total' },
  { value: 'qualify_for_federation', label: 'Qualify for Federation' },
  { value: 'peak_for_meet', label: 'Peak for Meet' },
  { value: 'make_podium', label: 'Make Podium' },
  { value: 'conservative_pr', label: 'Conservative PR' },
  { value: 'train_through', label: 'Train Through' },
  { value: 'rank_percentile', label: 'Rank Percentile' },
  { value: 'improve_dots', label: 'Improve DOTS' },
  { value: 'maintain_weight_class', label: 'Maintain Weight Class' },
  { value: 'coach_defined', label: 'Coach Defined' },
]

const PRIORITY_OPTIONS: Array<{ value: GoalPriority; label: string }> = [
  { value: 'primary', label: 'Primary' },
  { value: 'secondary', label: 'Secondary' },
  { value: 'optional', label: 'Optional' },
]

const STRATEGY_OPTIONS: Array<{ value: AttemptStrategyMode; label: string }> = [
  { value: 'max_total', label: 'Max Total' },
  { value: 'qualify', label: 'Qualify' },
  { value: 'minimum_total', label: 'Minimum Total' },
  { value: 'podium', label: 'Podium' },
  { value: 'train_through', label: 'Train Through' },
  { value: 'conservative_pr', label: 'Conservative PR' },
]

const RISK_OPTIONS: Array<{ value: RiskTolerance; label: string }> = [
  { value: 'low', label: 'Low' },
  { value: 'medium', label: 'Medium' },
  { value: 'high', label: 'High' },
]

function makeGoal(): AthleteGoal {
  return {
    id: crypto.randomUUID(),
    title: 'New Goal',
    goal_type: 'hit_total',
    priority: 'secondary',
    strategy_mode: 'max_total',
    risk_tolerance: 'medium',
    target_competition_dates: [],
    target_standard_ids: [],
    acceptable_weight_classes_kg: [],
    notes: '',
  }
}

function cloneLibrary(library: FederationLibrary | null): FederationLibrary | null {
  if (!library) return null
  return JSON.parse(JSON.stringify(library)) as FederationLibrary
}

function parseNumberList(value: string): number[] {
  return value
    .split(',')
    .map(item => Number(item.trim()))
    .filter(item => Number.isFinite(item) && item > 0)
}

function formatNumberList(value?: number[]): string {
  return (value ?? []).join(', ')
}

function normalizeStringList(values?: string[], legacyValue?: string): string[] {
  const deduped = new Set<string>()
  for (const value of values ?? []) {
    const trimmed = value.trim()
    if (trimmed) deduped.add(trimmed)
  }
  if (legacyValue?.trim()) deduped.add(legacyValue.trim())
  return [...deduped]
}

function normalizeGoal(goal: AthleteGoal): AthleteGoal {
  const targetCompetitionDates = normalizeStringList(goal.target_competition_dates, goal.target_competition_date)
  const targetStandardIds = normalizeStringList(goal.target_standard_ids, goal.target_standard_id)
  return {
    ...goal,
    target_competition_dates: targetCompetitionDates,
    target_competition_date: targetCompetitionDates[0] || undefined,
    target_standard_ids: targetStandardIds,
    target_standard_id: targetStandardIds[0] || undefined,
    acceptable_weight_classes_kg: goal.acceptable_weight_classes_kg ?? [],
    notes: goal.notes ?? '',
  }
}

function goalBadgeColor(priority: GoalPriority): string {
  if (priority === 'primary') return 'red'
  if (priority === 'secondary') return 'blue'
  return 'gray'
}

function standardLabel(standard: QualificationStandard, library: FederationLibrary | null): string {
  const federation = library?.federations.find(item => item.id === standard.federation_id)
  const federationLabel = federation?.abbreviation || federation?.name || 'Unknown'
  const detail = [standard.season_year, standard.sex, `${standard.weight_class_kg}kg`, `${standard.required_total_kg}kg`]
  return `${federationLabel} • ${detail.join(' • ')}`
}

export default function GoalsPage() {
  const { program, updateGoals } = useProgramStore()
  const { library, loadLibrary } = useFederationStore()
  const { pushToast } = useUiStore()
  const { sex: settingsSex } = useSettingsStore()
  const [goals, setGoals] = useState<AthleteGoal[]>([])
  const [hasChanges, setHasChanges] = useState(false)

  useEffect(() => {
    loadLibrary().catch(console.error)
  }, [loadLibrary])

  useEffect(() => {
    if (!program) return
    setGoals((program.goals ?? []).map(normalizeGoal))
    setHasChanges(false)
  }, [program])

  const effectiveSex = program?.meta.sex ?? settingsSex
  const competitions = useMemo(() => {
    return [...(program?.competitions ?? [])].sort((a, b) => a.date.localeCompare(b.date))
  }, [program?.competitions])

  const competitionOptions = useMemo(() => {
    return competitions.map(comp => ({
      value: comp.date,
      label: `${comp.name} • ${comp.date} • ${comp.status}`,
    }))
  }, [competitions])

  const federationOptions = useMemo(() => {
    return (library?.federations ?? [])
      .filter(item => item.status === 'active')
      .map(item => ({
        value: item.id,
        label: item.abbreviation ? `${item.abbreviation} • ${item.name}` : item.name,
      }))
  }, [library])

  function updateGoal(goalId: string, patch: Partial<AthleteGoal>) {
    setGoals(current => current.map(goal => (
      goal.id === goalId
        ? normalizeGoal({ ...goal, ...patch })
        : goal
    )))
    setHasChanges(true)
  }

  function addGoal() {
    setGoals(current => [...current, makeGoal()])
    setHasChanges(true)
  }

  function removeGoal(goalId: string) {
    setGoals(current => current.filter(goal => goal.id !== goalId))
    setHasChanges(true)
  }

  async function handleSave() {
    try {
      await updateGoals(goals.map(normalizeGoal))
      setHasChanges(false)
      pushToast({ message: 'Goals saved', type: 'success' })
    } catch (error) {
      pushToast({ message: 'Failed to save goals', type: 'error' })
    }
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
            <Button leftSection={<Save size={16} />} onClick={handleSave}>
              Save
            </Button>
          )}
          <Button variant="default" leftSection={<Plus size={16} />} onClick={addGoal}>
            Add Goal
          </Button>
        </Group>
      </Group>

      <Paper withBorder p="md">
        <Text size="sm" c="dimmed">
          Goals are saved on the current program version. Federation standards are shared across programs and managed on the Federations page.
        </Text>
        {!library && (
          <Text size="sm" mt="xs" c="dimmed">
            Federation library has not loaded yet. You can still define generic goals now and link standards later.
          </Text>
        )}
      </Paper>

      {goals.length === 0 ? (
        <Paper withBorder p="xl">
          <Stack gap="xs" align="center">
            <Target size={20} />
            <Text fw={500}>No explicit goals yet</Text>
            <Text size="sm" c="dimmed" ta="center">
              Add at least one goal if you want block analysis to prioritize meets, qualifying totals, weight-class tradeoffs, and strategy mode.
            </Text>
          </Stack>
        </Paper>
      ) : (
        <Accordion variant="separated">
          {goals.map(goal => {
            const standards = (cloneLibrary(library)?.qualification_standards ?? [])
              .filter(item => item.status === 'active')
              .filter(item => item.sex === effectiveSex)
              .map(item => ({
                value: item.id,
                label: standardLabel(item, library),
              }))
            const selectedStandards = (library?.qualification_standards ?? []).filter(item => (
              (goal.target_standard_ids ?? []).includes(item.id)
            ))

            return (
              <Accordion.Item key={goal.id} value={goal.id}>
                <Accordion.Control>
                  <Group gap="sm" wrap="nowrap">
                    <Badge color={goalBadgeColor(goal.priority)} variant="light">
                      {goal.priority}
                    </Badge>
                    <Stack gap={0}>
                      <Text fw={500}>{goal.title || 'Untitled goal'}</Text>
                      <Text size="xs" c="dimmed">
                        {GOAL_TYPE_OPTIONS.find(item => item.value === goal.goal_type)?.label || goal.goal_type}
                      </Text>
                    </Stack>
                  </Group>
                </Accordion.Control>
                <Accordion.Panel>
                  <Stack gap="md">
                    <SimpleGrid cols={{ base: 1, sm: 2, lg: 4 }}>
                      <TextInput
                        label="Title"
                        value={goal.title}
                        onChange={(event) => updateGoal(goal.id, { title: event.currentTarget.value })}
                      />
                      <Select
                        label="Goal Type"
                        data={GOAL_TYPE_OPTIONS}
                        value={goal.goal_type}
                        onChange={(value) => value && updateGoal(goal.id, { goal_type: value as GoalType })}
                      />
                      <Select
                        label="Priority"
                        data={PRIORITY_OPTIONS}
                        value={goal.priority}
                        onChange={(value) => value && updateGoal(goal.id, { priority: value as GoalPriority })}
                      />
                      <Select
                        label="Strategy Mode"
                        data={STRATEGY_OPTIONS}
                        value={goal.strategy_mode}
                        onChange={(value) => value && updateGoal(goal.id, { strategy_mode: value as AttemptStrategyMode })}
                      />
                    </SimpleGrid>

                    <SimpleGrid cols={{ base: 1, sm: 2, lg: 4 }}>
                      <MultiSelect
                        label="Target Competitions"
                        data={competitionOptions}
                        value={goal.target_competition_dates ?? []}
                        onChange={(value) => updateGoal(goal.id, { target_competition_dates: value })}
                      />
                      <DatePickerInput
                        clearable
                        label="Target Date"
                        value={goal.target_date || null}
                        onChange={(value) => updateGoal(goal.id, { target_date: value || undefined })}
                      />
                      <Select
                        clearable
                        searchable
                        label="Primary Federation"
                        data={federationOptions}
                        value={goal.target_federation_id || null}
                        onChange={(value) => updateGoal(goal.id, { target_federation_id: value || undefined })}
                      />
                      <MultiSelect
                        searchable
                        label="Qualification Standards"
                        data={standards}
                        value={goal.target_standard_ids ?? []}
                        onChange={(value) => {
                          const matchingStandards = (library?.qualification_standards ?? []).filter(item => value.includes(item.id))
                          const firstStandard = matchingStandards[0]
                          const requiredTotals = matchingStandards
                            .map(item => item.required_total_kg)
                            .filter(item => Number.isFinite(item) && item > 0)
                          const weightClasses = [...new Set(matchingStandards.map(item => item.weight_class_kg).filter(item => Number.isFinite(item) && item > 0))]
                          updateGoal(goal.id, {
                            target_standard_ids: value,
                            target_federation_id: goal.target_federation_id ?? firstStandard?.federation_id,
                            target_total_kg: requiredTotals.length > 0 ? Math.max(...requiredTotals) : undefined,
                            target_weight_class_kg: weightClasses.length === 1 ? weightClasses[0] : goal.target_weight_class_kg,
                          })
                        }}
                      />
                    </SimpleGrid>

                    {selectedStandards.length > 0 && (
                      <Stack gap="xs">
                        {selectedStandards.map(standard => (
                          <Paper key={standard.id} withBorder p="sm">
                            <Text size="sm" fw={500}>
                              Linked standard: {standardLabel(standard, library)}
                            </Text>
                            <Text size="xs" c="dimmed" mt={4}>
                              Event {standard.event} • Equipment {standard.equipment}
                              {standard.age_class ? ` • ${standard.age_class}` : ''}
                              {standard.division ? ` • ${standard.division}` : ''}
                            </Text>
                          </Paper>
                        ))}
                      </Stack>
                    )}

                    <SimpleGrid cols={{ base: 1, sm: 2, lg: 4 }}>
                      <TextInput
                        type="number"
                        label="Target Total (kg)"
                        value={goal.target_total_kg ?? ''}
                        onChange={(e) => updateGoal(goal.id, { target_total_kg: e.currentTarget.value ? Number(e.currentTarget.value) : undefined })}
                      />
                      <TextInput
                        type="number"
                        label="Target DOTS"
                        value={goal.target_dots ?? ''}
                        onChange={(e) => updateGoal(goal.id, { target_dots: e.currentTarget.value ? Number(e.currentTarget.value) : undefined })}
                      />
                      <TextInput
                        type="number"
                        label="Target IPF GL"
                        value={goal.target_ipf_gl ?? ''}
                        onChange={(e) => updateGoal(goal.id, { target_ipf_gl: e.currentTarget.value ? Number(e.currentTarget.value) : undefined })}
                      />
                      <TextInput
                        type="number"
                        label="Target Weight Class (kg)"
                        value={goal.target_weight_class_kg ?? ''}
                        onChange={(e) => updateGoal(goal.id, { target_weight_class_kg: e.currentTarget.value ? Number(e.currentTarget.value) : undefined })}
                      />
                    </SimpleGrid>

                    <SimpleGrid cols={{ base: 1, sm: 2, lg: 4 }}>
                      <TextInput
                        label="Acceptable Weight Classes"
                        placeholder="74, 83"
                        value={formatNumberList(goal.acceptable_weight_classes_kg)}
                        onChange={(event) => updateGoal(goal.id, {
                          acceptable_weight_classes_kg: parseNumberList(event.currentTarget.value),
                        })}
                      />
                      <Select
                        label="Risk Tolerance"
                        data={RISK_OPTIONS}
                        value={goal.risk_tolerance}
                        onChange={(value) => value && updateGoal(goal.id, { risk_tolerance: value as RiskTolerance })}
                      />
                      <TextInput
                        type="number"
                        label="Max Bodyweight Loss %"
                        value={goal.max_acceptable_bodyweight_loss_pct ?? ''}
                        onChange={(e) => updateGoal(goal.id, {
                          max_acceptable_bodyweight_loss_pct: e.currentTarget.value ? Number(e.currentTarget.value) : undefined,
                        })}
                      />
                      <TextInput
                        type="number"
                        label="Max Water Cut %"
                        value={goal.max_acceptable_water_cut_pct ?? ''}
                        onChange={(e) => updateGoal(goal.id, {
                          max_acceptable_water_cut_pct: e.currentTarget.value ? Number(e.currentTarget.value) : undefined,
                        })}
                      />
                    </SimpleGrid>

                    <Textarea
                      label="Notes"
                      autosize
                      minRows={2}
                      value={goal.notes || ''}
                      onChange={(event) => updateGoal(goal.id, { notes: event.currentTarget.value })}
                    />

                    <Group justify="space-between">
                      <Text size="xs" c="dimmed">
                        Goals can point at multiple competitions and multiple standards. Use Primary Federation only when one federation should take precedence in the analysis.
                      </Text>
                      <Button
                        color="red"
                        variant="light"
                        leftSection={<Trash2 size={14} />}
                        onClick={() => removeGoal(goal.id)}
                      >
                        Delete
                      </Button>
                    </Group>
                  </Stack>
                </Accordion.Panel>
              </Accordion.Item>
            )
          })}
        </Accordion>
      )}
    </Stack>
  )
}
