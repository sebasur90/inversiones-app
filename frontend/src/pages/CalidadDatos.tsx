import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import ScreenHeader from '../components/layout/ScreenHeader'
import { getCalidadDatos } from '../api'
import type { CalidadDatosOut, SyncIssueOut } from '../api'
import CalidadIssueRow from '../components/inversiones/CalidadIssueRow'
import { parseApiError, type ParsedApiError } from '../help/errors/apiErrors'
import ErrorBanner from '../help/components/ErrorBanner'
import InfoTooltip from '../help/components/InfoTooltip'

export default function CalidadDatos() {
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
  }, [])

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

  const { ultimo_sync, issues, issues_por_tab } = calidad

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
