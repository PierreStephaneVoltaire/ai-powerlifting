import { Card, SimpleGrid, Stack, Text, Title } from '@mantine/core'
import type { LiftProfile } from '@powerlifting/types'
import { getMediaUrl } from '@/utils/media'

export default function LiftProfileContext({ profiles, athlete }: { profiles?: LiftProfile[]; athlete: string }) {
  if (!profiles?.length) return null
  return <Stack>
    <Title order={3}>Lift profiles</Title>
    {profiles.map(profile => <Card key={profile.lift} withBorder>
      <Stack gap="xs">
        <Text tt="capitalize" fw={600}>{profile.lift}</Text>
        {profile.style_notes && <Text>{profile.style_notes}</Text>}
        {profile.sticking_points && <Text>{profile.sticking_points}</Text>}
        {profile.failure_nodes?.length ? <ul>{profile.failure_nodes.map(node => <li key={node}>{node}</li>)}</ul> : <Text size="sm" c="dimmed">No failure nodes recorded.</Text>}
        <SimpleGrid cols={{ base: 1, sm: 3 }}>{Object.entries(profile.form_videos || {}).map(([angle, video]) => <Stack key={angle} gap={4}>
          <Text tt="capitalize">{angle}</Text>
          {video?.video_id && video.s3_key ? <video aria-label={`${profile.lift} ${angle} form recording`} controls playsInline preload="none" src={getMediaUrl(video.s3_key, athlete)} poster={getMediaUrl(video.thumbnail_s3_key, athlete)} style={{ width: '100%' }} /> : <Text size="sm">Recording is not ready.</Text>}
          {video?.pending_media_id && <Text size="xs">Replacement: {video.processing_status || 'processing'}</Text>}
        </Stack>)}</SimpleGrid>
      </Stack>
    </Card>)}
  </Stack>
}
