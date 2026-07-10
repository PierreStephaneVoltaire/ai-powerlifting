import { Router } from 'express'
import multer from 'multer'
import { getSettingsHandler, updateAvatarHandler, updateNicknameHandler, updateProfileHandler, updateRankingLocationHandler, updateAgeClassHandler, addTagHandler, removeTagHandler, approveTagHandler, proposeTagHandler } from '../controllers/settingsController'

export const settingsRouter = Router()

const avatarUpload = multer({
  storage: multer.memoryStorage(),
  limits: {
    fileSize: 8 * 1024 * 1024,
  },
  fileFilter: (_req, file, cb) => {
    const validTypes = ['image/jpeg', 'image/png', 'image/webp', 'image/gif']
    if (validTypes.includes(file.mimetype)) {
      cb(null, true)
    } else {
      cb(new Error('Invalid file type. Only JPG, PNG, WebP, and GIF are allowed.'))
    }
  },
})

settingsRouter.get('/', getSettingsHandler)
settingsRouter.put('/nickname', updateNicknameHandler)
settingsRouter.put('/profile', updateProfileHandler)
settingsRouter.put('/ranking-location', updateRankingLocationHandler)
settingsRouter.put('/age-class', updateAgeClassHandler)
settingsRouter.post('/avatar', avatarUpload.single('avatar'), updateAvatarHandler)

// Tags (FEAT-8)
settingsRouter.post('/tags', addTagHandler)
settingsRouter.delete('/tags/:tag', removeTagHandler)
settingsRouter.post('/tags/:tag/approve', approveTagHandler)
settingsRouter.post('/tags/propose', proposeTagHandler)
