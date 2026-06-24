import { QueryCommand, PutCommand, DeleteCommand, GetCommand } from '@aws-sdk/lib-dynamodb'
import { S3Client, DeleteObjectCommand } from '@aws-sdk/client-s3'
import { Upload } from '@aws-sdk/lib-storage'
import { v4 as uuidv4 } from 'uuid'
import { docClient, POWERLIFTING_BUDGET_TABLE, BUDGET_MEDIA_BUCKET } from '../db/dynamo'
import { AppError } from '../middleware/errorHandler'
import type {
  BudgetItem,
  BudgetConfig,
  BudgetStore,
  BudgetCategory,
  BudgetPriority,
  BudgetRecurrence,
  EquipmentCondition,
  TrainingPriority,
} from '@powerlifting/types'

const CONFIG_SK = 'CONFIG#budget'
const ITEM_PREFIX = 'ITEM#'

const CATEGORY_VALUES: ReadonlyArray<BudgetCategory> = [
  'equipment',
  'supplement',
  'gym_membership',
  'federation_membership',
  'competition_entry',
]
const PRIORITY_VALUES: ReadonlyArray<BudgetPriority> = ['buy_now', 'buy_later', 'optional', 'drop']
const RECURRENCE_VALUES: ReadonlyArray<BudgetRecurrence> = ['one_time', 'monthly', 'multi_month']
const CONDITION_VALUES: ReadonlyArray<EquipmentCondition> = ['good', 'worn', 'needs_replacement', 'unknown']
const TRAINING_VALUES: ReadonlyArray<TrainingPriority> = ['low', 'medium', 'high']

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

function pickEnum<T extends string>(value: unknown, allowed: ReadonlyArray<T>, fallback: T): T {
  return typeof value === 'string' && (allowed as ReadonlyArray<string>).includes(value) ? (value as T) : fallback
}

function toFiniteNumber(value: unknown): number {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string' && value.trim() !== '') {
    const num = Number(value)
    if (Number.isFinite(num)) return num
  }
  return 0
}

