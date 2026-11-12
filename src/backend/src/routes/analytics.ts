import { Router } from 'express'
import { invokeToolDirect } from '../utils/agent'
import { callOperation, readGeneration } from '../utils/operations'
import * as programController from '../controllers/programController'

export const analyticsRouter = Router()

analyticsRouter.post('/e1rm-multiplier/suggestions', async (req, res) => {
  try {
    const result = await invokeToolDirect('health_suggest_e1rm_multipliers', {})
    res.json({ data: result })
  } catch (error) {
    res.status(500).json({ error: String(error) })
  }
})

analyticsRouter.get('/generations/:generationId', async (req, res) => {
  try {
    res.json({ data: await readGeneration(req.params.generationId, req.mapped_pk!), error: null })
  } catch (err) {
    res.status(502).json({ data: null, error: String(err) })
  }
})

analyticsRouter.put('/blocks/:blockKey/start-maxes', async (req, res) => {
  try {
    const pk = req.mapped_pk!
    const blocks: Array<{ blockKey: string }> = await callOperation('analytics.blocks_list', { pk })
    const block = blocks.find((entry) => entry.blockKey === req.params.blockKey)
    if (!block) {
      return res.status(404).json({ data: null, error: `Block ${req.params.blockKey} not found` })
    }

    const parseKg = (value: unknown): number | null => {
      if (value === null || value === undefined || value === '') return null
      const numberValue = Number(value)
      if (!Number.isFinite(numberValue) || numberValue < 0) {
        throw new Error('Start maxes must be positive kg values or null')
      }
      return Math.round(numberValue * 10) / 10
    }

    const squat = parseKg(req.body?.squat_kg)
    const bench = parseKg(req.body?.bench_kg)
    const deadlift = parseKg(req.body?.deadlift_kg)
    const total = squat != null && bench != null && deadlift != null
      ? Math.round((squat + bench + deadlift) * 10) / 10
      : null
    const startMaxes = {
      squat_kg: squat,
      bench_kg: bench,
      deadlift_kg: deadlift,
      total_kg: total,
      source: 'manual' as const,
      updated_at: new Date().toISOString(),
    }

    const program = await programController.getProgram(pk, 'current')
    const blockId = block.blockKey === 'current' ? program.meta.current_block_id ?? 'current' : block.blockKey
    const records = program.meta.blocks ?? []
    if (!records.some((record) => String(record.id ?? record.block_id ?? '') === blockId)) {
      return res.status(404).json({ data: null, error: `Block ${req.params.blockKey} has no block record` })
    }
    const startMaxesKg = Object.fromEntries(Object.entries({ squat, bench, deadlift }).filter((entry): entry is [string, number] => entry[1] != null))
    await programController.updateMetaField(
      pk,
      'current',
      'blocks',
      records.map((record) => String(record.id ?? record.block_id ?? '') === blockId ? { ...record, start_maxes_kg: startMaxesKg } : record),
    )

    res.json({ data: startMaxes, error: null })
  } catch (err) {
    res.status(400).json({ data: null, error: `Block start max update error: ${err}` })
  }
})

analyticsRouter.get('/correlation', async (req, res) => {
  try {
    const data = await callOperation('analytics.correlation', {
      pk: req.mapped_pk,
      blockKey: (req.query.block as string) || 'current',
      refresh: req.query.refresh === 'true',
      cacheOnly: req.readOnly || req.query.cacheOnly === 'true',
    })
    res.json({ data, error: null })
  } catch (err) {
    res.status(502).json({ data: null, error: `Tool invocation error: ${err}` })
  }
})

analyticsRouter.get('/program-evaluation', async (req, res) => {
  try {
    const data = await callOperation('analytics.block_evaluation', {
      pk: req.mapped_pk,
      blockKey: (req.query.block as string) || 'current',
      refresh: req.query.refresh === 'true',
      cacheOnly: req.readOnly || req.query.cacheOnly === 'true',
    })
    res.json({ data, error: null })
  } catch (err) {
    res.status(502).json({ data: null, error: `Tool invocation error: ${err}` })
  }
})

analyticsRouter.post('/fatigue-profile/estimate', async (req, res) => {
  try {
    const exercise = req.body?.exercise ?? req.body
    const data = await invokeToolDirect('fatigue_profile_estimate', { exercise, pk: req.mapped_pk })
    res.json({ data, error: null })
  } catch (err) {
    res.status(502).json({ data: null, error: `Tool invocation error: ${err}` })
  }
})

analyticsRouter.post('/muscle-groups/estimate', async (req, res) => {
  try {
    const body = req.body ?? {}
    const exercise = body.exercise ?? body
    const lift_profiles = Array.isArray(body.lift_profiles) ? body.lift_profiles : undefined
    const data = await invokeToolDirect('muscle_group_estimate', {
      exercise,
      ...(lift_profiles ? { lift_profiles } : {}),
      pk: req.mapped_pk,
    })
    res.json({ data, error: null })
  } catch (err) {
    res.status(502).json({ data: null, error: `Tool invocation error: ${err}` })
  }
})

analyticsRouter.post('/glossary/text/generate', async (req, res) => {
  try {
    const body = req.body ?? {}
    const exercise = body.exercise ?? body
    if (!exercise?.name) {
      return res.status(400).json({ data: null, error: 'Exercise name is required' })
    }
    const lift_profiles = Array.isArray(body.lift_profiles) ? body.lift_profiles : undefined
    const data = await invokeToolDirect('glossary_generate_text', {
      exercise,
      ...(lift_profiles ? { lift_profiles } : {}),
      pk: req.mapped_pk,
    })
    res.json({ data, error: null })
  } catch (err) {
    res.status(502).json({ data: null, error: `Tool invocation error: ${err}` })
  }
})

analyticsRouter.post('/lift-profile/estimate-stimulus', async (req, res) => {
  try {
    const profile = req.body?.profile ?? req.body
    const data = await invokeToolDirect('lift_profile_estimate_stimulus', { profile, pk: req.mapped_pk })
    res.json({ data, error: null })
  } catch (err) {
    res.status(502).json({ data: null, error: `Tool invocation error: ${err}` })
  }
})

analyticsRouter.post('/lift-profile/suggest', async (req, res) => {
  try {
    const { lift, description, profile } = req.body ?? {}
    const data = await invokeToolDirect('lift_profile_suggest', { lift, description, ...(profile ? { profile } : {}), pk: req.mapped_pk })
    res.json({ data, error: null })
  } catch (err) {
    res.status(502).json({ data: null, error: `Tool invocation error: ${err}` })
  }
})
