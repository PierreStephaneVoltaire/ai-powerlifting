import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { Plus, Trash2, Save, Trophy, Target, CheckCircle } from 'lucide-react'
import {
  Accordion,
  Badge,
  Button,
  Checkbox,
  Group,
  Modal,
  MultiSelect,
  NumberInput,
  Paper,
  Select,
  SimpleGrid,
  Stack,
  Table,
  Text,
  TextInput,
  Textarea,
  Title,
} from '@mantine/core'
import { DatePickerInput } from '@mantine/dates'
import { useProgramStore } from '@/store/programStore'
import { useFederationStore } from '@/store/federationStore'
import { useUiStore } from '@/store/uiStore'
import { useSettingsStore } from '@/store/settingsStore'
import { calculateDots } from '@/utils/dots'
import type {
  Competition,
  FederationLibrary,
  LiftResults,
  PostMeetReport,
  CompetitionAttempt,
  CompetitionLift,
  CompetitionAttemptResult,
  CompetitionMissCategory,
  CompetitionMissReason,
} from '@powerlifting/types'

const STATUS_COLORS: Record<string, string> = {
  completed: 'green',
  confirmed: 'blue',
  optional: 'yellow',
  skipped: 'gray',
}

const STATUS_LABELS: Record<string, string> = {
  completed: 'Completed',
  confirmed: 'Confirmed',
  optional: 'Optional',
  skipped: 'Skipped',
}

const STATUS_OPTIONS = [
  { value: 'optional', label: 'Optional' },
  { value: 'confirmed', label: 'Confirmed' },
  { value: 'completed', label: 'Completed' },
  { value: 'skipped', label: 'Skipped' },
]

const LIFT_LABELS: Record<CompetitionLift, string> = {
  squat: 'Squat',
  bench: 'Bench',
  deadlift: 'Deadlift',
}

const ATTEMPT_ROWS: Array<{ lift: CompetitionLift; attempt_number: 1 | 2 | 3 }> = (['squat', 'bench', 'deadlift'] as CompetitionLift[])
  .flatMap((lift) => ([1, 2, 3] as const).map((attempt_number) => ({ lift, attempt_number })))

const ATTEMPT_RESULT_OPTIONS: Array<{ value: CompetitionAttemptResult; label: string }> = [
  { value: 'made', label: 'Made' },
  { value: 'missed', label: 'Missed' },
  { value: 'not_taken', label: 'Not taken' },
]

const MISS_CATEGORY_OPTIONS: Array<{ value: CompetitionMissCategory; label: string }> = [
  { value: 'strength', label: 'Strength' },
  { value: 'judged_technical', label: 'Judged technical' },
  { value: 'command', label: 'Command' },
  { value: 'attempt_selection', label: 'Attempt selection' },
  { value: 'pain', label: 'Pain' },
  { value: 'fatigue', label: 'Fatigue' },
  { value: 'equipment', label: 'Equipment' },
  { value: 'other', label: 'Other' },
]
const MISS_CATEGORY_LABELS = new Map(MISS_CATEGORY_OPTIONS.map((option) => [option.value, option.label]))

const MISS_REASON_OPTIONS: Array<{ value: CompetitionMissReason; label: string }> = [
  { value: 'strength_failure', label: 'Strength failure' },
  { value: 'technical_failure', label: 'Technical failure' },
  { value: 'command_failure', label: 'Command failure' },
  { value: 'grip', label: 'Grip' },
  { value: 'depth', label: 'Depth' },
  { value: 'pause', label: 'Pause' },
  { value: 'lockout', label: 'Lockout' },
  { value: 'balance', label: 'Balance' },
  { value: 'pain', label: 'Pain' },
  { value: 'fatigue', label: 'Fatigue' },
  { value: 'misload_bad_attempt_selection', label: 'Misload / bad attempt selection' },
  { value: 'equipment_issue', label: 'Equipment issue' },
]

const MISS_REASON_LABELS = new Map(MISS_REASON_OPTIONS.map((option) => [option.value, option.label]))

