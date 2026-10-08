import { useEffect, useMemo, useState } from 'react'
import type { ModoNivel, NivelesTickerIn, TickerPositionOut, TipoNivel } from '../../api'
import { formatPrecio } from '../../utils'
import Button from '../ui/Button'
import Segmented from '../ui/Segmented'
import InfoTooltip from '../../help/components/InfoTooltip'

/**
 * Contenido del modal para fijar el stop-loss y el objetivo de un ticker desde la app.
 *
 * Los dos niveles se pueden cargar en el Sheet (pestaña `Instrumentos`) o acá, y **gana lo que se
 * fija acá**. Por eso cada nivel muestra el valor del Sheet como referencia y, cuando hay
 * override, un botón para volver a él.
 *
 * Vacíar el campo y guardar también quita el override: es lo que uno espera al borrar el número.
 */

interface EstadoNivel {
  modo: ModoNivel
  texto: string
}

const ETIQUETA: Record<TipoNivel, string> = {
  stop_loss: 'Stop loss',
  objetivo: 'Precio objetivo',
}

/** Cómo se lee un nivel guardado, para la línea de referencia del Sheet. */
function textoNivel(modo: string | null, valor: number | null): string {
  if (!modo || valor == null) return '—'
  if (modo === 'Porcentaje') return `${valor > 0 ? '+' : ''}${valor}% sobre el precio de compra`
  return formatPrecio(valor)
}

function parsear(texto: string): number | null {
  const limpio = texto.trim()
  if (limpio === '') return null
  const valor = Number(limpio.replace(',', '.'))
  return Number.isFinite(valor) ? valor : NaN
}

/** Espejo de las reglas de `niveles_analytics._validar`, para avisar antes de mandar el PUT. */
function errorDe(tipo: TipoNivel, modo: ModoNivel, valor: number | null): string | null {
  if (valor === null) return null
  if (Number.isNaN(valor)) return 'Tiene que ser un número.'
  if (modo === 'Fijo') return valor > 0 ? null : 'Un precio tiene que ser mayor que cero.'
  if (valor === 0) return 'Un 0% deja el nivel en el precio de compra.'
  if (tipo === 'stop_loss') {
    if (valor > 0) return 'El stop loss va negativo: -5 es 5% por debajo del precio de compra.'
    if (valor <= -100) return 'No se puede caer más del 100%.'
  } else {
    if (valor < 0) return 'El objetivo va positivo: 20 es 20% por encima del precio de compra.'
    if (valor > 1000) return 'Como mucho 1000%.'
  }
  return null
}

