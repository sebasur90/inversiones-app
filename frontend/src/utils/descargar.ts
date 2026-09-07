/** Descarga un archivo generado en el cliente. Es el único mecanismo de descarga del front
 * (lo usa `csv.ts` y el export de estrategias). */
export function descargarArchivo(nombreArchivo: string, contenido: string, mime: string): void {
  const blob = new Blob([contenido], { type: mime })
  const url = URL.createObjectURL(blob)
  const enlace = document.createElement('a')
  enlace.href = url
  enlace.download = nombreArchivo
  document.body.appendChild(enlace)
  enlace.click()
  document.body.removeChild(enlace)
  URL.revokeObjectURL(url)
}
