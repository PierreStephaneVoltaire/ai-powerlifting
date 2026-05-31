// Types matching the backend API response and MAIN_PORTAL_PLAN.md spec

export interface SignalsData {
  mental_health_score: number
  trend: 'stable' | 'improving' | 'declining_slow' | 'declining_fast'
  life_load: 'low' | 'moderate' | 'high' | 'very_high'
  social_battery?: 'low' | 'moderate' | 'high'
  themes?: string[]
  note?: string
}

export interface FinanceData {
  net_worth: number
  monthly_surplus: number
  pending_alerts?: string[]
  credit_card_utilization_pct?: number
  tfsa_room_remaining?: number
}

export interface HealthData {
  current_week: string
  next_session_date: string | null
  days_to_comp: number | null
  training_status?: 'off_season' | 'building' | 'peaking' | 'deloading' | 'recovering'
  current_program?: string
}

export interface ProposalsData {
  pending_count: number
  latest_created_at?: string
  breakdown?: {
    agent: number
    user: number
  }
}

export interface DiaryData {
  latest_score: number
  active_entry_count: number
}

export interface HubStatusResponse {
  signals: SignalsData | null
  finance: FinanceData | null
  health: HealthData | null
  proposals: ProposalsData | null
  diary: DiaryData | null
  alerts: string[]
  portal_status: {
    health: 'reachable' | 'unreachable'
    finance: 'reachable' | 'unreachable'
    diary: 'reachable' | 'unreachable'
    proposals: 'reachable' | 'unreachable'
    directives: 'reachable' | 'unreachable'
  }
  computed_at: string
}
