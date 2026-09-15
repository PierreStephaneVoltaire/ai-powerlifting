import { useEffect, useState } from 'react'
import { Alert, Button, Group } from '@mantine/core'
import type { Program } from '@powerlifting/types'
import { useAuth } from '@/auth/AuthProvider'
import { useProgramStore } from '@/store/programStore'
import { readDraft, removeDraft, saveDraft, type Draft } from '@/api/drafts'
import { requestPartition } from '@/api/context'

export default function ProgramDraftNotice() {
  const { person_pk, mapped_pk, permissions, offline } = useAuth()
  const { version, program } = useProgramStore()
  const [draft, setDraft] = useState<Draft<Program> | undefined>()
  const [error, setError] = useState('')
  useEffect(() => {
    let current = true
    void readDraft<Program>(`program:${version}`).then(value => { if (current) setDraft(value) }).catch(() => {})
    return () => { current = false }
  }, [person_pk, mapped_pk, version])
  useEffect(() => useProgramStore.subscribe((state, previous) => {
    if (!person_pk || !state.isDirty || !state.program || state.program === previous.program) return
    const partition = requestPartition()
    void saveDraft(`program:${state.version}`, state.program, partition).catch(() => setError('Your browser could not save this draft. Keep this page open.'))
  }), [person_pk, mapped_pk])
  if (error) return <Alert color="red">{error}</Alert>
  if (!draft || !program || !permissions.includes('sessions:write')) return null
  return <Alert mb="md" title="An unsaved draft belongs to this Athlete">
    Saved {new Date(draft.updated_at).toLocaleString()}{offline ? ' while offline' : ''}. Restoring keeps its original revisions; changed server records require conflict resolution.
    <Group mt="xs"><Button onClick={() => { useProgramStore.setState({ program: draft.value, isDirty: true }); setDraft(undefined) }}>Restore draft</Button><Button variant="default" onClick={async () => { await removeDraft(`program:${version}`); setDraft(undefined) }}>Discard draft</Button></Group>
  </Alert>
}
