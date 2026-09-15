import { Request, Response, NextFunction } from 'express'
import { logger } from '../utils/logger'

export class AppError extends Error {
  statusCode: number
  code?: string
  current_revision?: number
  current_record?: unknown

  constructor(message: string, statusCode: number = 500, code?: string) {
    super(message)
    this.statusCode = statusCode
    this.code = code
    this.name = 'AppError'
  }
}

export function errorHandler(
  err: AppError,
  _req: Request,
  res: Response,
  _next: NextFunction
): void {
  if (res.headersSent) { _next(err); return }
  const statusCode = err.statusCode || 500
  const message = err.message || 'Internal Server Error'

  logger.error({ err, statusCode }, message)

  res.status(statusCode).json({
    data: null,
    error: message,
    ...(err.current_revision !== undefined ? { current_revision: err.current_revision, current_record: err.current_record } : {}),
    ...(err.code ? { code: err.code } : {}),
  })
}
