export function formatCurrency(amount: number, currency: string = 'CAD'): string {
  return new Intl.NumberFormat('en-CA', {
    style: 'currency',
    currency,
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(amount)
}

export function formatDate(dateStr: string | null | undefined): string {
  if (!dateStr) return 'N/A'
  const date = new Date(dateStr)
  return new Intl.DateTimeFormat('en-CA', {
    month: 'short',
    day: 'numeric',
  }).format(date)
}

export function formatDaysUntil(days: number | null): string {
  if (days === null) return 'N/A'
  if (days === 0) return 'Today'
  if (days === 1) return 'Tomorrow'
  if (days < 0) return `${Math.abs(days)} days ago`
  return `${days} days`
}

export function formatRelativeTime(dateStr: string | null | undefined): string {
  if (!dateStr) return ''
  const date = new Date(dateStr)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffMins = Math.floor(diffMs / 60000)
  const diffHours = Math.floor(diffMins / 60)
  const diffDays = Math.floor(diffHours / 24)

  if (diffMins < 1) return 'Just now'
  if (diffMins < 60) return `${diffMins}m ago`
  if (diffHours < 24) return `${diffHours}h ago`
  if (diffDays < 7) return `${diffDays}d ago`
  return formatDate(dateStr)
}

export function getTrendIcon(trend: string): string {
  switch (trend) {
    case 'improving': return '↑'
    case 'declining_slow': return '↓'
    case 'declining_fast': return '↓↓'
    case 'stable':
    default: return '→'
  }
}

// getScoreColor: returns a CSS color string
export function getScoreColor(score: number): string {
  if (score >= 7) return 'var(--status-success-text)'
  if (score >= 4) return 'var(--status-warning-text)'
  return 'var(--status-danger-text)'
}

// getTrendColor: returns a CSS color string
export function getTrendColor(trend: string): string {
  if (trend === 'improving') return 'var(--status-success-text)'
  if (trend === 'declining_slow' || trend === 'declining_fast') return 'var(--status-danger-text)'
  return 'var(--text-secondary)'
}

// getLifeLoadColor: returns an object with bg, text, border CSS var strings
export function getLifeLoadColor(load: string): { bg: string; text: string; border: string } {
  if (load === 'low') return { bg: 'var(--status-success-bg)', text: 'var(--status-success-text)', border: 'var(--status-success-border)' }
  if (load === 'high' || load === 'very_high') return { bg: 'var(--status-danger-bg)', text: 'var(--status-danger-text)', border: 'var(--status-danger-border)' }
  return { bg: 'var(--status-neutral-bg)', text: 'var(--status-neutral-text)', border: 'var(--status-neutral-border)' }
}
