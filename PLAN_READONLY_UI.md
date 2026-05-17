# Powerlifting Frontend Read-Only UI Plan

## Goal
When the user is not authenticated (no Discord token or invalid), ALL interactive controls across the entire powerlifting app must be disabled. The user should be able to see the contents but not edit them. This is purely a frontend change.

## Current State Analysis

### Already Working (readOnly correctly applied) ✓
- **ReadOnlyBanner** - Shown in AppShell, visible on all pages ✓
- **Dashboard** - Edit buttons for maxes, weight, phases, anthropometrics, lift profiles all have `disabled={readOnly}` ✓
- **SessionDrawer** - ALL interactive controls (inputs, buttons, sliders, drag handles) have `disabled={readOnly}` ✓
- **DesignerPage** - Add Session, Copy Previous/Next, session editor modal buttons have `disabled={readOnly}` ✓
- **NotesPage** - Save button has `disabled={readOnly}` ✓
- **TopBar** - Fork, Archive, Convert to Template have `disabled={readOnly}` ✓
- **TemplateCreatePage** - All inputs and Create button have `disabled={readOnly}` ✓

### Pages NOW COMPLETED ✓

#### 1. SupplementsPage (`pages/SupplementsPage.tsx`) ✅ DONE
- Added `useAuth` import and `readOnly` destructuring
- `disabled={readOnly}` added to: Save button, Add Phase button, phase name TextInput, edit trigger, Start/End Week Selects, Phase Notes Textarea, Add Item button, all item TextInputs/Textareas, remove item ActionIcons, Add Field button, protocol key TextInputs, remove protocol key ActionIcons, Delete Phase button
- Block Select left enabled (navigation/filtering)

#### 2. FederationsPage (`pages/FederationsPage.tsx`) ✅ DONE
- `disabled={readOnly}` added to ALL 25 controls: Save, Add Federation, Add Standard buttons, all Federation form inputs (name, abbreviation, region, status, notes, archive/restore), all Standard form inputs (federation, season year, sex, status, equipment, event, age class, division, weight class, required total, qualifying dates, competition name, source label/url, archive/restore)

#### 3. GlossaryPage (`pages/GlossaryPage.tsx`) ✅ DONE
- `disabled={readOnly}` or `|| readOnly` added to: all 3 bulk estimate buttons, Add Exercise button, modal form inputs (name, category, equipment), FatigueSlider (added disabled prop), AI Estimate buttons, e1RM value input, muscle toggle buttons (primary/secondary/tertiary), AI Generate button, text Textareas (description/how-to/why-do-it), YouTube URL, Create/Update Exercise button, exercise action buttons (Edit, Delete, Archive/Unarchive)

#### 4. CompetitionsPage (`pages/CompetitionsPage.tsx`) ✅ DONE
- `disabled={readOnly}` added to 34+ controls: Save, Add Competition, all competition form inputs (name, date, federation, status, host federation, counts toward, weight class, body weight, location, hotel checkbox, targets/results, notes), Edit Post-Meet Report, Mark as Completed, Delete, and all complete modal controls

#### 5. GoalsPage (`pages/GoalsPage.tsx`) ✅ DONE
- `disabled={readOnly}` added to 20 controls: Save, Add Goal, Delete, all form inputs (title, goal type, priority, strategy, target competitions, target date, primary federation, qualification standards, target total/DOTS/IPF GL/weight class, acceptable weight classes, risk tolerance, max bodyweight loss %, max water cut %, notes)

#### 6. BiometricsPage (`pages/BiometricsPage.tsx`) ✅ DONE
- `disabled={readOnly}` added to 11 additional controls (Add Entry already had it): Save, Delete ActionIcon, DatePickerInput, calories/protein/carbs/fat/sleep TextInputs, water intake TextInput, water unit Select, nutrition consistency SegmentedControl, notes Textarea

#### 7. DesignerPhases (`pages/DesignerPhases.tsx`) ✅ DONE
- `disabled={readOnly}` added to 12 controls: Add Phase button, Edit ActionIcon, Delete ActionIcon, and modal controls (name, start/end week, intent, RPE min/max, days/wk, notes, Save/Update Phase button)

#### 8. LiftProfilePage (`pages/LiftProfilePage.tsx`) ✅ DONE
- `disabled={readOnly}` added to 11 controls: Review, Rewrite, Estimate Stimulus (`disabled={!canEstimate || readOnly}`), Save Profile, Apply suggestion, Style & Setup/Sticking Points Textareas, Primary Muscle TextInput, Reset multiplier ActionIcon, e1RM Multiplier TextInput, Volume Tolerance SegmentedControl, Stimulus Coefficient TextInput

