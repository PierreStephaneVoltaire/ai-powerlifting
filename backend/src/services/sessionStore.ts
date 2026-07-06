import { invokeLambda } from '../utils/lambda'
import type { Phase, Session } from '@powerlifting/types'

// ─── Fission shim ───────────────────────────────────────────────────────────
//
// Sessions are owned by the `session_*` Fission functions (layer pl_sessions /
// session_store), which perform ALL DynamoDB work against the if-sessions table
// (program#current pointer resolution, phase loading, SK construction,
// same-day ordinals, buildItem/publicSession).
//
// This file is now a thin delegating shim kept ONLY so that other controllers
// not yet refactored (videoController, programController) keep compiling with
// their existing imports. It contains NO DynamoDB logic — every call forwards
// to Fission with the caller's `programSk` (those controllers still resolve a
// versioned programSk themselves; the session controller itself no longer uses
// this file). The `phases` arguments are ignored here because the Fission store
// loads phases from the program item itself.

export function transformVideo(video: any): any {
  // Videos are served directly from CloudFront by the frontend, which resolves
  // s3_key / thumbnail_s3_key into full URLs at render time. No transform needed.
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
