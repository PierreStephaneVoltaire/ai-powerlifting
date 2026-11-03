import { Request, Response } from 'express'
import { invokeLambda } from '../utils/lambda'

export async function getPublication(_req: Request, res: Response): Promise<void> {
  res.json({ data: await invokeLambda('settings_publication_get', {}) })
}

export async function updatePublication(req: Request, res: Response): Promise<void> {
  res.json({ data: await invokeLambda('settings_publication_update', req.body) })
}
