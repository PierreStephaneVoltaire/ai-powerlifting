import { useEffect, useState } from 'react'
import { Alert, Badge, Button, Group, Loader, Select, Stack, Text, TextInput } from '@mantine/core'
import api from '@/api/http'
import { addTag, removeTag, type UserSettings } from '@/api/settings'
import { useAuth } from '@/auth/AuthProvider'

interface CatalogTag { tag: string; status: 'approved' | 'pending' | 'rejected'; revision: number }

export default function ProfileTags({ settings, onChange }: { settings: UserSettings | null; onChange: (settings: UserSettings) => void }) {
  const { permissions } = useAuth()
  const operator = permissions.includes('operator:write')
  const [catalog, setCatalog] = useState<CatalogTag[]>([])
  const [name, setName] = useState('')
  const [selected, setSelected] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [loaded, setLoaded] = useState(false)
  const [error, setError] = useState('')

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
  return <Stack gap="sm">
    <Text fw={600}>Profile tags</Text>
    {error && <Alert color="red">{error} <Button variant="subtle" onClick={() => run(load)}>Retry</Button></Alert>}
    {!loaded && !error && <Loader size="sm" aria-label="Loading tag catalog" />}
    {loaded && <>
      <Group gap="xs">
        {(settings?.tags || []).map(tag => <Group gap={4} key={tag.tag}>
          <Badge color={approved.has(tag.tag) ? 'blue' : 'orange'}>{tag.tag}{approved.has(tag.tag) ? '' : catalog.find(item => item.tag === tag.tag)?.status === 'rejected' ? ' · rejected' : ' · pending review'}</Badge>
          <Button size="compact-sm" mih={44} variant="subtle" aria-label={`Remove ${tag.tag}`} disabled={busy} onClick={() => run(async () => onChange(await removeTag(tag.tag)))}>Remove</Button>
        </Group>)}
      </Group>
      {!(settings?.tags.length) && <Text size="sm" c="dimmed">Select approved tags or request a new name. You can keep up to twenty.</Text>}
      <Group align="end">
        <Select label="Approved tags" data={[...approved]} searchable value={selected} onChange={setSelected} disabled={busy} />
        <Button mih={44} disabled={busy || !selected || !settings} onClick={() => run(async () => { onChange(await addTag(selected!)); setSelected(null) })}>Select</Button>
      </Group>
      <Group align="end">
        <TextInput label="Request a tag" description="New names need operator approval." maxLength={30} value={name} onChange={event => setName(event.currentTarget.value)} disabled={busy} />
        <Button mih={44} disabled={busy || !name.trim() || !settings} onClick={() => run(async () => { onChange(await addTag(name)); setName('') })}>Request</Button>
      </Group>
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
