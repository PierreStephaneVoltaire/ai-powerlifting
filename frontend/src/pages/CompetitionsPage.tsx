import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { CheckCircle, Search, Target, Trophy } from 'lucide-react'
import {
  Accordion,
  Badge,
  Button,
  Checkbox,
  Group,
  Modal,
  Paper,
  Select,
  SimpleGrid,
  Stack,
  Text,
  TextInput,
  Textarea,
  Title,
} from '@mantine/core'
import { useCompetitionsStore } from '@/store/competitionsStore'
import { useUiStore } from '@/store/uiStore'
import { useSettingsStore } from '@/store/settingsStore'
import { useAuth } from '@/auth/AuthProvider'
import { calculateDots } from '@/utils/dots'
import { fetchStatCategories } from '@/api/client'
import type {
  UserCompetition,
  UserCompetitionUpdate,
  LiftResults,
  PostMeetReport,
  CompetitionLift,
  CompetitionAttempt,
  CompetitionAttemptResult,
  CompetitionMissCategory,
  CompetitionMissReason,
} from '@powerlifting/types'

const STATUS_COLORS: Record<string, string> = {
  available: 'gray', optional: 'yellow', confirmed: 'blue', completed: 'green', skipped: 'dark',
}
const STATUS_LABELS: Record<string, string> = {
  available: 'Available', optional: 'Optional', confirmed: 'Confirmed', completed: 'Completed', skipped: 'Skipped',
}
const STATUS_OPTIONS = [
  { value: 'available', label: 'Available' },
  { value: 'optional', label: 'Optional' },
  { value: 'confirmed', label: 'Confirmed' },
  { value: 'completed', label: 'Completed' },
  { value: 'skipped', label: 'Skipped' },
]

const LIFT_LABELS: Record<CompetitionLift, string> = { squat: 'Squat', bench: 'Bench', deadlift: 'Deadlift' }
const ATTEMPT_ROWS: Array<{ lift: CompetitionLift; attempt_number: 1 | 2 | 3 }> = (
  ['squat', 'bench', 'deadlift'] as CompetitionLift[]
).flatMap((lift) => ([1, 2, 3] as const).map((attempt_number) => ({ lift, attempt_number })))
const ATTEMPT_RESULT_OPTIONS: Array<{ value: CompetitionAttemptResult; label: string }> = [
  { value: 'made', label: 'Made' }, { value: 'missed', label: 'Missed' }, { value: 'not_taken', label: 'Not taken' },
]

function effectiveRegistrationStatus(comp: UserCompetition): string {
  if (comp.cancelled) return 'cancelled'
  if (comp.registration_end_date && comp.registration_status === 'open') {
    if (new Date(comp.registration_end_date) < new Date()) return 'closed'
  }
  return comp.registration_status
}

function formatDateRange(comp: UserCompetition): string {
  const start = new Date(comp.start_date).toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' })
  if (comp.end_date) {
    const end = new Date(comp.end_date).toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' })
    return start + ' \u2013 ' + end
  }
  return start
}

function normalizeAttempt(raw: Partial<CompetitionAttempt> | undefined, lift: CompetitionLift, attempt_number: 1 | 2 | 3): CompetitionAttempt {
  const result = raw?.result === 'made' || raw?.result === 'missed' || raw?.result === 'not_taken' ? raw.result : 'not_taken'
  return {
    lift, attempt_number,
    kg: typeof raw?.kg === 'number' && Number.isFinite(raw.kg) ? raw.kg : null,
    result,
    miss_reasons: [],
    miss_category: null,
  }
}

