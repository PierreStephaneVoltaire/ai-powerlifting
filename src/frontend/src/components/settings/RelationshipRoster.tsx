import { useCallback, useEffect, useState } from 'react'
import { Alert, Badge, Button, Card, Group, Loader, Stack, Text } from '@mantine/core'
import { useNavigate } from 'react-router-dom'
import { listRelationshipsApi, type RelationshipRequest } from '@/api/relationships'
import { useAuth } from '@/auth/AuthProvider'
import { useProgramStore } from '@/store/programStore'
import { saveDraft } from '@/api/drafts'

export function RelationshipRoster() {
  const auth = useAuth()
  const navigate = useNavigate()
  const [items, setItems] = useState<RelationshipRequest[]>([])
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const load = useCallback(async () => {
    if (!auth.user) return
    setLoading(true)
    try {
      const result = await listRelationshipsApi()
      const relationships = new Map([...result.received, ...result.sent].map(item => [item.relationship_id, item]))
      setItems([...relationships.values()].filter(item => item.active && item.athlete_person_pk !== auth.person_pk && (item.relationship_type === auth.user?.active_role || item.relationship_type === 'peer')))
      setError('')
    } catch { setError('Could not load your current roster') }
    finally { setLoading(false) }
  }, [auth.person_pk, auth.user?.active_role])
  useEffect(() => { void load() }, [load])
  if (!auth.user) return null
  const select = async (item: RelationshipRequest) => {
    try {
      const state = useProgramStore.getState()
      if (state.isDirty && state.program) await saveDraft(`program:${state.version}`, state.program)
      await auth.selectAthlete(item.athlete_mapped_pk)
      navigate(auth.user?.active_role === 'handler' ? '/athlete' : '/sessions')
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not select Athlete') }
  }
  return <Stack gap="sm">
    {error && <Alert color="red">{error}</Alert>}
    <Button onClick={load} variant="light" loading={loading}>Refresh roster</Button>
    {loading ? <Loader size="sm" /> : items.length === 0 ? <Text c="dimmed">No active Athletes. Accepted requests appear here while their grants remain active.</Text> : items.map(item => <Card key={item.relationship_id} withBorder padding="sm"><Stack gap="xs"><Group justify="space-between"><Text fw={600}>{item.athlete_display_name || 'Athlete'}</Text><Badge>{item.relationship_type}</Badge></Group><Text size="xs" c="dimmed">{item.expires_at ? `Access through ${new Date(item.expires_at).toLocaleDateString()}` : 'Peer read access'}</Text><Button onClick={() => select(item)}>Open Athlete</Button></Stack></Card>)}
  </Stack>
}
