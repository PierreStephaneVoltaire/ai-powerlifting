import { useEffect, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Alert, Avatar, Badge, Button, Group, Loader, MultiSelect, Paper, SegmentedControl, Select, SimpleGrid, Stack, Text, TextInput } from '@mantine/core'
import { Search, Users } from 'lucide-react'
import { searchProfilePage, type ProfileSearchInput, type PublicProfile } from '@/api/profiles'
import { fetchFederations } from '@/api/client'
import api from '@/api/http'
import { useAuth } from '@/auth/AuthProvider'
import { resolveAvatarUrl } from '@/utils/media'
import { listFavoritesApi, setFavoriteApi } from '@/api/relationships'

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean)
  if (!parts.length) return 'U'
  return parts.slice(0, 2).map((part) => part[0]?.toUpperCase()).join('')
}

function ProfileCard({ profile }: { profile: PublicProfile }) {
  return (
    <Paper component={Link} to={`/profiles/${profile.nickname}`} p="md" radius="md" withBorder className="if-card" style={{ textDecoration: 'none' }}>
      <Stack gap="sm">
        <Group gap="sm" align="center" wrap="nowrap"><Avatar src={resolveAvatarUrl(profile.avatar_url)} alt={profile.display_name} radius="xl">{initials(profile.display_name)}</Avatar><Stack gap={0} style={{ minWidth: 0 }}><Group gap="xs" wrap="wrap"><Text fw={600} c="var(--text-primary)" truncate>{profile.display_name}</Text>{profile.is_self && <Badge size="xs">You</Badge>}</Group><Text size="xs" c="var(--text-secondary)">@{profile.nickname}</Text></Stack></Group>
        {profile.bio && <Text size="sm" c="var(--text-secondary)" lineClamp={3}>{profile.bio}</Text>}
        {(profile.federation || profile.weight_class_kg) && <Text size="xs" c="var(--text-secondary)">{profile.federation || 'Federation unset'} - {profile.weight_class_kg || '--'} kg</Text>}
        {(profile.tags || []).length > 0 && <Group gap={4} wrap="wrap">{profile.tags.map((tag) => <Badge key={tag} variant="light" size="xs">{tag}</Badge>)}</Group>}
        <Group gap="xs"><span className={`if-pill ${profile.profile_visibility === 'public' ? 'if-pill-info' : 'if-pill-neutral'}`}>{profile.profile_visibility}</span></Group>
      </Stack>
    </Paper>
  )
}

export default function ProfilesPage() {
  const { user } = useAuth()
  const [searchParams, setSearchParams] = useSearchParams()
  const [query, setQuery] = useState(() => searchParams.get('q') || '')
  const [profiles, setProfiles] = useState<PublicProfile[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [tags, setTags] = useState<string[]>(() => searchParams.getAll('tag'))
  const [tagMode, setTagMode] = useState<'and' | 'or'>(() => searchParams.get('tag_mode') === 'or' ? 'or' : 'and')
  const [federations, setFederations] = useState<string[]>(() => searchParams.getAll('federation'))
  const [role, setRole] = useState<'athlete' | 'coach' | null>(() => { const value = searchParams.get('role'); return value === 'athlete' || value === 'coach' ? value : null })
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
    if (!append) {
      activeSearch.current = { query: nextQuery, tags, federations, tag_mode: tagMode, ...(role ? { role } : {}) }
      const params = new URLSearchParams()
      if (nextQuery) params.set('q', nextQuery)
      for (const tag of tags) params.append('tag', tag)
      for (const federation of federations) params.append('federation', federation)
      if (role) params.set('role', role)
      if (tagMode === 'or') params.set('tag_mode', 'or')
      setSearchParams(params, { replace: true })
    }
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

  useEffect(() => { runSearch() }, [tags, federations, role, tagMode])
  useEffect(() => {
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
      <div className="if-page-header"><Stack gap={2}><Group gap="xs"><Users size={22} /><Text component="h1" className="if-page-title">Profiles</Text></Group><Text className="if-page-subtitle">Find public Athletes and Coaches, plus private profiles you have permission to view.</Text></Stack></div>
      <Paper p="md" radius="md" withBorder className="if-card"><Group align="flex-end"><TextInput leftSection={<Search size={16} />} label="Search" placeholder="Handle or display name" value={query} onChange={(event) => setQuery(event.currentTarget.value)} onKeyDown={(event) => { if (event.key === 'Enter') runSearch() }} style={{ flex: 1, minWidth: 220 }} /><Button leftSection={<Search size={16} />} loading={loading} onClick={() => runSearch()}>Search</Button></Group><Group align="end" mt="md"><MultiSelect label="Federations" data={federationOptions} searchable value={federations} onChange={setFederations} /><MultiSelect label="Approved tags" data={tagOptions} searchable value={tags} onChange={setTags} /><Select label="Role" placeholder="Athletes and Coaches" clearable data={[{ value: 'athlete', label: 'Athlete' }, { value: 'coach', label: 'Coach' }]} value={role} onChange={value => setRole(value as 'athlete' | 'coach' | null)} /><Stack gap={4}><Text size="sm">Match tags</Text><SegmentedControl value={tagMode} onChange={value => setTagMode(value as 'and' | 'or')} data={[{ value: 'and', label: 'All' }, { value: 'or', label: 'Any' }]} /></Stack></Group></Paper>
      {user && <Paper p="md" radius="md" withBorder className="if-card"><Group justify="space-between"><Text fw={600}>Private favorites</Text><Text size="xs" c="dimmed">Only you can see these IDs. Favorites grant no access.</Text></Group>{favorites.length === 0 ? <Text size="sm" c="dimmed" mt="sm">No favorites yet.</Text> : <Stack gap="xs" mt="sm">{favorites.map(athlete => <Group key={athlete} justify="space-between"><code>{athlete}</code><Button size="xs" variant="subtle" onClick={() => void setFavoriteApi(athlete, 'remove').then(() => setFavorites(items => items.filter(item => item !== athlete)))}>Remove</Button></Group>)}</Stack>}</Paper>}
      {error && <Alert color="red">{error} <Button variant="subtle" onClick={() => runSearch()}>Retry</Button></Alert>}
      {loading && profiles.length === 0 ? <Group justify="center" py="xl"><Loader size="sm" /></Group> : profiles.length > 0 ? <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }} spacing="md">{profiles.map((profile) => <ProfileCard key={profile.nickname} profile={profile} />)}</SimpleGrid> : <Paper p="xl" radius="md" withBorder className="if-card"><Text c="var(--text-secondary)" ta="center">No profiles match these filters.</Text></Paper>}
      {nextCursor && <Button loading={loading} onClick={() => runSearch(query, true)}>Show twenty more</Button>}
    </Stack>
  )
}