#### 9. TemplateEditPage (`pages/TemplateEditPage.tsx`) ✅ DONE
- Save button now has `disabled={saving || !template || readOnly}`
- `disabled={readOnly}` passed to TemplateMetaEditor, TemplatePhasesEditor, TemplateSessionsEditor

#### 10. TemplateLibraryPage (`pages/TemplateLibraryPage.tsx`) ✅ DONE
- Added `useAuth` import and `readOnly`
- `disabled={readOnly}` on Create Template and Import Template buttons

#### 11. TemplateDetailPage (`pages/TemplateDetailPage.tsx`) ✅ DONE
- Added `useAuth` import and `readOnly`
- Passed `readOnly` to TemplateDetail component
- TemplateDetail: Edit and Apply Template buttons have `|| readOnly` on disabled prop

#### 12. ImportWizardPage (`pages/ImportWizardPage.tsx`) ✅ DONE
- Added `useAuth` import and `readOnly`
- Passed `readOnly` to ImportWizard component
- ImportWizard passes `readOnly` to Step1_Upload and Step6_Apply
- Step1_Upload: dropzone disabled when readOnly, cursor not-allowed
- Step6_Apply: Apply Import button disabled when readOnly

### NotesPage Textarea Fix ✅ DONE
- Added `disabled={readOnly}` to the Textarea in NotesPage

### Sub-component Changes ✅ DONE
- `FatigueSlider` - Added `disabled` prop, passed to `<Slider>`
- `TemplateMetaEditor` - Added `disabled` prop, passed to all TextInputs/Textareas
- `TemplatePhasesEditor` - Added `disabled` prop, passed to all controls
- `TemplateSessionsEditor` - Added `disabled` prop, passed to all controls
- `TemplateSessionModal` - Added `disabled` prop, passed to all controls
- `TemplateDetail` - Added `readOnly` prop, used on Edit/Apply buttons
- `ImportWizard` - Added `readOnly` prop, passed to steps
- `Step1_Upload` - Added `readOnly` prop, disabled dropzone
- `Step6_Apply` - Added `readOnly` prop, disabled Apply button

## Implementation Plan

### Phase 1: Add readOnly to all page components ✅ DONE

For each page listed above:
1. Import `useAuth` if not already imported
2. Destructure `readOnly` from `useAuth()`
3. Add `disabled={readOnly}` to ALL interactive controls:
   - `<Button>` elements that mutate data (Save, Add, Delete, Apply, Upload, etc.)
   - `<TextInput>`, `<Textarea>`, `<Select>`, `<MultiSelect>`, `<SegmentedControl>`, `<Slider>` that edit data
   - `<ActionIcon>` that trigger mutations (Edit, Delete, Remove, etc.)
   - `<Checkbox>` that toggle state
   - `<DatePickerInput>` that change dates
   - `<Autocomplete>` for exercise search in edit mode
   - Drag handles (GripVertical) should not be draggable
   - Note: Navigation buttons (Prev Week, Next Week, Cancel, Back) should NOT be disabled

### Phase 2: Fix NotesPage Textarea ✅ DONE
- Add `disabled={readOnly}` to the Textarea in NotesPage

### Phase 3: Expand test script ✅ DONE

Update `scripts/test_powerlifting_readonly_ui_live.mjs` to add tests for:

#### Additional read-only tests: ✅ DONE
- **Supplements page**: Verify Add Phase button is disabled
- **Competitions page**: Verify Add Competition button is disabled
- **Goals page**: Verify Add Goal button is disabled
- **Biometrics/Diet page**: Verify Add Entry button is disabled
- **Glossary page**: Verify Add Exercise, Estimate Fatigue buttons are disabled
- **Federations page**: Verify Add Federation, Add Standard buttons are disabled
- **Designer Phases page**: Verify Add Phase button is disabled
- **Lift Profile page**: Verify Save Profile button is disabled
- **Template Library page**: Verify Create Template, Import Template buttons are disabled
- **Import Wizard page**: Verify file input is disabled
- **Notes page**: Verify Textarea is disabled (in addition to Save button)

#### Additional authenticated tests: ✅ DONE
- **Supplements page**: Verify Add Phase button is enabled
- **Competitions page**: Verify Add Competition button is enabled
- **Goals page**: Verify Add Goal button is enabled

