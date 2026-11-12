import { Request, Response } from 'express'
import { deriveOnboardingStatus } from '../services/userSettings'
import { evaluateRbac } from '../auth/rbac'

export function listProviders(_req: Request, res: Response): void {
  res.json({ authentik: { enabled: true } })
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

export function logout(_req: Request, res: Response): void {
  res.json({ ok: true, redirect: '/oauth2/sign_out?rd=%2F' })
}
