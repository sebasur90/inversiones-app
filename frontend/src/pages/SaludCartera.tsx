import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { useInversionesContext } from '../context/InversionesContext'
import { getSaludCartera, type SaludDimension, type SaludIndicador, type EstadoSalud } from '../api'
import type { HelpKey } from '../help/content/index'
import { qk } from '../api/queryClient'
import { formatARS, formatUSD } from '../utils'
import ScreenHeader from '../components/layout/ScreenHeader'
import Card from '../components/ui/Card'
import MetricTile from '../components/ui/MetricTile'
import Semaforo from '../components/ui/Semaforo'
import EmptyState from '../components/ui/EmptyState'
import QueryBoundary from '../components/ui/QueryBoundary'
import SkeletonPantalla from '../components/ui/Skeleton'
import InfoTooltip from '../help/components/InfoTooltip'
import ObservacionCard from '../components/inversiones/ObservacionCard'
import { Icon } from '../components/icons/Icons'
import type { Nivel } from '../utils/niveles'

const NIVEL_POR_ESTADO: Record<Exclude<EstadoSalud, 'sin_datos'>, Nivel> = {
  normal: 'bien',
  atencion: 'atencion',
  revisar: 'riesgo',
}

function indicadorTexto(ind: SaludIndicador, esARS: boolean, formatMoneda: (v: number) => string): string {
  if (ind.texto) return ind.texto
  const v = esARS ? ind.valor_ars : ind.valor_usd
  return v != null ? formatMoneda(v) : '—'
}

function DimensionRow({ dim, abierta, onToggle }: { dim: SaludDimension; abierta: boolean; onToggle: () => void }) {
  const navigate = useNavigate()

  return (
    <div className="border-b border-app-border last:border-b-0 py-3">
      <button onClick={onToggle} className="w-full flex items-center justify-between gap-2 text-left" aria-expanded={abierta}>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1 mb-0.5">
            <span className="dimension-name">{dim.nombre}</span>
            <InfoTooltip term={dim.ayuda as HelpKey} label="" />
          </div>
          {dim.estado === 'sin_datos' ? (
            <span className="text-label font-semibold text-app-text-dim">{dim.etiqueta}</span>
          ) : (
            <Semaforo nivel={NIVEL_POR_ESTADO[dim.estado]} etiqueta={dim.etiqueta} />
          )}
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          <span className="dimension-detail text-right max-w-[140px]">{dim.valor}</span>
          <Icon name="chevron" className={`w-3.5 h-3.5 text-app-text-dim shrink-0 transition-transform ${abierta ? 'rotate-0' : '-rotate-90'}`} />
        </div>
      </button>

      {abierta && (
        <div className="mt-2.5 flex flex-col gap-2">
          <div className="text-caption text-app-text-dim">{dim.explicacion}</div>
          <div className="bg-app-surface-2 rounded-xl p-2.5">
            <div className="text-label font-bold uppercase tracking-wide text-app-text-faint mb-1">¿Cómo se decide?</div>
            <div className="text-caption text-app-text-dim">{dim.regla}</div>
          </div>
          <div className="text-label text-app-text-faint">Fuente: {dim.fuente}</div>
          <button
            onClick={() => navigate(dim.pantalla)}
            className="self-start text-caption font-bold text-app-accent"
          >
            Ver en detalle →
          </button>
        </div>
      )}
    </div>
  )
}

