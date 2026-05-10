import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ArrowLeft, Save, Sparkles, RotateCcw } from 'lucide-react'
import {
  Alert,
  Badge,
  Box,
  Button,
  Divider,
  Grid,
  Group,
  Loader,
  NumberInput,
  Paper,
  SegmentedControl,
  SimpleGrid,
  Stack,
  Text,
  Textarea,
  TextInput,
  Title,
  ActionIcon,
} from '@mantine/core'
import { useProgramStore } from '@/store/programStore'
import { useUiStore } from '@/store/uiStore'
import { useSettingsStore } from '@/store/settingsStore'
import {
  estimateLiftProfileStimulus,
  fetchE1rmMultiplierSuggestions,
  reviewLiftProfile,
  rewriteLiftProfile,
  type LiftProfileReview,
} from '@/api/client'
import type { LiftProfile } from '@powerlifting/types'
import { toDisplayUnit } from '@/utils/units'

const LIFT_ORDER = ['squat', 'bench', 'deadlift'] as const
const PROFILE_ESTIMATE_READY_SCORE = 55

export interface MultiplierSuggestion {
  lift: string
  suggested_multiplier: number
  current_multiplier: number
  difference: number
  basis: string
  sample_size: number
}

const LIFT_LABELS: Record<LiftProfile['lift'], string> = {
  squat: 'Squat',
  bench: 'Bench',
  deadlift: 'Deadlift',
}

const LIFT_STYLE_PLACEHOLDERS: Record<LiftProfile['lift'], string> = {
  squat: 'High bar or low bar, stance width, depth, torso angle, bar path, tempo/eccentric, and how ROM compares with competition standard.',
  bench: 'Grip width, arch, touch point, leg drive, pause/sink, bar path, lockout, and how ROM compares with competition standard.',
  deadlift: 'Conventional or sumo, stance/grip, wedge/start position, lockout style, tempo, and how ROM compares with competition standard.',
}

const STICKING_PLACEHOLDERS: Record<LiftProfile['lift'], string> = {
  squat: 'Exact ROM where it slows/fails, e.g. out of the hole, above parallel, knee/hip shift, bracing loss, speed loss.',
  bench: 'Exact ROM where it slows/fails, e.g. off chest, mid-range, lockout, elbow flare, bar drift, triceps/pec limit.',
  deadlift: 'Exact ROM where it slows/fails, e.g. off floor, below knee, above knee, lockout, hips rise, bar drift.',
}

function defaultProfile(lift: LiftProfile['lift']): LiftProfile {
  return {
    lift,
    style_notes: '',
    sticking_points: '',
    primary_muscle: '',
    volume_tolerance: 'moderate',
    stimulus_coefficient: 1,
    e1rm_multiplier: 1.00,
  }
}

function normalizeProfile(profile: LiftProfile): LiftProfile {
  const multiplier = profile.e1rm_multiplier ?? 1.00
  const clampedMultiplier = Math.max(0.85, Math.min(1.10, multiplier))

  return {
    ...defaultProfile(profile.lift),
    ...profile,
    stimulus_coefficient: Math.max(1, Math.min(2, profile.stimulus_coefficient ?? 1)),
    e1rm_multiplier: Number(clampedMultiplier.toFixed(2)),
  }
}

function mergeProfiles(profiles: LiftProfile[] | undefined, replacement: LiftProfile): LiftProfile[] {
  return LIFT_ORDER.map((lift) => {
    if (lift === replacement.lift) return normalizeProfile(replacement)
    return normalizeProfile(profiles?.find((profile) => profile.lift === lift) ?? defaultProfile(lift))
  })
}

function multiplierValue(value: string | number): number {
  if (typeof value !== 'number' || !Number.isFinite(value)) return 1.00
  return Math.max(0.85, Math.min(1.10, value))
}

function coefficientValue(value: string | number): number {
  if (typeof value !== 'number' || !Number.isFinite(value)) return 1
  return Math.max(1, Math.min(2, value))
}

