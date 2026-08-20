import { useEffect, useState, useMemo } from 'react'
import dayjs from 'dayjs'
import { useInversionesContext } from '../context/InversionesContext'
import { useObjetivoInversion } from '../hooks/useObjetivoInversion'
import { formatUSD, formatPct } from '../utils'
import {
  derivarPlanObjetivo,
  calcularDesviacionPlan,
  calcularEscenarios,
  resolverFechaAlcanzable,
  calcularGrillaSensibilidad,
  simularMesAMes,
  resolverTasaBase,
} from '../utils/proyeccion'
import ScreenHeader from '../components/layout/ScreenHeader'
import Card from '../components/ui/Card'
import EmptyState from '../components/ui/EmptyState'
import Segmented from '../components/ui/Segmented'
import MetricTile from '../components/ui/MetricTile'
import AportesChart from '../components/charts/AportesChart'
import ProyeccionPatrimonialChart from '../components/charts/ProyeccionPatrimonialChart'
import SensibilidadGrid from '../components/charts/SensibilidadGrid'
import SimuladorInverso from '../components/inversiones/SimuladorInverso'
import { Icon } from '../components/icons/Icons'
import InfoTooltip from '../help/components/InfoTooltip'
import FormHelp from '../help/components/FormHelp'

export default function Objetivo() {
  const { carteras, carteraSeleccionada, setCarteraSeleccionada } = useInversionesContext()
  const { objetivo, aportesHistoricos, evolucion, riesgo, configuracion, loading } =
    useObjetivoInversion(carteraSeleccionada)
  const [tasaOverride, setTasaOverride] = useState('')
  const [escenarioActual, setEscenarioActual] = useState<'conservador' | 'base' | 'optimista'>(
    'base'
  )

  useEffect(() => {
    if (!carteraSeleccionada) return
    const stored = localStorage.getItem(`objetivo-tasa-${carteraSeleccionada}`)
    setTasaOverride(stored ?? '')
  }, [carteraSeleccionada])

  const handleTasaOverride = (value: string) => {
    setTasaOverride(value)
    if (carteraSeleccionada) {
      localStorage.setItem(`objetivo-tasa-${carteraSeleccionada}`, value)
    }
  }

  // Resolver tasa base (con posible override en localStorage)
  const tasaBaseResuelto = useMemo(() => {
    if (tasaOverride) {
      const override = parseFloat(tasaOverride.replace(',', '.'))
      if (!isNaN(override)) {
        return { valor: override, fuente: 'configuracion' as const } // override es una customización del usuario, no persiste en backend
      }
    }
    return resolverTasaBase(configuracion ?? null, riesgo ?? null)
  }, [tasaOverride, configuracion, riesgo])

  // Derivar plan
  const plan = useMemo(() => {
    if (!objetivo || !aportesHistoricos) return null
    return derivarPlanObjetivo(
      objetivo.monto_usd,
      objetivo.fecha_limite,
      aportesHistoricos.curva[0]?.mes ?? null,
      tasaBaseResuelto.valor
    )
  }, [objetivo, aportesHistoricos, tasaBaseResuelto.valor])

  // Desviación frente al plan
  const desviacion = useMemo(() => {
    if (!plan || !evolucion) return null
    const ultimoPunto = evolucion.puntos[evolucion.puntos.length - 1]
    return calcularDesviacionPlan(plan, ultimoPunto?.valor_usd ?? 0)
  }, [plan, evolucion])

  // Escenarios
  const escenarios = useMemo(() => {
    if (!objetivo) return null
    return calcularEscenarios(
      tasaBaseResuelto.valor,
      riesgo?.volatilidad.estado === 'ok' ? riesgo.volatilidad.anualizada ?? null : null
    )
  }, [objetivo, tasaBaseResuelto.valor, riesgo])

  // Fechas estimadas (aporte actual)
  const fechaAportueActual = useMemo(() => {
    if (!objetivo) return null
    return resolverFechaAlcanzable(
      objetivo.monto_usd,
      {
        valorInicialUsd: objetivo.valor_actual_usd,
        aporteMensualUsd: objetivo.aporte_mensual_promedio_usd,
        crecimientoAporteAnualPct: 0,
        tasaAnualPct: tasaBaseResuelto.valor,
      },
      1200,
      new Date()
    )
  }, [objetivo, tasaBaseResuelto.valor])

  // Fechas estimadas (aporte necesario + presets)
  const [aporteBonusMultiplier, setAporteBonusMultiplier] = useState(0) // 0 = necesario, 1.25 = +25%, 1.5 = +50%, 2 = +100%
  const aportesPresets = useMemo(() => {
    if (!objetivo || !objetivo.aporte_mensual_necesario_usd) return { necesario: null, plus25: null, plus50: null, plus100: null }
    const base = objetivo.aporte_mensual_necesario_usd
    return {
      necesario: base,
      plus25: base * 1.25,
      plus50: base * 1.5,
      plus100: base * 2,
    }
  }, [objetivo])

  const fechaAporteObjetivo = useMemo(() => {
    if (!objetivo) return null
    const aporte =
      aporteBonusMultiplier === 0
        ? objetivo.aporte_mensual_necesario_usd
        : aportesPresets[['necesario', 'plus25', 'plus50', 'plus100'][aporteBonusMultiplier] as keyof typeof aportesPresets]
    if (!aporte) return null
    return resolverFechaAlcanzable(
      objetivo.monto_usd,
      {
        valorInicialUsd: objetivo.valor_actual_usd,
        aporteMensualUsd: aporte,
        crecimientoAporteAnualPct: 0,
        tasaAnualPct: tasaBaseResuelto.valor,
      },
      1200,
      new Date()
    )
  }, [objetivo, tasaBaseResuelto.valor, aporteBonusMultiplier, aportesPresets])

  // Grilla de sensibilidad
  const grillaSensibilidad = useMemo(() => {
    if (!objetivo || !escenarios) return null
    const tasas = [
      escenarios.conservador - escenarios.conservador + escenarios.conservador - 2 * (escenarios.base - escenarios.conservador),
      escenarios.conservador - (escenarios.base - escenarios.conservador),
      escenarios.base,
      escenarios.optimista + (escenarios.optimista - escenarios.base),
      escenarios.optimista + 2 * (escenarios.optimista - escenarios.base),
    ]
    const aportesGrilla = [
      objetivo.aporte_mensual_promedio_usd,
      objetivo.aporte_mensual_necesario_usd ?? objetivo.aporte_mensual_promedio_usd * 1.5,
      (objetivo.aporte_mensual_necesario_usd ?? objetivo.aporte_mensual_promedio_usd * 1.5) * 1.25,
      (objetivo.aporte_mensual_necesario_usd ?? objetivo.aporte_mensual_promedio_usd * 1.5) * 1.5,
    ]
    return {
      grilla: calcularGrillaSensibilidad(
        objetivo.monto_usd,
        objetivo.valor_actual_usd,
        tasas,
        aportesGrilla
      ),
      tasas,
      aportes: aportesGrilla,
    }
  }, [objetivo, escenarios])

  // Proyección patrimonial
  const puntosPlan = useMemo(() => {
    if (!plan) return []
    return simularMesAMes(
      {
        valorInicialUsd: 0,
        aporteMensualUsd: plan.aporteMensualEsperadoUsd,
        crecimientoAporteAnualPct: 0,
        tasaAnualPct: plan.tasaBaseAnualPct,
      },
      plan.mesesTotales,
      dayjs(plan.fechaInicio).toDate()
    )
  }, [plan])

  const puntosProyeccion = useMemo(() => {
    if (!objetivo || !escenarios) return []
    const tasaEscenario = escenarios[escenarioActual]
    return simularMesAMes(
      {
        valorInicialUsd: objetivo.valor_actual_usd,
        aporteMensualUsd: objetivo.aporte_mensual_promedio_usd,
        crecimientoAporteAnualPct: 0,
        tasaAnualPct: tasaEscenario,
      },
      objetivo.meses_restantes,
      new Date()
    )
  }, [objetivo, escenarios, escenarioActual])

  const esProyeccionAlcanzable = useMemo(() => {
    if (!puntosProyeccion || puntosProyeccion.length === 0 || !objetivo) return false
    return puntosProyeccion[puntosProyeccion.length - 1].valorUsd >= objetivo.monto_usd
  }, [puntosProyeccion, objetivo])

  if (!carteraSeleccionada) {
    return (
      <div className="pb-4">
        <ScreenHeader title="Objetivo" />
        <EmptyState
          title="Elegí una cartera"
          description="Los objetivos se definen por cartera, no aplican al Consolidado."
        />
        <div className="flex flex-col gap-1.5 px-4">
          {carteras.map(c => (
            <button
              key={c.nombre}
              onClick={() => setCarteraSeleccionada(c.nombre)}
              className="text-left px-3.5 py-3 rounded-xl text-[13.5px] font-semibold text-app-text bg-app-surface border border-app-border"
            >
              {c.nombre}
            </button>
          ))}
        </div>
      </div>
    )
  }

  const progreso = objetivo ? Math.min((objetivo.valor_actual_usd / objetivo.monto_usd) * 100, 100) : 0

  return (
    <div className="pb-4">
      <ScreenHeader title="Objetivo" />

      {loading ? (
        <div className="py-20 text-center text-app-text-dim text-[13px]">Cargando…</div>
      ) : !objetivo ? (
        <EmptyState
          title="Esta cartera no tiene un objetivo definido"
          description={`Agregá una fila para "${carteraSeleccionada}" en la pestaña "Objetivos" del Sheet (Cartera, Nombre, Fecha Límite, Monto USD) y sincronizá con el botón de arriba.`}
        />
      ) : (
        <>
          {/* Header + anillo de progreso */}
          <div className="flex items-center gap-3 mb-4">
            <div className="w-[46px] h-[46px] rounded-2xl bg-app-gold-soft flex items-center justify-center text-[21px] shrink-0">
              {objetivo.icono}
            </div>
            <div className="flex-1 min-w-0">
              <div className="font-display text-[18px] font-semibold text-app-text truncate">
                {objetivo.nombre}
              </div>
              <div className="text-[11.5px] text-app-text-dim">
                Meta al {dayjs(objetivo.fecha_limite).format('MMM YYYY')} · cartera {carteraSeleccionada}
              </div>
            </div>
          </div>

          <Card>
            <div className="flex items-center gap-5">
              <div
                className="relative w-[130px] h-[130px] rounded-full shrink-0"
                style={{
                  background: `conic-gradient(${objetivo.alcanzable ? '#d8b14a' : '#e2665a'} 0% ${progreso}%, #223028 ${progreso}% 100%)`,
                }}
              >
                <div className="absolute inset-3.5 rounded-full bg-app-surface flex flex-col items-center justify-center">
                  <b className="font-mono text-[21px] text-app-text tabular-nums">
                    {progreso.toFixed(0)}%
                  </b>
                  <span className="text-[9px] text-app-text-dim mt-0.5">completado</span>
                </div>
              </div>
              <div className="flex-1 flex flex-col gap-2.5 min-w-0">
                <div>
                  <b className="font-mono text-[14px] text-app-text tabular-nums block">
                    {formatUSD(objetivo.valor_actual_usd)}
                  </b>
                  <span className="text-[10px] uppercase tracking-wide text-app-text-dim">
                    de {formatUSD(objetivo.monto_usd)}
                  </span>
                </div>
                <div>
                  <b className="font-mono text-[14px] text-app-text tabular-nums block">
                    {objetivo.meses_restantes} meses
                  </b>
                  <span className="text-[10px] uppercase tracking-wide text-app-text-dim">Restantes</span>
                </div>
                <span
                  className={`inline-flex items-center gap-1.5 font-bold text-[11px] px-2.5 py-1.5 rounded-lg w-fit ${
                    objetivo.alcanzable
                      ? 'bg-app-teal-soft text-app-teal'
                      : 'bg-app-coral-soft text-app-coral'
                  }`}
                >
                  <Icon name={objetivo.alcanzable ? 'up' : 'down'} className="w-3 h-3" />
                  {objetivo.meses_restantes === 0
                    ? 'Fecha límite vencida'
                    : objetivo.alcanzable
                      ? 'Alcanzable'
                      : 'En riesgo'}
                </span>
              </div>
            </div>
          </Card>

          {/* Grid 2x2 de aportes */}
          <div className="grid grid-cols-2 gap-2 my-3.5">
            <MetricTile
              label="Aporte prom./mes"
              value={formatUSD(objetivo.aporte_mensual_promedio_usd)}
              infoTerm="objetivo_aporte_mensual"
            />
            <MetricTile
              label="Necesario/mes"
              value={objetivo.aporte_mensual_necesario_usd != null ? formatUSD(objetivo.aporte_mensual_necesario_usd) : '—'}
              tone={objetivo.alcanzable ? undefined : 'neg'}
            />
            {plan ? (
              <>
                <MetricTile
                  label="Esperado/mes"
                  value={formatUSD(plan.aporteMensualEsperadoUsd)}
                  sub="según plan original"
                />
                {desviacion ? (
                  <MetricTile
                    label="Desviación vs. plan"
                    value={formatUSD(Math.abs(desviacion.desviacionUsd))}
                    sub={desviacion.desviacionPct != null ? `${desviacion.adelantado ? '+' : ''}${(desviacion.desviacionPct * 100).toFixed(1)}%` : undefined}
                    tone={desviacion.adelantado ? 'pos' : 'neg'}
                    infoTerm="objetivo_desviacion_plan"
                  />
                ) : null}
              </>
            ) : null}
          </div>

          {/* Fechas estimadas */}
          <h3 className="text-[13.5px] font-bold text-app-text mb-2.5 flex items-center gap-1.5">
            <Icon name="trend" className="w-3.5 h-3.5 text-app-gold" />
            Fechas estimadas
          </h3>
          <Card>
            <div className="space-y-3.5">
              <div>
                <div className="text-[10px] font-bold uppercase tracking-wide text-app-text-faint mb-1">
                  Manteniendo aporte actual ({formatUSD(objetivo.aporte_mensual_promedio_usd)}/mes)
                </div>
                {fechaAportueActual?.fecha ? (
                  <div className="font-mono text-[14px] font-semibold text-app-text">
                    {dayjs(fechaAportueActual.fecha).format('MMM DD, YYYY')}{' '}
                    <span className="text-[11px] text-app-text-dim">
                      ({fechaAportueActual.meses} meses)
                    </span>
                  </div>
                ) : (
                  <div className="text-[12px] text-app-text-dim">—</div>
                )}
              </div>

              <div>
                <div className="text-[10px] font-bold uppercase tracking-wide text-app-text-faint mb-2">
                  Con aporte objetivo
                </div>
                {fechaAporteObjetivo?.fecha ? (
                  <div className="font-mono text-[14px] font-semibold text-app-text mb-2">
                    {dayjs(fechaAporteObjetivo.fecha).format('MMM DD, YYYY')}{' '}
                    <span className="text-[11px] text-app-text-dim">
                      ({fechaAporteObjetivo.meses} meses)
                    </span>
                  </div>
                ) : (
                  <div className="text-[12px] text-app-text-dim mb-2">—</div>
                )}
                <div className="flex gap-1.5">
                  {['Necesario', '+25%', '+50%', '+100%'].map((label, idx) => (
                    <button
                      key={idx}
                      onClick={() => setAporteBonusMultiplier(idx)}
                      className={`text-[10px] px-2 py-1 rounded-lg font-semibold transition-colors ${
                        aporteBonusMultiplier === idx
                          ? 'bg-app-gold text-app-text'
                          : 'bg-app-surface-2 text-app-text-dim hover:text-app-text'
                      }`}
                    >
                      {label}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          </Card>

          {/* Escenarios */}
          {escenarios ? (
            <>
              <h3 className="text-[13.5px] font-bold text-app-text mb-2.5 mt-3.5">Escenarios</h3>
              <Card>
                <div className="grid grid-cols-3 gap-2 mb-3">
                  {(['conservador', 'base', 'optimista'] as const).map(esc => {
                    const tasa = escenarios[esc]
                    const fechaEsc = resolverFechaAlcanzable(
                      objetivo.monto_usd,
                      {
                        valorInicialUsd: objetivo.valor_actual_usd,
                        aporteMensualUsd: objetivo.aporte_mensual_promedio_usd,
                        crecimientoAporteAnualPct: 0,
                        tasaAnualPct: tasa,
                      },
                      1200,
                      new Date()
                    )
                    const alcanzable = fechaEsc.fecha
                      ? dayjs(fechaEsc.fecha).isBefore(dayjs(objetivo.fecha_limite).add(1, 'day'))
                      : false

                    return (
                      <div key={esc} className="bg-app-surface rounded-lg p-2.5">
                        <div className="text-[9px] font-bold uppercase tracking-wide text-app-text-faint mb-1">
                          {esc}
                        </div>
                        <div className="font-mono text-[14px] font-bold text-app-text mb-1">
                          {formatPct(tasa)}
                        </div>
                        <div className="text-[10px] text-app-text-dim mb-2">
                          {fechaEsc.fecha
                            ? dayjs(fechaEsc.fecha).format('MMM YYYY')
                            : '∞'}
                        </div>
                        <span
                          className={`inline-flex text-[9px] font-semibold px-2 py-1 rounded-md w-full text-center justify-center ${
                            alcanzable
                              ? 'bg-app-teal-soft text-app-teal'
                              : 'bg-app-coral-soft text-app-coral'
                          }`}
                        >
                          {alcanzable ? 'Alcanzable' : 'En riesgo'}
                        </span>
                      </div>
                    )
                  })}
                </div>
                <div className="text-[8.5px] text-app-text-faint">
                  Spread:{' '}
                  {escenarios.fuenteSpread === 'volatilidad'
                    ? `± ${((escenarios.optimista - escenarios.conservador) / 2).toFixed(1)}pp según volatilidad histórica`
                    : '± 3pp (historial insuficiente, estimación fija)'}
                </div>
              </Card>
            </>
          ) : null}

          {/* Proyección patrimonial */}
          {puntosPlan.length > 0 && puntosProyeccion.length > 0 ? (
            <>
              <h3 className="text-[13.5px] font-bold text-app-text mb-2.5 mt-3.5">Proyección patrimonial</h3>
              <Card>
                {escenarios && (
                  <div className="mb-3">
                    <label className="block text-[10px] font-bold uppercase tracking-wide text-app-text-faint mb-1.5 flex items-center gap-1.5">
                      Escenario mostrado
                      <InfoTooltip term="objetivo_escenario_mostrado" />
                    </label>
                    <Segmented<'conservador' | 'base' | 'optimista'>
                      value={escenarioActual}
                      onChange={setEscenarioActual}
                      options={[
                        { value: 'conservador', label: 'Conservador' },
                        { value: 'base', label: 'Base' },
                        { value: 'optimista', label: 'Optimista' },
                      ]}
                    />
                  </div>
                )}
                <ProyeccionPatrimonialChart
                  evolucionReal={evolucion}
                  planPuntos={puntosPlan}
                  proyeccionPuntos={puntosProyeccion}
                  montoObjetivo={objetivo.monto_usd}
                  fechaLimite={objetivo.fecha_limite}
                  esProyeccionAlcanzable={esProyeccionAlcanzable}
                />
              </Card>
            </>
          ) : null}

          {/* Sensibilidad */}
          {grillaSensibilidad ? (
            <>
              <h3 className="text-[13.5px] font-bold text-app-text mb-2.5 mt-3.5">Sensibilidad: tasa × aporte</h3>
              <SensibilidadGrid
                grilla={grillaSensibilidad.grilla}
                tasas={grillaSensibilidad.tasas}
                aportes={grillaSensibilidad.aportes}
                mesesRestantesAlFinal={objetivo.meses_restantes}
              />
            </>
          ) : null}

          {/* Aportes históricos */}
          <h3 className="text-[13.5px] font-bold text-app-text mb-2.5 mt-3.5">Aportes históricos</h3>
          <Card>
            <AportesChart aportesHistoricos={aportesHistoricos} montoObjetivo={objetivo.monto_usd} />
          </Card>

          {/* Simulador inverso */}
          <div className="mt-3.5">
            <SimuladorInverso
              objetivoMontoCargado={objetivo.monto_usd}
              objetivoFechaLimiteCargada={objetivo.fecha_limite}
              valorInicialCargado={objetivo.valor_actual_usd}
              aporteMensualCargado={objetivo.aporte_mensual_promedio_usd}
              tasaBaseCargada={tasaBaseResuelto.valor}
              tasaBaseSource={tasaBaseResuelto.fuente}
            />
          </div>
        </>
      )}
    </div>
  )
}
