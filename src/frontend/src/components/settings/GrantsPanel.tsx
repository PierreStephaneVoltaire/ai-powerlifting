import { useEffect, useMemo, useState } from 'react'
import {
  Alert,
  Badge,
  Button,
  Card,
  Center,
  Group,
  Loader,
  Modal,
  MultiSelect,
  Select,
  Stack,
  Text,
  TextInput,
  Textarea,
  Title,
} from '@mantine/core'
import { useDisclosure } from '@mantine/hooks'
import { Trash2, UserPlus } from 'lucide-react'
import { useAuth } from '@/auth/AuthProvider'
import {
  type Grant,
  type GrantType,
  listGrantsApi,
} from '@/api/grants'
import { createRelationshipRequestApi, listRelationshipsApi, revokeRelationshipApi, type RelationshipRequest } from '@/api/relationships'
import { searchProfiles, type PublicProfile } from '@/api/profiles'
import { fetchUserCompetitions } from '@/api/client'
import { RelationshipInbox } from '@/components/settings/RelationshipInbox'

function formatDate(iso: string | null | undefined): string {
  if (!iso) return '\u2014'
  try {
    return new Date(iso).toLocaleString()
  } catch {
    return iso
  }
}

function isActiveGrant(g: Grant): boolean {
  if (g.revoked_at) return false
  if (!g.expires_at) return false
  return new Date(g.expires_at).getTime() > Date.now()
}

