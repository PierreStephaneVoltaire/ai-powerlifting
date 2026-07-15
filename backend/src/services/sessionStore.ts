import { invokeLambda } from '../utils/lambda'
import type { Phase, Session } from '@powerlifting/types'


export function transformVideo(video: any): any {
  return video
}

export async function listSessions(pk: string, programSk: string, _phases?: Phase[]): Promise<Session[]> {
  const result = await invokeLambda('pod_sessions', { function: 'session_list_full',  pk, program_sk: programSk })
  return Array.isArray(result) ? (result as Session[]) : []
}

export async function createSession(
  pk: string,
  programSk: string,
  session: Session,
  _phases?: Phase[],
): Promise<Session> {
  return (await invokeLambda('pod_sessions', { function: 'session_create',  pk, program_sk: programSk, session })) as Session
}

export async function patchSessionAt(
  pk: string,
  programSk: string,
  date: string,
  index: number,
  patch: Partial<Session>,
  _phases?: Phase[],
): Promise<Session> {
  return (await invokeLambda('pod_sessions', { function: 'session_patch',  pk, program_sk: programSk, date, index, patch })) as Session
}

export async function patchSessionByDate(
  pk: string,
  programSk: string,
  date: string,
  patch: Partial<Session>,
  _phases?: Phase[],
): Promise<Session> {
  return (await invokeLambda('pod_sessions', { function: 'session_patch_by_date',  pk, program_sk: programSk, date, patch })) as Session
}

export async function replaceProgramSessions(
  pk: string,
  programSk: string,
  sessions: Session[],
  _phases?: Phase[],
): Promise<void> {
  await invokeLambda('pod_sessions', { function: 'session_replace_all',  pk, program_sk: programSk, sessions })
}