function emptyAttempt(lift: CompetitionLift, attempt_number: 1 | 2 | 3): CompetitionAttempt {
  return {
    lift,
    attempt_number,
    kg: null,
    result: 'not_taken',
    miss_reasons: [],
    miss_category: null,
  }
}

function normalizeAttempt(raw: Partial<CompetitionAttempt> | undefined, lift: CompetitionLift, attempt_number: 1 | 2 | 3): CompetitionAttempt {
  const result = raw?.result === 'made' || raw?.result === 'missed' || raw?.result === 'not_taken'
    ? raw.result
    : 'not_taken'
  return {
    lift,
    attempt_number,
    kg: typeof raw?.kg === 'number' && Number.isFinite(raw.kg) ? raw.kg : null,
    result,
    miss_reasons: result === 'missed' && Array.isArray(raw?.miss_reasons)
      ? raw.miss_reasons.filter((reason, index, reasons): reason is CompetitionMissReason =>
          MISS_REASON_OPTIONS.some((option) => option.value === reason) && reasons.indexOf(reason) === index
        )
      : [],
    miss_category: result === 'missed' && raw?.miss_category && MISS_CATEGORY_OPTIONS.some((option) => option.value === raw.miss_category)
      ? raw.miss_category
      : null,
  }
}

function reportFromCompetition(comp: Competition): PostMeetReport {
  const existingAttempts = comp.post_meet_report?.attempts || []
  const attempts = ATTEMPT_ROWS.map(({ lift, attempt_number }) => {
    const raw = existingAttempts.find((attempt) => attempt.lift === lift && attempt.attempt_number === attempt_number)
    if (raw) return normalizeAttempt(raw, lift, attempt_number)
    const resultKey = `${lift === 'deadlift' ? 'deadlift' : lift}_kg` as keyof LiftResults
    const resultKg = comp.results?.[resultKey]
    if (comp.status === 'completed' && attempt_number === 3 && resultKg) {
      return normalizeAttempt({ kg: resultKg, result: 'made' }, lift, attempt_number)
    }
    return emptyAttempt(lift, attempt_number)
  })

  return {
    attempts,
    sleep_hours: comp.post_meet_report?.sleep_hours ?? null,
    travel_notes: comp.post_meet_report?.travel_notes ?? '',
    warmup_timing: comp.post_meet_report?.warmup_timing ?? '',
    pre_meet_food: comp.post_meet_report?.pre_meet_food ?? '',
    during_meet_food: comp.post_meet_report?.during_meet_food ?? '',
    caffeine_mg: comp.post_meet_report?.caffeine_mg ?? null,
    caffeine_timing: comp.post_meet_report?.caffeine_timing ?? '',
    equipment_issues: comp.post_meet_report?.equipment_issues ?? '',
    commands_missed: comp.post_meet_report?.commands_missed ?? '',
    attempt_selection_grade: comp.post_meet_report?.attempt_selection_grade ?? null,
    notes: comp.post_meet_report?.notes ?? '',
  }
}

function deriveResultsFromReport(report: PostMeetReport): LiftResults {
  const best = { squat_kg: 0, bench_kg: 0, deadlift_kg: 0 }
  for (const attempt of report.attempts) {
    if (attempt.result !== 'made' || typeof attempt.kg !== 'number') continue
    if (attempt.lift === 'squat') best.squat_kg = Math.max(best.squat_kg, attempt.kg)
    if (attempt.lift === 'bench') best.bench_kg = Math.max(best.bench_kg, attempt.kg)
    if (attempt.lift === 'deadlift') best.deadlift_kg = Math.max(best.deadlift_kg, attempt.kg)
  }
  return {
    ...best,
    total_kg: best.squat_kg + best.bench_kg + best.deadlift_kg,
  }
}

function formatAttemptSummary(report?: PostMeetReport): string {
  if (!report?.attempts?.length) return ''
  const made = report.attempts.filter((attempt) => attempt.result === 'made').length
  const missed = report.attempts.filter((attempt) => attempt.result === 'missed').length
  return `${made}/9 made${missed > 0 ? `, ${missed} missed` : ''}`
}

function missReasonLabels(reasons: CompetitionMissReason[]): string {
  return reasons.map((reason) => MISS_REASON_LABELS.get(reason) || reason).join(', ')
}

