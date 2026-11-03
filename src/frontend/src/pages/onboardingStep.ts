export function onboardingStepFor(nextStep: string | null | undefined, activeRole: string | null | undefined, editing: boolean, editBasics: boolean): number {
  if (editing) return editBasics && activeRole === 'athlete' ? 2 : 0
  if (nextStep === 'role') return 0
  if (nextStep === 'profile') return 1
  return nextStep === 'athlete_basics' && activeRole === 'athlete' ? 2 : 1
}
