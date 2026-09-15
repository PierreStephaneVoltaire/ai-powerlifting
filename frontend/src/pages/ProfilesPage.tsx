import LiftProfileContext from '@/components/lift-profiles/LiftProfileContext'
import ProfileFavorite from '@/components/settings/ProfileFavorite'
import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { Alert, Avatar, Badge, Button, Group, Loader, MultiSelect, Paper, SegmentedControl, Select, SimpleGrid, Stack, Text, TextInput } from '@mantine/core'
import { ArrowLeft, Calendar, Film, Search, User, Users } from 'lucide-react'
import { fetchProfile, searchProfilePage, type ProfileSearchInput, type PublicProfile } from '@/api/profiles'
import { fetchFederations } from '@/api/client'
import api from '@/api/http'
import { useUiStore } from '@/store/uiStore'
import { useSettingsStore } from '@/store/settingsStore'
import { resolveAvatarUrl } from '@/utils/media'
import { toDisplayUnit } from '@/utils/units'
import VideoCard from '@/components/videos/VideoCard'
import VideoPlayerModal from '@/components/videos/VideoPlayerModal'
import { sortVideos, VIDEO_SORTS, type VideoSort } from '@/utils/videoSort'
import { useVideoModalFromUrl } from '@/utils/useVideoModalFromUrl'
import { listFavoritesApi, setFavoriteApi } from '@/api/relationships'
import { useAuth } from '@/auth/AuthProvider'

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean)
  if (!parts.length) return 'U'
  return parts.slice(0, 2).map((part) => part[0]?.toUpperCase()).join('')
}

function ProfileCard({ profile }: { profile: PublicProfile }) {
  return (
    <Paper component={Link} to={`/profiles/${profile.nickname}`} p="md" radius="md" withBorder className="if-card" style={{ textDecoration: 'none' }}>
      <Stack gap="sm">
        <Group gap="sm" align="center" wrap="nowrap">
          <Avatar src={resolveAvatarUrl(profile.avatar_url)} alt={profile.display_name} radius="xl">
            {initials(profile.display_name)}
          </Avatar>
          <Stack gap={0} style={{ minWidth: 0 }}>
            <Group gap="xs" wrap="wrap">
              <Text fw={600} c="var(--text-primary)" truncate>{profile.display_name}</Text>
              {profile.is_self && <Badge size="xs">You</Badge>}
            </Group>
            <Text size="xs" c="var(--text-secondary)">@{profile.nickname}</Text>
          </Stack>
        </Group>
        {profile.bio && (
          <Text size="sm" c="var(--text-secondary)" lineClamp={3}>
            {profile.bio}
          </Text>
        )}
        {(profile.federation || profile.weight_class_kg) && (
          <Text size="xs" c="var(--text-secondary)">
            {profile.federation || 'Federation unset'} - {profile.weight_class_kg || '--'} kg
          </Text>
        )}
        {(profile.tags || []).length > 0 && (
          <Group gap={4} wrap="wrap">
            {profile.tags.map((tag) => (
              <Badge key={tag} variant="light" size="xs">{tag}</Badge>
            ))}
          </Group>
        )}
        <Group gap="xs">
          <span className={`if-pill ${profile.profile_visibility === 'public' ? 'if-pill-info' : 'if-pill-neutral'}`}>
            {profile.profile_visibility}
          </span>
        </Group>
      </Stack>
    </Paper>
  )
}

