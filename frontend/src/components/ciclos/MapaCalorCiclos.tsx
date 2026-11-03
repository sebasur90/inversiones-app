import { useMemo } from 'react'
import type { CicloGrupoPanorama } from '../../api'
import { heatmapIntensity } from '../../utils'
import Segmented from '../ui/Segmented'
import TablaOrdenable, { type ColumnaOrdenable } from '../ui/TablaOrdenable'
import BadgeCuadrante from './BadgeCuadrante'
import { CAP_HEATMAP, fmtPct } from './constantes'

export type ModoCalor = 'absoluto' | 'relativo'

interface Props {
  grupos: CicloGrupoPanorama[]
  horizontes: string[]
  modo: ModoCalor
  onModo: (m: ModoCalor) => void
  onSeleccionar: (id: string) => void
}

const ETIQUETA_H: Record<string, string> = { '1M': '1M', '3M': '3M', '6M': '6M', '1A': '1A', '3A': '3A', '5A': '5A', '10A': '10A' }

/**
 * Rendimientos por horizonte, absolutos o relativos a la referencia. Un horizonte sin historia real queda como
 * «—» (sin datos suficientes): jamás se completa con una estimación ni se acorta el período en silencio.
 */
export default function MapaCalorCiclos({ grupos, horizontes, modo, onModo, onSeleccionar }: Props) {
  const columnas = useMemo<ColumnaOrdenable<CicloGrupoPanorama>[]>(
    () => [
      {
        key: 'nombre',
        label: 'Grupo',
        align: 'left',
        valor: g => g.nombre,
        render: g => (
          <span className="flex flex-col items-start gap-0.5 pr-2 min-w-[96px]">
            <span className="text-caption font-semibold text-app-text leading-tight">{g.nombre}</span>
            <BadgeCuadrante cuadrante={g.rrg.actual?.cuadrante} />
          </span>
        ),
      },
      ...horizontes.map<ColumnaOrdenable<CicloGrupoPanorama>>(h => ({
        key: h,
        label: ETIQUETA_H[h] ?? h,
        valor: g => {
          const c = g.rendimientos[h]
          return c ? (modo === 'absoluto' ? c.absoluto : c.relativo) : null
        },
        render: g => {
          const c = g.rendimientos[h]
          const v = c ? (modo === 'absoluto' ? c.absoluto : c.relativo) : null
          if (v == null) {
            return (
              <span className="block text-center text-app-text-faint" title="Sin datos suficientes" aria-label="Sin datos suficientes">
                —
              </span>
            )
          }
          return (
            <span className="block rounded-md px-1 py-1 text-center font-mono tabular-nums text-label" style={heatmapIntensity(v, CAP_HEATMAP[h] ?? 40)}>
              {fmtPct(v, Math.abs(v) >= 1 ? 0 : 1, true)}
            </span>
          )
        },
      })),
    ],
    [horizontes, modo],
  )

  return (
    <div className="flex flex-col gap-2">
      <Segmented
        options={[
          { value: 'absoluto' as ModoCalor, label: 'Rendimiento absoluto' },
          { value: 'relativo' as ModoCalor, label: 'Relativo a la referencia' },
        ]}
        value={modo}
        onChange={onModo}
      />
      <TablaOrdenable
        columnas={columnas}
        filas={grupos}
        getKey={g => g.id}
        ordenInicial={{ key: horizontes.includes('1A') ? '1A' : horizontes[horizontes.length - 1] ?? 'nombre', dir: 'desc' }}
        onFilaClick={g => onSeleccionar(g.id)}
      />
      <p className="text-label text-app-text-faint">
        «—» = sin datos suficientes para ese horizonte (no se completa con estimaciones). Los horizontes de 5 y 10 años aparecen sólo si algún grupo
        tiene esa historia.
      </p>
    </div>
  )
}
