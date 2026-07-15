import { DeleteObjectCommand, S3Client } from '@aws-sdk/client-s3'
import { Upload } from '@aws-sdk/lib-storage'
import { v4 as uuidv4 } from 'uuid'
import { invokeLambda } from '../utils/lambda'
import { AppError } from '../middleware/errorHandler'
import { logger } from '../utils/logger'
import type {
  BudgetCategory,
  BudgetConfig,
  BudgetItem,
  BudgetPriorityTier,
  BudgetStore,
  BudgetSummary,
  BudgetAiAnalysis,
} from '@powerlifting/types'

const BUDGET_MEDIA_BUCKET = process.env.BUDGET_MEDIA_BUCKET || 'powerlifting-budget-media'

export const CATEGORY_VALUES: ReadonlyArray<BudgetCategory> = [
  'equipment',
  'supplement',
  'gym_membership',
  'federation_membership',
  'coaching',
  'app_subscription',
  'competition_entry',
  'transport',
  'accommodation',
  'food_comp_day',
  'food_weigh_in',
  'food_prep',
  'recovery',
  'other',
]

export const PRIORITY_TIER_VALUES: ReadonlyArray<BudgetPriorityTier> = ['MANDATORY', 'IMPORTANT', 'OPTIONAL']

const s3Client = new S3Client({
  region: process.env.AWS_REGION || 'ca-central-1',
  credentials: process.env.AWS_ACCESS_KEY_ID && process.env.AWS_SECRET_ACCESS_KEY
    ? { accessKeyId: process.env.AWS_ACCESS_KEY_ID, secretAccessKey: process.env.AWS_SECRET_ACCESS_KEY }
    : undefined,
})

function s3SafeSegment(value: string): string {
  return value.replace(/[^A-Za-z0-9_-]/g, '_').slice(0, 128) || 'user'
}

export interface BudgetItemFilters {
  comp_id?: string
  category?: BudgetCategory
  priority?: BudgetPriorityTier
}

function normalizeConfig(raw: unknown, pk: string): BudgetConfig {
  const obj = typeof raw === 'object' && raw !== null ? (raw as Record<string, unknown>) : {}
  return {
    user_pk: pk,
    monthly_cap: typeof obj.monthly_cap === 'number' ? obj.monthly_cap : 0,
    currency: typeof obj.currency === 'string' ? obj.currency : 'USD',
    notes: typeof obj.notes === 'string' ? obj.notes : null,
    updated_at: typeof obj.updated_at === 'string' ? obj.updated_at : new Date().toISOString(),
  }
}

export async function getBudgetConfig(pk: string): Promise<BudgetConfig> {
  const result = await invokeLambda('pod_budget', { function: 'budget_get_config',  pk })
  return normalizeConfig(result, pk)
}

export async function putBudgetConfig(pk: string, raw: unknown): Promise<BudgetConfig> {
  const result = await invokeLambda('pod_budget', { function: 'budget_put_config',  pk, config: raw })
  return normalizeConfig(result, pk)
}

export async function listBudgetItems(pk: string, filters?: BudgetItemFilters): Promise<BudgetItem[]> {
  const payload: Record<string, unknown> = { pk }
  if (filters?.comp_id !== undefined) payload.comp_id = filters.comp_id
  if (filters?.category !== undefined) payload.category = filters.category
  if (filters?.priority !== undefined) payload.priority = filters.priority
  const result = await invokeLambda('pod_budget', { function: 'budget_list_items', ...payload })
  return Array.isArray(result?.items) ? result.items : []
}

export async function createBudgetItem(pk: string, raw: unknown): Promise<BudgetItem> {
  const result = await invokeLambda('pod_budget', { function: 'budget_create_item',  pk, item: raw })
  if (!result) throw new AppError('Failed to create budget item', 500)
  logger.info({ pk, module: 'budget', fn: 'createBudgetItem', itemId: (result as BudgetItem).id }, 'budget item created via Fission')
  return result as BudgetItem
}

export async function updateBudgetItem(pk: string, itemId: string, raw: unknown): Promise<BudgetItem> {
  const result = await invokeLambda('pod_budget', { function: 'budget_update_item',  pk, item_id: itemId, item: raw })
  if (!result) throw new AppError('Failed to update budget item', 500)
  logger.info({ pk, module: 'budget', fn: 'updateBudgetItem', itemId }, 'budget item updated via Fission')
  return result as BudgetItem
}

export async function deleteBudgetItem(pk: string, itemId: string): Promise<void> {
  await invokeLambda('pod_budget', { function: 'budget_delete_item',  pk, item_id: itemId })
  logger.info({ pk, module: 'budget', fn: 'deleteBudgetItem', itemId }, 'budget item deleted via Fission')
}

export async function markItemCut(pk: string, itemId: string, cut: boolean): Promise<BudgetItem> {
  const items = await listBudgetItems(pk)
  const existing = items.find((i) => i.id === itemId)
  if (!existing) {
    logger.warn({ pk, module: 'budget', fn: 'markItemCut', itemId }, 'budget item not found')
    throw new AppError(`Budget item ${itemId} not found`, 404, 'BUDGET_ITEM_NOT_FOUND')
  }
  const updated: BudgetItem = { ...existing, cut_by_ai: cut, updated_at: new Date().toISOString() }
  return updateBudgetItem(pk, itemId, updated)
}

export async function getBudgetSummary(pk: string, month: string): Promise<BudgetSummary> {
  return invokeLambda('pod_budget', { function: 'budget_get_summary',  pk, month }) as Promise<BudgetSummary>
}

export async function getBudget(pk: string): Promise<BudgetStore> {
  const [config, items] = await Promise.all([getBudgetConfig(pk), listBudgetItems(pk)])
  return { config, items }
}

