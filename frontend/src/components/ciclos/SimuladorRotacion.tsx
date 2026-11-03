import { useMemo, useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { simularRotacion, type CicloGrupoCatalogo, type CiclosCarteraOut, type CiclosSimulacionOut } from '../../api'
import { parseApiError } from '../../help/errors/apiErrors'
import ErrorBanner from '../../help/components/ErrorBanner'
import InfoTooltip from '../../help/components/InfoTooltip'
import { useFormatoFijo } from '../../hooks/useFormatoMoneda'
import Button from '../ui/Button'
import Segmented from '../ui/Segmented'
import BadgeCuadrante from './BadgeCuadrante'
import { fmtNum } from './constantes'

const NIVEL: Record<string, string> = { revisar: 'text-app-neg', atencion: 'text-app-warn', info: 'text-app-text-dim' }
const NIVEL_TXT: Record<string, string> = { revisar: 'Revisar', atencion: 'Atención', info: 'Dato' }

interface Props {
  cartera: string | null
  exposicion: CiclosCarteraOut
  grupos: CicloGrupoCatalogo[]
  benchmark: string | null
  inicial?: { origen?: string; destino?: string }
}

/**
 * «¿Qué pasaría si traslado un X % de mi cartera de un grupo a otro?». Simulación en memoria: no escribe movimientos,
 * no modifica la cartera ni estima rendimientos futuros.
 */
export default function SimuladorRotacion({ cartera, exposicion, grupos, benchmark, inicial }: Props) {
  const { monto } = useFormatoFijo('USD')
  const origenes = useMemo(() => {
    const m = new Map<string, { id: string; nombre: string; pct: number }>()
    for (const d of exposicion.dimensiones) for (const i of d.items) if (i.grupo_id && i.valor_usd > 0) m.set(i.grupo_id, { id: i.grupo_id, nombre: i.grupo_nombre ?? i.etiqueta, pct: i.porcentaje })
    for (const s of exposicion.superpuestas) if (s.porcentaje > 0) m.set(s.grupo_id, { id: s.grupo_id, nombre: s.nombre, pct: s.porcentaje })
    return [...m.values()].sort((a, b) => b.pct - a.pct)
  }, [exposicion])
  const destinos = useMemo(() => grupos.filter(g => g.activo && !g.es_benchmark).sort((a, b) => a.nombre.localeCompare(b.nombre, 'es-AR')), [grupos])

  const [origen, setOrigen] = useState(inicial?.origen ?? origenes[0]?.id ?? '')
  const [destino, setDestino] = useState(inicial?.destino ?? '')
  const [pct, setPct] = useState('5')
  const [eje, setEje] = useState('Sector')

  const m = useMutation<CiclosSimulacionOut, unknown, void>({
    mutationFn: () => simularRotacion(cartera, { origen, destino, pct: Number(pct.replace(',', '.')), benchmark }),
  })
  const sim = m.data
  const maxPct = origenes.find(o => o.id === origen)?.pct ?? 100
  const listo = !!origen && !!destino && origen !== destino && Number(pct.replace(',', '.')) > 0

  const campo = 'h-11 w-full rounded-xl bg-app-surface border border-app-border px-3 text-body text-app-text'
  return (
    <div className="flex flex-col gap-3">
      <p className="text-caption text-app-text-dim">
        Probá cómo cambiaría la mezcla de tu cartera si trasladaras un porcentaje de un grupo a otro. No guarda nada ni modifica tus posiciones. Más sobre el{' '}
        <InfoTooltip term="ciclos_simulador" label="simulador" />.
      </p>
      {origenes.length === 0 ? (
        <p className="text-caption text-app-text-faint">Tu cartera no tiene exposición a ningún grupo del catálogo: no hay nada para trasladar.</p>
      ) : (
        <>
          <label className="flex flex-col gap-1 text-label font-bold uppercase text-app-text-faint">
            Desde (grupo en tu cartera)
            <select className={campo} value={origen} onChange={e => setOrigen(e.target.value)}>
              {origenes.map(o => (
                <option key={o.id} value={o.id}>
                  {o.nombre} — {fmtNum(o.pct, 1)}% de la cartera
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-label font-bold uppercase text-app-text-faint">
            Hacia
            <select className={campo} value={destino} onChange={e => setDestino(e.target.value)}>
              <option value="">Elegí un grupo…</option>
              {destinos
                .filter(g => g.id !== origen)
                .map(g => (
                  <option key={g.id} value={g.id}>
                    {g.nombre}
                  </option>
                ))}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-label font-bold uppercase text-app-text-faint">
            Porcentaje de la cartera a trasladar (hasta {fmtNum(maxPct, 1)}%)
            <input className={campo} inputMode="decimal" value={pct} onChange={e => setPct(e.target.value)} aria-label="Porcentaje de la cartera a trasladar" />
          </label>
          <Button onClick={() => m.mutate()} disabled={!listo} loading={m.isPending}>
            Simular
          </Button>
        </>
      )}
      {m.error != null && <ErrorBanner error={parseApiError(m.error)} />}

      {sim && (
        <div className="flex flex-col gap-3">
          <div className="rounded-xl border border-app-border bg-app-surface px-3 py-2 text-caption text-app-text-dim">
            Se trasladarían <b className="text-app-text">{fmtNum(sim.rotacion.pct_cartera, 1)}%</b> de la cartera ({monto(sim.rotacion.monto_usd)}), que es el{' '}
            {fmtNum(sim.rotacion.pct_del_origen, 1)}% de lo que tenés en {sim.rotacion.origen.nombre}.
            <div className="flex flex-wrap items-center gap-1.5 mt-1.5">
              <span>{sim.rotacion.origen.nombre}</span>
              <BadgeCuadrante cuadrante={sim.rotacion.origen.estado?.cuadrante} />
              <span aria-hidden="true" className="text-app-text-faint">→</span>
              <span>{sim.rotacion.destino.nombre}</span>
              <BadgeCuadrante cuadrante={sim.rotacion.destino.estado?.cuadrante} />
            </div>
          </div>

          {sim.observaciones.length > 0 && (
            <ul className="flex flex-col gap-1.5">
              {sim.observaciones.map(o => (
                <li key={`${o.eje}-${o.texto}`} className="rounded-lg border border-app-border px-2.5 py-1.5">
                  <div className="text-caption text-app-text-dim">
                    <b className={NIVEL[o.nivel]}>{NIVEL_TXT[o.nivel]}.</b> {o.texto}
                  </div>
                  {o.regla && <div className="text-label text-app-text-faint">Regla: {o.regla}</div>}
                </li>
              ))}
            </ul>
          )}

          <Segmented options={sim.ejes.map(e => ({ value: e.eje, label: e.eje }))} value={sim.ejes.some(e => e.eje === eje) ? eje : sim.ejes[0].eje} onChange={setEje} />
          {sim.ejes
            .filter(e => e.eje === (sim.ejes.some(x => x.eje === eje) ? eje : sim.ejes[0].eje))
            .map(e => (
              <div key={e.eje} className="flex flex-col gap-1">
                <div className="grid grid-cols-[1fr,auto,auto,auto] gap-x-3 text-label font-bold uppercase text-app-text-faint px-1">
                  <span>{e.eje}</span>
                  <span className="text-right">Hoy</span>
                  <span className="text-right">Después</span>
                  <span className="text-right">Δ pp</span>
                </div>
                {e.items
                  .filter(i => i.antes_pct > 0 || i.despues_pct > 0)
                  .map(i => (
                    <div key={i.etiqueta} className={`grid grid-cols-[1fr,auto,auto,auto] gap-x-3 items-center rounded-lg px-1 py-1 text-caption ${i.afectada ? 'bg-app-accent-soft' : ''}`}>
                      <span className="truncate text-app-text">{i.etiqueta}</span>
                      <span className="text-right font-mono tabular-nums text-app-text-dim">{fmtNum(i.antes_pct, 1)}%</span>
                      <span className="text-right font-mono tabular-nums text-app-text">{fmtNum(i.despues_pct, 1)}%</span>
                      <span className={`text-right font-mono tabular-nums font-bold ${i.delta_pp > 0.005 ? 'text-app-pos' : i.delta_pp < -0.005 ? 'text-app-neg' : 'text-app-text-faint'}`}>
                        {i.delta_pp > 0 ? '+' : ''}
                        {fmtNum(i.delta_pp, 1)}
                      </span>
                    </div>
                  ))}
                <div className="text-label text-app-text-faint px-1">
                  Mayor posición: {e.antes.mayor ? `${e.antes.mayor.etiqueta} ${fmtNum(e.antes.mayor.porcentaje, 1)}%` : '—'} →{' '}
                  {e.despues.mayor ? `${e.despues.mayor.etiqueta} ${fmtNum(e.despues.mayor.porcentaje, 1)}%` : '—'}
                </div>
              </div>
            ))}

          {sim.rebalanceo.length > 0 && (
            <div className="flex flex-col gap-1">
              <div className="text-label font-bold uppercase text-app-text-faint">Distancia a tus objetivos</div>
              {sim.rebalanceo.map(r => (
                <div key={r.eje} className="rounded-lg border border-app-border px-2.5 py-1.5 text-caption text-app-text-dim">
                  <b className="text-app-text">{r.eje}:</b> desvío {fmtNum(r.desvio_antes_pp, 1)} pp → {fmtNum(r.desvio_despues_pp, 1)} pp
                  <div className="text-label text-app-text-faint">{r.regla}</div>
                </div>
              ))}
            </div>
          )}

          <div className="text-label text-app-text-faint">
            <div className="font-semibold text-app-text-dim mb-0.5">Cómo se simuló</div>
            <ul className="list-disc pl-4 space-y-0.5">
              {sim.supuestos.map(s => (
                <li key={s}>{s}</li>
              ))}
              {sim.notas.map(s => (
                <li key={s}>{s}</li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </div>
  )
}
