import { useMemo } from 'react'
import { Paper, Title, Group, Badge, Text, Stack, Loader, Center } from '@mantine/core'
import { useProgramStore } from '@/store/programStore'
import { parseISO, differenceInDays, format } from 'date-fns'
import { phaseColor } from '@/utils/phases'

export default function TimelinePage() {
  const { program, isLoading } = useProgramStore()

  const timelineData = useMemo(() => {
    if (!program) return null

    const startDate = parseISO(program.meta.program_start)
    const compDate = parseISO(program.meta.comp_date)
    const totalDays = differenceInDays(compDate, startDate)
    const today = new Date()
    const todayOffset = differenceInDays(today, startDate)

    return {
      startDate,
      compDate,
      totalDays,
      todayOffset,
      phases: program.phases.map((phase) => ({
        ...phase,
        startOffset: (phase.start_week - 1) * 7,
        endOffset: phase.end_week * 7,
      })),
      sessions: program.sessions.map((s) => ({
        ...s,
        offset: differenceInDays(parseISO(s.date), startDate),
      })),
      competitions: program.competitions.filter((c) => c.status !== 'skipped'),
    }
  }, [program])

  if (isLoading || !program || !timelineData) {
    return (
      <Center mih="50vh">
        <Loader />
      </Center>
    )
  }

  const width = Math.max(800, timelineData.totalDays * 3)

  return (
    <Stack gap="xs" style={{ height: 'calc(100vh - 180px)' }}>
      <Group justify="space-between" wrap="wrap">
        <Title order={2}>Program Timeline</Title>

        {/* Phase Legend */}
        <Group gap="sm" wrap="wrap">
          {program.phases.map((phase, idx) => (
            <Badge
              key={idx}
              variant="dot"
              color={phaseColor(phase, program.phases)}
              size="sm"
            >
              {phase.name} (W{phase.start_week}-W{phase.end_week})
            </Badge>
          ))}
        </Group>
      </Group>

      {/* Timeline SVG */}
      <Paper withBorder style={{ flex: 1, overflow: 'auto', minHeight: 0 }}>
        <svg viewBox={`0 0 ${width} 300`} preserveAspectRatio="xMidYMid meet" style={{ width: '100%', height: '100%', minHeight: '180px' }}>
          {/* Phase bands */}
          {timelineData.phases.map((phase, idx) => {
            const x1 = (phase.startOffset / timelineData.totalDays) * width
            const x2 = (phase.endOffset / timelineData.totalDays) * width
            const color = phaseColor(phase, program.phases)

            return (
              <rect
                key={idx}
                x={x1}
                y={0}
                width={x2 - x1}
                height={40}
                fill={color}
                opacity={0.3}
              />
            )
          })}

          {/* Session dots */}
          {timelineData.sessions.map((session, idx) => {
            const x = (session.offset / timelineData.totalDays) * width
            const color = phaseColor(session.phase, program.phases)

            return (
              <g key={idx}>
                <circle
                  cx={x}
                  cy={60}
                  r={session.completed ? 6 : 4}
                  fill={color}
                  opacity={session.completed ? 1 : 0.5}
                />
                <title>
                  {format(parseISO(session.date), 'MMM d')}: {session.exercises.length} exercises
                </title>
              </g>
            )
          })}

          {/* Competition markers */}
          {timelineData.competitions.map((comp, idx) => {
            const compDate = parseISO(comp.date)
            const offset = differenceInDays(compDate, timelineData.startDate)
            const x = (offset / timelineData.totalDays) * width

            return (
              <g key={idx}>
                <line
                  x1={x}
                  y1={0}
                  x2={x}
                  y2={280}
                  stroke="#ef4444"
                  strokeWidth={2}
                  strokeDasharray="4,4"
                />
                <text x={x + 4} y={20} fontSize={12} fill="#ef4444">
                  {comp.name}
                </text>
              </g>
            )
          })}

          {/* Today line */}
          {timelineData.todayOffset >= 0 && timelineData.todayOffset <= timelineData.totalDays && (
            <line
              x1={(timelineData.todayOffset / timelineData.totalDays) * width}
              y1={0}
              x2={(timelineData.todayOffset / timelineData.totalDays) * width}
              y2={280}
              stroke="#22c55e"
              strokeWidth={2}
            />
          )}

          {/* Week labels */}
          {Array.from({ length: Math.ceil(timelineData.totalDays / 7) }, (_, i) => i + 1).map((week) => {
            const x = ((week - 1) * 7 / timelineData.totalDays) * width
            return (
              <text
                key={week}
                x={x}
                y={295}
                fontSize={10}
                fill="#94a3b8"
              >
                W{week}
              </text>
            )
          })}
        </svg>
      </Paper>

      {/* Info */}
      <Text size="xs" c="dimmed">
        {format(timelineData.startDate, 'MMM d, yyyy')} → {format(timelineData.compDate, 'MMM d, yyyy')} ({timelineData.totalDays} days, {Math.ceil(timelineData.totalDays / 7)} weeks)
      </Text>
    </Stack>
  )
}
