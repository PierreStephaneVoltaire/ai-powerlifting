import { useEffect } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { useProgramStore } from '@/store/programStore'
import { AuthProvider, useAuth } from '@/auth/AuthProvider'
import AppShell from '@/components/layout/AppShell'
import Dashboard from '@/pages/Dashboard'
import CalendarPage from '@/pages/CalendarPage'
import DesignerPage from '@/pages/DesignerPage'
import DesignerLanding from '@/pages/DesignerLanding'
import DesignerPhases from '@/pages/DesignerPhases'
import ListPage from '@/pages/ListPage'
import SessionDetailPage from '@/pages/SessionDetailPage'
import AnalysisPage from '@/pages/AnalysisPage'
import GlossaryPage from '@/pages/GlossaryPage'
import ToolsPage from '@/pages/ToolsPage'
import SupplementsPage from '@/pages/SupplementsPage'
import BiometricsPage from '@/pages/BiometricsPage'
import CompetitionsPage from '@/pages/CompetitionsPage'
import GoalsPage from '@/pages/GoalsPage'
import FederationsPage from '@/pages/FederationsPage'
import BudgetPage from '@/pages/BudgetPage'
import VideosPage from '@/pages/VideosPage'
import AboutPage from '@/pages/AboutPage'
import ImportWizardPage from '@/pages/ImportWizardPage'
import TemplateLibraryPage from '@/pages/TemplateLibraryPage'
import TemplateDetailPage from '@/pages/TemplateDetailPage'
import TemplateCreatePage from '@/pages/TemplateCreatePage'
import TemplateEditPage from '@/pages/TemplateEditPage'
import TemplateImportPage from '@/pages/TemplateImportPage'
import RankingsPage from '@/pages/RankingsPage'
import NotesPage from '@/pages/NotesPage'
import ProfilesPage, { PublicProfilePage } from '@/pages/ProfilesPage'
import ProfilePage from '@/pages/ProfilePage'
import LogPage from '@/pages/LogPage'
import LoginPage from '@/pages/LoginPage'
import AuthCallbackPage from '@/pages/AuthCallbackPage'
import OnboardingPage from '@/pages/OnboardingPage'
import LiftProfilePage from '@/pages/LiftProfilePage'

// Tool Components
import PlateCalculator from '@/components/tools/PlateCalculator'
import DotsCalculator from '@/components/tools/DotsCalculator'
import WeightTracker from '@/components/tools/WeightTracker'
import PercentTable from '@/components/tools/PercentTable'
import UnitConverter from '@/components/tools/UnitConverter'
import AttemptSelector from '@/components/tools/AttemptSelector'

export default function App() {
  return (
    <AuthProvider>
      <AppContent />
    </AuthProvider>
  )
}

function AppContent() {
  const { loadProgram, reset } = useProgramStore()
  const { mapped_pk, loading } = useAuth()

  useEffect(() => {
    if (loading) return
    reset()
    loadProgram('current').catch(console.error)
  }, [loading, mapped_pk, loadProgram, reset])

  return (
    <AppShell>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/auth/callback" element={<AuthCallbackPage />} />
        <Route path="/onboarding" element={<OnboardingPage />} />
        <Route path="/" element={<Dashboard />} />
        <Route path="/lift-profiles/:lift" element={<LiftProfilePage />} />
        <Route path="/calendar" element={<Navigate to="/sessions" replace />} />
        <Route path="/sessions" element={<CalendarPage />} />
        <Route path="/designer" element={<DesignerLanding />} />
        <Route path="/designer/phases" element={<DesignerPhases />} />
        <Route path="/designer/sessions" element={<DesignerPage />} />
        <Route path="/designer/goals" element={<GoalsPage />} />
        <Route path="/designer/federations" element={<FederationsPage />} />
        <Route path="/budget" element={<BudgetPage />} />
        <Route path="/list" element={<ListPage />} />
        <Route path="/session/:date/:index?" element={<SessionDetailPage />} />
        <Route path="/list/:date/:index?" element={<SessionDetailPage />} />
        <Route path="/analysis" element={<AnalysisPage />} />
        <Route path="/rankings" element={<RankingsPage />} />
        <Route path="/log" element={<LogPage />} />
        <Route path="/notes" element={<NotesPage />} />
        <Route path="/supplements" element={<SupplementsPage />} />
        <Route path="/biometrics" element={<BiometricsPage />} />
        <Route path="/diet" element={<BiometricsPage />} />
        <Route path="/designer/competitions" element={<CompetitionsPage />} />
        <Route path="/designer/glossary" element={<GlossaryPage />} />
        <Route path="/maxes" element={<Navigate to="/analysis?type=maxes" replace />} />
        <Route path="/tools" element={<ToolsPage />} />
        <Route path="/tools/plate" element={<PlateCalculator />} />
        <Route path="/tools/dots" element={<DotsCalculator />} />
        <Route path="/tools/weight" element={<WeightTracker />} />
        <Route path="/tools/percent" element={<PercentTable />} />
        <Route path="/tools/converter" element={<UnitConverter />} />
        <Route path="/tools/attempts" element={<AttemptSelector />} />
        <Route path="/videos" element={<VideosPage />} />
        <Route path="/profile" element={<ProfilePage />} />
        <Route path="/profiles" element={<ProfilesPage />} />
        <Route path="/profiles/:nickname" element={<PublicProfilePage />} />
        <Route path="/designer/import" element={<ImportWizardPage />} />
        <Route path="/designer/templates" element={<TemplateLibraryPage />} />
        <Route path="/designer/templates/new" element={<TemplateCreatePage />} />
        <Route path="/designer/templates/import" element={<TemplateImportPage />} />
        <Route path="/designer/template" element={<TemplateDetailPage />} />
        <Route path="/designer/template/edit" element={<TemplateEditPage />} />
        <Route path="/designer/templates/:sk/edit" element={<TemplateEditPage />} />
        <Route path="/designer/templates/:sk" element={<TemplateDetailPage />} />
        <Route path="/about" element={<AboutPage />} />
      </Routes>
    </AppShell>
  )
}
