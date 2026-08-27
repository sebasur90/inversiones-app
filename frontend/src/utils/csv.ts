export type ValorCelda = string | number | boolean | null | undefined

/**
 * Escapa una celda para CSV: comillas dobles duplicadas, y entrecomillado si el valor
 * contiene el separador, comillas o saltos de línea.
 *
 * Los números van con punto decimal y sin separador de miles: Excel en configuración local
 * es-AR los reinterpreta según su propia configuración, y cualquier formateo nuestro (el
 * "$ 1.234,56" que muestra la pantalla) llegaría como texto.
 */
function escapar(valor: ValorCelda, separador: string): string {
  if (valor === null || valor === undefined) return ''
  const texto = typeof valor === 'number' ? String(valor) : String(valor)
  if (texto.includes(separador) || texto.includes('"') || texto.includes('\n')) {
    return `"${texto.replace(/"/g, '""')}"`
  }
  return texto
}

/**
 * Arma un CSV y dispara la descarga en el navegador.
 *
 * Usa `;` como separador y BOM UTF-8 porque el destino habitual es Excel en español: con `,`
 * mete todo en una sola columna, y sin BOM rompe los acentos.
 *
 * @param nombreArchivo nombre sugerido, sin extensión
 * @param encabezados fila de títulos
 * @param filas datos, en el mismo orden que los encabezados
 */
export function descargarCSV(
  nombreArchivo: string,
  encabezados: string[],
  filas: ValorCelda[][],
): void {
  const separador = ';'
  const lineas = [encabezados, ...filas].map(fila =>
    fila.map(celda => escapar(celda, separador)).join(separador),
  )
  const contenido = '﻿' + lineas.join('\r\n')

  const blob = new Blob([contenido], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const enlace = document.createElement('a')
  enlace.href = url
  enlace.download = `${nombreArchivo}.csv`
  document.body.appendChild(enlace)
  enlace.click()
  document.body.removeChild(enlace)
  URL.revokeObjectURL(url)
}

/** Sufijo de fecha para los nombres de archivo: `movimientos-2026-08-27.csv`. */
export function sufijoFechaHoy(): string {
  const d = new Date()
  const mes = String(d.getMonth() + 1).padStart(2, '0')
  const dia = String(d.getDate()).padStart(2, '0')
  return `${d.getFullYear()}-${mes}-${dia}`
}
