import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import {
  Alert,
  Badge,
  Button,
  Center,
  Group,
  Loader,
  MultiSelect,
  NumberInput,
  Paper,
  Progress,
  Radio,
  Select,
  Stack,
  Stepper,
  Text,
  Textarea,
  TextInput,
  Title,
} from '@mantine/core'
import { AlertCircle, ArrowLeft, Check, ChevronLeft, ChevronRight, LogIn, Save } from 'lucide-react'
import { useAuth } from '@/auth/AuthProvider'
import {
  getOnboardingStatus,
  setRole as apiSetRole,
  submitAthleteBasics,
  submitOnboardingProfile,
  type OnboardingStatus,
} from '@/api/onboarding'
import { fetchFederations } from '@/api/client'
import type { AppRole, UserSettings } from '@/api/settings'
import { getSettings } from '@/api/settings'
import { onboardingStepFor } from './onboardingStep'
import type { MasterFederation } from '@powerlifting/types'
import { fromDisplayUnit, toDisplayUnit } from '@/utils/units'
import { readDraft, removeDraft, saveDraft } from '@/api/drafts'

const ROLE_OPTIONS: { value: AppRole; label: string; description: string }[] = [
  {
    value: 'athlete',
    label: 'Athlete',
    description: 'Track my own training, programs, and competitions.',
  },
  {
    value: 'coach',
    label: 'Coach',
    description: 'Support Athletes who grant you training access.',
  },
  {
    value: 'handler',
    label: 'Handler / support',
    description: 'Support Athletes on competition day with their permission.',
  },
]

const SEX_OPTIONS = [
  { value: 'male', label: 'Male' },
  { value: 'female', label: 'Female' },
]

const VISIBILITY_OPTIONS = [
  { value: 'private', label: 'Private (you and people you grant access)' },
  { value: 'public', label: 'Public (visible to everyone)' },
]

