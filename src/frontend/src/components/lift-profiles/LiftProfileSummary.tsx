import { Stack, Text } from '@mantine/core'
import type { LiftProfile } from '@powerlifting/types'
import { describeLiftProfile } from '@/utils/liftProfile'

export function LiftProfileSummary({ profile, size = 'xs' }: { profile: LiftProfile; size?: 'xs' | 'sm' }) {
  const rows = describeLiftProfile(profile)
  if (!rows.length && !profile.notes) return <Text fz={size} c="dimmed">No technique options chosen yet.</Text>
  return (
    <Stack gap={2}>
      {rows.map((row) => (
        <Text key={row.label} fz={size} lh="lg">
          <Text span fz={size} c="dimmed">{row.label}: </Text>
          {row.value}
        </Text>
      ))}
      {profile.notes && <Text fz={size} c="dimmed" style={{ whiteSpace: 'pre-wrap' }}>{profile.notes}</Text>}
    </Stack>
  )
}
