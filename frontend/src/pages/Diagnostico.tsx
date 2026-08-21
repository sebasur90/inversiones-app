import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useInversionesContext } from '../context/InversionesContext'
import { getDiagnostico, type DiagnosticoOut } from '../api'
import { useObjetivoInversion } from '../hooks/useObjetivoInversion'
import ScreenHeader from '../components/layout/ScreenHeader'
import Card from '../components/ui/Card'
import EmptyState from '../components/ui/EmptyState'
import HallazgoCard from '../components/inversiones/HallazgoCard'
import { priorizarHallazgos, evaluarDesviacionPlan } from '../utils/hallazgos'
import { parseApiError, type ParsedApiError } from '../help/errors/apiErrors'
import ErrorBanner from '../help/components/ErrorBanner'
import InfoTooltip from '../help/components/InfoTooltip'

export default function Diagnostico() {
  const navigate = useNavigate()
  const { carteraSeleccionada, loading: contextLoading } = useInversionesContext()
  const [diagnostico, setDiagnostico] = useState<DiagnosticoOut | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<ParsedApiError | null>(null)
  const [expandido, setExpandido] = useState(false)

  const { objetivo } = useObjetivoInversion(carteraSeleccionada)

  useEffect(() => {
    let cancelado = false
    setLoading(true)
    setError(null)
    getDiagnostico(carteraSeleccionada)
      .then(d => {
        if (!cancelado) {
          setDiagnostico(d)
          setError(null)
        }
      })
      .catch(err => {
        if (!cancelado) {
          setDiagnostico(null)
          setError(parseApiError(err))
        }
      })
      .finally(() => {
        if (!cancelado) setLoading(false)
      })
    return () => {
      cancelado = true
    }
  }, [carteraSeleccionada])

  const hallazgos = useMemo(() => {
    if (!diagnostico) return []
    const hallazgoFrontend = evaluarDesviacionPlan(objetivo ?? null)
    return priorizarHallazgos([...diagnostico.hallazgos, ...(hallazgoFrontend ? [hallazgoFrontend] : [])])
  }, [diagnostico, objetivo])

  const visibles = expandido ? hallazgos : hallazgos.slice(0, 5)

  if (contextLoading || loading) {
    return (
      <div className="pb-4">
        <ScreenHeader title="Diagnóstico" onBack={() => navigate('/resumen')} />
        <div className="py-20 text-center text-app-text-dim text-[13px]">Cargando…</div>
      </div>
    )
  }

  if (!diagnostico) {
    return (
      <div className="pb-4">
        <ScreenHeader title="Diagnóstico" onBack={() => navigate('/resumen')} />
        <div className="p-6 max-w-2xl">
          {error ? (
            <ErrorBanner error={error} />
          ) : (
            <EmptyState title="Error al cargar" description="No se pudo cargar el diagnóstico. Intentá de nuevo." />
          )}
        </div>
      </div>
    )
  }

  return (
    <div className="pb-4">
      <ScreenHeader title="Diagnóstico" onBack={() => navigate('/resumen')} />

      <div className="flex flex-col gap-3">
        {/* Health Score Card */}
        <Card className="bg-gradient-to-br from-app-surface to-app-surface-2">
          <div className="mb-1">
            <div className="flex items-center gap-1">
              <div className="salud-title">Salud de cartera</div>
              <InfoTooltip term="diagnostico_salud_cartera" label="" />
            </div>
            <div className="font-display salud-score">
              {diagnostico.salud.score_total !== null ? Math.round(diagnostico.salud.score_total) : '—'}
              <span className="salud-score-divider">/100</span>
            </div>
          </div>

          {diagnostico.salud.score_total !== null && (
            <div className="mt-5 space-y-3">
              {diagnostico.salud.dimensiones.map(dim => {
                const dimensionTermMap: Record<string, keyof typeof import('../help/content').DIAGNOSTICO_HELP> = {
                  rendimiento: 'diagnostico_dimension_rendimiento',
                  diversificacion: 'diagnostico_dimension_diversificacion',
                  riesgo: 'diagnostico_dimension_riesgo',
                  costos: 'diagnostico_dimension_costos',
                }
                const insuficienciaTermMap: Record<string, keyof typeof import('../help/content').DIAGNOSTICO_HELP> = {
                  performance: 'diagnostico_datos_insuficientes_performance',
                  objetivo: 'diagnostico_datos_insuficientes_objetivo',
                }
                const termKey = (dim.estado === 'excluida'
                  ? insuficienciaTermMap[dim.nombre.toLowerCase()]
                  : dimensionTermMap[dim.nombre.toLowerCase()]) as any

                return (
                  <div key={dim.nombre}>
                    <div className="flex items-baseline justify-between mb-1">
                      <div className="flex items-center gap-1">
                        <span className={`dimension-name capitalize ${dim.estado === 'excluida' ? 'text-app-text-dim' : ''}`}>
                          {dim.nombre}
                        </span>
                        {termKey && <InfoTooltip term={termKey} label="" />}
                      </div>
                      <span className={`dimension-score ${dim.estado === 'excluida' ? 'text-app-text-dim' : ''}`}>
                        {dim.score !== null ? Math.round(dim.score) : '—'}
                      </span>
                    </div>
                    <div className="h-2 rounded-full bg-app-surface-2 overflow-hidden mb-1.5">
                      {dim.score !== null ? (
                        <div
                          className={`h-full rounded-full transition-all ${
                            dim.score >= 70
                              ? 'bg-app-teal'
                              : dim.score >= 40
                                ? 'bg-app-gold'
                                : 'bg-app-coral'
                          }`}
                          style={{ width: `${Math.max(5, dim.score)}%` }}
                        />
                      ) : (
                        <div className="h-full bg-app-text-faint opacity-20" />
                      )}
                    </div>
                    <div className={`dimension-detail ${dim.estado === 'excluida' ? 'text-app-text-dim' : ''}`}>
                      {dim.detalle}
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </Card>

        {/* Findings List */}
        {hallazgos.length === 0 ? (
          <EmptyState title="Sin hallazgos" description="No detectamos puntos de atención en esta cartera." />
        ) : (
          <div>
            <div className="text-[13.5px] font-bold text-app-text mb-2.5">
              {hallazgos.length} hallazgo{hallazgos.length !== 1 ? 's' : ''}
            </div>
            {visibles.map(h => (
              <HallazgoCard
                key={h.tipo}
                item={h}
                onClick={() => {
                  navigate(h.pantalla)
                }}
              />
            ))}
            {hallazgos.length > 5 && (
              <button
                onClick={() => setExpandido(v => !v)}
                className="w-full text-center py-2.5 text-[12.5px] font-semibold text-app-text-dim hover:text-app-text transition-colors"
              >
                {expandido ? 'Ver menos' : `Ver más (${hallazgos.length - 5})`}
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
