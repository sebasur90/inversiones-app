import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  borrarNivelTicker, getDescomposicionFxPorPosicion, getPreciosTicker, guardarNivelesTicker,
  type PrecioPunto, type DescomposicionFxPosicionItem, type NivelesTickerIn, type TipoNivel,
} from '../../api'
import { qk } from '../../api/queryClient'
import { formatCantidad, formatPctRatio, formatPrecio } from '../../utils'
import { useFormatoFijo } from '../../hooks/useFormatoMoneda'
import Sparkline from '../../components/charts/Sparkline'
import MetricTile from '../../components/ui/MetricTile'
import Modal from '../../components/ui/Modal'
import Toast from '../../components/ui/Toast'
import AlertaPrecioBadge from '../../components/inversiones/AlertaPrecioBadge'
import EditarNiveles from '../../components/inversiones/EditarNiveles'
import { estadoAlerta, pctDelEstado } from '../../utils/alertasPrecio'
import { useInversionesContext } from '../../context/InversionesContext'
import { parseApiError } from '../../help/errors/apiErrors'
import { Icon } from '../../components/icons/Icons'
import type { TickerPositionOut } from '../../api'

export default function TickerResumenTab({ position, cartera, monedaSeleccionada }: { position: TickerPositionOut; cartera: string | null; monedaSeleccionada: 'ARS' | 'USD' }) {
  const { umbralProximidad } = useInversionesContext()
  const alerta = estadoAlerta(position, umbralProximidad)
  const queryClient = useQueryClient()

  const [editandoNiveles, setEditandoNiveles] = useState(false)
  const [aviso, setAviso] = useState<{ texto: string; tono: 'success' | 'error' } | null>(null)
  const [quitando, setQuitando] = useState<TipoNivel | null>(null)

  // Los niveles los leen esta pantalla, Posiciones, el badge de la barra inferior y Resumen; el
  // `staleTime: Infinity` del cliente obliga a invalidar a mano.
  const refrescarNiveles = async () => {
    await queryClient.invalidateQueries({ queryKey: qk.de('ticker-analisis', position.ticker, cartera) })
    void queryClient.invalidateQueries({ queryKey: qk.rendimientoPorTicker(cartera) })
    void queryClient.invalidateQueries({ queryKey: qk.diagnostico(cartera) })
  }

  const guardarNiveles = useMutation({
    mutationFn: (cambios: NivelesTickerIn) => guardarNivelesTicker(position.ticker, cambios),
    onSuccess: async () => {
      await refrescarNiveles()
      setEditandoNiveles(false)
      setAviso({ texto: 'Niveles guardados', tono: 'success' })
    },
    onError: (err: unknown) => setAviso({ texto: parseApiError(err).message, tono: 'error' }),
  })

  const quitarNivel = useMutation({
    mutationFn: (tipo: TipoNivel) => borrarNivelTicker(position.ticker, tipo),
    onMutate: (tipo: TipoNivel) => setQuitando(tipo),
    onSuccess: async () => {
      await refrescarNiveles()
      setAviso({ texto: 'Volvió al valor del Sheet', tono: 'success' })
    },
    onError: (err: unknown) => setAviso({ texto: parseApiError(err).message, tono: 'error' }),
    onSettled: () => setQuitando(null),
  })

  const preciosQuery = useQuery({
    queryKey: qk.de('precios-ticker', position.ticker),
    queryFn: () => getPreciosTicker(position.ticker),
  })
  // La descomposición FX es de la cartera entera: cacheada por cartera, se comparte con
  // cualquier otro ticker que se mire después.
  const fxQuery = useQuery({
    queryKey: qk.de('descomposicion-fx-posicion', cartera),
    queryFn: () => getDescomposicionFxPorPosicion(cartera),
  })

  const precios: PrecioPunto[] = preciosQuery.data?.puntos ?? []
  const descomposicionFxPorTicker: DescomposicionFxPosicionItem | null =
    fxQuery.data?.posiciones.find(p => p.ticker === position.ticker) ?? null

  const esARS = monedaSeleccionada === 'ARS'
  // Sólo "Invertido" y "Valor actual" son dinero tuyo. El precio actual, el promedio, el objetivo
  // y el stop-loss son precios del instrumento y siguen visibles con el modo privacidad.
  const { monto: formatMoneda } = useFormatoFijo(monedaSeleccionada)
  const valorInvertido = esARS ? position.total_invertido_ars : position.total_invertido_usd
  const valorActual = esARS ? position.valor_actual_ars : position.valor_actual_usd
  const rendimiento = esARS ? position.rendimiento_simple_ars : position.rendimiento_simple_usd
  const positivo = (rendimiento ?? 0) >= 0

  return (
    <div className="pb-4">
      <div className="mt-3">
        <div className="font-mono text-metric-lg font-bold text-app-text tabular-nums">{position.precio_actual != null ? formatPrecio(position.precio_actual) : '—'}</div>
        {rendimiento != null && (
          <span className={`inline-flex items-center gap-0.5 font-mono font-bold text-caption mt-1 tabular-nums ${positivo ? 'text-app-pos' : 'text-app-neg'}`}>
            <Icon name={positivo ? 'up' : 'down'} className="w-3 h-3" />
            {formatPctRatio(rendimiento)} desde promedio
          </span>
        )}
        {alerta && (
          <div className="flex flex-wrap gap-1.5 mt-2">
            <AlertaPrecioBadge estado={alerta} pct={pctDelEstado(position, alerta)} className="px-2 py-1" />
          </div>
        )}
        {precios.length > 0 && (
          <Sparkline
            data={precios.map(p => p.precio)}
            color={positivo ? '#10b981' : '#ef4444'}
            className="w-full h-14 mt-2.5"
          />
        )}
      </div>

      <div className="grid grid-cols-2 gap-2 mt-4">
        <MetricTile label="Cantidad" value={formatCantidad(position.cantidad_actual)} />
        <MetricTile label="Precio promedio" value={formatPrecio(position.precio_promedio)} />
        <MetricTile label="Invertido" infoTerm="invertido" value={formatMoneda(valorInvertido)} />
        <MetricTile label="Valor actual" value={formatMoneda(valorActual)} />
        <MetricTile label="Rend. simple" infoTerm="simple" value={formatPctRatio(rendimiento)} tone={rendimiento == null ? undefined : positivo ? 'pos' : 'neg'} />
        {esARS && position.rendimiento_simple_ars_real != null && (
          <MetricTile label="Rend. ARS real" infoTerm="cer" value={formatPctRatio(position.rendimiento_simple_ars_real)} tone={position.rendimiento_simple_ars_real >= 0 ? 'pos' : 'neg'} />
        )}
        {descomposicionFxPorTicker && descomposicionFxPorTicker.estado === 'ok' && (
          <>
            <MetricTile
              label="Efecto FX"
              infoTerm="efecto_fx"
              value={formatPctRatio(descomposicionFxPorTicker.efecto_fx_pct)}
              tone={descomposicionFxPorTicker.efecto_fx_pct == null ? undefined : descomposicionFxPorTicker.efecto_fx_pct >= 0 ? 'pos' : 'neg'}
            />
            <MetricTile
              label="Retorno activo"
              infoTerm="retorno_activo"
              value={formatPctRatio(descomposicionFxPorTicker.retorno_activo_pct)}
              tone={descomposicionFxPorTicker.retorno_activo_pct == null ? undefined : descomposicionFxPorTicker.retorno_activo_pct >= 0 ? 'pos' : 'neg'}
            />
          </>
        )}
        {/* Los dos niveles se muestran siempre, aunque no estén definidos: tocarlos es cómo se
            fijan desde la app. Antes la tile desaparecía y no había nada que tocar. */}
        <button type="button" onClick={() => setEditandoNiveles(true)} className="text-left">
          <MetricTile
            label="Precio Objetivo"
            infoTerm="objetivo"
            value={position.precio_objetivo != null ? formatPrecio(position.precio_objetivo) : '—'}
            sub={subNivel(
              position.precio_objetivo,
              position.pct_a_objetivo,
              position.objetivo_origen,
              true,
            )}
            tone={position.objetivo_alcanzado ? 'pos' : undefined}
          />
        </button>
        <button type="button" onClick={() => setEditandoNiveles(true)} className="text-left">
          <MetricTile
            label="Stop Loss"
            infoTerm="stopLoss"
            value={position.precio_stop_loss != null ? formatPrecio(position.precio_stop_loss) : '—'}
            sub={subNivel(
              position.precio_stop_loss,
              position.pct_a_stop_loss,
              position.stop_loss_origen,
              false,
            )}
            tone={position.stop_loss_disparado ? 'neg' : undefined}
          />
        </button>
      </div>

      {editandoNiveles && (
        <Modal open onClose={() => setEditandoNiveles(false)} title={`Niveles de ${position.ticker}`}>
          <EditarNiveles
            position={position}
            guardando={guardarNiveles.isPending}
            quitando={quitando}
            onGuardar={cambios => guardarNiveles.mutate(cambios)}
            onQuitar={tipo => quitarNivel.mutate(tipo)}
          />
        </Modal>
      )}

      <Toast message={aviso?.texto ?? null} tone={aviso?.tono} onDone={() => setAviso(null)} />
    </div>
  )
}

/**
 * Pie de la tile de un nivel: la distancia al precio de hoy, o la invitación a definirlo.
 * "fijado acá" es la marca de que ese nivel pisa al del Sheet.
 *
 * `pct` es `(nivel - precio_actual) / precio_actual`, así que el objetivo (que se cruza hacia
 * arriba) está superado con `pct < 0` y el stop-loss (hacia abajo) con `pct <= 0`.
 */
function subNivel(
  precio: number | null,
  pct: number | null,
  origen: string,
  cruzaHaciaArriba: boolean,
): string {
  if (precio == null) return 'Tocá para definirlo'
  const marca = origen === 'app' ? ' · fijado acá' : ''
  if (pct == null) return `Tocá para editarlo${marca}`
  const cruzado = cruzaHaciaArriba ? pct < 0 : pct <= 0
  return `${cruzado ? 'superado por' : 'falta'} ${(Math.abs(pct) * 100).toFixed(2)}%${marca}`
}
