import { severidadDeEstado, type EstadoAlerta } from '../../utils/alertasPrecio'
import type { Severidad } from './SeverityBadge'

// Mismos tokens semánticos que SeverityBadge, pero con etiqueta propia: dentro de la
// severidad "advertencia" hay que poder distinguir un stop-loss cercano de un objetivo
// cercano, y "ATENCIÓN" a secas no lo dice.
const SEVERIDAD_CLASSES: Record<Severidad, string> = {
  critico: 'bg-app-coral-soft text-app-coral',
  advertencia: 'bg-app-gold-soft text-app-gold',
  info: 'bg-app-teal-soft text-app-teal',
}

const COMPACTO: Record<EstadoAlerta, string> = {
  stop_loss_disparado: '🛑 STOP',
  stop_loss_cerca: '⚠ STOP',
  objetivo_alcanzado: '🎯 META',
  objetivo_cerca: '⚠ META',
}

const COMPLETO: Record<EstadoAlerta, string> = {
  stop_loss_disparado: 'Stop-loss disparado',
  stop_loss_cerca: 'Cerca del stop-loss',
  objetivo_alcanzado: 'Objetivo alcanzado',
  objetivo_cerca: 'Cerca del objetivo',
}

/** Texto de distancia al nivel. `pct` es un ratio y su signo no importa acá: lo que se
 *  comunica es cuánto falta (o por cuánto se pasó), y eso lo define el estado. */
function textoDistancia(estado: EstadoAlerta, pct: number | null | undefined): string | null {
  if (pct == null) return null
  const magnitud = `${Math.abs(pct * 100).toFixed(1)}%`
  const cruzado = estado === 'stop_loss_disparado' || estado === 'objetivo_alcanzado'
  return cruzado ? `superado por ${magnitud}` : `a ${magnitud}`
}

/**
 * Señal visual de que una posición cruzó —o está por cruzar— su stop-loss o su precio
 * objetivo. `compacto` es la variante para listas densas (una fila de Posiciones); la
 * completa se usa donde hay espacio para la frase entera.
 */
export default function AlertaPrecioBadge({
  estado,
  pct,
  compacto = false,
  className = '',
}: {
  estado: EstadoAlerta
  pct?: number | null
  compacto?: boolean
  className?: string
}) {
  const severidad = severidadDeEstado(estado)
  const distancia = textoDistancia(estado, pct)
  // La versión compacta se abrevia hasta perder sentido fuera de contexto, y además vive
  // dentro de un botón que ya tiene su propio label: el texto largo va al title/aria.
  const descripcion = distancia ? `${COMPLETO[estado]} · ${distancia}` : COMPLETO[estado]

  return (
    <span
      title={descripcion}
      aria-label={descripcion}
      className={`inline-block font-bold text-label tracking-wide px-1.5 py-0.5 rounded-[6px] shrink-0 ${SEVERIDAD_CLASSES[severidad]} ${className}`}
    >
      {compacto ? COMPACTO[estado] : descripcion}
    </span>
  )
}
