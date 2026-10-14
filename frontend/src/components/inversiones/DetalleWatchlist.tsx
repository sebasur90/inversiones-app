import { useEffect, useState } from 'react'
import type { WatchlistItemOut } from '../../api'
import { Icon } from '../icons/Icons'
import Button from '../ui/Button'
import InfoTooltip from '../../help/components/InfoTooltip'
import { cabeEnUnInput, textoZona } from '../../utils/zonas'

/**
 * Contenido del modal de un instrumento seguido: ajustar la zona de compra y las notas, refrescar
 * el precio, o dejar de seguirlo.
 *
 * El precio se escribe en la misma unidad en la que se muestra el precio de mercado (el que cotiza
 * IOL para ese símbolo), así que no hay nada que reconciliar: el ticker sale del catálogo.
 *
 * El input único es un **atajo**: escribe el techo de la zona de compra, que es "comprar por
 * debajo de X". Una zona con los dos bordes, o medida sobre la serie del subyacente en dólares, no
 * cabe en un solo número: esas se muestran en modo lectura y se editan arrastrándolas en el
 * gráfico, que es donde se dibujaron.
 */
export default function DetalleWatchlist({
  item,
  formatMoneda,
  onGuardar,
  onRefrescar,
  onEliminar,
  onVerTecnico,
  onVerPosicion,
  guardando,
  refrescando,
  eliminando,
}: {
  item: WatchlistItemOut
  formatMoneda: (valor: number, moneda: string) => string
  onGuardar: (cambios: { objetivo?: number | null; notas: string | null }) => void
  onRefrescar: () => void
  onEliminar: () => void
  onVerTecnico: () => void
  /** Sólo se ofrece si el ticker está en cartera: `/ticker/:ticker` es la pantalla de la
   * **posición** y sin tenencia no tiene nada que mostrar. El análisis técnico, en cambio, sale de
   * la serie del ticker y existe para cualquier instrumento seguido. */
  onVerPosicion: () => void
  guardando?: boolean
  refrescando?: boolean
  eliminando?: boolean
}) {
  const [objetivo, setObjetivo] = useState('')
  const [notas, setNotas] = useState('')
  const [confirmandoBaja, setConfirmandoBaja] = useState(false)

  // El input representa el **techo** de la zona de compra (ver la docstring): se siembra de ahí y
  // no de `precio_objetivo`, que queda en `null` cuando la zona se mide sobre otra serie.
  const techoZona = item.zona_compra?.techo ?? null
  const simple = cabeEnUnInput(item.zona_compra)

  // Re-sincroniza con el ítem: tras guardar o refrescar llega una versión nueva del servidor.
  useEffect(() => {
    setObjetivo(techoZona != null ? String(techoZona) : '')
    setNotas(item.notas ?? '')
  }, [item.ticker, techoZona, item.notas])

  const parseado = objetivo.trim() === '' ? null : Number(objetivo.replace(',', '.'))
  const objetivoInvalido = parseado !== null && (!Number.isFinite(parseado) || parseado <= 0)

  return (
    <div className="flex flex-col gap-4">
      <div>
        <div className="text-label text-app-text-dim">{item.nombre}</div>
        <div className="flex items-baseline gap-2 mt-1">
          <span className="font-mono text-heading font-bold text-app-text tabular-nums">
            {item.precio_actual != null
              ? formatMoneda(item.precio_actual, item.moneda_precio ?? item.moneda)
              : 'Sin cotización'}
          </span>
          {item.fecha_precio && (
            <span className="text-label text-app-text-dim">al {item.fecha_precio}</span>
          )}
        </div>
        <div className="text-label text-app-text-dim mt-0.5">
          {item.tipo_instrumento || '—'} · {item.mercado || '—'}
          {item.fuente_precio && ` · ${item.fuente_precio}`}
          {item.en_cartera && ' · En cartera'}
        </div>
      </div>

      {simple ? (
        <label className="flex flex-col gap-1.5">
          <span className="inline-flex items-center gap-1 text-label font-bold text-app-text-dim">
            Comprar por debajo de
            <InfoTooltip term="watchlist_precio_objetivo" />
          </span>
          <input
            inputMode="decimal"
            value={objetivo}
            onChange={e => setObjetivo(e.target.value)}
            placeholder="Ej. 1200"
            className={`h-11 px-3 rounded-2xl bg-app-surface-2 border text-body text-app-text tabular-nums outline-none ${
              objetivoInvalido ? 'border-app-neg' : 'border-app-border'
            }`}
          />
          {objetivoInvalido && (
            <span className="text-label text-app-neg">Tiene que ser un número mayor que cero.</span>
          )}
          <span className="text-label text-app-text-faint">
            Para un rango con piso y techo, dibujalo en el gráfico.
          </span>
        </label>
      ) : (
        <div className="flex flex-col gap-1.5">
          <span className="inline-flex items-center gap-1 text-label font-bold text-app-text-dim">
            Zona de compra
            <InfoTooltip term="zonas_precio" />
          </span>
          <span className="font-mono text-body text-app-text tabular-nums">
            {textoZona(item.zona_compra, formatMoneda)}
            {item.zona_compra?.variante === 'subyacente' && (
              <span className="ml-1.5 text-label text-app-text-dim">sobre el subyacente</span>
            )}
          </span>
          <span className="text-label text-app-text-faint">
            Esta zona se ajusta arrastrándola en el gráfico.
          </span>
        </div>
      )}

      {item.zona_venta && (
        <div className="flex flex-col gap-1.5">
          <span className="inline-flex items-center gap-1 text-label font-bold text-app-text-dim">
            Zona de venta
            <InfoTooltip term="zonas_precio" />
          </span>
          <span className="font-mono text-body text-app-text tabular-nums">
            {textoZona(item.zona_venta, formatMoneda)}
            {item.zona_venta.variante === 'subyacente' && (
              <span className="ml-1.5 text-label text-app-text-dim">sobre el subyacente</span>
            )}
          </span>
        </div>
      )}

      <label className="flex flex-col gap-1.5">
        <span className="text-label font-bold text-app-text-dim">Notas</span>
        <textarea
          rows={2}
          maxLength={500}
          value={notas}
          onChange={e => setNotas(e.target.value)}
          placeholder="Por qué lo seguís, qué esperás…"
          className="px-3 py-2 rounded-2xl bg-app-surface-2 border border-app-border text-body text-app-text outline-none resize-none"
        />
      </label>

      <div className="flex gap-2">
        <Button
          className="flex-1"
          disabled={objetivoInvalido}
          loading={guardando}
          onClick={() => onGuardar(
            simple
              ? { objetivo: parseado, notas: notas.trim() || null }
              // Sin `objetivo`: mandarlo convertiría el rango en "por debajo de X" y perdería el
              // piso o la serie sobre la que está medido.
              : { notas: notas.trim() || null },
          )}
        >
          Guardar
        </Button>
        <Button
          variant="outline"
          loading={refrescando}
          onClick={onRefrescar}
          icon={<Icon name="sync" className="w-4 h-4" />}
        >
          Precio
        </Button>
      </div>

      <div className="flex flex-col gap-2 pt-1 border-t border-app-border-soft">
        <div className="flex gap-2">
          <Button variant="ghost" className="flex-1" onClick={onVerTecnico}>
            Ver análisis técnico
          </Button>
          {item.en_cartera && (
            <Button variant="ghost" className="flex-1" onClick={onVerPosicion}>
              Ver posición
            </Button>
          )}
        </div>
        {confirmandoBaja ? (
          <Button
            variant="danger"
            loading={eliminando}
            onClick={onEliminar}
            icon={<Icon name="trash" className="w-4 h-4" />}
          >
            Confirmar baja
          </Button>
        ) : (
          <Button
            variant="ghost"
            onClick={() => setConfirmandoBaja(true)}
            icon={<Icon name="trash" className="w-4 h-4" />}
          >
            Dejar de seguir
          </Button>
        )}
      </div>
    </div>
  )
}
