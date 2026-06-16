import { GetCommand, PutCommand, QueryCommand, UpdateCommand } from '@aws-sdk/lib-dynamodb'
import { docClient, POWERLIFTING_USER_FEDERATIONS_TABLE, TABLE } from '../db/dynamo'
import type {
  AgeCategory,
  FederationDisplayOptions,
  FederationLevel,
  FederationLibrary,
  FederationSex,
  FederationStandard,
  FederationStandardEntry,
  MasterFederation,
} from '@powerlifting/types'

const FEDERATIONS_PK = 'operator'
const FEDERATIONS_SK = 'federations#v1'

const AGE_CATEGORY_VALUES: ReadonlyArray<AgeCategory> = [
  'open',
  'subjunior',
  'junior',
  'master1',
  'master2',
  'master3',
  'master4',
]

const LEVEL_VALUES: ReadonlyArray<FederationLevel> = ['national', 'regional']

const SEX_VALUES: ReadonlyArray<FederationSex> = ['male', 'female']

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function newEntryId(): string {
  return `std-${Date.now()}-${Math.floor(Math.random() * 1e6)}`
}

function pickAgeCategory(value: unknown): AgeCategory | undefined {
  if (typeof value !== 'string') return undefined
  const normalized = value.trim().toLowerCase().replace(/[\s-]+/g, '')
  if ((AGE_CATEGORY_VALUES as ReadonlyArray<string>).includes(normalized)) {
    return normalized as AgeCategory
  }
  if (normalized === 'masters1') return 'master1'
  if (normalized === 'masters2') return 'master2'
  if (normalized === 'masters3') return 'master3'
  if (normalized === 'masters4') return 'master4'
  return undefined
}

function pickSex(value: unknown): FederationSex | undefined {
  if (typeof value !== 'string') return undefined
  const normalized = value.trim().toLowerCase()
  return (SEX_VALUES as ReadonlyArray<string>).includes(normalized)
    ? (normalized as FederationSex)
    : undefined
}

function pickLevel(value: unknown): FederationLevel | undefined {
  if (typeof value !== 'string') return undefined
  const normalized = value.trim().toLowerCase()
  return (LEVEL_VALUES as ReadonlyArray<string>).includes(normalized)
    ? (normalized as FederationLevel)
    : undefined
}

function toFiniteNumber(value: unknown): number {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string' && value.trim() !== '') {
    const num = Number(value)
    if (Number.isFinite(num)) return num
  }
  return 0
}

function coerceEntry(raw: unknown): FederationStandardEntry | null {
  if (!isPlainObject(raw)) return null
  const id = typeof raw.id === 'string' && raw.id.length > 0 ? raw.id : newEntryId()
  const total = toFiniteNumber(raw.qualifying_total ?? raw.total)
  return {
    id,
    sex: pickSex(raw.sex),
    age_class: pickAgeCategory(raw.age_class),
    weight_class: typeof raw.weight_class === 'string' && raw.weight_class.trim() !== ''
      ? raw.weight_class.trim()
      : undefined,
    level: pickLevel(raw.level),
    category: typeof raw.category === 'string' && raw.category.trim() !== ''
      ? raw.category.trim()
      : undefined,
    qualifying_total: total,
  }
}

function entriesFromBrackets(brackets: unknown): FederationStandardEntry[] {
  const out: FederationStandardEntry[] = []
  if (!isPlainObject(brackets)) return out
  for (const sexRaw of ['male', 'female'] as FederationSex[]) {
    const sexMap = brackets[sexRaw]
    if (!isPlainObject(sexMap)) continue
    for (const [ageRaw, wcMap] of Object.entries(sexMap)) {
      const age = pickAgeCategory(ageRaw)
      if (!isPlainObject(wcMap)) continue
      for (const [weightClass, total] of Object.entries(wcMap)) {
        out.push({
          id: newEntryId(),
          sex: sexRaw,
          age_class: age,
          weight_class: weightClass,
          qualifying_total: toFiniteNumber(total),
        })
      }
    }
  }
  return out
}

function entriesFromLegacyMaps(
  national: unknown, regional: unknown,
): FederationStandardEntry[] {
  const out: FederationStandardEntry[] = []
  for (const [level, map] of [['national', national], ['regional', regional]] as const) {
    if (!isPlainObject(map)) continue
    for (const [weightClass, total] of Object.entries(map)) {
      out.push({
        id: newEntryId(),
        level,
        weight_class: weightClass,
        qualifying_total: toFiniteNumber(total),
      })
    }
  }
  return out
}

function normalizeEntries(raw: unknown): FederationStandardEntry[] {
  if (Array.isArray(raw)) {
    const out: FederationStandardEntry[] = []
    for (const item of raw) {
      const entry = coerceEntry(item)
      if (entry) out.push(entry)
    }
    return out
  }
  if (isPlainObject(raw)) {
    if (isPlainObject(raw.male) || isPlainObject(raw.female)) {
      return entriesFromBrackets(raw)
    }
    if (isPlainObject(raw.national) || isPlainObject(raw.regional)) {
      return entriesFromLegacyMaps(raw.national, raw.regional)
    }
  }
  return []
}

