import { useState } from 'react'
import type { CiclosCarteraOut, CicloItemExposicion } from '../../api'
import InfoTooltip from '../../help/components/InfoTooltip'
import { useFormatoFijo } from '../../hooks/useFormatoMoneda'
import Segmented from '../ui/Segmented'
import BadgeCuadrante from './BadgeCuadrante'
import { INFO_CUADRANTE, MOTIVO_SIN_ESTADO, fmtNum } from './constantes'

const COLOR_SIN_ESTADO = '#475569'

function colorDe(clave: string): string {
  return clave === 'sin_estado' ? COLOR_SIN_ESTADO : INFO_CUADRANTE[clave as keyof typeof INFO_CUADRANTE].color
}

function nombreDe(clave: string): string {
  return clave === 'sin_estado' ? 'Sin estado' : INFO_CUADRANTE[clave as keyof typeof INFO_CUADRANTE].nombre
}

function FilaItem({ it, onSeleccionar, monto }: { it: CicloItemExposicion; onSeleccionar: (id: string) => void; monto: (v: number) => string }) {
  const contenido = (
    <>
      <div className="flex items-center justify-between gap-2">
        <span className="text-caption font-semibold text-app-text truncate">{it.etiqueta}</span>
        <span className="font-mono tabular-nums text-caption font-bold text-app-text shrink-0">{fmtNum(it.porcentaje, 1)}%</span>
      </div>
      <div className="flex items-center justify-between gap-2 mt-0.5">
        {it.cuadrante ? (
          <BadgeCuadrante cuadrante={it.cuadrante} pendiente={!!it.confirmado && it.confirmado !== it.cuadrante} />
        ) : (
          <span className="text-label text-app-text-faint">{MOTIVO_SIN_ESTADO[it.rubro] ?? 'Sin estado'}</span>
        )}
        <span className="text-label text-app-text-faint tabular-nums">{monto(it.valor_usd)}</span>
      </div>
    </>
  )
  const clase = 'w-full rounded-xl border border-app-border bg-app-surface px-3 py-2 text-left'
  return it.grupo_id ? (
    <button type="button" onClick={() => onSeleccionar(it.grupo_id!)} className={`${clase} active:scale-[0.99]`}>
      {contenido}
    </button>
  ) : (
    <div className={clase} title={it.motivo_sin_estado ?? undefined}>
      {contenido}
    </div>
  )
}

/**
 * Dónde está el capital según el estado actual de cada ciclo. Sector, región y país son dimensiones excluyentes (cada
 * una suma 100 %); industrias, commodities y temas se superponen y se muestran aparte, sin sumarlos.
 */
