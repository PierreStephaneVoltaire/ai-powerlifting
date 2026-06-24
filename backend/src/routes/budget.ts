import { Router } from 'express'
import multer from 'multer'
import * as budgetController from '../controllers/budgetController'

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
