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
  type GrantScope,
  createGrantApi,
  listGrantsApi,
  revokeGrantApi,
} from '@/api/grants'

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
  const { user, mapped_pk, readOnly } = useAuth()
  const [grants, setGrants] = useState<Grant[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [opened, { open, close }] = useDisclosure(false)
  const [submitting, setSubmitting] = useState(false)

  const [granteeInput, setGranteeInput] = useState('')
  const [granteeNickname, setGranteeNickname] = useState('')
  const [grantType, setGrantType] = useState<GrantType>('coach')
  const [scope, setScope] = useState<GrantScope>('read')
  const [tiedCompetitionIds, setTiedCompetitionIds] = useState('')
  const [note, setNote] = useState('')

  const canManage = Boolean(user) && !readOnly

  const load = async () => {
    if (!user) return
    setLoading(true)
    setError(null)
    try {
      const result = await listGrantsApi({ athlete_mapped_pk: mapped_pk, include_inactive: true })
      setGrants(result.active.concat(result.inactive))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load grants')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (user) load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.sub, mapped_pk])

  const submit = async () => {
    setSubmitting(true)
    setError(null)
    try {
      const tied = tiedCompetitionIds
        .split(',')
        .map(s => s.trim())
        .filter(Boolean)
      let grantee_mapped_pk = granteeInput.trim()
      let grantee_discord_id: string | undefined
      let grantee_authentik_sub: string | undefined
      if (grantee_mapped_pk.startsWith('discord:')) {
        grantee_discord_id = grantee_mapped_pk.slice('discord:'.length)
      } else if (grantee_mapped_pk.startsWith('authentik:')) {
        grantee_authentik_sub = grantee_mapped_pk.slice('authentik:'.length)
      }
      await createGrantApi({
        athlete_mapped_pk: mapped_pk,
        grantee_mapped_pk,
        grantee_nickname: granteeNickname.trim() || undefined,
        grantee_discord_id,
        grantee_authentik_sub,
        grant_type: grantType,
        scope,
        tied_competition_ids: tied.length ? tied : undefined,
        note: note.trim() || undefined,
      })
      close()
      setGranteeInput('')
      setGranteeNickname('')
      setTiedCompetitionIds('')
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
      await revokeGrantApi({ athlete_mapped_pk: g.athlete_mapped_pk, sk: g.sk })
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to revoke grant')
    }
  }

  const sorted = useMemo(
    () => [...grants].sort((a, b) => b.created_at.localeCompare(a.created_at)),
    [grants],
  )

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
        {canManage && (
          <Button leftSection={<UserPlus size={16} />} onClick={open} data-testid="open-grant-modal">
            New grant
          </Button>
        )}
      </Group>

      <Text size="sm" c="dimmed">
        Grant a coach or handler time-bound access to your training data. Grants auto-expire;
        you can revoke them at any time.
      </Text>

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
            label="Grantee mapped pk (or discord:/authentik: sub)"
            placeholder="discord:1234567890 or authentik:abc-def or coach_username"
            value={granteeInput}
            onChange={(e) => setGranteeInput(e.currentTarget.value)}
            required
            data-testid="grant-grantee-input"
          />
          <TextInput
            label="Grantee nickname (optional)"
            value={granteeNickname}
            onChange={(e) => setGranteeNickname(e.currentTarget.value)}
          />
          <Select
            label="Grant type"
            data={[
              { value: 'coach', label: 'Coach (read-only access to programming)' },
              { value: 'handler', label: "Handler (can edit sessions on the athlete's behalf)" },
            ]}
            value={grantType}
            onChange={(v) => setGrantType((v as GrantType) ?? 'coach')}
            allowDeselect={false}
          />
          <Select
            label="Scope"
            data={[
              { value: 'read', label: 'Read' },
              { value: 'write', label: 'Write' },
            ]}
            value={scope}
            onChange={(v) => setScope((v as GrantScope) ?? 'read')}
            allowDeselect={false}
          />
          <TextInput
            label="Tied competition IDs (comma-separated, optional)"
            placeholder="ipf-worlds-2026,wpc-bench-2026"
            value={tiedCompetitionIds}
            onChange={(e) => setTiedCompetitionIds(e.currentTarget.value)}
          />
          <Textarea
            label="Note (optional)"
            value={note}
            onChange={(e) => setNote(e.currentTarget.value)}
            minRows={2}
            maxRows={4}
          />
          <Group justify="flex-end">
            <Button variant="default" onClick={close}>Cancel</Button>
            <Button onClick={submit} loading={submitting} disabled={!granteeInput.trim()}>
              Create grant
            </Button>
          </Group>
        </Stack>
      </Modal>
    </Stack>
  )
}
