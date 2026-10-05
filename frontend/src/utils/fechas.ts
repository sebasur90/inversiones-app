import dayjs from 'dayjs'
import 'dayjs/locale/es'

// El locale se fija acá además de en `main.tsx`: cualquier módulo que use estos helpers lo
// obtiene por el solo hecho de importarlos, sin depender del orden de evaluación.
// Sin esto, dayjs formatea en inglés y la app mostraba "Oct 05, 2027" y "October 2027".
dayjs.locale('es')

/**
 * Formato de fechas, en un solo lugar.
 *
 * El equivalente de `formatoMonto.ts` para fechas: antes había cuatro formatos distintos
 * repartidos en ~22 llamadas a `.format()` -- tres de ellos en inglés -- y nueve copias de la
 * misma función `fmtFecha` con `toLocaleDateString`. Una fecha de vencimiento se mostraba
 * "5 oct 2027" en una pantalla y "05/10/2027" en otra.
 */

/** ISO (`2027-10-05`), período mensual (`2027-10`), `Date` o timestamp. */
type EntradaFecha = string | number | Date | null | undefined

const SOLO_MES = /^\d{4}-\d{2}$/

function parsear(valor: EntradaFecha) {
  if (valor == null || valor === '') return null
  // Los períodos mensuales del backend vienen como `YYYY-MM`, que dayjs no parsea solo.
  const entrada = typeof valor === 'string' && SOLO_MES.test(valor) ? `${valor}-01` : valor
  const d = dayjs(entrada)
  return d.isValid() ? d : null
}

/** El locale devuelve los meses en minúscula; al empezar una etiqueta hay que capitalizarlos. */
const capitalizar = (s: string) => s.charAt(0).toUpperCase() + s.slice(1)

/** `5 oct 2027`. El formato por defecto para una fecha puntual. */
export function fechaCorta(valor: EntradaFecha): string {
  return parsear(valor)?.format('D MMM YYYY') ?? '—'
}

/** `5 de octubre de 2027`. Para texto corrido. */
export function fechaLarga(valor: EntradaFecha): string {
  return parsear(valor)?.format('D [de] MMMM [de] YYYY') ?? '—'
}

/** `5 oct`. Para agrupar por día dentro del año en curso. */
export function diaMes(valor: EntradaFecha): string {
  return parsear(valor)?.format('D MMM') ?? '—'
}

/** `oct 2027`. Para períodos mensuales. */
export function mesAnio(valor: EntradaFecha): string {
  return parsear(valor)?.format('MMM YYYY') ?? '—'
}

/** `oct 27`. Para los ejes de los gráficos, donde el ancho manda. */
export function mesAnioCorto(valor: EntradaFecha): string {
  return parsear(valor)?.format('MMM YY') ?? '—'
}

/** `Octubre 2027`. Para encabezados y tooltips. */
export function mesAnioLargo(valor: EntradaFecha): string {
  const d = parsear(valor)
  return d ? capitalizar(d.format('MMMM YYYY')) : '—'
}

/** `Octubre`. El mes solo. */
export function nombreMes(valor: EntradaFecha): string {
  const d = parsear(valor)
  return d ? capitalizar(d.format('MMMM')) : '—'
}

/**
 * `Oct`. El mes solo, abreviado.
 *
 * No se llama `mesCorto`: ese nombre ya está tomado en `components/aportes/comun.ts`
 * con otra semántica (mes + año, "sep 2025").
 */
export function mesAbreviado(valor: EntradaFecha): string {
  const d = parsear(valor)
  return d ? capitalizar(d.format('MMM')) : '—'
}

/** `5 oct 2027, 14:32`. */
export function fechaHora(valor: EntradaFecha): string {
  return parsear(valor)?.format('D MMM YYYY, HH:mm') ?? '—'
}

/**
 * `['Ene', …, 'Dic']`, derivados del locale.
 *
 * Reemplaza los tres arrays idénticos que estaban escritos a mano en los heatmaps y en Riesgo.
 * El año fijo es para que el nombre no dependa de la fecha de hoy: `dayjs().month(i)` desde un
 * día 31 se desborda al mes siguiente.
 */
export const MESES_CORTOS: string[] = Array.from({ length: 12 }, (_, i) =>
  capitalizar(dayjs(`2000-${String(i + 1).padStart(2, '0')}-01`).format('MMM')),
)
