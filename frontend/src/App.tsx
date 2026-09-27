import { Routes, Route, Navigate, useLocation, Link } from 'react-router-dom'
import { Alert, Button, Center, Loader, Select, Stack, Title } from '@mantine/core'
import { useEffect, useState } from 'react'
import { routePermission } from '@/auth/routes'
import { RelationshipRoster } from '@/components/settings/RelationshipRoster'
import { RelationshipInbox } from '@/components/settings/RelationshipInbox'
import { useProgramStore } from '@/store/programStore'
import { AuthProvider, useAuth, type ActiveRole } from '@/auth/AuthProvider'
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
import AthleteDetailsPage from '@/pages/AthleteDetailsPage'
import SettingsPage from '@/pages/SettingsPage'
import AboutPage from '@/pages/AboutPage'
import LandingPage, { PublicLayout } from '@/pages/LandingPage'
import ImportWizardPage from '@/pages/ImportWizardPage'
import TemplateLibraryPage from '@/pages/TemplateLibraryPage'
import TemplateDetailPage from '@/pages/TemplateDetailPage'
import TemplateCreatePage from '@/pages/TemplateCreatePage'
import TemplateEditPage from '@/pages/TemplateEditPage'
import TemplateImportPage from '@/pages/TemplateImportPage'
import RankingsPage from '@/pages/RankingsPage'
import NotesPage from '@/pages/NotesPage'
import AuthoredNotes from '@/components/notes/AuthoredNotes'
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
  const { user, person_pk, mapped_pk, loading, permissions } = useAuth()
  const location = useLocation()
  const permission = routePermission(location.pathname)

  useEffect(() => {
    if (loading) return
    reset()
    if (permissions.includes('program:read')) loadProgram('current').catch(console.error)
  }, [loading, person_pk, mapped_pk, permissions, loadProgram, reset])

  if (loading) return <Center mih="100vh"><Loader aria-label="Loading your access" /></Center>

  const content = permission && !permissions.includes(permission) ? <Alert title="This view needs access" color="orange"><Stack><span>Choose an Athlete you can access, or complete your Athlete basics before personal training.</span><Button component={Link} to="/onboarding">Edit onboarding</Button><Button component={Link} to="/profiles" variant="default">Search profiles</Button></Stack></Alert> : <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/auth/callback" element={<AuthCallbackPage />} />
        <Route path="/onboarding" element={<OnboardingPage />} />
        <Route path="/" element={<Landing />} />
        <Route path="/athlete" element={<AthleteDetailsPage />} />
        <Route path="/roster" element={<RosterPage />} />
        <Route path="/inbox" element={<RelationshipInbox />} />
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
        <Route path="/my-notes" element={<AuthoredNotes />} />
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
        <Route path="/settings" element={<SettingsPage />} />
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
  const publicRoute = !user && (/^\/(login|about|profiles)(\/|$)/.test(location.pathname) || location.pathname === '/')
  return publicRoute ? <PublicLayout>{content}</PublicLayout> : <AppShell key={`${person_pk}:${mapped_pk}`}>{content}</AppShell>
}

function RosterPage() {
  const { user } = useAuth()
  return <Stack><Title order={2}>{user?.active_role === 'handler' ? 'Competition-day roster' : 'Athlete roster'}</Title><RelationshipRoster /></Stack>
}

function Landing() {
  const { user, person_pk, is_onboarded, selectRole } = useAuth()
  const viewKey = person_pk ? `nolift-role-view:${person_pk}` : ''
  const [view, setView] = useState<string | null>(null)
  const [choice, setChoice] = useState<ActiveRole | null>(user?.active_role || null)
  useEffect(() => { setView(viewKey ? sessionStorage.getItem(viewKey) : null) }, [viewKey])
  useEffect(() => { setChoice(user?.active_role || null) }, [user?.active_role])
  if (!user) return <LandingPage />
  if (!is_onboarded) return <Navigate to="/onboarding" replace />
  if (user.roles.length > 1 && !view) return <Stack maw={480} mx="auto"><Title order={2}>Choose your NoLift view</Title><Select label="View" data={user.roles.map(role => ({ value: role, label: role[0].toUpperCase() + role.slice(1) }))} value={choice} onChange={value => setChoice(value as ActiveRole)} allowDeselect={false} /><Button onClick={() => { if (choice) { selectRole(choice); if (viewKey) sessionStorage.setItem(viewKey, choice); setView(choice) } }} disabled={!choice}>Continue</Button></Stack>
  if (user.active_role === 'coach' || user.active_role === 'handler') return <RosterPage />
  return <Dashboard />
}
