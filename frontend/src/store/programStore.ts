import { create } from 'zustand'
import type { Program, Session, Exercise, Phase, MaxEntry, WeightEntry, ProgramListItem, SupplementPhase, DietNote, BlockNote, Competition, SessionVideo, LiftResults, LiftProfile, Sex, AthleteGoal, PostMeetReport, WeekStartDay } from '@powerlifting/types'
import * as api from '@/api/client'
import { requestPartition } from '@/api/context'

interface ProgramState {
  program: Program | null
  version: string
  versions: ProgramListItem[]
  isLoading: boolean
  error: string | null
  needsSetup: boolean
  setupStatus: api.SetupStatus | null
  isDirty: boolean
  activeSessionDate: string | null
  activeSessionIndex: number | null

  // Actions
  loadProgram: (version: string) => Promise<void>
  loadSetupStatus: () => Promise<api.SetupStatus>
  initializeSetup: (input: api.InitializeSetupInput) => Promise<api.InitializeSetupResult>
  loadVersions: () => Promise<void>
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
  updateMaxes: (maxes: {
    squat_kg: number
    bench_kg: number
    deadlift_kg: number
  }) => Promise<void>
  updateBodyWeight: (weightKg: number) => Promise<void>
  updatePhases: (phases: Phase[], block?: string) => Promise<void>
  addWeightEntry: (entry: WeightEntry) => Promise<void>
  removeWeightEntry: (date: string) => Promise<void>
  forkVersion: (label?: string) => Promise<string>
  archiveProgram: () => Promise<void>
  unarchiveProgram: () => Promise<void>
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
  updateCompetitions: (competitions: Competition[]) => Promise<void>
  migrateLastComp: () => Promise<void>
  completeCompetition: (date: string, results: LiftResults, bodyWeightKg: number, postMeetReport?: PostMeetReport) => Promise<void>
  updateGoals: (goals: AthleteGoal[]) => Promise<void>

  // Videos
  removeSessionVideo: (sessionDate: string, videoId: string) => void
  updateSessionVideo: (sessionDate: string, videoId: string, video: SessionVideo) => void
}