export default function OnboardingPage() {
  const navigate = useNavigate()
  const [search] = useSearchParams()
  const editing = search.get('edit') === '1'
  const { user, signOut } = useAuth()
  const [status, setStatus] = useState<OnboardingStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [active, setActive] = useState(0)

  const [roles, setRoles] = useState<AppRole[]>([])
  const [activeRole, setActiveRole] = useState<AppRole>('athlete')

  const [displayName, setDisplayName] = useState('')
  const [bio, setBio] = useState('')
  const [visibility, setVisibility] = useState<'private' | 'public'>('private')
  const [federations, setFederations] = useState<string[]>([])
  const [federationLibrary, setFederationLibrary] = useState<MasterFederation[]>([])
  const [federationCatalogError, setFederationCatalogError] = useState(false)

  const [sex, setSex] = useState<'male' | 'female' | ''>('')
  const [country, setCountry] = useState('')
  const [region, setRegion] = useState('')
  const [bodyweight, setBodyweight] = useState<number | string>('')
  const [squat, setSquat] = useState<number | string>('')
  const [bench, setBench] = useState<number | string>('')
  const [deadlift, setDeadlift] = useState<number | string>('')
  const [maxesDate, setMaxesDate] = useState(new Date().toLocaleDateString('en-CA'))
  const [estimated, setEstimated] = useState({ squat: false, bench: false, deadlift: false })
  const formDraft = { active, roles, activeRole, displayName, bio, visibility, federations, sex, country, region, bodyweight, squat, bench, deadlift, maxesDate, estimated }
  type FormDraft = typeof formDraft

  useEffect(() => {
    if (!loading && user) void saveDraft('onboarding-form', formDraft).catch(() => setError('Your browser could not preserve this form. Keep this page open.'))
  }, [loading, user, JSON.stringify(formDraft)])

  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const [s, settings, feds] = await Promise.all([
          getOnboardingStatus(),
          getSettings().catch(() => null),
          fetchFederations().catch(() => {
            setFederationCatalogError(true)
            return [] as MasterFederation[]
          }),
        ])
        if (cancelled) return
        setStatus(s)
        setFederationLibrary(feds)
        if (s.prefill?.bodyweight_kg) setBodyweight(s.prefill.bodyweight_kg)
        if (s.prefill?.training_maxes) {
          setSquat(s.prefill.training_maxes.squat_kg ?? '')
          setBench(s.prefill.training_maxes.bench_kg ?? '')
          setDeadlift(s.prefill.training_maxes.deadlift_kg ?? '')
        }
        if (settings) {
          if (settings.display_name) setDisplayName(settings.display_name)
          if (settings.bio) setBio(settings.bio)
          if (settings.profile_visibility) setVisibility(settings.profile_visibility)
          if (settings.federations?.length) setFederations(settings.federations)
          if (settings.sex) setSex(settings.sex)
          if (settings.bodyweight_kg) setBodyweight(settings.bodyweight_kg)
          if (settings.training_maxes) {
            setSquat(settings.training_maxes.squat_kg)
            setBench(settings.training_maxes.bench_kg)
            setDeadlift(settings.training_maxes.deadlift_kg)
          }
          if (settings.maxes_date) setMaxesDate(settings.maxes_date)
          if (settings.training_maxes_estimated) setEstimated(settings.training_maxes_estimated)
          if (settings.ranking_country) setCountry(settings.ranking_country)
          if (settings.ranking_region) setRegion(settings.ranking_region)
        }
        if (s.state.roles.length > 0) setRoles(s.state.roles)
        if (s.state.active_role) setActiveRole(s.state.active_role)
        setActive(onboardingStepFor(s.next_step, s.state.active_role || s.state.roles[0], editing, search.get('step') === 'basics'))
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load onboarding status')
        }
      } finally {
        const draft = await readDraft<FormDraft>('onboarding-form').catch(() => undefined)
        if (cancelled) return
        if (draft) {
          const value = draft.value
          setActive(value.active); setRoles(value.roles); setActiveRole(value.activeRole)
          setDisplayName(value.displayName); setBio(value.bio); setVisibility(value.visibility); setFederations(value.federations)
          setSex(value.sex); setCountry(value.country); setRegion(value.region); setBodyweight(value.bodyweight)
          setSquat(value.squat); setBench(value.bench); setDeadlift(value.deadlift); setMaxesDate(value.maxesDate)
        }
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => {
      cancelled = true
    }
  }, [])

  const showAthleteStep = activeRole === 'athlete'
  const athleteRequired = showAthleteStep
  const totalRequiredSteps = 2 + (athleteRequired ? 1 : 0)

  const completedCount = useMemo(() => {
    if (!status) return 0
    let c = 0
    if (status.state.roles.length > 0) c += 1
    if (status.state.profile_complete) c += 1
    if (showAthleteStep && status.has_athlete_basics) c += 1
    return c
  }, [status, showAthleteStep])

  const progressPct = totalRequiredSteps > 0 ? Math.round((completedCount / totalRequiredSteps) * 100) : 0

  function applySettings(s: UserSettings) {
    setStatus((prev) => {
      if (!prev) return prev
      return {
        ...prev,
        state: {
          ...prev.state,
          roles: s.roles,
          active_role: s.active_role,
        },
        has_athlete_basics: s.athlete_basics_complete || prev.has_athlete_basics,
      }
    })
  }

  async function handleRoleNext() {
    if (roles.length === 0) {
      setError('Pick at least one role to continue.')
      return
    }
    setSubmitting(true)
    setError(null)
    try {
      const next = await apiSetRole({ roles, active_role: activeRole })
      applySettings(next)
      setStatus((prev) =>
        prev
          ? {
              ...prev,
              state: { ...prev.state, roles: next.roles, active_role: next.active_role },
              next_step: 'profile',
            }
          : prev,
      )
      setActive(1)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save role')
    } finally {
      setSubmitting(false)
    }
  }

  async function handleProfileNext() {
    if (!displayName.trim()) {
      setError('Display name is required.')
      return
    }
    setSubmitting(true)
    setError(null)
    try {
      const next = await submitOnboardingProfile({
        display_name: displayName.trim(),
        bio: bio.trim(),
        profile_visibility: visibility,
        federations,
      })
      applySettings(next)
      const stillAthlete = (next.active_role ?? activeRole) === 'athlete'
      if (stillAthlete) {
        setStatus((prev) =>
          prev
            ? { ...prev, state: { ...prev.state, profile_complete: true }, next_step: 'athlete_basics' }
            : prev,
        )
        setActive(2)
      } else {
        setStatus((prev) =>
          prev
            ? { ...prev, state: { ...prev.state, profile_complete: true }, next_step: 'done', is_onboarded: true }
            : prev,
        )
        await removeDraft('onboarding-form')
        window.location.assign('/')
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save profile')
    } finally {
      setSubmitting(false)
    }
  }

  async function handleBasicsNext() {
    if (!sex) { setError('Select sex for competition calculations.'); return }
    if (!country.trim()) {
      setError('Country is required.')
      return
    }
    const bw = typeof bodyweight === 'string' ? parseFloat(bodyweight) : bodyweight
    const sq = typeof squat === 'string' ? parseFloat(squat) : squat
    const be = typeof bench === 'string' ? parseFloat(bench) : bench
    const dl = typeof deadlift === 'string' ? parseFloat(deadlift) : deadlift
    if (!Number.isFinite(bw) || bw <= 0) {
      setError('Bodyweight must be a positive number.')
      return
    }
    if (!Number.isFinite(sq) || !Number.isFinite(be) || !Number.isFinite(dl)) {
      setError('All training maxes are required.')
      return
    }
    setSubmitting(true)
    setError(null)
    try {
      const next = await submitAthleteBasics({
        sex,
        country: country.trim().toUpperCase(),
        region: region.trim() || null,
        bodyweight_kg: bw,
        training_maxes: { squat_kg: sq, bench_kg: be, deadlift_kg: dl },
        maxes_date: maxesDate,
        training_maxes_estimated: estimated,
      })
      applySettings(next)
      setStatus((prev) =>
        prev ? { ...prev, has_athlete_basics: true, next_step: 'done', is_onboarded: true } : prev,
      )
      await removeDraft('onboarding-form')
      window.location.assign('/')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save athlete basics')
    } finally {
      setSubmitting(false)
    }
  }

  if (loading) {
    return (
      <Center mih={400}>
        <Loader />
      </Center>
    )
  }

  if (!editing && (status?.is_onboarded || status?.next_step === 'done')) {
    return (
      <Center maw={640} mx="auto" mt="xl" px="md">
        <Paper p="xl" radius="md" shadow="sm" w="100%">
          <Stack align="center" gap="md">
            <Check size={48} color="var(--mantine-color-teal-6)" />
            <Title order={2}>You're onboarded</Title>
            <Text c="dimmed" ta="center">
              Your profile, role, and athlete basics are saved. You can update any of these later in Settings.
            </Text>
            <Group>
              <Button onClick={() => navigate('/')}>Go to dashboard</Button>
              <Button variant="default" onClick={() => navigate('/profile')}>
                View profile
              </Button>
            </Group>
          </Stack>
        </Paper>
      </Center>
    )
  }

  if (!user) {
    return (
      <Center maw={480} mx="auto" mt="xl" px="md">
        <Paper p="xl" radius="md" shadow="sm" w="100%">
          <Stack align="center" gap="md">
            <Text>Please sign in to complete onboarding.</Text>
            <Button onClick={() => navigate('/login')}>Sign in</Button>
          </Stack>
        </Paper>
      </Center>
    )
  }

  const stepLabels = ['Your role', 'Profile', ...(showAthleteStep ? ['Athlete basics'] : [])]
  const fedOptions = federationLibrary
    .filter((f) => f.status === 'active')
    .map((f) => ({
      value: f.pk,
      label: f.abbreviation ? `${f.name} (${f.abbreviation})` : f.name,
    }))

  return (
    <Center maw={720} mx="auto" mt="xl" px="md">
      <Paper p="xl" radius="md" shadow="sm" w="100%">
        <Stack gap="md">
          <Group justify="space-between" wrap="wrap" align="center">
            <Stack gap={2}>
              <Title order={2}>{editing ? 'Edit your profile and basics' : 'Welcome to NoLift Training'}</Title>
              <Text c="dimmed" size="sm">
                Tell us a bit about yourself so we can set up the right tools.
              </Text>
            </Stack>
            <Button variant="subtle" leftSection={<LogIn size={14} />} onClick={signOut} size="xs">
              Sign out
            </Button>
          </Group>

          <Stack gap={4}>
            <Group justify="space-between">
              <Text size="sm" c="dimmed">
                Onboarding progress
              </Text>
              <Text size="sm" c="dimmed">
                {completedCount}/{totalRequiredSteps}
              </Text>
            </Group>
            <Progress value={progressPct} size="sm" />
          </Stack>

          {error && (
            <Alert color="red" icon={<AlertCircle size={18} />}>
              {error}
            </Alert>
          )}

          <Stepper active={active} onStepClick={setActive} allowNextStepsSelect={false}>
            <Stepper.Step label="Role" description="Who you are" allowStepSelect={active > 0}>
              <RoleStep
                roles={roles}
                setRoles={setRoles}
                activeRole={activeRole}
                setActiveRole={setActiveRole}
                disabled={submitting}
              />
              <Group justify="space-between" mt="lg">
                <Button variant="subtle" onClick={() => navigate(-1)} leftSection={<ArrowLeft size={16} />}>
                  Back
                </Button>
                <Button
                  onClick={handleRoleNext}
                  loading={submitting}
                  rightSection={<ChevronRight size={16} />}
                >
                  Continue
                </Button>
              </Group>
            </Stepper.Step>

            <Stepper.Step label="Profile" description="How you appear" allowStepSelect={active > 1}>
              <ProfileStep
                displayName={displayName}
                setDisplayName={setDisplayName}
                bio={bio}
                setBio={setBio}
                visibility={visibility}
                setVisibility={setVisibility}
                federations={federations}
                setFederations={setFederations}
                federationOptions={fedOptions}
                federationCatalogError={federationCatalogError}
                disabled={submitting}
              />
              <Group justify="space-between" mt="lg">
                <Button
                  variant="subtle"
                  onClick={() => setActive(0)}
                  leftSection={<ChevronLeft size={16} />}
                >
                  Back
                </Button>
                <Button
                  onClick={handleProfileNext}
                  loading={submitting}
                  rightSection={<ChevronRight size={16} />}
                >
                  Continue
                </Button>
              </Group>
            </Stepper.Step>

            {showAthleteStep && (
              <Stepper.Step label="Athlete" description="Basics for athletes">
                <AthleteBasicsStep
                  sex={sex}
                  setSex={setSex}
                  country={country}
                  setCountry={setCountry}
                  region={region}
                  setRegion={setRegion}
                  bodyweight={bodyweight}
                  setBodyweight={setBodyweight}
                  squat={squat}
                  setSquat={setSquat}
                  bench={bench}
                  setBench={setBench}
                  deadlift={deadlift}
                  setDeadlift={setDeadlift}
                  disabled={submitting}
                />
                <TextInput type="date" label="1RM reference date" value={maxesDate} onChange={event => setMaxesDate(event.currentTarget.value)} max={new Date().toLocaleDateString('en-CA')} required mt="md" />
                <Group justify="space-between" mt="lg">
                  <Button
                    variant="subtle"
                    onClick={() => setActive(1)}
                    leftSection={<ChevronLeft size={16} />}
                  >
                    Back
                  </Button>
                  <Button
                    onClick={handleBasicsNext}
                    loading={submitting}
                    rightSection={<Save size={16} />}
                  >
                    Finish onboarding
                  </Button>
                </Group>
              </Stepper.Step>
            )}
          </Stepper>

          <Group gap="xs" mt="xs">
            {stepLabels.map((label, i) => (
              <Badge
                key={i}
                color={i <= active ? 'teal' : 'gray'}
                variant={i === active ? 'filled' : 'light'}
              >
                {label}
              </Badge>
            ))}
          </Group>
        </Stack>
      </Paper>
    </Center>
  )
}

