import { Navigate } from 'react-router-dom'

export default function ListPage() {
  return <Navigate to="/sessions?view=Compact" replace />
}
