import { Router, type Request, type Response } from 'express'
import { invokeLambda } from '../utils/lambda'

export const exportRouter = Router()

type ExportFormat = 'xlsx' | 'markdown'

const EXPORT_DEFAULTS: Record<ExportFormat, { filename: string; contentType: string }> = {
  xlsx: {
    filename: 'program_history.xlsx',
    contentType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  },
  markdown: {
    filename: 'program_history.md',
    contentType: 'text/markdown; charset=utf-8',
  },
}

async function proxyExport(req: Request, res: Response, format: ExportFormat): Promise<void> {
  try {
    const pk = req.mapped_pk || 'operator'
    const defaults = EXPORT_DEFAULTS[format]
    const exported = await invokeLambda('export_program_history', { pk, format }) as { filename: string; format: ExportFormat; content_base64: string }
    if (exported.format !== format || !exported.content_base64) throw new Error('Invalid export response')
    res.setHeader('Content-Type', defaults.contentType)
    res.setHeader('Content-Disposition', `attachment; filename="${exported.filename || defaults.filename}"`)
    res.end(Buffer.from(exported.content_base64, 'base64'))
  } catch (err) {
    res.status(502).json({ data: null, error: `Proxy error: ${err}` })
  }
}

exportRouter.get('/xlsx', async (req, res) => {
  await proxyExport(req, res, 'xlsx')
})

exportRouter.get('/markdown', async (req, res) => {
  await proxyExport(req, res, 'markdown')
})