export default function SaludCartera() {
  const { carteraSeleccionada, monedaSeleccionada, loading: contextLoading } = useInversionesContext()
  const [dimensionAbierta, setDimensionAbierta] = useState<string | null>(null)

  const esARS = monedaSeleccionada === 'ARS'
  const formatMoneda = esARS ? formatARS : formatUSD

  const saludQuery = useQuery({
    queryKey: qk.de('salud', carteraSeleccionada),
    queryFn: () => getSaludCartera(carteraSeleccionada),
  })
  const salud = saludQuery.data ?? null

  return (
    <div className="pb-4">
      <ScreenHeader title="Salud de cartera" />

      <QueryBoundary isLoading={contextLoading || saludQuery.isLoading} error={saludQuery.error} onRetry={() => void saludQuery.refetch()}>
        {!salud ? (
          <SkeletonPantalla />
        ) : (
          <div className="flex flex-col gap-3">
            {/* Sección 1: Resumen general */}
            <div>
              <div className="flex items-center gap-1 mb-2.5">
                <h3 className="text-body font-bold text-app-text">Resumen general</h3>
                <InfoTooltip term="salud_que_es" label="" />
              </div>
              <div className="grid grid-cols-2 gap-2">
                {salud.indicadores.map(ind => (
                  <MetricTile
                    key={ind.clave}
                    label={ind.nombre}
                    value={indicadorTexto(ind, esARS, formatMoneda)}
                    infoTerm={ind.ayuda as HelpKey}
                  />
                ))}
              </div>
            </div>

            {(salud.exposicion_moneda.length > 0 || salud.exposicion_tipo.length > 0) && (
              <Card>
                {salud.exposicion_moneda.length > 0 && (
                  <div className="mb-3">
                    <div className="flex items-center gap-1 mb-1.5">
                      <span className="text-label font-bold uppercase tracking-wide text-app-text-faint">Exposición ARS / USD</span>
                      <InfoTooltip term="salud_exposicion_moneda" label="" />
                    </div>
                    <div className="h-2.5 rounded-full bg-app-surface-2 overflow-hidden flex">
                      {salud.exposicion_moneda.map(item => (
                        <div
                          key={item.etiqueta}
                          className={item.etiqueta === 'ARS' ? 'bg-app-cyan h-full' : 'bg-app-accent h-full'}
                          style={{ width: `${item.porcentaje}%` }}
                          title={`${item.etiqueta}: ${item.porcentaje.toFixed(1)}%`}
                        />
                      ))}
                    </div>
                    <div className="flex justify-between mt-1 text-label text-app-text-dim">
                      {salud.exposicion_moneda.map(item => (
                        <span key={item.etiqueta}>{item.etiqueta} {item.porcentaje.toFixed(1)}%</span>
                      ))}
                    </div>
                  </div>
                )}

                {salud.exposicion_tipo.length > 0 && (
                  <div>
                    <div className="flex items-center gap-1 mb-1.5">
                      <span className="text-label font-bold uppercase tracking-wide text-app-text-faint">Exposición por tipo de instrumento</span>
                      <InfoTooltip term="salud_exposicion_tipo" label="" />
                    </div>
                    <div className="flex flex-col gap-1.5">
                      {salud.exposicion_tipo.map(item => (
                        <div key={item.etiqueta} className="flex justify-between text-caption">
                          <span className="text-app-text">{item.etiqueta}</span>
                          <span className="font-mono text-app-text-dim">{item.porcentaje.toFixed(1)}%</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </Card>
            )}

            {/* Sección 2: Estado por dimensión */}
            <div>
              <div className="flex items-center gap-1 mb-2.5">
                <h3 className="text-body font-bold text-app-text">Estado por dimensión</h3>
                <InfoTooltip term="salud_estados" label="" />
              </div>
              <Card>
                {salud.dimensiones.map(dim => (
                  <DimensionRow
                    key={dim.clave}
                    dim={dim}
                    abierta={dimensionAbierta === dim.clave}
                    onToggle={() => setDimensionAbierta(v => (v === dim.clave ? null : dim.clave))}
                  />
                ))}
              </Card>
            </div>

            {/* Sección 3: Cosas para revisar */}
            <div>
              <div className="text-body font-bold text-app-text mb-2.5">
                {salud.observaciones.length === 0
                  ? 'Cosas para revisar'
                  : `${salud.observaciones.length} cosa${salud.observaciones.length !== 1 ? 's' : ''} para revisar`}
              </div>
              {salud.observaciones.length === 0 ? (
                <EmptyState title="Todo en orden" description="No detectamos ninguna observación en esta cartera." />
              ) : (
                salud.observaciones.map(obs => <ObservacionCard key={obs.id} item={obs} />)
              )}
            </div>

            <div className="text-label text-app-text-faint text-center px-4">
              Cálculo en USD a precios de hoy · fuente de verdad: tu Sheet/Excel ·{' '}
              {salud.resumen.n_revisar} para revisar, {salud.resumen.n_atencion} en atención
            </div>
          </div>
        )}
      </QueryBoundary>
    </div>
  )
}