export function GrantsPanel() {
  const { user, mapped_pk, own_athlete_pk, readOnly } = useAuth()
  const [grants, setGrants] = useState<Grant[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [opened, { open, close }] = useDisclosure(false)
  const [submitting, setSubmitting] = useState(false)

  const [granteeInput, setGranteeInput] = useState('')
  const [grantType, setGrantType] = useState<GrantType | 'peer'>(user?.active_role === 'handler' ? 'handler' : 'coach')
  const [tiedCompetitionIds, setTiedCompetitionIds] = useState('')
  const [note, setNote] = useState('')
  const [profiles, setProfiles] = useState<PublicProfile[]>([])
  const [selectedProfile, setSelectedProfile] = useState<PublicProfile | null>(null)
  const [competitions, setCompetitions] = useState<Array<{ master_id: string; name: string; start_date: string; user_status: string }>>([])
  const [replacementId, setReplacementId] = useState<string | null>(null)
  const [currentRelationships, setCurrentRelationships] = useState<RelationshipRequest[]>([])

  const isAthleteOwner = Boolean(user?.roles.includes('athlete') && mapped_pk === own_athlete_pk)
  const canManage = isAthleteOwner && !readOnly
  const canRequest = Boolean(user) && !readOnly && Boolean(user?.active_role)

  const load = async () => {
    if (!user) return
    setLoading(true)
    setError(null)
    try {
      if (!isAthleteOwner) { setGrants([]); return }
      const [result, relationships] = await Promise.all([listGrantsApi({ athlete_mapped_pk: mapped_pk, include_inactive: true }), listRelationshipsApi()])
      setGrants(result.active.concat(result.inactive))
      setCurrentRelationships(relationships.history.filter(item => item.active && item.state === 'approved' && item.relationship_type !== 'peer'))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load grants')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (user) load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.sub, mapped_pk, isAthleteOwner])

  useEffect(() => {
    if (!isAthleteOwner && (user?.active_role === 'coach' || user?.active_role === 'handler')) setGrantType(user.active_role)
  }, [isAthleteOwner, user?.active_role])

  useEffect(() => {
    if (granteeInput.trim().length < 2) { setProfiles([]); return }
    let active = true
    void searchProfiles(granteeInput.trim()).then(result => { if (active) setProfiles(result.filter(profile => profile.athlete_pk !== mapped_pk && (isAthleteOwner ? true : profile.roles?.includes('athlete')))) }).catch(() => { if (active) setProfiles([]) })
    return () => { active = false }
  }, [granteeInput, mapped_pk, isAthleteOwner])

  useEffect(() => {
    if (!opened || !isAthleteOwner) return
    void fetchUserCompetitions().then(setCompetitions).catch(() => setCompetitions([]))
  }, [opened, isAthleteOwner])

  const submit = async () => {
    setSubmitting(true)
    setError(null)
    try {
      const tied = tiedCompetitionIds
        .split(',')
        .map(s => s.trim())
        .filter(Boolean)
      if (!selectedProfile) throw new Error('Select a verified profile')
      const athlete = isAthleteOwner ? mapped_pk : selectedProfile.athlete_pk
      await createRelationshipRequestApi({
        athlete_mapped_pk: athlete,
        recipient_person_pk: selectedProfile.person_pk || selectedProfile.athlete_pk,
        relationship_type: grantType,
        scope: grantType === 'peer' ? 'read' : 'write',
        tied_competition_ids: isAthleteOwner ? tied : [],
        ...(replacementId ? { replace_current_relationship_id: replacementId } : {}),
        note: note.trim() || undefined,
      })
      close()
      setGranteeInput('')
      setSelectedProfile(null)
      setTiedCompetitionIds('')
      setReplacementId(null)
      setNote('')
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create grant')
    } finally {
      setSubmitting(false)
    }
  }

  const revoke = async (g: Grant) => {
    if (!window.confirm(`Revoke ${g.grant_type} grant for ${g.grantee_mapped_pk}?`)) return
    setError(null)
    try {
      const relationshipId = (g as Grant & { relationship_id?: string }).relationship_id
      if (!relationshipId) throw new Error('This legacy grant must be migrated before it can be revoked')
      await revokeRelationshipApi(relationshipId)
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to revoke grant')
    }
  }

  const sorted = useMemo(
    () => [...grants].sort((a, b) => b.created_at.localeCompare(a.created_at)),
    [grants],
  )
  const activeReplacement = [
    ...sorted.filter(grant => isActiveGrant(grant) && grant.grant_type === grantType && (grant as Grant & { relationship_id?: string }).relationship_id).map(grant => ({ id: String((grant as Grant & { relationship_id?: string }).relationship_id), label: `${grant.grantee_nickname || grant.grantee_mapped_pk} (${formatDate(grant.expires_at)})` })),
    ...currentRelationships.filter(item => item.relationship_type === grantType).map(item => ({ id: item.relationship_id, label: `${item.recipient_person_pk} (${formatDate(item.expires_at)})` })),
  ]

  if (!user) {
    return (
      <Alert color="gray" variant="light">
        Sign in to manage grants for your account.
      </Alert>
    )
  }

  return (
    <Stack gap="md">
      <Group justify="space-between" align="center">
        <Title order={4}>Grants (coaches &amp; handlers)</Title>
        {canRequest && (
          <Button leftSection={<UserPlus size={16} />} onClick={open} data-testid="open-grant-modal">
            New grant
          </Button>
        )}
      </Group>

      <Text size="sm" c="dimmed">
        Grant a coach or handler time-bound access to your training data. Grants auto-expire;
        you can revoke them at any time.
      </Text>

      <RelationshipInbox />

      {error && (
        <Alert color="red" onClose={() => setError(null)} withCloseButton>
          {error}
        </Alert>
      )}

      {loading ? (
        <Center py="md"><Loader /></Center>
      ) : sorted.length === 0 ? (
        <Text c="dimmed" size="sm">No grants issued yet.</Text>
      ) : (
        <Stack gap="sm">
          {sorted.map((g) => {
            const active = isActiveGrant(g)
            return (
              <Card key={g.sk} withBorder padding="sm">
                <Group justify="space-between" align="flex-start" wrap="nowrap">
                  <Stack gap={4} style={{ flex: 1 }}>
                    <Group gap="xs">
                      <Badge color={g.grant_type === 'coach' ? 'blue' : 'grape'} variant="light">
                        {g.grant_type}
                      </Badge>
                      <Badge color={g.scope === 'write' ? 'orange' : 'gray'} variant="light">
                        {g.scope}
                      </Badge>
                      <Badge color={active ? 'green' : 'red'} variant="light">
                        {active ? 'active' : 'revoked/expired'}
                      </Badge>
                    </Group>
                    <Text fw={500} size="sm">
                      {g.grantee_nickname || g.grantee_mapped_pk}
                    </Text>
                    <Text size="xs" c="dimmed">
                      pk: <code>{g.grantee_mapped_pk}</code>
                    </Text>
                    <Text size="xs" c="dimmed">
                      expires: {formatDate(g.expires_at)} {g.revoked_at ? `(revoked ${formatDate(g.revoked_at)})` : ''}
                    </Text>
                    {g.tied_competition_ids.length > 0 && (
                      <Text size="xs" c="dimmed">
                        tied competitions: {g.tied_competition_ids.join(', ')}
                      </Text>
                    )}
                    {g.note && <Text size="xs">\u201c{g.note}\u201d</Text>}
                  </Stack>
                  {canManage && active && (
                    <Button
                      size="xs"
                      color="red"
                      variant="light"
                      leftSection={<Trash2 size={14} />}
                      onClick={() => revoke(g)}
                    >
                      Revoke
                    </Button>
                  )}
                </Group>
              </Card>
            )
          })}
        </Stack>
      )}

      <Modal opened={opened} onClose={close} title="New grant" size="md">
        <Stack>
          <TextInput
            label={isAthleteOwner ? 'Search for a verified Coach or Handler' : 'Search for an Athlete to invite'}
            placeholder="Display name or handle"
            value={granteeInput}
            onChange={(e) => setGranteeInput(e.currentTarget.value)}
            required
            data-testid="grant-grantee-input"
          />
          {profiles.length > 0 && <Select label="Verified profile" data={profiles.map(profile => ({ value: profile.athlete_pk, label: `${profile.display_name} (${profile.nickname})` }))} value={selectedProfile?.athlete_pk || null} onChange={value => setSelectedProfile(profiles.find(profile => profile.athlete_pk === value) || null)} />}
          <Select
            label="Grant type"
            data={isAthleteOwner ? [
              { value: 'coach', label: 'Coach (read-only access to programming)' },
              { value: 'handler', label: "Handler (can edit sessions on the athlete's behalf)" },
              { value: 'peer', label: 'Peer (selected read-only domains)' },
            ] : [{ value: user?.active_role || 'coach', label: `${user?.active_role || 'coach'} invitation` }]}
            value={grantType}
            onChange={(v) => setGrantType((v as GrantType | 'peer') ?? 'coach')}
            allowDeselect={false}
          />
          {isAthleteOwner && <MultiSelect
            label="Tied competition entries"
            placeholder="Select competition entries"
            value={tiedCompetitionIds.split(',').filter(Boolean)}
            onChange={(value) => setTiedCompetitionIds(value.join(','))}
            data={competitions.map(competition => ({ value: competition.master_id, label: `${competition.name} (${competition.start_date})` }))}
            searchable
          />}
          {isAthleteOwner && activeReplacement.length > 0 && <Select label="Replace current relationship (Athlete confirmation)" placeholder="Select the relationship to replace" data={activeReplacement.map(item => ({ value: item.id, label: item.label }))} value={replacementId} onChange={setReplacementId} clearable />}
          <Textarea
            label="Note (optional)"
            value={note}
            onChange={(e) => setNote(e.currentTarget.value)}
            minRows={2}
            maxRows={4}
          />
          <Group justify="flex-end">
            <Button variant="default" onClick={close}>Cancel</Button>
            <Button onClick={submit} loading={submitting} disabled={!selectedProfile || (isAthleteOwner && grantType !== 'peer' && !tiedCompetitionIds)}>
              {isAthleteOwner ? 'Send request' : 'Invite Athlete'}
            </Button>
          </Group>
        </Stack>
      </Modal>
    </Stack>
  )
}
