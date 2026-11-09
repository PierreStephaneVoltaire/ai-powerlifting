import { operationScope } from './operationScope'
import { randomUUID } from 'crypto'
import { callOperation, pollJob } from './operations'
import { coachUrl } from './coachUrl'

const INTERNAL_API_TOKEN = process.env.INTERNAL_API_TOKEN || ''

async function invokeInference(payload: Record<string, unknown>, conversationId: string): Promise<any> {
  if (!INTERNAL_API_TOKEN) throw new Error('INTERNAL_API_TOKEN is not set')
  const scope = operationScope.getStore()
  if (!scope?.athlete || !scope.person) throw new Error('Authenticated scope is required for inference')
  if (scope.ifJobId) throw new Error('Active domain work must use native continuation, not submit another conversation')
  const conversation = `powerlifting:${scope.athlete}:${conversationId || randomUUID()}`
  const response = await fetch(`${coachUrl()}/v1/conversations/${encodeURIComponent(conversation)}/turns`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Internal-Token': INTERNAL_API_TOKEN, 'X-Person-Pk': scope.person },
    body: JSON.stringify({ messages: payload.messages, specialist: payload.specialist, model: 'gpt-5.6-sol' }),
  })
  if (!response.ok) throw new Error(`IF job submission failed ${response.status}: ${await response.text()}`)
  const job: any = await response.json()
  return pollJob(job.job_id, 'inference', scope.person)
}

function coachScope(): { athlete: string; person: string } {
  if (!INTERNAL_API_TOKEN) throw new Error('INTERNAL_API_TOKEN is not set')
  const scope = operationScope.getStore()
  if (!scope?.athlete || !scope.person) throw new Error('Authenticated scope is required for chat')
  return { athlete: scope.athlete, person: scope.person }
}

export async function coachChat(conversationId: string, message: string, binding?: { surface: string; template_sk: string }): Promise<unknown> {
  const { person } = coachScope()
  const response = await fetch(`${coachUrl()}/v1/conversations/${encodeURIComponent(conversationId)}/turns`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Internal-Token': INTERNAL_API_TOKEN, 'X-Person-Pk': person },
    body: JSON.stringify({ messages: [{ role: 'user', content: message }], ...(binding || {}) }),
  })
  if (!response.ok) throw new Error(`Chat submission failed ${response.status}: ${await response.text()}`)
  const job: any = await response.json()
  return pollJob(job.job_id, 'chat', person)
}

export async function resetCoachChat(conversationId: string): Promise<void> {
  const { person } = coachScope()
  const response = await fetch(`${coachUrl()}/v1/conversations/${encodeURIComponent(conversationId)}`, {
    method: 'DELETE',
    headers: { 'X-Internal-Token': INTERNAL_API_TOKEN, 'X-Person-Pk': person },
  })
  if (!response.ok) throw new Error(`Chat reset failed ${response.status}: ${await response.text()}`)
}

export function templateConversation(athlete: string, sk?: string, chatId?: string): string {
  return sk ? `powerlifting:${athlete}:template:${sk}` : `powerlifting:${athlete}:template-chat:${chatId}`
}

export function invokeToolDirect(toolName: string, args: Record<string, unknown>): Promise<any> {
  return callOperation(toolName, args)
}

export function invokeSpecialistJson(specialist: string, task: string, chatId?: string, useHealthHelperModel = false): Promise<any> {
  return invokeInference({ specialist, messages: [{ role: 'user', content: `Use the named Specialist for this task and return only valid JSON.\n${task}` }], ...(useHealthHelperModel ? { metadata: { use_health_helper_model: true } } : {}) }, chatId || '')
}
