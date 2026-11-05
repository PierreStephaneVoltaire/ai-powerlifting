import { Request, Response } from 'express'
import { callOperation } from '../utils/lambda'

export async function getPublication(_req: Request, res: Response): Promise<void> {
  res.json({ data: await callOperation('settings_publication_get', {}) })
}

export async function updatePublication(req: Request, res: Response): Promise<void> {
  res.json({ data: await callOperation('settings_publication_update', req.body) })
}
