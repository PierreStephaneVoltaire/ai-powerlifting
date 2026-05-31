import type {
  HubStatusResponse,
  SignalsData,
  FinanceData,
  HealthData,
  ProposalsData,
  DiaryData,
  HealthPortalResponse,
  FinancePortalResponse,
  DiaryPortalResponse,
  ProposalsPortalResponse,
} from '../types/index.ts'

const FINANCE_PORTAL_URL = process.env.FINANCE_PORTAL_URL || 'http://localhost:3002'
const HEALTH_PORTAL_URL = process.env.HEALTH_PORTAL_URL || 'http://localhost:3001'
const DIARY_PORTAL_URL = process.env.DIARY_PORTAL_URL || 'http://localhost:3003'
const PROPOSALS_PORTAL_URL = process.env.PROPOSALS_PORTAL_URL || 'http://localhost:3004'
const DIRECTIVES_PORTAL_URL = process.env.DIRECTIVES_PORTAL_URL || 'http://localhost:3006'

async function fetchPortal<T>(url: string, label: string): Promise<{ data: T | null; reachable: boolean }> {
  try {
    const response = await fetch(url, {
      method: 'GET',
      headers: { 'Content-Type': 'application/json' },
      signal: AbortSignal.timeout(5000),
    })

    if (!response.ok) {
      console.warn(`${label} returned ${response.status}`)
      return { data: null, reachable: false }
    }

    const json = await response.json() as Record<string, unknown>
    return { data: (json.data ?? json) as T, reachable: true }
  } catch (error) {
    console.warn(`${label} unreachable:`, error instanceof Error ? error.message : error)
    return { data: null, reachable: false }
  }
}

function computeAlerts(
  signals: SignalsData | null,
  finance: FinanceData | null,
  health: HealthData | null
): string[] {
  const alerts: string[] = []
  const currentMonth = new Date().getMonth() + 1

  // Finance alerts
  if (finance) {
    if (finance.credit_card_utilization_pct && finance.credit_card_utilization_pct > 40) {
      alerts.push(`CC utilization: ${finance.credit_card_utilization_pct.toFixed(0)}%`)
    }
    if (finance.tfsa_room_remaining && finance.tfsa_room_remaining > 5000 && currentMonth >= 10) {
      alerts.push(`TFSA room unused: $${finance.tfsa_room_remaining.toLocaleString()}`)
    }
  }

  // Health alerts
  if (health) {
    if (health.days_to_comp !== null && health.days_to_comp <= 14) {
      alerts.push(`Comp in ${health.days_to_comp} days — check weight class`)
    }
  }

  // Signal alerts
  if (signals) {
    if (signals.mental_health_score < 4) {
      alerts.push(`Mental health signal: low (${signals.mental_health_score.toFixed(1)})`)
    }
    if (signals.trend === 'declining_fast') {
      alerts.push('Mental health trending down fast')
    }
  }

  return alerts
}

export async function getHubStatus(): Promise<HubStatusResponse> {
  const [healthResult, financeResult, diaryResult, proposalsResult, directivesResult] = await Promise.allSettled([
    fetchPortal<HealthPortalResponse>(`${HEALTH_PORTAL_URL}/api/programs/current`, 'Health Portal'),
    fetchPortal<FinancePortalResponse>(`${FINANCE_PORTAL_URL}/api/finance/current`, 'Finance Portal'),
    fetchPortal<DiaryPortalResponse>(`${DIARY_PORTAL_URL}/api/signals/latest`, 'Diary Portal'),
    fetchPortal<ProposalsPortalResponse>(`${PROPOSALS_PORTAL_URL}/api/proposals?status=pending`, 'Proposals Portal'),
    fetchPortal<unknown>(`${DIRECTIVES_PORTAL_URL}/health`, 'Directives Portal'),
  ])

  const health = healthResult.status === 'fulfilled' ? healthResult.value : { data: null, reachable: false }
  const finance = financeResult.status === 'fulfilled' ? financeResult.value : { data: null, reachable: false }
  const diary = diaryResult.status === 'fulfilled' ? diaryResult.value : { data: null, reachable: false }
  const proposals = proposalsResult.status === 'fulfilled' ? proposalsResult.value : { data: null, reachable: false }
  const directives = directivesResult.status === 'fulfilled' ? directivesResult.value : { data: null, reachable: false }

  // Transform health data
  const healthData: HealthData | null = health.data ? {
    current_week: health.data.current_program?.week || 'N/A',
    next_session_date: health.data.next_session?.date || null,
    days_to_comp: health.data.comp?.days_until ?? null,
    training_status: health.data.current_program?.training_status as HealthData['training_status'],
    current_program: health.data.current_program?.name,
  } : null

  // Transform finance data
  const financeData: FinanceData | null = finance.data ? {
    net_worth: finance.data.net_worth_snapshot?.net_worth ?? 0,
    monthly_surplus: finance.data.monthly_cashflow?.monthly_surplus ?? 0,
    credit_card_utilization_pct: finance.data.accounts?.credit_cards?.[0]?.utilization_pct,
    tfsa_room_remaining: finance.data.tax?.unused_tfsa_room,
  } : null

  // Transform diary/signals data
  const signalsData: SignalsData | null = diary.data?.latest_signal ? {
    mental_health_score: diary.data.latest_signal.score,
    trend: diary.data.latest_signal.trend as SignalsData['trend'],
    life_load: diary.data.latest_signal.life_load as SignalsData['life_load'],
    social_battery: diary.data.latest_signal.social_battery as SignalsData['social_battery'],
    themes: diary.data.latest_signal.themes,
    note: diary.data.latest_signal.note,
  } : null

  const diaryData: DiaryData | null = diary.data ? {
    latest_score: diary.data.latest_signal?.score ?? 0,
    active_entry_count: diary.data.active_entry_count ?? 0,
  } : null

  // Transform proposals data
  const pendingProposals = proposals.data?.proposals?.filter((p) => p.status === 'pending') ?? []
  const proposalsData: ProposalsData | null = proposals.data ? {
    pending_count: pendingProposals.length,
    latest_created_at: pendingProposals[0]?.created_at,
    breakdown: {
      agent: pendingProposals.filter((p) => p.author === 'agent').length,
      user: pendingProposals.filter((p) => p.author === 'user').length,
    },
  } : null

  const alerts = computeAlerts(signalsData, financeData, healthData)

  return {
    signals: signalsData,
    finance: financeData,
    health: healthData,
    proposals: proposalsData,
    diary: diaryData,
    alerts,
    portal_status: {
      health: health.reachable ? 'reachable' : 'unreachable',
      finance: finance.reachable ? 'reachable' : 'unreachable',
      diary: diary.reachable ? 'reachable' : 'unreachable',
      proposals: proposals.reachable ? 'reachable' : 'unreachable',
      directives: directives.reachable ? 'reachable' : 'unreachable',
    },
    computed_at: new Date().toISOString(),
  }
}