export default function EditarNiveles({
  position,
  guardando,
  quitando,
  onGuardar,
  onQuitar,
}: {
  position: TickerPositionOut
  guardando?: boolean
  quitando?: TipoNivel | null
  onGuardar: (cambios: NivelesTickerIn) => void
  onQuitar: (tipo: TipoNivel) => void
}) {
  const vigente = useMemo(() => ({
    stop_loss: {
      modo: position.stop_loss_modo,
      valor: position.stop_loss_valor,
      origen: position.stop_loss_origen,
      modoSheet: position.stop_loss_modo_sheet,
      valorSheet: position.stop_loss_valor_sheet,
    },
    objetivo: {
      modo: position.objetivo_modo,
      valor: position.objetivo_valor,
      origen: position.objetivo_origen,
      modoSheet: position.objetivo_modo_sheet,
      valorSheet: position.objetivo_valor_sheet,
    },
  }), [position])

  // Sin nivel cargado se arranca en porcentaje, que es como se piensa un stop ("un 8% abajo"),
  // salvo que no haya precio de compra del cual partir.
  const modoPorDefecto: ModoNivel = position.precio_promedio > 0 ? 'Porcentaje' : 'Fijo'
  const sembrar = (v: { modo: string | null; valor: number | null }): EstadoNivel => ({
    modo: (v.modo as ModoNivel) ?? modoPorDefecto,
    texto: v.valor != null ? String(v.valor) : '',
  })

  const [stopLoss, setStopLoss] = useState<EstadoNivel>(() => sembrar(vigente.stop_loss))
  const [objetivo, setObjetivo] = useState<EstadoNivel>(() => sembrar(vigente.objetivo))

  // Tras guardar llega una versión nueva del servidor: el formulario se re-siembra con ella.
  useEffect(() => {
    setStopLoss(sembrar(vigente.stop_loss))
    setObjetivo(sembrar(vigente.objetivo))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [position.ticker, vigente.stop_loss.modo, vigente.stop_loss.valor, vigente.objetivo.modo, vigente.objetivo.valor])

  const estados: Record<TipoNivel, EstadoNivel> = { stop_loss: stopLoss, objetivo }
  const setters: Record<TipoNivel, (e: EstadoNivel) => void> = {
    stop_loss: setStopLoss,
    objetivo: setObjetivo,
  }

  const errores = {
    stop_loss: errorDe('stop_loss', stopLoss.modo, parsear(stopLoss.texto)),
    objetivo: errorDe('objetivo', objetivo.modo, parsear(objetivo.texto)),
  }
  const hayErrores = errores.stop_loss !== null || errores.objetivo !== null

  /** Sólo lo que cambió: guardar sin tocar nada no crea un override igual al del Sheet. */
  const cambios = useMemo(() => {
    const salida: NivelesTickerIn = {}
    for (const tipo of ['stop_loss', 'objetivo'] as TipoNivel[]) {
      const valor = parsear(estados[tipo].texto)
      const modo = estados[tipo].modo
      const actual = vigente[tipo]
      if (valor === null) {
        // Campo vacío: quita el override si había uno. Si no había, no hay nada que mandar.
        if (actual.origen === 'app') salida[tipo] = null
        continue
      }
      if (Number.isNaN(valor)) continue
      if (actual.modo === modo && actual.valor === valor) continue
      salida[tipo] = { modo, valor }
    }
    return salida
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stopLoss, objetivo, vigente])

  const sinCambios = Object.keys(cambios).length === 0

  const precioActual = position.precio_actual

  /** Dónde queda el nivel con lo que hay escrito, para verlo antes de guardar. */
  function vistaPrevia(tipo: TipoNivel): string | null {
    const valor = parsear(estados[tipo].texto)
    if (valor === null || Number.isNaN(valor) || errores[tipo]) return null
    const precio = estados[tipo].modo === 'Porcentaje'
      ? position.precio_promedio * (1 + valor / 100)
      : valor
    if (precio <= 0) return null
    const base = `Queda en ${formatPrecio(precio)}`
    if (precioActual == null || precioActual === 0) return base
    const distancia = ((precio - precioActual) / precioActual) * 100
    const palabra = distancia >= 0 ? 'por encima' : 'por debajo'
    return `${base} · ${Math.abs(distancia).toFixed(2)}% ${palabra} del precio de hoy`
  }

  return (
    <div className="flex flex-col gap-4">
      <div>
        <div className="text-label text-app-text-dim">{position.nombre}</div>
        <div className="flex items-baseline gap-2 mt-1">
          <span className="font-mono text-heading font-bold text-app-text tabular-nums">
            {precioActual != null ? formatPrecio(precioActual) : 'Sin cotización'}
          </span>
          <span className="text-label text-app-text-dim">
            compra {formatPrecio(position.precio_promedio)}
          </span>
        </div>
      </div>

      {(['stop_loss', 'objetivo'] as TipoNivel[]).map(tipo => {
        const estado = estados[tipo]
        const actual = vigente[tipo]
        const previa = vistaPrevia(tipo)
        const hayEnSheet = actual.modoSheet != null && actual.valorSheet != null
        return (
          <div key={tipo} className="flex flex-col gap-2 pt-3 border-t border-app-border-soft">
            <span className="inline-flex items-center gap-1 text-label font-bold text-app-text-dim">
              {ETIQUETA[tipo]}
              <InfoTooltip term={tipo === 'stop_loss' ? 'stopLoss' : 'objetivo'} />
            </span>

            <Segmented<ModoNivel>
              options={[
                { value: 'Porcentaje', label: '% del precio de compra' },
                { value: 'Fijo', label: 'Precio fijo' },
              ]}
              value={estado.modo}
              onChange={modo => setters[tipo]({ ...estado, modo })}
            />

            <input
              inputMode="decimal"
              value={estado.texto}
              onChange={e => setters[tipo]({ ...estado, texto: e.target.value })}
              placeholder={estado.modo === 'Porcentaje'
                ? (tipo === 'stop_loss' ? 'Ej. -8' : 'Ej. 25')
                : 'Ej. 1200'}
              className={`h-11 px-3 rounded-2xl bg-app-surface-2 border text-body text-app-text tabular-nums outline-none ${
                errores[tipo] ? 'border-app-neg' : 'border-app-border'
              }`}
            />

            {errores[tipo] && <span className="text-label text-app-neg">{errores[tipo]}</span>}
            {!errores[tipo] && previa && (
              <span className="text-label text-app-text-dim tabular-nums">{previa}</span>
            )}
            {!errores[tipo] && !previa && estado.texto.trim() === '' && (
              <span className="text-label text-app-text-faint">
                {actual.origen === 'app'
                  ? 'Vacío quita el nivel fijado acá y vuelve al del Sheet.'
                  : 'Sin nivel: este ticker no va a avisar nada.'}
              </span>
            )}

            {hayEnSheet && (
              <div className="flex items-center justify-between gap-2">
                <span className="text-label text-app-text-faint">
                  En el Sheet: {textoNivel(actual.modoSheet, actual.valorSheet)}
                  {actual.origen === 'app' && ' (pisado desde acá)'}
                </span>
                {actual.origen === 'app' && (
                  <Button
                    variant="ghost"
                    loading={quitando === tipo}
                    onClick={() => onQuitar(tipo)}
                  >
                    Volver al Sheet
                  </Button>
                )}
              </div>
            )}
          </div>
        )
      })}

      <Button
        disabled={hayErrores || sinCambios}
        loading={guardando}
        onClick={() => onGuardar(cambios)}
      >
        Guardar
      </Button>
      <span className="inline-flex items-start gap-1 text-label text-app-text-faint">
        Lo que fijes acá pisa al Sheet y sobrevive a las sincronizaciones. El aviso al celular usa
        este nivel desde la próxima corrida.
        <InfoTooltip term="nivel_origen" />
      </span>
    </div>
  )
}
