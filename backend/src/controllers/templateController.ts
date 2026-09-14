import { Request, Response } from 'express'
import { invokeLambda } from '../utils/lambda'
import { invokeToolDirect } from '../utils/agent'
import { AppError } from '../middleware/errorHandler'

const IF_API_URL = process.env.IF_API_URL || 'http://if-agent-api.if-portals.svc.cluster.local:8000'
const INTERNAL_API_TOKEN = process.env.INTERNAL_API_TOKEN || ''

function normalizeTemplateSk(sk: string): string {
  try {
    return decodeURIComponent(sk)
  } catch {
    return sk
  }
}

function templateActor(req: Request): Record<string, string> {
  if (req.readOnly || !req.user || !req.mapped_pk) return {}
  return {
    actor_pk: req.mapped_pk,
    author: req.user.username || req.mapped_pk,
  }
}

export async function listTemplates(req: Request, res: Response) {
  const include_archived = req.query.includeArchived === 'true'
  try {
    const data = await invokeLambda('pod_templates', { function: 'template_list',  include_archived, ...templateActor(req) })
    res.json(data)
  } catch (err: any) {
    throw new AppError(`List failed: ${err.message}`, 502)
  }
}

export async function getTemplate(req: Request, res: Response) {
  const sk = normalizeTemplateSk(req.params.sk)
  try {
    const data = await invokeLambda('pod_templates', { function: 'template_get',  sk, ...templateActor(req) })
    res.json(data)
  } catch (err: any) {
    if (err.message?.includes('not found')) throw new AppError('Template not found', 404)
    throw new AppError(`Get failed: ${err.message}`, 502)
  }
}

export async function createTemplateFromBlock(req: Request, res: Response) {
  const { name, program_sk } = req.body
  try {
    const result = await invokeLambda('pod_templates', { function: 'template_create_from_block',  name, program_sk, ...templateActor(req), pk: req.mapped_pk })
    res.status(201).json(result)
  } catch (err: any) {
    throw new AppError(`Template creation failed: ${err.message}`, 502)
  }
}

export async function createBlankTemplate(req: Request, res: Response) {
  const { name, description, estimated_weeks, days_per_week } = req.body
  try {
    const result = await invokeLambda('pod_templates', { function: 'template_create_blank', 
      name,
      description: description ?? '',
      estimated_weeks: estimated_weeks ?? 4,
      days_per_week: days_per_week ?? 3,
      ...templateActor(req),
      pk: req.mapped_pk,
    })
    res.status(201).json(result)
  } catch (err: any) {
    throw new AppError(`Template creation failed: ${err.message}`, 502)
  }
}

export async function updateTemplate(req: Request, res: Response) {
  const sk = normalizeTemplateSk(req.params.sk)
  const template = req.body
  try {
    const result = await invokeLambda('pod_templates', { function: 'template_update',  sk, template, ...templateActor(req), pk: req.mapped_pk })
    res.json(result)
  } catch (err: any) {
    if (err.message?.includes('not found')) throw new AppError('Template not found', 404)
    throw new AppError(`Update failed: ${err.message}`, 502)
  }
}

export async function copyTemplate(req: Request, res: Response) {
  const sk = normalizeTemplateSk(req.params.sk)
  const { new_name } = req.body
  try {
    const result = await invokeLambda('pod_templates', { function: 'template_copy',  sk, new_name, ...templateActor(req), pk: req.mapped_pk })
    res.status(201).json(result)
  } catch (err: any) {
    throw new AppError(`Copy failed: ${err.message}`, 502)
  }
}

export async function archiveTemplate(req: Request, res: Response) {
  const sk = normalizeTemplateSk(req.params.sk)
  try {
    const result = await invokeLambda('pod_templates', { function: 'template_archive',  sk, ...templateActor(req), pk: req.mapped_pk })
    res.json(result)
  } catch (err: any) {
    throw new AppError(`Archive failed: ${err.message}`, 502)
  }
}

export async function unarchiveTemplate(req: Request, res: Response) {
  const sk = normalizeTemplateSk(req.params.sk)
  try {
    const result = await invokeLambda('pod_templates', { function: 'template_unarchive',  sk, ...templateActor(req), pk: req.mapped_pk })
    res.json(result)
  } catch (err: any) {
    throw new AppError(`Unarchive failed: ${err.message}`, 502)
  }
}

export async function evaluateTemplate(req: Request, res: Response) {
  const sk = normalizeTemplateSk(req.params.sk)
  try {
    const result = await invokeToolDirect('template_evaluate', { sk, ...templateActor(req), pk: req.mapped_pk })
    res.json(result)
  } catch (err: any) {
    throw new AppError(`Evaluation failed: ${err.message}`, 502)
  }
}

export async function applyTemplate(req: Request, res: Response) {
  const sk = normalizeTemplateSk(req.params.sk)
  const { target, start_date, week_start_day } = req.body
  try {
    const result = await invokeLambda('pod_templates', { function: 'template_apply',  sk, target, start_date, week_start_day, ...templateActor(req), pk: req.mapped_pk })
    res.json(result)
  } catch (err: any) {
    throw new AppError(`Apply preview failed: ${err.message}`, 502)
  }
}

