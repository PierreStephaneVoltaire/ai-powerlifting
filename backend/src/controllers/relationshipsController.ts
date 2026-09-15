import { Request, Response } from 'express'
import { AppError } from '../middleware/errorHandler'
import {
  listFavorites,
  listNotifications,
  listRelationships,
  readNotifications,
  requestRelationship,
  respondRelationship,
  relationshipHistory,
  revokeRelationship,
  updateFavorite,
} from '../services/relationships'

function body(req: Request): Record<string, unknown> {
  if (!req.user) throw new AppError('Sign in required', 401, 'AUTH_REQUIRED')
  return req.body && typeof req.body === 'object' ? req.body as Record<string, unknown> : {}
}

export async function requestRelationshipHandler(req: Request, res: Response): Promise<void> {
  res.json({ data: await requestRelationship(body(req)) })
}

export async function respondRelationshipHandler(req: Request, res: Response): Promise<void> {
  res.json({ data: await respondRelationship(body(req)) })
}

export async function revokeRelationshipHandler(req: Request, res: Response): Promise<void> {
  res.json({ data: await revokeRelationship(body(req)) })
}

export async function listRelationshipsHandler(req: Request, res: Response): Promise<void> {
  body(req)
  res.json({ data: await listRelationships() })
}

export async function relationshipHistoryHandler(req: Request, res: Response): Promise<void> {
  body(req)
  res.json({ data: await relationshipHistory() })
}

export async function favoriteHandler(req: Request, res: Response): Promise<void> {
  res.json({ data: await updateFavorite(body(req)) })
}

export async function favoritesHandler(req: Request, res: Response): Promise<void> {
  body(req)
  res.json({ data: await listFavorites() })
}

export async function notificationsHandler(req: Request, res: Response): Promise<void> {
  body(req)
  res.json({ data: await listNotifications() })
}

export async function notificationsReadHandler(req: Request, res: Response): Promise<void> {
  res.json({ data: await readNotifications(body(req)) })
}