function federationNameById(
  federationId: string | undefined,
  library: FederationLibrary | null,
): string | null {
  if (!federationId) return null
  const federation = library?.federations.find(item => item.id === federationId)
  if (!federation) return null
  return federation.abbreviation || federation.name || null
}

export default function CompetitionsPage() {
  const { program, updateCompetitions, migrateLastComp, completeCompetition } = useProgramStore()
  const { library, loadLibrary } = useFederationStore()
  const { pushToast } = useUiStore()
  const { sex } = useSettingsStore()
  const [competitions, setCompetitions] = useState<Competition[]>([])
  const [hasChanges, setHasChanges] = useState(false)
  const [showCompleteModal, setShowCompleteModal] = useState<string | null>(null)
  const [completeForm, setCompleteForm] = useState({
    body_weight_kg: 0,
    report: reportFromCompetition({
      name: '',
      date: '',
      federation: '',
      status: 'optional',
      weight_class_kg: 0,
    }),
  })

  useEffect(() => {
    loadLibrary().catch(console.error)
  }, [loadLibrary])

  useEffect(() => {
    if (program?.competitions) {
      const sorted = [...program.competitions].sort((a, b) => a.date.localeCompare(b.date))
      setCompetitions(sorted)
      setHasChanges(false)
    }
  }, [program])

  useEffect(() => {
    async function checkMigration() {
      const hasCompletedComp = competitions.some((c) => c.status === 'completed')
      if (!hasCompletedComp && program?.meta?.last_comp) {
        try {
          await migrateLastComp()
          pushToast({ message: 'Migrated past competition data', type: 'success' })
        } catch (err) {
          console.error('Migration failed:', err)
        }
      }
    }
    checkMigration()
  }, [])

  const federationOptions = useMemo(() => {
    return (library?.federations ?? [])
      .filter(item => item.status === 'active')
      .map(item => ({
        value: item.id,
        label: item.abbreviation ? `${item.abbreviation} • ${item.name}` : item.name,
      }))
  }, [library])

  function updateComp(date: string, updates: Partial<Competition>) {
    setCompetitions((prev) =>
      prev.map((c) => (c.date === date ? { ...c, ...updates } : c)),
    )
    setHasChanges(true)
  }

  function addCompetition() {
    const today = new Date().toISOString().split('T')[0]
    const newComp: Competition = {
      name: 'New Competition',
      date: today,
      federation: '',
      status: 'optional',
      weight_class_kg: 75,
      counts_toward_federation_ids: [],
      targets: {
        squat_kg: 0,
        bench_kg: 0,
        deadlift_kg: 0,
        total_kg: 0,
      },
      notes: '',
    }
    setCompetitions((prev) => [...prev, newComp])
    setHasChanges(true)
  }

  function removeCompetition(date: string) {
    if (!confirm('Delete this competition?')) return
    setCompetitions((prev) => prev.filter((c) => c.date !== date))
    setHasChanges(true)
  }

  async function handleSave() {
    try {
      const sorted = [...competitions].sort((a, b) => a.date.localeCompare(b.date))
      await updateCompetitions(sorted)
      setHasChanges(false)
      pushToast({ message: 'Competitions saved', type: 'success' })
    } catch (err) {
      pushToast({ message: 'Failed to save competitions', type: 'error' })
    }
  }

  async function handleMarkComplete(date: string) {
    try {
      const results = deriveResultsFromReport(completeForm.report)
      await completeCompetition(date, results, completeForm.body_weight_kg, completeForm.report)
      setShowCompleteModal(null)
      pushToast({ message: 'Competition marked as completed', type: 'success' })
    } catch (err) {
      pushToast({ message: 'Failed to mark competition as completed', type: 'error' })
    }
  }

  function openCompleteModal(comp: Competition) {
    setCompleteForm({
      body_weight_kg: comp.body_weight_kg || comp.weight_class_kg,
      report: reportFromCompetition(comp),
    })
    setShowCompleteModal(comp.date)
  }

  function updateCompleteReport(updates: Partial<PostMeetReport>) {
    setCompleteForm((prev) => ({
      ...prev,
      report: {
        ...prev.report,
        ...updates,
      },
    }))
  }

  function updateCompleteAttempt(index: number, updates: Partial<CompetitionAttempt>) {
    setCompleteForm((prev) => {
      const attempts = prev.report.attempts.map((attempt, attemptIndex) => {
        if (attemptIndex !== index) return attempt
        const next = { ...attempt, ...updates }
        if (updates.result && updates.result !== 'missed') {
          next.miss_reasons = []
          next.miss_category = null
        }
        return normalizeAttempt(next, attempt.lift, attempt.attempt_number)
      })
      return {
        ...prev,
        report: {
          ...prev.report,
          attempts,
        },
      }
    })
  }

  function calculateDotsScore(comp: Competition): { dots: number; label: string } | null {
    const total = comp.status === 'completed'
      ? comp.results?.total_kg
      : comp.targets?.total_kg

    if (!total) return null

    const bodyweight = comp.body_weight_kg || comp.weight_class_kg
    const dots = calculateDots(total, bodyweight, sex)

    return {
      dots,
      label: comp.status === 'completed' ? 'Actual' : 'Projected',
    }
  }

  const sortedCompetitions = [...competitions].sort((a, b) => a.date.localeCompare(b.date))

  return (
    <Stack gap="md">
      <Group justify="space-between">
        <Stack gap={0}>
          <Group gap="xs">
            <Text component={Link} to="/designer" size="sm" c="dimmed" style={{ textDecoration: 'none' }}>
              Designer
            </Text>
            <Text c="dimmed">/</Text>
            <Title order={2}>Competitions</Title>
          </Group>
          <Text c="dimmed" size="sm" mt={4}>
            Track upcoming and past competitions as meet opportunities, including which federations each meet can count toward.
          </Text>
        </Stack>
        <Group gap="sm">
          {hasChanges && (
            <Button
              leftSection={<Save size={16} />}
              onClick={handleSave}
            >
              Save
            </Button>
          )}
          <Button
            variant="default"
            leftSection={<Plus size={16} />}
            onClick={addCompetition}
          >
            Add Competition
          </Button>
        </Group>
      </Group>

      {sortedCompetitions.length > 0 ? (
        <Accordion variant="separated">
          {sortedCompetitions.map((comp) => {
            const dotsResult = calculateDotsScore(comp)
            const trophyColor = comp.status === 'completed' ? 'green'
              : comp.status === 'confirmed' ? 'blue'
              : 'yellow'
            const hostFederationLabel = federationNameById(comp.federation_id, library) || comp.federation || 'No federation'
            const countsTowardLabels = (comp.counts_toward_federation_ids ?? [])
              .map((federationId) => federationNameById(federationId, library))
              .filter((value): value is string => Boolean(value))
            const countsTowardOptions = federationOptions.filter(item => item.value !== comp.federation_id)

            return (
              <Accordion.Item key={comp.date} value={comp.date}>
                <Accordion.Control>
                  <Group gap="sm" wrap="nowrap">
                    <Trophy size={20} style={{ color: `var(--mantine-color-${trophyColor}-6)` }} />
                    <Stack gap={0}>
                      <Text fw={500}>{comp.name}</Text>
                      <Text size="xs" c="dimmed">
                        {new Date(comp.date).toLocaleDateString('en-US', {
                          year: 'numeric',
                          month: 'short',
                          day: 'numeric',
                        })}
                        {' \u2022 '}
                        {hostFederationLabel}
                        {countsTowardLabels.length > 0 ? ` • Counts toward ${countsTowardLabels.join(', ')}` : ''}
                      </Text>
                    </Stack>
                  </Group>
                </Accordion.Control>

                <Accordion.Panel>
                  <Stack gap="md">
                    <SimpleGrid cols={{ base: 1, sm: 2, lg: 4 }} spacing="md">
                      <TextInput
                        label="Name"
                        value={comp.name}
                        onChange={(e) => updateComp(comp.date, { name: e.currentTarget.value })}
                      />
                      <DatePickerInput
                        label="Date"
                        value={comp.date}
                        onChange={(d) => {
                          const newDate = d ?? comp.date
                          if (competitions.some((c) => c.date === newDate && c.date !== comp.date)) {
                            pushToast({ message: 'A competition on this date already exists', type: 'error' })
                            return
                          }
                          updateComp(comp.date, { date: newDate })
                        }}
                      />
                      <TextInput
                        label="Federation Label"
                        value={comp.federation}
                        onChange={(e) => updateComp(comp.date, { federation: e.currentTarget.value })}
                      />
                      <Select
                        label="Status"
                        value={comp.status}
                        onChange={(v) => updateComp(comp.date, { status: v as Competition['status'] })}
                        data={STATUS_OPTIONS}
                      />
                    </SimpleGrid>

                    <SimpleGrid cols={{ base: 1, sm: 2, lg: 4 }} spacing="md">
                      <Select
                        clearable
                        searchable
                        label="Host Federation"
                        value={comp.federation_id || null}
                        data={federationOptions}
                        onChange={(value) => {
                          const federation = library?.federations.find(item => item.id === value)
                          updateComp(comp.date, {
                            federation_id: value || undefined,
                            federation: federation?.name ?? comp.federation,
                            counts_toward_federation_ids: (comp.counts_toward_federation_ids ?? []).filter(item => item !== value),
                          })
                        }}
                      />
                      <MultiSelect
                        searchable
                        clearable
                        label="Counts Toward Federations"
                        value={comp.counts_toward_federation_ids ?? []}
                        data={countsTowardOptions}
                        onChange={(value) => updateComp(comp.date, {
                          counts_toward_federation_ids: value.filter(item => item !== comp.federation_id),
                        })}
                        description="Use this when a meet hosted by one federation can satisfy goals for another federation."
                      />
                    </SimpleGrid>

                    <SimpleGrid cols={{ base: 1, sm: 2, lg: 4 }} spacing="md">
                      <NumberInput
                        label="Weight Class (kg)"
                        value={comp.weight_class_kg}
                        onChange={(v) => updateComp(comp.date, { weight_class_kg: Number(v) || 0 })}
                      />
                      {comp.status === 'completed' && (
                        <NumberInput
                          label="Body Weight (kg)"
                          decimalScale={1}
                          value={comp.body_weight_kg || undefined}
                          onChange={(v) => updateComp(comp.date, { body_weight_kg: v ? Number(v) : undefined })}
                        />
                      )}
                      <TextInput
                        label="Location"
                        value={comp.location || ''}
                        onChange={(e) => updateComp(comp.date, { location: e.currentTarget.value })}
                      />
                      <Checkbox
                        mt={30}
                        label="Hotel required"
                        checked={Boolean(comp.hotel_required)}
                        onChange={(event) => updateComp(comp.date, { hotel_required: event.currentTarget.checked })}
                      />
                    </SimpleGrid>

                    <Stack gap="xs">
                      <Text size="xs" c="dimmed">
                        {comp.status === 'completed' ? 'Results (kg)' : 'Targets (kg)'}
                      </Text>
                      <SimpleGrid cols={{ base: 2, sm: 4 }} spacing="md">
                        {(['squat_kg', 'bench_kg', 'deadlift_kg', 'total_kg'] as const).map((lift) => (
                          <NumberInput
                            key={lift}
                            label={lift.replace('_kg', '')}
                            value={
                              comp.status === 'completed'
                                ? comp.results?.[lift] || 0
                                : comp.targets?.[lift] || 0
                            }
                            onChange={(value) => {
                              const v = Number(value) || 0
                              const field = comp.status === 'completed' ? 'results' : 'targets'
                              const currentField = comp[field] || {
                                squat_kg: 0,
                                bench_kg: 0,
                                deadlift_kg: 0,
                                total_kg: 0,
                              }
                              const newLifts = {
                                squat_kg: currentField.squat_kg || 0,
                                bench_kg: currentField.bench_kg || 0,
                                deadlift_kg: currentField.deadlift_kg || 0,
                                [lift]: v,
                              }
                              const newTotal = newLifts.squat_kg + newLifts.bench_kg + newLifts.deadlift_kg
                              updateComp(comp.date, {
                                [field]: {
                                  ...currentField,
                                  [lift]: v,
                                  total_kg: newTotal,
                                },
                              })
                            }}
                            disabled={lift === 'total_kg' || (comp.status === 'completed' && Boolean(comp.post_meet_report))}
                          />
                        ))}
                      </SimpleGrid>
                    </Stack>

                    {dotsResult && (
                      <Paper bg="var(--mantine-color-default)" p="sm" radius="md">
                        <Stack gap={4}>
                          <Group gap="sm">
                            <Target size={16} style={{ color: 'var(--mantine-color-blue-6)' }} />
                            <Text size="sm">
                              <Text span c="dimmed">{dotsResult.label} DOTS:</Text>{' '}
                              <Text span fw={700} ff="monospace">{dotsResult.dots.toFixed(2)}</Text>
                            </Text>
                          </Group>
                        </Stack>
                      </Paper>
                    )}

                    {comp.post_meet_report && (
                      <Paper bg="var(--mantine-color-default)" p="sm" radius="md">
                        <Stack gap="sm">
                          <Group justify="space-between" align="center">
                            <Text size="sm" fw={500}>Post-meet report</Text>
                            <Badge variant="light" color="green">{formatAttemptSummary(comp.post_meet_report)}</Badge>
                          </Group>
                          <Table striped withTableBorder withColumnBorders>
                            <Table.Thead>
                              <Table.Tr>
                                <Table.Th>Attempt</Table.Th>
                                <Table.Th>kg</Table.Th>
                                <Table.Th>Result</Table.Th>
                                <Table.Th>Miss detail</Table.Th>
                              </Table.Tr>
                            </Table.Thead>
                            <Table.Tbody>
                              {comp.post_meet_report.attempts.map((attempt) => (
                                <Table.Tr key={`${attempt.lift}-${attempt.attempt_number}`}>
                                  <Table.Td>{LIFT_LABELS[attempt.lift]} {attempt.attempt_number}</Table.Td>
                                  <Table.Td>{attempt.kg ?? ''}</Table.Td>
                                  <Table.Td>
                                    <Badge
                                      size="sm"
                                      variant="light"
                                      color={attempt.result === 'made' ? 'green' : attempt.result === 'missed' ? 'red' : 'gray'}
                                    >
                                      {attempt.result.replace('_', ' ')}
                                    </Badge>
                                  </Table.Td>
                                  <Table.Td>
                                    {attempt.result === 'missed'
                                      ? [attempt.miss_category ? MISS_CATEGORY_LABELS.get(attempt.miss_category) : '', missReasonLabels(attempt.miss_reasons)].filter(Boolean).join(' - ')
                                      : ''}
                                  </Table.Td>
                                </Table.Tr>
                              ))}
                            </Table.Tbody>
                          </Table>
                          <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }} spacing="xs">
                            <Text size="sm"><Text span c="dimmed">Sleep:</Text> {comp.post_meet_report.sleep_hours ?? ''} h</Text>
                            <Text size="sm"><Text span c="dimmed">Caffeine:</Text> {comp.post_meet_report.caffeine_mg ?? ''} mg</Text>
                            <Text size="sm"><Text span c="dimmed">Selection grade:</Text> {comp.post_meet_report.attempt_selection_grade ?? ''}/5</Text>
                            <Text size="sm"><Text span c="dimmed">Warm-ups:</Text> {comp.post_meet_report.warmup_timing || ''}</Text>
                            <Text size="sm"><Text span c="dimmed">Commands:</Text> {comp.post_meet_report.commands_missed || ''}</Text>
                            <Text size="sm"><Text span c="dimmed">Equipment:</Text> {comp.post_meet_report.equipment_issues || ''}</Text>
                          </SimpleGrid>
                          {(comp.post_meet_report.pre_meet_food || comp.post_meet_report.during_meet_food || comp.post_meet_report.caffeine_timing || comp.post_meet_report.travel_notes || comp.post_meet_report.notes) && (
                            <Textarea
                              value={[
                                comp.post_meet_report.travel_notes ? `Travel: ${comp.post_meet_report.travel_notes}` : '',
                                comp.post_meet_report.pre_meet_food ? `Before: ${comp.post_meet_report.pre_meet_food}` : '',
                                comp.post_meet_report.during_meet_food ? `During: ${comp.post_meet_report.during_meet_food}` : '',
                                comp.post_meet_report.caffeine_timing ? `Caffeine timing: ${comp.post_meet_report.caffeine_timing}` : '',
                                comp.post_meet_report.notes,
                              ].filter(Boolean).join('\n')}
                              readOnly
                              autosize
                              minRows={2}
                              variant="filled"
                            />
                          )}
                        </Stack>
                      </Paper>
                    )}

                    <Textarea
                      label="Notes"
                      value={comp.notes || ''}
                      onChange={(e) => updateComp(comp.date, { notes: e.currentTarget.value })}
                      rows={3}
                      placeholder="Competition notes..."
                      autosize
                    />

                    <Group>
                      <Badge variant="light" color={STATUS_COLORS[comp.status]}>
                        {STATUS_LABELS[comp.status]}
                      </Badge>
                      <Badge variant="light" color="grape">
                        Host: {hostFederationLabel}
                      </Badge>
                      {countsTowardLabels.length > 0 && (
                        <Badge variant="light" color="blue">
                          Counts toward: {countsTowardLabels.join(', ')}
                        </Badge>
                      )}
                      {dotsResult && (
                        <Text size="sm" ff="monospace">
                          {dotsResult.label}: {dotsResult.dots.toFixed(1)}
                        </Text>
                      )}
                    </Group>

                    <Group justify="space-between" pt="sm">
                      {comp.status === 'completed' && (
                        <Button
                          variant="light"
                          color="green"
                          size="sm"
                          leftSection={<CheckCircle size={14} />}
                          onClick={() => openCompleteModal(comp)}
                        >
                          {comp.post_meet_report ? 'Edit Post-Meet Report' : 'Add Post-Meet Report'}
                        </Button>
                      )}
                      {comp.status !== 'completed' && new Date(comp.date) < new Date() && (
                        <Button
                          variant="light"
                          color="green"
                          size="sm"
                          leftSection={<CheckCircle size={14} />}
                          onClick={() => openCompleteModal(comp)}
                        >
                          Mark as Completed
                        </Button>
                      )}
                      <Button
                        variant="light"
                        color="red"
                        size="sm"
                        ml="auto"
                        leftSection={<Trash2 size={14} />}
                        onClick={() => removeCompetition(comp.date)}
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
      ) : (
        <Group justify="center" py={48}>
          <Text c="dimmed">No competitions yet. Click "Add Competition" to get started.</Text>
        </Group>
      )}

      <Modal
        opened={showCompleteModal !== null}
        onClose={() => setShowCompleteModal(null)}
        title="Post-Meet Report"
        size="xl"
      >
        <Stack gap="md">
          <Text size="sm" c="dimmed">
            Log the attempt card and meet-day context. Best made attempts are used as the official results.
          </Text>

          <SimpleGrid cols={{ base: 1, sm: 3 }} spacing="md">
            <NumberInput
              label="Body Weight at Weigh-in (kg)"
              decimalScale={1}
              value={completeForm.body_weight_kg}
              onChange={(v) => setCompleteForm((p) => ({ ...p, body_weight_kg: Number(v) || 0 }))}
            />
            <NumberInput
              label="Sleep before meet (hours)"
              min={0}
              max={24}
              decimalScale={1}
              value={completeForm.report.sleep_hours ?? ''}
              onChange={(v) => updateCompleteReport({ sleep_hours: v !== '' ? Number(v) : null })}
            />
            <NumberInput
              label="Attempt selection grade"
              min={1}
              max={5}
              value={completeForm.report.attempt_selection_grade ?? ''}
              onChange={(v) => updateCompleteReport({ attempt_selection_grade: v !== '' ? Math.max(1, Math.min(5, Math.round(Number(v)))) as 1 | 2 | 3 | 4 | 5 : null })}
            />

          </SimpleGrid>

          <Table striped withTableBorder withColumnBorders>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Attempt</Table.Th>
                <Table.Th>kg</Table.Th>
                <Table.Th>Result</Table.Th>
                <Table.Th>Miss category</Table.Th>
                <Table.Th>Reasons</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {completeForm.report.attempts.map((attempt, index) => (
                <Table.Tr key={`${attempt.lift}-${attempt.attempt_number}`}>
                  <Table.Td>
                    <Text size="sm" fw={500}>{LIFT_LABELS[attempt.lift]} {attempt.attempt_number}</Text>
                  </Table.Td>
                  <Table.Td>
                    <NumberInput
                      value={attempt.kg ?? ''}
                      onChange={(v) => updateCompleteAttempt(index, { kg: v !== '' ? Number(v) : null })}
                      decimalScale={1}
                      min={0}
                      size="xs"
                    />
                  </Table.Td>
                  <Table.Td>
                    <Select
                      value={attempt.result}
                      data={ATTEMPT_RESULT_OPTIONS}
                      onChange={(value) => updateCompleteAttempt(index, { result: (value || 'not_taken') as CompetitionAttemptResult })}
                      size="xs"
                    />
                  </Table.Td>
                  <Table.Td>
                    <Select
                      clearable
                      disabled={attempt.result !== 'missed'}
                      value={attempt.miss_category}
                      data={MISS_CATEGORY_OPTIONS}
                      onChange={(value) => updateCompleteAttempt(index, { miss_category: value as CompetitionMissCategory | null })}
                      size="xs"
                    />
                  </Table.Td>
                  <Table.Td>
                    <MultiSelect
                      disabled={attempt.result !== 'missed'}
                      value={attempt.miss_reasons}
                      data={MISS_REASON_OPTIONS}
                      onChange={(value) => updateCompleteAttempt(index, { miss_reasons: value as CompetitionMissReason[] })}
                      size="xs"
                    />
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>

          <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="md">
            <Textarea
              label="Warm-up timing"
              value={completeForm.report.warmup_timing}
              onChange={(e) => updateCompleteReport({ warmup_timing: e.currentTarget.value })}
              autosize
              minRows={2}
            />
            <Textarea
              label="Sleep / travel"
              value={completeForm.report.travel_notes}
              onChange={(e) => updateCompleteReport({ travel_notes: e.currentTarget.value })}
              autosize
              minRows={2}
            />
            <Textarea
              label="Food before"
              value={completeForm.report.pre_meet_food}
              onChange={(e) => updateCompleteReport({ pre_meet_food: e.currentTarget.value })}
              autosize
              minRows={2}
            />
            <Textarea
              label="Food during"
              value={completeForm.report.during_meet_food}
              onChange={(e) => updateCompleteReport({ during_meet_food: e.currentTarget.value })}
              autosize
              minRows={2}
            />
            <NumberInput
              label="Caffeine total (mg)"
              value={completeForm.report.caffeine_mg ?? ''}
              onChange={(v) => updateCompleteReport({ caffeine_mg: v !== '' ? Number(v) : null })}
              min={0}
            />
            <Textarea
              label="Caffeine timing"
              value={completeForm.report.caffeine_timing}
              onChange={(e) => updateCompleteReport({ caffeine_timing: e.currentTarget.value })}
              autosize
              minRows={2}
            />
            <Textarea
              label="Equipment issues"
              value={completeForm.report.equipment_issues}
              onChange={(e) => updateCompleteReport({ equipment_issues: e.currentTarget.value })}
              autosize
              minRows={2}
            />
            <Textarea
              label="Commands missed"
              value={completeForm.report.commands_missed}
              onChange={(e) => updateCompleteReport({ commands_missed: e.currentTarget.value })}
              autosize
              minRows={2}
            />
          </SimpleGrid>

          <Textarea
            label="Meet notes"
            value={completeForm.report.notes}
            onChange={(e) => updateCompleteReport({ notes: e.currentTarget.value })}
            autosize
            minRows={3}
          />

          <Group justify="flex-end" gap="sm" pt="sm">
            <Button variant="default" onClick={() => setShowCompleteModal(null)}>
              Cancel
            </Button>
            <Button onClick={() => showCompleteModal && handleMarkComplete(showCompleteModal)}>
              Complete
            </Button>
          </Group>
        </Stack>
      </Modal>
    </Stack>
  )
}
