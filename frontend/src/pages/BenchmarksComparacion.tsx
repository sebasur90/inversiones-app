import { useState, useEffect } from 'react'
import {
  Container,
  Grid,
  Paper,
  Segmented,
  Group,
  Title,
  Text,
  Stack,
  Loader,
  Center,
  MultiSelect,
  Badge,
  Table,
  Tabs,
} from '@mantine/core'
import {
  getPerformanceCompare,
  getOpportunityCost,
  getBenchmarksDisponibles,
  getTickersConPrecios,
  type PerformanceCompareOut,
  type OpportunityCostOut,
} from '../api'
import BenchmarkComparisonTable from '../components/inversiones/BenchmarkComparisonTable'
import PerformanceCompareChart from '../components/charts/PerformanceCompareChart'
import { formatUSD, formatARS } from '../utils'

const OPCIONES_PERIODO = [
  { label: 'Último mes', value: '1m' },
  { label: 'Últimos 3 meses', value: '3m' },
  { label: 'Últimos 6 meses', value: '6m' },
  { label: 'Último año', value: '1y' },
  { label: 'Desde inicio', value: 'all' },
]

const OPCIONES_MONEDA = [
  { label: 'USD', value: 'usd' },
  { label: 'ARS Nominal', value: 'ars_nominal' },
  { label: 'ARS Real', value: 'ars_real' },
]

const calcularDesdeFromPeriod = (period: string): string | undefined => {
  const hoy = new Date()
  let desde: Date | null = null

  switch (period) {
    case '1m':
      desde = new Date(hoy.setMonth(hoy.getMonth() - 1))
      break
    case '3m':
      desde = new Date(hoy.setMonth(hoy.getMonth() - 3))
      break
    case '6m':
      desde = new Date(hoy.setMonth(hoy.getMonth() - 6))
      break
    case '1y':
      desde = new Date(hoy.setFullYear(hoy.getFullYear() - 1))
      break
    default:
      return undefined
  }

  return desde ? desde.toISOString().split('T')[0] : undefined
}

interface BenchmarksComparacionProps {
  cartera?: string | null
}