### Phase 4: Build, Deploy, Test
1. Build frontend: `cd utils/powerlifting-app && npm run build --workspace=frontend` ✅ DONE (build passes)
2. Copy operator data to test: `python scripts/copy_operator_health_to_test.py --replace`
3. Build and deploy test images: `BUILD_ONLY=frontend scripts/build-test-images.sh --only frontend`
4. Port-forward and run live test: `node scripts/test_powerlifting_readonly_ui_live.mjs`
5. Verify no regressions with existing test: `node scripts/test_powerlifting_session_save_ui_live.mjs`

## File Change Summary

### Files to modify:
1. `utils/powerlifting-app/frontend/src/pages/SupplementsPage.tsx` - ✅ DONE - Add useAuth + disabled to ALL controls
2. `utils/powerlifting-app/frontend/src/pages/FederationsPage.tsx` - ✅ DONE - Add disabled to ALL controls
3. `utils/powerlifting-app/frontend/src/pages/GlossaryPage.tsx` - ✅ DONE - Add disabled to edit/save/delete controls + FatigueSlider disabled prop
4. `utils/powerlifting-app/frontend/src/pages/CompetitionsPage.tsx` - ✅ DONE - Add disabled to ALL controls
5. `utils/powerlifting-app/frontend/src/pages/GoalsPage.tsx` - ✅ DONE - Add disabled to ALL controls
6. `utils/powerlifting-app/frontend/src/pages/BiometricsPage.tsx` - ✅ DONE - Add disabled to remaining controls
7. `utils/powerlifting-app/frontend/src/pages/DesignerPhases.tsx` - ✅ DONE - Add disabled to controls
8. `utils/powerlifting-app/frontend/src/pages/LiftProfilePage.tsx` - ✅ DONE - Add disabled to remaining controls
9. `utils/powerlifting-app/frontend/src/pages/NotesPage.tsx` - ✅ DONE - Add disabled to Textarea
10. `utils/powerlifting-app/frontend/src/pages/TemplateEditPage.tsx` - ✅ DONE - Add disabled to form controls + pass disabled to sub-components
11. `utils/powerlifting-app/frontend/src/pages/TemplateLibraryPage.tsx` - ✅ DONE - Add useAuth + disabled to buttons
12. `utils/powerlifting-app/frontend/src/pages/TemplateDetailPage.tsx` - ✅ DONE - Add useAuth + pass readOnly to TemplateDetail
13. `utils/powerlifting-app/frontend/src/pages/ImportWizardPage.tsx` - ✅ DONE - Add useAuth + pass readOnly to ImportWizard

### Sub-components also modified:
14. `utils/powerlifting-app/frontend/src/components/templates/TemplateMetaEditor.tsx` - ✅ DONE - Add disabled prop
15. `utils/powerlifting-app/frontend/src/components/templates/TemplatePhasesEditor.tsx` - ✅ DONE - Add disabled prop
16. `utils/powerlifting-app/frontend/src/components/templates/TemplateSessionsEditor.tsx` - ✅ DONE - Add disabled prop
17. `utils/powerlifting-app/frontend/src/components/templates/TemplateSessionModal.tsx` - ✅ DONE - Add disabled prop
18. `utils/powerlifting-app/frontend/src/components/templates/TemplateDetail.tsx` - ✅ DONE - Add readOnly prop
19. `utils/powerlifting-app/frontend/src/components/import/ImportWizard.tsx` - ✅ DONE - Add readOnly prop
20. `utils/powerlifting-app/frontend/src/components/import/Step1_Upload.tsx` - ✅ DONE - Add readOnly prop + disable dropzone
21. `utils/powerlifting-app/frontend/src/components/import/Step6_Apply.tsx` - ✅ DONE - Add readOnly prop

### Test script updated:
22. `scripts/test_powerlifting_readonly_ui_live.mjs` - ✅ DONE - Expanded test coverage

## Key Design Decisions

1. **Which controls to disable**: ANY control that triggers a data mutation (write operation) should be disabled. Navigation, viewing, sorting, and filtering controls should remain enabled.
2. **Textareas/TextInputs**: Even though the backend has `requireWriteAuth` middleware, we should disable the inputs in the frontend too. This gives a clear visual signal and prevents wasted user effort typing data that cant be saved.
3. **Mantine disabled prop**: All Mantine form controls (`<TextInput>`, `<Textarea>`, `<Select>`, `<Button>`, `<ActionIcon>`, etc.) support `disabled` prop directly.
4. **Consistent approach**: Use `disabled={readOnly}` everywhere. No conditional rendering or hiding of buttons - just disable them.
5. **ReadOnlyBanner**: Already rendered in AppShell so visible on all pages. No changes needed there.
