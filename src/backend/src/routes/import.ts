import { Router } from 'express'
import multer from 'multer'
import * as importController from '../controllers/importController'

export const importRouter = Router()
const upload = multer({
  storage: multer.memoryStorage(),
  limits: { fileSize: 10 * 1024 * 1024 }, // 10 MB cap
  fileFilter: (req, file, cb) => {
    const ok = [
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      'application/vnd.ms-excel',
      'text/csv',
    ].includes(file.mimetype) || file.originalname.match(/\.(xlsx|xls|csv)$/i);
    cb(null, !!ok);
  },
})

// POST /api/import/upload
importRouter.post('/upload', upload.single('file'), importController.uploadImport)

// GET /api/import/pending
importRouter.get('/pending', importController.listPendingImports)

// GET /api/import/:importId
importRouter.get('/:importId', importController.getPendingImport)

// POST /api/import/:importId/apply
importRouter.post('/:importId/apply', importController.applyImport)

// POST /api/import/:importId/reject
importRouter.post('/:importId/reject', importController.rejectImport)
