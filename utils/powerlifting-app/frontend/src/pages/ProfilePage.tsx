import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
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
  SegmentedControl,
  SimpleGrid,
  Stack,
  Text,
  Textarea,
  TextInput,
} from '@mantine/core'
import { AlertCircle, Calendar, Film, LogIn, Save, Upload, User } from 'lucide-react'
import {
  getSettings,
  isValidProfileAvatarType,
  MAX_PROFILE_AVATAR_SIZE,
  updateNickname,
  updateProfile,
  uploadProfileAvatar,
  type UserSettings,
} from '@/api/settings'
import { fetchCurrentProfile, type PublicProfile } from '@/api/profiles'
import * as api from '@/api/client'
import { useAuth } from '@/auth/AuthProvider'
import { useProgramStore } from '@/store/programStore'
import { useSettingsStore } from '@/store/settingsStore'
import { useUiStore } from '@/store/uiStore'
import { calculateDotsFromLifts } from '@/utils/dots'
import { toDisplayUnit } from '@/utils/units'
import VideoCard from '@/components/videos/VideoCard'
import VideoPlayerModal from '@/components/videos/VideoPlayerModal'
import type { Session, VideoLibraryItem } from '@powerlifting/types'

type ProfileVisibility = UserSettings['profile_visibility']
type LiftFilter = 'all' | 'squat' | 'bench' | 'deadlift'

const LIFT_FILTERS: Array<{ value: LiftFilter; label: string }> = [
  { value: 'all', label: 'All' },
  { value: 'squat', label: 'Squat' },
  { value: 'bench', label: 'Bench' },
  { value: 'deadlift', label: 'Deadlift' },
]

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean)
  if (!parts.length) return 'U'
  return parts.slice(0, 2).map((part) => part[0]?.toUpperCase()).join('')
}

