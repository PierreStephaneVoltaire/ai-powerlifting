import { create } from 'zustand'
import type { Program, Session, Exercise, Phase, WeightEntry, SupplementPhase, DietNote, BlockNote, SessionVideo, LiftProfile, Sex, AthleteGoal, WeekStartDay } from '@powerlifting/types'
import * as api from '@/api/client'
import { requestPartition } from '@/api/context'
import { activeBlockId } from '@/utils/weekStart'
import { currentBlockId, recordBlock } from '@/utils/blockScope'
import { kgToLb } from '@/utils/units'

interface ProgramState {
  program: Program | null
  isLoading: boolean
  error: string | null
  needsSetup: boolean
  setupStatus: api.SetupStatus | null
  isDirty: boolean
  activeSessionDate: string | null
  activeSessionIndex: number | null

  // Actions
  loadProgram: () => Promise<void>
  loadSetupStatus: () => Promise<api.SetupStatus>
  initializeSetup: (input: api.InitializeSetupInput) => Promise<api.InitializeSetupResult>
  setActiveSession: (date: string | null, index: number | null) => void
  createSession: (session: Partial<Session> & { date: string }) => Promise<Session>
  deleteSession: (date: string, index: number, sessionId?: string) => Promise<void>
  updateSession: (date: string, index: number, session: Session) => void
  updateExercise: (
    date: string,
    index: number,
    exerciseIndex: number,
    field: keyof Exercise,
    value: unknown
  ) => void
  addExercise: (date: string, index: number, exercise: Exercise) => void
  removeExercise: (date: string, index: number, exerciseIndex: number) => void
  rescheduleSession: (date: string, index: number, newDate: string, newDay: string, sessionId?: string) => Promise<void>
  markComplete: (
    date: string,
    index: number,
    data: { rpe?: number; bodyWeightKg?: number; notes?: string; wellness?: Session['wellness'] }, sessionId?: string
  ) => Promise<void>
  saveSession: (date: string, index: number, session?: Session) => Promise<Session>
  persistSession: (date: string, index: number, session: Session) => Promise<Session>
  updateMaxes: (maxes: {
    squat_kg: number
    bench_kg: number
    deadlift_kg: number
  }) => Promise<void>
  updateBodyWeight: (weightKg: number) => Promise<void>
  updatePhases: (phases: Phase[], block?: string) => Promise<void>
  addWeightEntry: (entry: WeightEntry) => Promise<void>
  removeWeightEntry: (date: string) => Promise<void>
  reset: () => void

  // Supplements
  updateSupplementPhases: (phases: SupplementPhase[]) => Promise<void>

  // Lift Profiles
  updateLiftProfiles: (liftProfiles: LiftProfile[]) => Promise<void>

  // Sex
  setSex: (sex: Sex) => Promise<void>
  setWeekStartDay: (day: WeekStartDay) => Promise<void>

  // Diet Notes
  updateDietNotes: (dietNotes: DietNote[]) => Promise<void>

  // Block Notes
  updateBlockNotes: (blockNotes: BlockNote[]) => Promise<void>

  // Competitions
  updateGoals: (goals: AthleteGoal[]) => Promise<void>

  // Videos
  removeSessionVideo: (sessionDate: string, videoId: string) => void
  updateSessionVideo: (sessionDate: string, videoId: string, video: SessionVideo) => void
}

