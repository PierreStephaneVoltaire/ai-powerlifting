import { Request, Response } from 'express'
import {
  deriveOnboardingStatus,
  getSettings,
  getOrCreateSettings,
  updateAthleteBasics,
  updateOnboardingProfile,
  updateRole,
  ValidationError,
} from '../services/userSettings'
import { reissueTokenFromSettings } from '../middleware/auth'

function sendError(res: Response, status: number, error: string): void {
  res.status(status).json({ data: null, error })
}

function handleValidation(res: Response, err: unknown): void {
  if (err instanceof ValidationError) {
    sendError(res, 400, err.message)
    return
  }
  const message = err instanceof Error ? err.message : 'Internal error'
  sendError(res, 500, message)
}

async function refreshAuthClaims(req: Request, res: Response, username: string): Promise<void> {
  if (!req.user?.identity) return
  try {
    await reissueTokenFromSettings(
      res,
      {
        provider: req.user.identity.provider,
        sub: req.user.identity.sub,
        username: req.user.identity.username,
        display_name: req.user.identity.display_name,
        avatar: req.user.identity.avatar,
        groups: req.user.identity.groups,
        roles: req.user.identity.roles,
        email: req.user.identity.email ?? null,
        active_role: req.user.identity.active_role ?? null,
        discord_id: req.user.discord_id,
      },
      username,
    )
  } catch (err) {
    // Token refresh failures must not break the write — the user can still see
    // their updated state on the next page load, and the claims will be picked
    // up on the next login.
    console.warn('Failed to reissue auth token after onboarding step:', err)
  }
}

export async function getOnboardingStatusHandler(req: Request, res: Response): Promise<void> {
  try {
    if (!req.user?.discord_id || !req.user.username) {
      sendError(res, 401, 'Authentication required')
      return
    }
    const existing = await getSettings(req.user.username)
    const settings =
      existing ??
      (await getOrCreateSettings(
        req.user.discord_id,
        req.user.username,
        req.user.avatar ?? null,
      ))
    res.json({ data: deriveOnboardingStatus(settings) })
  } catch (err) {
    handleValidation(res, err)
  }
}

export async function completeAthleteBasicsHandler(req: Request, res: Response): Promise<void> {
  try {
    if (!req.user?.username) {
      sendError(res, 401, 'Authentication required')
      return
    }
    const settings = await updateAthleteBasics(req.user.username, req.body)
    await refreshAuthClaims(req, res, req.user.username)
    res.json({ data: settings })
  } catch (err) {
    handleValidation(res, err)
  }
}

export async function completeProfileHandler(req: Request, res: Response): Promise<void> {
  try {
    if (!req.user?.username) {
      sendError(res, 401, 'Authentication required')
      return
    }
    const settings = await updateOnboardingProfile(req.user.username, req.body)
    await refreshAuthClaims(req, res, req.user.username)
    res.json({ data: settings })
  } catch (err) {
    handleValidation(res, err)
  }
}

export async function setRoleHandler(req: Request, res: Response): Promise<void> {
  try {
    if (!req.user?.username) {
      sendError(res, 401, 'Authentication required')
      return
    }
    const settings = await updateRole(req.user.username, req.body)
    await refreshAuthClaims(req, res, req.user.username)
    res.json({ data: settings })
  } catch (err) {
    handleValidation(res, err)
  }
}