function reportFromComp(comp: UserCompetition): PostMeetReport {
  const existingAttempts = comp.post_meet_report?.attempts || []
  const attempts = ATTEMPT_ROWS.map(({ lift, attempt_number }) => {
    const raw = existingAttempts.find((a) => a.lift === lift && a.attempt_number === attempt_number)
    if (raw) return normalizeAttempt(raw, lift, attempt_number)
    return normalizeAttempt(undefined, lift, attempt_number)
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
  for (const a of report.attempts) {
    if (a.result !== 'made' || typeof a.kg !== 'number') continue
    if (a.lift === 'squat') best.squat_kg = Math.max(best.squat_kg, a.kg)
    if (a.lift === 'bench') best.bench_kg = Math.max(best.bench_kg, a.kg)
    if (a.lift === 'deadlift') best.deadlift_kg = Math.max(best.deadlift_kg, a.kg)
  }
  return { ...best, total_kg: best.squat_kg + best.bench_kg + best.deadlift_kg }
}

function formatAttemptSummary(report?: PostMeetReport): string {
  if (!report?.attempts?.length) return ''
  const made = report.attempts.filter((a) => a.result === 'made').length
  const missed = report.attempts.filter((a) => a.result === 'missed').length
  return made + '/9 made' + (missed > 0 ? ', ' + missed + ' missed' : '')
}

function venueDisplay(comp: UserCompetition): string {
  return [comp.venue_city, comp.venue_state, comp.venue_country].filter(Boolean).join(', ') || 'No venue'
}

const EMPTY_COMP: UserCompetition = {
  master_id: '', name: '', start_date: '', end_date: null,
  federation_label: '', federation_slug: null, federation_website_url: null,
  venue_name: null, venue_address: null, venue_city: null, venue_state: null, venue_country: '',
  venue_postal_code: null,
  website_url: null, testing_status: 'unknown', registration_status: 'unknown',
  registration_url: null, registration_end_date: null, source_url: null, source_name: null,
  last_verified_at: null, event_type: null, cancelled: false,
  user_status: 'available', weight_class_kg: null, body_weight_kg: null,
  targets: null, results: null, post_meet_report: null, hotel_required: false,
  counts_toward_federation_ids: [], between_comp_plan: null, comp_day_protocol: null,
  decision_date: null, attempt_selection: null, attempt_strategy_mode: null,
  qualifying_standard_id: null, qualifying_total_kg: null,
  projected_at_t_minus_1w: null, projection_snapshot_date: null,
  notes: '', created_at: '', updated_at: '',
}

export default function CompetitionsPage() {
  const { readOnly, ranking_country, ranking_region, loading: authLoading } = useAuth()
  const { competitions, isLoading, loadAll, patch, complete } = useCompetitionsStore()
  const { pushToast } = useUiStore()
  const { sex } = useSettingsStore()

  const rankingCountry = ranking_country
  const [selectedState, setSelectedState] = useState<string | null>(ranking_region)
  const [categories, setCategories] = useState<{ countries: string[]; country_regions: Record<string, string[]> } | null>(null)

  const [showCompleteModal, setShowCompleteModal] = useState<string | null>(null)
  const [completeForm, setCompleteForm] = useState<{ body_weight_kg: number; report: PostMeetReport }>({
    body_weight_kg: 0, report: reportFromComp(EMPTY_COMP),
  })

  useEffect(() => {
    fetchStatCategories().then((data: any) => {
      if (data && !data.error) setCategories({ countries: data.countries || [], country_regions: data.country_regions || {} })
    }).catch(() => {})
  }, [])

  useEffect(() => {
  }, [])

  useEffect(() => {
    if (authLoading) return
    loadAll({ country: rankingCountry ?? undefined, state: selectedState ?? undefined })
  }, [authLoading, rankingCountry, selectedState, loadAll])

  const stateOptions = useMemo(() => {
    if (!rankingCountry || !categories) return []
    const regions = categories.country_regions[rankingCountry] ?? []
    return [{ value: '__all__', label: 'All States' }, ...regions.map((r) => ({ value: r, label: r }))]
  }, [rankingCountry, categories])

  const handleSearch = useCallback(() => {
    loadAll({ country: rankingCountry ?? undefined, state: selectedState ?? undefined })
  }, [rankingCountry, selectedState, loadAll])

  async function updateField(masterId: string, updates: UserCompetitionUpdate) {
    try { await patch(masterId, updates) } catch { pushToast({ message: 'Failed to update competition', type: 'error' }) }
  }

  function openCompleteModal(comp: UserCompetition) {
    setCompleteForm({ body_weight_kg: comp.body_weight_kg ?? comp.weight_class_kg ?? 0, report: reportFromComp(comp) })
    setShowCompleteModal(comp.master_id)
  }

  async function handleMarkComplete(masterId: string) {
    try {
      const results = deriveResultsFromReport(completeForm.report)
      await complete(masterId, results, completeForm.body_weight_kg, completeForm.report)
      setShowCompleteModal(null)
      pushToast({ message: 'Competition marked as completed', type: 'success' })
    } catch { pushToast({ message: 'Failed to mark competition as completed', type: 'error' }) }
  }

  function updateCompleteReport(updates: Partial<PostMeetReport>) {
    setCompleteForm((prev) => ({ ...prev, report: { ...prev.report, ...updates } }))
  }

  function updateCompleteAttempt(index: number, updates: Partial<CompetitionAttempt>) {
    setCompleteForm((prev) => {
      const attempts = prev.report.attempts.map((attempt, i) => {
        if (i !== index) return attempt
        const next = { ...attempt, ...updates }
        if (updates.result && updates.result !== 'missed') { next.miss_reasons = []; next.miss_category = null }
        return normalizeAttempt(next, attempt.lift, attempt.attempt_number)
      })
      return { ...prev, report: { ...prev.report, attempts } }
    })
  }

  function calculateDotsScore(comp: UserCompetition): { dots: number; label: string } | null {
    const total = comp.user_status === 'completed' ? comp.results?.total_kg : comp.targets?.total_kg
    if (!total) return null
    const bodyweight = comp.body_weight_kg || comp.weight_class_kg
    if (!bodyweight) return null
    return { dots: calculateDots(total, bodyweight, sex), label: comp.user_status === 'completed' ? 'Actual' : 'Projected' }
  }

  const sortedCompetitions = useMemo(() => [...competitions].sort((a, b) => a.start_date.localeCompare(b.start_date)), [competitions])

  return (
    <Stack gap="md">
      <Group justify="space-between">
        <Stack gap={0}>
          <Group gap="xs">
            <Text component={Link} to="/designer" size="sm" c="dimmed" style={{ textDecoration: 'none' }}>Designer</Text>
            <Text c="dimmed">/</Text>
            <Title order={2}>Competitions</Title>
          </Group>
          <Text c="dimmed" size="sm" mt={4}>Browse upcoming competitions. Master details are read-only \u2014 edit only your personal fields.</Text>
        </Stack>
      </Group>

      <Paper withBorder p="md">
        <Group gap="md" align="flex-end">
          <TextInput label="Country" value={rankingCountry ?? ''} readOnly style={{ minWidth: 120 }} description="From your ranking settings" />
          <Select label="State / Region" placeholder="Select state" data={stateOptions} value={selectedState} onChange={setSelectedState} style={{ minWidth: 180 }} searchable />
          <Button leftSection={<Search size={16} />} onClick={handleSearch} loading={isLoading}>Search</Button>
        </Group>
      </Paper>

      {isLoading && competitions.length === 0 ? (
        <Paper withBorder p="xl"><Group justify="center"><Text c="dimmed">Loading competitions...</Text></Group></Paper>
      ) : sortedCompetitions.length === 0 ? (
        <Paper withBorder p="xl"><Group justify="center"><Text c="dimmed">No competitions found for this filter.</Text></Group></Paper>
      ) : (
        <Accordion variant="separated">
          {sortedCompetitions
            .filter((comp) => Boolean(comp.master_id))
            .map((comp) => {
            const dotsResult = calculateDotsScore(comp)
            const effRegStatus = effectiveRegistrationStatus(comp)
            const isCancelled = comp.cancelled
            const isAvailable = comp.user_status === 'available'
            const isDisabled = isCancelled

            return (
              <Accordion.Item key={comp.master_id} value={comp.master_id} style={isCancelled ? { opacity: 0.5 } : undefined}>
                <Accordion.Control>
                  <Group gap="sm" wrap="nowrap">
                    <Trophy size={20} style={{ color: isCancelled ? 'var(--mantine-color-gray-6)' : comp.user_status === 'completed' ? 'var(--mantine-color-green-6)' : comp.user_status === 'confirmed' ? 'var(--mantine-color-blue-6)' : 'var(--mantine-color-yellow-6)' }} />
                    <Stack gap={0}>
                      <Text fw={500}>{comp.name}</Text>
                      <Text size="xs" c="dimmed">{formatDateRange(comp)} {'\u2022'} {comp.federation_label || 'No federation'} {'\u2022'} {venueDisplay(comp)}</Text>
                    </Stack>
                    <Badge variant="light" color={STATUS_COLORS[comp.user_status] ?? 'gray'}>{STATUS_LABELS[comp.user_status] ?? comp.user_status}</Badge>
                    {isCancelled && <Badge variant="light" color="red">Cancelled</Badge>}
                  </Group>
                </Accordion.Control>
                <Accordion.Panel>
                  <Stack gap="md">
                    <SimpleGrid cols={{ base: 1, sm: 2, lg: 4 }} spacing="md">
                      <TextInput label="Name" value={comp.name} readOnly />
                      <TextInput label="Dates" value={formatDateRange(comp)} readOnly />
                      <TextInput label="Federation" value={comp.federation_label || ''} readOnly />
                      <TextInput label="Registration" value={effRegStatus === 'cancelled' ? 'Cancelled' : effRegStatus === 'closed' ? 'Closed' : effRegStatus === 'open' ? 'Open' : 'Unknown'} readOnly rightSection={effRegStatus === 'open' && comp.registration_url ? <Text component="a" href={comp.registration_url} target="_blank" size="xs" c="blue" style={{ textDecoration: 'none' }}>Register</Text> : null} />
                    </SimpleGrid>
                    <SimpleGrid cols={{ base: 1, sm: 2, lg: 4 }} spacing="md">
                      <TextInput label="Venue" value={venueDisplay(comp)} readOnly />
                      <TextInput label="Testing" value={comp.testing_status} readOnly />
                      <TextInput label="Event Type" value={comp.event_type || 'Unknown'} readOnly />
                      {comp.website_url && <TextInput label="Website" value={comp.website_url} readOnly rightSection={<Text component="a" href={comp.website_url} target="_blank" size="xs" c="blue" style={{ textDecoration: 'none' }}>Open</Text>} />}
                    </SimpleGrid>
                    <SimpleGrid cols={{ base: 1, sm: 2, lg: 4 }} spacing="md">
                      <Select label="Your Status" value={comp.user_status} data={STATUS_OPTIONS} onChange={(v) => { if (v && !isDisabled) updateField(comp.master_id, { user_status: v as UserCompetition['user_status'] }) }} disabled={readOnly || isCancelled} />
                      <TextInput type="number" label="Weight Class (kg)" value={comp.weight_class_kg ?? ''} onChange={(e) => { if (!readOnly && !isCancelled) updateField(comp.master_id, { weight_class_kg: e.currentTarget.value ? Number(e.currentTarget.value) : null }) }} disabled={readOnly || isCancelled} />
                      {comp.user_status === 'completed' && <TextInput type="number" label="Body Weight (kg)" value={comp.body_weight_kg ?? ''} onChange={(e) => { if (!readOnly && !isCancelled) updateField(comp.master_id, { body_weight_kg: e.currentTarget.value ? Number(e.currentTarget.value) : null }) }} disabled={readOnly || isCancelled} />}
                      <Checkbox mt={30} label="Hotel required" checked={comp.hotel_required} onChange={(event) => { if (!readOnly && !isCancelled) updateField(comp.master_id, { hotel_required: event.currentTarget.checked }) }} disabled={readOnly || isCancelled} />
                    </SimpleGrid>
                    <Stack gap="xs">
                      <Text size="xs" c="dimmed">{comp.user_status === 'completed' ? 'Results (kg)' : 'Targets (kg)'}</Text>
                      <SimpleGrid cols={{ base: 2, sm: 4 }} spacing="md">
                        {(['squat_kg', 'bench_kg', 'deadlift_kg', 'total_kg'] as const).map((lift) => (
                          <TextInput key={lift} type="number" label={lift.replace('_kg', '')} value={comp.user_status === 'completed' ? comp.results?.[lift] || 0 : comp.targets?.[lift] || 0} onChange={(e) => {
                            if (readOnly || isCancelled) return
                            const v = Number(e.currentTarget.value) || 0
                            const field = comp.user_status === 'completed' ? 'results' : 'targets'
                            const currentField = comp[field] || { squat_kg: 0, bench_kg: 0, deadlift_kg: 0, total_kg: 0 }
                            const newLifts = { squat_kg: currentField.squat_kg || 0, bench_kg: currentField.bench_kg || 0, deadlift_kg: currentField.deadlift_kg || 0, [lift]: v }
                            const newTotal = newLifts.squat_kg + newLifts.bench_kg + newLifts.deadlift_kg
                            updateField(comp.master_id, { [field]: { ...currentField, [lift]: v, total_kg: newTotal } })
                          }} disabled={lift === 'total_kg' || (comp.user_status === 'completed' && Boolean(comp.post_meet_report)) || readOnly || isCancelled} />
                        ))}
                      </SimpleGrid>
                    </Stack>
                    {dotsResult && !isAvailable && (
                      <Paper bg="var(--mantine-color-default)" p="sm" radius="md">
                        <Group gap="sm"><Target size={16} style={{ color: 'var(--mantine-color-blue-6)' }} /><Text size="sm"><Text span c="dimmed">{dotsResult.label} DOTS:</Text>{' '}<Text span fw={700} ff="monospace">{dotsResult.dots.toFixed(2)}</Text></Text></Group>
                      </Paper>
                    )}
                    {comp.post_meet_report && (
                      <Paper bg="var(--mantine-color-default)" p="sm" radius="md">
                        <Stack gap="sm">
                          <Group justify="space-between" align="center"><Text size="sm" fw={500}>Post-meet report</Text><Badge variant="light" color="green">{formatAttemptSummary(comp.post_meet_report)}</Badge></Group>
                          <Text size="sm"><Text span c="dimmed">Sleep:</Text> {comp.post_meet_report.sleep_hours ?? ''} h</Text>
                        </Stack>
                      </Paper>
                    )}
                    <Textarea label="Notes" value={comp.notes || ''} onChange={(e) => { if (!readOnly && !isCancelled) updateField(comp.master_id, { notes: e.currentTarget.value }) }} rows={2} placeholder="Competition notes..." autosize disabled={readOnly || isCancelled} />
                    <Group justify="flex-end" pt="sm">
                      {comp.user_status !== 'completed' && new Date(comp.start_date) < new Date() && !isCancelled && (
                        <Button variant="light" color="green" size="sm" leftSection={<CheckCircle size={14} />} onClick={() => openCompleteModal(comp)} disabled={readOnly}>Mark as Completed</Button>
                      )}
                      {comp.user_status === 'completed' && !isCancelled && (
                        <Button variant="light" color="green" size="sm" leftSection={<CheckCircle size={14} />} onClick={() => openCompleteModal(comp)} disabled={readOnly}>{comp.post_meet_report ? 'Edit Post-Meet Report' : 'Add Post-Meet Report'}</Button>
                      )}
                    </Group>
                  </Stack>
                </Accordion.Panel>
              </Accordion.Item>
            )
          })}
        </Accordion>
      )}

      <Modal opened={showCompleteModal !== null} onClose={() => setShowCompleteModal(null)} title="Post-Meet Report" size="xl">
        <Stack gap="md">
          <Text size="sm" c="dimmed">Log the attempt card and meet-day context.</Text>
          <SimpleGrid cols={{ base: 1, sm: 3 }} spacing="md">
            <TextInput type="number" label="Body Weight at Weigh-in (kg)" value={completeForm.body_weight_kg} onChange={(e) => setCompleteForm((p) => ({ ...p, body_weight_kg: Number(e.currentTarget.value) || 0 }))} disabled={readOnly} />
            <TextInput type="number" label="Sleep before meet (hours)" value={completeForm.report.sleep_hours ?? ''} onChange={(e) => updateCompleteReport({ sleep_hours: e.currentTarget.value !== '' ? Number(e.currentTarget.value) : null })} disabled={readOnly} />
            <TextInput type="number" label="Attempt selection grade" value={completeForm.report.attempt_selection_grade ?? ''} onChange={(e) => updateCompleteReport({ attempt_selection_grade: e.currentTarget.value !== '' ? Math.max(1, Math.min(5, Math.round(Number(e.currentTarget.value)))) as 1 | 2 | 3 | 4 | 5 : null })} disabled={readOnly} />
          </SimpleGrid>
          <Text size="sm" fw={500}>Attempt Card</Text>
          <SimpleGrid cols={{ base: 1, sm: 3 }} spacing="xs">
            {completeForm.report.attempts.map((attempt, index) => (
              <Paper key={attempt.lift + '-' + attempt.attempt_number} withBorder p="xs">
                <Text size="xs" fw={500}>{LIFT_LABELS[attempt.lift]} {attempt.attempt_number}</Text>
                <Group gap="xs" mt={4}>
                  <TextInput type="number" placeholder="kg" value={attempt.kg ?? ''} onChange={(e) => updateCompleteAttempt(index, { kg: e.currentTarget.value !== '' ? Number(e.currentTarget.value) : null })} size="xs" style={{ width: 70 }} disabled={readOnly} />
                  <Select value={attempt.result} data={ATTEMPT_RESULT_OPTIONS} onChange={(value) => updateCompleteAttempt(index, { result: (value || 'not_taken') as CompetitionAttemptResult })} size="xs" style={{ width: 100 }} disabled={readOnly} />
                </Group>
              </Paper>
            ))}
          </SimpleGrid>
          <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="md">
            <Textarea label="Warm-up timing" value={completeForm.report.warmup_timing} onChange={(e) => updateCompleteReport({ warmup_timing: e.currentTarget.value })} autosize minRows={2} disabled={readOnly} />
            <Textarea label="Sleep / travel" value={completeForm.report.travel_notes} onChange={(e) => updateCompleteReport({ travel_notes: e.currentTarget.value })} autosize minRows={2} disabled={readOnly} />
            <Textarea label="Food before" value={completeForm.report.pre_meet_food} onChange={(e) => updateCompleteReport({ pre_meet_food: e.currentTarget.value })} autosize minRows={2} disabled={readOnly} />
            <Textarea label="Food during" value={completeForm.report.during_meet_food} onChange={(e) => updateCompleteReport({ during_meet_food: e.currentTarget.value })} autosize minRows={2} disabled={readOnly} />
            <TextInput type="number" label="Caffeine total (mg)" value={completeForm.report.caffeine_mg ?? ''} onChange={(e) => updateCompleteReport({ caffeine_mg: e.currentTarget.value !== '' ? Number(e.currentTarget.value) : null })} disabled={readOnly} />
            <Textarea label="Caffeine timing" value={completeForm.report.caffeine_timing} onChange={(e) => updateCompleteReport({ caffeine_timing: e.currentTarget.value })} autosize minRows={2} disabled={readOnly} />
            <Textarea label="Equipment issues" value={completeForm.report.equipment_issues} onChange={(e) => updateCompleteReport({ equipment_issues: e.currentTarget.value })} autosize minRows={2} disabled={readOnly} />
            <Textarea label="Commands missed" value={completeForm.report.commands_missed} onChange={(e) => updateCompleteReport({ commands_missed: e.currentTarget.value })} autosize minRows={2} disabled={readOnly} />
          </SimpleGrid>
          <Textarea label="Meet notes" value={completeForm.report.notes} onChange={(e) => updateCompleteReport({ notes: e.currentTarget.value })} autosize minRows={3} disabled={readOnly} />
          <Group justify="flex-end" gap="sm" pt="sm">
            <Button variant="default" onClick={() => setShowCompleteModal(null)}>Cancel</Button>
            <Button onClick={() => showCompleteModal && handleMarkComplete(showCompleteModal)} disabled={readOnly}>Complete</Button>
          </Group>
        </Stack>
      </Modal>
    </Stack>
  )
}
