import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { qk } from '../../api/queryClient'
import { getTamanoPosicion, type VarianteSerie } from '../../api'
import { useFormatoFijo } from '../../hooks/useFormatoMoneda'
import InfoTooltip from '../../help/components/InfoTooltip'
import Segmented from '../ui/Segmented'
import { formatoPrecio } from './formatoEjes'
import {
  calcularPosicion, type ModoRiesgo, type ModoStop, type ProblemaCalculo,
} from './calculoPosicion'

const TEXTO_PROBLEMA: Record<ProblemaCalculo, string> = {
  sin_precio: 'Todavía no hay un último precio para esta serie.',
  riesgo_invalido: 'Poné un riesgo mayor que cero.',
  sin_cartera: 'No hay valor de cartera para medir el riesgo en %. Usá un monto en dólares.',
  stop_invalido: 'Revisá el stop: tiene que ser mayor que cero y quedar por debajo del precio.',
  sin_atr: 'Esta serie no tiene ATR todavía (hacen falta unas 15 ruedas).',
  stop_sobre_el_precio: 'El stop tiene que estar por debajo del precio de entrada.',
}

const AYUDA_STOP: Record<ModoStop, { label: string; sufijo: string }> = {
  atr: { label: 'Veces el ATR', sufijo: '× ATR' },
  pct: { label: 'Porcentaje', sufijo: '%' },
  precio: { label: 'Precio', sufijo: '' },
}

/** "12,5" o "12.5" → 12.5; vacío o basura → NaN (y la cuenta lo marca como inválido). */
const numero = (s: string) => (s.trim() === '' ? NaN : Number(s.replace(',', '.')))

const unidades = (v: number) =>
  v.toLocaleString('es-AR', { maximumFractionDigits: v >= 100 ? 0 : 2 })

/**
 * Calculadora de tamaño de posición, plegable debajo del gráfico: cuánto comprar para que, si el
 * precio toca el stop, se pierda sólo lo que se decidió arriesgar. La cuenta vive en
 * `calculoPosicion.ts`; el servidor aporta el último cierre y el ATR de la serie que se está
 * mirando, el MEP, el último precio del CEDEAR en pesos y el valor de la cartera.
 *
 * Los importes que salen de la cartera (riesgo en %, monto a invertir) pasan por el modo
 * privacidad; los precios, el ATR, los porcentajes y las unidades se muestran siempre.
 */