function RoleStep(props: {
  roles: AppRole[]
  setRoles: (r: AppRole[]) => void
  activeRole: AppRole
  setActiveRole: (r: AppRole) => void
  disabled: boolean
}) {
  const { roles, setRoles, activeRole, setActiveRole, disabled } = props
  function toggle(role: AppRole) {
    if (disabled) return
    if (roles.includes(role)) {
      const next = roles.filter((r) => r !== role)
      setRoles(next)
      if (activeRole === role && next.length > 0) setActiveRole(next[0])
    } else {
      const next = [...roles, role]
      setRoles(next)
      setActiveRole(role)
    }
  }
  return (
    <Stack gap="md">
      <Text size="sm" c="dimmed">
        Pick at least one role. You can change this later in Settings.
      </Text>
      <Stack gap="sm">
        {ROLE_OPTIONS.map((opt) => {
          const checked = roles.includes(opt.value)
          const isActive = activeRole === opt.value
          return (
            <Paper
              key={opt.value}
              withBorder
              radius="sm"
              p="sm"
              style={{
                cursor: disabled ? 'not-allowed' : 'pointer',
                borderColor: isActive ? 'var(--mantine-color-teal-5)' : undefined,
                background: checked ? 'var(--mantine-color-teal-light)' : undefined,
              }}
              onClick={() => toggle(opt.value)}
              role="button"
              tabIndex={disabled ? -1 : 0}
              aria-pressed={checked}
              onKeyDown={event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); toggle(opt.value) } }}
            >
              <Group justify="space-between" align="flex-start" wrap="nowrap">
                <Stack gap={2}>
                  <Group gap="xs" align="center">
                    <Text fw={600}>{opt.label}</Text>
                    {isActive && <Badge size="xs" color="teal">active</Badge>}
                  </Group>
                  <Text size="sm" c="dimmed">{opt.description}</Text>
                </Stack>
                {checked && <Badge color="teal" size="sm">Added</Badge>}
              </Group>
            </Paper>
          )
        })}
      </Stack>
      {roles.length > 1 && (
        <Text size="xs" c="dimmed">
          You picked {roles.length} roles. The active role determines which tools show by
          default — switch any time.
        </Text>
      )}
    </Stack>
  )
}

