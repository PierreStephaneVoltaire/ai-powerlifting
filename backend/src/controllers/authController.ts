import { Request, Response } from 'express'
import passport from 'passport'
import { deriveOnboardingStatus } from '../services/userSettings'
import { evaluateRbac } from '../auth/rbac'

const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:5173'

function configuredAuthentikOrigin(): string {
  return process.env.AUTHENTIK_ISSUER_URL ? new URL(process.env.AUTHENTIK_ISSUER_URL).origin : ''
}
export function discordSourceRedirect(url: string, origin = configuredAuthentikOrigin()): string | null {
  return origin && url.startsWith(`${origin}/application/o/authorize/`)
    ? `${origin}/source/oauth/login/discord/?next=${encodeURIComponent(url)}`
    : null
}
export function discordLogin(req: Request, res: Response, next: (error?: unknown) => void): void {
  const setHeader = res.setHeader.bind(res)
  const end = res.end.bind(res) as Response['end']
  const restore = () => {
    res.setHeader = setHeader
    res.end = end
  }
  res.setHeader = ((name, value) => {
    const headerValue = typeof value === 'string' && name.toLowerCase() === 'location' ? discordSourceRedirect(value) || value : value
    return setHeader(name, headerValue)
  }) as Response['setHeader']
  res.end = ((...args) => {
    restore()
    return (end as (...values: unknown[]) => Response)(...args)
  }) as Response['end']
  passport.authenticate('authentik')(req, res, (error?: unknown) => {
    restore()
    next(error)
  })
}
export const authentikLogin = passport.authenticate('authentik')
const callback = passport.authenticate('authentik', { failureRedirect: `${FRONTEND_URL}/login?error=auth_failed` })
export const discordCallback = [callback, (_req: Request, res: Response) => res.redirect(FRONTEND_URL)]
export const authentikCallback = discordCallback

export function listProviders(_req: Request, res: Response): void {
  res.json({ discord: { enabled: isAuthentikConfigured() }, authentik: { enabled: isAuthentikConfigured() } })
}

function isAuthentikConfigured(): boolean {
  return Boolean(process.env.AUTHENTIK_ISSUER_URL && process.env.AUTHENTIK_CLIENT_ID && process.env.AUTHENTIK_CLIENT_SECRET && process.env.AUTHENTIK_REDIRECT_URI)
}

export async function getMe(req: Request, res: Response): Promise<void> {
  const settings = req.settings
  const access = await evaluateRbac(req)
  res.json({
    user: req.user ? { ...req.user.identity, roles: settings?.roles || [], active_role: settings?.active_role || null, display_name: settings?.display_name || req.user.identity.display_name, avatar: settings?.avatar_url || req.user.identity.avatar, discord_id: req.user.discord_id } : null,
    person_pk: req.actor_mapped_pk || null, own_athlete_pk: settings?.mapped_pk || settings?.pk || null,
    mapped_pk: req.mapped_pk ?? 'operator', readOnly: req.readOnly ?? true,
    ranking_country: settings?.ranking_country ?? null, ranking_region: settings?.ranking_region ?? null, age_class: settings?.age_class ?? 'open',
    access,
    onboarding: settings ? deriveOnboardingStatus(settings) : null,
  })
}

export function logout(req: Request, res: Response): void {
  req.logout((error) => {
    if (error) { res.status(500).json({ ok: false }); return }
    req.session.destroy(() => res.clearCookie('connect.sid').json({ ok: true }))
  })
}
