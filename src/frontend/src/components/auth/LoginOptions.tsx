import { Button } from '@mantine/core'
import { useAuth } from '@/auth/AuthProvider'

interface LoginOptionsProps {
  compact?: boolean
}

export default function LoginOptions({ compact = false }: LoginOptionsProps) {
  const { signIn } = useAuth()
  return (
    <Button size={compact ? 'md' : 'lg'} onClick={signIn} fullWidth style={{ minHeight: 44 }} data-testid="signin-authentik">
      Log in
    </Button>
  )
}