function normalizeConfig(raw: unknown): BudgetConfig {
  const r = isPlainObject(raw) ? raw : {}
  return {
    monthly_budget: Math.max(0, toFiniteNumber(r.monthly_budget)),
    currency: typeof r.currency === 'string' && r.currency.trim() ? r.currency.trim() : 'CAD',
    budget_start_month: typeof r.budget_start_month === 'string' && r.budget_start_month ? r.budget_start_month : undefined,
  }
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function normalizeItem(raw: unknown, existingCreatedAt?: string): BudgetItem | null {
  if (!isPlainObject(raw)) return null
  const r = raw
  const id = typeof r.id === 'string' && r.id.length > 0 ? r.id : newItemId()
  const now = new Date().toISOString()

  const out: BudgetItem = {
    id,
    name: typeof r.name === 'string' ? r.name : '',
    category: pickEnum(r.category, CATEGORY_VALUES, 'equipment'),
    cost: Math.max(0, toFiniteNumber(r.cost)),
    recurrence: pickEnum(r.recurrence, RECURRENCE_VALUES, 'one_time'),
    priority: pickEnum(r.priority, PRIORITY_VALUES, 'optional'),
    created_at: existingCreatedAt ?? (typeof r.created_at === 'string' ? r.created_at : now),
    updated_at: now,
  }

  if (typeof r.currency === 'string' && r.currency.trim()) out.currency = r.currency.trim()
  if (typeof r.months === 'number' && Number.isFinite(r.months) && r.months > 0) out.months = Math.round(r.months)
  if (typeof r.start_month === 'string' && r.start_month) out.start_month = r.start_month
  if (typeof r.needed_for_comp_day === 'boolean') out.needed_for_comp_day = r.needed_for_comp_day
  if (typeof r.comp_master_id === 'string' && r.comp_master_id) out.comp_master_id = r.comp_master_id
  if (typeof r.training_priority === 'string') out.training_priority = pickEnum(r.training_priority, TRAINING_VALUES, 'medium')
  if (typeof r.equipment_condition === 'string') out.equipment_condition = pickEnum(r.equipment_condition, CONDITION_VALUES, 'unknown')
  if (typeof r.equipment_comp_legal === 'boolean') out.equipment_comp_legal = r.equipment_comp_legal
  if (typeof r.photo_s3_key === 'string') out.photo_s3_key = r.photo_s3_key || null
  if (typeof r.photo_url === 'string') out.photo_url = r.photo_url || null
  if (typeof r.purchased === 'boolean') out.purchased = r.purchased
  if (typeof r.purchased_date === 'string') out.purchased_date = r.purchased_date || null
  if (typeof r.notes === 'string') out.notes = r.notes
  if (typeof r.federation_abbreviation === 'string' && r.federation_abbreviation) out.federation_abbreviation = r.federation_abbreviation

  return out
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

async function getConfig(pk: string): Promise<BudgetConfig> {
  const result = await docClient.send(new GetCommand({
    TableName: POWERLIFTING_BUDGET_TABLE,
    Key: { pk, sk: CONFIG_SK },
  }))
  if (!result.Item) return { monthly_budget: 0, currency: 'CAD' }
  const stored = result.Item as StoredConfig
  return normalizeConfig(stored.config)
}

export async function getBudget(pk: string): Promise<BudgetStore> {
  const [config, storedItems] = await Promise.all([getConfig(pk), queryItems(pk)])
  const items = storedItems
    .map(({ pk: _pk, sk: _sk, ...rest }) => rest)
    .map((it) => normalizeItem(it, it.created_at))
    .filter((i): i is BudgetItem => i !== null)
  return { config, items }
}

export async function putBudget(
  pk: string,
  configRaw: unknown,
  itemsRaw: unknown[],
): Promise<void> {
  const config = normalizeConfig(configRaw)
  const existing = await queryItems(pk)
  const byId = new Map<string, StoredItem>()
  for (const it of existing) byId.set(it.id, it)
  const incomingIds = new Set<string>()
  const now = new Date().toISOString()

  await docClient.send(new PutCommand({
    TableName: POWERLIFTING_BUDGET_TABLE,
    Item: { pk, sk: CONFIG_SK, config, updated_at: now } as StoredConfig,
  }))

  for (const raw of itemsRaw) {
    const existingItem = isPlainObject(raw) && typeof raw.id === 'string' ? byId.get(raw.id) : undefined
    const normalized = normalizeItem(raw, existingItem?.created_at)
    if (!normalized) continue
    incomingIds.add(normalized.id)
    await docClient.send(new PutCommand({
      TableName: POWERLIFTING_BUDGET_TABLE,
      Item: { ...normalized, pk, sk: `${ITEM_PREFIX}${normalized.id}` } as StoredItem,
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
}

export async function uploadItemPhoto(
  pk: string,
  itemId: string,
  file: Buffer,
  filename: string,
  mimeType: string,
): Promise<{ photo_s3_key: string }> {
  const existing = await queryItems(pk)
  const item = existing.find((i) => i.id === itemId)
  if (!item) throw new AppError(`Budget item ${itemId} not found`, 404)

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
      console.warn('Failed to delete previous budget photo:', err)
    }
  }

  const now = new Date().toISOString()
  await docClient.send(new PutCommand({
    TableName: POWERLIFTING_BUDGET_TABLE,
    Item: { ...item, photo_s3_key: s3Key, photo_url: null, updated_at: now, pk, sk: `${ITEM_PREFIX}${itemId}` } as StoredItem,
  }))

  return { photo_s3_key: s3Key }
}

export async function deleteItemPhoto(pk: string, itemId: string): Promise<void> {
  const existing = await queryItems(pk)
  const item = existing.find((i) => i.id === itemId)
  if (!item) throw new AppError(`Budget item ${itemId} not found`, 404)
  if (!item.photo_s3_key) return

  await s3Client.send(new DeleteObjectCommand({ Bucket: BUDGET_MEDIA_BUCKET, Key: item.photo_s3_key }))

  const now = new Date().toISOString()
  await docClient.send(new PutCommand({
    TableName: POWERLIFTING_BUDGET_TABLE,
    Item: { ...item, photo_s3_key: null, photo_url: null, updated_at: now, pk, sk: `${ITEM_PREFIX}${itemId}` } as StoredItem,
  }))
}
