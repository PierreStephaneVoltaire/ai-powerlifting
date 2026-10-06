import { useCallback, useEffect, useState } from 'react'
import { Alert, Button, Group, Modal, Stack, Text, Textarea } from '@mantine/core'
import { listMutations, removeMutation, resolveMutation, type PendingMutation } from '@/api/drafts'
import { synchronizeOfflineQueue } from '@/api/offlineQueue'
import { requestPartition } from '@/api/context'

function loadQueue(): Promise<PendingMutation[]> { return listMutations(requestPartition()) }
function content(record: PendingMutation): Record<string, unknown> {
  const { expected_revision: _revision, idempotency_key: _key, ...fields } = record.data as Record<string, unknown>
  return fields
}

export default function OfflineQueueNotice() {
  const [records, setRecords] = useState<PendingMutation[]>([])
  const [editing, setEditing] = useState<PendingMutation | null>(null)
  const [changes, setChanges] = useState('')
  const [error, setError] = useState('')
  const refresh = useCallback(() => { void loadQueue().then(setRecords).catch(() => {}) }, [])
  useEffect(() => {
    refresh()
    window.addEventListener('powerlifting-queue-changed', refresh)
    window.addEventListener('online', refresh)
    return () => {
      window.removeEventListener('powerlifting-queue-changed', refresh)
      window.removeEventListener('online', refresh)
    }
  }, [refresh])
  const conflicts = records.filter(record => record.status === 'conflict')
  if (!conflicts.length && !editing) return null
  return <Stack gap="xs" mb="md">
    {conflicts.map(record => <Alert key={record.id} color="orange" title="A saved change needs review">
      <Text size="sm">This record changed on the server. Compare your saved changes with the current record before deciding what to keep.</Text>
      <details><summary>Show differences</summary><pre style={{ whiteSpace: 'pre-wrap' }}>{JSON.stringify({ local: content(record), server: record.conflict?.current_record }, null, 2)}</pre></details>
      <Group mt="xs"><Button size="xs" onClick={() => { void removeMutation(record.id) }}>Keep server</Button><Button size="xs" variant="default" onClick={() => { setEditing(record); setChanges(JSON.stringify(content(record), null, 2)); setError('') }}>Review local</Button></Group>
    </Alert>)}
    <Modal opened={Boolean(editing)} onClose={() => setEditing(null)} title="Review conflicting changes" size="lg">
      <Stack>
        <Text size="sm">Keep any newer logged work from the server in your revised changes. Saving submits only after your access is checked again.</Text>
        <details open><summary>Current server record</summary><pre style={{ whiteSpace: 'pre-wrap' }}>{JSON.stringify(editing?.conflict?.current_record, null, 2)}</pre></details>
        <Textarea label="Your revised changes (JSON)" value={changes} onChange={event => setChanges(event.currentTarget.value)} autosize minRows={8} />
        {error && <Alert color="red">{error}</Alert>}
        <Button disabled={!Number.isInteger(editing?.conflict?.current_revision)} onClick={async () => {
          if (!editing) return
          try {
            const fields: unknown = JSON.parse(changes)
            if (!fields || typeof fields !== 'object' || Array.isArray(fields)) throw new Error('Changes must be a JSON object')
            await resolveMutation(editing, fields as Record<string, unknown>)
            setEditing(null)
            await synchronizeOfflineQueue()
          } catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not save these changes') }
        }}>Save reviewed changes</Button>
        {!Number.isInteger(editing?.conflict?.current_revision) && <Text size="sm">Reopen the original editor to fetch the latest record before applying your saved changes.</Text>}
      </Stack>
    </Modal>
  </Stack>
}
