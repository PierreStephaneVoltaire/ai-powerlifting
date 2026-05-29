// API response types for the Main Portal Hub

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

// Individual portal response types (what we expect from each portal)

export interface HealthPortalResponse {
  current_program?: {
    week: string
    name: string
    training_status: string
  }
  next_session?: {
    date: string
    completed: boolean
  } | null
  comp?: {
    date: string
    days_until: number
  }
}

export interface FinancePortalResponse {
  net_worth_snapshot?: {
    net_worth: number
    as_of: string
  }
  monthly_cashflow?: {
    monthly_surplus: number
    as_of: string
  }
  accounts?: {
    credit_cards?: Array<{
      label: string
      utilization_pct: number
    }>
  }
  tax?: {
    tfsa_room_used_this_year?: number
    unused_tfsa_room?: number
  }
}

export interface DiaryPortalResponse {
  latest_signal?: {
    score: number
    trend: string
    life_load: string
    social_battery?: string
    themes?: string[]
    note?: string
    computed_at: string
  }
  active_entry_count?: number
}

export interface ProposalsPortalResponse {
  proposals?: Array<{
    sk: string
    type: string
    status: string
    author: string
    title: string
    created_at: string
  }>
  total?: number
}
