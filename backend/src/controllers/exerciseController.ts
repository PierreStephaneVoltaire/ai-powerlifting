import { GetCommand, PutCommand } from '@aws-sdk/lib-dynamodb'
import { docClient, TABLE } from '../db/dynamo'
import { invokeToolDirect } from '../utils/agent'
import { AppError } from '../middleware/errorHandler'
import type { GlossaryExercise, GlossaryStore } from '@powerlifting/types'
import { v4 as uuidv4 } from 'uuid'

const GLOSSARY_SK = 'glossary#v1'
const YOUTUBE_HOSTS = new Set(['youtube.com', 'www.youtube.com', 'm.youtube.com', 'youtu.be'])

function sanitizeText(value: unknown): string {
  return typeof value === 'string' ? value.trim() : ''
}

function normalizeVideoUrl(value: unknown): string | undefined {
  const raw = sanitizeText(value)
  if (!raw) return undefined
  let parsed: URL
  try {
    parsed = new URL(raw)
  } catch {
    throw new AppError('Video URL must be a valid YouTube URL', 400)
  }
  if (!YOUTUBE_HOSTS.has(parsed.hostname.toLowerCase())) {
    throw new AppError('Video URL must be from YouTube', 400)
  }
  return parsed.toString()
}

function normalizeExercise(raw: GlossaryExercise): GlossaryExercise {
  const videoUrl = normalizeVideoUrl(raw.video_url)
  const normalized: GlossaryExercise = {
    ...raw,
    name: sanitizeText(raw.name),
    primary_muscles: Array.isArray(raw.primary_muscles) ? raw.primary_muscles : [],
    secondary_muscles: Array.isArray(raw.secondary_muscles) ? raw.secondary_muscles : [],
    tertiary_muscles: Array.isArray(raw.tertiary_muscles) ? raw.tertiary_muscles : [],
    description: sanitizeText(raw.description),
    how_to_perform: sanitizeText(raw.how_to_perform),
    why_do_it: sanitizeText(raw.why_do_it),
  }
  if (videoUrl) {
    normalized.video_url = videoUrl
  } else {
    delete normalized.video_url
  }
  delete (normalized as GlossaryExercise & { cues?: unknown }).cues
  delete (normalized as GlossaryExercise & { notes?: unknown }).notes
  return normalized
}

function normalizeStoredExercise(raw: GlossaryExercise): GlossaryExercise {
  try {
    return normalizeExercise(raw)
  } catch {
    const fallback = { ...raw, video_url: undefined }
    return normalizeExercise(fallback)
  }
}

export async function getGlossary(pk: string): Promise<GlossaryStore> {
  const command = new GetCommand({
    TableName: TABLE,
    Key: {
      pk,
      sk: GLOSSARY_SK,
    },
  })

  const result = await docClient.send(command)

  if (!result.Item) {
    // Return empty glossary if not found
    return {
      pk,
      sk: GLOSSARY_SK,
      exercises: [],
      updated_at: new Date().toISOString(),
    }
  }

  const glossary = result.Item as GlossaryStore
  return {
    ...glossary,
    exercises: (glossary.exercises ?? []).map(normalizeStoredExercise),
  }
}

export async function upsertExercise(pk: string, exercise: GlossaryExercise): Promise<void> {
  const glossary = await getGlossary(pk)
  exercise = normalizeExercise(exercise)

  // Generate ID if not provided
  if (!exercise.id) {
    exercise.id = uuidv4()
  }

  // Find existing exercise by ID
  const existingIndex = glossary.exercises.findIndex(e => e.id === exercise.id)

  if (existingIndex >= 0) {
    // Update existing
    glossary.exercises[existingIndex] = exercise
  } else {
    // Add new
    glossary.exercises.push(exercise)
  }

  // Sort by name
  glossary.exercises.sort((a, b) => a.name.localeCompare(b.name))
  glossary.updated_at = new Date().toISOString()

  const command = new PutCommand({
    TableName: TABLE,
    Item: glossary,
  })

  await docClient.send(command)

  // Fire-and-forget AI fatigue profile estimation if profile is missing and not manually set
  if (!exercise.fatigue_profile && exercise.fatigue_profile_source !== 'manual') {
    invokeToolDirect('fatigue_profile_estimate', {
      exercise: {
        name: exercise.name,
        category: exercise.category,
        equipment: exercise.equipment,
        primary_muscles: exercise.primary_muscles,
        secondary_muscles: exercise.secondary_muscles,
        tertiary_muscles: exercise.tertiary_muscles,
        description: exercise.description,
        how_to_perform: exercise.how_to_perform,
        why_do_it: exercise.why_do_it,
      },
      pk,
    })
      .then((profile) => {
        if (!profile) return
        return updateExerciseProfile(pk, exercise.id, {
          fatigue_profile: { axial: profile.axial, neural: profile.neural, peripheral: profile.peripheral, systemic: profile.systemic },
          fatigue_profile_source: 'ai_estimated',
          fatigue_profile_reasoning: profile.reasoning,
        })
      })
      .catch(err => console.error('Fatigue profile estimation failed:', err))
  }
}

