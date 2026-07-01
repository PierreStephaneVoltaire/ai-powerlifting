import { Router } from 'express'
import multer from 'multer'
import * as budgetController from '../controllers/budgetController'
import * as competitionController from '../controllers/competitionController'
import type { BudgetCategory, BudgetPriorityTier } from '@powerlifting/types'

const upload = multer({
  storage: multer.memoryStorage(),
  limits: { fileSize: 25 * 1024 * 1024 },
  fileFilter: (_req, file, cb) => {
    if (file.mimetype.startsWith('image/')) {
      cb(null, true)
    } else {
      cb(new Error('Invalid file type. Only images are allowed.'))
    }
  },
})

export const budgetRouter = Router()

// ─── Config ──────────────────────────────────────────────────────────────────

budgetRouter.get('/config', async (req, res, next) => {
  try {
    const config = await budgetController.getBudgetConfig(req.mapped_pk!)
    res.json({ data: config, error: null })
  } catch (err) {
    next(err)
  }
})

budgetRouter.put('/config', async (req, res, next) => {
  try {
    const config = await budgetController.putBudgetConfig(req.mapped_pk!, req.body)
    res.json({ data: config, error: null })
  } catch (err) {
    next(err)
  }
})

// ─── Items ───────────────────────────────────────────────────────────────────

function parseFilters(query: Record<string, unknown>): budgetController.BudgetItemFilters | undefined {
  const compId = typeof query.comp_id === 'string' ? query.comp_id : undefined
  const category =
    typeof query.category === 'string' ? (query.category as BudgetCategory) : undefined
  const priority =
    typeof query.priority === 'string' ? (query.priority as BudgetPriorityTier) : undefined
  if (compId === undefined && category === undefined && priority === undefined) return undefined
  return { comp_id: compId, category, priority }
}

budgetRouter.get('/items', async (req, res, next) => {
  try {
    const filters = parseFilters(req.query as Record<string, unknown>)
    const items = await budgetController.listBudgetItems(req.mapped_pk!, filters)
    res.json({ data: items, error: null })
  } catch (err) {
    next(err)
  }
})

budgetRouter.post('/items', async (req, res, next) => {
  try {
    const item = await budgetController.createBudgetItem(req.mapped_pk!, req.body)
    res.json({ data: item, error: null })
  } catch (err) {
    next(err)
  }
})

budgetRouter.put('/items/:id', async (req, res, next) => {
  try {
    const item = await budgetController.updateBudgetItem(req.mapped_pk!, req.params.id, req.body)
    res.json({ data: item, error: null })
  } catch (err) {
    next(err)
  }
})

budgetRouter.delete('/items/:id', async (req, res, next) => {
  try {
    await budgetController.deleteBudgetItem(req.mapped_pk!, req.params.id)
    res.json({ data: { success: true }, error: null })
  } catch (err) {
    next(err)
  }
})

budgetRouter.post('/items/:itemId/photo', upload.single('photo'), async (req, res, next) => {
  try {
    const file = req.file
    if (!file) {
      return res.status(400).json({ data: null, error: 'No photo file provided' })
    }
    const result = await budgetController.uploadItemPhoto(
      req.mapped_pk!,
      req.params.itemId,
      file.buffer,
      file.originalname,
      file.mimetype,
    )
    res.json({ data: result, error: null })
  } catch (err) {
    next(err)
  }
})

budgetRouter.delete('/items/:itemId/photo', async (req, res, next) => {
  try {
    await budgetController.deleteItemPhoto(req.mapped_pk!, req.params.itemId)
    res.json({ data: { success: true }, error: null })
  } catch (err) {
    next(err)
  }
})

budgetRouter.patch('/items/:id/cut', async (req, res, next) => {
  try {
    const body = req.body as { cut?: boolean } | null
    const cut = body?.cut !== false
    const item = await budgetController.markItemCut(req.mapped_pk!, req.params.id, cut)
    res.json({ data: item, error: null })
  } catch (err) {
    next(err)
  }
})

// ─── Summary ──────────────────────────────────────────────────────────────────

budgetRouter.get('/summary', async (req, res, next) => {
  try {
    const monthQuery = typeof req.query.month === 'string' ? req.query.month : ''
    const month = /^\d{4}-\d{2}$/.test(monthQuery)
      ? monthQuery
      : new Date().toISOString().slice(0, 7)
    const summary = await budgetController.getBudgetSummary(req.mapped_pk!, month)
    res.json({ data: summary, error: null })
  } catch (err) {
    next(err)
  }
})

// ─── AI advisor (BUD-05) ──────────────────────────────────────────────────────

budgetRouter.post('/ai-analysis', async (req, res, next) => {
  try {
    const refresh = req.query.refresh === 'true'
    if (refresh && req.readOnly) {
      return res.status(403).json({ data: null, error: 'Only the athlete can generate a fresh budget analysis.' })
    }
    const analysis = await budgetController.getBudgetAiAnalysis(req.mapped_pk!, refresh, async (pk) => {
      const competitions = await competitionController.getCompetitions(pk, 'current')
      return competitions.map((c) => ({
        master_id: c.date,
        name: c.name,
        start_date: c.date,
        user_status: c.status === 'completed' || c.status === 'skipped' ? c.status : 'optional',
      }))
    })
    res.json({ data: analysis, error: null })
  } catch (err) {
    next(err)
  }
})

// ─── Legacy whole-store read/write (backward compatibility) ───────────────────
//
// Kept so the existing frontend store (useBudgetStore) and the analytics budget
// timeline endpoint keep working until BUD-02..05 migrate to the granular API.

budgetRouter.get('/', async (req, res, next) => {
  try {
    const store = await budgetController.getBudget(req.mapped_pk!)
    res.json({ data: store, error: null })
  } catch (err) {
    next(err)
  }
})

budgetRouter.put('/', async (req, res, next) => {
  try {
    const { config, items } = req.body as { config?: unknown; items?: unknown[] }
    if (!config || typeof config !== 'object') {
      return res.status(400).json({ data: null, error: 'config must be an object' })
    }
    if (!Array.isArray(items)) {
      return res.status(400).json({ data: null, error: 'items must be an array' })
    }
    await budgetController.putBudget(req.mapped_pk!, config, items)
    res.json({ data: { success: true }, error: null })
  } catch (err) {
    next(err)
  }
})
