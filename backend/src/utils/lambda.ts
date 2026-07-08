// ─── Lambda / Fission invocation (HTTP path) ────────────────────────────────
// The powerlifting tools are exposed as POST `/{tool}` on the configured
// runtime substrate. In production the substrate is the in-cluster Fission
// router (`http://router.fission.svc.cluster.local:80`). During the migration
// the same code works against the AWS API Gateway HTTP endpoint by changing
// the `POWERLIFTING_LAMBDA_BASE_URL` env var.
const LAMBDA_BASE_URL = process.env.POWERLIFTING_LAMBDA_BASE_URL
const INTERNAL_API_TOKEN = process.env.INTERNAL_API_TOKEN || ''

/**
 * Invoke a Phase 2 powerlifting tool through its API Gateway HTTP route.
 *
 * `functionName` is the endpoint name (e.g. `pod_sessions`). The request
 * is a POST to `${POWERLIFTING_LAMBDA_BASE_URL}/${functionName}` with the tool
 * arguments JSON-encoded as the request body and a `Content-Type: application/json`
 * header.
 */
export async function invokeLambda(
  functionName: string,
  args: Record<string, unknown>,
): Promise<any> {
  if (!LAMBDA_BASE_URL) {
    throw new Error(
      'POWERLIFTING_LAMBDA_BASE_URL is not set: cannot invoke Lambda tool over API Gateway HTTP endpoint',
    )
  }

  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), Number(process.env.POWERLIFTING_LAMBDA_TIMEOUT_MS || 15000))

  let response: Response
  try {
    response = await fetch(`${LAMBDA_BASE_URL}/${functionName}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(INTERNAL_API_TOKEN ? { 'X-Internal-Token': INTERNAL_API_TOKEN } : {}),
      },
      body: JSON.stringify(args),
      signal: controller.signal,
    })
  } catch (fetchErr: any) {
    if (fetchErr?.name === 'AbortError') {
      throw new Error(`Lambda tool timeout after 15s for ${functionName}`)
    }
    throw fetchErr
  } finally {
    clearTimeout(timeout)
  }

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
