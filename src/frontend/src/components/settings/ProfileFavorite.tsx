import { useEffect, useState } from 'react'
import { Button, Stack, Text } from '@mantine/core'
import { Star } from 'lucide-react'
import { useAuth } from '@/auth/AuthProvider'
import { listFavoritesApi, setFavoriteApi } from '@/api/relationships'

export default function ProfileFavorite({ athlete }: { athlete: string }) {
  const { user } = useAuth()
  const [favorite, setFavorite] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => {
    if (!user) return
    let current = true
    void listFavoritesApi().then(result => { if (current) setFavorite(result.favorites.some(item => item.athlete_mapped_pk === athlete)) }).catch(() => { if (current) setError('Could not load your favorites') })
    return () => { current = false }
  }, [athlete, user?.sub])
  if (!user) return null
  const toggle = async () => {
    setSaving(true)
    try { await setFavoriteApi(athlete, favorite ? 'remove' : 'add'); setFavorite(!favorite); setError('') }
    catch { setError('Favorite was not saved. Retry when connected.') }
    finally { setSaving(false) }
  }
  return <Stack gap={4}><Button variant="light" leftSection={<Star size={16} fill={favorite ? 'currentColor' : 'none'} />} aria-pressed={favorite} loading={saving} onClick={toggle}>{favorite ? 'Remove favorite' : 'Favorite privately'}</Button><Text size="xs" c={error ? 'red' : 'dimmed'}>{error || 'Favorites confer no access.'}</Text></Stack>
}
