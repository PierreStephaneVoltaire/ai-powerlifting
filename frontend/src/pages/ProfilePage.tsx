import { useEffect, useMemo, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import {
  Alert,
  Avatar,
  Box,
  Button,
  FileButton,
  Group,
  Loader,
  Paper,
  Progress,
  MultiSelect,
  Select,
  SimpleGrid,
  Stack,
  Text,
  Textarea,
  TextInput,
} from '@mantine/core'
import { AlertCircle, Calendar, Check, Film, Plus, Save, Upload, User, X } from 'lucide-react'
import ProfileTrainingView, { type ProfileTrainingTab } from '@/components/profile/ProfileTrainingView'
import {
  getSettings,
  isValidProfileAvatarType,
  MAX_PROFILE_AVATAR_SIZE,
  updateAgeClass,
  updateNickname,
  updateProfile,
  uploadProfileAvatar,
  type UserSettings,
} from '@/api/settings'
import { fetchCurrentProfile, fetchProfile, type PublicProfile } from '@/api/profiles'
import * as api from '@/api/client'
import { useAuth } from '@/auth/AuthProvider'
import { useProgramStore } from '@/store/programStore'
import { useSettingsStore } from '@/store/settingsStore'
import { useUiStore } from '@/store/uiStore'
import { calculateDotsFromLifts } from '@/utils/dots'
import { resolveAvatarUrl } from '@/utils/media'
import { toDisplayUnit } from '@/utils/units'
import VideoCard from '@/components/videos/VideoCard'
import VideoPlayerModal from '@/components/videos/VideoPlayerModal'
import { sortVideos, VIDEO_SORTS, type VideoSort } from '@/utils/videoSort'
import { useVideoModalFromUrl } from '@/utils/useVideoModalFromUrl'
import type { Session, VideoLibraryItem, MasterFederation } from '@powerlifting/types'
import { AGE_CATEGORY_OPTIONS, type AgeCategory } from '@powerlifting/types'

type LiftFilter = 'all' | 'squat' | 'bench' | 'deadlift' | 'other'

const LIFT_FILTERS: Array<{ value: LiftFilter; label: string }> = [
  { value: 'all', label: 'All' },
  { value: 'squat', label: 'Squat' },
  { value: 'bench', label: 'Bench' },
  { value: 'deadlift', label: 'Deadlift' },
  { value: 'other', label: 'Other' },
]

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean)
  if (!parts.length) return 'U'
  return parts.slice(0, 2).map((part) => part[0]?.toUpperCase()).join('')
}

function liftMatches(item: VideoLibraryItem, filter: LiftFilter): boolean {
  if (filter === 'all') return true
  if (filter === 'other') return !['squat', 'bench', 'deadlift'].some((lift) => (item.video.exercise_name || '').toLowerCase().includes(lift))
  return (item.video.exercise_name || '').toLowerCase().includes(filter)
}

function hasCompletedSet(exercise: Session['exercises'][number]): boolean {
  const setCount = Math.max(0, Math.round(Number(exercise.sets) || 0))

  if (exercise.set_statuses?.length) {
    for (let index = 0; index < setCount; index += 1) {
      const status = exercise.set_statuses[index]
      if (status === 'completed' || status === undefined) return true
    }
    return false
  }

  if (exercise.failed_sets?.length) {
    const legacySetCount = Math.max(setCount, exercise.failed_sets.length)
    for (let index = 0; index < legacySetCount; index += 1) {
      if (exercise.failed_sets[index] !== true) return true
    }
    return false
  }

  if (exercise.failed) return false
  return setCount > 0
}

function positiveNumber(value: number | null | undefined): number | null {
  return typeof value === 'number' && Number.isFinite(value) && value > 0 ? value : null
}

function bestSessionLift(sessions: Session[] | undefined, lift: Exclude<LiftFilter, 'all'>): number | null {
  let best = 0
  for (const session of sessions ?? []) {
    if (!session.completed || session.status === 'skipped') continue
    for (const exercise of session.exercises) {
      if (!exercise.kg || exercise.kg <= best) continue
      if (!hasCompletedSet(exercise)) continue
      if (exercise.name.toLowerCase().includes(lift)) best = exercise.kg
    }
  }
  return best > 0 ? best : null
}

