import type { Nivel } from '../../utils/niveles'

const COLOR_PUNTO: Record<Nivel, string> = {
  bien: 'bg-app-teal',
  atencion: 'bg-app-gold',
  riesgo: 'bg-app-coral',
}

const COLOR_TEXTO: Record<Nivel, string> = {
  bien: 'text-app-teal',
  atencion: 'text-app-gold',
  riesgo: 'text-app-coral',
}

/** Punto de color + texto: nunca sólo color, para que la alerta no dependa de distinguir
 *  verde/dorado/coral. Ver `utils/niveles.ts` para los umbrales de cada métrica. */
export default function Semaforo({ nivel, etiqueta, className = '' }: { nivel: Nivel; etiqueta: string; className?: string }) {
  return (
    <span className={`inline-flex items-center gap-1.5 ${className}`}>
      <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${COLOR_PUNTO[nivel]}`} aria-hidden="true" />
      <span className={`text-label font-semibold ${COLOR_TEXTO[nivel]}`}>{etiqueta}</span>
    </span>
  )
}
