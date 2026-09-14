import { operationScope } from './operationScope'
import { randomUUID } from 'crypto'
import { invokeLambda, pollJob } from './lambda'

const IF_API_URL = process.env.IF_API_URL || 'http://if-agent-api.if-portals.svc.cluster.local:8000'
const INTERNAL_API_TOKEN = process.env.INTERNAL_API_TOKEN || ''

async function invokeInference(payload: Record<string, unknown>, conversationId: string): Promise<any> {
  if (!INTERNAL_API_TOKEN) throw new Error('INTERNAL_API_TOKEN is not set')
  const scope = operationScope.getStore()
  if (!scope?.athlete || !scope.person) throw new Error('Authenticated scope is required for inference')
  if (scope.ifJobId) throw new Error('Active domain work must use native continuation, not submit another conversation')
  const conversation = `powerlifting:${scope.athlete}:${conversationId || randomUUID()}`
  const response = await fetch(`${IF_API_URL}/v1/conversations/${encodeURIComponent(conversation)}/turns`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Internal-Token': INTERNAL_API_TOKEN, 'X-Person-Pk': scope.person },
    body: JSON.stringify({ messages: payload.messages, specialist: payload.specialist, model: 'gpt-5.6-sol', idempotency_key: randomUUID() }),
  })
  if (!response.ok) throw new Error(`IF job submission failed ${response.status}: ${await response.text()}`)
  const job: any = await response.json()
  return pollJob(job.job_id, 'inference', scope.person)
}

export function invokeToolDirect(toolName: string, args: Record<string, unknown>): Promise<any> {
  return invokeLambda(toolName, args)
}

export function invokeSpecialistJson(specialist: string, task: string, chatId?: string, useHealthHelperModel = false): Promise<any> {
  return invokeInference({ specialist, messages: [{ role: 'user', content: `Use the named Specialist for this task and return only valid JSON.\n${task}` }], ...(useHealthHelperModel ? { metadata: { use_health_helper_model: true } } : {}) }, chatId || '')
}