function normalizeStandard(standard: unknown): FederationStandard | null {
  if (!isPlainObject(standard)) return null
  const start = typeof standard.start_date === 'string' && standard.start_date.length > 0
    ? standard.start_date
    : ''
  const end = typeof standard.end_date === 'string' && standard.end_date.length > 0
    ? standard.end_date
    : ''
  return {
    start_date: start,
    end_date: end,
    entries: normalizeEntries(standard.entries ?? standard),
  }
}

function normalizeDisplayOptions(raw: unknown): FederationDisplayOptions | undefined {
  if (!isPlainObject(raw)) return undefined
  return {
    show_sex: typeof raw.show_sex === 'boolean' ? raw.show_sex : true,
    show_age_class: typeof raw.show_age_class === 'boolean' ? raw.show_age_class : true,
    show_weight_class: typeof raw.show_weight_class === 'boolean' ? raw.show_weight_class : true,
    show_category: typeof raw.show_category === 'boolean' ? raw.show_category : true,
  }
}

function normalizeFederation(raw: unknown): MasterFederation {
  const f = isPlainObject(raw) ? raw : {}
  const standardsRaw = isPlainObject(f.standards) ? f.standards : {}
  const standards: Record<string, FederationStandard> = {}
  for (const [year, std] of Object.entries(standardsRaw)) {
    const normalized = normalizeStandard(std)
    if (normalized) standards[year] = normalized
  }
  return {
    pk: typeof f.pk === 'string' ? f.pk : '',
    sk: typeof f.sk === 'string' ? f.sk : '',
    name: typeof f.name === 'string' ? f.name : '',
    abbreviation: typeof f.abbreviation === 'string' ? f.abbreviation : null,
    region: typeof f.region === 'string' && f.region.trim() ? f.region.trim() : null,
    website_url: typeof f.website_url === 'string' ? f.website_url : null,
    status: f.status === 'archived' ? 'archived' : 'active',
    source_slug: typeof f.source_slug === 'string' ? f.source_slug : null,
    has_standards: Boolean(f.has_standards),
    standard_unit: f.standard_unit === 'kg' || f.standard_unit === 'dots' ? f.standard_unit : null,
    standards,
    display_options: normalizeDisplayOptions(f.display_options),
    created_at: typeof f.created_at === 'string' ? f.created_at : new Date().toISOString(),
    updated_at: typeof f.updated_at === 'string' ? f.updated_at : new Date().toISOString(),
  }
}

export async function listFederations(): Promise<MasterFederation[]> {
  const items: MasterFederation[] = []
  let lastKey: Record<string, unknown> | undefined
  do {
    const resp = await docClient.send(new QueryCommand({
      TableName: POWERLIFTING_USER_FEDERATIONS_TABLE,
      KeyConditionExpression: 'pk = :pk',
      ExpressionAttributeValues: { ':pk': FEDERATIONS_PK },
      ExclusiveStartKey: lastKey,
    }))
    for (const it of resp.Items ?? []) items.push(normalizeFederation(it))
    lastKey = resp.LastEvaluatedKey
  } while (lastKey)
  return items
}

export type FederationUpdate = {
  name?: string
  abbreviation?: string | null
  region?: string | null
  website_url?: string | null
  status?: 'active' | 'archived'
  has_standards?: boolean
  standard_unit?: 'kg' | 'dots' | null
  standards?: Record<string, FederationStandard>
  display_options?: FederationDisplayOptions | null
}

export async function updateFederation(masterId: string, updates: FederationUpdate): Promise<void> {
  const names: Record<string, string> = {}
  const values: Record<string, unknown> = {}
  const sets: string[] = []
  let i = 0

  for (const [k, v] of Object.entries(updates)) {
    const n = `#f${i}`
    const ph = `:v${i}`
    names[n] = k
    values[ph] = v
    sets.push(`${n} = ${ph}`)
    i += 1
  }

  if (sets.length === 0) return

  names['#u'] = 'updated_at'
  values[':u'] = new Date().toISOString()
  sets.push('#u = :u')

  await docClient.send(new UpdateCommand({
    TableName: POWERLIFTING_USER_FEDERATIONS_TABLE,
    Key: { pk: FEDERATIONS_PK, sk: `FED#${masterId}` },
    UpdateExpression: 'SET ' + sets.join(', '),
    ExpressionAttributeNames: names,
    ExpressionAttributeValues: values,
  }))
}

function emptyLibrary(pk: string): FederationLibrary {
  return {
    pk,
    sk: FEDERATIONS_SK,
    updated_at: new Date().toISOString(),
    federations: [],
    qualification_standards: [],
  }
}

export async function getFederationLibrary(pk: string): Promise<FederationLibrary> {
  const result = await docClient.send(new GetCommand({
    TableName: TABLE,
    Key: { pk, sk: FEDERATIONS_SK },
  }))

  if (!result.Item) {
    return emptyLibrary(pk)
  }

  return result.Item as FederationLibrary
}

export async function updateFederationLibrary(
  pk: string,
  library: Pick<FederationLibrary, 'federations' | 'qualification_standards'>,
): Promise<FederationLibrary> {
  const nextLibrary: FederationLibrary = {
    pk,
    sk: FEDERATIONS_SK,
    updated_at: new Date().toISOString(),
    federations: library.federations ?? [],
    qualification_standards: library.qualification_standards ?? [],
  }

  await docClient.send(new PutCommand({
    TableName: TABLE,
    Item: nextLibrary,
  }))

  return nextLibrary
}