export async function putBudget(
  pk: string,
  configRaw: unknown,
  itemsRaw: unknown[],
): Promise<void> {
  await putBudgetConfig(pk, configRaw)
  const existing = await listBudgetItems(pk)
  const incomingById = new Map<string, unknown>()
  for (const raw of itemsRaw) {
    if (raw && typeof raw === 'object' && typeof (raw as { id?: unknown }).id === 'string') {
      incomingById.set((raw as { id: string }).id, raw)
    }
  }

  for (const raw of itemsRaw) {
    const idFromRaw = raw && typeof raw === 'object' && typeof (raw as { id?: unknown }).id === 'string'
      ? (raw as { id: string }).id
      : ''
    if (idFromRaw && existing.some((i) => i.id === idFromRaw)) {
      await updateBudgetItem(pk, idFromRaw, raw)
    } else {
      await createBudgetItem(pk, raw)
    }
  }

  for (const it of existing) {
    if (!incomingById.has(it.id)) {
      await deleteBudgetItem(pk, it.id)
    }
  }

  logger.info({ pk, module: 'budget', fn: 'putBudget', itemCount: incomingById.size }, 'budget store replaced via Fission')
}

export async function uploadItemPhoto(
  pk: string,
  itemId: string,
  file: Buffer,
  filename: string,
  mimeType: string,
): Promise<{ photo_s3_key: string }> {
  const items = await listBudgetItems(pk)
  const item = items.find((i) => i.id === itemId)
  if (!item) throw new AppError(`Budget item ${itemId} not found`, 404, 'BUDGET_ITEM_NOT_FOUND')

  const photoId = uuidv4()
  const extension = filename.split('.').pop() || 'jpg'
  const s3Key = `budget/${s3SafeSegment(pk)}/${itemId}/${photoId}.${extension}`

  const upload = new Upload({
    client: s3Client,
    params: {
      Bucket: BUDGET_MEDIA_BUCKET,
      Key: s3Key,
      Body: file,
      ContentType: mimeType,
    },
  })
  await upload.done()

  if (item.photo_s3_key) {
    try {
      await s3Client.send(new DeleteObjectCommand({ Bucket: BUDGET_MEDIA_BUCKET, Key: item.photo_s3_key }))
    } catch (err) {
      logger.warn({ err, module: 'budget', fn: 'uploadItemPhoto' }, 'failed to delete previous budget photo')
    }
  }

  const updated: BudgetItem = { ...item, photo_s3_key: s3Key, updated_at: new Date().toISOString() }
  await updateBudgetItem(pk, itemId, updated)

  return { photo_s3_key: s3Key }
}

export async function deleteItemPhoto(pk: string, itemId: string): Promise<void> {
  const items = await listBudgetItems(pk)
  const item = items.find((i) => i.id === itemId)
  if (!item) throw new AppError(`Budget item ${itemId} not found`, 404, 'BUDGET_ITEM_NOT_FOUND')
  if (!item.photo_s3_key) return

  await s3Client.send(new DeleteObjectCommand({ Bucket: BUDGET_MEDIA_BUCKET, Key: item.photo_s3_key }))

  const updated: BudgetItem = { ...item, photo_s3_key: null as any, updated_at: new Date().toISOString() }
  await updateBudgetItem(pk, itemId, updated)
}

export interface BudgetAiCompetition {
  master_id: string
  name: string
  start_date: string
  user_status: string
}

export async function getBudgetAiAnalysis(
  pk: string,
  refresh: boolean,
  competitionsProvider: (pk: string) => Promise<BudgetAiCompetition[]>,
): Promise<BudgetAiAnalysis> {
  const now = new Date().toISOString()

  const [config, items] = await Promise.all([getBudgetConfig(pk), listBudgetItems(pk)])

  let competitions: BudgetAiCompetition[] = []
  try {
    const userComps = await competitionsProvider(pk)
    competitions = userComps
      .filter((c) => c.user_status !== 'completed' && c.user_status !== 'skipped')
      .sort((a, b) => a.start_date.localeCompare(b.start_date))
  } catch (compErr) {
    logger.warn({ err: compErr, pk, module: 'budget', fn: 'getBudgetAiAnalysis' }, 'failed to load competitions for budget AI')
  }

  const payload = {
    config: { monthly_cap: config.monthly_cap, currency: config.currency },
    items: items.map((it) => ({
      id: it.id,
      name: it.name,
      category: it.category,
      cost: it.cost,
      recurrence: it.recurrence,
      start_date: it.start_date,
      end_date: it.end_date,
      priority_tier: it.priority_tier,
      comp_linked: it.comp_linked,
      competition_id: it.competition_id,
      purchased: it.purchased,
      purchased_date: it.purchased_date,
      cut_by_ai: it.cut_by_ai,
    })),
    competitions,
  }

  logger.info({ pk, module: 'budget', fn: 'getBudgetAiAnalysis', refresh, itemCount: items.length }, 'budget AI analysis generating via Fission')

  const result = (await invokeLambda('pod_budget', { function: 'budget_priority_timeline', ...payload })) as Partial<BudgetAiAnalysis>

  const analysis: BudgetAiAnalysis = {
    overall_assessment: String(result?.overall_assessment ?? ''),
    locked_in: Array.isArray(result?.locked_in) ? result.locked_in : [],
    suggested_cuts: Array.isArray(result?.suggested_cuts) ? result.suggested_cuts : [],
    gaps: Array.isArray(result?.gaps) ? result.gaps : [],
    coach_note: String(result?.coach_note ?? ''),
    insufficient_data: Boolean(result?.insufficient_data),
    insufficient_data_reason: String(result?.insufficient_data_reason ?? ''),
    cached: false,
    generated_at: now,
  }

  return analysis
}
