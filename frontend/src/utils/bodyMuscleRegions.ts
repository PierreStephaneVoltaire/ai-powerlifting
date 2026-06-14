import type { MuscleId } from 'body-muscles'
import type { MuscleGroup } from '@powerlifting/types'
import { MUSCLE_DISPLAY_NAMES } from '@/utils/muscles'

export const ALL_MUSCLE_GROUPS = Object.keys(MUSCLE_DISPLAY_NAMES) as MuscleGroup[]

export const MUSCLE_REGION_MAP: Partial<Record<MuscleGroup, MuscleId[]>> = {
  quads: ['quads-left', 'quads-right', 'knee-left', 'knee-right'],
  hamstrings: ['hamstrings-medial-left', 'hamstrings-lateral-left', 'hamstrings-medial-right', 'hamstrings-lateral-right', 'knee-back-left', 'knee-back-right'],
  glutes: ['gluteus-medius-left', 'gluteus-maximus-left', 'gluteus-medius-right', 'gluteus-maximus-right'],
  calves: [
    'calves-gastroc-medial-left',
    'calves-gastroc-lateral-left',
    'calves-soleus-left',
    'calves-gastroc-medial-right',
    'calves-gastroc-lateral-right',
    'calves-soleus-right',
  ],
  tibialis_anterior: ['tibialis-anterior-left', 'tibialis-anterior-right'],
  hip_flexors: ['hip-flexor-left', 'hip-flexor-right'],
  adductors: ['adductors-left', 'adductors-right'],
  chest: ['chest-upper-left', 'chest-lower-left', 'chest-upper-right', 'chest-lower-right'],
  triceps: ['triceps-long-left', 'triceps-lateral-left', 'triceps-long-right', 'triceps-lateral-right'],
  front_delts: ['shoulder-front-left', 'shoulder-front-right'],
  side_delts: ['shoulder-side-left', 'shoulder-side-right'],
  rear_delts: ['deltoid-rear-left', 'deltoid-rear-right'],
  lats: ['lats-upper-left', 'lats-mid-left', 'lats-lower-left', 'lats-upper-right', 'lats-mid-right', 'lats-lower-right'],
  traps: ['traps-upper-left', 'traps-mid-left', 'traps-lower-left', 'traps-upper-right', 'traps-mid-right', 'traps-lower-right'],
  rhomboids: ['traps-mid-left', 'traps-mid-right'],
  teres_major: ['lats-upper-left', 'lats-upper-right'],
  biceps: ['biceps-left', 'biceps-right'],
  forearms: ['forearm-left', 'forearm-right', 'forearm-flexors-left', 'forearm-extensors-left', 'forearm-flexors-right', 'forearm-extensors-right'],
  erectors: ['spine', 'lower-back-erectors-left', 'lower-back-erectors-right'],
  lower_back: ['spine', 'lower-back-erectors-left', 'lower-back-ql-left', 'lower-back-erectors-right', 'lower-back-ql-right'],
  core: ['abs-upper-left', 'abs-lower-left', 'abs-upper-right', 'abs-lower-right'],
  obliques: ['obliques-left', 'obliques-right'],
  serratus: ['serratus-anterior-left', 'serratus-anterior-right'],
}
