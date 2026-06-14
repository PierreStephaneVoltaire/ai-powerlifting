import { Router } from 'express'
import multer from 'multer'
import * as templateController from '../controllers/templateController'

export const templateRouter = Router()
const upload = multer({
  storage: multer.memoryStorage(),
  limits: { fileSize: 10 * 1024 * 1024 },
  fileFilter: (_req, file, cb) => {
    const ok = [
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      'application/vnd.ms-excel',
      'text/csv',
    ].includes(file.mimetype) || Boolean(file.originalname.match(/\.(xlsx|xls|csv)$/i))
    cb(null, ok)
  },
})

// GET /api/templates
templateRouter.get('/', templateController.listTemplates)

// POST /api/templates/imports
templateRouter.post('/imports', upload.single('file'), templateController.uploadTemplateImport)

// GET /api/templates/imports/:jobId
templateRouter.get('/imports/:jobId', templateController.getTemplateImport)

// GET /api/templates/:sk
templateRouter.get('/:sk', templateController.getTemplate)

// POST /api/templates
templateRouter.post('/', templateController.createTemplateFromBlock)

// POST /api/templates/:sk/copy
templateRouter.post('/:sk/copy', templateController.copyTemplate)

// PATCH /api/templates/:sk/archive
templateRouter.patch('/:sk/archive', templateController.archiveTemplate)

// PATCH /api/templates/:sk/unarchive
templateRouter.patch('/:sk/unarchive', templateController.unarchiveTemplate)

// POST /api/templates/:sk/publish
templateRouter.post('/:sk/publish', templateController.publishTemplate)

// POST /api/templates/:sk/unpublish
templateRouter.post('/:sk/unpublish', templateController.unpublishTemplate)

// POST /api/templates/:sk/evaluate
templateRouter.post('/:sk/evaluate', templateController.evaluateTemplate)

// POST /api/templates/:sk/apply
templateRouter.post('/:sk/apply', templateController.applyTemplate)

// POST /api/templates/:sk/apply/confirm
templateRouter.post('/:sk/apply/confirm', templateController.confirmApplyTemplate)

// POST /api/templates/blank
templateRouter.post('/blank', templateController.createBlankTemplate)

// PUT /api/templates/:sk
templateRouter.put('/:sk', templateController.updateTemplate)
