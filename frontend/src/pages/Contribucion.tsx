import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useInversionesContext } from '../context/InversionesContext'
import {
  getContribucion,
  getCorrelaciones,
  type ContribucionOut,
  type ContribucionItem,
  type CorrelacionesOut,
  type UniversoCorrelacion,
} from '../api'
import { formatPct } from '../utils'
import ScreenHeader from '../components/layout/ScreenHeader'
import EmptyState from '../components/ui/EmptyState'
import Segmented from '../components/ui/Segmented'
import InfoTerm from '../components/ui/InfoTerm'
import MetricTile from '../components/ui/MetricTile'
import CorrelacionMatriz from '../components/charts/CorrelacionMatriz'
import { Icon } from '../components/icons/Icons'

function toneClass(v: number | null | undefined): string {
  if (v == null) return 'text-app-text'
  return v >= 0 ? 'text-app-teal' : 'text-app-coral'
}

function ContribucionBar({ item, maxAbs }: { item: ContribucionItem; maxAbs: number }) {
  const ancho = maxAbs > 0 ? (Math.abs(item.contribucion_pct) / maxAbs) * 100 : 0
  return (
    <div>
      <div className="flex justify-between items-baseline text-[11.5px] mb-1">
        <span className="text-app-text">{item.etiqueta}</span>
        <span className={`font-mono font-bold tabular-nums ${toneClass(item.contribucion_pct)}`}>
          {formatPct(item.contribucion_pct)}
        </span>
      </div>
      <div className="h-1.5 rounded-full bg-app-surface-2 overflow-hidden mb-1">
        <div
          className={`h-full rounded-full ${item.contribucion_pct >= 0 ? 'bg-app-teal' : 'bg-app-coral'}`}
          style={{ width: `${ancho}%` }}
        />
      </div>
      <div className="flex justify-between text-[10px] text-app-text-dim">
        <span>Peso prom.: {formatPct(item.peso_promedio_pct)}</span>
        <span>Rent.: {item.rentabilidad_pct == null ? '—' : formatPct(item.rentabilidad_pct)}</span>
      </div>
    </div>
  )
}

function etiquetaHhi(hhi: number | null): string | undefined {
  if (hhi == null) return undefined
  if (hhi < 1500) return 'Poco concentrado'
  if (hhi <= 2500) return 'Moderadamente concentrado'
  return 'Muy concentrado'
}

const OPCIONES_UNIVERSO: { value: UniversoCorrelacion; label: string }[] = [
  { value: 'tenencias', label: 'Tenencias actuales' },
  { value: 'todos', label: 'Todos con precio' },
]

