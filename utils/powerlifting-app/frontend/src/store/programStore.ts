import { create } from 'zustand'
import type { Program, Session, Exercise, Phase, MaxEntry, WeightEntry, ProgramListItem, SupplementPhase, DietNote, Competition, SessionVideo, LiftResults, LiftProfile, Sex, AthleteGoal, PostMeetReport, WeekStartDay } from '@powerlifting/types'
import * as api from '@/api/client'

interface ProgramState {
  program: Program | null
  version: string
  versions: ProgramListItem[]
  isLoading: boolean
  error: string | null
  isDirty: boolean
  activeSessionDate: string | null
  activeSessionIndex: number | null

  // Actions
  loadProgram: (version: string) => Promise<void>
  loadVersions: () => Promise<void>
  setActiveSession: (date: string | null, index: number | null) => void
  createSession: (session: Partial<Session> & { date: string }) => Promise<Session>
  deleteSession: (date: string, index: number) => Promise<void>
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
  rescheduleSession: (date: string, index: number, newDate: string, newDay: string) => Promise<void>
  markComplete: (
    date: string,
    index: number,
    data: { rpe?: number; bodyWeightKg?: number; notes?: string; wellness?: Session['wellness'] }
  ) => Promise<void>
  saveSession: (date: string, index: number) => Promise<void>
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

  // Competitions
  updateCompetitions: (competitions: Competition[]) => Promise<void>
  migrateLastComp: () => Promise<void>
  completeCompetition: (date: string, results: LiftResults, bodyWeightKg: number, postMeetReport?: PostMeetReport) => Promise<void>
  updateGoals: (goals: AthleteGoal[]) => Promise<void>

  // Videos
  removeSessionVideo: (sessionDate: string, videoId: string) => void
}

export const useProgramStore = create<ProgramState>((set, get) => ({
  program: null,
  version: 'current',
  versions: [],
  isLoading: false,
  error: null,
  isDirty: false,
  activeSessionDate: null,
  activeSessionIndex: null,

  loadProgram: async (version) => {
    set({ isLoading: true, error: null })
    try {
      const program = await api.fetchProgram(version)
      set({ program, version, isLoading: false })
    } catch (e) {
      set({ error: String(e), isLoading: false })
    }
  },

  loadVersions: async () => {
    try {
      const versions = await api.fetchPrograms()
      // Sort by version number descending (newest first)
      versions.sort((a, b) => b.version.localeCompare(a.version))
      set({ versions })
    } catch (e) {
      console.error('Failed to load versions:', e)
    }
  },

  setActiveSession: (date, index) => set({ activeSessionDate: date, activeSessionIndex: index }),

  createSession: async (sessionData) => {
    const { version } = get()
    const session = await api.createSession(version, sessionData)

    // Reload program to get updated sessions with derived fields
    await get().loadProgram(version)
    return session
  },

  deleteSession: async (date, index) => {
    const { version } = get()
    await api.deleteSession(version, date, index)

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

  rescheduleSession: async (date, index, newDate, newDay) => {
    const { version, program } = get()
    if (!program) return

    await api.rescheduleSession(version, date, index, newDate, newDay)

    // Update local state
    set((state) => {
      if (!state.program) return state
      const sessions = [...state.program.sessions]
      if (index >= 0 && index < sessions.length) {
        sessions[index] = { ...sessions[index], date: newDate, day: newDay }
      }
      return { program: { ...state.program, sessions } }
    })
  },

  markComplete: async (date, index, data) => {
    const { version } = get()
    await api.completeSession(version, date, index, data)

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
          ...sessions[index],
          completed: true,
          session_rpe: data.rpe ?? sessions[index].session_rpe,
          body_weight_kg: data.bodyWeightKg ?? sessions[index].body_weight_kg,
          session_notes: data.notes ?? sessions[index].session_notes,
          wellness: data.wellness ?? sessions[index].wellness,
        }
      }
      return { program: { ...state.program, sessions } }
    })
  },

  saveSession: async (date, index) => {
    const { program, version } = get()
    if (!program) return

    const session = program.sessions[index]
    if (!session) return

    await api.updateSession(version, date, index, session)

    // Sync body weight to weight log if present
    if (session.body_weight_kg) {
      api.addWeightEntry(version, { date: session.date, kg: session.body_weight_kg }).catch((e) =>
        console.error('Failed to sync body weight to weight log:', e)
      )
    }

    set({ isDirty: false })
  },

  updateMaxes: async (maxes) => {
    const { version } = get()
    await api.updateTargetMaxes(version, maxes)

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
    const { version } = get()
    await api.updateBodyWeight(version, weightKg)

    set((state) => {
      if (!state.program) return state
      return {
        program: {
          ...state.program,
          meta: {
            ...state.program.meta,
            current_body_weight_kg: weightKg,
            current_body_weight_lb: weightKg * 2.20462,
          },
        },
      }
    })
  },

  updatePhases: async (phases: Phase[], block?: string) => {
    const { version } = get()
    await api.updatePhases(version, phases, block)

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
    const { version } = get()
    await api.archiveProgram(version)
    await get().loadVersions()
    await get().loadProgram(version)
  },

  unarchiveProgram: async () => {
    const { version } = get()
    await api.unarchiveProgram(version)
    await get().loadVersions()
    await get().loadProgram(version)
  },

  // Supplements
  updateSupplementPhases: async (phases) => {
    const { version } = get()
    await api.updateSupplementPhases(version, phases)

    set((state) => {
      if (!state.program) return state
      return {
        program: {
          ...state.program,
          supplement_phases: phases,
        },
      }
    })
  },

  // Lift Profiles
  updateLiftProfiles: async (liftProfiles: LiftProfile[]) => {
    const { version } = get()
    await api.updateLiftProfiles(version, liftProfiles)

    set((state) => {
      if (!state.program) return state
      return {
        program: {
          ...state.program,
          lift_profiles: liftProfiles,
        },
      }
    })
  },

  // Sex
  setSex: async (sex: Sex) => {
    const { version } = get()
    await api.updateMetaField(version, 'sex', sex)

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
    const { version, program } = get()
    const nextBlockWeekStarts = {
      ...(program?.meta.block_week_start_days ?? {}),
      current: day,
    }

    await api.updateMetaField(version, 'program_week_start_day', day)
    await api.updateMetaField(version, 'block_week_start_days', nextBlockWeekStarts)

    set((state) => {
      if (!state.program) return state
      return {
        program: {
          ...state.program,
          meta: {
            ...state.program.meta,
            program_week_start_day: day,
            block_week_start_days: nextBlockWeekStarts,
          },
        },
      }
    })
  },

  // Diet Notes
  updateDietNotes: async (dietNotes) => {
    const { version } = get()
    await api.updateDietNotes(version, dietNotes)

    set((state) => {
      if (!state.program) return state
      return {
        program: {
          ...state.program,
          diet_notes: dietNotes,
        },
      }
    })
  },

  // Competitions
  updateCompetitions: async (competitions) => {
    const { version } = get()
    await api.updateCompetitions(version, competitions)

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
    const { version } = get()
    const updatedCompetition = await api.completeCompetition(version, date, results, bodyWeightKg, postMeetReport)

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
        },
      }
    })
  },

  updateGoals: async (goals) => {
    const { version } = get()
    await api.updateGoals(version, goals)

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

  reset: () =>
    set({
      program: null,
      version: 'current',
      versions: [],
      isLoading: false,
      error: null,
      isDirty: false,
      activeSessionDate: null,
      activeSessionIndex: null,
    }),
}))
