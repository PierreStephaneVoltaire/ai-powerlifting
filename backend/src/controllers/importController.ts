import { Request, Response } from 'express'
import { invokeToolDirect } from '../utils/agent'
import { AppError } from '../middleware/errorHandler'
import type { ImportType } from '@powerlifting/types'

export async function uploadImport(req: Request, res: Response) {
  if (!req.file) {
    throw new AppError('No file uploaded', 400)
  }

  const base64_content = req.file.buffer.toString('base64')
  const filename = req.file.originalname

  try {
    const result = await invokeToolDirect('import_parse_file', { base64_content, filename, pk: req.mapped_pk })
    res.status(201).json(result)
  } catch (err: any) {
    throw new AppError(`Import failed: ${err.message}`, 502)
  }
}

export async function listPendingImports(req: Request, res: Response) {
  const import_type = req.query.type as ImportType | undefined
  try {
    const data = await invokeToolDirect('import_list_pending', { import_type, pk: req.mapped_pk })
    res.json(data)
  } catch (err: any) {
    throw new AppError(`List failed: ${err.message}`, 502)
  }
}

export async function getPendingImport(req: Request, res: Response) {
  const { importId } = req.params
  try {
    const data = await invokeToolDirect('import_get_pending', { import_id: importId, pk: req.mapped_pk })
    res.json(data)
  } catch (err: any) {
    if (err.message?.includes('not found')) throw new AppError('Import not found', 404)
    throw new AppError(`Get failed: ${err.message}`, 502)
  }
}

export async function applyImport(req: Request, res: Response) {
  const { importId } = req.params
  const { merge_strategy, conflict_resolutions, start_date } = req.body

  try {
    const result = await invokeToolDirect('import_apply', {
      import_id: importId,
      merge_strategy,
      conflict_resolutions,
      start_date,
      pk: req.mapped_pk,
    })
    res.json(result)
  } catch (err: any) {
    throw new AppError(`Apply failed: ${err.message}`, 502)
  }
}

export async function rejectImport(req: Request, res: Response) {
  const { importId } = req.params
  const { reason } = req.body

  try {
    const result = await invokeToolDirect('import_reject', { import_id: importId, reason, pk: req.mapped_pk })
    res.json(result)
  } catch (err: any) {
    throw new AppError(`Reject failed: ${err.message}`, 502)
  }
}
