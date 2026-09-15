import { useCallback, useEffect, useState } from 'react'
import { Alert, Badge, Button, Card, Group, Loader, MultiSelect, Select, SegmentedControl, Stack, Text } from '@mantine/core'
import { useAuth } from '@/auth/AuthProvider'
import {
  cancelRelationshipApi,
  listNotificationsApi,
  listRelationshipsApi,
  markNotificationsReadApi,
  respondRelationshipApi,
  revokeRelationshipApi,
  type RelationshipRequest,
} from '@/api/relationships'
import { fetchUserCompetitions } from '@/api/client'

const PERMISSION_OPTIONS = ['profile', 'program', 'sessions', 'competition', 'federation', 'glossary', 'goals', 'budget', 'calculations', 'performance', 'weight-log', 'templates', 'imports', 'lift-profiles', 'analytics', 'videos'].flatMap(domain => [`${domain}:read`, `${domain}:write`])

type View = 'received' | 'sent' | 'history'

function RequestCard({ item, view, competitions, currentRelationships, onChanged }: { item: RelationshipRequest; view: View; competitions: Array<{ master_id: string; name: string; start_date: string }>; currentRelationships: RelationshipRequest[]; onChanged: () => void }) {
  const [working, setWorking] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [scope, setScope] = useState<'read' | 'write'>('write')
  const [permissions, setPermissions] = useState<string[]>([])
  const [tied, setTied] = useState<string[]>([])
  const [replacementId, setReplacementId] = useState<string | null>(null)
  const act = async (action: 'approve' | 'reject' | 'cancel' | 'revoke') => {
    setWorking(true)
    setError(null)
    try {
      if (action === 'approve' || action === 'reject') await respondRelationshipApi(item.relationship_id, action, action === 'approve' && item.request_direction === 'coach_to_athlete' ? { scope, permissions, tied_competition_ids: tied, ...(replacementId ? { replace_current_relationship_id: replacementId } : {}) } : {})
      else if (action === 'cancel') await cancelRelationshipApi(item.relationship_id)
      else await revokeRelationshipApi(item.relationship_id)
      onChanged()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Relationship update failed')
    } finally {
      setWorking(false)
    }
  }
  const pending = item.state === 'pending'
  return (
    <Card withBorder padding="sm">
      <Stack gap="xs">
        <Group justify="space-between">
          <Group gap="xs">
            <Badge>{item.relationship_type}</Badge>
            <Badge color={item.state === 'approved' ? 'green' : item.state === 'pending' ? 'yellow' : 'gray'}>{item.state}</Badge>
          </Group>
          <Text size="xs" c="dimmed">{new Date(item.created_at).toLocaleDateString()}</Text>
        </Group>
        <Text size="sm">Athlete: <code>{item.athlete_mapped_pk}</code></Text>
        <Text size="xs" c="dimmed">Requester: <code>{item.requester_person_pk || item.athlete_person_pk}</code> · Recipient: <code>{item.recipient_person_pk}</code></Text>
        <Text size="xs" c="dimmed">Permissions: {item.permissions.join(', ') || 'none'}</Text>
        {item.tied_competition_ids.length > 0 && <Text size="xs" c="dimmed">Competitions: {item.tied_competition_ids.join(', ')}</Text>}
        {error && <Alert color="red">{error}</Alert>}
        {pending && view === 'received' && item.request_direction === 'coach_to_athlete' && <><Select label="Authorized scope" data={[{ value: 'read', label: 'Read only' }, { value: 'write', label: 'Read and write' }]} value={scope} onChange={value => setScope((value as 'read' | 'write') || 'write')} /><MultiSelect label="Authorized permissions" data={PERMISSION_OPTIONS} value={permissions} onChange={setPermissions} searchable /><MultiSelect label="Tied competition entries" data={competitions.map(competition => ({ value: competition.master_id, label: `${competition.name} (${competition.start_date})` }))} value={tied} onChange={setTied} searchable />{currentRelationships.length > 0 && <Select label="Replace current relationship (Athlete confirmation)" placeholder="Choose a current Coach or Handler" data={currentRelationships.map(current => ({ value: current.relationship_id, label: `${current.relationship_type} · ${current.recipient_person_pk} · ${current.expires_at ? new Date(current.expires_at).toLocaleDateString() : 'legacy'}` }))} value={replacementId} onChange={setReplacementId} clearable />}</>}
        {pending && view === 'received' && <Group><Button size="xs" loading={working} onClick={() => act('approve')}>Approve</Button><Button size="xs" color="red" variant="light" loading={working} onClick={() => act('reject')}>Reject</Button></Group>}
        {pending && view === 'sent' && <Button size="xs" variant="light" loading={working} onClick={() => act('cancel')}>Cancel request</Button>}
        {item.state === 'approved' && view === 'received' && <Button size="xs" color="red" variant="light" loading={working} onClick={() => act('revoke')}>Revoke</Button>}
      </Stack>
    </Card>
  )
}