function ProfileStep(props: {
  displayName: string
  setDisplayName: (v: string) => void
  bio: string
  setBio: (v: string) => void
  visibility: 'private' | 'public'
  setVisibility: (v: 'private' | 'public') => void
  federations: string[]
  setFederations: (v: string[]) => void
  federationOptions: { value: string; label: string }[]
  federationCatalogError: boolean
  disabled: boolean
}) {
  const {
    displayName,
    setDisplayName,
    bio,
    setBio,
    visibility,
    setVisibility,
    federations,
    setFederations,
    federationOptions,
    federationCatalogError,
    disabled,
  } = props
  return (
    <Stack gap="md">
      <TextInput
        label="Display name"
        description="Shown to other users. Up to 80 characters."
        placeholder="e.g. Squat McLifter"
        value={displayName}
        onChange={(e) => setDisplayName(e.currentTarget.value.slice(0, 80))}
        maxLength={80}
        required
        disabled={disabled}
      />
      <Textarea
        label="Short bio"
        description="Optional. Up to 280 characters."
        placeholder="One or two lines about your training."
        value={bio}
        onChange={(e) => setBio(e.currentTarget.value.slice(0, 280))}
        maxLength={280}
        autosize
        minRows={2}
        maxRows={4}
        disabled={disabled}
      />
      <Select
        label="Profile visibility"
        data={VISIBILITY_OPTIONS}
        value={visibility}
        onChange={(v) => setVisibility(v === 'public' ? 'public' : 'private')}
        allowDeselect={false}
        disabled={disabled}
      />
      <Text size="sm" c="dimmed">Training stays private until you select domains in Profile publication settings.</Text>
      <MultiSelect
        label="Federations you compete in"
        description="Used to pick your weight class — no matter where you compete."
        placeholder={
          federationOptions.length ? 'Pick one or more' : federationCatalogError ? 'Federation directory unavailable' : 'No active federations found'
        }
        data={federationOptions}
        value={federations}
        onChange={setFederations}
        searchable
        clearable
        disabled={disabled || federationCatalogError}
        maxValues={20}
      />
    </Stack>
  )
}