async function updateExerciseProfile(
  pk: string,
  exerciseId: string,
  profile: { fatigue_profile: GlossaryExercise['fatigue_profile']; fatigue_profile_source: GlossaryExercise['fatigue_profile_source']; fatigue_profile_reasoning: string | null }
): Promise<void> {
  const glossary = await getGlossary(pk)
  const idx = glossary.exercises.findIndex(e => e.id === exerciseId)
  if (idx < 0) return

  glossary.exercises[idx] = {
    ...glossary.exercises[idx],
    ...profile,
  }
  glossary.updated_at = new Date().toISOString()

  const command = new PutCommand({ TableName: TABLE, Item: glossary })
  await docClient.send(command)
}

export async function removeExercise(pk: string, exerciseId: string): Promise<void> {
  const glossary = await getGlossary(pk)

  glossary.exercises = glossary.exercises.filter(e => e.id !== exerciseId)
  glossary.updated_at = new Date().toISOString()

  const command = new PutCommand({
    TableName: TABLE,
    Item: glossary,
  })

  await docClient.send(command)
}

export async function getExerciseById(pk: string, exerciseId: string): Promise<GlossaryExercise | null> {
  const glossary = await getGlossary(pk)
  return glossary.exercises.find(e => e.id === exerciseId) || null
}

export async function searchExercises(pk: string, query: string): Promise<GlossaryExercise[]> {
  const glossary = await getGlossary(pk)
  const lowerQuery = query.toLowerCase()

  return glossary.exercises.filter(e =>
    e.name.toLowerCase().includes(lowerQuery) ||
    e.description.toLowerCase().includes(lowerQuery) ||
    e.how_to_perform.toLowerCase().includes(lowerQuery) ||
    e.why_do_it.toLowerCase().includes(lowerQuery) ||
    e.primary_muscles.some(m => m.toLowerCase().includes(lowerQuery)) ||
    e.secondary_muscles.some(m => m.toLowerCase().includes(lowerQuery)) ||
    (e.tertiary_muscles ?? []).some(m => m.toLowerCase().includes(lowerQuery))
  )
}

export async function archiveExercise(pk: string, id: string): Promise<void> {
  const glossary = await getGlossary(pk)
  const idx = glossary.exercises.findIndex(e => e.id === id)
  if (idx < 0) return

  glossary.exercises[idx].archived = true
  glossary.updated_at = new Date().toISOString()

  await docClient.send(new PutCommand({ TableName: TABLE, Item: glossary }))
}

export async function unarchiveExercise(pk: string, id: string): Promise<void> {
  const glossary = await getGlossary(pk)
  const idx = glossary.exercises.findIndex(e => e.id === id)
  if (idx < 0) return

  glossary.exercises[idx].archived = false
  glossary.updated_at = new Date().toISOString()

  await docClient.send(new PutCommand({ TableName: TABLE, Item: glossary }))
}

export async function setE1rmEstimate(
  pk: string,
  id: string,
  valueKg: number,
  method: 'manual' | 'ai_backfill' | 'logged' = 'manual'
): Promise<void> {
  const glossary = await getGlossary(pk)
  const idx = glossary.exercises.findIndex(e => e.id === id)
  if (idx < 0) return

  glossary.exercises[idx].e1rm_estimate = {
    value_kg: valueKg,
    method,
    basis: method === 'manual' ? 'Manual entry' : '',
    confidence: method === 'manual' ? 'medium' : 'low',
    set_at: new Date().toISOString(),
    manually_overridden: method === 'manual'
  }
  glossary.updated_at = new Date().toISOString()

  await docClient.send(new PutCommand({ TableName: TABLE, Item: glossary }))
}

export async function estimateExerciseE1rm(pk: string, id: string): Promise<any> {
  return invokeToolDirect('glossary_estimate_e1rm', { id, pk })
}

export async function estimateExerciseFatigue(pk: string, id: string): Promise<any> {
  return invokeToolDirect('glossary_estimate_fatigue', { id, pk })
}

export async function estimateExerciseMuscles(pk: string, id: string): Promise<any> {
  return invokeToolDirect('glossary_estimate_muscles', { id, pk })
}
