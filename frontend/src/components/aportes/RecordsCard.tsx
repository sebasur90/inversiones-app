import type { AporteRecords } from '../../api'
import Card from '../ui/Card'
import { formatUSD } from '../../utils'
import { mesCorto, meses } from './comun'

/** Récords personales. La comparación es siempre contra uno mismo: no hay rankings ni otros
 *  usuarios. Lo que no se puede calcular todavía se omite, no se rellena con ceros. */
export default function RecordsCard({ records }: { records: AporteRecords }) {
  const filas: { clave: string; emoji: string; titulo: string; valor: string; detalle?: string }[] = []

  if (records.mayor_aporte_mensual) {
    filas.push({
      clave: 'mes',
      emoji: '💪',
      titulo: 'Mayor aporte en un mes',
      valor: formatUSD(records.mayor_aporte_mensual.neto_usd),
      detalle: mesCorto(records.mayor_aporte_mensual.mes),
    })
  }
  if (records.mejor_racha.meses > 0) {
    filas.push({
      clave: 'racha',
      emoji: '🔥',
      titulo: 'Mejor racha',
      valor: meses(records.mejor_racha.meses),
      detalle: `${mesCorto(records.mejor_racha.desde)} → ${mesCorto(records.mejor_racha.hasta)}`,
    })
  }
  if (records.mayor_aporte_anual) {
    filas.push({
      clave: 'anual',
      emoji: '📆',
      titulo: 'Mayor aporte en un año',
      valor: formatUSD(records.mayor_aporte_anual.total_usd),
      detalle: String(records.mayor_aporte_anual.anio),
    })
  }
  if (records.mayor_promedio_mensual_anual) {
    filas.push({
      clave: 'promedio',
      emoji: '📊',
      titulo: 'Mejor promedio mensual',
      valor: formatUSD(records.mayor_promedio_mensual_anual.promedio_usd),
      detalle: String(records.mayor_promedio_mensual_anual.anio),
    })
  }
  if (records.mas_meses_cumpliendo_objetivo) {
    filas.push({
      clave: 'objetivo',
      emoji: '🎯',
      titulo: 'Más meses cumpliendo el objetivo',
      valor: meses(records.mas_meses_cumpliendo_objetivo.meses),
      detalle: String(records.mas_meses_cumpliendo_objetivo.anio),
    })
  }

  if (filas.length === 0) {
    return (
      <Card className="mb-4">
        <h3 className="text-body font-bold text-app-text mb-1">🏆 Tus récords</h3>
        <div className="text-caption text-app-text-dim">
          Todavía no hay historial suficiente. Con los primeros meses cerrados van a aparecer acá.
        </div>
      </Card>
    )
  }

  return (
    <Card className="mb-4">
      <h3 className="text-body font-bold text-app-text mb-3">🏆 Tus récords</h3>
      <div className="flex flex-col gap-2.5">
        {filas.map(f => (
          <div key={f.clave} className="flex items-baseline justify-between gap-2">
            <span className="text-caption text-app-text">
              <span className="mr-1.5" aria-hidden="true">{f.emoji}</span>
              {f.titulo}
            </span>
            <span className="text-right shrink-0">
              <span className="font-mono text-body font-bold tabular-nums text-app-text">{f.valor}</span>
              {f.detalle && <span className="block text-label text-app-text-faint">{f.detalle}</span>}
            </span>
          </div>
        ))}
      </div>
    </Card>
  )
}
