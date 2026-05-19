import { Router } from 'express'
import crypto from 'crypto'
import * as sessionController from '../controllers/sessionController'
import * as programController from '../controllers/programController'
import { invokeSpecialistJson } from '../utils/agent'
import {
  getCachedWindowAnalysis,
  markMarkdownExportDirty,
} from '../services/analysisCache'
import type { Session, Exercise, SessionStatus, SessionWellness, FailedSetReason } from '@powerlifting/types'

export const sessionsRouter = Router({ mergeParams: true })

function todayIso(): string {
  return new Date().toISOString().slice(0, 10)
}

function fallbackNoteDraft(session: Session, answers: Record<string, unknown>): string {
  const parts: string[] = []
  const overall = String(answers.overall || '').trim()
  const technique = String(answers.technique || '').trim()
  const failedSets = String(answers.failedSets || '').trim()
  const skippedWork = String(answers.skippedWork || '').trim()
  const rpeMismatch = String(answers.rpeMismatch || '').trim()
  const plannedVsExecuted = String(answers.plannedVsExecuted || '').trim()
  const freeText = String(answers.freeText || '').trim()

  parts.push(`Session on ${session.date}${session.session_rpe ? ` felt like RPE ${session.session_rpe}` : ''}.`)
  if (overall) parts.push(`Overall: ${overall}`)
  if (technique) parts.push(`Technique: ${technique}`)
  if (failedSets) parts.push(`Failed sets/RPE: ${failedSets}`)
  if (skippedWork) parts.push(`Skipped or missed work: ${skippedWork}`)
  if (rpeMismatch) parts.push(`Load/RPE mismatch: ${rpeMismatch}`)
  if (plannedVsExecuted) parts.push(`Planned vs executed: ${plannedVsExecuted}`)
  if (freeText) parts.push(freeText)

  return parts.filter(Boolean).join('\n')
}

