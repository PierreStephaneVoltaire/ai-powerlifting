import { operationScope } from './operationScope'
import { randomUUID } from 'crypto'
import { callOperation, pollJob } from './operations'
import { assistantUrl } from './coachUrl'
import { serviceHeaders } from './serviceHeaders'
import type { OperationContext } from './operationScope'


async function invokeInference(payload: Record<string, unknown>, conversationId: string): Promise<any> {
  const scope = operationScope.getStore()
  if (!scope?.athlete || !scope.person) throw new Error('Authenticated scope is required for inference')
  if (scope.ifJobId) throw new Error('Active domain work must use native continuation, not submit another conversation')
  const conversation = `powerlifting:${scope.athlete}:web:${scope.person}:agent-${conversationId || randomUUID()}`
  const response = await fetch(`${assistantUrl()}/v1/conversations/${encodeURIComponent(conversation)}/turns`, {
    method: 'POST',
    headers: serviceHeaders(scope),
    body: JSON.stringify({ athlete: scope.athlete, messages: payload.messages }),
  })
  if (!response.ok) throw new Error(`Assistant job submission failed ${response.status}: ${await response.text()}`)
  const job: any = await response.json()
  return pollJob(job.job_id, 'inference', scope.person, scope.athlete, assistantUrl())
}

function coachScope(): OperationContext {
  const scope = operationScope.getStore()
  if (!scope?.athlete || !scope.person) throw new Error('Authenticated scope is required for chat')
  return scope
}

export async function coachChat(conversationId: string, message: string, binding?: { surface: string; template_sk: string }): Promise<unknown> {
  const scope = coachScope()
  const { person } = scope
  const response = await fetch(`${assistantUrl()}/v1/conversations/${encodeURIComponent(conversationId)}/turns`, {
    method: 'POST',
    headers: serviceHeaders(scope),
    body: JSON.stringify({
      athlete: scope.athlete,
      messages: [{ role: 'user', content: message }],
      ...(binding ? { surface: binding.surface, context: { template_sk: binding.template_sk } } : {}),
    }),
  })
  if (!response.ok) throw new Error(`Chat submission failed ${response.status}: ${await response.text()}`)
  const job: any = await response.json()
  return pollJob(job.job_id, 'chat', person, scope.athlete, assistantUrl())
}

export function templateConversation(athlete: string, person: string, sk?: string, chatId?: string): string {
  return `powerlifting:${athlete}:web:${person}:${sk ? `template:${sk}` : `template-chat:${chatId}`}`
}

export function invokeToolDirect(toolName: string, args: Record<string, unknown>): Promise<any> {
  return callOperation(toolName, args)
}

export function invokeSpecialistJson(specialist: string, task: string, chatId?: string, useHealthHelperModel = false): Promise<any> {
  return invokeInference({ specialist, messages: [{ role: 'user', content: `Use the named Specialist for this task and return only valid JSON.\n${task}` }], ...(useHealthHelperModel ? { metadata: { use_health_helper_model: true } } : {}) }, chatId || '')
}
