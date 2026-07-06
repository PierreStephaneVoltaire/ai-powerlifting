import { Router } from 'express'
import { invokeLambda } from '../utils/lambda'
import { AppError } from '../middleware/errorHandler'

export const statsRouter = Router()

// All three stats calls go through the MCP direct-tool-invoke path:
//   POST /v1/chat/completions  X-Direct-Tool-Invoke: true
// No custom FastAPI routes — the agent API is purely OpenAI-compatible + webhooks.

statsRouter.get('/categories', async (req, res, next) => {
  try {
    const data = await invokeLambda('pod_analysis', { function: 'powerlifting_filter_categories', })
    // Return 503 while dataset is still loading
    if (typeof data === 'string' && data.includes('Dataset not ready')) {
      return res.status(503).set('Retry-After', '30').json({ error: 'DATASET_NOT_FOUND', message: data })
    }
    if (typeof data === 'string' && data.includes('Dataset missing')) {
      return res.status(404).json({ error: 'DATASET_NOT_FOUND', message: data })
    }
    res.json(data)
  } catch (err: any) {
    next(new AppError(`Categories failed: ${err.message}`, 502))
  }
})

statsRouter.post('/analyze', async (req, res, next) => {
  try {
    const {
      squat, bench, deadlift, bodyweight,
      sex_code, federation, country, region,
      equipment, sex, age_class, year, event_type, min_dots,
    } = req.body
    const data = await invokeLambda('pod_analysis', { function: 'analyze_powerlifting_stats', 
      squat_kg: squat,
      bench_kg: bench,
      deadlift_kg: deadlift,
      bodyweight_kg: bodyweight,
      sex_code,
      federation,
      country,
      region,
      equipment,
      sex,
      age_class,
      year,
      event_type,
      min_dots,
    })
    if (typeof data === 'string' && data.includes('Dataset not ready')) {
      return res.status(503).set('Retry-After', '30').json({ detail: data })
    }
    if (typeof data === 'string' && data.includes('Dataset missing')) {
      return res.status(404).json({ detail: data })
    }
    res.json(data)
  } catch (err: any) {
    next(new AppError(`Analyze failed: ${err.message}`, 502))
  }
})

statsRouter.get('/ranking_percentile', async (req, res, next) => {
  try {
    const toNum = (v: unknown) => v !== undefined && v !== '' ? Number(v) : undefined
    const toStr = (v: unknown) => v !== undefined && v !== '' ? String(v) : undefined

    const data = await invokeLambda('pod_analysis', { function: 'powerlifting_ranking_percentile', 
      squat_kg:     toNum(req.query.squat_kg),
      bench_kg:     toNum(req.query.bench_kg),
      deadlift_kg:  toNum(req.query.deadlift_kg),
      bodyweight_kg: toNum(req.query.bodyweight_kg),
      sex_code:     toStr(req.query.sex_code),
      country:      toStr(req.query.country),
      region:       toStr(req.query.region),
      age_class:    toStr(req.query.age_class),
      equipment:    toStr(req.query.equipment),
    })
    if (typeof data === 'string' && data.includes('Dataset not ready')) {
      return res.status(503).set('Retry-After', '30').json({ detail: data })
    }
    if (typeof data === 'string' && data.includes('Dataset missing')) {
      return res.status(404).json({ detail: data })
    }
    res.json(data)
  } catch (err: any) {
    next(new AppError(`Ranking percentile failed: ${err.message}`, 502))
  }
})
