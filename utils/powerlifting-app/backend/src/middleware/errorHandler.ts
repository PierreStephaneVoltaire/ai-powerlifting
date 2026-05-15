import { Request, Response, NextFunction } from 'express'
import { logger } from '../utils/logger'

export class AppError extends Error {
  statusCode: number
  code?: string

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
  const statusCode = err.statusCode || 500
  const message = err.message || 'Internal Server Error'

  logger.error({ err, statusCode }, message)

  res.status(statusCode).json({
    data: null,
    error: message,
    ...(err.code ? { code: err.code } : {}),
  })
}
