import { Request, Response } from 'express'
import {
  getProfileSettingsByMappedPk,
  getProfileSettingsByNickname,
  mappedPkForSettings,
  publicProfile,
  searchProfiles,
} from '../services/userSettings'
import { AppError } from '../middleware/errorHandler'
import * as programController from './programController'
import * as videoController from './videoController'
import type { Program } from '@powerlifting/types'

type BigThreeLift = 'squat' | 'bench' | 'deadlift'
type Sex = 'male' | 'female'

const DOTS_COEFFICIENTS: Record<Sex, { a: number; b: number; c: number; d: number; e: number }> = {
  male: {
    a: -307.75076,
    b: 24.0900756,
    c: -0.1918759221,
    d: 0.0007391293,
    e: -0.000001093,
  },
  female: {
    a: -57.96288,
    b: 13.6175032,
    c: -0.1126655495,
    d: 0.0005158568,
    e: -0.0000010706,
  },
}

function positiveNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) && value > 0 ? value : null
}

function targetMax(program: Program, lift: BigThreeLift): number | null {
  if (lift === 'squat') return positiveNumber(program.meta.target_squat_kg)
  if (lift === 'bench') return positiveNumber(program.meta.target_bench_kg)
  return positiveNumber(program.meta.target_dl_kg)
}

function hasCompletedSet(exercise: Program['sessions'][number]['exercises'][number]): boolean {
  const setCount = Math.max(0, Math.round(Number(exercise.sets) || 0))

  if (exercise.set_statuses?.length) {
    for (let index = 0; index < setCount; index += 1) {
      const status = exercise.set_statuses[index]
      if (status === 'completed' || status === undefined) return true
    }
    return false
  }

  if (exercise.failed_sets?.length) {
    const legacySetCount = Math.max(setCount, exercise.failed_sets.length)
    for (let index = 0; index < legacySetCount; index += 1) {
      if (exercise.failed_sets[index] !== true) return true
    }
    return false
  }

  if (exercise.failed) return false
  return setCount > 0
}

function bestSessionLift(program: Program, lift: BigThreeLift): number | null {
  let best = 0
  for (const session of program.sessions ?? []) {
    if (!session.completed || session.status === 'skipped') continue
    for (const exercise of session.exercises) {
      if (!exercise.kg || exercise.kg <= best) continue
      if (!hasCompletedSet(exercise)) continue
      if (exercise.name.toLowerCase().includes(lift)) best = exercise.kg
    }
  }
  return best > 0 ? best : null
}

function latestSessionBodyweight(program: Program): number | null {
  return (program.sessions ?? [])
    .filter((session) => typeof session.body_weight_kg === 'number' && session.body_weight_kg > 0)
    .sort((a, b) => b.date.localeCompare(a.date))[0]?.body_weight_kg ?? null
}

function resolvedLift(program: Program, lift: BigThreeLift): number | null {
  return positiveNumber(program.current_maxes?.[lift])
    ?? positiveNumber(program.meta.manual_maxes?.[lift])
    ?? bestSessionLift(program, lift)
    ?? targetMax(program, lift)
}

function calculateDots(totalKg: number, bodyweightKg: number, sex: Sex): number | null {
  if (totalKg <= 0 || bodyweightKg <= 0) return null
  const c = DOTS_COEFFICIENTS[sex]
  const denominator = c.a + c.b * bodyweightKg + c.c * bodyweightKg ** 2 + c.d * bodyweightKg ** 3 + c.e * bodyweightKg ** 4
  if (Math.abs(denominator) < 1e-12) return null
  return Number(((500 / denominator) * totalKg).toFixed(2))
}

async function buildProfileResponse(settings: Awaited<ReturnType<typeof getProfileSettingsByNickname>>, viewerUsername?: string) {
  if (!settings) return null

  const base = publicProfile(settings, viewerUsername)
  const pk = mappedPkForSettings(settings)

  try {
    const program = await programController.getProgram(pk, 'current')
    const squat = resolvedLift(program, 'squat')
    const bench = resolvedLift(program, 'bench')
    const deadlift = resolvedLift(program, 'deadlift')
    const total = [squat, bench, deadlift].every((value) => value !== null)
      ? (squat ?? 0) + (bench ?? 0) + (deadlift ?? 0)
      : null
    const bodyweight = positiveNumber(program.meta.current_body_weight_kg)
      ?? latestSessionBodyweight(program)
      ?? positiveNumber(program.meta.last_comp?.body_weight_kg)
    const sex = program.meta.sex === 'female' ? 'female' : 'male'
    const dots = total !== null && bodyweight !== null && sex
      ? calculateDots(total, bodyweight, sex)
      : null
    const videoLibrary = await videoController.getVideoLibrary(pk, 'current', undefined, 'newest')

    return {
      ...base,
      federation: program.meta.federation || null,
      weight_class_kg: positiveNumber(program.meta.weight_class_kg),
      practicing_for: program.meta.practicing_for || null,
      summary: {
        squat_kg: squat,
        bench_kg: bench,
        deadlift_kg: deadlift,
        total_kg: total,
        bodyweight_kg: bodyweight,
        dots,
      },
      lift_videos: videoLibrary.videos.slice(0, 24),
    }
  } catch {
    return {
      ...base,
      federation: null,
      weight_class_kg: null,
      practicing_for: null,
      summary: {
        squat_kg: null,
        bench_kg: null,
        deadlift_kg: null,
        total_kg: null,
        bodyweight_kg: null,
        dots: null,
      },
      lift_videos: [],
    }
  }
}

export async function searchProfilesHandler(req: Request, res: Response): Promise<void> {
  const query = typeof req.query.q === 'string' ? req.query.q : ''
  const profiles = await searchProfiles(query, req.user?.username)
  res.json({ data: profiles, error: null })
}

export async function getCurrentProfileHandler(req: Request, res: Response): Promise<void> {
  const settings = await getProfileSettingsByMappedPk(req.mapped_pk ?? 'operator', req.user?.username)
  const profile = await buildProfileResponse(settings, req.user?.username)
  if (!profile) {
    throw new AppError('Profile not found', 404)
  }

  res.json({ data: profile, error: null })
}

export async function getProfileHandler(req: Request, res: Response): Promise<void> {
  const settings = await getProfileSettingsByNickname(req.params.nickname, req.user?.username)
  const profile = await buildProfileResponse(settings, req.user?.username)
  if (!profile) {
    throw new AppError('Profile not found', 404)
  }

  res.json({ data: profile, error: null })
}
