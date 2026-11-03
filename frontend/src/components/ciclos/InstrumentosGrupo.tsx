import type { CiclosInstrumentosOut } from '../../api'
import InfoTooltip from '../../help/components/InfoTooltip'
import { useFormatoFijo } from '../../hooks/useFormatoMoneda'
import BadgeCuadrante from './BadgeCuadrante'
import { fmtNum, fmtPct } from './constantes'

/** Las posiciones de la cartera que pertenecen a un grupo, juntadas por emisor (CEDEAR y acción de origen cuentan una vez). */
export default function InstrumentosGrupo({ data }: { data: CiclosInstrumentosOut }) {
  const { monto, montoConSigno } = useFormatoFijo('USD')
  const regla = Object.entries(data.regla).filter(([, v]) => v && (Array.isArray(v) ? v.length > 0 : true))
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <BadgeCuadrante cuadrante={data.estado?.cuadrante} />
        <span className="text-caption text-app-text-dim">
          {data.instrumentos.length === 0 ? (
            'No tenés posiciones en este grupo.'
          ) : (
            <>
              Exposición total: <b className="text-app-text">{fmtNum(data.exposicion_pct, 1)}%</b> de la cartera ({monto(data.exposicion_usd)})
            </>
          )}
        </span>
      </div>
      {data.instrumentos.length > 0 && (
        <ul className="flex flex-col gap-1.5">
          {data.instrumentos.map(i => (
            <li key={i.emisor} className="rounded-xl border border-app-border bg-app-surface px-3 py-2">
              <div className="flex items-center justify-between gap-2">
                <span className="text-caption font-semibold text-app-text truncate">{i.nombre}</span>
                <span className="font-mono tabular-nums text-caption font-bold text-app-text shrink-0">{fmtNum(i.peso_cartera_pct, 1)}%</span>
              </div>
              <div className="text-label text-app-text-faint">
                {i.tickers.join(' · ')} · {fmtNum(i.peso_en_grupo_pct, 1)}% del grupo
              </div>
              <div className="flex items-center justify-between gap-2 mt-1 text-label">
                <span className="text-app-text-dim">{monto(i.valor_usd)}</span>
                {i.rendimiento_pct == null ? (
                  <span className="text-app-text-faint" title={i.rendimiento_no_calculable ?? undefined}>
                    rendimiento no calculable
                  </span>
                ) : (
                  <span className={i.rendimiento_pct >= 0 ? 'text-app-pos' : 'text-app-neg'}>
                    {fmtPct(i.rendimiento_pct / 100)} · {montoConSigno(i.resultado_usd)}
                  </span>
                )}
              </div>
              {i.clasificacion && (
                <div className="text-label text-app-text-faint mt-0.5">
                  {[i.clasificacion.tipo, i.clasificacion.sector, i.clasificacion.industria, i.clasificacion.pais, i.clasificacion.region].filter(Boolean).join(' · ') || 'Sin clasificar'}
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
      {data.resultado_usd != null && (
        <p className="text-caption text-app-text-dim">
          Resultado de las posiciones de este grupo: <b className={data.resultado_usd >= 0 ? 'text-app-pos' : 'text-app-neg'}>{montoConSigno(data.resultado_usd)}</b>
          {data.resultado_parcial ? ' (sin contar las que no tienen cotización)' : ''}.
        </p>
      )}
      <div className="text-label text-app-text-faint">
        Cómo se decide la pertenencia:{' '}
        {regla.map(([k, v]) => `${k.replace('exacta_', '')}: ${Array.isArray(v) ? v.join(', ') : v}`).join(' · ') || 'sin regla'}.
        {data.grupo.lista_curada && <> Es una <InfoTooltip term="ciclos_lista_curada" label="lista curada" />.</>}
      </div>
      {data.avisos.map(a => (
        <p key={a} className="text-label text-app-text-faint">{a}</p>
      ))}
    </div>
  )
}