export default function BenchmarksComparacion({ cartera = null }: BenchmarksComparacionProps) {
  const [periodo, setPeriodo] = useState('1y')
  const [moneda, setMoneda] = useState<'usd' | 'ars_nominal' | 'ars_real'>('usd')
  const [benchmarks, setBenchmarks] = useState<string[]>([])
  const [tickers, setTickers] = useState<string[]>([])
  const [benchmarksDisponibles, setBenchmarksDisponibles] = useState<string[]>([])
  const [tickersConPrecios, setTickersConPrecios] = useState<string[]>([])
  const [performanceData, setPerformanceData] = useState<PerformanceCompareOut | null>(null)
  const [opportunityCostData, setOpportunityCostData] = useState<OpportunityCostOut | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    Promise.all([getBenchmarksDisponibles(), getTickersConPrecios()])
      .then(([benchs, ticks]) => {
        setBenchmarksDisponibles(benchs)
        setTickersConPrecios(ticks.map(t => t.ticker))
      })
      .catch(err => console.error('Error loading benchmarks/tickers:', err))
  }, [])

  useEffect(() => {
    if (benchmarksDisponibles.length > 0 && benchmarks.length === 0) {
      // Auto-select first two benchmarks
      setBenchmarks(benchmarksDisponibles.slice(0, 2))
    }
  }, [benchmarksDisponibles])

  const loadData = async () => {
    setLoading(true)
    try {
      const desde = calcularDesdeFromPeriod(periodo)
      const [perfData, oppData] = await Promise.all([
        getPerformanceCompare(cartera, moneda, desde, benchmarks, tickers),
        benchmarks.length > 0 ? getOpportunityCost(cartera, benchmarks[0], desde) : Promise.resolve(null),
      ])
      setPerformanceData(perfData)
      if (oppData) setOpportunityCostData(oppData)
    } catch (err) {
      console.error('Error loading performance data:', err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (benchmarks.length > 0 || tickers.length > 0) {
      loadData()
    }
  }, [periodo, moneda, benchmarks, tickers])

  if (loading) {
    return (
      <Center style={{ height: '400px' }}>
        <Loader />
      </Center>
    )
  }

  return (
    <Container size="xl" py="lg">
      <Title order={1} mb="lg">
        Comparación de Benchmarks
      </Title>

      <Paper p="md" mb="lg" withBorder>
        <Grid>
          <Grid.Col span={{ base: 12, sm: 6 }}>
            <Stack gap="sm">
              <div>
                <Text size="sm" fw={500} mb="xs">
                  Período
                </Text>
                <Segmented
                  value={periodo}
                  onChange={setPeriodo}
                  data={OPCIONES_PERIODO}
                  fullWidth
                />
              </div>
              <div>
                <Text size="sm" fw={500} mb="xs">
                  Moneda
                </Text>
                <Segmented
                  value={moneda}
                  onChange={setMoneda as any}
                  data={OPCIONES_MONEDA}
                  fullWidth
                />
              </div>
            </Stack>
          </Grid.Col>
          <Grid.Col span={{ base: 12, sm: 6 }}>
            <Stack gap="sm">
              <div>
                <Text size="sm" fw={500} mb="xs">
                  Benchmarks
                </Text>
                <MultiSelect
                  data={benchmarksDisponibles}
                  value={benchmarks}
                  onChange={setBenchmarks}
                  placeholder="Selecciona benchmarks"
                  searchable
                  clearable
                />
              </div>
              <div>
                <Text size="sm" fw={500} mb="xs">
                  Tickers
                </Text>
                <MultiSelect
                  data={tickersConPrecios}
                  value={tickers}
                  onChange={setTickers}
                  placeholder="Selecciona tickers"
                  searchable
                  clearable
                />
              </div>
            </Stack>
          </Grid.Col>
        </Grid>
      </Paper>

      {performanceData && (
        <Tabs defaultValue="comparacion">
          <Tabs.List>
            <Tabs.Tab value="comparacion">Comparación</Tabs.Tab>
            <Tabs.Tab value="oportunidad">Costo de Oportunidad</Tabs.Tab>
          </Tabs.List>

          <Tabs.Panel value="comparacion" py="lg">
            <Stack gap="lg">
              <div>
                <Title order={3} mb="md">
                  Rendimientos
                </Title>
                <BenchmarkComparisonTable filas={performanceData.filas} />
              </div>

              {performanceData.serie && performanceData.serie.length > 0 && (
                <div>
                  <Title order={3} mb="md">
                    Evolución del Índice
                  </Title>
                  <Paper withBorder p="md">
                    <PerformanceCompareChart serie={performanceData.serie} />
                  </Paper>
                </div>
              )}
            </Stack>
          </Tabs.Panel>

          <Tabs.Panel value="oportunidad" py="lg">
            {opportunityCostData ? (
              <Stack gap="lg">
                <div>
                  <Title order={3} mb="md">
                    Resumen de Costo de Oportunidad
                  </Title>
                  {opportunityCostData.estado === 'ok' ? (
                    <Grid>
                      <Grid.Col span={{ base: 12, sm: 6, md: 3 }}>
                        <Paper p="md" withBorder>
                          <Text size="sm" c="dimmed" mb="xs">
                            Valor Actual
                          </Text>
                          <Group justify="space-between">
                            <Text fw={500}>
                              {moneda === 'usd'
                                ? formatUSD(opportunityCostData.valor_actual_usd || 0)
                                : formatARS(opportunityCostData.valor_actual_ars || 0)}
                            </Text>
                          </Group>
                        </Paper>
                      </Grid.Col>
                      <Grid.Col span={{ base: 12, sm: 6, md: 3 }}>
                        <Paper p="md" withBorder>
                          <Text size="sm" c="dimmed" mb="xs">
                            Valor Shadow
                          </Text>
                          <Text fw={500}>
                            {moneda === 'usd'
                              ? formatUSD(opportunityCostData.valor_shadow_usd || 0)
                              : formatARS(opportunityCostData.valor_shadow_ars || 0)}
                          </Text>
                        </Paper>
                      </Grid.Col>
                      <Grid.Col span={{ base: 12, sm: 6, md: 3 }}>
                        <Paper p="md" withBorder>
                          <Text size="sm" c="dimmed" mb="xs">
                            Costo de Oportunidad
                          </Text>
                          <Text
                            fw={500}
                            c={
                              (opportunityCostData.costo_oportunidad_usd || 0) > 0
                                ? 'red'
                                : 'green'
                            }
                          >
                            {moneda === 'usd'
                              ? formatUSD(opportunityCostData.costo_oportunidad_usd || 0)
                              : formatARS(opportunityCostData.costo_oportunidad_ars || 0)}
                          </Text>
                        </Paper>
                      </Grid.Col>
                      <Grid.Col span={{ base: 12, sm: 6, md: 3 }}>
                        <Paper p="md" withBorder>
                          <Text size="sm" c="dimmed" mb="xs">
                            Benchmark
                          </Text>
                          <Badge>{opportunityCostData.benchmark_usado}</Badge>
                        </Paper>
                      </Grid.Col>
                    </Grid>
                  ) : (
                    <Paper p="md" withBorder>
                      <Text c="dimmed">
                        {opportunityCostData.estado === 'sin_benchmark'
                          ? 'No hay benchmark configurado'
                          : 'Datos insuficientes'}
                      </Text>
                    </Paper>
                  )}
                </div>

                {opportunityCostData.estado === 'ok' && opportunityCostData.por_posicion.length > 0 && (
                  <div>
                    <Title order={3} mb="md">
                      Costo de Oportunidad por Posición
                    </Title>
                    <Paper withBorder>
                      <Table striped highlightOnHover>
                        <Table.Thead>
                          <Table.Tr>
                            <Table.Th>Ticker</Table.Th>
                            <Table.Th style={{ textAlign: 'right' }}>Valor Actual</Table.Th>
                            <Table.Th style={{ textAlign: 'right' }}>Valor Shadow</Table.Th>
                            <Table.Th style={{ textAlign: 'right' }}>Costo Oportunidad (USD)</Table.Th>
                            <Table.Th style={{ textAlign: 'right' }}>Costo Oportunidad (ARS)</Table.Th>
                          </Table.Tr>
                        </Table.Thead>
                        <Table.Tbody>
                          {opportunityCostData.por_posicion.map((pos) => (
                            <Table.Tr key={pos.ticker}>
                              <Table.Td fw={500}>{pos.ticker}</Table.Td>
                              <Table.Td style={{ textAlign: 'right' }}>
                                {formatUSD(pos.valor_actual_usd)}
                              </Table.Td>
                              <Table.Td style={{ textAlign: 'right' }}>
                                {formatUSD(pos.valor_shadow_usd)}
                              </Table.Td>
                              <Table.Td style={{ textAlign: 'right', color: pos.costo_oportunidad_usd > 0 ? '#fa5252' : '#40c057' }}>
                                {formatUSD(pos.costo_oportunidad_usd)}
                              </Table.Td>
                              <Table.Td style={{ textAlign: 'right', color: pos.costo_oportunidad_ars > 0 ? '#fa5252' : '#40c057' }}>
                                {formatARS(pos.costo_oportunidad_ars)}
                              </Table.Td>
                            </Table.Tr>
                          ))}
                        </Table.Tbody>
                      </Table>
                    </Paper>
                  </div>
                )}
              </Stack>
            ) : (
              <Paper p="md" withBorder>
                <Text c="dimmed">Selecciona un benchmark para ver el análisis de costo de oportunidad</Text>
              </Paper>
            )}
          </Tabs.Panel>
        </Tabs>
      )}
    </Container>
  )
}
