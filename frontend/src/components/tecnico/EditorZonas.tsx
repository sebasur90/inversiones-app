import type { TipoZona, VarianteSerie, ZonaPrecioOut } from '../../api'
import Button from '../ui/Button'
import InfoTooltip from '../../help/components/InfoTooltip'
import { COLOR_ZONA_COMPRA, COLOR_ZONA_VENTA, type ZonasDibujo } from './ZonasPrecio'
import { redondearA, textoBorde } from './formatoEjes'

/** El borrador guarda strings y no números: mientras se tipea, un input controlado por número
 * pelea con el usuario (borrar el último dígito de "4900" no puede dejar `NaN`). Se parsea al
 * dibujar y al guardar. Mismo criterio que el input de objetivo de `DetalleWatchlist`. */
export interface BorradorZona {
  piso: string
  techo: string
}

export interface BorradorZonas {
  compra: BorradorZona | null
  venta: BorradorZona | null
}

export const ZONA_VACIA: BorradorZona = { piso: '', techo: '' }

/** Rango con el que arranca una zona nueva, relativo al último cierre. No pretende ser un buen
 * nivel: es un punto de partida **visible**. Una zona vacía no se dibuja y en el celular no habría
 * nada que arrastrar hasta tipear un número. La de compra queda apenas debajo del precio y la de
 * venta apenas arriba, así arrancan del lado correcto y no disparan un aviso en cuanto se guardan. */
const SUGERENCIA: Record<TipoZona, { piso: number; techo: number }> = {
  compra: { piso: 0.92, techo: 0.97 },
  venta: { piso: 1.05, techo: 1.12 },
}

export function zonaSugerida(tipo: TipoZona, precio: number | null | undefined): BorradorZona {
  if (precio == null || !(precio > 0)) return ZONA_VACIA
  // Tres cifras significativas: 164,9 → 165; 25.217 → 25.200.
  const paso = Math.pow(10, Math.floor(Math.log10(precio)) - 2)
  const { piso, techo } = SUGERENCIA[tipo]
  return {
    piso: textoBorde(redondearA(precio * piso, paso)),
    techo: textoBorde(redondearA(precio * techo, paso)),
  }
}

export function parsearBorde(texto: string): number | null {
  const limpio = texto.trim().replace(',', '.')
  if (limpio === '') return null
  const n = Number(limpio)
  return Number.isFinite(n) && n > 0 ? n : null
}

/** ¿El texto es algo distinto de un borde válido o de "vacío"? Es lo que habilita el Guardar. */
function bordeInvalido(texto: string): boolean {
  return texto.trim() !== '' && parsearBorde(texto) === null
}

export function zonaDesdeOut(zona: ZonaPrecioOut | null | undefined): BorradorZona | null {
  if (!zona) return null
  return {
    piso: zona.piso != null ? String(zona.piso) : '',
    techo: zona.techo != null ? String(zona.techo) : '',
  }
}

export function borradorDesdeOut(
  compra: ZonaPrecioOut | null | undefined, venta: ZonaPrecioOut | null | undefined,
): BorradorZonas {
  return { compra: zonaDesdeOut(compra), venta: zonaDesdeOut(venta) }
}

/** El borrador en la forma que dibuja `ZonasPrecio`. */
export function borradorADibujo(
  borrador: BorradorZonas, stopLoss?: number | null, objetivo?: number | null,
): ZonasDibujo {
  const una = (z: BorradorZona | null) =>
    z === null ? null : { piso: parsearBorde(z.piso), techo: parsearBorde(z.techo) }
  return { compra: una(borrador.compra), venta: una(borrador.venta), stopLoss, objetivo }
}

/** Una zona sin ningún borde no es una zona: el backend la rechaza (`zona_vacia`). */
export function zonaSinBordes(z: BorradorZona | null): boolean {
  return z !== null && parsearBorde(z.piso) === null && parsearBorde(z.techo) === null
}

export function borradorInvalido(borrador: BorradorZonas): string | null {
  for (const [tipo, z] of [['compra', borrador.compra], ['venta', borrador.venta]] as const) {
    if (z === null) continue
    const nombre = tipo === 'compra' ? 'compra' : 'venta'
    if (bordeInvalido(z.piso) || bordeInvalido(z.techo)) {
      return `Los bordes de la zona de ${nombre} tienen que ser números mayores que cero.`
    }
    if (zonaSinBordes(z)) {
      return `La zona de ${nombre} necesita al menos uno de los dos bordes.`
    }
    const piso = parsearBorde(z.piso)
    const techo = parsearBorde(z.techo)
    if (piso !== null && techo !== null && piso >= techo) {
      return `En la zona de ${nombre}, el piso tiene que ser menor que el techo.`
    }
  }
  return null
}

