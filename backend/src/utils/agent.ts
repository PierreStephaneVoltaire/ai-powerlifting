const IF_API_URL = process.env.IF_API_URL || 'http://if-agent-api.if-portals.svc.cluster.local:8000'
const AGENT_MODEL = process.env.AGENT_MODEL || 'if-prototype'

type CompletionMessage = {
  role: 'system' | 'user' | 'assistant'
  content: string
}

type InvokeChatOptions = {
  chatId?: string
  metadata?: Record<string, unknown>
}

function extractJson(text: string): any {
  const match = text.match(/\{[\s\S]*\}|\[[\s\S]*\]/)
  if (!match) throw new Error(`No JSON in tool response: ${text.slice(0, 200)}`)
  return JSON.parse(match[0])
}

async function invokeChat(
  messages: CompletionMessage[],
  options: InvokeChatOptions = {},
): Promise<string> {
  const response = await fetch(`${IF_API_URL}/v1/chat/completions`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      model: AGENT_MODEL,
      messages,
      ...(options.chatId ? { chat_id: options.chatId } : {}),
      ...(options.metadata ? { metadata: options.metadata } : {}),
    }),
  })
  if (!response.ok) {
    const text = await response.text()
    throw new Error(`Agent API error ${response.status}: ${text}`)
  }
  const body: any = await response.json()
  return body?.choices?.[0]?.message?.content ?? ''
}

async function invokeRawTool(
  toolName: string,
  args: Record<string, unknown>,
): Promise<any> {
  const content = `/${toolName} ${JSON.stringify(args)}`
  const response = await fetch(`${IF_API_URL}/v1/chat/completions`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Direct-Tool-Invoke': 'true',
    },
    body: JSON.stringify({
      model: AGENT_MODEL,
      messages: [{ role: 'user', content }],
    }),
  })
  if (!response.ok) {
    const text = await response.text()
    throw new Error(`Agent API error ${response.status}: ${text}`)
  }
  const body: any = await response.json()
  const rawContent: string = body?.choices?.[0]?.message?.content ?? ''
  return extractJson(rawContent)
}

async function reloadIfTools(): Promise<void> {
  const response = await fetch(`${IF_API_URL}/admin/reload-tools`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
  })
  if (!response.ok) {
    const text = await response.text()
    throw new Error(`IF tool reload failed ${response.status}: ${text}`)
  }
}

export async function invokeToolDirect(
  toolName: string,
  args: Record<string, unknown>,
): Promise<any> {
  try {
    return await invokeRawTool(toolName, args)
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error)
    if (!message.includes(`Unknown tool: ${toolName}`)) {
      throw error
    }
  }

  await reloadIfTools()
  return invokeRawTool(toolName, args)
}

export async function invokeJsonCompletion(
  messages: CompletionMessage[],
  chatId?: string,
): Promise<any> {
  const content = await invokeChat(messages, { chatId })
  return extractJson(content)
}

export async function invokeSpecialistJson(
  specialist: string,
  task: string,
  chatId?: string,
  useHealthHelperModel = false,
): Promise<any> {
  const content = await invokeChat(
    [{ role: 'user', content: `/${specialist} ${task}` }],
    {
      chatId,
      ...(useHealthHelperModel ? { metadata: { use_health_helper_model: true } } : {}),
    },
  )
  return extractJson(content)
}
