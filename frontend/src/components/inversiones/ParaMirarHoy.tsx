import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import type { CalidadDatosOut, DiagnosticoOut, RendimientoPorTickerItem, WatchlistItemOut } from '../../api'
import { priorizarHallazgos } from '../../utils/hallazgos'
import { alertasDeCompra, alertasDePrecio, type EstadoAlerta } from '../../utils/alertasPrecio'
import { Icon, type IconName } from '../icons/Icons'
import SeverityBadge, { type Severidad } from './SeverityBadge'
import AlertaPrecioBadge from './AlertaPrecioBadge'

const MAX_HALLAZGOS = 3
const MAX_TICKERS = 4

type Vista = 'alertas' | 'compras'

// Los cruces consumados llevan la flecha de la dirección del precio; los avisos de
// proximidad, el triángulo de atención: todavía no pasó nada, sólo falta poco.
function iconoDeEstado(estado: EstadoAlerta): IconName {
  if (estado === 'stop_loss_disparado') return 'down'
  if (estado === 'objetivo_alcanzado') return 'up'
  return 'alert'
}

const FONDO_SEVERIDAD: Record<Severidad, string> = {
  critico: 'bg-app-neg-soft text-app-neg',
  advertencia: 'bg-app-accent-soft text-app-accent',
  info: 'bg-app-pos-soft text-app-pos',
}

const BORDE_FILA = 'w-full text-left px-3.5 py-3 border-b border-app-border-soft last:border-b-0'
const FILA = `${BORDE_FILA} flex items-center gap-3`
const FILA_TEXTO = `${BORDE_FILA} flex flex-col gap-0.5`

/**
 * Lo que el usuario necesita mirar hoy, junto y en el Resumen: las alertas de precio de sus
 * posiciones, los hallazgos del diagnóstico, los errores del sync y —en otra pestaña— los
 * instrumentos de la Watchlist que entraron (o están por entrar) en su zona de compra. Antes
 * eran dos bloques de tarjetas sueltas que empujaban todo lo demás hacia abajo.
 *
 * No hace ningún fetch: los insumos ya están cargados en la pantalla. Si no hay nada, lo dice:
 * un bloque que desaparece no distingue "todo bien" de "no se revisó".
 */
