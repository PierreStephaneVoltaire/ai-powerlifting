import { Request, Response } from 'express'
import { invokeLambda } from '../utils/lambda'
import { AppError } from '../middleware/errorHandler'

type InitializeBody = {
  mode?: string
  programName?: string
  startDate?: string
  weekStartDay?: string
  templateSk?: string
  maxes?: Record<string, number>
}

function setupError(error: unknown): AppError {
  const message = error instanceof Error ? error.message : String(error)

  if (message.includes('ALREADY_INITIALIZED')) {
    return new AppError('Current program already exists', 409, 'ALREADY_INITIALIZED')
  }
  if (message.includes('INVALID_SETUP_MODE')) {
    return new AppError('mode must be blank, manual_sessions, or template', 400, 'INVALID_SETUP_MODE')
  }
  if (message.includes('INVALID_START_DATE')) {
    return new AppError('startDate must use YYYY-MM-DD format', 400, 'INVALID_START_DATE')
  }
  if (message.includes('INVALID_WEEK_START_DAY')) {
    return new AppError('weekStartDay must be a valid weekday name', 400, 'INVALID_WEEK_START_DAY')
  }
  if (message.includes('TEMPLATE_REQUIRED')) {
    return new AppError('templateSk is required for template setup', 400, 'TEMPLATE_REQUIRED')
  }
  if (message.includes('TEMPLATE_NOT_FOUND')) {
    return new AppError('Template not found', 404, 'TEMPLATE_NOT_FOUND')
  }

  return new AppError(`Setup failed: ${message}`, 502)
}

export async function getSetupStatus(req: Request, res: Response): Promise<void> {
  try {
    const result = await invokeLambda('health_setup_status', { pk: req.mapped_pk })
    res.json({
      data: {
        mapped_pk: req.mapped_pk ?? result.mapped_pk ?? 'operator',
        authenticated: Boolean(req.user),
        readOnly: Boolean(req.readOnly),
        hasCurrentProgram: Boolean(result.hasCurrentProgram),
        needsSetup: Boolean(result.needsSetup),
      },
      error: null,
    })
  } catch (error) {
    throw setupError(error)
  }
}

export async function initializeSetup(req: Request, res: Response): Promise<void> {
  if (!req.user || req.readOnly) {
    throw new AppError('Sign in required', 401, 'AUTH_REQUIRED')
  }

  const body = req.body as InitializeBody
  try {
    const result = await invokeLambda('health_setup_initialize', {
      pk: req.mapped_pk,
      mode: body.mode,
      program_name: body.programName,
      start_date: body.startDate,
      week_start_day: body.weekStartDay,
      template_sk: body.templateSk,
      maxes: body.maxes,
    })

    const status = result?.status
    res.status(status === 'initialized' ? 201 : 200).json({ data: result, error: null })
  } catch (error) {
    throw setupError(error)
  }
}