export function RelationshipInbox() {
  const { user, person_pk } = useAuth()
  const [view, setView] = useState<View>('received')
  const [data, setData] = useState<{ sent: RelationshipRequest[]; received: RelationshipRequest[]; history: RelationshipRequest[] }>({ sent: [], received: [], history: [] })
  const [notifications, setNotifications] = useState<Array<{ notification_id: string; kind: string; payload?: Record<string, unknown>; read_at: string | null; created_at: string }>>([])
  const [competitions, setCompetitions] = useState<Array<{ master_id: string; name: string; start_date: string }>>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const load = useCallback(async () => {
    if (!user) return
    setLoading(true)
    setError(null)
    try {
      const [relationships, inbox] = await Promise.all([listRelationshipsApi(), listNotificationsApi()])
      setData(relationships)
      setNotifications(inbox.notifications)
      if (relationships.received.some(item => item.state === 'pending' && item.request_direction === 'coach_to_athlete')) setCompetitions(await fetchUserCompetitions())
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Failed to load relationships') } finally { setLoading(false) }
  }, [user])
  useEffect(() => { void load() }, [load])
  if (!user) return null
  const items = data[view]
  const currentRelationships = data.history.filter(item => item.state === 'approved' && item.active && item.relationship_type !== 'peer')
  return (
    <Stack gap="sm">
      <SegmentedControl value={view} onChange={(value) => setView(value as View)} data={[{ value: 'received', label: 'Received' }, { value: 'sent', label: 'Sent' }, { value: 'history', label: 'History' }]} fullWidth />
      {error && <Alert color="red" withCloseButton onClose={() => setError(null)}>{error}</Alert>}
      {notifications.some(notification => !notification.read_at) && <Card withBorder padding="sm"><Group justify="space-between"><Text size="sm" fw={600}>Notifications</Text><Button size="xs" variant="light" onClick={() => markNotificationsReadApi(notifications.filter(notification => !notification.read_at).map(notification => notification.notification_id)).then(() => void load())}>Mark all read</Button></Group><Stack gap={2}>{notifications.filter(notification => !notification.read_at).slice(0, 5).map(notification => <Text size="xs" key={notification.notification_id}>{typeof notification.payload?.message === 'string' ? notification.payload.message : notification.kind} · {new Date(notification.created_at).toLocaleString()}</Text>)}</Stack></Card>}
      {loading ? <Loader size="sm" /> : items.length === 0 ? <Text size="sm" c="dimmed">No relationship requests.</Text> : items.map((item) => <RequestCard key={item.relationship_id} item={item} competitions={competitions} currentRelationships={currentRelationships.filter(current => current.athlete_mapped_pk === item.athlete_mapped_pk && current.relationship_type === item.relationship_type && current.relationship_id !== item.relationship_id)} view={view === 'history' ? (item.recipient_person_pk === person_pk ? 'received' : 'sent') : view} onChanged={() => void load()} />)}
    </Stack>
  )
}
