The scope is massive. Here's what the scope of this refactor, I need to get your sign-off on the approach before I start changing ~30+ files. Let me lay out the plan and ask for confirmation.
The scope is massive. Here's what I'm looking at:
Files that import db/dynamo.ts (direct DynamoDB):

- services/userSettings.ts — user profile/mapped I'm looking at:
  Files that import db/dynamo.ts (direct DynamoDB):
- services/userSettings.ts — user profile/mapped_pk lookup (this is auth-adjacent)
- services/sessionStore.ts — session CRUD
- services/masterCopy.ts — master data copies
- services/analysisCache.ts — analysis cache
- services/blockAnalytics.ts — block analytics
- services/blockAnalysisExport.ts_pk lookup (this is auth-adjacent)
- services/sessionStore.ts — session CRUD
- services/masterCopy.ts — master data copies
- services/analysisCache.ts — analysis cache
- services/blockAnalytics.ts — block analytics
- services/blockAnalysisExport.ts — exports
- controllers/programController.ts (programs)
- controllers/sessionController.ts (sessions)
- controllers/exerciseController.ts (glossary)
- controllers/maxController.ts (maxes)
- controllers/weightController.ts (weight log)
- controllers/supplementController.ts, dietNotesController.ts, `block — exports
- controllers/programController.ts (programs)
- controllers/sessionController.ts (sessions)
- controllers/exerciseController.ts (glossary)
- controllers/maxController.ts (maxes)
- controllers/weightController.ts (weight log)
- controllers/supplementController.ts, dietNotesController.ts, blockNotesController.ts
- controllers/competitionController.ts, federationsController.ts, goalsController.ts, budgetController.ts, videoController.ts, importController.ts, templateController.ts
  Routes: ~20 files, mostly thin (just delegate to controllers), but a few doNotesController.ts`
- controllers/competitionController.ts, federationsController.ts, goalsController.ts, budgetController.ts, videoController.ts, importController.ts, templateController.ts
  Routes: ~20 files, mostly thin (just delegate to controllers), but a few do their own work (e.g., competitions.ts already mixes direct controller + invokeLambda; analytics.ts, stats.ts already mostly use F their own work (e.g., competitions.ts already mixes direct controller + invokeLambda; analytics.ts, stats.ts already mostly use Fission).
  Existing Fission tools (from lambda/ + k8s-fission-powerlifting.tf): health*get_program, health_get_session, health_get_sessions_range, `health_getission).
  Existing Fission tools (from lambda/ + k8s-fission-powerlifting.tf): health_get_program, health_get_session, health_get_sessions_range, health_get_current_maxes, health_get_goals, health_get_meta, health_get_phases, health_update_meta, health_update_session, template_list, template_get, glossary_list_terms, federation_list, program_list, session_list, import_list, get_current_maxes, health_get_goals, health_get_meta, health_get_phases, health_update_meta, health_update_session, template_list, template_get, glossary_list_terms, federation_list, program_list, session_list, import_list, get_analysis_markdown, health_complete_competition, health_snapshot_competition_projection, analyze*_, glossary\__, budget**, etc. — ~95 tools total.
  *Gaps I_analysis_markdown, health_complete_competition, health_snapshot_competition_projection, analyze*, glossary*, budget*`, etc. — ~95 tools total.
  Gaps I can see:
- No Fission tool for user settings/mapped_pk lookup — userSettings.ts has no Fission equivalent. The auth middleware depends on this can see\*\*:
- No Fission tool for user settings/mapped_pk lookup — userSettings.ts has no Fission equivalent. The auth middleware depends on this to resolve req.mapped_pk.
- No Fission tool for the master/user competition+ federation tables — masterCopy.ts scans master tables and batch-writes user copies.
- \*\*No to resolve req.mapped_pk.
- No Fission tool for the master/user competition+ federation tables — masterCopy.ts scans master tables and batch-writes user copies.
- No Fission tool for the per-block user federation library — federationsController writes a per-user library to its own table.
- No Fission tool for the budget store Fission tool for the per-block user federation library — federationsController writes a per-user library to its own table.
- No Fission tool for the budget store, video store, diet notes, block notes, weight log, supplements, maxes — all per-user per-feature tables.
- No Fission tool for the analysis cache table — analysisCache.ts reads/writes `, video store, diet notes, block notes, weight log, supplements, maxes\*\* — all per-user per-feature tables.
- No Fission tool for the analysis cache table — analysisCache.ts reads/writes if-powerlifting-analysis-cache.
