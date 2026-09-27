import { useEffect, useState } from 'react'
import { Alert, Autocomplete, Badge, Button, Group, Loader, Modal, Stack, Text } from '@mantine/core'
import api from '@/api/http'
import { addTag, removeTag, type UserSettings } from '@/api/settings'
import { useAuth } from '@/auth/AuthProvider'

interface CatalogTag { tag: string; status: 'approved' | 'pending' | 'rejected'; revision: number }

export default function ProfileTags({ settings, onChange }: { settings: UserSettings | null; onChange: (settings: UserSettings) => void }) {
  const { permissions } = useAuth()
  const operator = permissions.includes('operator:write')
  const [catalog, setCatalog] = useState<CatalogTag[]>([])
  const [name, setName] = useState('')
  const [busy, setBusy] = useState(false)
  const [loaded, setLoaded] = useState(false)
  const [error, setError] = useState('')
  const [pickerOpen, setPickerOpen] = useState(false)
  const [pendingRequest, setPendingRequest] = useState('')

  async function load() {
    const response = await api.get<{ data: CatalogTag[] }>(`/profiles/tags?review=${operator}`)
    setCatalog(response.data.data)
    setLoaded(true)
  }

  useEffect(() => { load().catch(() => setError('The tag catalog could not be loaded.')) }, [operator])

  async function run(action: () => Promise<unknown>) {
    setBusy(true)
    setError('')
    try { await action(); await load() }
    catch (cause: any) { setError(cause.response?.data?.error || cause.message || 'Tag changes could not be saved.') }
    finally { setBusy(false) }
  }

  const approved = new Set(catalog.filter(tag => tag.status === 'approved').map(tag => tag.tag))
  const pending = [...(pendingRequest ? [pendingRequest] : []), ...(settings?.tags || []).filter(tag => (tag as typeof tag & { status?: string }).status === 'pending').map(tag => tag.tag)].filter((tag, index, all) => all.indexOf(tag) === index)
  return <Stack gap="sm">
    <Text fw={600}>Profile tags</Text>
    {error && <Alert color="red">{error} <Button variant="subtle" onClick={() => run(load)}>Retry</Button></Alert>}
    {!loaded && !error && <Loader size="sm" aria-label="Loading tag catalog" />}
    {loaded && <>
      <Group gap="xs">
        {(settings?.tags || []).filter(tag => approved.has(tag.tag)).map(tag => <Group gap={4} key={tag.tag}>
          <Badge color="blue">{tag.tag}</Badge>
          <Button size="compact-sm" mih={44} variant="subtle" aria-label={`Remove ${tag.tag}`} disabled={busy} onClick={() => run(async () => onChange(await removeTag(tag.tag)))}>Remove</Button>
        </Group>)}
      </Group>
      {!(settings?.tags.length) && <Text size="sm" c="dimmed">Select approved tags or request a new name. You can keep up to twenty.</Text>}
      <Button mih={44} variant="light" onClick={() => setPickerOpen(true)} disabled={busy || !settings} aria-label="Add profile tag">+ Add tag</Button>
      <Modal opened={pickerOpen} onClose={() => setPickerOpen(false)} title="Add profile tag" centered>
        <Stack>
          <Autocomplete label="Choose or request a tag" description="Approved names are added now; new names are submitted for approval." data={[...approved]} value={name} onChange={setName} disabled={busy} />
          {pending.length > 0 && <Text size="sm" c="orange">Submitted and pending approval: {pending.join(', ')}</Text>}
          <Button mih={44} disabled={busy || !name.trim() || !settings} onClick={() => run(async () => { const requested = name.trim(); onChange(await addTag(requested)); if (!approved.has(requested)) setPendingRequest(requested); setName('') })}>{approved.has(name.trim()) ? 'Add approved tag' : 'Submit for approval'}</Button>
        </Stack>
      </Modal>
      {operator && <Stack gap="xs">
        <Text fw={600}>Catalog review</Text>
        {catalog.map(tag => <Group key={tag.tag} justify="space-between">
          <Text size="sm">{tag.tag} · {tag.status}</Text>
          <Group gap="xs">{(['approved', 'rejected'] as const).filter(decision => decision !== tag.status).map(decision => <Button key={decision} mih={44} size="xs" color={decision === 'approved' ? 'teal' : 'red'} disabled={busy} onClick={() => run(async () => { await api.post(`/settings/tags/${encodeURIComponent(tag.tag)}/approve`, { decision, expected_revision: tag.revision, idempotency_key: crypto.randomUUID() }) })}>{decision === 'approved' ? 'Approve' : 'Reject'}</Button>)}</Group>
        </Group>)}
      </Stack>}
    </>}
  </Stack>
}
