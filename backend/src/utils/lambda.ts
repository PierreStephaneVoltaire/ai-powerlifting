import { LambdaClient, InvokeCommand } from '@aws-sdk/client-lambda'

// ─── Lambda configuration ───────────────────────────────────────────────────
// Deterministic Phase 2 powerlifting tools are deployed as self-contained AWS
// Lambda functions (Phase 1) and invoked directly here instead of routing through
// the IF agent pod's X-Direct-Tool-Invoke path. The function name is built from the
// configurable prefix (default `pl-`) plus the tool name, e.g. `pl-health_get_session`.
//
// Region falls back to AWS_REGION (the same default used by the DynamoDB/S3 clients)
// unless POWERLIFTING_LAMBDA_REGION is set explicitly.
const LAMBDA_REGION = process.env.POWERLIFTING_LAMBDA_REGION || process.env.AWS_REGION || 'ca-central-1'
const LAMBDA_PREFIX = process.env.POWERLIFTING_LAMBDA_PREFIX || 'pl-'

const lambdaClient = new LambdaClient({
  region: LAMBDA_REGION,
  credentials: process.env.AWS_ACCESS_KEY_ID && process.env.AWS_SECRET_ACCESS_KEY
    ? {
        accessKeyId: process.env.AWS_ACCESS_KEY_ID,
        secretAccessKey: process.env.AWS_SECRET_ACCESS_KEY,
      }
    : undefined,
})

function decodeBody(payload: Uint8Array | undefined): any {
  if (!payload || payload.length === 0) return null
  const text = Buffer.from(payload).toString('utf8')
  return JSON.parse(text)
}

/**
 * Invoke a Phase 2 powerlifting Lambda function by tool name.
 *
 * The Lambda event is `{ "args": args }` and the Lambda returns
 * `{ "statusCode": 200, "body": "<json string>" }`. This helper parses the body
 * JSON and returns the same shape `invokeToolDirect` returns, so callers can be
 * swapped one-for-one without changing how they consume the result.
 *
 * `functionName` is the exact tool name (e.g. `health_get_session`). The deployed
 * Lambda is named `${LAMBDA_PREFIX}${functionName}` (default prefix `pl-`).
 */
export async function invokeLambda(
  functionName: string,
  args: Record<string, unknown>,
): Promise<any> {
  const command = new InvokeCommand({
    FunctionName: `${LAMBDA_PREFIX}${functionName}`,
    Payload: Buffer.from(JSON.stringify({ args })),
  })

  const response = await lambdaClient.send(command)

  const parsed = decodeBody(response.Payload)
  if (parsed && typeof parsed === 'object' && 'body' in parsed) {
    const body = parsed.body
    if (typeof body === 'string') {
      return JSON.parse(body)
    }
    return body
  }
  return parsed
}