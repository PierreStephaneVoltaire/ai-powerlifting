import { valkey } from '../utils/valkey'

function recordKey(athlete: string, key: string): string {
  return `pl:analysis:${athlete}:${key}`
}

export async function readAnalysisRecord<T>(athlete: string, key: string): Promise<T | null> {
  const raw = await (await valkey()).get(recordKey(athlete, key))
  return raw ? JSON.parse(raw) as T : null
}

export async function writeAnalysisRecord(athlete: string, key: string, value: unknown, createOnly = false): Promise<boolean> {
  const result = await (await valkey()).set(recordKey(athlete, key), JSON.stringify(value), createOnly ? { NX: true } : {})
  return result === 'OK'
}