function liftMatches(item: VideoLibraryItem, filter: LiftFilter): boolean {
  if (filter === 'all') return true
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

export default function ProfilePage() {
  const { user, loading: authLoading, readOnly, signIn } = useAuth()
  const { program, version } = useProgramStore()
  const { unit, sex } = useSettingsStore()
  const { pushToast } = useUiStore()
  const [settings, setSettings] = useState<UserSettings | null>(null)
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [nickname, setNickname] = useState('')
  const [profileVisibility, setProfileVisibility] = useState<ProfileVisibility>('private')
  const [displayName, setDisplayName] = useState('')
  const [bio, setBio] = useState('')
  const [publicProfile, setPublicProfile] = useState<PublicProfile | null>(null)
  const [publicProfileLoading, setPublicProfileLoading] = useState(false)
  const [videos, setVideos] = useState<VideoLibraryItem[]>([])
  const [videosLoading, setVideosLoading] = useState(false)
  const [videoFilter, setVideoFilter] = useState<LiftFilter>('all')
  const [selectedVideo, setSelectedVideo] = useState<VideoLibraryItem | null>(null)
  const [avatarUploading, setAvatarUploading] = useState(false)
  const [avatarProgress, setAvatarProgress] = useState(0)

  useEffect(() => {
    if (authLoading || !user) return

    let cancelled = false
    setLoading(true)
    setError(null)
    getSettings()
      .then((nextSettings) => {
        if (cancelled) return
        setSettings(nextSettings)
        setNickname(nextSettings.nickname)
        setProfileVisibility(nextSettings.profile_visibility)
        setDisplayName(nextSettings.display_name)
        setBio(nextSettings.bio)
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
  }, [authLoading, user])

  useEffect(() => {
    if (authLoading || user) return

    let cancelled = false
    setPublicProfileLoading(true)
    setPublicProfile(null)
    setError(null)
    fetchCurrentProfile()
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
  }, [authLoading, user])

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
    if (!user) return
    loadVideos()
    // Reload when the active program version changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user, version])

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

    const weightValue = (kg: number) => {
      if (kg <= 0) return '--'
      const display = toDisplayUnit(kg, unit)
      return Number.isInteger(display) ? String(display) : display.toFixed(1)
    }

    return [
      { label: 'Squat', value: weightValue(squat), sub: unit },
      { label: 'Bench', value: weightValue(bench), sub: unit },
      { label: 'Deadlift', value: weightValue(deadlift), sub: unit },
      { label: 'Total', value: weightValue(total), sub: unit },
      { label: 'DOTS', value: dots !== null ? dots.toFixed(1) : '--', sub: 'pts' },
      { label: 'Class', value: meta?.weight_class_kg ? String(meta.weight_class_kg) : '--', sub: 'kg' },
    ]
  }, [program, sex, unit])

  const filteredVideos = useMemo(
    () => videos
      .filter((item) => liftMatches(item, videoFilter))
      .sort((a, b) => (
        b.session_date.localeCompare(a.session_date)
        || b.video.uploaded_at.localeCompare(a.video.uploaded_at)
      )),
    [videoFilter, videos],
  )

  const publicProfileMetrics = useMemo(() => {
    const summary = publicProfile?.summary
    const weightValue = (kg: number | null | undefined) => {
      if (!kg || kg <= 0) return '--'
      const display = toDisplayUnit(kg, unit)
      return Number.isInteger(display) ? String(display) : display.toFixed(1)
    }

    return [
      { label: 'Squat', value: weightValue(summary?.squat_kg), sub: unit },
      { label: 'Bench', value: weightValue(summary?.bench_kg), sub: unit },
      { label: 'Deadlift', value: weightValue(summary?.deadlift_kg), sub: unit },
      { label: 'Total', value: weightValue(summary?.total_kg), sub: unit },
      { label: 'DOTS', value: summary?.dots !== null && summary?.dots !== undefined ? summary.dots.toFixed(1) : '--', sub: 'pts' },
      { label: 'Class', value: publicProfile?.weight_class_kg ? String(publicProfile.weight_class_kg) : '--', sub: 'kg' },
    ]
  }, [publicProfile, unit])

  const readonlyFilteredVideos = useMemo(
    () => (publicProfile?.lift_videos ?? [])
      .filter((item) => liftMatches(item, videoFilter))
      .sort((a, b) => (
        b.session_date.localeCompare(a.session_date)
        || b.video.uploaded_at.localeCompare(a.video.uploaded_at)
      )),
    [publicProfile?.lift_videos, videoFilter],
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
        profile_visibility: profileVisibility,
        display_name: displayName,
        bio,
      })

      setSettings(nextSettings)
      setNickname(nextSettings.nickname)
      setProfileVisibility(nextSettings.profile_visibility)
      setDisplayName(nextSettings.display_name)
      setBio(nextSettings.bio)
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

  if (!user) {
    if (publicProfileLoading) {
      return (
        <Group justify="center" py="xl" data-testid="profile-page">
          <Loader size="sm" />
        </Group>
      )
    }

    if (publicProfile) {
      return (
        <Stack gap="md" data-testid="profile-page">
          <div className="if-page-header">
            <Stack gap={2}>
              <Text component="h1" className="if-page-title">Profile</Text>
              <Text className="if-page-subtitle">Read-only public profile and lift gallery.</Text>
            </Stack>
            <Button leftSection={<LogIn size={16} />} onClick={signIn} variant="light">
              Sign in with Discord
            </Button>
          </div>

          <Paper withBorder p="lg" radius="md" className="if-card">
            <Stack gap="md">
              <Group gap="md" align="flex-start" wrap="nowrap" style={{ minWidth: 0 }}>
                <Avatar src={publicProfile.avatar_url} alt={publicProfile.display_name} radius="xl" size={60}>
                  {initials(publicProfile.display_name)}
                </Avatar>
                <Stack gap={8} style={{ minWidth: 0 }}>
                  <Group gap="xs" wrap="wrap">
                    <Text fw={600} size="lg" c="var(--text-primary)" truncate>
                      {publicProfile.display_name}
                    </Text>
                    <Text size="sm" c="var(--text-secondary)">
                      @{publicProfile.nickname}
                    </Text>
                    <span className="if-pill if-pill-info">Public profile</span>
                    <span className="if-pill if-pill-neutral">Read only</span>
                  </Group>
                  <Text size="sm" c="var(--text-secondary)">
                    {publicProfile.federation || 'Federation unset'} - {publicProfile.weight_class_kg || '--'} kg
                    {publicProfile.practicing_for ? ` - ${publicProfile.practicing_for}` : ''}
                  </Text>
                  {publicProfile.bio && (
                    <Text size="sm" c="var(--text-primary)" lh={1.6}>
                      {publicProfile.bio}
                    </Text>
                  )}
                </Stack>
              </Group>
            </Stack>
          </Paper>

          <SimpleGrid cols={{ base: 2, xs: 3, md: 6 }} spacing="xs">
            {publicProfileMetrics.map((metric) => (
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
                    {(publicProfile.lift_videos ?? []).length} video{(publicProfile.lift_videos ?? []).length === 1 ? '' : 's'}
                  </Text>
                </Group>
                <div className="if-tab-group">
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
              </div>

              {readonlyFilteredVideos.length > 0 ? (
                <div className="if-video-grid">
                  {readonlyFilteredVideos.map((item) => (
                    <VideoCard key={item.video.video_id} item={item} onClick={() => setSelectedVideo(item)} />
                  ))}
                </div>
              ) : (
                <Paper className="if-metric-card" p="lg">
                  <Stack align="center" gap="xs">
                    <Calendar size={28} color="var(--text-muted)" />
                    <Text size="sm" c="var(--text-secondary)" ta="center">
                      No public lift videos match this filter.
                    </Text>
                  </Stack>
                </Paper>
              )}
            </Stack>
          </Paper>

          <VideoPlayerModal
            item={selectedVideo}
            onClose={() => setSelectedVideo(null)}
            onDeleted={() => undefined}
            readOnly
          />
        </Stack>
      )
    }

    return (
      <Stack gap="lg" data-testid="profile-page">
        <Group gap="xs">
          <User size={24} />
          <Text component="h1" className="if-page-title">Profile</Text>
        </Group>
        <Paper withBorder p="lg" radius="md" className="if-card">
          <Stack gap="md">
            <Text c="dimmed">This profile is private or unavailable. Sign in to manage your profile.</Text>
            <Button leftSection={<LogIn size={16} />} onClick={signIn} w="fit-content">
              Sign in with Discord
            </Button>
          </Stack>
        </Paper>
      </Stack>
    )
  }

  const resolvedName = displayName || settings?.display_name || user.username

  return (
    <Stack gap="md" data-testid="profile-page">
      <div className="if-page-header">
        <Stack gap={2}>
          <Text component="h1" className="if-page-title">Profile</Text>
          <Text className="if-page-subtitle">Public identity, training summary, and lift video gallery.</Text>
        </Stack>
        <Button
          leftSection={<Save size={16} />}
          onClick={saveProfile}
          loading={saving}
          disabled={readOnly || loading || !settings}
          data-testid="profile-save"
        >
          Save Profile
        </Button>
      </div>

      {error && (
        <Alert color="red" title="Profile unavailable" icon={<AlertCircle size={16} />}>
          {error}
        </Alert>
      )}

      <Paper withBorder p="lg" radius="md" className="if-card">
        <Stack gap="md">
          <Group justify="space-between" align="flex-start" wrap="nowrap">
            <Group gap="md" align="flex-start" wrap="nowrap" style={{ minWidth: 0 }}>
              <Stack gap={6} align="center" style={{ flexShrink: 0 }}>
                <Avatar src={settings?.avatar_url ?? user.avatar} alt={resolvedName} radius="xl" size={60}>
                  {initials(resolvedName)}
                </Avatar>
                <FileButton
                  onChange={handleAvatarUpload}
                  accept="image/jpeg,image/png,image/webp,image/gif"
                  disabled={readOnly || loading || !settings || avatarUploading}
                >
                  {(props) => (
                    <Button
                      {...props}
                      size="xs"
                      variant="light"
                      leftSection={<Upload size={14} />}
                      loading={avatarUploading}
                      disabled={readOnly || loading || !settings}
                      data-testid="profile-avatar-upload"
                    >
                      Photo
                    </Button>
                  )}
                </FileButton>
                {avatarUploading && <Progress value={avatarProgress} size="xs" w={72} />}
              </Stack>
              <Stack gap={8} style={{ minWidth: 0 }}>
                <Group gap="xs" wrap="wrap">
                  <Text fw={600} size="lg" c="var(--text-primary)" truncate>
                    {resolvedName}
                  </Text>
                  <Text size="sm" c="var(--text-secondary)">
                    @{nickname || settings?.nickname}
                  </Text>
                  <span className="if-pill if-pill-success">Discord connected</span>
                  <span className={`if-pill ${profileVisibility === 'public' ? 'if-pill-info' : 'if-pill-neutral'}`}>
                    {profileVisibility}
                  </span>
                </Group>
                <Text size="sm" c="var(--text-secondary)">
                  {program?.meta.federation || 'Federation unset'} - {program?.meta.weight_class_kg || '--'} kg
                  {program?.meta.practicing_for ? ` - ${program.meta.practicing_for}` : ''}
                </Text>
              </Stack>
            </Group>
          </Group>

          <SimpleGrid cols={{ base: 1, md: 2 }} spacing="md">
            <TextInput
              label="Nickname"
              value={nickname}
              onChange={(event) => setNickname(event.currentTarget.value)}
              disabled={readOnly || loading || !settings}
              maxLength={32}
              data-testid="profile-nickname"
            />
            <TextInput
              label="Display name"
              value={displayName}
              onChange={(event) => setDisplayName(event.currentTarget.value)}
              disabled={readOnly || loading || !settings}
              maxLength={80}
              data-testid="profile-display-name"
            />
          </SimpleGrid>

          <Box>
            <Text size="sm" fw={500} mb={6}>Visibility</Text>
            <SegmentedControl
              value={profileVisibility}
              onChange={(value) => setProfileVisibility(value as ProfileVisibility)}
              data={[
                { label: 'Private', value: 'private' },
                { label: 'Public', value: 'public' },
              ]}
              className="if-segmented"
              disabled={readOnly || loading || !settings}
              fullWidth
            />
          </Box>

          <Textarea
            label="Bio"
            value={bio}
            onChange={(event) => setBio(event.currentTarget.value)}
            disabled={readOnly || loading || !settings}
            maxLength={280}
            minRows={3}
            data-testid="profile-bio"
          />
        </Stack>
      </Paper>

      <SimpleGrid cols={{ base: 2, xs: 3, md: 6 }} spacing="xs">
        {profileMetrics.map((metric) => (
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
                {videos.length} video{videos.length === 1 ? '' : 's'}
              </Text>
            </Group>
            <Group gap="xs" wrap="wrap">
              <div className="if-tab-group">
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
              <Button
                component={Link}
                to="/sessions"
                size="xs"
                variant="default"
                leftSection={<Upload size={14} />}
              >
                Upload
              </Button>
            </Group>
          </div>

          {videosLoading ? (
            <Group justify="center" py="xl">
              <Loader size="sm" />
            </Group>
          ) : filteredVideos.length > 0 ? (
            <div className="if-video-grid">
              {filteredVideos.map((item) => (
                <VideoCard key={item.video.video_id} item={item} onClick={() => setSelectedVideo(item)} />
              ))}
            </div>
          ) : (
            <Paper className="if-metric-card" p="lg">
              <Stack align="center" gap="xs">
                <Calendar size={28} color="var(--text-muted)" />
                <Text size="sm" c="var(--text-secondary)" ta="center">
                  No lift videos match this filter. Upload videos from a session.
                </Text>
              </Stack>
            </Paper>
          )}
        </Stack>
      </Paper>

      <VideoPlayerModal
        item={selectedVideo}
        onClose={() => setSelectedVideo(null)}
        onDeleted={loadVideos}
        readOnly={readOnly}
      />
    </Stack>
  )
}