export default function ProfilesPage() {
  const { user } = useAuth()
  const [query, setQuery] = useState('')
  const [profiles, setProfiles] = useState<PublicProfile[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [tags, setTags] = useState<string[]>([])
  const [tagMode, setTagMode] = useState<'and' | 'or'>('and')
  const [federations, setFederations] = useState<string[]>([])
  const [role, setRole] = useState<'athlete' | 'coach' | null>(null)
  const [tagOptions, setTagOptions] = useState<string[]>([])
  const [federationOptions, setFederationOptions] = useState<{ value: string; label: string }[]>([])
  const [nextCursor, setNextCursor] = useState<string | null>(null)
  const [favorites, setFavorites] = useState<string[]>([])
  const activeSearch = useRef<ProfileSearchInput>({})
  const requestNumber = useRef(0)

  const runSearch = async (nextQuery = query, append = false) => {
    const request = ++requestNumber.current
    setLoading(true)
    setError('')
    if (!append) activeSearch.current = { query: nextQuery, tags, federations, tag_mode: tagMode, ...(role ? { role } : {}) }
    try {
      const page = await searchProfilePage({ ...activeSearch.current, ...(append && nextCursor ? { cursor: nextCursor } : {}) })
      if (request !== requestNumber.current) return
      setProfiles(previous => append ? [...previous, ...page.profiles] : page.profiles)
      setNextCursor(page.next_cursor)
    } catch {
      if (request === requestNumber.current) setError('Profile search failed. Please retry.')
    } finally {
      if (request === requestNumber.current) setLoading(false)
    }
  }

  useEffect(() => {
    runSearch('')
    Promise.all([api.get('/profiles/tags'), fetchFederations()]).then(([catalog, library]) => {
      setTagOptions(catalog.data.data.filter((tag: { status: string }) => tag.status === 'approved').map((tag: { tag: string }) => tag.tag))
      setFederationOptions(library.map(federation => ({ value: federation.pk, label: federation.abbreviation || federation.name })))
    }).catch(() => setError('Search filters could not be loaded. Reload the page to retry.'))
  }, [])

  useEffect(() => {
    if (!user) { setFavorites([]); return }
    void listFavoritesApi().then(result => setFavorites(result.favorites.map(item => item.athlete_mapped_pk))).catch(() => setFavorites([]))
  }, [user?.sub])

  return (
    <Stack gap="md">
      <div className="if-page-header">
        <Stack gap={2}>
          <Group gap="xs">
            <Users size={22} />
            <Text component="h1" className="if-page-title">Profiles</Text>
          </Group>
          <Text className="if-page-subtitle">Find public Athletes and Coaches, plus private profiles you have permission to view.</Text>
        </Stack>
      </div>

      <Paper p="md" radius="md" withBorder className="if-card">
        <Group align="flex-end">
          <TextInput
            leftSection={<Search size={16} />}
            label="Search"
            placeholder="Handle or display name"
            value={query}
            onChange={(event) => setQuery(event.currentTarget.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') runSearch()
            }}
            style={{ flex: 1, minWidth: 220 }}
          />
          <Button leftSection={<Search size={16} />} loading={loading} onClick={() => runSearch()}>
            Search
          </Button>
        </Group>
        <Group align="end" mt="md">
          <MultiSelect label="Federations" data={federationOptions} searchable value={federations} onChange={setFederations} />
          <MultiSelect label="Approved tags" data={tagOptions} searchable value={tags} onChange={setTags} />
          <Select label="Role" placeholder="Athletes and Coaches" clearable data={[{ value: 'athlete', label: 'Athlete' }, { value: 'coach', label: 'Coach' }]} value={role} onChange={value => setRole(value as 'athlete' | 'coach' | null)} />
          <Stack gap={4}><Text size="sm">Match tags</Text><SegmentedControl value={tagMode} onChange={value => setTagMode(value as 'and' | 'or')} data={[{ value: 'and', label: 'All' }, { value: 'or', label: 'Any' }]} /></Stack>
        </Group>
      </Paper>
      {user && <Paper p="md" radius="md" withBorder className="if-card"><Group justify="space-between"><Text fw={600}>Private favorites</Text><Text size="xs" c="dimmed">Only you can see these IDs. Favorites grant no access.</Text></Group>{favorites.length === 0 ? <Text size="sm" c="dimmed" mt="sm">No favorites yet.</Text> : <Stack gap="xs" mt="sm">{favorites.map(athlete => <Group key={athlete} justify="space-between"><code>{athlete}</code><Button size="xs" variant="subtle" onClick={() => void setFavoriteApi(athlete, 'remove').then(() => setFavorites(items => items.filter(item => item !== athlete)))}>Remove</Button></Group>)}</Stack>}</Paper>}
      {error && <Alert color="red">{error} <Button variant="subtle" onClick={() => runSearch()}>Retry</Button></Alert>}

      {loading && profiles.length === 0 ? (
        <Group justify="center" py="xl">
          <Loader size="sm" />
        </Group>
      ) : profiles.length > 0 ? (
        <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }} spacing="md">
          {profiles.map((profile) => (
            <ProfileCard key={profile.nickname} profile={profile} />
          ))}
        </SimpleGrid>
      ) : (
        <Paper p="xl" radius="md" withBorder className="if-card">
          <Text c="var(--text-secondary)" ta="center">No profiles match these filters.</Text>
        </Paper>
      )}
      {nextCursor && <Button loading={loading} onClick={() => runSearch(query, true)}>Show twenty more</Button>}
    </Stack>
  )
}

