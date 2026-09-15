import { useEffect, useState } from 'react'
import { Alert, Button, Checkbox, Group, Stack, Text, Title } from '@mantine/core'
import api from '@/api/http'
import { useAuth } from '@/auth/AuthProvider'
import { readDraft, removeDraft, saveDraft } from '@/api/drafts'

const domains = [
  ['program', 'Program, Blocks and Program notes'], ['sessions', 'Sessions and training logs'],
  ['competition', 'Competition Entries and Attempts'], ['performance', 'Maxes and max history'],
  ['weight-log', 'Body measurements and weight history'], ['lift-profiles', 'Lift profiles'],
  ['analytics', 'Analysis and reports'], ['videos', 'Training videos'], ['goals', 'Goals'],
  ['budget', 'Competition budget'], ['glossary', 'Exercise library'], ['templates', 'Templates'],
  ['federation', 'Federation library'], ['imports', 'Imported training files'],
] as const
interface Publication { domains: string[]; revision: number }
interface PublicationMutation { domains: string[]; expected_revision: number; idempotency_key: string }
interface PublicationDraft { current: Publication; selected: string[]; pending: PublicationMutation | null }

export default function PublicationSettings() {
  const { user } = useAuth()
  const [current, setCurrent] = useState<Publication | null>(null)
  const [selected, setSelected] = useState<string[]>([])
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  const [pending, setPending] = useState<PublicationMutation | null>(null)
  const load = async () => {
    try {
      const response = await api.get('/settings/publication')
      setCurrent(response.data.data)
      setSelected(response.data.data.domains)
      setPending(null)
      setError('')
    } catch { setError('Could not load publication settings. Your selections are preserved.') }
  }
  useEffect(() => {
    void readDraft<PublicationDraft>('publication-form').then(draft => {
      if (!draft) return load()
      setCurrent(draft.value.current)
      setSelected(draft.value.selected)
      setPending(draft.value.pending)
      setError('Your unsent publication choices were restored. Save when connected, or reload to discard them.')
    }).catch(() => void load())
  }, [])
  useEffect(() => {
    if (!current) return
    const changed = JSON.stringify([...selected].sort()) !== JSON.stringify([...current.domains].sort())
    void (changed || pending ? saveDraft('publication-form', { current, selected, pending } satisfies PublicationDraft) : removeDraft('publication-form')).catch(() => setError('Your browser could not preserve these choices. Keep this page open.'))
  }, [current, selected, pending])
  if (!user?.roles.includes('athlete')) return null
  const save = async () => {
    if (!current) return
    if (!navigator.onLine) { setError('Connect to publish changes. Your selections are preserved.'); return }
    setSaving(true)
    const payload = pending || { domains: selected, expected_revision: current.revision, idempotency_key: crypto.randomUUID() }
    setPending(payload)
    try {
      const response = await api.put('/settings/publication', payload)
      setCurrent(response.data.data)
      setSelected(response.data.data.domains)
      setPending(null)
      setError('')
    } catch (cause: any) { setError(cause.response?.data?.error?.message || cause.response?.data?.message || 'Publication was not confirmed. Retry, or reload if it changed elsewhere.') }
    finally { setSaving(false) }
  }
  return <Stack gap="sm">
    <Title order={4}>Published training domains</Title>
    <Text size="sm">When your profile is public, anyone can read the domains you select. Your display name, avatar, federations and approved tags form the public profile. Account details and private author originals stay private.</Text>
    <Checkbox.Group value={selected} onChange={values => { setSelected(values); setPending(null) }}>
      <Stack gap="xs">{domains.map(([value, label]) => <Checkbox key={value} value={value} label={label} disabled={saving || !current} />)}</Stack>
    </Checkbox.Group>
    {error && <Alert color="red">{error}</Alert>}
    <Group><Button onClick={save} loading={saving} disabled={!current}>Save publication</Button><Button variant="default" onClick={load} disabled={saving}>Reload publication</Button></Group>
  </Stack>
}
