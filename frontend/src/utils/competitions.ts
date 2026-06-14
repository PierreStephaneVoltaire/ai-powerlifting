import type { Competition, UserCompetition } from '@powerlifting/types'

export function userCompToCompetition(uc: UserCompetition): Competition {
  return {
    name: uc.name,
    date: uc.start_date,
    federation: uc.federation_label || '',
    federation_id: uc.federation_id || undefined,
    counts_toward_federation_ids: uc.counts_toward_federation_ids?.length ? uc.counts_toward_federation_ids : undefined,
    location: undefined,
    hotel_required: uc.hotel_required,
    status: (uc.user_status === 'available' ? 'optional' : uc.user_status) as Competition['status'],
    weight_class_kg: uc.weight_class_kg ?? 0,
    body_weight_kg: uc.body_weight_kg ?? undefined,
    qualifying_standard_id: uc.qualifying_standard_id ?? undefined,
    qualifying_total_kg: uc.qualifying_total_kg ?? undefined,
    attempt_strategy_mode: uc.attempt_strategy_mode ?? undefined,
    targets: uc.targets ?? undefined,
    projected_at_t_minus_1w: uc.projected_at_t_minus_1w ?? undefined,
    projection_snapshot_date: uc.projection_snapshot_date ?? undefined,
    results: uc.results ?? undefined,
    post_meet_report: uc.post_meet_report ?? undefined,
    notes: uc.notes || undefined,
    decision_date: uc.decision_date ?? null,
    between_comp_plan: uc.between_comp_plan ?? undefined,
    comp_day_protocol: uc.comp_day_protocol ?? undefined,
  }
}
