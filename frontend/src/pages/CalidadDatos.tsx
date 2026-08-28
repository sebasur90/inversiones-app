import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import ScreenHeader from '../components/layout/ScreenHeader'
import { getCalidadDatos } from '../api'
import type { CalidadDatosOut, SyncIssueOut } from '../api'
import CalidadIssueRow from '../components/inversiones/CalidadIssueRow'
import Sparkline from '../components/charts/Sparkline'
import { parseApiError, type ParsedApiError } from '../help/errors/apiErrors'
import ErrorBanner from '../help/components/ErrorBanner'
import InfoTooltip from '../help/components/InfoTooltip'
import { useInversionesContext } from '../context/InversionesContext'

export default function CalidadDatos() {
  const { syncVersion } = useInversionesContext()
  const navigate = useNavigate()
  const [calidad, setCalidad] = useState<CalidadDatosOut | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<ParsedApiError | null>(null)

  useEffect(() => {
    const fetch = async () => {
      try {
        const data = await getCalidadDatos()
        setCalidad(data)
      } catch (err) {
        setError(parseApiError(err))
      } finally {
        setLoading(false)
      }
    }
    fetch()
  }, [syncVersion])

  if (loading) {
    return (
      <>
        <ScreenHeader title="Calidad de datos" onBack={() => navigate('/resumen')} />
        <div className="flex items-center justify-center h-64 text-app-text-dim">Cargando...</div>
      </>
    )
  }

  if (error || !calidad) {
    return (
      <>
        <ScreenHeader title="Calidad de datos" onBack={() => navigate('/resumen')} />
        <div className="p-6 max-w-2xl">
          <ErrorBanner error={error ?? { message: 'No pudimos cargar los datos de calidad.' }} />
        </div>
      </>
    )
  }

  const { ultimo_sync, issues, issues_por_tab, historial, reglas_recurrentes } = calidad

  const sevColor = (s: string) =>
    s === 'critico' ? 'text-app-coral' : s === 'advertencia' ? 'text-app-gold' : 'text-app-text-dim'
  const sevIcon = (s: string) => (s === 'critico' ? '🔴' : s === 'advertencia' ? '🟡' : 'ℹ️')

  const scores = historial.map(h => h.health_score)
  const scoreDelta =
    scores.length >= 2 ? scores[scores.length - 1] - scores[scores.length - 2] : null

  return (
    <>
      <ScreenHeader title="Calidad de datos" onBack={() => navigate('/resumen')} />
      <div className="p-6 max-w-2xl">
        {ultimo_sync && (
          <div className="mb-6 p-4 bg-app-surface border border-app-border rounded-2xl">
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-baseline gap-1">
                <div className="text-[42px] font-display font-semibold text-app-text">
                  {ultimo_sync.health_score}
                  <span className="text-[20px] text-app-text-dim ml-1">/100</span>
                </div>
                <InfoTooltip term="calidaddatos_health_score" />
              </div>
            </div>
            <div className="text-[13px] text-app-text-dim">
              Última sincronización: {new Date(ultimo_sync.timestamp).toLocaleString()}
              <br />
              Tiempo: {ultimo_sync.duration_ms}ms
            </div>
            {ultimo_sync.resultado !== 'ok' && (
              <div className="mt-2 text-[12px]">
                {ultimo_sync.filas_error > 0 && (
                  <div className="text-app-coral flex items-center gap-1">
                    🔴 {ultimo_sync.filas_error} error(es) crítico(s)
                    <InfoTooltip term="calidaddatos_filas_error" />
                  </div>
                )}
                {ultimo_sync.filas_advertencia > 0 && (
                  <div className="text-app-gold flex items-center gap-1">
                    🟡 {ultimo_sync.filas_advertencia} advertencia(s)
                    <InfoTooltip term="calidaddatos_filas_advertencia" />
                  </div>
                )}
              </div>
            )}

            {historial.length >= 2 && (
              <div className="mt-4 pt-3 border-t border-app-border">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-[11px] uppercase tracking-wide text-app-text-faint">
                    Health score · últimos {historial.length} syncs
                  </span>
                  {scoreDelta !== null && (
                    <span
                      className={`text-[11px] font-mono tabular-nums ${
                        scoreDelta > 0 ? 'text-app-teal' : scoreDelta < 0 ? 'text-app-coral' : 'text-app-text-dim'
                      }`}
                    >
                      {scoreDelta > 0 ? '+' : ''}
                      {scoreDelta} vs. sync previo
                    </span>
                  )}
                </div>
                <Sparkline
                  data={scores}
                  color={
                    ultimo_sync.health_score >= 80
                      ? '#4bbf9a'
                      : ultimo_sync.health_score >= 50
                        ? '#d8b14a'
                        : '#e0685f'
                  }
                />
                <div className="flex justify-between text-[10px] text-app-text-faint mt-0.5 tabular-nums">
                  <span>{new Date(historial[0].timestamp).toLocaleDateString()}</span>
                  <span>{scores[0]} → {scores[scores.length - 1]}</span>
                  <span>{new Date(historial[historial.length - 1].timestamp).toLocaleDateString()}</span>
                </div>
              </div>
            )}
          </div>
        )}

        {reglas_recurrentes.length > 0 && (
          <div className="mb-6">
            <div className="text-[14px] font-semibold text-app-text mb-2">
              Reglas que se repiten ({reglas_recurrentes.length})
            </div>
            <div className="text-[12px] text-app-text-dim mb-3">
              Aparecieron en 2 o más de los últimos {calidad.total_syncs} syncs — conviene
              corregirlas en el Sheet en vez de revisarlas cada vez.
            </div>
            <div className="flex flex-col gap-2">
              {reglas_recurrentes.map(r => (
                <div
                  key={r.regla}
                  className="p-3 bg-app-surface-2 border border-app-border rounded-xl"
                >
                  <div className="flex items-center justify-between gap-2 mb-1">
                    <span className={`text-[12.5px] font-semibold ${sevColor(r.severidad)}`}>
                      {sevIcon(r.severidad)} {r.tab} · {r.regla}
                    </span>
                    <span className="text-[11px] text-app-text-dim shrink-0 tabular-nums">
                      {r.apariciones}/{calidad.total_syncs} syncs
                      {!r.en_ultimo_sync && ' · no en el último'}
                    </span>
                  </div>
                  <div className="text-[11.5px] text-app-text-dim">{r.mensaje_muestra}</div>
                </div>
              ))}
            </div>
          </div>
        )}

        {issues.length === 0 && ultimo_sync ? (
          <div className="p-6 text-center bg-app-surface-2 rounded-2xl">
            <div className="text-[16px] font-semibold text-app-text mb-1">✓ Sin problemas detectados</div>
            <div className="text-[13px] text-app-text-dim">Los datos se sincronizaron correctamente</div>
          </div>
        ) : !ultimo_sync ? (
          <div className="p-6 text-center bg-app-surface-2 rounded-2xl">
            <div className="text-[16px] font-semibold text-app-text mb-1">⚙️ Todavía no sincronizaste</div>
            <div className="text-[13px] text-app-text-dim">Haz tu primer sync para ver el estado de calidad</div>
          </div>
        ) : (
          <div>
            <div className="text-[14px] font-semibold text-app-text mb-4">Problemas encontrados ({issues.length})</div>
            {Object.entries(issues_por_tab).map(([tab, tab_issues]) => (
              <div key={tab} className="mb-6">
                <div className="text-[13px] font-semibold text-app-text mb-2 uppercase tracking-wide">{tab}</div>
                <div className="flex flex-col gap-2">
                  {tab_issues.map((issue, idx) => (
                    <CalidadIssueRow key={`${tab}-${idx}`} issue={issue} />
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </>
  )
}