export const useProgramStore = create<ProgramState>((set, get) => ({
  program: null,
  version: 'current',
  versions: [],
  isLoading: false,
  error: null,
  needsSetup: false,
  setupStatus: null,
  isDirty: false,
  activeSessionDate: null,
  activeSessionIndex: null,

  loadProgram: async (version) => {
    const partition = requestPartition()
    set({ isLoading: true, error: null })
    try {
      const program = await api.fetchProgram(version)
      if (requestPartition() !== partition) return
      set({ program, version, isLoading: false, needsSetup: false })
    } catch (e) {
      if (requestPartition() !== partition) return
      if (version === 'current' && api.isApiNotFound(e)) {
        set({ program: null, version, isLoading: false, needsSetup: true, error: null })
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

  loadVersions: async () => {
    const partition = requestPartition()
    try {
      const versions = await api.fetchPrograms()
      if (requestPartition() !== partition) return
      // Sort by version number descending (newest first)
      versions.sort((a, b) => b.version.localeCompare(a.version))
      set({ versions })
    } catch (e) {
      if (requestPartition() !== partition) return
      console.error('Failed to load versions:', e)
    }
  },

  setActiveSession: (date, index) => set({ activeSessionDate: date, activeSessionIndex: index }),

  createSession: async (sessionData) => {
    const { version, program } = get()
    const session = await api.createSession(version, sessionData, api.mutationEnvelope(program?.meta.revision ?? 0))

    // Reload program to get updated sessions with derived fields
    await get().loadProgram(version)
    return session
  },

  deleteSession: async (date, index, sessionId) => {
    const { version, program } = get()
    await api.deleteSession(version, date, index, api.mutationEnvelope(program?.meta.revision ?? 0, undefined, sessionId || program?.sessions[index]?.id))

    // Reload to get correct indices after deletion
    await get().loadProgram(version)
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
    const { version, program } = get()
    if (!program) return

    const updated = await api.rescheduleSession(version, date, index, newDate, newDay, api.mutationEnvelope(program.meta.revision ?? 0, undefined, sessionId || program.sessions[index]?.id))

    // Update local state
    set((state) => {
      if (!state.program) return state
      const sessions = [...state.program.sessions]
      if (index >= 0 && index < sessions.length) {
        sessions[index] = updated
      }
      return { program: { ...state.program, sessions, meta: { ...state.program.meta, revision: updated.revision ?? state.program.meta.revision } } }
    })
  },

  markComplete: async (date, index, data, sessionId) => {
    const { version, program } = get()
    const updated = await api.completeSession(version, date, index, data, api.mutationEnvelope(program?.meta.revision ?? 0, undefined, sessionId || program?.sessions[index]?.id))

    // Sync body weight to weight log if provided
    if (data.bodyWeightKg) {
      api.addWeightEntry(version, { date, kg: data.bodyWeightKg }).catch((e) =>
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
      return { program: { ...state.program, sessions, meta: { ...state.program.meta, revision: updated.revision ?? state.program.meta.revision } } }
    })
  },

  saveSession: async (date, index, sessionOverride) => {
    const { program, version } = get()
    if (!program) throw new Error('Cannot save session before a program is loaded')

    const session = sessionOverride ?? program.sessions[index]
    if (!session) throw new Error(`Cannot save session at index ${index}: session not found`)

    const updated = await api.updateSession(version, date, index, session, api.mutationEnvelope(program.meta.revision ?? 0, undefined, session.id))

    // Sync body weight to weight log if present
    if (session.body_weight_kg != null) {
      api.addWeightEntry(version, { date: session.date, kg: session.body_weight_kg }).catch((e) =>
        console.error('Failed to sync body weight to weight log:', e)
      )
    }

    set((state) => {
      if (!state.program) return { isDirty: false }
      const sessions = [...state.program.sessions]
      if (index >= 0 && index < sessions.length) {
        sessions[index] = updated
      }
      return { program: { ...state.program, sessions, meta: { ...state.program.meta, revision: updated.revision ?? state.program.meta.revision } }, isDirty: false }
    })
    return updated
  },

  updateMaxes: async (maxes) => {
    const { version, program } = get()
    const result = await api.updateTargetMaxes(version, maxes, api.mutationEnvelope(program?.meta.revision ?? 0))

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
            revision: result.revision ?? state.program.meta.revision,
          },
        },
      }
    })
  },

  updateBodyWeight: async (weightKg: number) => {
    const { version, program } = get()
    const result = await api.updateBodyWeight(version, weightKg, api.mutationEnvelope(program?.meta.revision ?? 0))

    set((state) => {
      if (!state.program) return state
      return {
        program: {
          ...state.program,
          meta: {
            ...state.program.meta,
            current_body_weight_kg: weightKg,
            current_body_weight_lb: weightKg * 2.20462,
            revision: result.revision ?? state.program.meta.revision,
          },
        },
      }
    })
  },

  updatePhases: async (phases: Phase[], block?: string) => {
    const { version, program } = get()
    const result = await api.updatePhases(version, phases, block, api.mutationEnvelope(program?.meta.revision ?? 0))

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
          meta: { ...state.program.meta, revision: result.revision ?? state.program.meta.revision },
        },
      }
    })
  },

  addWeightEntry: async (entry) => {
    const { version } = get()
    await api.addWeightEntry(version, entry)
  },

  removeWeightEntry: async (date) => {
    const { version } = get()
    await api.removeWeightEntry(version, date)
  },

  forkVersion: async (label) => {
    const { version } = get()
    const newVersion = await api.forkProgram(version, label)
    await get().loadProgram(newVersion)
    return newVersion
  },

  archiveProgram: async () => {
    const { version, program } = get()
    await api.archiveProgram(version, api.mutationEnvelope(program?.meta.revision ?? 0))
    await get().loadVersions()
    await get().loadProgram(version)
  },

  unarchiveProgram: async () => {
    const { version, program } = get()
    await api.unarchiveProgram(version, api.mutationEnvelope(program?.meta.revision ?? 0))
    await get().loadVersions()
    await get().loadProgram(version)
  },

  // Supplements
  updateSupplementPhases: async (phases) => {
    const { version, program } = get()
    const result = await api.updateSupplementPhases(version, phases, api.mutationEnvelope(program?.meta.revision ?? 0))

    set((state) => {
      if (!state.program) return state
      return {
        program: {
          ...state.program,
          supplement_phases: phases,
          meta: { ...state.program.meta, revision: result.revision ?? state.program.meta.revision },
        },
      }
    })
  },

  // Lift Profiles
  updateLiftProfiles: async (liftProfiles: LiftProfile[]) => {
    const { version, program } = get()
    const result = await api.updateLiftProfiles(version, liftProfiles, api.mutationEnvelope(program?.meta.revision ?? 0))

    set((state) => {
      if (!state.program) return state
      return {
        program: {
          ...state.program,
          lift_profiles: liftProfiles,
          meta: { ...state.program.meta, revision: result.revision ?? state.program.meta.revision },
        },
      }
    })
  },

  // Sex
  setSex: async (sex: Sex) => {
    const { version, program } = get()
    const result = await api.updateMetaField(version, 'sex', sex, api.mutationEnvelope(program?.meta.revision ?? 0))

    set((state) => {
      if (!state.program) return state
      return {
        program: {
          ...state.program,
          meta: {
            ...state.program.meta,
            sex,
            revision: result.revision ?? state.program.meta.revision,
          },
        },
      }
    })
  },

  setWeekStartDay: async (day: WeekStartDay) => {
    const { version, program } = get()
    const nextBlockWeekStarts = {
      ...(program?.meta.block_week_start_days ?? {}),
      current: day,
    }

    const result = await api.updateMetaFields(version, { program_week_start_day: day, block_week_start_days: nextBlockWeekStarts }, api.mutationEnvelope(program?.meta.revision ?? 0))

    set((state) => {
      if (!state.program) return state
      return {
        program: {
          ...state.program,
          meta: {
            ...state.program.meta,
            program_week_start_day: day,
            block_week_start_days: nextBlockWeekStarts,
            revision: result.revision ?? state.program.meta.revision,
          },
        },
      }
    })
  },

  // Diet Notes
  updateDietNotes: async (dietNotes) => {
    const { version, program } = get()
    const result = await api.updateDietNotes(version, dietNotes, api.mutationEnvelope(program?.meta.revision ?? 0))

    set((state) => {
      if (!state.program) return state
      return {
        program: {
          ...state.program,
          diet_notes: dietNotes,
          meta: { ...state.program.meta, revision: result.revision ?? state.program.meta.revision },
        },
      }
    })
  },

  // Block Notes
  updateBlockNotes: async (blockNotes) => {
    const { version, program } = get()
    const result = await api.updateBlockNotes(version, blockNotes, api.mutationEnvelope(program?.meta.revision ?? 0))

    set((state) => {
      if (!state.program) return state
      return {
        program: {
          ...state.program,
          meta: {
            ...state.program.meta,
            block_notes: blockNotes,
            revision: result.revision ?? state.program.meta.revision,
          },
        },
      }
    })
  },

  // Competitions
  updateCompetitions: async (competitions) => {
    const { version, program } = get()
    const result = await api.updateCompetitions(version, competitions, api.mutationEnvelope(program?.meta.revision ?? 0))

    set((state) => {
      if (!state.program) return state
      return {
        program: {
          ...state.program,
          competitions,
          meta: { ...state.program.meta, revision: result.revision ?? state.program.meta.revision },
        },
      }
    })
  },

  migrateLastComp: async () => {
    const { version } = get()
    const competitions = await api.migrateLastComp(version)

    set((state) => {
      if (!state.program) return state
      return {
        program: {
          ...state.program,
          competitions,
        },
      }
    })
  },

  completeCompetition: async (date, results, bodyWeightKg, postMeetReport) => {
    const { version, program } = get()
    const updatedCompetition = await api.completeCompetition(version, date, results, bodyWeightKg, api.mutationEnvelope(program?.meta.revision ?? 0), postMeetReport)

    set((state) => {
      if (!state.program) return state
      const competitions = state.program.competitions.map((c) =>
        c.date === date
          ? updatedCompetition
          : c
      )
      return {
        program: {
          ...state.program,
          competitions,
          meta: { ...state.program.meta, revision: (updatedCompetition as Competition & { revision?: number }).revision ?? state.program.meta.revision },
        },
      }
    })
  },

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
      version: 'current',
      versions: [],
      isLoading: false,
      error: null,
      needsSetup: false,
      setupStatus: null,
      isDirty: false,
      activeSessionDate: null,
      activeSessionIndex: null,
    }),
}))