const SESSION_TOOL_SCOPE_MESSAGE = 'This helper only supports session notes or auto-regulation for the selected exercise in this exact session.'
const OUT_OF_SCOPE_PATTERNS = [
  /\b(when|what|show|tell|list|view|find|lookup|look up)\b.{0,50}\b(next|future|upcoming)\b.{0,35}\b(workout|session|training day)\b/i,
  /\b(create|add|make|schedule|insert)\b.{0,30}\b(new\s+)?(workout|session|training day)\b/i,
  /\b(delete|remove|drop|cancel|erase)\b.{0,30}\b(this|that|the|today'?s)?\s*(workout|session|training day|program)\b/i,
  /\b(reschedule|move|postpone|advance)\b.{0,30}\b(this|that|the|today'?s)?\s*(workout|session|training day)\b/i,
  /\b(complete|finish|mark|log)\b.{0,30}\b(this|that|the|today'?s)?\s*(workout|session)\b/i,
  /\b(program overview|show my program|what'?s my program)\b/i,
]

function collectUserText(value: unknown): string {
  if (typeof value === 'string') return value
  if (Array.isArray(value)) return value.map(collectUserText).join('\n')
  if (value && typeof value === 'object') {
    return Object.values(value as Record<string, unknown>).map(collectUserText).join('\n')
  }
  return ''
}

function hasOutOfScopeSessionRequest(value: unknown): boolean {
  const text = collectUserText(value)
  return OUT_OF_SCOPE_PATTERNS.some((pattern) => pattern.test(text))
}

const SET_STATUSES = new Set(['pending', 'completed', 'failed', 'skipped'])
const FAILED_SET_REASONS = new Set([
  'strength_failure',
  'technical_failure',
  'command_failure',
  'grip',
  'depth',
  'pause',
  'lockout',
  'balance',
  'pain',
  'fatigue',
  'misload_bad_attempt_selection',
])

function normalizeSetStatuses(exercise: Exercise, completed = false): Array<'pending' | 'completed' | 'failed' | 'skipped'> {
  const setCount = Math.max(0, Math.round(Number(exercise.sets) || 0))
  const fallback = completed ? 'completed' : 'pending'
  const rawStatuses = Array.isArray((exercise as any).set_statuses)
    ? (exercise as any).set_statuses
    : Array.from({ length: setCount }, (_, index) => exercise.failed_sets?.[index] ? 'failed' : fallback)
  const statuses = rawStatuses.slice(0, setCount).map((status: unknown) =>
    typeof status === 'string' && SET_STATUSES.has(status) ? status as 'pending' | 'completed' | 'failed' | 'skipped' : fallback
  )
  while (statuses.length < setCount) statuses.push(fallback)
  return statuses
}

function normalizeFailedSetReasons(
  exercise: Exercise,
  statuses = normalizeSetStatuses(exercise),
): FailedSetReason[][] {
  const source = Array.isArray((exercise as any).failed_set_reasons)
    ? (exercise as any).failed_set_reasons
    : []
  return statuses.map((status, setIndex) => {
    if (status !== 'failed') return []
    const rawReasons = Array.isArray(source[setIndex]) ? source[setIndex] : []
    const reasons: FailedSetReason[] = []
    for (const rawReason of rawReasons) {
      if (
        typeof rawReason === 'string' &&
        FAILED_SET_REASONS.has(rawReason) &&
        !reasons.includes(rawReason as FailedSetReason)
      ) {
        reasons.push(rawReason as FailedSetReason)
      }
    }
    return reasons
  })
}

function sanitizeExercise(exercise: Exercise, completed = false): Exercise {
  const sets = Math.max(0, Math.round(Number(exercise.sets) || 0))
  const reps = Math.max(0, Math.round(Number(exercise.reps) || 0))
  const rawKg = (exercise as { kg?: unknown }).kg
  const kg = rawKg === null || rawKg === undefined || rawKg === ''
    ? null
    : Number(rawKg)
  const set_statuses = normalizeSetStatuses({ ...exercise, sets }, completed)
  const failed_sets = set_statuses.map((status) => status === 'failed')
  const failed_set_reasons = normalizeFailedSetReasons({ ...exercise, sets }, set_statuses)
  return {
    name: String(exercise.name || '').slice(0, 160),
    sets,
    reps,
    kg: typeof kg === 'number' && Number.isFinite(kg) ? kg : null,
    notes: String(exercise.notes || '').slice(0, 4000),
    failed: failed_sets.some(Boolean),
    failed_sets,
    set_statuses,
    failed_set_reasons,
    load_source: exercise.load_source,
    rpe_target: exercise.rpe_target ?? null,
  } as Exercise
}

function sanitizeProposedExercises(
  rawProposed: unknown,
  session: Session,
  exerciseIndex: number,
): Exercise[] | null {
  if (!Array.isArray(rawProposed)) return null
  const base = (session.exercises || []).map((exercise) => sanitizeExercise(exercise, session.completed))
  const rawSelected = rawProposed[exerciseIndex]
  if (!rawSelected || typeof rawSelected !== 'object') return null

  const current = base[exerciseIndex]
  if (!current) return null
  const proposed = sanitizeExercise({ ...current, ...(rawSelected as Partial<Exercise>) }, session.completed)
  const currentStatuses = normalizeSetStatuses(current, session.completed)
  const currentReasons = normalizeFailedSetReasons(current, currentStatuses)
  const locked = currentStatuses
    .map((status, index) => ({ status, reasons: currentReasons[index] || [] }))
    .filter((entry) => entry.status === 'completed' || entry.status === 'failed')
  if (proposed.sets < locked.length) proposed.sets = locked.length

  const proposedStatuses = normalizeSetStatuses(proposed, session.completed)
  const proposedReasons = normalizeFailedSetReasons(proposed, proposedStatuses)
  for (let i = 0; i < locked.length; i += 1) proposedStatuses[i] = locked[i].status
  for (let i = 0; i < locked.length; i += 1) {
    proposedReasons[i] = locked[i].status === 'failed' ? locked[i].reasons : []
  }
  while (proposedStatuses.length < proposed.sets) proposedStatuses.push('pending')
  while (proposedReasons.length < proposed.sets) proposedReasons.push([])
  proposed.set_statuses = proposedStatuses.slice(0, proposed.sets)
  proposed.failed_set_reasons = proposedReasons.slice(0, proposed.sets)
  proposed.failed_sets = proposed.set_statuses.map((status) => status === 'failed')
  proposed.failed = proposed.failed_sets.some(Boolean)

  base[exerciseIndex] = proposed
  return base
}

function normalizeCoachResponse(raw: any, session?: Session, exerciseIndex?: number): any {
  const status = ['needs_more_info', 'denied', 'ready'].includes(raw?.status)
    ? raw.status
    : 'needs_more_info'
  const proposed = status === 'ready' && session && exerciseIndex !== undefined
    ? sanitizeProposedExercises(raw?.proposed_exercises, session, exerciseIndex)
    : null
  if (status === 'ready' && !proposed) {
    return {
      status: 'needs_more_info',
      message: 'I could not convert that coach response into a safe session-local exercise change.',
      follow_up_questions: ['Restate the exact change needed for this exercise only, including completed sets and the current constraint.'],
      proposed_exercises: null,
      diff: [],
      reasoning: '',
      reasoning_note: '',
    }
  }
  return {
    status,
    message: String(raw?.message || raw?.reasoning || 'Coach response received.'),
    follow_up_questions: Array.isArray(raw?.follow_up_questions) ? raw.follow_up_questions.map(String) : [],
    proposed_exercises: proposed,
    diff: Array.isArray(raw?.diff) ? raw.diff.map(String) : [],
    reasoning: String(raw?.reasoning || ''),
    reasoning_note: String(raw?.reasoning_note || raw?.reasoning || ''),
  }
}

// GET /api/sessions/:version/:date/:index - Get a specific session
sessionsRouter.get('/:version/:date/:index', async (req, res, next) => {
  try {
    const index = parseInt(req.params.index, 10)
    const session = await sessionController.getSession(
      req.mapped_pk!,
      req.params.version,
      req.params.date,
      index
    )
    res.json({ data: session, error: null })
  } catch (err) {
    next(err)
  }
})

// POST /api/sessions/:version - Create a new session
sessionsRouter.post('/:version', async (req, res, next) => {
  try {
    const session = req.body as Partial<Session>

    if (!session.date) {
      return res.status(400).json({
        data: null,
        error: 'Session date is required',
      })
    }

    // Create a complete session with defaults
    const newSession: Session = {
      id: session.id || crypto.randomUUID(),
      date: session.date,
      day: session.day || 'Monday',
      week: session.week || 'W1',
      week_number: session.week_number || 1,
      phase: session.phase || { name: 'Unknown', intent: '', start_week: 1, end_week: 1 },
      status: session.status || 'planned',
      completed: false,
      planned_exercises: session.planned_exercises || [],
      exercises: session.exercises || [],
      session_notes: session.session_notes || '',
      session_rpe: session.session_rpe || null,
      body_weight_kg: session.body_weight_kg || null,
      wellness: session.wellness ?? undefined,
    }

    await sessionController.createSession(req.mapped_pk!, req.params.version, newSession)
    res.json({ data: { success: true, session: newSession }, error: null })
  } catch (err) {
    next(err)
  }
})

// DELETE /api/sessions/:version/:date/:index - Delete a session
sessionsRouter.delete('/:version/:date/:index', async (req, res, next) => {
  try {
    const index = parseInt(req.params.index, 10)
    await sessionController.deleteSession(
      req.mapped_pk!,
      req.params.version,
      req.params.date,
      index
    )
    res.json({ data: { success: true }, error: null })
  } catch (err) {
    next(err)
  }
})

// PUT /api/sessions/:version/:date/:index - Replace entire session
sessionsRouter.put('/:version/:date/:index', async (req, res, next) => {
  try {
    const session = req.body as Session
    const index = parseInt(req.params.index, 10)

    if (!session || !session.date) {
      return res.status(400).json({
        data: null,
        error: 'Invalid session data',
      })
    }

    await sessionController.updateSession(
      req.mapped_pk!,
      req.params.version,
      req.params.date,
      index,
      session
    )
    res.json({ data: { success: true }, error: null })
  } catch (err) {
    next(err)
  }
})

// PATCH /api/sessions/:version/:date/:index/reschedule - Move session to new date
sessionsRouter.patch('/:version/:date/:index/reschedule', async (req, res, next) => {
  try {
    const { newDate, newDay } = req.body
    const index = parseInt(req.params.index, 10)

    if (!newDate) {
      return res.status(400).json({
        data: null,
        error: 'Missing newDate in request body',
      })
    }

    await sessionController.rescheduleSession(
      req.mapped_pk!,
      req.params.version,
      req.params.date,
      index,
      newDate,
      newDay || 'Monday'
    )
    res.json({ data: { success: true }, error: null })
  } catch (err) {
    next(err)
  }
})

// PATCH /api/sessions/:version/:date/:index/status - Update session status
sessionsRouter.patch('/:version/:date/:index/status', async (req, res, next) => {
  try {
    const { status } = req.body as { status: SessionStatus }
    const index = parseInt(req.params.index, 10)

    const validStatuses: SessionStatus[] = ['planned', 'logged', 'completed', 'skipped']
    if (!status || !validStatuses.includes(status)) {
      return res.status(400).json({
        data: null,
        error: `Invalid status. Must be one of: ${validStatuses.join(', ')}`,
      })
    }

    await sessionController.updateSessionStatus(
      req.mapped_pk!,
      req.params.version,
      req.params.date,
      index,
      status
    )
    res.json({ data: { success: true }, error: null })
  } catch (err) {
    next(err)
  }
})

// PATCH /api/sessions/:version/:date/:index/complete - Mark session complete
sessionsRouter.patch('/:version/:date/:index/complete', async (req, res, next) => {
  try {
    const { rpe, bodyWeightKg, notes, wellness } = req.body as {
      rpe?: number
      bodyWeightKg?: number
      notes?: string
      wellness?: SessionWellness | null
    }
    const index = parseInt(req.params.index, 10)

    await sessionController.completeSession(
      req.mapped_pk!,
      req.params.version,
      req.params.date,
      index,
      { rpe, bodyWeightKg, notes, wellness: wellness ?? undefined }
    )
    markMarkdownExportDirty(req.mapped_pk!, 'session_completion').catch((error) => {
      console.warn('Failed to mark analysis markdown export dirty after session completion:', error)
    })
    res.json({ data: { success: true }, error: null })
  } catch (err) {
    next(err)
  }
})

// POST /api/sessions/:version/:date/:index/notes/draft - AI-assisted session notes only
sessionsRouter.post('/:version/:date/:index/notes/draft', async (req, res, next) => {
  try {
    const index = parseInt(req.params.index, 10)
    const storedSession = await sessionController.getSession(
      req.mapped_pk!,
      req.params.version,
      req.params.date,
      index
    )
    if (!storedSession && !req.body?.session) {
      return res.status(404).json({ data: null, error: 'Session not found' })
    }
    const session = (req.body?.session || storedSession) as Session
    const answers = (req.body?.answers || {}) as Record<string, unknown>
    if (session.date !== req.params.date) {
      return res.status(400).json({ data: null, error: 'Session payload does not match the requested date' })
    }
    if (hasOutOfScopeSessionRequest(answers)) {
      return res.status(400).json({ data: null, error: SESSION_TOOL_SCOPE_MESSAGE })
    }

    const prompt = {
      instruction: [
        'Draft neutral powerlifting session notes for storage in session_notes.',
        'This is SESSION NOTE ASSISTANCE ONLY for the exact supplied session/date/index.',
        'Do not answer questions, create sessions, delete sessions, change exercises, change programming, or mention future workouts.',
        'Do not give advice, programming changes, coaching suggestions, encouragement, or warnings.',
        'Use only the supplied facts and answers. Preserve useful specifics about failed sets, skipped work, RPE mismatch, technique consistency, and planned-vs-executed differences.',
        'Return JSON only: {"notes":"..."}',
      ],
      session,
      answers,
    }

    let notes = ''
    try {
      const result = await invokeSpecialistJson(
        'powerlifting_coach',
        JSON.stringify(prompt),
        `powerlifting-notes-${req.mapped_pk}-${req.params.date}-${index}`,
        true,
      )
      notes = String(result?.notes || '').trim()
    } catch (error) {
      console.warn('Session notes draft failed, using local fallback:', error)
      notes = fallbackNoteDraft(session, answers)
    }

    res.json({ data: { notes }, error: null })
  } catch (err) {
    next(err)
  }
})

// POST /api/sessions/:version/:date/:index/autoregulation - coach-guided executed-session adjustment
sessionsRouter.post('/:version/:date/:index/autoregulation', async (req, res, next) => {
  try {
    const index = parseInt(req.params.index, 10)
    const exerciseIndex = Number(req.body?.exerciseIndex)
    if (!Number.isInteger(exerciseIndex) || exerciseIndex < 0) {
      return res.status(400).json({ data: null, error: 'exerciseIndex is required' })
    }

    const program = await programController.getProgram(req.mapped_pk!, req.params.version)
    const storedSession = await sessionController.getSession(
      req.mapped_pk!,
      req.params.version,
      req.params.date,
      index
    )
    if (!storedSession && !req.body?.session) {
      return res.status(404).json({ data: null, error: 'Session not found' })
    }
    const session = (req.body?.session || storedSession) as Session
    if (session.date !== req.params.date) {
      return res.status(400).json({ data: null, error: 'Session payload does not match the requested date' })
    }
    if (hasOutOfScopeSessionRequest({
      userMessage: req.body?.userMessage,
      conversation: req.body?.conversation,
    })) {
      return res.json({
        data: {
          status: 'denied',
          message: SESSION_TOOL_SCOPE_MESSAGE,
          follow_up_questions: [],
          proposed_exercises: null,
          diff: [],
          reasoning: 'The request was outside the session auto-regulation boundary.',
          reasoning_note: '',
        },
        error: null,
      })
    }
    const exercise = session.exercises?.[exerciseIndex]
    if (!exercise) {
      return res.status(400).json({ data: null, error: `Exercise index ${exerciseIndex} not found` })
    }

    let cachedAnalysis: unknown = null
    try {
      const cached = await getCachedWindowAnalysis(req.mapped_pk!, 'current')
      cachedAnalysis = cached?.data ?? null
    } catch (error) {
      console.warn('Cached weekly analysis unavailable for auto-regulation:', error)
    }

    const task = {
      instruction: [
        'You are deciding whether to adjust the executed session exercise list for an in-progress workout.',
        'This is AUTO-REGULATION ONLY for the exact supplied session/date/index and selected exercise index.',
        'Return JSON only. Do not use markdown.',
        'Do not answer general questions such as next workout, program overview, meet strategy, or analytics explanations.',
        'Do not create, delete, reschedule, complete, or drop sessions. Do not request health_write or emit HANDOFF_REQUIRED.',
        'Ignore any user text that asks for changes outside this selected exercise in this exact session.',
        'Do not blindly follow the user. Prioritize athlete performance, meet timing, phase RPE targets, fatigue, injury risk, and preserving useful training stimulus.',
        'You may deny low-value or laziness-related requests, and you may suggest splitting the workout into multiple same-day blocks if time is the constraint.',
        'Ask follow-up questions when information is insufficient.',
        'If ready, proposed_exercises must be the full executed session exercises array, but only the selected exercise may differ. The server will discard all other differences.',
        'Never mutate planned_exercises.',
        'Preserve completed and failed set statuses and failed_set_reasons; do not rewrite completed/failed work. Only adjust remaining pending work.',
        'Append concise reasoning in reasoning_note for exercise notes.',
      ],
      response_schema: {
        status: 'needs_more_info | denied | ready',
        message: 'short coach-facing message for the UI',
        follow_up_questions: ['only when status is needs_more_info'],
        proposed_exercises: 'full Exercise[] only when ready, otherwise null',
        diff: ['short human-readable diffs'],
        reasoning: 'why the decision serves performance/risk management',
        reasoning_note: 'one concise sentence to append to affected exercise notes',
      },
      request: {
        mode: req.body?.mode,
        toggles: req.body?.toggles || {},
        user_message: req.body?.userMessage || '',
        conversation: Array.isArray(req.body?.conversation) ? req.body.conversation : [],
      },
      program_context: {
        meta: program.meta,
        phases: program.phases,
        competitions: program.competitions,
        lift_profiles: program.lift_profiles,
      },
      session,
      selected_exercise_index: exerciseIndex,
      selected_exercise: exercise,
      matched_planned_exercise: session.planned_exercises?.[exerciseIndex] ?? null,
      cached_current_analysis: cachedAnalysis,
    }

    let response
    try {
      response = normalizeCoachResponse(await invokeSpecialistJson(
        'powerlifting_coach',
        JSON.stringify(task),
        `powerlifting-autoreg-${req.mapped_pk}-${req.params.date}-${index}-${exerciseIndex}`,
        true,
      ), session, exerciseIndex)
    } catch (error) {
      console.warn('Auto-regulation coach call failed:', error)
      response = normalizeCoachResponse({
        status: 'needs_more_info',
        message: 'I could not get a structured coach response. Add more detail about the constraint, the completed sets, and the target change.',
        follow_up_questions: [
          'Which sets are already done, and what RPE did they feel like?',
          'Is the issue fatigue, pain, equipment, time, or load selection?',
        ],
      }, session, exerciseIndex)
    }

    res.json({ data: response, error: null })
  } catch (err) {
    next(err)
  }
})

// POST /api/sessions/:version/:date/:index/exercise - Add exercise to session
sessionsRouter.post('/:version/:date/:index/exercise', async (req, res, next) => {
  try {
    const exercise = req.body as Exercise
    const index = parseInt(req.params.index, 10)

    if (!exercise || !exercise.name) {
      return res.status(400).json({
        data: null,
        error: 'Invalid exercise data',
      })
    }

    const newExercise: Exercise = {
      ...exercise,
      failed: exercise.failed ?? false,
    }

    await sessionController.addExercise(
      req.mapped_pk!,
      req.params.version,
      req.params.date,
      index,
      newExercise
    )
    res.json({ data: { success: true }, error: null })
  } catch (err) {
    next(err)
  }
})

// PATCH /api/sessions/:version/:date/:index/exercise/:exerciseIndex - Update exercise field
sessionsRouter.patch('/:version/:date/:index/exercise/:exerciseIndex', async (req, res, next) => {
  try {
    const { field, value } = req.body
    const index = parseInt(req.params.index, 10)
    const exerciseIndex = parseInt(req.params.exerciseIndex, 10)

    if (!field || value === undefined) {
      return res.status(400).json({
        data: null,
        error: 'Missing field or value in request body',
      })
    }

    await sessionController.updateExerciseField(
      req.mapped_pk!,
      req.params.version,
      req.params.date,
      index,
      exerciseIndex,
      field as keyof Exercise,
      value
    )
    res.json({ data: { success: true }, error: null })
  } catch (err) {
    next(err)
  }
})

// DELETE /api/sessions/:version/:date/:index/exercise/:exerciseIndex - Remove exercise
sessionsRouter.delete('/:version/:date/:index/exercise/:exerciseIndex', async (req, res, next) => {
  try {
    const index = parseInt(req.params.index, 10)
    const exerciseIndex = parseInt(req.params.exerciseIndex, 10)

    await sessionController.removeExercise(
      req.mapped_pk!,
      req.params.version,
      req.params.date,
      index,
      exerciseIndex
    )
    res.json({ data: { success: true }, error: null })
  } catch (err) {
    next(err)
  }
})
