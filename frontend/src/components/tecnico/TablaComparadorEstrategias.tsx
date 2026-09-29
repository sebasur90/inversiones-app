import TablaOrdenable, { type ColumnaOrdenable } from '../ui/TablaOrdenable'
import type { ComparadorFilaOut } from '../../api'
import { formatARS, formatUSD, formatPrecio } from '../../utils'

const ETIQUETA_ESTADO: Record<string, string> = {
  sin_senales: 'Sin señales',
  datos_insuficientes: 'Datos insuficientes',
  warm_up_insuficiente: 'Warm-up insuficiente',
  definicion_invalida: 'Definición inválida',
}

function formatMoneda(v: number, moneda: string): string {
  if (moneda === 'ARS') return formatARS(v)
  if (moneda === 'USD') return formatUSD(v)
  return formatPrecio(v)
}

function claveFila(f: ComparadorFilaOut): string {
  return String(f.estrategia_id ?? 'bh')
}

/** Tabla comparativa: filas con `estado != 'ok'` muestran por qué no hay número en vez de un
 * valor inventado (0, guiones sin explicación, etc). */
export default function TablaComparadorEstrategias({
  filas, moneda, onFilaClick,
}: {
  filas: ComparadorFilaOut[]
  moneda: string
  onFilaClick?: (fila: ComparadorFilaOut) => void
}) {
  const columnas: ColumnaOrdenable<ComparadorFilaOut>[] = [
    {
      key: 'nombre', label: 'Estrategia', align: 'left',
      valor: f => f.nombre,
      render: f => (
        <span className="inline-flex items-center gap-1.5">
          <span className="font-semibold text-app-text">{f.nombre}</span>
          {f.es_referencia && (
            <span className="text-label font-bold px-1.5 py-0.5 rounded bg-app-accent-soft text-app-accent">referencia</span>
          )}
        </span>
      ),
    },
    {
      key: 'capital_final', label: 'Capital final',
      valor: f => f.capital_final,
      render: f => f.capital_final != null ? formatMoneda(f.capital_final, moneda) : (ETIQUETA_ESTADO[f.estado] ?? '—'),
    },
    {
      key: 'retorno_total_pct', label: 'Rendimiento',
      valor: f => f.retorno_total_pct,
      render: f => f.retorno_total_pct != null ? (
        <span className={`font-mono font-bold ${f.retorno_total_pct >= 0 ? 'text-app-pos' : 'text-app-neg'}`}>
          {f.retorno_total_pct >= 0 ? '+' : ''}{f.retorno_total_pct.toFixed(2)}%
        </span>
      ) : (
        <span className="text-app-text-faint">{ETIQUETA_ESTADO[f.estado] ?? '—'}</span>
      ),
    },
    {
      key: 'diferencia_pp', label: 'vs. referencia',
      valor: f => f.diferencia_pp,
      render: f => f.diferencia_pp != null ? (
        <span className={`font-mono ${f.diferencia_pp >= 0 ? 'text-app-pos' : 'text-app-neg'}`}>
          {f.diferencia_pp >= 0 ? '+' : ''}{f.diferencia_pp.toFixed(2)} pp
        </span>
      ) : '—',
    },
    {
      key: 'max_drawdown_pct', label: 'Drawdown',
      valor: f => f.riesgo?.max_drawdown_pct ?? null,
      render: f => f.riesgo?.max_drawdown_pct != null ? `${f.riesgo.max_drawdown_pct.toFixed(2)}%` : '—',
    },
    {
      key: 'operaciones', label: 'Operaciones',
      valor: f => f.riesgo?.operaciones ?? null,
      render: f => f.riesgo?.operaciones ?? '—',
    },
  ]

  return (
    <TablaOrdenable
      columnas={columnas}
      filas={filas}
      getKey={claveFila}
      ordenInicial={{ key: 'retorno_total_pct', dir: 'desc' }}
      onFilaClick={onFilaClick}
    />
  )
}