function AthleteBasicsStep(props: {
  sex: 'male' | 'female' | ''
  setSex: (v: 'male' | 'female' | '') => void
  country: string
  setCountry: (v: string) => void
  region: string
  setRegion: (v: string) => void
  bodyweight: number | string
  setBodyweight: (v: number | string) => void
  squat: number | string
  setSquat: (v: number | string) => void
  bench: number | string
  setBench: (v: number | string) => void
  deadlift: number | string
  setDeadlift: (v: number | string) => void
  disabled: boolean
}) {
  const [unit, setUnit] = useState<'kg' | 'lb'>('kg')
  const display = (value: number | string) => typeof value === 'number' ? toDisplayUnit(value, unit) : value
  const kilograms = (value: number | string) => value === '' ? '' : fromDisplayUnit(Number(value), unit)
  const {
    sex,
    setSex,
    country,
    setCountry,
    region,
    setRegion,
    bodyweight,
    setBodyweight,
    squat,
    setSquat,
    bench,
    setBench,
    deadlift,
    setDeadlift,
    disabled,
  } = props
  return (
    <Stack gap="md">
      <Text size="sm" c="dimmed">
        Used to calculate your relative strength scores (DOTS/Wilks) and pick weight
        classes for your federations.
      </Text>
      <Radio.Group
        label="Sex"
        value={sex}
        onChange={(v) => setSex(v === 'female' ? 'female' : 'male')}
      >
        <Group mt="xs">
          {SEX_OPTIONS.map((opt) => (
            <Radio key={opt.value} value={opt.value} label={opt.label} disabled={disabled} />
          ))}
        </Group>
      </Radio.Group>
      <Group grow align="flex-end">
        <TextInput
          label="Country (ISO-2)"
          description="e.g. US, GB, DE"
          placeholder="US"
          value={country}
          onChange={(e) => setCountry(e.currentTarget.value.toUpperCase().slice(0, 8))}
          required
          disabled={disabled}
        />
        <TextInput
          label="Region / state (optional)"
          placeholder="CA, Ontario, ..."
          value={region}
          onChange={(e) => setRegion(e.currentTarget.value.slice(0, 64))}
          disabled={disabled}
        />
      </Group>
      <Select label="Weight units" value={unit} data={[{ value: 'kg', label: 'Kilograms' }, { value: 'lb', label: 'Pounds' }]} onChange={value => setUnit(value === 'lb' ? 'lb' : 'kg')} allowDeselect={false} disabled={disabled} />
      <NumberInput
        label={`Bodyweight (${unit})`}
        description="Current bodyweight, used for weight-class lookup."
        value={display(bodyweight)}
        onChange={(v) => setBodyweight(kilograms(v))}
        min={toDisplayUnit(30, unit)}
        max={toDisplayUnit(300, unit)}
        decimalScale={1}
        step={0.1}
        required
        disabled={disabled}
      />
      <Text size="sm" fw={500} mt="sm">
        Best-known current 1RMs ({unit})
      </Text>
      <Text size="sm" c="dimmed">Enter the most you believe you can lift for one repetition today. Estimates are welcome; identify them below.</Text>
      <Group grow>
        <NumberInput
          label="Squat"
          value={display(squat)}
          onChange={(v) => setSquat(kilograms(v))}
          min={toDisplayUnit(20, unit)}
          max={toDisplayUnit(600, unit)}
          step={2.5}
          decimalScale={1}
          required
          disabled={disabled}
        />
        <NumberInput
          label="Bench"
          value={display(bench)}
          onChange={(v) => setBench(kilograms(v))}
          min={toDisplayUnit(20, unit)}
          max={toDisplayUnit(600, unit)}
          step={2.5}
          decimalScale={1}
          required
          disabled={disabled}
        />
        <NumberInput
          label="Deadlift"
          value={display(deadlift)}
          onChange={(v) => setDeadlift(kilograms(v))}
          min={toDisplayUnit(20, unit)}
          max={toDisplayUnit(600, unit)}
          step={2.5}
          decimalScale={1}
          required
          disabled={disabled}
        />
      </Group>
    </Stack>
  )
}