export const useProgramStore = create<ProgramState>((set, get) => ({
  program: null,
  isLoading: false,
  error: null,
  needsSetup: false,
  setupStatus: null,
  isDirty: false,
  activeSessionDate: null,
  activeSessionIndex: null,

  loadProgram: async () => {
    const partition = requestPartition()
    set({ isLoading: true, error: null })
    try {
      const program = await api.fetchProgram()
      if (requestPartition() !== partition) return
      set({ program, isLoading: false, needsSetup: false })
    } catch (e) {
      if (requestPartition() !== partition) return
      if (api.isApiNotFound(e)) {
        set({ program: null, isLoading: false, needsSetup: true, error: null })
        return
      }
      set({ error: String(e), isLoading: false })
    }
  },

  loadSetupStatus: async () => {
    const partition = requestPartition()
    const status = await api.fetchSetupStatus()
    if (requestPartition() !== partition) return status
    set({
      setupStatus: status,
      needsSetup: status.needsSetup,
    })
    return status
  },

  initializeSetup: async (input) => {
    const result = await api.initializeSetup(input)
    if (result.status === 'initialized') {
      set({ needsSetup: false, setupStatus: null })
    }
    return result
  },

  setActiveSession: (date, index) => set({ activeSessionDate: date, activeSessionIndex: index }),

  createSession: async (sessionData) => {
    const session = await api.createSession(sessionData, api.sessionTarget())

    // Reload program to get updated sessions with derived fields
    await get().loadProgram()
    return session
  },

  deleteSession: async (date, index, sessionId) => {
    const { program } = get()
    await api.deleteSession(date, index, api.sessionTarget(sessionId || program?.sessions[index]?.id))

    // Reload to get correct indices after deletion
    await get().loadProgram()
  },

  updateSession: (date, index, session) =>
    set((state) => {
      if (!state.program) return state
      const sessions = [...state.program.sessions]
      if (index >= 0 && index < sessions.length) {
        sessions[index] = session
      }
      return { program: { ...state.program, sessions }, isDirty: true }
    }),

  updateExercise: (date, index, exerciseIndex, field, value) =>
    set((state) => {
      if (!state.program) return state
      const sessions = [...state.program.sessions]
      if (index >= 0 && index < sessions.length) {
        const exercises = [...sessions[index].exercises]
        ;(exercises[exerciseIndex] as any)[field] = value
        sessions[index] = { ...sessions[index], exercises }
      }
      return { program: { ...state.program, sessions }, isDirty: true }
    }),

  addExercise: (date, index, exercise) =>
    set((state) => {
      if (!state.program) return state
      const sessions = [...state.program.sessions]
      if (index >= 0 && index < sessions.length) {
        sessions[index] = {
          ...sessions[index],
          exercises: [...sessions[index].exercises, exercise],
        }
      }
      return { program: { ...state.program, sessions }, isDirty: true }
    }),

  removeExercise: (date, index, exerciseIndex) =>
    set((state) => {
      if (!state.program) return state
      const sessions = [...state.program.sessions]
      if (index >= 0 && index < sessions.length) {
        const exercises = sessions[index].exercises.filter((_, i) => i !== exerciseIndex)
        sessions[index] = { ...sessions[index], exercises }
      }
      return { program: { ...state.program, sessions }, isDirty: true }
    }),

  rescheduleSession: async (date, index, newDate, newDay, sessionId) => {
    const { program } = get()
    if (!program) return

    const updated = await api.rescheduleSession(date, index, newDate, newDay, api.sessionTarget(sessionId || program.sessions[index]?.id))

    // Update local state
    set((state) => {
      if (!state.program) return state
      const sessions = [...state.program.sessions]
      if (index >= 0 && index < sessions.length) {
        sessions[index] = updated
      }
      return { program: { ...state.program, sessions, meta: { ...state.program.meta } } }
    })
  },

  markComplete: async (date, index, data, sessionId) => {
    const { program } = get()
    const updated = await api.completeSession(date, index, data, api.sessionTarget(sessionId || program?.sessions[index]?.id))

    // Sync body weight to weight log if provided
    if (data.bodyWeightKg) {
      api.addWeightEntry({ date, kg: data.bodyWeightKg }).catch((e) =>
        console.error('Failed to sync body weight to weight log:', e)
      )
    }

    set((state) => {
      if (!state.program) return state
      const sessions = [...state.program.sessions]
      if (index >= 0 && index < sessions.length) {
        sessions[index] = {
          ...updated,
        }
      }
      return { program: { ...state.program, sessions, meta: { ...state.program.meta } } }
    })
  },

  saveSession: async (date, index, sessionOverride) => {
    const { program } = get()
    if (!program) throw new Error('Cannot save session before a program is loaded')

    const session = sessionOverride ?? program.sessions[index]
    if (!session) throw new Error(`Cannot save session at index ${index}: session not found`)

    const updated = await get().persistSession(date, index, session)

    set((state) => {
      if (!state.program) return { isDirty: false }
      const sessions = [...state.program.sessions]
      if (index >= 0 && index < sessions.length) {
        sessions[index] = updated
      }
      return { program: { ...state.program, sessions, meta: { ...state.program.meta } }, isDirty: false }
    })
    return updated
  },

  persistSession: async (date, index, session) => {
    const updated = await api.updateSession(date, index, session, api.sessionTarget(session.id))
    if (session.body_weight_kg != null) {
      api.addWeightEntry({ date: session.date, kg: session.body_weight_kg }).catch((e) =>
        console.error('Failed to sync body weight to weight log:', e)
      )
    }
    return updated
  },

  updateMaxes: async (maxes) => {
    await api.updateTargetMaxes(maxes)

    set((state) => {
      if (!state.program) return state
      return {
        program: {
          ...state.program,
          meta: {
            ...state.program.meta,
            target_squat_kg: maxes.squat_kg,
            target_bench_kg: maxes.bench_kg,
            target_dl_kg: maxes.deadlift_kg,
            target_total_kg: maxes.squat_kg + maxes.bench_kg + maxes.deadlift_kg,
          },
        },
      }
    })
  },

  updateBodyWeight: async (weightKg: number) => {
    await api.updateBodyWeight(weightKg)

    set((state) => {
      if (!state.program) return state
      return {
        program: {
          ...state.program,
          meta: {
            ...state.program.meta,
            current_body_weight_kg: weightKg,
            current_body_weight_lb: kgToLb(weightKg),
          },
        },
      }
    })
  },

  updatePhases: async (phases: Phase[], block?: string) => {
    await api.updatePhases(phases, block)

    set((state) => {
      if (!state.program) return state
      const existing = state.program.phases ?? []
      let nextPhases: Phase[]
      if (block) {
        const other = existing.filter(p => (p.block ?? 'current') !== block)
        const incoming = phases.map(p => ({ ...p, block: p.block ?? block }))
        nextPhases = [...other, ...incoming]
      } else {
        nextPhases = phases.map(p => ({ ...p, block: p.block ?? 'current' }))
      }
      return {
        program: {
          ...state.program,
          phases: nextPhases,
          meta: { ...state.program.meta },
        },
      }
    })
  },

  addWeightEntry: async (entry) => {
    await api.addWeightEntry(entry)
  },

  removeWeightEntry: async (date) => {
    await api.removeWeightEntry(date)
  },

  // Supplements
  updateSupplementPhases: async (phases) => {
    const { program } = get()
    const active = currentBlockId(program)
    await api.updateSupplementPhases(phases.filter((phase) => recordBlock(phase, 'supplement_phases', program) === active))

    set((state) => {
      if (!state.program) return state
      return {
        program: {
          ...state.program,
          supplement_phases: phases,
          meta: { ...state.program.meta },
        },
      }
    })
  },

  // Lift Profiles
  updateLiftProfiles: async (liftProfiles: LiftProfile[]) => {
    await api.updateLiftProfiles(liftProfiles)

    set((state) => {
      if (!state.program) return state
      return {
        program: {
          ...state.program,
          lift_profiles: liftProfiles,
          meta: { ...state.program.meta },
        },
      }
    })
  },

  // Sex
  setSex: async (sex: Sex) => {
    await api.updateMetaField('sex', sex)

    set((state) => {
      if (!state.program) return state
      return {
        program: {
          ...state.program,
          meta: {
            ...state.program.meta,
            sex,
          },
        },
      }
    })
  },

  setWeekStartDay: async (day: WeekStartDay) => {
    const { program } = get()
    const blockId = activeBlockId(program) ?? 'current'
    const blocks = (program?.meta.blocks ?? []).map((block) => String(block.id ?? block.block_id ?? '') === blockId ? { ...block, week_start_day: day } : block)

    await api.updateMetaField('blocks', blocks)

    set((state) => {
      if (!state.program) return state
      return {
        program: {
          ...state.program,
          meta: {
            ...state.program.meta,
            blocks,
          },
        },
      }
    })
  },

  // Diet Notes
  updateDietNotes: async (dietNotes) => {
    await api.updateDietNotes(dietNotes)

    set((state) => {
      if (!state.program) return state
      return {
        program: {
          ...state.program,
          diet_notes: dietNotes,
          meta: { ...state.program.meta },
        },
      }
    })
  },

  // Block Notes
  updateBlockNotes: async (blockNotes) => {
    await api.updateBlockNotes(blockNotes)

    set((state) => {
      if (!state.program) return state
      return {
        program: {
          ...state.program,
          meta: {
            ...state.program.meta,
            block_notes: blockNotes,
          },
        },
      }
    })
  },

  // Competitions
  updateGoals: async (goals) => {
    await api.updateGoals(goals)

    set((state) => {
      if (!state.program) return state
      return {
        program: {
          ...state.program,
          goals,
        },
      }
    })
  },

  // Videos
  removeSessionVideo: (sessionDate, videoId) => {
    set((state) => {
      if (!state.program) return state
      const sessions = state.program.sessions.map((s) => {
        if (s.date !== sessionDate) return s
        const videos = (s.videos || []).filter((v) => v.video_id !== videoId)
        return { ...s, videos: videos.length > 0 ? videos : undefined }
      })
      return { program: { ...state.program, sessions } }
    })
  },

  updateSessionVideo: (sessionDate, videoId, video) => {
    set((state) => {
      if (!state.program) return state
      const sessions = state.program.sessions.map((s) => {
        if (s.date !== sessionDate) return s
        const videos = (s.videos || []).map((v) => v.video_id === videoId ? video : v)
        return { ...s, videos }
      })
      return { program: { ...state.program, sessions } }
    })
  },

  reset: () =>
    set({
      program: null,
              isLoading: false,
      error: null,
      needsSetup: false,
      setupStatus: null,
      isDirty: false,
      activeSessionDate: null,
      activeSessionIndex: null,
    }),
}))
