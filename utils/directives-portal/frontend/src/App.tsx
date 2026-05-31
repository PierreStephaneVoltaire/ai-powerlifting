import { Routes, Route } from 'react-router-dom'
import { AuthProvider } from './auth/AuthProvider'
import { LoginPage } from './pages/LoginPage'
import { DirectivesPage } from './pages/DirectivesPage'
import { AuthCallbackPage } from './pages/AuthCallbackPage'

function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/auth/callback" element={<AuthCallbackPage />} />
        <Route path="/*" element={<DirectivesPage />} />
      </Routes>
    </AuthProvider>
  )
}

export default App