const ETIQUETA: Record<TipoZona, { titulo: string; color: string; dispara: string; ayuda: string }> = {
  compra: {
    titulo: 'Zona de compra',
    color: COLOR_ZONA_COMPRA,
    dispara: 'techo',
    ayuda: 'El aviso sale cuando el precio baja y cruza el techo de la zona.',
  },
  venta: {
    titulo: 'Zona de venta',
    color: COLOR_ZONA_VENTA,
    dispara: 'piso',
    ayuda: 'El aviso sale cuando el precio sube y cruza el piso de la zona.',
  },
}

/**
 * Editor de las zonas de compra y venta: los mismos valores que se arrastran en el gráfico, en
 * inputs numéricos.
 *
 * Los dos caminos conviven a propósito. Arrastrar es rápido y se ve contra las velas, pero no es
 * preciso; el input permite poner el número exacto y es el único camino accesible desde un teclado.
 * Los dos escriben el mismo borrador, así que mover el borde actualiza el input y viceversa.
 *
 * Nada se guarda al arrastrar: el guardado es explícito, porque una zona manda un aviso al
 * celular y un roce accidental no debería cambiar cuándo llega.
 */
export default function EditorZonas({
  borrador, moneda, variante, precioReferencia, onCambiar, onGuardar, onCancelar, guardando, error,
}: {
  borrador: BorradorZonas
  /** Último cierre de la serie: de ahí sale el rango inicial de una zona nueva. */
  precioReferencia?: number | null
  moneda: string
  variante: VarianteSerie
  onCambiar: (b: BorradorZonas) => void
  onGuardar: () => void
  onCancelar: () => void
  guardando?: boolean
  error?: string | null
}) {
  const problema = borradorInvalido(borrador)

  function cambiarBorde(tipo: TipoZona, borde: 'piso' | 'techo', valor: string) {
    const actual = borrador[tipo] ?? ZONA_VACIA
    onCambiar({ ...borrador, [tipo]: { ...actual, [borde]: valor } })
  }

  return (
    <div className="flex flex-col gap-3 bg-app-surface-2 rounded-2xl p-3">
      <div className="flex items-center gap-1 text-label font-bold text-app-text-dim uppercase">
        Editar zonas
        <InfoTooltip term="zonas_precio" />
      </div>

      <p className="text-label text-app-text-dim">
        Arrastrá las manijas ↕ del gráfico o escribí los precios acá; podés acercar y desplazar el
        gráfico mientras editás. Se miden sobre la serie{' '}
        <strong>{variante === 'subyacente' ? 'del subyacente' : 'local'}</strong>
        {moneda ? ` (${moneda})` : ''}, sin convertir de moneda.
      </p>

      {(['compra', 'venta'] as TipoZona[]).map(tipo => {
        const zona = borrador[tipo]
        const meta = ETIQUETA[tipo]
        return (
          <div key={tipo} className="flex flex-col gap-2 border-t border-app-border-soft pt-2">
            <div className="flex items-center justify-between gap-2">
              <span className="inline-flex items-center gap-1.5 text-caption font-bold text-app-text">
                <span
                  className="w-2.5 h-2.5 rounded-sm shrink-0"
                  style={{ background: meta.color }}
                  aria-hidden
                />
                {meta.titulo}
              </span>
              {zona === null ? (
                <button
                  type="button"
                  onClick={() => onCambiar({ ...borrador, [tipo]: zonaSugerida(tipo, precioReferencia) })}
                  className="text-label font-semibold text-app-accent"
                >
                  Agregar
                </button>
              ) : (
                <button
                  type="button"
                  onClick={() => onCambiar({ ...borrador, [tipo]: null })}
                  className="text-label font-semibold text-app-text-faint underline"
                >
                  Quitar
                </button>
              )}
            </div>

            {zona !== null && (
              <>
                <div className="flex gap-2">
                  {(['piso', 'techo'] as const).map(borde => (
                    <label key={borde} className="flex-1 flex flex-col gap-1">
                      <span className="text-label text-app-text-dim">
                        {borde === 'piso' ? 'Piso' : 'Techo'}
                        {borde === meta.dispara && (
                          <span className="ml-1 text-app-accent">· dispara</span>
                        )}
                      </span>
                      <input
                        inputMode="decimal"
                        value={zona[borde]}
                        onChange={e => cambiarBorde(tipo, borde, e.target.value)}
                        placeholder="sin límite"
                        className={`h-11 px-3 rounded-2xl bg-app-surface border text-body text-app-text tabular-nums outline-none ${
                          bordeInvalido(zona[borde]) ? 'border-app-neg' : 'border-app-border'
                        }`}
                      />
                    </label>
                  ))}
                </div>
                <span className="text-label text-app-text-faint">{meta.ayuda}</span>
              </>
            )}
          </div>
        )
      })}

      {(problema || error) && (
        <div className="text-label text-app-neg">{problema ?? error}</div>
      )}

      <div className="flex gap-2">
        <Button className="flex-1" onClick={onGuardar} disabled={!!problema} loading={guardando}>
          Guardar zonas
        </Button>
        <Button variant="outline" onClick={onCancelar}>Cancelar</Button>
      </div>
    </div>
  )
}
