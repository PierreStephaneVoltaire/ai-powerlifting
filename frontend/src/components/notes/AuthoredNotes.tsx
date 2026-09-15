import { useEffect, useMemo, useRef, useState } from 'react'
import { Alert, Badge, Button, Group, Paper, Select, Stack, Text, Textarea } from '@mantine/core'
import { useAuth } from '@/auth/AuthProvider'
import { readDraft, removeDraftIfMatch, saveDraft, type Draft } from '@/api/drafts'
import { requestPartition } from '@/api/context'
import { fetchAttachments, fetchPrivateNotes, savePrivateNote, shareNote, detachNote, type NoteAttachment, type NoteContextDomain, type NoteMutation, type PrivateNote } from '@/api/authoredNotes'
import { OfflineQueuedError } from '@/api/http'

const domains: NoteContextDomain[] = ['program', 'sessions', 'competition']
const newId = () => globalThis.crypto.randomUUID()
const newMutation = (note_id: string, text: string, expected_revision: number): NoteMutation => ({ note_id, text, expected_revision, idempotency_key: newId() })

export default function AuthoredNotes({ initialDomain }: { initialDomain?: NoteContextDomain }) {
  const { mapped_pk, own_athlete_pk, person_pk, permissions, user } = useAuth()
  const canEditPrivate = permissions.includes('settings:write')
  const canDetach = mapped_pk === own_athlete_pk && Boolean(user?.roles.includes('athlete'))
  const [notes, setNotes] = useState<PrivateNote[]>([])
  const [mutations, setMutations] = useState<Record<string, NoteMutation>>({})
  const [attachments, setAttachments] = useState<NoteAttachment[]>([])
  const [domain, setDomain] = useState<NoteContextDomain>(initialDomain ?? 'program')
  const [newDraft, setNewDraft] = useState(() => newMutation(newId(), '', 0))
  const [shareKeys, setShareKeys] = useState<Record<string, string>>({})
  const [conflict, setConflict] = useState<Record<string, unknown>>({})
  const [status, setStatus] = useState('')
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')
  const [newSaveError, setNewSaveError] = useState('')
  const [retry, setRetry] = useState(0)
  const contextKey = JSON.stringify([person_pk, mapped_pk, domain])
  const [loadedContextKey, setLoadedContextKey] = useState('')
  const refreshSequence = useRef(0)
  const contextRef = useRef(contextKey)
  const newDraftRef = useRef(newDraft)
  const notesRef = useRef(notes)
  const mutationsRef = useRef(mutations)
  const conflictRef = useRef(conflict)
  const draftWritesRef = useRef<Record<string, Promise<Draft<NoteMutation> | undefined>>>({})
  notesRef.current = notes
  mutationsRef.current = mutations
  conflictRef.current = conflict
  contextRef.current = contextKey

  const contextIsCurrent = (capturedContext: string, sequence?: number): boolean => capturedContext === contextRef.current && (sequence === undefined || sequence === refreshSequence.current)

  const attachmentByNote = useMemo(() => new Map(attachments.map(item => [item.note_id, item])), [attachments])

  useEffect(() => {
    const sequence = ++refreshSequence.current
    const partition = requestPartition()
    const isCurrent = () => contextIsCurrent(contextKey, sequence)
    setLoadedContextKey('')
    setNotes([])
    setMutations({})
    setAttachments([])
    setConflict({})
    setStatus('')
    setLoadError('')
    setNewSaveError('')
    const blankDraft = newMutation(newId(), '', 0)
    newDraftRef.current = blankDraft
    setNewDraft(blankDraft)
    if (!mapped_pk) { setLoading(false); setLoadedContextKey(contextKey); return }
    let active = true
    setLoading(true)
    const privateLoad = fetchPrivateNotes().then(async privateResult => {
      const records: Record<string, NoteMutation> = {}
      await Promise.all(privateResult.notes.map(async note => {
        const draft = await readDraft<NoteMutation>(`authored-note:${note.note_id}`, partition)
        records[note.note_id] = draft?.value ?? newMutation(note.note_id, note.text, note.revision)
      }))
      return { notes: privateResult.notes, mutations: records }
    }).catch(() => {
      if (active && isCurrent()) setLoadError('Could not load private notes.')
      return undefined
    })
    const attachmentLoad = fetchAttachments(domain).catch(() => {
      if (active && isCurrent()) setLoadError(previous => previous || 'Could not load attached notes.')
      return undefined
    })
    const newDraftLoad = readDraft<NoteMutation>('authored-note:new', partition).then(draft => draft?.value).catch(() => undefined)
    void Promise.all([privateLoad, attachmentLoad, newDraftLoad]).then(([privateResult, sharedResult, savedNewDraft]) => {
      if (!active || !isCurrent()) return
      if (privateResult) {
        notesRef.current = privateResult.notes
        mutationsRef.current = privateResult.mutations
        setNotes(privateResult.notes)
        setMutations(privateResult.mutations)
      }
      if (sharedResult) setAttachments(sharedResult.attachments)
      if (savedNewDraft) {
        newDraftRef.current = savedNewDraft
        setNewDraft(savedNewDraft)
      }
      setLoadedContextKey(contextKey)
      setLoading(false)
    })
    const refresh = () => {
      if (!navigator.onLine) return
      const nextSequence = ++refreshSequence.current
      void fetchPrivateNotes().then(privateResult => {
        if (!active || !contextIsCurrent(contextKey, nextSequence)) return
        const previousNotes = new Map(notesRef.current.map(note => [note.note_id, note]))
        const nextMutations = { ...mutationsRef.current }
        const nextConflicts = { ...conflictRef.current }
        for (const note of privateResult.notes) {
          const previous = previousNotes.get(note.note_id)
          const mutation = nextMutations[note.note_id]
          const localDirty = Boolean(mutation && previous && mutation.text !== previous.text)
          if (!mutation || !localDirty || mutation.text === note.text) {
            nextMutations[note.note_id] = newMutation(note.note_id, note.text, note.revision)
            delete nextConflicts[note.note_id]
          } else if (mutation.expected_revision !== note.revision) {
            nextConflicts[note.note_id] = note
          }
        }
        notesRef.current = privateResult.notes
        mutationsRef.current = nextMutations
        conflictRef.current = nextConflicts
        setNotes(privateResult.notes)
        setMutations(nextMutations)
        setConflict(nextConflicts)
      }).catch(() => { if (active && contextIsCurrent(contextKey, nextSequence)) setLoadError('Could not refresh private notes.') })
      void fetchAttachments(domain).then(sharedResult => {
        if (active && contextIsCurrent(contextKey, nextSequence)) setAttachments(sharedResult.attachments)
      }).catch(() => { if (active && contextIsCurrent(contextKey, nextSequence)) setLoadError('Could not refresh attached notes.') })
    }
    window.addEventListener('powerlifting-queue-changed', refresh)
    return () => { active = false; window.removeEventListener('powerlifting-queue-changed', refresh) }
  }, [contextKey, domain, mapped_pk, retry])

  function updateMutation(note: PrivateNote, text: string): void {
    const next = { ...(mutations[note.note_id] ?? newMutation(note.note_id, note.text, note.revision)), text }
    mutationsRef.current = { ...mutationsRef.current, [note.note_id]: next }
    setMutations(previous => ({ ...previous, [note.note_id]: next }))
    void queueDraftWrite(`authored-note:${note.note_id}`, next, requestPartition())
  }

  function queueDraftWrite(record: string, value: NoteMutation, partition: string): Promise<Draft<NoteMutation>> {
    const write = (draftWritesRef.current[record] ?? Promise.resolve(undefined)).then(() => saveDraft(record, value, partition))
    draftWritesRef.current[record] = write.catch(() => undefined)
    return write
  }

  async function save(note: PrivateNote): Promise<void> {
    if (!canEditPrivate) return
    const capturedContext = contextKey
    const mutation = mutations[note.note_id] ?? newMutation(note.note_id, note.text, note.revision)
    if (!mutation.text.trim()) return
    const partition = requestPartition()
    let draft: Draft<NoteMutation>
    try {
      draft = await queueDraftWrite(`authored-note:${note.note_id}`, mutation, partition)
      if (!contextIsCurrent(capturedContext)) return
      const saved = await savePrivateNote(mutation)
      if (!contextIsCurrent(capturedContext)) return
      setNotes(previous => previous.map(item => item.note_id === saved.note_id ? saved : item))
      const next = newMutation(saved.note_id, saved.text, saved.revision)
      if (mutationsRef.current[saved.note_id]?.idempotency_key === mutation.idempotency_key) {
        mutationsRef.current = { ...mutationsRef.current, [saved.note_id]: next }
        setMutations(previous => ({ ...previous, [saved.note_id]: next }))
        await removeDraftIfMatch(`authored-note:${saved.note_id}`, draft, partition)
        if (!contextIsCurrent(capturedContext)) return
        const nextConflicts = { ...conflictRef.current }
        delete nextConflicts[saved.note_id]
        conflictRef.current = nextConflicts
        setConflict(nextConflicts)
      }
      if (contextIsCurrent(capturedContext)) setStatus('Private note saved')
    } catch (error) {
      if (!contextIsCurrent(capturedContext)) return
      if (error instanceof OfflineQueuedError) { setStatus('Private note saved for when you reconnect'); return }
      const response = (error as { response?: { status?: number; data?: { current_record?: unknown } } }).response
      if (response?.status === 409) setConflict(previous => ({ ...previous, [note.note_id]: response.data?.current_record ?? 'The server has a newer revision.' }))
      else setStatus('Could not save private note')
    }
  }

  async function share(note: PrivateNote): Promise<void> {
    const capturedContext = contextKey
    if (!permissions.includes(`${domain}:write`)) { setStatus('You do not have permission to share in this context'); return }
    if (!navigator.onLine) { setStatus('Sharing requires a connection'); return }
    const current = attachmentByNote.get(note.note_id)
    const sharePayload = `${note.note_id}:${note.revision}:${domain}:${current?.revision ?? 0}`
    const idempotencyKey = shareKeys[sharePayload] ?? newId()
    if (!shareKeys[sharePayload]) setShareKeys(previous => ({ ...previous, [sharePayload]: idempotencyKey }))
    try {
      const shared = await shareNote({ note_id: note.note_id, wanted_revision: note.revision, context_domain: domain, expected_attachment_revision: current?.revision ?? 0, idempotency_key: idempotencyKey })
      if (!contextIsCurrent(capturedContext)) return
      setAttachments(previous => [...previous.filter(item => item.note_id !== shared.note_id), shared])
      setShareKeys(previous => { const next = { ...previous }; delete next[sharePayload]; return next })
      if (contextIsCurrent(capturedContext)) setStatus('Revision shared')
    } catch (error) {
      if (contextIsCurrent(capturedContext)) setStatus((error as { response?: { status?: number } }).response?.status === 409 ? 'Attachment changed; reload before sharing again' : 'Could not share note')
    }
  }

  async function detach(attachment: NoteAttachment): Promise<void> {
    if (!canDetach) return
    const capturedContext = contextKey
    try {
      await detachNote({ attachment_id: attachment.attachment_id, expected_attachment_revision: attachment.revision, idempotency_key: newId() })
      if (contextIsCurrent(capturedContext)) setAttachments(previous => previous.filter(item => item.attachment_id !== attachment.attachment_id))
    } catch { if (contextIsCurrent(capturedContext)) setStatus('Could not detach note') }
  }

  async function saveNew(mutation: NoteMutation): Promise<void> {
    const capturedContext = contextKey
    if (contextIsCurrent(capturedContext)) setNewSaveError('')
    const partition = requestPartition()
    try {
      const draft = await queueDraftWrite('authored-note:new', mutation, partition)
      const note = await savePrivateNote(mutation)
      if (!contextIsCurrent(capturedContext)) return
      setNotes(previous => [note, ...previous])
      if (newDraftRef.current.idempotency_key === mutation.idempotency_key) {
        const next = newMutation(newId(), '', 0)
        newDraftRef.current = next
        setNewDraft(next)
        await removeDraftIfMatch('authored-note:new', draft, partition)
        if (!contextIsCurrent(capturedContext)) return
      }
    } catch (error) {
      if (!contextIsCurrent(capturedContext)) return
      if (error instanceof OfflineQueuedError) setStatus('Private note saved for when you reconnect')
      else setNewSaveError('Could not save private note. Please retry.')
    }
  }

  return <Stack gap="md" data-testid="authored-notes">
    {loadedContextKey === contextKey && status && <Alert>{status}</Alert>}
    {loadedContextKey === contextKey && loadError && <Alert color="red">{loadError} <Button variant="subtle" onClick={() => setRetry(value => value + 1)}>Retry</Button></Alert>}
    {loading || loadedContextKey !== contextKey ? <Text c="dimmed">Loading notes…</Text> : notes.length === 0 ? <Text c="dimmed">No private notes yet.</Text> : notes.map(note => {
      const mutation = mutations[note.note_id] ?? newMutation(note.note_id, note.text, note.revision)
      const shared = attachmentByNote.get(note.note_id)
      return <Paper key={note.note_id} withBorder p="md">
        <Stack gap="xs">
          <Group justify="space-between"><Text fw={600}>Private original</Text><Badge>Revision {note.revision}</Badge></Group>
          <Textarea value={mutation.text} onChange={event => updateMutation(note, event.currentTarget.value)} autosize minRows={3} disabled={!canEditPrivate} />
          {Boolean(conflict[note.note_id]) && <Alert color="orange" title="Save conflict">Server copy: {JSON.stringify(conflict[note.note_id])}</Alert>}
          <Group>
            <Button onClick={() => void save(note)} disabled={!canEditPrivate}>Save private</Button>
            <Select value={domain} onChange={value => value && setDomain(value as NoteContextDomain)} data={domains} allowDeselect={false} w={150} />
            <Button variant="light" onClick={() => void share(note)} disabled={!permissions.includes(`${domain}:write`)}>Share revision</Button>
            {shared && <Text size="xs" c="dimmed">Attached revision {shared.revision}</Text>}
          </Group>
        </Stack>
      </Paper>
    })}
    {canEditPrivate && loadedContextKey === contextKey && <NewNote mutation={newDraft} error={newSaveError} onChange={next => { const partition = requestPartition(); newDraftRef.current = next; setNewDraft(next); void queueDraftWrite('authored-note:new', next, partition) }} onSave={saveNew} />}
    <Stack gap="sm"><Text fw={600}>Attached notes</Text>{loading || loadedContextKey !== contextKey ? <Text c="dimmed">Loading attached notes…</Text> : attachments.length === 0 ? <Text c="dimmed">No attached notes yet.</Text> : attachments.map(attachment => <Paper key={attachment.attachment_id} withBorder p="md"><Stack gap="xs"><Text style={{ whiteSpace: 'pre-wrap' }}>{attachment.text}</Text><Text size="xs" c="dimmed">Author {attachment.author_person_pk} · source revision {attachment.source_revision}</Text><Button variant="subtle" onClick={() => void detach(attachment)} disabled={!canDetach}>Detach</Button></Stack></Paper>)}</Stack>
  </Stack>
}

function NewNote({ mutation, error, onChange, onSave }: { mutation: NoteMutation; error: string; onChange: (mutation: NoteMutation) => void; onSave: (mutation: NoteMutation) => Promise<void> }) {
  return <Paper withBorder p="md"><Stack gap="xs"><Text fw={600}>New private original</Text>{error && <Alert color="red">{error}</Alert>}<Textarea value={mutation.text} onChange={event => onChange({ ...mutation, text: event.currentTarget.value })} autosize minRows={3} /><Button disabled={!mutation.text.trim()} onClick={() => void onSave(mutation)}>Save private note</Button></Stack></Paper>
}
