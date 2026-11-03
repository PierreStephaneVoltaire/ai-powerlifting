import { useState, useRef } from 'react'
import { Paper, ActionIcon, Center, Box } from '@mantine/core'
import { Play, Pause, Maximize, Loader2 } from 'lucide-react'

interface VideoPlayerProps {
  src: string
  thumbnailUrl?: string
  className?: string
}

const PLAYBACK_SPEEDS = [0.25, 0.5, 0.75, 1, 1.25, 1.5, 2]

export default function VideoPlayer({
  src,
  thumbnailUrl,
  className,
}: VideoPlayerProps) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const [isPlaying, setIsPlaying] = useState(false)
  const [playbackSpeed, setPlaybackSpeed] = useState(1)
  const [isLoading, setIsLoading] = useState(true)
  const [showControls, setShowControls] = useState(true)

  function togglePlay() {
    const video = videoRef.current
    if (!video) return

    if (isPlaying) {
      video.pause()
    } else {
      video.play()
    }
    setIsPlaying(!isPlaying)
  }

  function handleSpeedChange() {
    const video = videoRef.current
    if (!video) return

    const currentIndex = PLAYBACK_SPEEDS.indexOf(playbackSpeed)
    const nextIndex = (currentIndex + 1) % PLAYBACK_SPEEDS.length
    const newSpeed = PLAYBACK_SPEEDS[nextIndex]

    video.playbackRate = newSpeed
    setPlaybackSpeed(newSpeed)
  }

  function handleFullscreen() {
    const video = videoRef.current
    if (!video) return

    if (document.fullscreenElement) {
      document.exitFullscreen()
    } else {
      video.requestFullscreen()
    }
  }

  function handleLoadedData() {
    setIsLoading(false)
  }

  function handleWaiting() {
    setIsLoading(true)
  }

  function handleCanPlay() {
    setIsLoading(false)
  }

  return (
    <Paper
      bg="black"
      radius="md"
      style={{ position: 'relative', overflow: 'hidden' }}
      className={className}
      onMouseEnter={() => setShowControls(true)}
      onMouseLeave={() => setShowControls(true)}
    >
      {/* Loading Overlay */}
      {isLoading && (
        <Center
          pos="absolute"
          inset={0}
          bg="rgba(0, 0, 0, 0.5)"
          style={{ zIndex: 10 }}
        >
          <Loader2
            size={32}
            color="white"
            style={{ animation: 'spin 1s linear infinite' }}
          />
        </Center>
      )}

      {/* Video Element */}
      <Box
        component="video"
        ref={videoRef}
        src={src}
        poster={thumbnailUrl}
        playsInline
        style={{ width: '100%', aspectRatio: '16 / 9', display: 'block' }}
        onLoadedData={handleLoadedData}
        onWaiting={handleWaiting}
        onCanPlay={handleCanPlay}
        onPlay={() => setIsPlaying(true)}
        onPause={() => setIsPlaying(false)}
        onClick={togglePlay}
      />

      {/* Controls Overlay */}
      <Box
        pos="absolute"
        bottom={0}
        left={0}
        right={0}
        p={12}
        style={{
          background: 'linear-gradient(to top, rgba(0,0,0,0.8), transparent)',
          transition: 'opacity 200ms',
          opacity: showControls ? 1 : 0,
        }}
      >
        <Box style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
          {/* Play/Pause */}
          <ActionIcon
            variant="default"
            size="lg"
            radius="xl"
            onClick={togglePlay}
            style={{ background: 'rgba(255,255,255,0.2)', border: 'none' }}
          >
            {isPlaying ? (
              <Pause size={20} color="white" />
            ) : (
              <Play size={20} color="white" />
            )}
          </ActionIcon>

          {/* Playback Speed */}
          <ActionIcon
            variant="default"
            size="lg"
            radius="md"
            onClick={handleSpeedChange}
            style={{ background: 'rgba(255,255,255,0.2)', border: 'none' }}
          >
            <Box
              component="span"
              style={{
                color: 'white',
                fontSize: 12,
                fontFamily: 'monospace',
                fontWeight: 700,
              }}
            >
              {playbackSpeed}x
            </Box>
          </ActionIcon>

          {/* Fullscreen */}
          <ActionIcon
            variant="default"
            size="lg"
            radius="xl"
            onClick={handleFullscreen}
            style={{ background: 'rgba(255,255,255,0.2)', border: 'none' }}
          >
            <Maximize size={20} color="white" />
          </ActionIcon>
        </Box>
      </Box>
    </Paper>
  )
}