export async function confirmApplyTemplate(req: Request, res: Response) {
  const sk = normalizeTemplateSk(req.params.sk)
  const { backfilled_maxes, start_date, week_start_day, target } = req.body
  try {
    const result = await invokeLambda('pod_templates', { function: 'template_apply_confirm', 
      sk,
      backfilled_maxes,
      start_date,
      week_start_day,
      target,
      ...templateActor(req),
      pk: req.mapped_pk,
    })
    res.json(result)
  } catch (err: any) {
    throw new AppError(`Confirm apply failed: ${err.message}`, 502)
  }
}

export async function publishTemplate(req: Request, res: Response) {
  const sk = normalizeTemplateSk(req.params.sk)
  try {
    const result = await invokeLambda('pod_templates', { function: 'template_publish',  sk, ...templateActor(req), pk: req.mapped_pk })
    res.json(result)
  } catch (err: any) {
    throw new AppError(`Publish failed: ${err.message}`, 502)
  }
}

export async function unpublishTemplate(req: Request, res: Response) {
  const sk = normalizeTemplateSk(req.params.sk)
  try {
    const result = await invokeLambda('pod_templates', { function: 'template_unpublish',  sk, ...templateActor(req), pk: req.mapped_pk })
    res.json(result)
  } catch (err: any) {
    throw new AppError(`Unpublish failed: ${err.message}`, 502)
  }
}

export async function uploadTemplateImport(req: Request, res: Response) {
  if (!req.file) {
    throw new AppError('No file uploaded', 400)
  }
  if (!req.user || req.readOnly || !req.mapped_pk) {
    throw new AppError('Sign in required', 401, 'AUTH_REQUIRED')
  }

  const response = await fetch(`${IF_API_URL}/v1/jobs`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Internal-Token': INTERNAL_API_TOKEN, 'X-Person-Pk': req.mapped_pk },
    body: JSON.stringify({
      conversation_id: `template-import:${req.mapped_pk}`,
      kind: 'domain',
      payload: { domain: 'imports', athlete: req.mapped_pk, operation: 'import_parse_file', arguments: { base64_content: req.file.buffer.toString('base64'), filename: req.file.originalname, pk: req.mapped_pk } },
      idempotency_key: `${req.mapped_pk}:${req.file.originalname}:${req.file.size}:${Date.now()}`,
    }),
  })
  if (!response.ok) {
    const text = await response.text()
    throw new AppError(`Template import upload failed: ${text}`, 502)
  }
  const body = await response.json()
  res.status(202).json(body)
}

export async function getTemplateImport(req: Request, res: Response) {
  if (!req.user || req.readOnly || !req.mapped_pk) {
    throw new AppError('Sign in required', 401, 'AUTH_REQUIRED')
  }
  const response = await fetch(`${IF_API_URL}/v1/jobs/${encodeURIComponent(req.params.jobId)}`, {
    headers: { 'X-Internal-Token': INTERNAL_API_TOKEN, 'X-Person-Pk': req.mapped_pk },
  })
  if (response.status === 404) throw new AppError('Template import job not found', 404)
  if (!response.ok) {
    const text = await response.text()
    throw new AppError(`Template import status failed: ${text}`, 502)
  }
  const job: any = await response.json()
  const result = job.result?.content
  let parsedResult = result
  if (typeof result === 'string') {
    try { parsedResult = JSON.parse(result) } catch { parsedResult = result }
  }
  res.json({
    job_id: job.job_id,
    status: job.status,
    filename: job.request?.payload?.arguments?.filename,
    ...(parsedResult && typeof parsedResult === 'object' ? parsedResult : {}),
    ...(job.error ? { error: job.error.message || String(job.error) } : {}),
  })
}

export async function applyTemplateImport(req: Request, res: Response) {
  if (!req.user || req.readOnly || !req.mapped_pk) throw new AppError('Sign in required', 401, 'AUTH_REQUIRED')
  const response = await fetch(`${IF_API_URL}/v1/jobs/${encodeURIComponent(req.params.jobId)}`, { headers: { 'X-Internal-Token': INTERNAL_API_TOKEN, 'X-Person-Pk': req.mapped_pk } })
  if (!response.ok) throw new AppError('Template import job not found', response.status === 404 ? 404 : 502)
  const job: any = await response.json()
  if (job.status !== 'succeeded') throw new AppError(`Template import is ${job.status}`, 409, 'IMPORT_NOT_READY')
  const raw = job.result?.content
  let result: any = raw
  if (typeof raw === 'string') { try { result = JSON.parse(raw) } catch { result = {} } }
  const importId = result?.import_id || result?.id
  if (!importId) throw new AppError('Template import result has no import id', 409, 'IMPORT_ID_MISSING')
  const { merge_strategy, conflict_resolutions, start_date, glossary_overrides, confirmed_auto_adds } = req.body || {}
  const applied = await invokeLambda('pod_import', { function: 'import_apply', import_id: importId, classification_override: 'template', author: req.user.username || req.mapped_pk, pk: req.mapped_pk, merge_strategy, conflict_resolutions, start_date, glossary_overrides, confirmed_auto_adds })
  res.json({ ...result, ...applied, job_id: job.job_id, status: 'succeeded', filename: job.request?.payload?.arguments?.filename, template_sk: applied?.target_sk || applied?.template_sk || applied?.sk })
}
