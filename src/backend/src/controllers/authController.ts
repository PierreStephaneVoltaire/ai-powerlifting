import { Request, Response } from 'express'
import passport from 'passport'
import { deriveOnboardingStatus } from '../services/userSettings'
import { evaluateRbac } from '../auth/rbac'

const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:5173'

export const discordLogin = passport.authenticate('discord')
export const authentikLogin = passport.authenticate('authentik')
const discordCallback = passport.authenticate('discord', { failureRedirect: `${FRONTEND_URL}/login?error=auth_failed` })
const authentikCallback = passport.authenticate('authentik', { failureRedirect: `${FRONTEND_URL}/login?error=auth_failed` })
export const discordCallbackRoute = [discordCallback, (_req: Request, res: Response) => res.redirect(FRONTEND_URL)]
export const authentikCallbackRoute = [authentikCallback, (_req: Request, res: Response) => res.redirect(FRONTEND_URL)]

export function listProviders(_req: Request, res: Response): void {
  res.json({ discord: { enabled: isDiscordConfigured() }, authentik: { enabled: isAuthentikConfigured() } })
}

function isAuthentikConfigured(): boolean {
  return Boolean(process.env.AUTHENTIK_ISSUER_URL && process.env.AUTHENTIK_CLIENT_ID && process.env.AUTHENTIK_CLIENT_SECRET && process.env.AUTHENTIK_REDIRECT_URI)
}

function isDiscordConfigured(): boolean {
  return Boolean(process.env.DISCORD_CLIENT_ID && process.env.DISCORD_CLIENT_SECRET && process.env.DISCORD_REDIRECT_URI)
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
