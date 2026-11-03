import { useEffect, useState } from 'react'
import { Alert, Autocomplete, Badge, Button, Group, Loader, Modal, Stack, Text } from '@mantine/core'
import api from '@/api/http'
import { addTag, removeTag, type UserSettings } from '@/api/settings'

interface CatalogTag { tag: string; status: 'approved' | 'pending' | 'rejected' }

export default function ProfileTags({ settings, onChange }: { settings: UserSettings | null; onChange: (settings: UserSettings) => void }) {
  const [catalog, setCatalog] = useState<CatalogTag[]>([])
  const [name, setName] = useState('')
  const [busy, setBusy] = useState(false)
  const [loaded, setLoaded] = useState(false)
  const [error, setError] = useState('')
  const [pickerOpen, setPickerOpen] = useState(false)

  async function load() {
    const response = await api.get<{ data: CatalogTag[] }>('/profiles/tags')
    setCatalog(response.data.data)
    setLoaded(true)
  }

  useEffect(() => { load().catch(() => setError('The tag catalog could not be loaded.')) }, [])

  async function run(action: () => Promise<unknown>) {
    setBusy(true)
    setError('')
    try { await action(); await load() }
    catch (cause: any) { setError(cause.response?.data?.error || cause.message || 'Tag changes could not be saved.') }
    finally { setBusy(false) }
  }

  const approved = new Set(catalog.filter(tag => tag.status === 'approved').map(tag => tag.tag))
  const shown = (settings?.tags || []).filter(tag => approved.has(tag.tag))
  return <Stack gap="sm">
    <Text fw={600}>Profile tags</Text>
    {error && <Alert color="red">{error} <Button variant="subtle" onClick={() => run(load)}>Retry</Button></Alert>}
    {!loaded && !error && <Loader size="sm" aria-label="Loading tag catalog" />}
    {loaded && <>
      <Group gap="xs">
        {shown.map(tag => <Group gap={4} key={tag.tag}>
          <Badge color="blue">{tag.tag}</Badge>
          <Button size="compact-sm" mih={44} variant="subtle" aria-label={`Remove ${tag.tag}`} disabled={busy} onClick={() => run(async () => onChange(await removeTag(tag.tag)))}>Remove</Button>
        </Group>)}
      </Group>
      {shown.length === 0 && <Text size="sm" c="dimmed">Choose a tag or suggest a new one. You can keep up to twenty.</Text>}
      <Button mih={44} variant="light" onClick={() => setPickerOpen(true)} disabled={busy || !settings} aria-label="Add profile tag">+ Add tag</Button>
      <Modal opened={pickerOpen} onClose={() => setPickerOpen(false)} title="Add profile tag" centered>
        <Stack>
          <Autocomplete label="Tag" data={[...approved]} value={name} onChange={setName} disabled={busy} />
          <Button mih={44} disabled={busy || !name.trim() || !settings} onClick={() => run(async () => { onChange(await addTag(name.trim())); setName(''); setPickerOpen(false) })}>Add tag</Button>
        </Stack>
      </Modal>
    </>}
  </Stack>
}
