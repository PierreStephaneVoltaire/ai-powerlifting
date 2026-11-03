import api from './http'
import type { NoteAttachment, NoteContextDomain, NoteMutation, PrivateNote } from '@powerlifting/types'
export type { NoteAttachment, NoteContextDomain, NoteMutation, PrivateNote }

export async function fetchPrivateNotes(cursor?: string): Promise<{ notes: PrivateNote[]; next_cursor: string | null }> {
  const response = await api.get<{ data: { notes: PrivateNote[]; next_cursor: string | null } }>('/authored-notes/private', { params: cursor ? { cursor } : undefined })
  return response.data.data
}

export async function savePrivateNote(input: NoteMutation): Promise<PrivateNote> {
  const response = await api.put<{ data: PrivateNote }>('/authored-notes/private', input)
  return response.data.data
}

export async function fetchAttachments(context_domain: NoteContextDomain): Promise<{ attachments: NoteAttachment[]; next_cursor: string | null }> {
  const response = await api.get<{ data: { attachments: NoteAttachment[]; next_cursor: string | null } }>(`/authored-notes/attachments/${context_domain}`)
  return response.data.data
}

export async function shareNote(input: { note_id: string; wanted_revision: number; context_domain: NoteContextDomain; context_id?: string; expected_attachment_revision: number; idempotency_key: string }): Promise<NoteAttachment> {
  const response = await api.post<{ data: NoteAttachment }>('/authored-notes/share', input)
  return response.data.data
}

export async function detachNote(input: { attachment_id: string; expected_attachment_revision: number; idempotency_key: string }): Promise<void> {
  await api.post('/authored-notes/detach', input)
}