function latestSessionBodyweight(sessions: Session[] | undefined): number | null {
  const dated = (sessions ?? [])
    .filter((session) => typeof session.body_weight_kg === 'number' && session.body_weight_kg > 0)
    .sort((a, b) => b.date.localeCompare(a.date))

  return dated[0]?.body_weight_kg ?? null
}

function metricTestId(label: string): string {
  return `profile-metric-${label.toLowerCase()}`
}

function federationSummary(federation: string | null | undefined, practicingFor: string | null | undefined, weightClass: number | string | null | undefined): string {
  const labels = String(federation || '').split('+').map((value) => value.trim()).filter(Boolean)
  const unique = [...new Set(labels)]
  if (practicingFor && !unique.some((value) => value.toLowerCase() === practicingFor.toLowerCase())) unique.push(practicingFor)
  return `${unique.join(' + ') || 'Federation unset'} - ${weightClass || '--'} kg`
}

type ProfileSection = 'profile' | ProfileTrainingTab

const PROFILE_SECTIONS: { value: ProfileSection; label: string }[] = [
  { value: 'profile', label: 'Profile' },
  { value: 'sessions', label: 'Sessions' },
  { value: 'analysis', label: 'Analysis' },
]

export default function ProfilePage() {
  const { nickname: targetNickname } = useParams<{ nickname?: string }>()
  const { user, loading: authLoading, readOnly } = useAuth('settings')
  const [searchParams, setSearchParams] = useSearchParams()
  const { program, version } = useProgramStore()
  const { unit, sex } = useSettingsStore()
  const { pushToast } = useUiStore()
  const [settings, setSettings] = useState<UserSettings | null>(null)
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [nickname, setNickname] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [bio, setBio] = useState('')
  const [publicProfile, setPublicProfile] = useState<PublicProfile | null>(null)
  const [publicProfileLoading, setPublicProfileLoading] = useState(false)
  const [videos, setVideos] = useState<VideoLibraryItem[]>([])
  const [videosLoading, setVideosLoading] = useState(false)
  const [videoFilter, setVideoFilter] = useState<LiftFilter>('all')
  const [videoSort, setVideoSort] = useState<VideoSort>('newest')
  const [avatarUploading, setAvatarUploading] = useState(false)
  const [avatarProgress, setAvatarProgress] = useState(0)
  const [ageClass, setAgeClass] = useState<AgeCategory>('open')
  const [mainFederation, setMainFederation] = useState('')
  const [weightClasses, setWeightClasses] = useState<string[]>([])
  const [federations, setFederations] = useState<MasterFederation[]>([])
  const [otherExercise, setOtherExercise] = useState<string | null>(null)
  const viewingOther = Boolean(targetNickname)

  // The page renders one of two video grids (own-videos when signed in,
  // public-videos when reading someone else's profile). Both grids feed
  // the same VideoPlayerModal, so the URL hook reads from whichever
  // source is currently active.
  const effectiveVideos = user && !viewingOther ? videos : (publicProfile?.lift_videos ?? [])
  const effectiveVideosReady = user && !viewingOther
    ? !videosLoading
    : !publicProfileLoading && !!publicProfile
  const { selectedVideo, openVideo, closeVideo } = useVideoModalFromUrl(
    effectiveVideos,
    effectiveVideosReady,
  )

  useEffect(() => {
    if (authLoading || !user || viewingOther) return

    let cancelled = false
    setLoading(true)
    setError(null)
    getSettings()
      .then((nextSettings) => {
        if (cancelled) return
        setSettings(nextSettings)
        setNickname(nextSettings.nickname)
        setDisplayName(nextSettings.display_name)
        setBio(nextSettings.bio)
        setAgeClass(nextSettings.age_class)
      })
      .catch(() => {
        if (!cancelled) setError('Profile settings are unavailable for this account.')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [authLoading, user, viewingOther])

  useEffect(() => {
    if (authLoading || (user && !viewingOther)) return

    let cancelled = false
    setPublicProfileLoading(true)
    setPublicProfile(null)
    setError(null)
    const profileRequest = viewingOther && targetNickname ? fetchProfile(targetNickname) : fetchCurrentProfile()
    profileRequest
      .then((profile) => {
        if (!cancelled) setPublicProfile(profile)
      })
      .catch(() => {
        if (!cancelled) setPublicProfile(null)
      })
      .finally(() => {
        if (!cancelled) setPublicProfileLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [authLoading, user, targetNickname, viewingOther])

  useEffect(() => {
    if (!program || viewingOther) return
    setMainFederation(program.meta.federation || '')
    setWeightClasses((program.meta.weight_classes_kg ?? (program.meta.weight_class_kg ? [program.meta.weight_class_kg] : [])).map(String).slice(0, 2))
    api.fetchFederations().then(setFederations).catch(() => setFederations([]))
  }, [program, viewingOther])

  const loadVideos = async () => {
    setVideosLoading(true)
    try {
      const result = await api.getVideos(version)
      setVideos(result.videos)
    } catch {
      pushToast({ message: 'Video library failed to load', type: 'error' })
    } finally {
      setVideosLoading(false)
    }
  }

  useEffect(() => {
    if (!user || viewingOther) return
    loadVideos()
    // Reload when the active program version changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user, version, viewingOther])

  const profileMetrics = useMemo(() => {
    const meta = program?.meta
    const current = program?.current_maxes
    const sessions = program?.sessions
    const squat = positiveNumber(current?.squat) ?? positiveNumber(meta?.manual_maxes?.squat) ?? bestSessionLift(sessions, 'squat') ?? positiveNumber(meta?.target_squat_kg) ?? 0
    const bench = positiveNumber(current?.bench) ?? positiveNumber(meta?.manual_maxes?.bench) ?? bestSessionLift(sessions, 'bench') ?? positiveNumber(meta?.target_bench_kg) ?? 0
    const deadlift = positiveNumber(current?.deadlift) ?? positiveNumber(meta?.manual_maxes?.deadlift) ?? bestSessionLift(sessions, 'deadlift') ?? positiveNumber(meta?.target_dl_kg) ?? 0
    const total = squat + bench + deadlift
    const bodyweight = positiveNumber(meta?.current_body_weight_kg) ?? latestSessionBodyweight(sessions) ?? positiveNumber(meta?.last_comp?.body_weight_kg) ?? 0
    const scoreSex = meta?.sex ?? sex
    const dots = scoreSex && total > 0 && bodyweight > 0
      ? calculateDotsFromLifts(squat, bench, deadlift, bodyweight, scoreSex).dots
      : null

    const weightValue = (kg: number | null | undefined) => {
      const n = Number(kg)
      if (!Number.isFinite(n) || n <= 0) return '--'
      const display = toDisplayUnit(n, unit)
      const num = Number(display)
      if (!Number.isFinite(num)) return '--'
      return Number.isInteger(num) ? String(num) : num.toFixed(1)
    }

    return [
      { label: 'Squat', value: weightValue(squat), sub: unit },
      { label: 'Bench', value: weightValue(bench), sub: unit },
      { label: 'Deadlift', value: weightValue(deadlift), sub: unit },
      { label: 'Total', value: weightValue(total), sub: unit },
      { label: 'DOTS', value: dots !== null && dots !== undefined && Number.isFinite(Number(dots)) ? Number(dots).toFixed(1) : '--', sub: 'pts' },
      { label: 'Class', value: meta?.weight_class_kg ? String(meta.weight_class_kg) : '--', sub: 'kg' },
    ]
  }, [program, sex, unit])

  const filteredVideos = useMemo(
    () => sortVideos(
      videos.filter((item) => liftMatches(item, videoFilter) && (videoFilter !== 'other' || !otherExercise || item.video.exercise_name === otherExercise)),
      videoSort,
    ),
    [videoFilter, videos, videoSort, otherExercise],
  )

  const otherExerciseOptions = useMemo(() => [...new Set(effectiveVideos.map((item) => item.video.exercise_name || '').filter((name) => name && !['squat', 'bench', 'deadlift'].some((lift) => name.toLowerCase().includes(lift))))].map((name) => ({ value: name, label: name })), [effectiveVideos])

  const publicProfileMetrics = useMemo(() => {
    const summary = publicProfile?.summary
    const weightValue = (kg: number | string | null | undefined) => {
      const n = Number(kg)
      if (!Number.isFinite(n) || n <= 0) return '--'
      const display = toDisplayUnit(n, unit)
      const num = Number(display)
      if (!Number.isFinite(num)) return '--'
      return Number.isInteger(num) ? String(num) : num.toFixed(1)
    }

    return [
      { label: 'Squat', value: weightValue(summary?.squat_kg), sub: unit },
      { label: 'Bench', value: weightValue(summary?.bench_kg), sub: unit },
      { label: 'Deadlift', value: weightValue(summary?.deadlift_kg), sub: unit },
      { label: 'Total', value: weightValue(summary?.total_kg), sub: unit },
      { label: 'DOTS', value: summary?.dots !== null && summary?.dots !== undefined && Number.isFinite(Number(summary.dots)) ? Number(summary.dots).toFixed(1) : '--', sub: 'pts' },
      { label: 'Class', value: publicProfile?.weight_class_kg ? String(publicProfile.weight_class_kg) : '--', sub: 'kg' },
    ]
  }, [publicProfile, unit])

  const readonlyFilteredVideos = useMemo(
    () => sortVideos(
      (publicProfile?.lift_videos ?? []).filter((item) => liftMatches(item, videoFilter) && (videoFilter !== 'other' || !otherExercise || item.video.exercise_name === otherExercise)),
      videoSort,
    ),
    [publicProfile?.lift_videos, videoFilter, videoSort, otherExercise],
  )

  async function handleAvatarUpload(file: File | null) {
    if (!file || avatarUploading) return
    if (!isValidProfileAvatarType(file)) {
      pushToast({ message: 'Profile picture must be JPG, PNG, WebP, or GIF', type: 'error' })
      return
    }
    if (file.size > MAX_PROFILE_AVATAR_SIZE) {
      pushToast({ message: 'Profile picture must be 8 MB or smaller', type: 'error' })
      return
    }

    setAvatarUploading(true)
    setAvatarProgress(0)
    setError(null)
    try {
      const nextSettings = await uploadProfileAvatar(file, setAvatarProgress)
      setSettings(nextSettings)
      pushToast({ message: 'Profile picture updated', type: 'success' })
    } catch {
      setError('Profile picture upload failed.')
      pushToast({ message: 'Profile picture upload failed', type: 'error' })
    } finally {
      setAvatarUploading(false)
      setAvatarProgress(0)
    }
  }

  async function saveProfile() {
    if (!settings || saving) return
    setSaving(true)
    setError(null)
    try {
      let nextSettings = settings
      const nextNickname = nickname.trim()
      if (nextNickname && nextNickname !== settings.nickname) {
        nextSettings = await updateNickname(nextNickname)
      }

      nextSettings = await updateProfile({
        profile_visibility: settings.profile_visibility,
        display_name: displayName,
        bio,
      })

      if (ageClass !== nextSettings.age_class) {
        nextSettings = await updateAgeClass({ age_class: ageClass })
      }

      if (program) {
        const selectedWeightClasses = weightClasses.map(Number).filter((value) => Number.isFinite(value)).slice(0, 2)
        await api.updateMetaFields(version, {
          federation: mainFederation.trim(),
          weight_class_kg: selectedWeightClasses[0] ?? null,
          weight_classes_kg: selectedWeightClasses,
        }, api.mutationEnvelope(program.meta.revision ?? 0))
        await useProgramStore.getState().loadProgram(version)
      }

      setSettings(nextSettings)
      setNickname(nextSettings.nickname)
      setDisplayName(nextSettings.display_name)
      setBio(nextSettings.bio)
      setAgeClass(nextSettings.age_class)
      pushToast({ message: 'Profile updated', type: 'success' })
    } catch {
      setError('Profile update failed.')
      pushToast({ message: 'Profile update failed', type: 'error' })
    } finally {
      setSaving(false)
    }
  }

  if (authLoading) {
    return <Text c="dimmed">Loading profile...</Text>
  }

  const readOnlyView = !user || viewingOther
  const requestedSection = searchParams.get('section')
  const profileSection: ProfileSection = requestedSection === 'sessions' || requestedSection === 'analysis' ? requestedSection : 'profile'
  const sectionAvailable = (section: ProfileSection) =>
    section === 'profile' || (section === 'sessions' ? publicProfile?.sessions_public === true : publicProfile?.sessions_public === true && publicProfile.public_training_summary_enabled)
  const selectSection = (section: ProfileSection) => {
    const next = new URLSearchParams(searchParams)
    if (section === 'profile') next.delete('section')
    else next.set('section', section)
    setSearchParams(next, { replace: true })
  }

  if (readOnlyView && publicProfileLoading) {
    return (
      <Group justify="center" py="xl" data-testid="profile-page">
        <Loader size="sm" />
      </Group>
    )
  }

  if (readOnlyView && !publicProfile) {
    return (
      <Stack gap="lg" data-testid="profile-page">
        <Group gap="xs">
          <User size={24} />
          <Text component="h1" className="if-page-title">Profile</Text>
        </Group>
        <Paper withBorder p="lg" radius="md" className="if-card">
          <Stack gap="md">
            <Text c="dimmed">This profile is private or unavailable.</Text>
          </Stack>
        </Paper>
      </Stack>
    )
  }

  const locked = readOnlyView || readOnly || loading || !settings
  const view = readOnlyView && publicProfile
    ? {
        name: publicProfile.display_name,
        avatar: resolveAvatarUrl(publicProfile.avatar_url),
        nickname: publicProfile.nickname,
        displayName: publicProfile.display_name,
        bio: publicProfile.bio,
        visibility: publicProfile.profile_visibility,
        federation: publicProfile.federation || '',
        weightClasses: publicProfile.weight_class_kg ? [String(publicProfile.weight_class_kg)] : [],
        summary: federationSummary(publicProfile.federation, publicProfile.practicing_for, publicProfile.weight_class_kg),
        metrics: publicProfileMetrics,
        videos: publicProfile.lift_videos ?? [],
        shownVideos: readonlyFilteredVideos,
      }
    : {
        name: displayName || settings?.display_name || user!.username,
        avatar: resolveAvatarUrl(settings?.avatar_url) || user!.avatar,
        nickname,
        displayName,
        bio,
        visibility: settings?.profile_visibility || 'private',
        federation: mainFederation,
        weightClasses,
        summary: federationSummary(mainFederation || program?.meta.federation, program?.meta.practicing_for, weightClasses[0] || program?.meta.weight_class_kg),
        metrics: profileMetrics,
        videos,
        shownVideos: filteredVideos,
      }
  const federationOptions = federations.length
    ? federations.map((federation) => ({ value: federation.abbreviation || federation.name, label: federation.abbreviation ? `${federation.abbreviation} — ${federation.name}` : federation.name }))
    : view.federation ? [{ value: view.federation, label: view.federation }] : []

  return (
    <Stack gap="md" data-testid="profile-page">
      <div className="if-page-header">
        <Stack gap={2}>
          <Text component="h1" className="if-page-title">Profile</Text>
        </Stack>
        {readOnlyView && publicProfile && (
          <div className="if-tab-group" role="tablist" aria-label="Profile sections" data-testid="profile-sections">
            {PROFILE_SECTIONS.map((section) => (
              <button
                key={section.value}
                type="button"
                role="tab"
                className="if-tab-button"
                aria-selected={profileSection === section.value}
                data-active={profileSection === section.value}
                disabled={section.value !== 'profile' && !sectionAvailable(section.value)}
                onClick={() => selectSection(section.value)}
                data-testid={`profile-section-${section.value}`}
              >
                {section.label}
              </button>
            ))}
          </div>
        )}
        {!readOnlyView && (
          <Button
            leftSection={<Save size={16} />}
            onClick={saveProfile}
            loading={saving}
            disabled={locked}
            data-testid="profile-save"
          >
            Save Profile
          </Button>
        )}
      </div>

      {error && (
        <Alert color="red" title="Profile unavailable" icon={<AlertCircle size={16} />}>
          {error}
        </Alert>
      )}

      {readOnlyView && publicProfile && profileSection !== 'profile' && sectionAvailable(profileSection) ? (
        <ProfileTrainingView athlete={publicProfile.athlete_pk} tab={profileSection} analysisAvailable={publicProfile.public_training_summary_enabled} />
      ) : (
      <>
      <Paper withBorder p="lg" radius="md" className="if-card">
        <Stack gap="md">
          <Group justify="space-between" align="flex-start" wrap="nowrap">
            <Group gap="md" align="flex-start" wrap="nowrap" style={{ minWidth: 0 }}>
              <Stack gap={6} align="center" style={{ flexShrink: 0 }}>
                <Avatar src={view.avatar} alt={view.name} radius="xl" size={60}>
                  {initials(view.name)}
                </Avatar>
                {!readOnlyView && (
                  <FileButton
                    onChange={handleAvatarUpload}
                    accept="image/jpeg,image/png,image/webp,image/gif"
                    disabled={locked || avatarUploading}
                  >
                    {(props) => (
                      <Button
                        {...props}
                        size="xs"
                        variant="light"
                        leftSection={<Upload size={14} />}
                        loading={avatarUploading}
                        disabled={locked}
                        data-testid="profile-avatar-upload"
                      >
                        Photo
                      </Button>
                    )}
                  </FileButton>
                )}
                {avatarUploading && <Progress value={avatarProgress} size="xs" w={72} />}
              </Stack>
              <Stack gap={8} style={{ minWidth: 0 }}>
                <Group gap="xs" wrap="wrap">
                  <Text fw={600} size="lg" c="var(--text-primary)" truncate>
                    {view.name}
                  </Text>
                  <Text size="sm" c="var(--text-secondary)">
                    @{view.nickname}
                  </Text>
                  {!readOnlyView && <span className="if-pill if-pill-success">Discord connected</span>}
                  <span className={`if-pill ${view.visibility === 'public' ? 'if-pill-info' : 'if-pill-neutral'}`}>
                    {view.visibility}
                  </span>
                  {readOnlyView && <span className="if-pill if-pill-neutral">Read only</span>}
                </Group>
                <Text size="sm" c="var(--text-secondary)">
                  {view.summary}
                </Text>
              </Stack>
            </Group>
          </Group>

          <SimpleGrid cols={{ base: 1, md: 2 }} spacing="md">
            <TextInput
              label="Nickname"
              value={view.nickname}
              onChange={(event) => setNickname(event.currentTarget.value)}
              disabled={locked}
              maxLength={32}
              data-testid="profile-nickname"
            />
            <TextInput
              label="Display name"
              value={view.displayName}
              onChange={(event) => setDisplayName(event.currentTarget.value)}
              disabled={locked}
              maxLength={80}
              data-testid="profile-display-name"
            />
          </SimpleGrid>

          <Textarea
            label="Bio"
            value={view.bio}
            onChange={(event) => setBio(event.currentTarget.value)}
            disabled={locked}
            maxLength={280}
            minRows={3}
            data-testid="profile-bio"
          />

          {!readOnlyView && (
            <Select
              label="Age Class (IPF)"
              description="Used for qualifying standards. Defaults to Open."
              data={AGE_CATEGORY_OPTIONS.map((o) => ({ value: o.value, label: o.label }))}
              value={ageClass}
              onChange={(v) => v && setAgeClass(v as AgeCategory)}
              disabled={locked}
              data-testid="profile-age-class"
            />
          )}

          <Select
            label="Main federation"
            data={federationOptions}
            value={view.federation || null}
            onChange={(value) => setMainFederation(value || '')}
            searchable
            clearable={!readOnlyView}
            disabled={locked}
            data-testid="profile-main-federation"
          />

          <MultiSelect
            label="Weight classes"
            description={readOnlyView ? undefined : 'Choose up to two classes.'}
            data={[...new Set(['47', '52', '57', '59', '63', '66', '69', '74', '76', '83', '84', '93', '105', '120', '125', ...view.weightClasses])].map((value) => ({ value, label: `${value} kg` }))}
            value={view.weightClasses}
            onChange={(values) => setWeightClasses(values.slice(0, 2))}
            maxValues={2}
            disabled={locked}
            data-testid="profile-weight-classes"
          />
        </Stack>
      </Paper>

      <SimpleGrid cols={{ base: 2, xs: 3, md: 6 }} spacing="xs">
        {view.metrics.map((metric) => (
          <Paper key={metric.label} className="if-metric-card" p="sm" ta="center" data-testid={metricTestId(metric.label)}>
            <Text className="if-metric-label">{metric.label}</Text>
            <Text className="if-metric-value" data-testid={`${metricTestId(metric.label)}-value`}>{metric.value}</Text>
            <Text size="xs" c="var(--text-secondary)">{metric.sub}</Text>
          </Paper>
        ))}
      </SimpleGrid>

      <Paper withBorder p="lg" radius="md" className="if-card">
        <Stack gap="md">
          <div className="if-panel-header">
            <Group gap="xs">
              <Film size={18} />
              <Text fw={600} c="var(--text-primary)">Lift videos</Text>
              <Text size="sm" c="var(--text-secondary)">
                {view.videos.length} video{view.videos.length === 1 ? '' : 's'}
              </Text>
            </Group>
            <Group gap="xs" wrap="wrap">
              <div className="if-tab-group" role="group" aria-label="Filter videos by lift" data-testid="profile-video-filter">
                {LIFT_FILTERS.map((filter) => (
                  <button
                    key={filter.value}
                    type="button"
                    className="if-tab-button"
                    data-active={videoFilter === filter.value}
                    onClick={() => setVideoFilter(filter.value)}
                  >
                    {filter.label}
                  </button>
                ))}
              </div>
              {videoFilter === 'other' && <Select placeholder="Exercise" data={otherExerciseOptions} value={otherExercise} onChange={setOtherExercise} searchable clearable />}
              <div className="if-tab-group" role="group" aria-label="Sort videos" data-testid="profile-video-sort">
                {VIDEO_SORTS.map((sort) => (
                  <button
                    key={sort.value}
                    type="button"
                    className="if-tab-button"
                    data-active={videoSort === sort.value}
                    onClick={() => setVideoSort(sort.value)}
                  >
                    {sort.label}
                  </button>
                ))}
              </div>
              {!readOnlyView && (
                <Button
                  component={Link}
                  to="/sessions"
                  size="xs"
                  variant="default"
                  leftSection={<Upload size={14} />}
                >
                  Upload
                </Button>
              )}
            </Group>
          </div>

          {!readOnlyView && videosLoading ? (
            <Group justify="center" py="xl">
              <Loader size="sm" />
            </Group>
          ) : view.shownVideos.length > 0 ? (
            <div className="if-video-grid">
              {view.shownVideos.map((item) => (
                <VideoCard
                  key={item.video.video_id}
                  item={item}
                  onClick={() => openVideo(item.video.video_id)}
                />
              ))}
            </div>
          ) : (
            <Paper className="if-metric-card" p="lg">
              <Stack align="center" gap="xs">
                <Calendar size={28} color="var(--text-muted)" />
                <Text size="sm" c="var(--text-secondary)" ta="center">
                  {readOnlyView ? 'No public lift videos match this filter.' : 'No lift videos match this filter. Upload videos from a session.'}
                </Text>
              </Stack>
            </Paper>
          )}
        </Stack>
      </Paper>

      <VideoPlayerModal
        item={selectedVideo}
        onClose={closeVideo}
        onDeleted={readOnlyView ? () => undefined : loadVideos}
        readOnly={readOnlyView || readOnly}
      />
      </>
      )}
    </Stack>
  )
}
