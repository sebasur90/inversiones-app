import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getCicloEfectividad, type CicloEfectividadEstado, type CicloEfectividadStats, type CicloTipo } from '../../api'
import { qk } from '../../api/queryClient'
import InfoTooltip from '../../help/components/InfoTooltip'
import { fechaCorta } from '../../utils/fechas'
import QueryBoundary from '../ui/QueryBoundary'
import Segmented from '../ui/Segmented'
import BadgeCuadrante from './BadgeCuadrante'
import PieDatos from './PieDatos'
import { TIPOS_ANALISIS, fmtNum, fmtPct, tonoDe } from './constantes'

type Alcance = 'grupo' | 'tipo'
type Vista = 'estado' | 'confirmar'

const HORIZONTES: { value: string; label: string }[] = [
  { value: '4', label: '4 sem.' },
  { value: '13', label: '13 sem.' },
  { value: '26', label: '26 sem.' },
]

const TONO: Record<string, string> = { pos: 'text-app-pos', neg: 'text-app-neg' }

/** Diferencia en puntos porcentuales de rendimiento relativo (la mediana del estado menos la de cualquier semana). */
function fmtPuntos(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return '—'
  return `${v > 0 ? '+' : ''}${fmtNum(v * 100, 1)} pp`
}

function Dato({ etiqueta, valor, tono }: { etiqueta: string; valor: string; tono?: 'pos' | 'neg' }) {
  return (
    <div>
      <div className="text-label text-app-text-faint">{etiqueta}</div>
      <div className={`font-mono tabular-nums text-strong font-bold ${tono ? TONO[tono] : 'text-app-text'}`}>{valor}</div>
    </div>
  )
}

function Resumen({ s, conBase }: { s: CicloEfectividadStats; conBase: boolean }) {
  if (!s.suficiente) {
    return (
      <p className="text-caption text-app-text-dim">
        {s.n === 0
          ? 'Sin casos con este horizonte.'
          : `Hay ${s.episodios} ${s.episodios === 1 ? 'episodio' : 'episodios'} (${s.n} semanas): no alcanza para resumir. Hacen falta al menos 5.`}
      </p>
    )
  }
  return (
    <div className="flex flex-col gap-1.5">
      <div className="grid grid-cols-3 gap-2">
        <Dato etiqueta="Mediana" valor={fmtPct(s.mediana)} tono={tonoDe(s.mediana)} />
        <Dato etiqueta="Rango típico" valor={`${fmtPct(s.p25, 0)} a ${fmtPct(s.p75, 0)}`} />
        <Dato etiqueta="Le ganó a la ref." valor={fmtPct((s.positivos_pct ?? 0) / 100, 0, false)} />
      </div>
      <p className="text-label text-app-text-faint">
        {s.episodios} episodios · {s.n} semanas
        {conBase && s.mediana_vs_base != null && (
          <>
            {' · '}vs. cualquier semana: <span className={`font-semibold ${TONO[tonoDe(s.mediana_vs_base) ?? ''] ?? 'text-app-text-dim'}`}>{fmtPuntos(s.mediana_vs_base)}</span>
          </>
        )}
      </p>
    </div>
  )
}

function TarjetaEstado({ e, h, vista }: { e: CicloEfectividadEstado; h: string; vista: Vista }) {
  const s = (vista === 'estado' ? e.horizontes : e.al_confirmar)[h]
  return (
    <li className="rounded-xl border border-app-border bg-app-surface-2 px-3 py-2.5">
      <div className="flex flex-wrap items-center justify-between gap-2 mb-1.5">
        <BadgeCuadrante cuadrante={e.cuadrante} />
        <span className="text-label text-app-text-faint">
          {vista === 'estado' ? `${e.episodios} episodios · ${e.semanas} semanas en el estado` : `${e.cambios_a_este_estado} cambios confirmados hacia este estado`}
        </span>
      </div>
      {s ? <Resumen s={s} conBase /> : null}
    </li>
  )
}

