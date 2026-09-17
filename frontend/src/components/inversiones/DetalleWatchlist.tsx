import { useEffect, useState } from 'react'
import type { WatchlistItemOut } from '../../api'
import { Icon } from '../icons/Icons'
import Button from '../ui/Button'
import InfoTooltip from '../../help/components/InfoTooltip'

/**
 * Contenido del modal de un instrumento seguido: editar el precio objetivo y las notas, refrescar
 * el precio, o dejar de seguirlo.
 *
 * El objetivo se escribe en la misma unidad en la que se muestra el precio de mercado (el que
 * cotiza IOL para ese símbolo), así que no hay nada que reconciliar: el ticker sale del catálogo.
 */
export default function DetalleWatchlist({
  item,
  formatMoneda,
  onGuardar,
  onRefrescar,
  onEliminar,
  onVerTecnico,
  guardando,
  refrescando,
  eliminando,
}: {
  item: WatchlistItemOut
  formatMoneda: (valor: number, moneda: string) => string
  onGuardar: (cambios: { objetivo: number | null; notas: string | null }) => void
  onRefrescar: () => void
  onEliminar: () => void
  onVerTecnico: () => void
  guardando?: boolean
  refrescando?: boolean
  eliminando?: boolean
}) {
  const [objetivo, setObjetivo] = useState('')
  const [notas, setNotas] = useState('')
  const [confirmandoBaja, setConfirmandoBaja] = useState(false)

  // Re-sincroniza con el ítem: tras guardar o refrescar llega una versión nueva del servidor.
  useEffect(() => {
    setObjetivo(item.precio_objetivo != null ? String(item.precio_objetivo) : '')
    setNotas(item.notas ?? '')
  }, [item.ticker, item.precio_objetivo, item.notas])

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

      <label className="flex flex-col gap-1.5">
        <span className="inline-flex items-center gap-1 text-label font-bold text-app-text-dim">
          Precio objetivo de compra
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
      </label>

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
          onClick={() => onGuardar({ objetivo: parseado, notas: notas.trim() || null })}
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

      <div className="flex gap-2 pt-1 border-t border-app-border-soft">
        {item.en_cartera && (
          <Button variant="ghost" className="flex-1" onClick={onVerTecnico}>
            Ver análisis técnico
          </Button>
        )}
        {confirmandoBaja ? (
          <Button
            variant="danger"
            className="flex-1"
            loading={eliminando}
            onClick={onEliminar}
            icon={<Icon name="trash" className="w-4 h-4" />}
          >
            Confirmar baja
          </Button>
        ) : (
          <Button
            variant="ghost"
            className="flex-1"
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