export function PublicProfilePage() {
  const { nickname = '' } = useParams<{ nickname: string }>()
  const { unit } = useSettingsStore()
  const [profile, setProfile] = useState<PublicProfile | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [videoSort, setVideoSort] = useState<VideoSort>('newest')

  const liftVideos = useMemo(() => profile?.lift_videos ?? [], [profile?.lift_videos])
  const sortedVideos = useMemo(() => sortVideos(liftVideos, videoSort), [liftVideos, videoSort])
  const { selectedVideo, openVideo, closeVideo } = useVideoModalFromUrl(liftVideos, !loading && !!profile)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    fetchProfile(nickname)
      .then((nextProfile) => {
        if (!cancelled) setProfile(nextProfile)
      })
      .catch(() => {
        if (!cancelled) setError('Profile not found or not public.')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [nickname])

  const profileMetrics = useMemo(() => {
    const summary = profile?.summary
    const weightValue = (kg: number | null | undefined) => {
      const n = Number(kg)
      if (!Number.isFinite(n) || n <= 0) return '--'
      const display = toDisplayUnit(n, unit)
      return Number.isInteger(display) ? String(display) : display.toFixed(1)
    }

    return [
      { label: 'Squat', value: weightValue(summary?.squat_kg), sub: unit },
      { label: 'Bench', value: weightValue(summary?.bench_kg), sub: unit },
      { label: 'Deadlift', value: weightValue(summary?.deadlift_kg), sub: unit },
      { label: 'Total', value: weightValue(summary?.total_kg), sub: unit },
      { label: 'DOTS', value: summary?.dots !== null && summary?.dots !== undefined && Number.isFinite(Number(summary.dots)) ? Number(summary.dots).toFixed(1) : '--', sub: 'pts' },
      { label: 'Class', value: profile?.weight_class_kg ? String(profile.weight_class_kg) : '--', sub: 'kg' },
    ]
  }, [profile, unit])

  if (loading) {
    return (
      <Group justify="center" py="xl">
        <Loader size="sm" />
      </Group>
    )
  }

  if (error || !profile) {
    return (
      <Stack gap="md">
        <Button component={Link} to="/profiles" variant="default" leftSection={<ArrowLeft size={16} />} w="fit-content">
          Back to profiles
        </Button>
        <Paper p="xl" radius="md" withBorder className="if-card">
          <Text c="var(--text-secondary)" ta="center">{error || 'Profile unavailable.'}</Text>
        </Paper>
      </Stack>
    )
  }

  return (
    <Stack gap="md">
      <Button component={Link} to="/profiles" variant="default" leftSection={<ArrowLeft size={16} />} w="fit-content">
        Back to profiles
      </Button>

      <Paper withBorder p="lg" radius="md" className="if-card">
        <Stack gap="md">
          <Group justify="space-between" align="flex-start">
            <Group gap="md" align="flex-start" wrap="nowrap" style={{ minWidth: 0 }}>
              <Avatar src={resolveAvatarUrl(profile.avatar_url)} alt={profile.display_name} radius="xl" size={60}>
                {initials(profile.display_name)}
              </Avatar>
              <Stack gap={6} style={{ minWidth: 0 }}>
                <Group gap="xs" wrap="wrap">
                  <Text fw={600} size="lg" c="var(--text-primary)" truncate>{profile.display_name}</Text>
                  <Text size="sm" c="var(--text-secondary)">@{profile.nickname}</Text>
                  {profile.is_self && <Badge size="xs">You</Badge>}
                </Group>
                <Group gap="xs">
                  <span className="if-pill if-pill-info">{profile.profile_visibility === 'public' ? 'Public profile' : 'Granted private profile'}</span>
                </Group>
                <Text size="sm" c="var(--text-secondary)">
                  {profile.federation || 'Federation unset'} - {profile.weight_class_kg || '--'} kg
                  {profile.practicing_for ? ` - ${profile.practicing_for}` : ''}
                </Text>
                {(profile.tags || []).length > 0 && (
                  <Group gap={4} wrap="wrap">
                    {profile.tags.map((tag) => (
                      <Badge key={tag} variant="light" size="sm">{tag}</Badge>
                    ))}
                  </Group>
                )}
              </Stack>
            </Group>
            {!profile.is_self && <ProfileFavorite athlete={profile.athlete_pk} />}
            {profile.is_self && (
              <Button component={Link} to="/profile" variant="light" leftSection={<User size={16} />}>
                Edit
              </Button>
            )}
          </Group>
          {profile.bio && (
            <Text size="sm" c="var(--text-primary)" lh={1.6}>
              {profile.bio}
            </Text>
          )}
        </Stack>
      </Paper>

      <LiftProfileContext profiles={profile.lift_profiles} athlete={profile.athlete_pk} />

      <SimpleGrid cols={{ base: 2, xs: 3, md: 6 }} spacing="xs">
        {profileMetrics.map((metric) => (
          <Paper key={metric.label} className="if-metric-card" p="sm" ta="center">
            <Text className="if-metric-label">{metric.label}</Text>
            <Text className="if-metric-value">{metric.value}</Text>
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
                {sortedVideos.length} video{sortedVideos.length === 1 ? '' : 's'}
              </Text>
            </Group>
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
          </div>
          {sortedVideos.length > 0 ? (
            <div className="if-video-grid">
              {sortedVideos.map((item) => (
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
                  No public lift videos yet.
                </Text>
              </Stack>
            </Paper>
          )}
        </Stack>
      </Paper>

      <VideoPlayerModal
        item={selectedVideo}
        onClose={closeVideo}
        onDeleted={() => undefined}
        readOnly
      />
    </Stack>
  )
}
