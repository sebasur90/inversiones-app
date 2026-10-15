import type { VarianteSerie, ZonasTickerOut } from '../../api'
import Button from '../ui/Button'
import InfoTooltip from '../../help/components/InfoTooltip'
import { COLOR_ZONA_COMPRA, COLOR_ZONA_VENTA } from './ZonasPrecio'

function rango(piso: number | null, techo: number | null, moneda: string): string {
  const m = moneda ? `${moneda} ` : ''
  if (piso != null && techo != null) return `${m}${piso} – ${techo}`
  if (techo != null) return `por debajo de ${m}${techo}`
  if (piso != null) return `por encima de ${m}${piso}`
  return '—'
}

/**
 * Las zonas guardadas de un ticker, en palabras, con el acceso a editarlas.
 *
 * Avisa cuando una zona está medida sobre **otra serie** que la que se está viendo: una zona en
 * USD sobre el subyacente no se puede comparar con el precio local, y editarla desde esta vista la
 * movería a la serie local (hay una sola zona por lado). Sin el aviso, el usuario estaría
 * reemplazando su zona en dólares sin darse cuenta.
 */
export default function ResumenZonas({
  zonas, variante, moneda, onEditar,
}: {
  zonas: ZonasTickerOut | undefined
  variante: VarianteSerie
  moneda: string
  onEditar: () => void
}) {
  const lados = [
    { tipo: 'compra' as const, titulo: 'Compra', zona: zonas?.compra, color: COLOR_ZONA_COMPRA },
    { tipo: 'venta' as const, titulo: 'Venta', zona: zonas?.venta, color: COLOR_ZONA_VENTA },
  ]
  const algunaZona = lados.some(l => l.zona)
  // Una zona vencida ya tiene su propio aviso: no se la cuenta además como "de otra serie".
  const vencidas = lados.filter(l => l.zona?.vencida)
  const otraSerie = lados.filter(l => l.zona && !l.zona.vencida && l.zona.variante !== variante)

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between gap-2">
        <span className="inline-flex items-center gap-1 text-label font-bold text-app-text-dim uppercase">
          Zonas
          <InfoTooltip term="zonas_precio" />
        </span>
        <Button variant="outline" className="h-8 px-3" onClick={onEditar}>
          {algunaZona ? 'Editar zonas' : 'Dibujar zona'}
        </Button>
      </div>

      {!algunaZona ? (
        <p className="text-label text-app-text-dim">
          Todavía no definiste zonas para este instrumento. Una zona es el rango de precios en el
          que querés comprar o vender: cuando el precio entra, llega el aviso.
        </p>
      ) : (
        <div className="flex flex-col gap-1">
          {lados.map(({ tipo, titulo, zona, color }) => (
            zona ? (
              <div key={tipo} className="flex items-baseline gap-1.5 text-caption">
                <span
                  className="w-2.5 h-2.5 rounded-sm shrink-0 translate-y-0.5"
                  style={{ background: color }}
                  aria-hidden
                />
                <span className="text-app-text-dim">{titulo}:</span>
                <span className="font-mono tabular-nums text-app-text">
                  {rango(zona.piso, zona.techo, zona.moneda)}
                </span>
                {zona.variante === 'subyacente' && (
                  <span className="text-label text-app-text-faint">· subyacente</span>
                )}
                {zona.vencida ? (
                  <span className="text-label text-app-text-faint">· vencida</span>
                ) : !zona.activa && (
                  <span className="text-label text-app-text-faint">· pausada</span>
                )}
              </div>
            ) : null
          ))}
        </div>
      )}

      {vencidas.length > 0 && (
        <div className="text-label text-app-text-dim bg-app-surface-2 rounded-xl px-2.5 py-2">
          {vencidas.length === 2 ? 'Tus zonas de compra y de venta estaban' : `Tu zona de ${vencidas[0].titulo.toLowerCase()} estaba`}{' '}
          medida{vencidas.length === 2 ? 's' : ''} sobre el CEDEAR en pesos. Este instrumento ahora se
          analiza por el precio de la acción en EE.UU. en dólares, y una zona en pesos no se puede
          pasar a dólares sin inventar el tipo de cambio y el ratio del CEDEAR: quedó
          pausada con sus números. Dibujá la zona de nuevo sobre el gráfico en dólares.
        </div>
      )}

      {otraSerie.length > 0 && (
        <div className="text-label text-app-text-dim bg-app-surface-2 rounded-xl px-2.5 py-2">
          {otraSerie.length === 2 ? 'Las dos zonas están' : 'Esta zona está'} medida
          {otraSerie.length === 2 ? 's' : ''} sobre la serie{' '}
          {otraSerie[0].zona!.variante === 'subyacente' ? 'del subyacente' : 'local'}
          {otraSerie[0].zona!.moneda ? ` (${otraSerie[0].zona!.moneda})` : ''}, así que no se
          dibuja{otraSerie.length === 2 ? 'n' : ''} en este gráfico, que está en{' '}
          {variante === 'subyacente' ? 'la serie del subyacente' : 'la serie local'}
          {moneda ? ` (${moneda})` : ''} — son dos instrumentos, no el mismo precio en dos monedas.
          Cambiá de serie con el selector de arriba para verla
          {otraSerie.length === 2 ? 's' : ''}, o dibujá una nueva acá: al guardar, la zona pasa a
          medirse sobre esta serie.
        </div>
      )}
    </div>
  )
}
