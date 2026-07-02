import { invokeLambda } from '../utils/lambda'
import { invokeToolDirect } from '../utils/agent'
import { AppError } from '../middleware/errorHandler'
import type { GlossaryExercise, GlossaryStore } from '@powerlifting/types'
import { v4 as uuidv4 } from 'uuid'

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
  const glossary = await invokeLambda('exercise_get_glossary', { pk })
  return {
    pk,
    sk: 'glossary#v1',
    exercises: Array.isArray(glossary?.exercises)
      ? glossary.exercises.map(normalizeStoredExercise)
      : [],
    updated_at: glossary?.updated_at || new Date().toISOString(),
  }
}

export async function upsertExercise(pk: string, exercise: GlossaryExercise): Promise<void> {
  exercise = normalizeExercise(exercise)
  if (!exercise.id) {
    exercise.id = uuidv4()
  }
  await invokeLambda('exercise_upsert', { pk, exercise })
}

export async function removeExercise(pk: string, exerciseId: string): Promise<void> {
  await invokeLambda('exercise_remove', { pk, id: exerciseId })
}

export async function getExerciseById(pk: string, exerciseId: string): Promise<GlossaryExercise | null> {
  const glossary = await getGlossary(pk)
  return glossary.exercises.find((e) => e.id === exerciseId) || null
}

export async function searchExercises(pk: string, query: string): Promise<GlossaryExercise[]> {
  const glossary = await getGlossary(pk)
  const lowerQuery = query.toLowerCase()

  return glossary.exercises.filter((e) =>
    e.name.toLowerCase().includes(lowerQuery) ||
    e.description.toLowerCase().includes(lowerQuery) ||
    e.how_to_perform.toLowerCase().includes(lowerQuery) ||
    e.why_do_it.toLowerCase().includes(lowerQuery) ||
    e.primary_muscles.some((m) => m.toLowerCase().includes(lowerQuery)) ||
    e.secondary_muscles.some((m) => m.toLowerCase().includes(lowerQuery)) ||
    (e.tertiary_muscles ?? []).some((m) => m.toLowerCase().includes(lowerQuery)),
  )
}

export async function archiveExercise(pk: string, id: string): Promise<void> {
  await invokeLambda('exercise_archive', { pk, id })
}

export async function unarchiveExercise(pk: string, id: string): Promise<void> {
  await invokeLambda('exercise_unarchive', { pk, id })
}

export async function setE1rmEstimate(
  pk: string,
  id: string,
  valueKg: number,
  method: 'manual' | 'ai_backfill' | 'logged' = 'manual',
): Promise<void> {
  await invokeLambda('exercise_set_e1rm', { pk, id, value_kg: valueKg, method })
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
