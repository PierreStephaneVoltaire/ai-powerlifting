import { useEffect, useState } from 'react'
import { Alert, Button, Card, Group, Loader, SimpleGrid, Stack, Table, Text, Title } from '@mantine/core'
import { Link } from 'react-router-dom'
import api from '@/api/http'
import { useAuth } from '@/auth/AuthProvider'
import { useSettingsStore } from '@/store/settingsStore'
import { toDisplayUnit } from '@/utils/units'
import type { CompetitionAttempt, LiftResults } from '@powerlifting/types'
import type { PublicProfile } from '@/api/profiles'
import AuthoredNotes from '@/components/notes/AuthoredNotes'
import LiftProfileContext from '@/components/lift-profiles/LiftProfileContext'

interface Context {
  profile: PublicProfile
  block: { id: string; name: string } | null
  phase: { name?: string } | string | null
  estimated_maxes: Record<string, number | string>
  competitions: Array<{ sk: string; name?: string; competition_name?: string; date?: string; start_date?: string; units?: 'kg' | 'lb'; post_meet_report?: { attempts: CompetitionAttempt[] }; results?: LiftResults; notes?: string }>
  notes: Array<{ date?: string; notes?: string; block?: string }>
}
export default function AthleteDetailsPage() {
  const { mapped_pk, person_pk, permissions } = useAuth()
  const { unit } = useSettingsStore()
  const contextKey = JSON.stringify([person_pk, mapped_pk, permissions])
  const [loaded, setLoaded] = useState<{ key: string; data?: Context; error?: string } | null>(null)
  const data = loaded?.key === contextKey ? loaded.data : undefined
  const error = loaded?.key === contextKey ? loaded.error : undefined
  const load = async (signal?: AbortSignal) => {
    setLoaded(null)
    try {
      const response = await api.get('/profiles/athlete/context', { signal })
      if (!signal?.aborted) setLoaded({ key: contextKey, data: response.data.data })
    } catch {
      if (!signal?.aborted) setLoaded({ key: contextKey, error: 'Could not load permitted Athlete details. Access may have changed.' })
    }
  }
  useEffect(() => {
    const controller = new AbortController()
    void load(controller.signal)
    return () => controller.abort()
  }, [contextKey])
  if (error) return <Alert color="red"><Stack><Text>{error}</Text><Button onClick={() => void load()}>Retry</Button></Stack></Alert>
  if (!data) return <Loader aria-label="Loading Athlete details" />
  return <Stack>
    <Title order={2}>{data.profile.display_name}</Title>
    <Text>{data.profile.federations?.join(' · ')}</Text>
    <LiftProfileContext profiles={data.profile.lift_profiles} athlete={mapped_pk} />
    <Group><Button component={Link} to={`/profiles/${encodeURIComponent(data.profile.nickname)}`} variant="light">Profile</Button>{permissions.includes('competition:read') && <Button component={Link} to="/designer/competitions">Competition Entries and Attempts</Button>}</Group>
    {data.block && <Card withBorder><Title order={3}>{data.block.name}</Title><Text>Phase: {typeof data.phase === 'string' ? data.phase : data.phase?.name || 'Not scheduled'}</Text></Card>}
    <Title order={3}>Current max estimates</Title>
    <Text size="xs" c="dimmed">Source: {String(data.estimated_maxes.method || 'none').replace(/_/g, ' ')}. Uses the same current-max calculation as Analysis.</Text>
    <SimpleGrid cols={3}>{['squat', 'bench', 'deadlift'].map(lift => <Card key={lift} withBorder><Text tt="capitalize">{lift}</Text><Text fw={600}>{typeof data.estimated_maxes[lift] === 'number' ? `${toDisplayUnit(Number(data.estimated_maxes[lift]), unit).toFixed(1)} ${unit}` : 'Not available'}</Text></Card>)}</SimpleGrid>
    <Title order={3}>Tied competitions</Title>
    {data.competitions.length ? data.competitions.map(entry => <Card key={entry.sk} withBorder><Stack gap="xs"><Text fw={600}>{entry.name || entry.competition_name || 'Competition'}</Text><Text>{entry.date || entry.start_date}</Text>{entry.notes && <Text>{entry.notes}</Text>}{entry.post_meet_report?.attempts?.length ? <Table><Table.Thead><Table.Tr><Table.Th>Lift</Table.Th><Table.Th>Attempt</Table.Th><Table.Th>Weight</Table.Th><Table.Th>Result</Table.Th></Table.Tr></Table.Thead><Table.Tbody>{entry.post_meet_report.attempts.map(attempt => <Table.Tr key={attempt.attempt_id || `${attempt.lift}:${attempt.attempt_number}`}><Table.Td tt="capitalize">{attempt.lift}</Table.Td><Table.Td>{attempt.attempt_number}</Table.Td><Table.Td>{attempt.kg == null ? 'Not set' : `${toDisplayUnit(attempt.kg, entry.units || 'kg').toFixed(1)} ${entry.units || 'kg'}`}</Table.Td><Table.Td>{attempt.result}</Table.Td></Table.Tr>)}</Table.Tbody></Table> : <Text c="dimmed" size="sm">Attempts have not been logged.</Text>}{entry.results && <Text>Total: {toDisplayUnit(entry.results.total_kg || 0, entry.units || 'kg').toFixed(1)} {entry.units || 'kg'}</Text>}</Stack></Card>) : <Text c="dimmed">No current tied Competition Entries. Access continues through seven days after the latest tied competition.</Text>}
    <Title order={3}>Block notes</Title>
    {data.notes.length ? data.notes.map((note, index) => <Card key={`${note.date}:${index}`} withBorder><Text size="xs">{note.date}</Text><Text style={{ whiteSpace: 'pre-wrap' }}>{note.notes}</Text></Card>) : <Text c="dimmed">No shared Block notes.</Text>}
    <AuthoredNotes initialDomain="competition" />
  </Stack>
}
