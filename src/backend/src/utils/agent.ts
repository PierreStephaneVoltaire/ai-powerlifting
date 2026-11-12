import { operationScope } from './operationScope'
import { randomUUID } from 'crypto'
import { callOperation, pollJob } from './operations'
import { coachUrl } from './coachUrl'
import { serviceHeaders } from '../auth/principal'
import type { OperationContext } from './operationScope'


async function invokeInference(payload: Record<string, unknown>, conversationId: string): Promise<any> {
  const scope = operationScope.getStore()
  if (!scope?.athlete || !scope.person) throw new Error('Authenticated scope is required for inference')
  if (scope.ifJobId) throw new Error('Active domain work must use native continuation, not submit another conversation')
  const conversation = `powerlifting:${scope.athlete}:${conversationId || randomUUID()}`
  const response = await fetch(`${coachUrl()}/v1/conversations/${encodeURIComponent(conversation)}/turns`, {
    method: 'POST',
    headers: await serviceHeaders('conversation_turn', scope, 'pl-coach'),
    body: JSON.stringify({ athlete: scope.athlete, messages: payload.messages, specialist: payload.specialist, model: 'gpt-5.6-sol' }),
  })
  if (!response.ok) throw new Error(`IF job submission failed ${response.status}: ${await response.text()}`)
  const job: any = await response.json()
  return pollJob(job.job_id, 'inference', scope.person)
}

function coachScope(): OperationContext {
  const scope = operationScope.getStore()
  if (!scope?.athlete || !scope.person) throw new Error('Authenticated scope is required for chat')
  return scope
}

export async function coachChat(conversationId: string, message: string, binding?: { surface: string; template_sk: string }): Promise<unknown> {
  const scope = coachScope()
  const { person } = scope
  const response = await fetch(`${coachUrl()}/v1/conversations/${encodeURIComponent(conversationId)}/turns`, {
    method: 'POST',
    headers: await serviceHeaders('conversation_turn', scope, 'pl-coach'),
    body: JSON.stringify({ athlete: scope.athlete, messages: [{ role: 'user', content: message }], ...(binding || {}) }),
  })
  if (!response.ok) throw new Error(`Chat submission failed ${response.status}: ${await response.text()}`)
  const job: any = await response.json()
  return pollJob(job.job_id, 'chat', person)
}

export async function resetCoachChat(conversationId: string): Promise<void> {
  const scope = coachScope()
  const { person } = scope
  const response = await fetch(`${coachUrl()}/v1/conversations/${encodeURIComponent(conversationId)}`, {
    method: 'DELETE',
    headers: await serviceHeaders('conversation_reset', scope, 'pl-coach'),
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
