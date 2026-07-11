
const LAMBDA_BASE_URL = process.env.POWERLIFTING_LAMBDA_BASE_URL
const INTERNAL_API_TOKEN = process.env.INTERNAL_API_TOKEN || ''


export async function invokeLambda(
  functionName: string,
  args: Record<string, unknown>,
): Promise<any> {
  if (!LAMBDA_BASE_URL) {
    throw new Error(
      'POWERLIFTING_LAMBDA_BASE_URL is not set: cannot invoke Lambda tool over API Gateway HTTP endpoint',
    )
  }

  const response = await fetch(`${LAMBDA_BASE_URL}/${functionName}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(INTERNAL_API_TOKEN ? { 'X-Internal-Token': INTERNAL_API_TOKEN } : {}),
    },
    body: JSON.stringify(args),
  })

  if (!response.ok) {
    const text = await response.text()
    throw new Error(`Lambda tool error ${response.status} for ${functionName}: ${text}`)
  }

  const parsed: any = await response.json()

  if (parsed && typeof parsed === 'object' && 'body' in parsed) {
    const body = parsed.body
    if (typeof body === 'string' && body.length > 0) {
      try {
        return JSON.parse(body)
      } catch {
        return body
      }
    }
    return body
  }
  return parsed
}