export default function Contribucion() {
  const navigate = useNavigate()
  const { carteraSeleccionada } = useInversionesContext()

  const [contribucion, setContribucion] = useState<ContribucionOut | null>(null)
  const [loadingContribucion, setLoadingContribucion] = useState(true)
  const [ejeContribucion, setEjeContribucion] = useState<string | null>(null)
  const [ejeConcentracion, setEjeConcentracion] = useState<string | null>(null)

  const [correlaciones, setCorrelaciones] = useState<CorrelacionesOut | null>(null)
  const [loadingCorrelaciones, setLoadingCorrelaciones] = useState(true)
  const [universo, setUniverso] = useState<UniversoCorrelacion>('tenencias')

  useEffect(() => {
    let cancelado = false
    setLoadingContribucion(true)
    getContribucion(carteraSeleccionada)
      .then(data => {
        if (!cancelado) setContribucion(data)
      })
      .catch(() => {
        if (!cancelado) setContribucion(null)
      })
      .finally(() => {
        if (!cancelado) setLoadingContribucion(false)
      })
    return () => {
      cancelado = true
    }
  }, [carteraSeleccionada])

  useEffect(() => {
    let cancelado = false
    setLoadingCorrelaciones(true)
    getCorrelaciones(carteraSeleccionada, universo)
      .then(data => {
        if (!cancelado) setCorrelaciones(data)
      })
      .catch(() => {
        if (!cancelado) setCorrelaciones(null)
      })
      .finally(() => {
        if (!cancelado) setLoadingCorrelaciones(false)
      })
    return () => {
      cancelado = true
    }
  }, [carteraSeleccionada, universo])

  const ejeActivoContribucion =
    contribucion?.contribucion.find(e => e.eje === ejeContribucion) ?? contribucion?.contribucion[0] ?? null
  const itemsContribucion = ejeActivoContribucion
    ? [...ejeActivoContribucion.items].sort((a, b) => Math.abs(b.contribucion_pct) - Math.abs(a.contribucion_pct))
    : []
  const maxAbsContribucion = Math.max(1e-9, ...itemsContribucion.map(i => Math.abs(i.contribucion_pct)))

  const ejeActivoConcentracion =
    contribucion?.concentracion.find(e => e.eje === ejeConcentracion) ?? contribucion?.concentracion[0] ?? null

  return (
    <div className="pb-4">
      <ScreenHeader title="Contribución y concentración" onBack={() => navigate(-1)} />

      <div className="flex flex-wrap gap-x-4 gap-y-1 mb-4">
        <button onClick={() => navigate('/exposicion')} className="inline-flex items-center gap-1 text-[11px] font-semibold text-app-text-dim">
          <Icon name="pie" className="w-3.5 h-3.5" /> Ver exposición
        </button>
        <button onClick={() => navigate('/riesgo')} className="inline-flex items-center gap-1 text-[11px] font-semibold text-app-text-dim">
          <Icon name="alert" className="w-3.5 h-3.5" /> Ver métricas de riesgo
        </button>
      </div>

      <h3 className="text-[13.5px] font-bold text-app-text mb-2.5">
        <InfoTerm term="contribucion" label="Contribución al rendimiento" />
      </h3>
      {loadingContribucion ? (
        <div className="py-10 text-center text-app-text-dim text-[13px]">Cargando…</div>
      ) : !contribucion || contribucion.contribucion.length === 0 ? (
        <EmptyState title="Sin datos" description="No hay movimientos suficientes para calcular contribución." />
      ) : (
        <>
          <div className="mb-3">
            <Segmented
              options={contribucion.contribucion.map(e => ({ value: e.eje, label: e.eje }))}
              value={ejeActivoContribucion?.eje ?? contribucion.contribucion[0].eje}
              onChange={setEjeContribucion}
            />
          </div>
          <div className="flex flex-col gap-3 mb-6">
            {itemsContribucion.map(item => (
              <ContribucionBar key={item.etiqueta} item={item} maxAbs={maxAbsContribucion} />
            ))}
          </div>
        </>
      )}

      <h3 className="text-[13.5px] font-bold text-app-text mb-2.5">Concentración</h3>
      {loadingContribucion ? null : !contribucion || contribucion.concentracion.length === 0 ? (
        <EmptyState title="Sin datos" description="No hay posiciones clasificadas para calcular concentración." />
      ) : (
        <>
          <div className="mb-3">
            <Segmented
              options={contribucion.concentracion.map(e => ({ value: e.eje, label: e.eje }))}
              value={ejeActivoConcentracion?.eje ?? contribucion.concentracion[0].eje}
              onChange={setEjeConcentracion}
            />
          </div>
          {ejeActivoConcentracion && (
            <div className="grid grid-cols-2 gap-2 mb-6">
              <MetricTile
                label="HHI"
                infoTerm="hhi"
                value={ejeActivoConcentracion.hhi != null ? ejeActivoConcentracion.hhi.toFixed(0) : '—'}
                sub={etiquetaHhi(ejeActivoConcentracion.hhi)}
                insuficiente={ejeActivoConcentracion.estado !== 'ok'}
              />
              <MetricTile
                label="N efectivo"
                infoTerm="hhi"
                value={ejeActivoConcentracion.effective_n != null ? ejeActivoConcentracion.effective_n.toFixed(1) : '—'}
                sub={`${ejeActivoConcentracion.n_componentes} componente${ejeActivoConcentracion.n_componentes === 1 ? '' : 's'}`}
                insuficiente={ejeActivoConcentracion.estado !== 'ok'}
              />
            </div>
          )}
        </>
      )}

      <h3 className="text-[13.5px] font-bold text-app-text mb-2.5">
        <InfoTerm term="correlacion" label="Correlación entre activos" />
      </h3>
      <div className="mb-3">
        <Segmented options={OPCIONES_UNIVERSO} value={universo} onChange={setUniverso} />
      </div>
      {loadingCorrelaciones ? (
        <div className="py-10 text-center text-app-text-dim text-[13px]">Cargando…</div>
      ) : !correlaciones || correlaciones.n_tickers < 2 ? (
        <EmptyState
          title="Sin suficientes activos"
          description="Se necesitan al menos 2 tickers con precio cargado para calcular correlaciones."
        />
      ) : (
        <>
          {correlaciones.advertencia_historial_corto && (
            <div className="mb-3 bg-app-gold-soft rounded-xl px-3 py-2.5 flex items-start gap-2">
              <Icon name="alert" className="w-3.5 h-3.5 shrink-0 mt-0.5 text-app-gold" />
              <span className="text-[11.5px] text-app-text">
                La mayoría de los pares todavía no tienen suficiente historial de precios (mínimo 6 meses solapados) para
                calcular una correlación confiable.
              </span>
            </div>
          )}
          <CorrelacionMatriz data={correlaciones} />
        </>
      )}
    </div>
  )
}
