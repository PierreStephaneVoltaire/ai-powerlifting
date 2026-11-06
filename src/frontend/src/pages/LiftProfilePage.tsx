import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { AlertCircle, ArrowLeft, Film, RotateCcw, Save, Sparkles, Upload } from 'lucide-react'
import {
  Alert,
  Badge,
  Box,
  Button,
  Divider,
  Grid,
  Group,
  Loader,
  Paper,
  SegmentedControl,
  SimpleGrid,
  Stack,
  Text,
  Title,
  ActionIcon,
} from '@mantine/core'
import { useProgramStore } from '@/store/programStore'
import { useUiStore } from '@/store/uiStore'
import { useSettingsStore } from '@/store/settingsStore'
import { useVideoUploadStore } from '@/store/videoUploadStore'
import {
  estimateLiftProfileStimulus,
  fetchE1rmMultiplierSuggestions,
} from '@/api/client'
import { LiftProfileForm } from '@/components/lift-profiles/LiftProfileForm'
import DraftNumberInput from '@/components/sessions/DraftNumberInput'
import { defaultLiftProfile as defaultProfile, mergeLiftProfiles as mergeProfiles, missingOptions, normalizeLiftProfile as normalizeProfile } from '@/utils/liftProfile'
import type { LiftProfile, LiftProfileVideoAngle } from '@powerlifting/types'
import { toDisplayUnit, formatDisplayWeight } from '@/utils/units'
import { useAuth } from '@/auth/AuthProvider'
import { formatFileSize, isValidVideoType, MAX_VIDEO_SIZE, uploadVideo } from '@/utils/s3'

const LIFT_ORDER = ['squat', 'bench', 'deadlift'] as const
const FORM_ANGLES: LiftProfileVideoAngle[] = ['front', 'side', 'diagonal']
const FORM_ANGLE_LABELS: Record<LiftProfileVideoAngle, string> = { front: 'Front', side: 'Side', diagonal: 'Diagonal' }

interface MultiplierSuggestion {
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

function multiplierValue(value: string | number): number {
  if (typeof value !== 'number' || !Number.isFinite(value)) return 1.00
  return Math.max(0.85, Math.min(1.10, value))
}

function coefficientValue(value: string | number): number {
  if (typeof value !== 'number' || !Number.isFinite(value)) return 1
  return Math.max(1, Math.min(2, value))
}

export default function LiftProfilePage() {
  const { readOnly } = useAuth()
  const { lift: liftParam } = useParams<{ lift: string }>()
  const navigate = useNavigate()
  const { program, version, updateLiftProfiles } = useProgramStore()
  const { pushToast } = useUiStore()
  const { unit } = useSettingsStore()
  const trackUpload = useVideoUploadStore((state) => state.track)

  const lift = LIFT_ORDER.includes(liftParam as LiftProfile['lift'])
    ? liftParam as LiftProfile['lift']
    : null

  const [draft, setDraft] = useState<LiftProfile | null>(null)
  const [suggestions, setSuggestions] = useState<Record<string, MultiplierSuggestion | null>>({})
  const [ignoredSuggestion, setIgnoredSuggestion] = useState(false)
  
  // Current max preview data
  const rawMax = lift ? program?.current_maxes?.[lift] ?? program?.meta.manual_maxes?.[lift] ?? 0 : 0
  const adjustedMax = rawMax * (draft?.e1rm_multiplier ?? 1.00)

  const [estimating, setEstimating] = useState(false)
  const [saving, setSaving] = useState(false)
  const [barWeight, setBarWeight] = useState('20')
  const [barUnit, setBarUnit] = useState<'kg' | 'lb'>('kg')
  const [uploadingAngle, setUploadingAngle] = useState<LiftProfileVideoAngle | null>(null)
  const uploadInput = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (!lift || !program) return
    const initial = normalizeProfile(program.lift_profiles?.find((profile) => profile.lift === lift) ?? defaultProfile(lift))
    setDraft(initial)
    setIgnoredSuggestion(false)

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

  const updateDraft = (updates: Partial<LiftProfile>) => {
    setDraft((current) => current ? normalizeProfile({ ...current, ...updates }) : current)
  }

  const chooseFormVideo = (angle: LiftProfileVideoAngle) => {
    setUploadingAngle(angle)
    uploadInput.current?.click()
  }

  const uploadFormVideo = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    const angle = uploadingAngle
    event.target.value = ''
    if (!file || !angle || !lift || !draft) return
    if (!isValidVideoType(file)) {
      pushToast({ message: 'Invalid file type. Please use MP4, MOV, or WebM.', type: 'error' })
      return
    }
    if (file.size > MAX_VIDEO_SIZE) {
      pushToast({ message: `File too large. Maximum size is ${formatFileSize(MAX_VIDEO_SIZE)}.`, type: 'error' })
      return
    }
    const existing = draft.form_videos?.[angle]
    if (existing?.video_id && !globalThis.confirm(`Replace the existing ${FORM_ANGLE_LABELS[angle].toLowerCase()} recording?`)) return
    setUploadingAngle(angle)
    try {
      const result = await trackUpload({ file }, (onProgress) => uploadVideo(version, {
        file,
        sessionDate: new Date().toISOString().slice(0, 10),
        lift,
        angle,
        onProgress,
      }))
      const pending = {
        ...(existing ?? result.video),
        ...(!existing ? result.video : {}),
        lift,
        angle,
        pending_media_id: result.video.video_id,
        processing_status: 'pending' as const,
        thumbnail_status: 'pending' as const,
        source_filename: file.name,
        source_size: file.size,
      }
      const next = normalizeProfile({ ...draft, form_videos: { ...(draft.form_videos ?? {}), [angle]: pending } })
      setDraft(next)
      await updateLiftProfiles(mergeProfiles(program?.lift_profiles, next))
      pushToast({ message: `${FORM_ANGLE_LABELS[angle]} recording is processing`, type: 'success' })
    } catch (error) {
      pushToast({ message: 'Form video upload failed; retry the file', type: 'error' })
    } finally {
      setUploadingAngle(null)
    }
  }

