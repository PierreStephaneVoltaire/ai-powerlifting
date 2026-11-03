import { useEffect, useState } from 'react'
import { Alert, Button, Group, Select, Stack, Text } from '@mantine/core'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth, type ActiveRole } from '@/auth/AuthProvider'
import { listRelationshipsApi } from '@/api/relationships'
import { useProgramStore } from '@/store/programStore'
import { saveDraft } from '@/api/drafts'

export default function AthleteContext() {
  const auth = useAuth()
  const navigate = useNavigate()
  const [athletes, setAthletes] = useState<Array<{ value: string; label: string }>>([])
  const [error, setError] = useState('')
  const [switching, setSwitching] = useState(false)
  const [expanded, setExpanded] = useState(false)
  useEffect(() => {
    if (!auth.user) return
    let current = true
    void listRelationshipsApi().then(result => {
      if (!current) return
      const selected = new Map<string, string>()
      if (auth.own_athlete_pk) selected.set(auth.own_athlete_pk, 'My profile and training')
      selected.set(auth.mapped_pk, auth.athlete_display_name)
      for (const item of [...result.received, ...result.sent]) if (item.active === true) selected.set(item.athlete_mapped_pk, item.athlete_display_name || item.athlete_mapped_pk)
      setAthletes([...selected].map(([value, label]) => ({ value, label })))
    }).catch(() => {})
    return () => { current = false }
  }, [auth.person_pk, auth.mapped_pk, auth.own_athlete_pk, auth.athlete_display_name, auth.permissions])
  if (!auth.user) return <Alert mb="md" title="Explore NoLift"><Group><Text size="sm">Training tools and public profiles</Text><Button component={Link} to="/profiles" variant="light">Search</Button><Button component={Link} to="/about" variant="subtle">About</Button></Group></Alert>
  const switchAthlete = async (value: string | null) => {
    if (!value || value === auth.mapped_pk) return
    setSwitching(true)
    try {
      const state = useProgramStore.getState()
      if (state.isDirty && state.program) await saveDraft(`program:${state.version}`, state.program)
      await auth.selectAthlete(value)
      setError('')
      navigate(value === auth.own_athlete_pk ? '/' : auth.user?.active_role === 'handler' ? '/athlete' : '/sessions')
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not change Athlete') }
    finally { setSwitching(false) }
  }
  const role = (value: string | null) => {
    if (!value) return
    auth.selectRole(value as ActiveRole)
    navigate(value === 'athlete' ? '/' : '/roster')
  }
  return <Alert mb="md" color={auth.mapped_pk === auth.own_athlete_pk ? 'blue' : 'violet'} title={<Group justify="space-between" wrap="nowrap" gap="xs"><Text truncate title={`${auth.user.active_role || 'Profile'} · ${auth.athlete_display_name}`}>{`${auth.user.active_role || 'Profile'} · ${auth.athlete_display_name}`}</Text><Button className="if-athlete-context-toggle" variant="subtle" size="sm" onClick={() => setExpanded(value => !value)} aria-expanded={expanded} aria-controls="athlete-context-controls">{expanded ? 'Close' : 'Change'}</Button></Group>}>
    <Stack gap="xs"><div id="athlete-context-controls" className={`if-athlete-context-controls${expanded ? ' is-expanded' : ''}`}><Group align="end">
      <Select label="Active role" data={auth.user.roles.map(value => ({ value, label: value[0].toUpperCase() + value.slice(1) }))} value={auth.user.active_role} onChange={role} allowDeselect={false} />
      <Select label="Selected Athlete" data={athletes} value={auth.mapped_pk} onChange={switchAthlete} disabled={switching} searchable allowDeselect={false} />
      <Button component={Link} to="/roster" variant="light">Roster</Button><Button component={Link} to="/inbox" variant="light">Inbox</Button><Button component={Link} to="/my-notes" variant="light">My notes</Button>
    </Group><Text size="xs" mt="xs">Edits belong to {auth.athlete_display_name}. Access follows the Athlete’s current grants.</Text>{error && <Text c="red" role="alert">{error}</Text>}</div></Stack>
  </Alert>
}
