import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { Avatar, Badge, Button, Group, Loader, Paper, SimpleGrid, Stack, Text, TextInput } from '@mantine/core'
import { ArrowLeft, Search, User, Users } from 'lucide-react'
import { fetchProfile, searchProfiles, type PublicProfile } from '@/api/profiles'
import { useUiStore } from '@/store/uiStore'

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
          <Avatar src={profile.avatar_url} alt={profile.display_name} radius="xl">
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
        <Text size="sm" c={profile.bio ? 'var(--text-secondary)' : 'var(--text-muted)'} lineClamp={3}>
          {profile.bio || 'No bio yet.'}
        </Text>
        <Group gap="xs">
          <span className={`if-pill ${profile.profile_visibility === 'public' ? 'if-pill-info' : 'if-pill-neutral'}`}>
            {profile.profile_visibility}
          </span>
          {profile.public_training_summary_enabled && (
            <span className="if-pill if-pill-success">Training summary public</span>
          )}
        </Group>
      </Stack>
    </Paper>
  )
}

export default function ProfilesPage() {
  const { pushToast } = useUiStore()
  const [query, setQuery] = useState('')
  const [profiles, setProfiles] = useState<PublicProfile[]>([])
  const [loading, setLoading] = useState(false)

  const runSearch = async (nextQuery = query) => {
    setLoading(true)
    try {
      setProfiles(await searchProfiles(nextQuery))
    } catch {
      pushToast({ message: 'Profile search failed', type: 'error' })
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    runSearch('')
    // Run once on mount. Manual searches use the current input value.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <Stack gap="md">
      <div className="if-page-header">
        <Stack gap={2}>
          <Group gap="xs">
            <Users size={22} />
            <Text component="h1" className="if-page-title">Profiles</Text>
          </Group>
          <Text className="if-page-subtitle">Find public lifter profiles. Private profiles are hidden unless they are yours.</Text>
        </Stack>
      </div>

      <Paper p="md" radius="md" withBorder className="if-card">
        <Group align="flex-end">
          <TextInput
            leftSection={<Search size={16} />}
            label="Search"
            placeholder="Nickname, display name, or bio"
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
      </Paper>

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
          <Text c="var(--text-secondary)" ta="center">No public profiles found.</Text>
        </Paper>
      )}
    </Stack>
  )
}

export function PublicProfilePage() {
  const { nickname = '' } = useParams<{ nickname: string }>()
  const [profile, setProfile] = useState<PublicProfile | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

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
              <Avatar src={profile.avatar_url} alt={profile.display_name} radius="xl" size={60}>
                {initials(profile.display_name)}
              </Avatar>
              <Stack gap={6} style={{ minWidth: 0 }}>
                <Group gap="xs" wrap="wrap">
                  <Text fw={600} size="lg" c="var(--text-primary)" truncate>{profile.display_name}</Text>
                  <Text size="sm" c="var(--text-secondary)">@{profile.nickname}</Text>
                  {profile.is_self && <Badge size="xs">You</Badge>}
                </Group>
                <Group gap="xs">
                  <span className="if-pill if-pill-info">Public profile</span>
                  {profile.public_training_summary_enabled && (
                    <span className="if-pill if-pill-success">Training summary public</span>
                  )}
                </Group>
              </Stack>
            </Group>
            {profile.is_self && (
              <Button component={Link} to="/profile" variant="light" leftSection={<User size={16} />}>
                Edit
              </Button>
            )}
          </Group>
          <Text size="sm" c={profile.bio ? 'var(--text-primary)' : 'var(--text-muted)'} lh={1.6}>
            {profile.bio || 'No bio yet.'}
          </Text>
        </Stack>
      </Paper>

      <SimpleGrid cols={{ base: 1, md: 2 }} spacing="md">
        <Paper withBorder p="lg" radius="md" className="if-card">
          <Stack gap="xs">
            <Text className="if-card-title">Training Summary</Text>
            <Text size="sm" c="var(--text-secondary)">
              {profile.public_training_summary_enabled
                ? 'This profile has opted into public training metadata, but public training summary fields are not exposed by the current API.'
                : 'This athlete has not enabled a public training summary.'}
            </Text>
          </Stack>
        </Paper>
        <Paper withBorder p="lg" radius="md" className="if-card">
          <Stack gap="xs">
            <Text className="if-card-title">Lift Videos</Text>
            <Text size="sm" c="var(--text-secondary)">
              Public lift videos are not exposed by the current API.
            </Text>
          </Stack>
        </Paper>
      </SimpleGrid>
    </Stack>
  )
}