  const runEstimate = async () => {
    if (!draft) return
    if (missingOptions(draft).length) {
      pushToast({ message: 'Choose every technique option before estimating stimulus', type: 'error' })
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
      pushToast({ message: error instanceof Error ? error.message : 'AI stimulus estimate failed', type: 'error' })
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

  const missing = draft ? missingOptions(draft) : []
  const canEstimate = Boolean(draft) && missing.length === 0

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
            {canEstimate ? 'Estimate ready' : `${missing.length} option${missing.length === 1 ? '' : 's'} left`}
          </Badge>
          {!canEstimate && <Text size="xs" c="dimmed">Still to choose: {missing.join(', ')}</Text>}
        </Stack>

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
          <Button variant="light" leftSection={<Sparkles size={16} />} loading={estimating} disabled={!canEstimate || readOnly} onClick={runEstimate}>
            Estimate Stimulus
          </Button>
          <Button leftSection={<Save size={16} />} loading={saving} onClick={save} disabled={readOnly}>
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
          {showSuggestion && suggestion && (
          <Paper withBorder p="md">
            <Stack gap="lg">
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
                        onClick={() => updateDraft({ e1rm_multiplier: suggestion.suggested_multiplier })}
                        disabled={readOnly}
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
            </Stack>
          </Paper>
          )}

          <LiftProfileForm profile={draft} onChange={(next) => setDraft(normalizeProfile(next))} readOnly={readOnly} />

          <Paper withBorder p="md">
            <Stack gap="sm">
              <input ref={uploadInput} type="file" accept="video/mp4,video/quicktime,video/webm,video/x-msvideo" onChange={uploadFormVideo} hidden />
              <Stack gap={0}>
                <Text fw={600}>Form recordings</Text>
                <Text size="xs" c="dimmed">Optional three-minute recordings. Show the full lift and leave space around the bar.</Text>
              </Stack>
              <SimpleGrid cols={{ base: 1, sm: 3 }}>
                {FORM_ANGLES.map((angle) => {
                  const video = draft.form_videos?.[angle]
                  const status = video?.processing_status ?? video?.thumbnail_status
                  return (
                    <Paper key={angle} withBorder p="sm">
                      <Stack gap="xs">
                        <Group justify="space-between">
                          <Text fw={500}>{FORM_ANGLE_LABELS[angle]}</Text>
                          {status === 'failed' ? <AlertCircle size={16} color="var(--mantine-color-red-6)" /> : <Film size={16} />}
                        </Group>
                        <Text size="xs" c="dimmed">
                          {status === 'pending' || status === 'processing' ? 'Processing…' : status === 'failed' ? 'Processing failed' : video?.video_id ? 'Ready' : 'No recording'}
                        </Text>
                        {video?.failure && <Text size="xs" c="red">{video.failure}</Text>}
                        <Button size="compact-sm" variant="light" leftSection={<Upload size={14} />} onClick={() => chooseFormVideo(angle)} disabled={readOnly || uploadingAngle !== null} loading={uploadingAngle === angle}>
                          {video?.video_id ? 'Replace' : 'Upload'}
                        </Button>
                      </Stack>
                    </Paper>
                  )
                })}
              </SimpleGrid>
            </Stack>
          </Paper>

          <Paper withBorder p="md">
            <Stack gap="sm">
              <Group justify="space-between" align="flex-end">
                <Stack gap={0}>
                  <Text fw={600}>Warm-up red-plate guide</Text>
                  <Text size="xs" c="dimmed">Advisory only; it updates when your current max changes.</Text>
                </Stack>
                <Group gap="xs" align="flex-end">
                  <DraftNumberInput label="Bar" value={Number(barWeight)} isValid={(value) => value >= 0} onValueChange={(next) => setBarWeight(next === null ? '' : String(next))} w={90} />
                  <SegmentedControl size="xs" data={['kg', 'lb']} value={barUnit} onChange={(value) => setBarUnit(value as 'kg' | 'lb')} />
                </Group>
              </Group>
              {rawMax > 0 && (() => {
                const enteredBar = Number(barWeight)
                const barKg = Number.isFinite(enteredBar) && enteredBar >= 0 ? barUnit === 'kg' ? enteredBar : enteredBar / 2.2046226218 : 20
                const platesPerSide = Math.max(0, Math.floor((rawMax - barKg) / 50))
                const recommendedKg = platesPerSide < 2 ? barKg : barKg + (platesPerSide - 1) * 50
                return <Text size="sm">For a {formatDisplayWeight(rawMax, unit)} {unit} max: <b>{platesPerSide < 2 ? 'empty bar' : `${formatDisplayWeight(recommendedKg, unit)} ${unit}`}</b> ({platesPerSide < 2 ? 0 : platesPerSide - 1} red plate{platesPerSide - 1 === 1 ? '' : 's'} per side).</Text>
              })()}
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
                    onClick={() => updateDraft({ e1rm_multiplier: 1.00 })}
                    title="Reset to 1.00"
                    disabled={readOnly}
                  >
                    <RotateCcw size={14} />
                  </ActionIcon>
                </Group>
                <DraftNumberInput
                  value={draft.e1rm_multiplier ?? 1.00}
                  isValid={(value) => value >= 0.85 && value <= 1.10}
                  commitOnlyValid
                  onValueChange={(next) => updateDraft({ e1rm_multiplier: multiplierValue(next ?? 1) })}
                  disabled={readOnly}
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
                        <Text size="sm" fw={700}>{formatDisplayWeight(rawMax, unit)} {unit}</Text>
                      </Stack>
                      <Stack gap={0} ta="right">
                        <Text size="10px" tt="uppercase" c="dimmed">Adjusted e1RM</Text>
                        <Text size="sm" fw={700} c="blue">{formatDisplayWeight(adjustedMax, unit)} {unit}</Text>
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
                  disabled={readOnly}
                />
              </Stack>
            </Paper>
          </SimpleGrid>

          <SimpleGrid cols={1} spacing="md">
            <Paper withBorder p="md">
              <Stack gap="xs">
                <Text size="sm" fw={500}>Stimulus Coefficient</Text>
                <DraftNumberInput
                  value={draft.stimulus_coefficient ?? 1}
                  isValid={(value) => value >= 1 && value <= 2}
                  commitOnlyValid
                  onValueChange={(next) => updateDraft({ stimulus_coefficient: coefficientValue(next ?? 1) })}
                  disabled={readOnly}
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
