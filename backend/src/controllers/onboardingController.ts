import { Request, Response } from 'express'
import { AppError } from '../middleware/errorHandler'
import {
  updateAthleteBasics,
  updateOnboardingProfile,
  updateRole,
  ValidationError,
} from '../services/userSettings'
import { invokeLambda } from '../utils/lambda'

function sendError(res: Response, status: number, error: string): void {
  res.status(status).json({ data: null, error })
}

function handleValidation(res: Response, err: unknown): void {
  if (err instanceof AppError) {
    res.status(err.statusCode).json({ data: null, error: err.message, code: err.code })
    return
  }
  if (err instanceof ValidationError) {
    sendError(res, 400, err.message)
    return
  }
  const message = err instanceof Error ? err.message : 'Internal error'
  sendError(res, 500, message)
}

export async function getOnboardingStatusHandler(req: Request, res: Response): Promise<void> {
  try {
    if (!req.user || !req.settings) {
      sendError(res, 401, 'Authentication required')
      return
    }
    res.json({ data: await invokeLambda('onboarding_status', {}) })
  } catch (err) {
    handleValidation(res, err)
  }
}

export async function completeAthleteBasicsHandler(req: Request, res: Response): Promise<void> {
  try {
    if (!req.actor_mapped_pk) {
      sendError(res, 401, 'Authentication required')
      return
    }
    const settings = await updateAthleteBasics(req.actor_mapped_pk!, req.body)
    res.json({ data: settings })
  } catch (err) {
    handleValidation(res, err)
  }
}

export async function completeProfileHandler(req: Request, res: Response): Promise<void> {
  try {
    if (!req.actor_mapped_pk) {
      sendError(res, 401, 'Authentication required')
      return
    }
    const settings = await updateOnboardingProfile(req.actor_mapped_pk!, req.body)
    res.json({ data: settings })
  } catch (err) {
    handleValidation(res, err)
  }
}

export async function setRoleHandler(req: Request, res: Response): Promise<void> {
  try {
    if (!req.actor_mapped_pk) {
      sendError(res, 401, 'Authentication required')
      return
    }
    const settings = await updateRole(req.actor_mapped_pk!, req.body)
    res.json({ data: settings })
  } catch (err) {
    handleValidation(res, err)
  }
}