export default function CalculadoraPosicion({
  ticker, variante, onStopProvisorio,
}: {
  ticker: string
  variante: VarianteSerie
  /** Precio del stop a dibujar sobre el gráfico, o `null` para sacarlo. */
  onStopProvisorio: (precio: number | null) => void
}) {
  const fmt = useFormatoFijo('USD')
  const [abierta, setAbierta] = useState(false)
  const [modoRiesgo, setModoRiesgo] = useState<ModoRiesgo>('pct_cartera')
  const [riesgo, setRiesgo] = useState('1')
  const [modoStop, setModoStop] = useState<ModoStop>('atr')
  const [stop, setStop] = useState('2')
  const [verStop, setVerStop] = useState(false)

  const query = useQuery({
    queryKey: qk.de('tecnico-tamano-posicion', ticker, variante),
    queryFn: () => getTamanoPosicion(ticker, variante),
    enabled: abierta,
  })
  const datos = query.data

  const calculo = datos?.ultimo_cierre != null
    ? calcularPosicion({
        precio: datos.ultimo_cierre, modoRiesgo, riesgo: numero(riesgo), modoStop, stop: numero(stop),
        atr: datos.atr, valorCarteraUsd: datos.valor_cartera_usd, serieEnUsd: datos.moneda === 'USD',
        mep: datos.mep, precioLocalArs: datos.moneda_local === 'ARS' ? datos.precio_local : null,
      })
    : null
  const resultado = calculo && 'montoUsd' in calculo ? calculo : null
  const problema = calculo && 'problema' in calculo ? TEXTO_PROBLEMA[calculo.problema] : null
  const precioStop = resultado?.precioStop ?? null

  // La línea provisoria sólo existe mientras la calculadora está abierta, el botón prendido y la
  // cuenta es válida; al plegarla o cambiar de ticker se saca del gráfico.
  const dibujar = abierta && verStop && precioStop != null ? precioStop : null
  useEffect(() => {
    onStopProvisorio(dibujar)
    return () => onStopProvisorio(null)
  }, [dibujar, onStopProvisorio])

  function cambiarModoStop(nuevo: ModoStop) {
    setModoStop(nuevo)
    setStop(nuevo === 'atr' ? '2' : nuevo === 'pct' ? '8' : datos?.ultimo_cierre != null ? (datos.ultimo_cierre * 0.92).toFixed(2) : '')
  }

  return (
    <div className="rounded-2xl bg-app-surface-2">
      <button
        type="button" onClick={() => setAbierta(a => !a)} aria-expanded={abierta}
        className="w-full flex items-center justify-between gap-2 px-3 py-2.5"
      >
        <span className="flex items-center gap-1.5 text-label font-bold text-app-text-dim uppercase">
          Calculadora de tamaño
          <InfoTooltip term="calculadora_posicion" />
        </span>
        <span className="text-caption text-app-text-dim">{abierta ? '▲' : '▼'}</span>
      </button>

      {abierta && (
        <div className="flex flex-col gap-3 px-3 pb-3">
          {query.isLoading && <p className="text-label text-app-text-dim">Cargando…</p>}
          {query.isError && <p className="text-label text-app-neg">No se pudieron cargar los datos de este ticker.</p>}

          {datos && (
            <>
              <p className="text-label text-app-text-dim">
                Entrada al último cierre:{' '}
                <span className="font-mono text-app-text">{datos.moneda} {formatoPrecio(datos.ultimo_cierre)}</span>
                {datos.atr != null && <> · ATR(14) <span className="font-mono text-app-text">{formatoPrecio(datos.atr)}</span></>}
              </p>

              <div className="flex flex-col gap-1.5">
                <span className="text-label text-app-text-dim">Cuánto arriesgás</span>
                <div className="flex items-center gap-2">
                  <Segmented
                    options={[{ value: 'pct_cartera', label: '% cartera' }, { value: 'usd', label: 'US$' }]}
                    value={modoRiesgo}
                    onChange={m => { setModoRiesgo(m); setRiesgo(m === 'pct_cartera' ? '1' : '100') }}
                  />
                  <input
                    inputMode="decimal" value={riesgo} onChange={e => setRiesgo(e.target.value)}
                    aria-label="Riesgo" className="h-11 w-24 px-3 rounded-2xl bg-app-surface border border-app-border text-body text-app-text tabular-nums outline-none"
                  />
                </div>
                {modoRiesgo === 'pct_cartera' && (
                  <span className="text-label text-app-text-faint">
                    {datos.valor_cartera_usd != null
                      ? `Sobre el valor actual de tu cartera: ${fmt.monto(datos.valor_cartera_usd)}`
                      : 'Sin valor de cartera: usá un monto en dólares.'}
                  </span>
                )}
              </div>

              <div className="flex flex-col gap-1.5">
                <span className="text-label text-app-text-dim">Dónde ponés el stop</span>
                <div className="flex items-center gap-2">
                  <Segmented
                    options={(['atr', 'pct', 'precio'] as ModoStop[]).map(m => ({ value: m, label: AYUDA_STOP[m].label }))}
                    value={modoStop} onChange={cambiarModoStop}
                  />
                </div>
                <div className="flex items-center gap-2">
                  <input
                    inputMode="decimal" value={stop} onChange={e => setStop(e.target.value)}
                    aria-label="Stop" className="h-11 w-28 px-3 rounded-2xl bg-app-surface border border-app-border text-body text-app-text tabular-nums outline-none"
                  />
                  <span className="text-label text-app-text-dim">{AYUDA_STOP[modoStop].sufijo || datos.moneda}</span>
                </div>
              </div>

              {problema && <p className="text-label text-app-neg">{problema}</p>}

              {resultado && (
                <div className="flex flex-col gap-1.5 rounded-xl bg-app-surface px-3 py-2.5 font-mono tabular-nums">
                  <Fila etiqueta="Stop en" valor={`${datos.moneda} ${formatoPrecio(resultado.precioStop)}`} />
                  <Fila etiqueta="Distancia al stop" valor={`${formatoPrecio(resultado.distancia)} (${resultado.distanciaPct.toFixed(1).replace('.', ',')}%)`} />
                  <Fila etiqueta="Perdés si toca el stop" valor={fmt.monto(resultado.riesgoUsd)} />
                  <Fila etiqueta="Invertir" valor={fmt.monto(resultado.montoUsd)} fuerte />
                  {resultado.cedears != null ? (
                    <Fila etiqueta="CEDEARs a comprar" valor={`${Math.floor(resultado.cedears).toLocaleString('es-AR')}`} fuerte />
                  ) : resultado.unidades != null ? (
                    <Fila etiqueta="Unidades" valor={unidades(resultado.unidades)} fuerte />
                  ) : null}
                </div>
              )}

              {resultado?.cedears != null && (
                <p className="text-label text-app-text-faint">
                  Con el dólar MEP ({formatoPrecio(datos.mep)}) y el último precio del CEDEAR (${' '}
                  {formatoPrecio(datos.precio_local)}); redondeado hacia abajo para no pasarte del riesgo.
                </p>
              )}
              {resultado?.unidades == null && resultado && resultado.cedears == null && datos.mep == null && (
                <p className="text-label text-app-text-faint">Falta el dólar MEP para pasar el monto a unidades.</p>
              )}
              {resultado?.superaLaCartera && (
                <p className="text-label text-app-neg">
                  El monto supera el valor de tu cartera: con ese stop tan cerca, el riesgo elegido es demasiado grande.
                </p>
              )}

              <button
                type="button" disabled={precioStop == null} onClick={() => setVerStop(v => !v)}
                className="self-start h-9 px-3 rounded-lg bg-app-surface text-caption font-semibold text-app-accent disabled:opacity-40"
              >
                {verStop ? 'Sacar el stop del gráfico' : 'Ver el stop en el gráfico'}
              </button>
            </>
          )}
        </div>
      )}
    </div>
  )
}

function Fila({ etiqueta, valor, fuerte }: { etiqueta: string; valor: string; fuerte?: boolean }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <span className="text-label text-app-text-dim font-sans">{etiqueta}</span>
      <span className={fuerte ? 'text-strong font-semibold text-app-text' : 'text-caption text-app-text'}>{valor}</span>
    </div>
  )
}
