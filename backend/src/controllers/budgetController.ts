import { QueryCommand, PutCommand, DeleteCommand, GetCommand } from '@aws-sdk/lib-dynamodb'
import { S3Client, DeleteObjectCommand } from '@aws-sdk/client-s3'
import { Upload } from '@aws-sdk/lib-storage'
import { v4 as uuidv4 } from 'uuid'
import { docClient, POWERLIFTING_BUDGET_TABLE, BUDGET_MEDIA_BUCKET } from '../db/dynamo'
import { AppError } from '../middleware/errorHandler'
import { logger } from '../utils/logger'
import {
  normalizeBudgetConfigFromStore,
  normalizeBudgetItemFromStore,
  normalizeBudgetItemInput,
} from '../db/transforms'
import type {
  BudgetItem,
  BudgetConfig,
  BudgetStore,
  BudgetSummary,
  BudgetCategory,
  BudgetPriorityTier,
  BudgetAiAnalysis,
} from '@powerlifting/types'

const CONFIG_SK = 'CONFIG#budget'
const ITEM_PREFIX = 'ITEM#'

const CATEGORY_VALUES: ReadonlyArray<BudgetCategory> = [
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
const PRIORITY_TIER_VALUES: ReadonlyArray<BudgetPriorityTier> = ['MANDATORY', 'IMPORTANT', 'OPTIONAL']

const s3Client = new S3Client({
  region: process.env.AWS_REGION || 'ca-central-1',
  credentials: process.env.AWS_ACCESS_KEY_ID && process.env.AWS_SECRET_ACCESS_KEY
    ? {
        accessKeyId: process.env.AWS_ACCESS_KEY_ID,
        secretAccessKey: process.env.AWS_SECRET_ACCESS_KEY,
      }
    : undefined,
})

function newItemId(): string {
  return `item-${Date.now().toString(36)}-${Math.floor(Math.random() * 1e9).toString(36)}`
}

interface StoredConfig {
  pk: string
  sk: string
  config: BudgetConfig
  updated_at: string
}

interface StoredItem extends BudgetItem {
  pk: string
  sk: string
}

async function queryItems(pk: string): Promise<StoredItem[]> {
  const items: StoredItem[] = []
  let lastKey: Record<string, unknown> | undefined
  do {
    const resp = await docClient.send(new QueryCommand({
      TableName: POWERLIFTING_BUDGET_TABLE,
      KeyConditionExpression: 'pk = :pk AND begins_with(sk, :prefix)',
      ExpressionAttributeValues: { ':pk': pk, ':prefix': ITEM_PREFIX },
      ExclusiveStartKey: lastKey,
    }))
    for (const it of resp.Items ?? []) items.push(it as StoredItem)
    lastKey = resp.LastEvaluatedKey
  } while (lastKey)
  return items
}

function stripStored({ pk: _pk, sk: _sk, ...rest }: StoredItem): BudgetItem {
  return rest
}

async function getConfig(pk: string): Promise<BudgetConfig> {
  const result = await docClient.send(new GetCommand({
    TableName: POWERLIFTING_BUDGET_TABLE,
    Key: { pk, sk: CONFIG_SK },
  }))
  return normalizeBudgetConfigFromStore(result.Item, pk)
}

export interface BudgetItemFilters {
  comp_id?: string
  category?: BudgetCategory
  priority?: BudgetPriorityTier
}

function itemMatchesFilters(item: BudgetItem, filters?: BudgetItemFilters): boolean {
  if (!filters) return true
  if (filters.comp_id !== undefined && (item.competition_id ?? null) !== filters.comp_id) return false
  if (filters.category !== undefined && item.category !== filters.category) return false
  if (filters.priority !== undefined && item.priority_tier !== filters.priority) return false
  return true
}

function monthKey(dateStr: string | null | undefined): string | null {
  if (typeof dateStr !== 'string' || !dateStr) return null
  return dateStr.length >= 7 ? dateStr.slice(0, 7) : null
}

function recurringMonthlyTotal(items: BudgetItem[]): number {
  return items
    .filter((it) => it.recurrence === 'MONTHLY')
    .reduce((sum, it) => sum + it.cost, 0)
}

function spentThisMonth(items: BudgetItem[], month: string): number {
  return items
    .filter((it) => {
      if (it.recurrence === 'MONTHLY') {
        const start = monthKey(it.start_date)
        const end = monthKey(it.end_date)
        const atOrAfterStart = start ? start <= month : true
        const atOrBeforeEnd = end ? month <= end : true
        return atOrAfterStart && atOrBeforeEnd
      }
      const effectiveDate = it.purchased_date ?? it.start_date
      return monthKey(effectiveDate) === month
    })
    .reduce((sum, it) => sum + it.cost, 0)
}

function emptyBreakdown(): { count: number; total: number } {
  return { count: 0, total: 0 }
}

function buildPriorityBreakdown(items: BudgetItem[], month: string): BudgetSummary['items_by_priority'] {
  const byPriority = {
    MANDATORY: emptyBreakdown(),
    IMPORTANT: emptyBreakdown(),
    OPTIONAL: emptyBreakdown(),
  }
  for (const it of items) {
    const bucket = byPriority[it.priority_tier]
    if (!bucket) continue
    if (it.recurrence === 'MONTHLY') {
      const start = monthKey(it.start_date)
      const end = monthKey(it.end_date)
      const active = (start ? start <= month : true) && (end ? month <= end : true)
      if (!active) continue
      bucket.count += 1
      bucket.total += it.cost
      continue
    }
    const effectiveDate = it.purchased_date ?? it.start_date
    if (monthKey(effectiveDate) !== month) continue
    bucket.count += 1
    bucket.total += it.cost
  }
  return byPriority
}

function upcomingOneTime(items: BudgetItem[]): BudgetItem[] {
  return items
    .filter((it) => it.recurrence === 'ONE_TIME' && !it.purchased)
    .sort((a, b) => (a.start_date || '').localeCompare(b.start_date || ''))
}

// ─── Config ──────────────────────────────────────────────────────────────────

export async function getBudgetConfig(pk: string): Promise<BudgetConfig> {
  const config = await getConfig(pk)
  logger.debug({ pk, module: 'budget', fn: 'getBudgetConfig' }, 'budget config read')
  return config
}

export async function putBudgetConfig(pk: string, raw: unknown): Promise<BudgetConfig> {
  const now = new Date().toISOString()
  const config = normalizeBudgetConfigFromStore(raw, pk)
  config.updated_at = now
  await docClient.send(new PutCommand({
    TableName: POWERLIFTING_BUDGET_TABLE,
    Item: { pk, sk: CONFIG_SK, config, updated_at: now } as StoredConfig,
  }))
  logger.info({ pk, module: 'budget', fn: 'putBudgetConfig', monthly_cap: config.monthly_cap }, 'budget config upserted')
  return config
}

// ─── Items ───────────────────────────────────────────────────────────────────

export async function listBudgetItems(
  pk: string,
  filters?: BudgetItemFilters,
): Promise<BudgetItem[]> {
  const stored = await queryItems(pk)
  const items = stored.map(stripStored).map((it) => normalizeBudgetItemFromStore(it, pk))
  const filtered = filters ? items.filter((it) => itemMatchesFilters(it, filters)) : items
  logger.debug({ pk, module: 'budget', fn: 'listBudgetItems', count: filtered.length }, 'budget items listed')
  return filtered
}

export async function createBudgetItem(pk: string, raw: unknown): Promise<BudgetItem> {
  const now = new Date().toISOString()
  const item = normalizeBudgetItemInput(raw, pk, newItemId(), undefined, now)
  await docClient.send(new PutCommand({
    TableName: POWERLIFTING_BUDGET_TABLE,
    Item: { ...item, pk, sk: `${ITEM_PREFIX}${item.id}` } as StoredItem,
  }))
  logger.info({ pk, module: 'budget', fn: 'createBudgetItem', itemId: item.id, category: item.category }, 'budget item created')
  return item
}

export async function updateBudgetItem(pk: string, itemId: string, raw: unknown): Promise<BudgetItem> {
  const stored = await queryItems(pk)
  const existing = stored.find((i) => i.id === itemId)
  if (!existing) {
    logger.warn({ pk, module: 'budget', fn: 'updateBudgetItem', itemId }, 'budget item not found')
    throw new AppError(`Budget item ${itemId} not found`, 404, 'BUDGET_ITEM_NOT_FOUND')
  }
  const normalized = normalizeBudgetItemFromStore(stripStored(existing), pk)
  const updated = normalizeBudgetItemInput(raw, pk, itemId, normalized, new Date().toISOString())
  await docClient.send(new PutCommand({
    TableName: POWERLIFTING_BUDGET_TABLE,
    Item: { ...updated, pk, sk: `${ITEM_PREFIX}${itemId}` } as StoredItem,
  }))
  logger.info({ pk, module: 'budget', fn: 'updateBudgetItem', itemId }, 'budget item updated')
  return updated
}

export async function deleteBudgetItem(pk: string, itemId: string): Promise<void> {
  const stored = await queryItems(pk)
  const existing = stored.find((i) => i.id === itemId)
  if (!existing) {
    logger.warn({ pk, module: 'budget', fn: 'deleteBudgetItem', itemId }, 'budget item not found')
    throw new AppError(`Budget item ${itemId} not found`, 404, 'BUDGET_ITEM_NOT_FOUND')
  }
  await docClient.send(new DeleteCommand({
    TableName: POWERLIFTING_BUDGET_TABLE,
    Key: { pk, sk: `${ITEM_PREFIX}${itemId}` },
  }))
  logger.info({ pk, module: 'budget', fn: 'deleteBudgetItem', itemId }, 'budget item deleted')
}

// ─── Summary ──────────────────────────────────────────────────────────────────

export async function getBudgetSummary(pk: string, month: string): Promise<BudgetSummary> {
  const [config, stored] = await Promise.all([getConfig(pk), queryItems(pk)])
  const items = stored.map(stripStored).map((it) => normalizeBudgetItemFromStore(it, pk))
  const summary: BudgetSummary = {
    monthly_cap: config.monthly_cap,
    currency: config.currency,
    spent_this_month: spentThisMonth(items, month),
    recurring_monthly_total: recurringMonthlyTotal(items),
    items_by_priority: buildPriorityBreakdown(items, month),
    upcoming_one_time: upcomingOneTime(items),
  }
  logger.debug(
    { pk, module: 'budget', fn: 'getBudgetSummary', month, spent: summary.spent_this_month },
    'budget summary computed',
  )
  return summary
}

// ─── Legacy whole-store read/write (backward compatibility) ───────────────────
//
// Kept so the existing frontend store (useBudgetStore) and the analytics budget
// timeline endpoint keep working until BUD-02..05 migrate to the granular API.

export async function getBudget(pk: string): Promise<BudgetStore> {
  const [config, storedItems] = await Promise.all([getConfig(pk), queryItems(pk)])
  const items = storedItems.map(stripStored).map((it) => normalizeBudgetItemFromStore(it, pk))
  return { config, items }
}

export async function putBudget(
  pk: string,
  configRaw: unknown,
  itemsRaw: unknown[],
): Promise<void> {
  const now = new Date().toISOString()
  const config = normalizeBudgetConfigFromStore(configRaw, pk)
  config.updated_at = now
  const existing = await queryItems(pk)
  const byId = new Map<string, StoredItem>()
  for (const it of existing) byId.set(it.id, it)
  const incomingIds = new Set<string>()

  await docClient.send(new PutCommand({
    TableName: POWERLIFTING_BUDGET_TABLE,
    Item: { pk, sk: CONFIG_SK, config, updated_at: now } as StoredConfig,
  }))

  for (const raw of itemsRaw) {
    const idFromRaw =
      raw && typeof raw === 'object' && 'id' in raw && typeof (raw as { id: unknown }).id === 'string'
        ? (raw as { id: string }).id
        : ''
    const existingItem = byId.get(idFromRaw)
    const priorCreatedAt = existingItem?.created_at
    const priorNormalized = existingItem ? normalizeBudgetItemFromStore(stripStored(existingItem), pk) : undefined
    const item = normalizeBudgetItemInput(raw, pk, priorNormalized?.id ?? newItemId(), priorNormalized, now, priorCreatedAt)
    incomingIds.add(item.id)
    await docClient.send(new PutCommand({
      TableName: POWERLIFTING_BUDGET_TABLE,
      Item: { ...item, pk, sk: `${ITEM_PREFIX}${item.id}` } as StoredItem,
    }))
  }

  for (const it of existing) {
    if (!incomingIds.has(it.id)) {
      await docClient.send(new DeleteCommand({
        TableName: POWERLIFTING_BUDGET_TABLE,
        Key: { pk, sk: `${ITEM_PREFIX}${it.id}` },
      }))
    }
  }
  logger.info({ pk, module: 'budget', fn: 'putBudget', itemCount: incomingIds.size }, 'budget store replaced')
}

// ─── Photos (S3 support preserved) ───────────────────────────────────────────

export async function uploadItemPhoto(
  pk: string,
  itemId: string,
  file: Buffer,
  filename: string,
  mimeType: string,
): Promise<{ photo_s3_key: string }> {
  const existing = await queryItems(pk)
  const item = existing.find((i) => i.id === itemId)
  if (!item) throw new AppError(`Budget item ${itemId} not found`, 404, 'BUDGET_ITEM_NOT_FOUND')

  const photoId = uuidv4()
  const extension = filename.split('.').pop() || 'jpg'
  const s3Key = `budget/${pk}/${itemId}/${photoId}.${extension}`

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

  const now = new Date().toISOString()
  await docClient.send(new PutCommand({
    TableName: POWERLIFTING_BUDGET_TABLE,
    Item: { ...stripStored(item), photo_s3_key: s3Key, updated_at: now, pk, sk: `${ITEM_PREFIX}${itemId}` } as StoredItem,
  }))

  return { photo_s3_key: s3Key }
}

export async function deleteItemPhoto(pk: string, itemId: string): Promise<void> {
  const existing = await queryItems(pk)
  const item = existing.find((i) => i.id === itemId)
  if (!item) throw new AppError(`Budget item ${itemId} not found`, 404, 'BUDGET_ITEM_NOT_FOUND')
  if (!item.photo_s3_key) return

  await s3Client.send(new DeleteObjectCommand({ Bucket: BUDGET_MEDIA_BUCKET, Key: item.photo_s3_key }))

  const now = new Date().toISOString()
  await docClient.send(new PutCommand({
    TableName: POWERLIFTING_BUDGET_TABLE,
    Item: { ...stripStored(item), photo_s3_key: null, updated_at: now, pk, sk: `${ITEM_PREFIX}${itemId}` } as StoredItem,
  }))
}

// ─── AI advisor cut flag (BUD-05) ─────────────────────────────────────────────

export async function markItemCut(pk: string, itemId: string, cut: boolean): Promise<BudgetItem> {
  const stored = await queryItems(pk)
  const existing = stored.find((i) => i.id === itemId)
  if (!existing) {
    logger.warn({ pk, module: 'budget', fn: 'markItemCut', itemId }, 'budget item not found')
    throw new AppError(`Budget item ${itemId} not found`, 404, 'BUDGET_ITEM_NOT_FOUND')
  }
  const now = new Date().toISOString()
  const normalized = normalizeBudgetItemFromStore(stripStored(existing), pk)
  const updated: BudgetItem = { ...normalized, cut_by_ai: cut, updated_at: now }
  await docClient.send(new PutCommand({
    TableName: POWERLIFTING_BUDGET_TABLE,
    Item: { ...updated, pk, sk: `${ITEM_PREFIX}${itemId}` } as StoredItem,
  }))
  logger.info({ pk, module: 'budget', fn: 'markItemCut', itemId, cut }, 'budget item cut flag toggled')
  return updated
}

// ─── AI advisor analysis (BUD-05) ─────────────────────────────────────────────

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
  const { invokeToolDirect } = await import('../utils/agent')
  const {
    getCachedBudgetAiAnalysis,
    putCachedBudgetAiAnalysis,
  } = await import('../services/analysisCache')

  const now = new Date().toISOString()
  const currentMonth = now.slice(0, 7)

  if (!refresh) {
    const cached = await getCachedBudgetAiAnalysis<BudgetAiAnalysis>(pk)
    if (cached) {
      logger.info({ pk, module: 'budget', fn: 'getBudgetAiAnalysis', cached: true }, 'budget AI analysis cache hit')
      return { ...cached.data, cached: true, generated_at: cached.generatedAt }
    }
  }

  const [config, stored] = await Promise.all([getConfig(pk), queryItems(pk)])
  const items = stored.map(stripStored).map((it) => normalizeBudgetItemFromStore(it, pk))
  const spent = spentThisMonth(items, currentMonth)

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
    spent_this_month: spent,
  }

  logger.info({ pk, module: 'budget', fn: 'getBudgetAiAnalysis', refresh, itemCount: items.length }, 'budget AI analysis generating')

  const result = (await invokeToolDirect('budget_advisor', payload)) as Partial<BudgetAiAnalysis>
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

  await putCachedBudgetAiAnalysis(pk, analysis).catch((err) => {
    logger.warn({ err, pk, module: 'budget', fn: 'getBudgetAiAnalysis' }, 'failed to cache budget AI analysis')
  })

  return analysis
}

export { CATEGORY_VALUES, PRIORITY_TIER_VALUES }
