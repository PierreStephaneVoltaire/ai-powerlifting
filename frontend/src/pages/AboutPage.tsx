import {
  Stack,
  Title,
  Text,
  Paper,
  Group,
  List,
  ThemeIcon,
  Divider,
  Table,
  Badge,
  Alert,
  Button,
  Center,
  SimpleGrid,
  Container,
} from '@mantine/core'
import {
  Activity,
  BarChart3,
  TrendingUp,
  AlertTriangle,
  Zap,
  ShieldCheck,
  Globe,
  Database,
  Calculator,
  FileSpreadsheet,
  FlaskConical,
  Utensils,
  Info,
} from 'lucide-react'
import { FORMULA_DESCRIPTIONS } from '@/constants/formulaDescriptions'

export default function AboutPage() {
  return (
    <Container size="lg" py="xl">
      <Stack gap="xl">
        {/* Header Section */}
        <Stack gap="xs">
          <Group gap="sm">
            <Activity size={32} color="var(--mantine-color-blue-filled)" />
            <Title order={1}>About the Peaking Portal</Title>
          </Group>
          <Text size="lg" c="dimmed" maw={800}>
            A single-athlete portal for preparing powerlifting competitions. It quantifies
            readiness, peaking trajectory, and attempt selection from the data produced by
            actual training — not from generic templates or coaching heuristics. The
            current peaking layer also tracks projection calibration (PRR), volume
            landmarks, and specificity bands so the meet build stays tied to recent meet
            outcomes rather than stale assumptions.
          </Text>
        </Stack>

        <Divider />

        {/* What it is + How it's built */}
        <SimpleGrid cols={{ base: 1, md: 2 }} spacing="xl">
          <Stack gap="md">
            <Title order={2} size="h3">What this is</Title>
            <Text>
              A personal performance portal focused on one question: will the current block
              put the athlete on the platform ready to hit a planned total? It ingests
              planned and logged sessions (sets, reps, kilograms, RPE, failed sets), per-session
              bodyweight, pre-session wellness, competition attempts and results, per-lift style
              profiles, and athlete body metrics. From those, it computes e1RM trajectories,
              DOTS progression, fatigue dimensions, Banister form, weekly monotony/strain,
              decoupling, projection calibration, volume landmarks, specificity bands,
              taper quality, readiness, and attempt selection for the upcoming meet.
            </Text>
            <Alert icon={<ShieldCheck size={16} />} color="blue" title="Signal over friction">
              Per-meal macros, per-night sleep scores, continuous heart rate, and minute-level
              HRV are intentionally not required. The portal tracks averages and periodic
              snapshots (bodyweight per session, diet notes, RPE) because the signal in daily
              micro-tracking rarely justifies the logging burden for a working athlete.
            </Alert>
          </Stack>
          <Stack gap="md">
            <Title order={2} size="h3">How it&apos;s built</Title>
            <Text>
              The analysis runs in two layers:
            </Text>
            <List
              spacing="xs"
              size="sm"
              center
              icon={
                <ThemeIcon color="blue" size={20} radius="xl">
                  <Zap size={12} />
                </ThemeIcon>
              }
            >
              <List.Item>
                <b>Statistical engine.</b> Deterministic math: e1RM, DOTS, INOL, EWMA ACWR,
                current fatigue state, Theil-Sen progression with fit quality, diminishing-returns
                projection, PRR calibration, volume landmarks, specificity bands, attempt
                selection, and split readiness.
              </List.Item>
              <List.Item>
                <b>AI reasoning layer.</b> Seven focused entry points: fatigue-profile
                estimation; lift-profile review, rewrite, and stimulus estimation;
                accessory-to-lift correlation analysis; block-level program evaluation;
                accessory e1RM backfill; template evaluation; and spreadsheet import.
                Each is fed the relevant subset of the program and athlete data — nothing
                else.
              </List.Item>
            </List>
          </Stack>
        </SimpleGrid>

        <Divider />

        {/* Data we capture (and why we don't capture more) */}
        <Stack gap="md">
          <Group gap="sm">
            <Database size={24} />
            <Title order={2}>Data we capture (and why we don&apos;t capture more)</Title>
          </Group>
          <Text>
            Everything below is either a direct input to a formula, a direct input to an
            AI reasoning tool, or context that changes how an output is interpreted. Fields
            the athlete would have to log obsessively to keep fresh are deliberately kept out.
          </Text>
          <SimpleGrid cols={{ base: 1, md: 2 }} spacing="md">
            <Paper withBorder p="md">
              <Text fw={600} size="sm" mb={4}>Sessions</Text>
              <Text size="sm" c="dimmed">
                Sets, reps, kilograms, RPE, failed-set flags per exercise. Session-level
                bodyweight, subjective RPE, and an optional pre-session wellness snapshot.
                Optional session notes. These are the raw inputs to e1RM, INOL, volume,
                EWMA ACWR, fatigue index, RPE drift, and readiness.
              </Text>
            </Paper>
            <Paper withBorder p="md">
              <Text fw={600} size="sm" mb={4}>Subjective wellness</Text>
              <Text size="sm" c="dimmed">
                A compact 1-5 capture of sleep, soreness, mood, stress, and energy before
                training. It is optional, fast to skip, and feeds the readiness score when
                present.
              </Text>
            </Paper>
            <Paper withBorder p="md">
              <Text fw={600} size="sm" mb={4}>Competitions</Text>
              <Text size="sm" c="dimmed">
                Federation, weight class, date, planned attempts, and results. Drives
                weeks-to-comp, peaking bonus, DOTS target, and attempt-selection math.
              </Text>
            </Paper>
            <Paper withBorder p="md">
              <Text fw={600} size="sm" mb={4}>Lift profiles</Text>
              <Text size="sm" c="dimmed">
                Per-lift style notes, sticking points, primary muscle dominance, volume
                tolerance. Used by the correlation and program-evaluation AIs to weight
                accessory relevance and to interpret metrics through the athlete&apos;s
                actual movement, not a generic textbook.
              </Text>
            </Paper>
            <Paper withBorder p="md">
              <Text fw={600} size="sm" mb={4}>Body metrics</Text>
              <Text size="sm" c="dimmed">
                Height, bodyweight, arm wingspan, leg length. Passed to the AI tools as soft
                context for leverages (e.g., long femurs shift squat loading toward the
                posterior chain). Not used in the rigid formulas.
              </Text>
            </Paper>
            <Paper withBorder p="md">
              <Text fw={600} size="sm" mb={4}>Diet notes (averages only)</Text>
              <Text size="sm" c="dimmed">
                Average daily calories, macros, sleep hours, water intake, consistency flag.
                Recorded per note window, not per meal or per night. The program-evaluation
                AI uses these to explain bodyweight trends and flag recovery confounders.
                Per-meal / per-night tracking is out of scope by design.
              </Text>
            </Paper>
            <Paper withBorder p="md">
              <Text fw={600} size="sm" mb={4}>Supplements (captured, summarized in evaluation)</Text>
              <Text size="sm" c="dimmed">
                Current stack and dosing are stored, and program evaluation already includes
                supplement summary context. Raw names and doses are still too coarse to drive
                deterministic formulas — the planned Examine.com integration will map each
                item to its evidence base before it reaches the models.
              </Text>
            </Paper>
          </SimpleGrid>
        </Stack>

        <Divider />

        {/* Detailed Formula Section */}
        <Stack gap="lg">
          <Group gap="sm">
            <Calculator size={24} />
            <Title order={2}>Mathematical Methodology</Title>
          </Group>
          <Text>
            Every number surfaced in the portal comes from one of the formulas below.
            They fall into five families: <b>scoring</b> (DOTS, estimated 1RM),{' '}
            <b>progression</b> (Theil-Sen regression on effective weeks, diminishing-returns
            projection, fit quality), <b>stress</b> (phase-adjusted INOL, EWMA ACWR,
            current fatigue state, RPE drift),{' '}
            <b>quality</b> (specificity ratio, relative-intensity distribution, compliance),
            and <b>peaking</b> (Banister fitness-fatigue, monotony/strain, decoupling,
            taper quality, attempt selection, readiness score). Each card lists the
            exact formula, its variables, and the thresholds used to interpret output.
          </Text>
          <Alert icon={<Info size={16} />} color="blue" title="Window filters and stateful metrics">
            The selected week filter narrows window summaries such as exercise stats, INOL,
            RI distribution, and specificity. Current fatigue state, ACWR, Banister, readiness,
            and alerts use full history up to the selected end date. Monotony uses a denominator
            floor and display cap, Banister projections use normalized future load, specificity
            prefers primary-goal competitions, and readiness is split into training, external,
            and overall scores.
          </Alert>

          {FORMULA_DESCRIPTIONS.map((f) => (
            <Paper key={f.id} withBorder p="xl" radius="md">
              <Stack gap="md">
                <Group justify="space-between" align="flex-start">
                  <div>
                    <Title order={3} size="h4">{f.title}</Title>
                    <Text size="sm" c="dimmed" mt={4}>{f.summary}</Text>
                  </div>
                  <Badge variant="light">Formula ID: {f.id}</Badge>
                </Group>

                <Paper withBorder p="md" bg="var(--mantine-color-gray-0)" style={{ borderLeft: '4px solid var(--mantine-color-blue-filled)', overflowX: 'auto' }}>
                  <Text ff="monospace" style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word', fontSize: '0.9rem' }}>
                    {f.formula}
                  </Text>
                </Paper>

                <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="md">
                  <div>
                    <Text fw={600} size="xs" tt="uppercase" c="dimmed" mb={8}>Variables & Parameters</Text>
                    <Table fz="xs" style={{ tableLayout: 'fixed' }}>
                      <Table.Tbody>
                        {f.variables.map((v) => (
                          <Table.Tr key={v.name}>
                            <Table.Td fw={700} w="35%" style={{ wordBreak: 'break-word' }}>{v.name}</Table.Td>
                            <Table.Td style={{ wordBreak: 'break-word' }}>{v.description}</Table.Td>
                          </Table.Tr>
                        ))}
                      </Table.Tbody>
                    </Table>
                  </div>
                  {f.thresholds && (
                    <div>
                      <Text fw={600} size="xs" tt="uppercase" c="dimmed" mb={8}>Thresholds & Interpretation</Text>
                      <Stack gap={4}>
                        {f.thresholds.map((t) => (
                          <Group key={t.label} gap="xs">
                            <Badge size="xs" variant="outline">{t.label}</Badge>
                            <Text size="xs"><b>{t.value}</b>: {t.flag}</Text>
                          </Group>
                        ))}
                      </Stack>
                    </div>
                  )}
                </SimpleGrid>
              </Stack>
            </Paper>
          ))}
        </Stack>

        <Divider />

        {/* Imperfections & Context */}
        <Stack gap="md">
          <Group gap="sm">
            <AlertTriangle size={24} color="var(--mantine-color-yellow-filled)" />
            <Title order={2}>Known Imperfections & Limitations</Title>
          </Group>
          <Text>
            The portal is honest about what it does not measure. The list below is the current
            set of known blind spots — not a claim that any of them are unimportant.
          </Text>
          <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="md">
            <Paper withBorder p="md">
              <Text fw={600} size="sm" mb={4}>Chronobiology</Text>
              <Text size="sm" c="dimmed">
                Training typically happens in the evening; meets typically run in the morning.
                The model does not adjust e1RM or readiness for time-of-day performance
                differences or for meet-flight timing.
              </Text>
            </Paper>
            <Paper withBorder p="md">
              <Text fw={600} size="sm" mb={4}>Supplementation</Text>
              <Text size="sm" c="dimmed">
                Supplement stacks and doses are stored and summarized for program evaluation,
                but they are still too coarse to drive deterministic formulas. The planned
                Examine.com integration will map each item to its evidence base before
                exposing it to the models.
              </Text>
            </Paper>
            <Paper withBorder p="md">
              <Text fw={600} size="sm" mb={4}>Diet and sleep granularity</Text>
              <Text size="sm" c="dimmed">
                Calories, macros, sleep, and water are tracked as averages per note window —
                never per meal or per night — because that level of logging is untenable in
                real training. Future Examine.com-backed reasoning will interpret these
                averages against progress and fatigue signals.
              </Text>
            </Paper>
            <Paper withBorder p="md">
              <Text fw={600} size="sm" mb={4}>Biometric precision</Text>
              <Text size="sm" c="dimmed">
                While we capture limb lengths, this data is currently NOT accounted for in the rigid
                fatigue profile formulas. It is passed to the AI as context, meaning fatigue index
                values lack this granularity, and its existence during evaluations is at the
                discretion of the AI reasoning layer.
              </Text>
            </Paper>
            <Paper withBorder p="md">
              <Text fw={600} size="sm" mb={4}>No video analysis</Text>
              <Text size="sm" c="dimmed">
                Bar path, rep consistency, and technical regressions are not captured. Velocity
                loss is inferred indirectly from RPE and failed-set patterns. Computer vision
                is out of scope for cost and complexity reasons.
              </Text>
            </Paper>
            <Paper withBorder p="md">
              <Text fw={600} size="sm" mb={4}>Single-athlete scope</Text>
              <Text size="sm" c="dimmed">
                Every calibration, phase definition, and attempt-selection default is tuned for
                one athlete. Population-level normalization (age, sex-curves, federation norms)
                is a separate roadmap item, not a current feature.
              </Text>
            </Paper>
          </SimpleGrid>
        </Stack>

        <Divider />

        {/* Future Roadmap */}
        <Stack gap="md">
          <Group gap="sm">
            <TrendingUp size={24} color="var(--mantine-color-green-filled)" />
            <Title order={2}>The Roadmap</Title>
          </Group>

          <Paper withBorder p="xl" bg="var(--mantine-color-blue-light)">
            <Stack gap="lg">
              <Group gap="lg" wrap="nowrap" align="flex-start">
                <Stack gap={4} align="center" miw={96}>
                  <FileSpreadsheet size={32} />
                  <Text size="xs" fw={700} ta="center">Excel workout import</Text>
                </Stack>
                <Text size="sm">
                  <b>Upload a filled training log</b> (Excel) and get the same statistical
                  and AI analysis the portal runs on natively-entered data. Targets athletes
                  who track in spreadsheets and don&apos;t want to re-enter history to get
                  access to the analytics.
                </Text>
              </Group>

              <Group gap="lg" wrap="nowrap" align="flex-start">
                <Stack gap={4} align="center" miw={96}>
                  <FileSpreadsheet size={32} />
                  <Text size="xs" fw={700} ta="center">Excel program import</Text>
                </Stack>
                <Text size="sm">
                  <b>Upload a program spec</b> (phases, session templates, per-day exercises)
                  to seed a new block without hand-entry. Pairs with the workout import so a
                  full block can be set up and back-filled in one pass.
                </Text>
              </Group>

              <Group gap="lg" wrap="nowrap" align="flex-start">
                <Stack gap={4} align="center" miw={96}>
                  <FlaskConical size={32} />
                  <Text size="xs" fw={700} ta="center">Examine.com supplements</Text>
                </Stack>
                <Text size="sm">
                  <b>Evidence-backed supplement reasoning.</b> Map each logged supplement
                  against Examine.com&apos;s research base, then let the AI tools factor the
                  substantiated effects (on fatigue, recovery, or progress) into their
                  interpretation instead of inferring from raw names.
                </Text>
              </Group>

              <Group gap="lg" wrap="nowrap" align="flex-start">
                <Stack gap={4} align="center" miw={96}>
                  <Utensils size={32} />
                  <Text size="xs" fw={700} ta="center">Examine.com nutrition</Text>
                </Stack>
                <Text size="sm">
                  <b>Evidence-backed macro / sleep / water reasoning.</b> Same approach as
                  supplements — use published research to translate average calorie, macro,
                  sleep, and water trends into concrete effects on progress and fatigue,
                  rather than hand-wave them in the prompt.
                </Text>
              </Group>

              <Group gap="lg" wrap="nowrap" align="flex-start">
                <Stack gap={4} align="center" miw={96}>
                  <Globe size={32} />
                  <Text size="xs" fw={700} ta="center">OpenPowerlifting</Text>
                </Stack>
                <Text size="sm">
                  <b>Comparative benchmarking.</b> Score readiness and projected totals
                  against regional, national, and global populations over recent years,
                  filtered by federation, weight class, age, and sex.
                </Text>
              </Group>

              <Group gap="lg" wrap="nowrap" align="flex-start">
                <Stack gap={4} align="center" miw={96}>
                  <Database size={32} />
                  <Text size="xs" fw={700} ta="center">Demographics</Text>
                </Stack>
                <Text size="sm">
                  <b>Age and sex normalization.</b> Adjust e1RM and DOTS trajectories
                  against age-graded performance curves and sex-specific recovery profiles,
                  so year-over-year comparisons don&apos;t reward or penalize aging.
                </Text>
              </Group>

              <Group gap="lg" wrap="nowrap" align="flex-start">
                <Stack gap={4} align="center" miw={96}>
                  <BarChart3 size={32} />
                  <Text size="xs" fw={700} ta="center">In-session adjustments</Text>
                </Stack>
                <Text size="sm">
                  <b>Mid-session corrections.</b> Suggest load or set changes during a session
                  based on acute fatigue, failed sets, or injury flags — rather than waiting
                  until the next block evaluation to react.
                </Text>
              </Group>
            </Stack>
          </Paper>
        </Stack>

        <Divider />

        {/* Footer info */}
        <Center pb="xl">
          <Text size="xs" c="dimmed" ta="center">
            Developed for statistical analysis of peaking programs. <br />
            Data is strictly used for performance modeling and visualization.
          </Text>
        </Center>
      </Stack>
    </Container>
  )
}