/**
 * Qué pasó con el rendimiento relativo del grupo después de estar en cada estado. Describe el pasado: siempre
 * junto a la base (cualquier semana) y al número de episodios, y sin ninguna cifra cuando los episodios no alcanzan.
 */
export default function EfectividadEstados({ grupoId, tipo, benchmark }: { grupoId: string; tipo: CicloTipo; benchmark: string | null }) {
  const [alcance, setAlcance] = useState<Alcance>('grupo')
  const [vista, setVista] = useState<Vista>('estado')
  const [horizonte, setHorizonte] = useState('13')
  const etiquetaTipo = TIPOS_ANALISIS.find(t => t.value === tipo)?.label.toLowerCase() ?? 'grupos'

  const query = useQuery({
    queryKey: qk.de('ciclos-efectividad', grupoId, alcance, benchmark),
    queryFn: () => getCicloEfectividad(grupoId, { alcance, benchmark }),
  })
  const d = query.data
  const r = d?.resultado

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-col gap-2">
        <Segmented
          options={[
            { value: 'grupo' as Alcance, label: 'Este grupo' },
            { value: 'tipo' as Alcance, label: `Todos los ${etiquetaTipo}` },
          ]}
          value={alcance}
          onChange={setAlcance}
        />
        <Segmented
          options={[
            { value: 'estado' as Vista, label: 'Mientras está en el estado' },
            { value: 'confirmar' as Vista, label: 'Al confirmarse el cambio' },
          ]}
          value={vista}
          onChange={setVista}
        />
        <Segmented options={HORIZONTES} value={horizonte} onChange={setHorizonte} />
      </div>

      <QueryBoundary isLoading={query.isLoading} error={query.error} onRetry={() => void query.refetch()} fallback={<p className="text-caption text-app-text-dim">Calculando…</p>}>
        {!d || !r ? (
          <p className="text-caption text-app-text-dim">{d?.motivo ?? 'Sin datos suficientes para este análisis.'}</p>
        ) : (
          <>
            <p className="text-caption text-app-text-dim">
              Rendimiento relativo del grupo contra {alcance === 'grupo' ? (d.benchmark?.nombre ?? 'su referencia') : 'la referencia de cada uno'} en las{' '}
              <b className="text-app-text">{horizonte} semanas siguientes</b>, con datos de {r.desde ? fechaCorta(r.desde) : '—'} a {r.hasta ? fechaCorta(r.hasta) : '—'}{' '}
              <InfoTooltip term="ciclos_efectividad" />
            </p>

            <div className="rounded-xl border border-app-border px-3 py-2.5">
              <div className="text-label font-bold uppercase text-app-text-faint mb-1.5">
                Cualquier semana (base) <InfoTooltip term="ciclos_base_semanas" />
              </div>
              {r.base[horizonte] ? <Resumen s={r.base[horizonte]} conBase={false} /> : null}
            </div>

            <ul className="flex flex-col gap-2">
              {r.por_estado.map(e => (
                <TarjetaEstado key={e.cuadrante} e={e} h={horizonte} vista={vista} />
              ))}
            </ul>

            <p className="text-label text-app-text-faint">
              Un <InfoTooltip term="ciclos_episodio" label="episodio" /> es una racha continua en el estado. {d.lectura}
            </p>
            {alcance === 'tipo' && (
              <details className="text-label text-app-text-dim">
                <summary className="cursor-pointer font-semibold">Grupos incluidos ({d.grupos.filter(g => g.semanas > 0).length} de {d.grupos.length})</summary>
                <ul className="mt-1 space-y-0.5">
                  {d.grupos.map(g => (
                    <li key={g.id}>
                      {g.nombre}: {g.semanas > 0 ? `${g.semanas} semanas` : (g.motivo ?? 'sin datos')}
                    </li>
                  ))}
                </ul>
              </details>
            )}
            <PieDatos meta={d.meta} />
          </>
        )}
      </QueryBoundary>
    </div>
  )
}
