import { Request, Response, NextFunction } from 'express'
import { AppError } from './errorHandler'

export function validateBody<T>(
  validator: (body: unknown) => body is T
): (req: Request, _res: Response, next: NextFunction) => void {
  return (req: Request, _res: Response, next: NextFunction) => {
    if (!validator(req.body)) {
      return next(new AppError('Invalid request body', 400))
    }
    next()
  }
}

// Common validators
export function hasField<K extends string>(obj: unknown, field: K): obj is Record<K, unknown> {
  return typeof obj === 'object' && obj !== null && field in obj
}

export function isString(value: unknown): value is string {
  return typeof value === 'string'
}

export function isNumber(value: unknown): value is number {
  return typeof value === 'number' && !isNaN(value)
}

export function isBoolean(value: unknown): value is boolean {
  return typeof value === 'boolean'
}
