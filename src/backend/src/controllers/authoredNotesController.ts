import { invokeLambda } from '../utils/lambda'
import type { NoteAttachment, NoteContextDomain, NoteMutation, PrivateNote } from '@powerlifting/types'
export type { NoteAttachment, NoteContextDomain, NoteMutation, PrivateNote }

export async function listPrivateNotes(): Promise<{ notes: PrivateNote[]; next_cursor: string | null }> {
  const result = await invokeLambda('pod_authored_notes', { function: 'note_list_private' })
  return { notes: Array.isArray(result?.notes) ? result.notes as PrivateNote[] : [], next_cursor: result?.next_cursor ?? null }
}

export async function savePrivateNote(note: NoteMutation): Promise<PrivateNote> {
  const result = await invokeLambda('pod_authored_notes', { function: 'note_save_private', ...note })
  return result.note as PrivateNote
}

export async function listAttachments(context_domain: NoteContextDomain, context_id?: string): Promise<{ attachments: NoteAttachment[]; next_cursor: string | null }> {
  const result = await invokeLambda('pod_authored_notes', { function: 'note_list_attachments', context_domain, ...(context_id ? { context_id } : {}) })
  return { attachments: Array.isArray(result?.attachments) ? result.attachments as NoteAttachment[] : [], next_cursor: result?.next_cursor ?? null }
}

export async function shareNote(input: { note_id: string; wanted_revision: number; context_domain: NoteContextDomain; context_id?: string; expected_attachment_revision: number; idempotency_key: string }): Promise<NoteAttachment> {
  const result = await invokeLambda('pod_authored_notes', { function: 'note_share', ...input })
  return result.attachment as NoteAttachment
}

export async function detachNote(input: { attachment_id: string; expected_attachment_revision: number; idempotency_key: string }): Promise<{ attachment_id: string; detached: true; revision: number }> {
  return invokeLambda('pod_authored_notes', { function: 'note_detach', ...input })
}