export default function ExposicionCiclos({ data, onSeleccionarGrupo }: { data: CiclosCarteraOut; onSeleccionarGrupo: (id: string) => void }) {
  const [dimension, setDimension] = useState<string>(data.dimensiones[0]?.dimension ?? 'Sector')
  const { monto } = useFormatoFijo('USD')
  const dim = data.dimensiones.find(d => d.dimension === dimension) ?? data.dimensiones[0]
  if (!dim) return null
  const sinEstado = dim.por_cuadrante.find(p => p.cuadrante === 'sin_estado')?.porcentaje ?? 0
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-2">
        <Segmented options={data.dimensiones.map(d => ({ value: d.dimension as string, label: d.dimension }))} value={dim.dimension} onChange={setDimension} />
        <div
          role="img"
          aria-label={`Capital por estado del ciclo, por ${dim.dimension.toLowerCase()}: ${dim.por_cuadrante.map(p => `${nombreDe(p.cuadrante)} ${fmtNum(p.porcentaje, 1)}%`).join(', ')}`}
          className="flex h-5 w-full overflow-hidden rounded-md bg-app-surface-2"
        >
          {dim.por_cuadrante
            .filter(p => p.porcentaje > 0)
            .map(p => (
              <div key={p.cuadrante} style={{ width: `${p.porcentaje}%`, backgroundColor: colorDe(p.cuadrante) }} title={`${nombreDe(p.cuadrante)} ${fmtNum(p.porcentaje, 1)}%`} />
            ))}
        </div>
        <ul className="grid grid-cols-2 gap-x-3 gap-y-1">
          {dim.por_cuadrante.map(p => (
            <li key={p.cuadrante} className="flex items-center justify-between gap-2 text-caption">
              <span className="inline-flex items-center gap-1.5 text-app-text-dim">
                <span aria-hidden="true" className="w-2 h-2 rounded-full" style={{ backgroundColor: colorDe(p.cuadrante) }} />
                {nombreDe(p.cuadrante)}
              </span>
              <span className="font-mono tabular-nums font-bold text-app-text">{fmtNum(p.porcentaje, 1)}%</span>
            </li>
          ))}
        </ul>
        {sinEstado > 0 && dim.sin_estado_detalle.length > 0 && (
          <p className="text-label text-app-text-faint">
            <InfoTooltip term="ciclos_sin_clasificar" label="Sin estado" /> ({fmtNum(sinEstado, 1)}%):{' '}
            {dim.sin_estado_detalle.map(d => `${MOTIVO_SIN_ESTADO[d.motivo] ?? d.motivo} ${fmtNum(d.porcentaje, 1)}%`).join(' · ')}.
          </p>
        )}
        <p className="text-label text-app-text-faint">{data.resumen.lectura}</p>
      </div>

      <ul className="flex flex-col gap-1.5">
        {dim.items.map(it => (
          <li key={it.etiqueta}>
            <FilaItem it={it} onSeleccionar={onSeleccionarGrupo} monto={monto} />
          </li>
        ))}
      </ul>

      {data.superpuestas.length > 0 && (
        <div className="flex flex-col gap-2">
          <div className="text-label font-bold uppercase text-app-text-faint">
            <InfoTooltip term="ciclos_no_suman" label="Industrias, commodities y temas (se superponen)" />
          </div>
          <p className="text-label text-app-text-dim">
            {data.aviso_superpuestos} Unión de cada tipo, contando cada posición una sola vez:{' '}
            {Object.entries(data.uniones_pct)
              .filter(([, v]) => v > 0)
              .map(([k, v]) => `${k === 'industria' ? 'industrias' : k === 'commodity' ? 'commodities' : 'temas'} ${fmtNum(v, 1)}%`)
              .join(' · ') || 'ninguna'}
            .
          </p>
          <ul className="flex flex-col gap-1.5">
            {data.superpuestas.map(s => (
              <li key={s.grupo_id}>
                <button
                  type="button"
                  onClick={() => onSeleccionarGrupo(s.grupo_id)}
                  className="w-full rounded-xl border border-app-border bg-app-surface px-3 py-2 text-left active:scale-[0.99]"
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-caption font-semibold text-app-text truncate">
                      {s.nombre}
                      {s.lista_curada && <span className="ml-1.5 text-label font-semibold text-app-text-faint">lista curada</span>}
                    </span>
                    <span className="font-mono tabular-nums text-caption font-bold text-app-text shrink-0">{fmtNum(s.porcentaje, 1)}%</span>
                  </div>
                  <div className="flex items-center justify-between gap-2 mt-0.5">
                    {s.cuadrante ? <BadgeCuadrante cuadrante={s.cuadrante} /> : <span className="text-label text-app-text-faint">{MOTIVO_SIN_ESTADO[s.rubro] ?? 'Sin estado'}</span>}
                    <span className="text-label text-app-text-faint truncate">{s.emisores.join(', ')}</span>
                  </div>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      {data.sin_clasificar.length > 0 && (
        <div className="flex flex-col gap-1.5">
          <div className="text-label font-bold uppercase text-app-text-faint">
            <InfoTooltip term="ciclos_sin_clasificar" label="Posiciones sin clasificar o con datos incompletos" />
          </div>
          <ul className="flex flex-col gap-1">
            {data.sin_clasificar.map(s => (
              <li key={s.ticker} className="flex items-center justify-between gap-2 rounded-lg border border-app-border px-2.5 py-1.5 text-caption">
                <span className="font-semibold text-app-text">{s.ticker}</span>
                <span className="text-label text-app-text-faint">{s.sin_ficha ? 'sin ficha' : `falta ${s.faltan.join(', ')}`}</span>
                <span className="font-mono tabular-nums text-app-text-dim shrink-0">{fmtNum(s.porcentaje, 1)}%</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {data.advertencias.map(a => (
        <p key={a} className="text-label text-app-warn">{a}</p>
      ))}
    </div>
  )
}
