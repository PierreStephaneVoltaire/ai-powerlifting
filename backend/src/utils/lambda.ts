// ─── Lambda invocation (API Gateway HTTP path) ──────────────────────────────
// Deterministic Phase 2 powerlifting tools are deployed behind an AWS API
// Gateway HTTP API (Phase 3). Each tool is exposed as a POST `/{tool}` route on
// the API Gateway endpoint. Instead of calling the Lambda functions directly
// through the AWS SDK, we POST the tool arguments to the per-tool HTTP route and
// parse the Lambda response body, returning the same shape the old SDK version
// returned and the same shape `invokeToolDirect` returns.
//
// The base URL is read from `POWERLIFTING_LAMBDA_BASE_URL` (e.g.
// `https://<id>.execute-api.<region>.amazonaws.com`). There is no default — if it
// is unset, invocation fails fast with a clear configuration error.
const LAMBDA_BASE_URL = process.env.POWERLIFTING_LAMBDA_BASE_URL

/**
 * Invoke a Phase 2 powerlifting tool through its API Gateway HTTP route.
 *
 * `functionName` is the exact tool name (e.g. `health_get_session`). The request
 * is a POST to `${POWERLIFTING_LAMBDA_BASE_URL}/${functionName}` with the tool
 * arguments JSON-encoded as the request body and a `Content-Type: application/json`
 * header.
 *
 * The Lambda returns `{ "statusCode": 200, "body": "<json string>" }`. This helper
 * parses the `body` JSON and returns it, matching the shape the previous
 * SDK-based implementation returned and the shape `invokeToolDirect` returns, so
 * callers can consume the result unchanged.
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

  const response = await fetch(`${LAMBDA_BASE_URL}/${functionName}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(args),
  })

  if (!response.ok) {
    const text = await response.text()
    throw new Error(`Lambda tool error ${response.status} for ${functionName}: ${text}`)
  }

  const parsed: any = await response.json()

  // API Gateway + Lambda proxy integration wraps the tool payload as
  // `{ statusCode, body: "<json string>" }`. Unwrap and parse the body JSON so
  // callers receive the raw tool payload.
  if (parsed && typeof parsed === 'object' && 'body' in parsed) {
    const body = parsed.body
    if (typeof body === 'string' && body.length > 0) {
      return JSON.parse(body)
    }
    return body
  }
  return parsed
}