export default function LiftProfilePage() {
  const { lift: liftParam } = useParams<{ lift: string }>()
  const navigate = useNavigate()
  const { program, updateLiftProfiles } = useProgramStore()
  const { pushToast } = useUiStore()
  const { unit } = useSettingsStore()

  const lift = LIFT_ORDER.includes(liftParam as LiftProfile['lift'])
    ? liftParam as LiftProfile['lift']
    : null

  const [draft, setDraft] = useState<LiftProfile | null>(null)
  const [suggestions, setSuggestions] = useState<Record<string, MultiplierSuggestion | null>>({})
  const [ignoredSuggestion, setIgnoredSuggestion] = useState(false)
  
  // Current max preview data
  const rawMax = lift ? program?.current_maxes?.[lift] ?? program?.meta.manual_maxes?.[lift] ?? 0 : 0
  const adjustedMax = rawMax * (draft?.e1rm_multiplier ?? 1.00)

  const [review, setReview] = useState<LiftProfileReview | null>(null)
  const [reviewing, setReviewing] = useState(false)
  const [rewriting, setRewriting] = useState(false)
  const [estimating, setEstimating] = useState(false)
  const [saving, setSaving] = useState(false)

  const runReview = async (profile: LiftProfile, showError = true) => {
    setReviewing(true)
    try {
      setReview(await reviewLiftProfile(profile))
    } catch (error) {
      if (showError) pushToast({ message: 'AI profile review failed', type: 'error' })
    } finally {
      setReviewing(false)
    }
  }

  useEffect(() => {
    if (!lift || !program) return
    const initial = normalizeProfile(program.lift_profiles?.find((profile) => profile.lift === lift) ?? defaultProfile(lift))
    setDraft(initial)
    setReview(null)
    setIgnoredSuggestion(false)
    if (Math.abs((initial.stimulus_coefficient ?? 1) - 1) < 0.001) {
      void runReview(initial, false)
    }

    const loadSuggestions = async () => {
      try {
        const result = await fetchE1rmMultiplierSuggestions()
        setSuggestions(result)
      } catch (err) {
        console.warn('Failed to load multiplier suggestions', err)
      }
    }
    void loadSuggestions()
  }, [lift, program])

  const updateDraft = (updates: Partial<LiftProfile>, resetReview = true) => {
    setDraft((current) => current ? normalizeProfile({ ...current, ...updates }) : current)
    if (resetReview) setReview(null)
  }

  const runRewrite = async () => {
    if (!draft) return
    setRewriting(true)
    try {
      const result = await rewriteLiftProfile(draft)
      const next = normalizeProfile({ ...draft, ...result })
      setDraft(next)
      setReview(null)
      pushToast({ message: 'Lift profile rewritten', type: 'success' })
    } catch (error) {
      pushToast({ message: 'AI rewrite failed', type: 'error' })
    } finally {
      setRewriting(false)
    }
  }

  const runEstimate = async () => {
    if (!draft) return
    const score = review?.completeness_score ?? 0
    if (score < PROFILE_ESTIMATE_READY_SCORE) {
      pushToast({ message: `Profile score needs ${PROFILE_ESTIMATE_READY_SCORE}% before estimating stimulus`, type: 'error' })
      return
    }
    setEstimating(true)
    try {
      const result = await estimateLiftProfileStimulus(draft)
      setDraft(normalizeProfile({
        ...draft,
        stimulus_coefficient: result.stimulus_coefficient,
        stimulus_coefficient_confidence: result.stimulus_coefficient_confidence,
        stimulus_coefficient_reasoning: result.stimulus_coefficient_reasoning,
        stimulus_coefficient_updated_at: result.stimulus_coefficient_updated_at,
      }))
      pushToast({ message: 'Stimulus coefficient applied', type: 'success' })
    } catch (error) {
      pushToast({ message: 'AI stimulus estimate failed', type: 'error' })
    } finally {
      setEstimating(false)
    }
  }

  const save = async () => {
    if (!draft) return
    setSaving(true)
    try {
      await updateLiftProfiles(mergeProfiles(program?.lift_profiles, draft))
      pushToast({ message: 'Lift profile saved', type: 'success' })
      navigate('/')
    } catch (error) {
      pushToast({ message: 'Failed to save lift profile', type: 'error' })
    } finally {
      setSaving(false)
    }
  }

  const score = review?.completeness_score ?? 0
  const canEstimate = score >= PROFILE_ESTIMATE_READY_SCORE

  const suggestion = lift ? suggestions[lift] : null
  const showSuggestion = suggestion && !ignoredSuggestion && Math.abs(suggestion.difference) >= 0.01

  const sidePanel = (
    <Paper withBorder p="md" style={{ minHeight: '100%' }}>
      <Stack gap="md" h="100%">
        <SimpleGrid cols={2}>
          <Stack gap={0}>
            <Text size="xs" c="dimmed">Stimulus Coeff.</Text>
            <Text fz="xl" fw={700}>x{(draft?.stimulus_coefficient ?? 1).toFixed(2)}</Text>
          </Stack>
          <Stack gap={0}>
            <Text size="xs" c="dimmed">e1RM Multiplier</Text>
            <Text fz="xl" fw={700}>x{(draft?.e1rm_multiplier ?? 1).toFixed(2)}</Text>
          </Stack>
        </SimpleGrid>

        <Stack gap="xs">
          <Badge color={canEstimate ? 'green' : 'yellow'} variant="light" w="fit-content">
            {review ? (canEstimate ? 'Estimate ready' : `Needs ${PROFILE_ESTIMATE_READY_SCORE}%`) : 'Review needed'}
          </Badge>
          {review && (
            <Text size="sm" c="dimmed">
              Score {review.completeness_score}%: style/setup 40, sticking point 35, primary driver 25.
            </Text>
          )}
        </Stack>

        {review?.score_breakdown && (
          <Stack gap="xs">
            {Object.entries(review.score_breakdown).map(([key, part]) => (
              <Paper key={key} withBorder p="xs">
                <Group justify="space-between" align="flex-start">
                  <Text size="sm" fw={500} tt="capitalize">{key.split('_').join(' ')}</Text>
                  <Text size="sm" fw={700}>{part.score}/{part.max}</Text>
                </Group>
                {(part.notes ?? []).slice(0, 2).map((note) => (
                  <Text key={note} size="xs" c="dimmed">{note}</Text>
                ))}
              </Paper>
            ))}
          </Stack>
        )}

        {review && (review.missing_details.length > 0 || review.suggestions.length > 0) && (
          <Alert color={canEstimate ? 'blue' : 'yellow'} variant="light">
            <Stack gap={4}>
              {[...review.missing_details, ...review.suggestions].slice(0, 6).map((item) => (
                <Text key={item} size="xs">{item}</Text>
              ))}
            </Stack>
          </Alert>
        )}

        {draft?.stimulus_coefficient_reasoning && (
          <Alert color="blue" variant="light">
            <Text size="sm">{draft.stimulus_coefficient_reasoning}</Text>
            {draft.stimulus_coefficient_confidence && (
              <Badge mt="xs" color="blue" variant="light">{draft.stimulus_coefficient_confidence} confidence</Badge>
            )}
          </Alert>
        )}

        <Divider />

        <Stack gap="xs" mt="auto">
          <Button variant="light" leftSection={<Sparkles size={16} />} loading={reviewing} onClick={() => draft && runReview(draft)}>
            Review
          </Button>
          <Button variant="light" leftSection={<Sparkles size={16} />} loading={rewriting} onClick={runRewrite}>
            Rewrite
          </Button>
          <Button variant="light" leftSection={<Sparkles size={16} />} loading={estimating} disabled={!canEstimate} onClick={runEstimate}>
            Estimate Stimulus
          </Button>
          <Button leftSection={<Save size={16} />} loading={saving} onClick={save}>
            Save Profile
          </Button>
        </Stack>
      </Stack>
    </Paper>
  )

  if (!lift) {
    return (
      <Alert color="red" variant="light">Unknown lift profile.</Alert>
    )
  }

  if (!program || !draft) {
    return (
      <Group justify="center" mih="50vh">
        <Loader />
      </Group>
    )
  }

  return (
    <Stack gap="lg">
      <Group justify="space-between" align="flex-start">
        <Stack gap={2}>
          <Text component={Link} to="/" size="sm" c="dimmed" style={{ textDecoration: 'none' }}>
            Dashboard
          </Text>
          <Title order={1}>{LIFT_LABELS[lift]} Profile</Title>
        </Stack>
        <Button component={Link} to="/" variant="default" leftSection={<ArrowLeft size={16} />}>
          Back
        </Button>
      </Group>

      <Box hiddenFrom="lg">
        {sidePanel}
      </Box>

      <Grid gap="lg" align="flex-start">
        <Grid.Col span={{ base: 12, lg: 8 }}>
          <Stack gap="lg" style={{ minWidth: 0 }}>
          <Paper withBorder p="md">
            <Stack gap="lg">
              {showSuggestion && suggestion && (
                <Alert 
                  color="blue" 
                  title="Suggested Calibration" 
                  variant="light"
                  icon={<Sparkles size={16} />}
                >
                  <Stack gap="xs">
                    <Text size="sm">
                      We suggest a multiplier of <b>{suggestion.suggested_multiplier.toFixed(2)}</b>.
                    </Text>
                    <Text size="xs" c="dimmed">{suggestion.basis}</Text>
                    <Group gap="xs">
                      <Button 
                        size="compact-xs" 
                        variant="filled" 
                        onClick={() => updateDraft({ e1rm_multiplier: suggestion.suggested_multiplier }, false)}
                      >
                        Apply
                      </Button>
                      <Button 
                        size="compact-xs" 
                        variant="subtle" 
                        color="gray"
                        onClick={() => setIgnoredSuggestion(true)}
                      >
                        Ignore
                      </Button>
                    </Group>
                  </Stack>
                </Alert>
              )}

              <Textarea
                label="Style & Setup"
                value={draft.style_notes}
                onChange={(event) => updateDraft({ style_notes: event.currentTarget.value })}
                placeholder={LIFT_STYLE_PLACEHOLDERS[lift]}
                autosize={false}
                styles={{ input: { minHeight: '44vh', width: '100%', resize: 'vertical', overflowY: 'auto' } }}
              />
              <Textarea
                label="Sticking Points"
                value={draft.sticking_points}
                onChange={(event) => updateDraft({ sticking_points: event.currentTarget.value })}
                placeholder={STICKING_PLACEHOLDERS[lift]}
                autosize={false}
                styles={{ input: { minHeight: '34vh', width: '100%', resize: 'vertical', overflowY: 'auto' } }}
              />
              <TextInput
                label="Primary Muscle Driver"
                value={draft.primary_muscle}
                onChange={(event) => updateDraft({ primary_muscle: event.currentTarget.value })}
                placeholder={lift === 'squat' ? 'Quad dominant' : lift === 'bench' ? 'Tricep dominant' : 'Glute dominant'}
              />
            </Stack>
          </Paper>

          <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="md">
            <Paper withBorder p="md">
              <Stack gap="xs">
                <Group justify="space-between">
                  <Text size="sm" fw={500}>e1RM Multiplier</Text>
                  <ActionIcon 
                    variant="subtle" 
                    color="gray" 
                    size="sm" 
                    onClick={() => updateDraft({ e1rm_multiplier: 1.00 }, false)}
                    title="Reset to 1.00"
                  >
                    <RotateCcw size={14} />
                  </ActionIcon>
                </Group>
                <NumberInput
                  min={0.85}
                  max={1.10}
                  step={0.01}
                  decimalScale={2}
                  value={draft.e1rm_multiplier ?? 1.00}
                  onChange={(value) => updateDraft({ e1rm_multiplier: multiplierValue(value) }, false)}
                />
                <Text size="xs" c="dimmed">
                  Use this if the app consistently overestimates or underestimates your real
                  max for this lift. 1.00 means no adjustment. 0.96 lowers estimates by 4%.
                </Text>

                {rawMax > 0 && (
                  <Box mt="xs" p="xs" style={{ background: 'var(--mantine-color-gray-0)', borderRadius: '4px' }}>
                    <Text size="xs" fw={500} mb={4}>Preview Impact:</Text>
                    <Group justify="space-between">
                      <Stack gap={0}>
                        <Text size="10px" tt="uppercase" c="dimmed">Raw e1RM</Text>
                        <Text size="sm" fw={700}>{toDisplayUnit(rawMax, unit).toFixed(1)} {unit}</Text>
                      </Stack>
                      <Stack gap={0} ta="right">
                        <Text size="10px" tt="uppercase" c="dimmed">Adjusted e1RM</Text>
                        <Text size="sm" fw={700} c="blue">{toDisplayUnit(adjustedMax, unit).toFixed(1)} {unit}</Text>
                      </Stack>
                    </Group>
                  </Box>
                )}
              </Stack>
            </Paper>

            <Paper withBorder p="md">
              <Stack gap="xs">
                <Text size="sm" fw={500}>Volume Recovery Tolerance</Text>
                <SegmentedControl
                  fullWidth
                  data={[
                    { label: 'Low', value: 'low' },
                    { label: 'Moderate', value: 'moderate' },
                    { label: 'High', value: 'high' },
                  ]}
                  value={draft.volume_tolerance}
                  onChange={(value) => updateDraft({ volume_tolerance: value as LiftProfile['volume_tolerance'] })}
                />
              </Stack>
            </Paper>
          </SimpleGrid>

          <SimpleGrid cols={1} spacing="md">
            <Paper withBorder p="md">
              <Stack gap="xs">
                <Text size="sm" fw={500}>Stimulus Coefficient</Text>
                <NumberInput
                  min={1}
                  max={2}
                  step={0.05}
                  decimalScale={2}
                  value={draft.stimulus_coefficient ?? 1}
                  onChange={(value) => updateDraft({ stimulus_coefficient: coefficientValue(value) }, false)}
                />
                <Text size="xs" c="dimmed">Range is 1.00 to 2.00. Baseline competition-standard stimulus is 1.00.</Text>
              </Stack>
            </Paper>
          </SimpleGrid>
          </Stack>
        </Grid.Col>

        <Grid.Col span={{ base: 12, lg: 4 }} visibleFrom="lg">
          <Box style={{ position: 'sticky', top: 76, minHeight: 'calc(100dvh - 96px)' }}>
            {sidePanel}
          </Box>
        </Grid.Col>
      </Grid>
    </Stack>
  )
}