export default function ParaMirarHoy({
  diagnostico,
  calidad,
  posiciones,
  watchlist,
  umbralProximidad,
}: {
  diagnostico: DiagnosticoOut | null
  calidad: CalidadDatosOut | null
  posiciones: RendimientoPorTickerItem[]
  watchlist: WatchlistItemOut[]
  umbralProximidad: number
}) {
  const navigate = useNavigate()
  const [vistaElegida, setVistaElegida] = useState<Vista>('alertas')

  const alertas = useMemo(() => alertasDePrecio(posiciones, umbralProximidad), [posiciones, umbralProximidad])
  const compras = useMemo(() => alertasDeCompra(watchlist, umbralProximidad), [watchlist, umbralProximidad])
  const enCartera = useMemo(() => new Set(watchlist.filter(w => w.en_cartera).map(w => w.ticker)), [watchlist])

  // Los hallazgos de precio ya se muestran ticker por ticker acá arriba: repetirlos como
  // hallazgo agregado ("2 posiciones alcanzaron su stop-loss") sería decir lo mismo dos veces.
  // Se compara contra los cruces consumados, no contra las alertas de proximidad: el
  // diagnóstico sólo emite estos hallazgos cuando el precio ya cruzó el nivel, así que un
  // "cerca del stop" no debe tapar un "stop-loss disparado" agregado.
  const hayCruce = useMemo(
    () => ({
      stop_loss_disparado: alertas.some(a => a.estado === 'stop_loss_disparado'),
      objetivo_precio_alcanzado: alertas.some(a => a.estado === 'objetivo_alcanzado'),
    }),
    [alertas],
  )

  const hallazgos = useMemo(() => {
    const items = diagnostico?.hallazgos ?? []
    const relevantes = items.filter(
      h => h.severidad !== 'info' && !hayCruce[h.tipo as keyof typeof hayCruce],
    )
    return priorizarHallazgos(relevantes).slice(0, MAX_HALLAZGOS)
  }, [diagnostico, hayCruce])

  const issuesCriticos = calidad?.issues.filter(i => i.severidad === 'critico').length ?? 0

  const totalAlertas = alertas.length + hallazgos.length + (issuesCriticos > 0 ? 1 : 0)
  const totalCompras = compras.length

  // Con una sola de las dos listas no hace falta elegir: se muestra esa, sin pestañas.
  const hayAmbas = totalAlertas > 0 && totalCompras > 0
  const vista: Vista = hayAmbas ? vistaElegida : totalAlertas > 0 ? 'alertas' : 'compras'

  return (
    <section className="mb-4" aria-label="Para mirar hoy">
      <h3 className="text-strong font-bold text-app-text mb-2">Para mirar hoy</h3>

      {totalAlertas + totalCompras === 0 ? (
        <div className="flex items-center gap-3 bg-app-surface border border-app-border rounded-2xl p-3.5">
          <div className="w-9 h-9 rounded-full bg-app-pos-soft text-app-pos flex items-center justify-center shrink-0">
            <Icon name="check" className="w-[18px] h-[18px]" />
          </div>
          <div className="min-w-0">
            <div className="text-body font-semibold text-app-text">Todo en orden</div>
            <div className="text-caption text-app-text-dim">
              Ninguna alerta de precio, hallazgo importante ni error de datos. Se revisaron {posiciones.length}{' '}
              posicion{posiciones.length !== 1 ? 'es' : ''} y {watchlist.length} de la Watchlist.
            </div>
          </div>
        </div>
      ) : (
        <>
          {hayAmbas && (
            <div role="tablist" aria-label="Tipo de aviso" className="grid grid-cols-2 gap-1 p-1 mb-2 bg-app-surface border border-app-border rounded-xl">
              {([
                ['alertas', 'Alertas', totalAlertas, 'bg-app-neg-soft text-app-neg'],
                ['compras', 'Para comprar', totalCompras, 'bg-app-pos-soft text-app-pos'],
              ] as const).map(([id, etiqueta, cantidad, claseCantidad]) => (
                <button
                  key={id}
                  role="tab"
                  aria-selected={vista === id}
                  onClick={() => setVistaElegida(id)}
                  className={`flex items-center justify-center gap-1.5 min-h-10 rounded-[9px] text-body font-semibold transition-colors ${
                    vista === id ? 'bg-app-surface-2 text-app-text' : 'text-app-text-dim'
                  }`}
                >
                  {etiqueta}
                  <span className={`min-w-5 h-5 px-1 rounded-full font-mono text-label inline-flex items-center justify-center ${claseCantidad}`}>
                    {cantidad}
                  </span>
                </button>
              ))}
            </div>
          )}

          <div className="bg-app-surface border border-app-border rounded-2xl overflow-hidden">
            {vista === 'alertas' && (
              <>
                {alertas.slice(0, MAX_TICKERS).map(a => (
                  <button
                    key={`${a.estado}-${a.ticker}`}
                    onClick={() => navigate(`/ticker/${encodeURIComponent(a.ticker)}`)}
                    className={FILA}
                  >
                    <div className={`w-8 h-8 rounded-lg flex items-center justify-center shrink-0 ${FONDO_SEVERIDAD[a.severidad]}`}>
                      <Icon name={iconoDeEstado(a.estado)} className="w-4 h-4" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="text-body font-semibold text-app-text truncate">{a.ticker}</div>
                      <div className="text-caption text-app-text-dim truncate">{a.nombre}</div>
                    </div>
                    <AlertaPrecioBadge estado={a.estado} pct={a.pct} />
                  </button>
                ))}

                {alertas.length > MAX_TICKERS && (
                  <button
                    onClick={() => navigate('/posiciones?alerta=con_alerta')}
                    className={`${FILA} text-caption font-semibold text-app-text-dim`}
                  >
                    Ver las {alertas.length - MAX_TICKERS} alertas restantes →
                  </button>
                )}

                {hallazgos.map(h => (
                  <button
                    key={`${h.tipo}-${h.titulo}`}
                    onClick={() => navigate(h.pantalla || '/diagnostico')}
                    className={FILA_TEXTO}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <div className="text-body font-semibold text-app-text truncate">{h.titulo}</div>
                      <SeverityBadge severidad={h.severidad as Severidad} />
                    </div>
                    <div className="text-caption text-app-text-dim line-clamp-2">{h.explicacion}</div>
                  </button>
                ))}

                {issuesCriticos > 0 && (
                  <button
                    onClick={() => navigate('/calidad-datos')}
                    className={FILA_TEXTO}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <div className="text-body font-semibold text-app-text">Errores en el último sync</div>
                      <SeverityBadge severidad="critico" />
                    </div>
                    <div className="text-caption text-app-text-dim">
                      {issuesCriticos} problema{issuesCriticos !== 1 ? 's' : ''} crítico{issuesCriticos !== 1 ? 's' : ''} en los
                      datos: los números de esta pantalla pueden estar incompletos.
                    </div>
                  </button>
                )}
              </>
            )}

            {vista === 'compras' && (
              <>
                {compras.slice(0, MAX_TICKERS).map(a => (
                  <button
                    key={a.ticker}
                    onClick={() =>
                      enCartera.has(a.ticker)
                        ? navigate(`/ticker/${encodeURIComponent(a.ticker)}`)
                        : navigate('/watchlist')
                    }
                    className={FILA}
                  >
                    <div className={`w-8 h-8 rounded-lg flex items-center justify-center shrink-0 ${FONDO_SEVERIDAD[a.severidad]}`}>
                      <Icon name="target" className="w-4 h-4" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="text-body font-semibold text-app-text truncate">{a.ticker}</div>
                      <div className="text-caption text-app-text-dim truncate">{a.nombre}</div>
                    </div>
                    <AlertaPrecioBadge estado={a.estado} pct={a.pct} />
                  </button>
                ))}

                {compras.length > MAX_TICKERS && (
                  <button
                    onClick={() => navigate('/watchlist?alerta=con_alerta')}
                    className={`${FILA} text-caption font-semibold text-app-text-dim`}
                  >
                    Ver las {compras.length - MAX_TICKERS} alertas restantes →
                  </button>
                )}
              </>
            )}
          </div>
        </>
      )}
    </section>
  )
}
