import { useRef, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { importarEventos, type EventosImportarOut, type FuentesEventos as FuentesEventosT } from '../../api'
import { qk } from '../../api/queryClient'
import { parseApiError } from '../../help/errors/apiErrors'
import { fechaHora } from '../../utils/fechas'
import Button from '../ui/Button'
import { Etiqueta } from './comun'

const ESTADO: Record<string, { texto: string; tono: 'pos' | 'neg' | 'warn' | 'neutro' }> = {
  ok: { texto: 'Al día', tono: 'pos' },
  parcial: { texto: 'Incompleta', tono: 'warn' },
  no_configurado: { texto: 'Sin configurar', tono: 'neutro' },
  desactivado: { texto: 'Apagada', tono: 'neutro' },
  rate_limited: { texto: 'Pidió esperar', tono: 'warn' },
  cupo_agotado: { texto: 'Cupo agotado', tono: 'warn' },
  error: { texto: 'Con error', tono: 'neg' },
}

/** Estado de cada proveedor y la importación de un archivo de calendario. Nunca muestra claves. */
export default function FuentesEventos({ fuentes }: { fuentes: FuentesEventosT }) {
  const qc = useQueryClient()
  const archivo = useRef<HTMLInputElement>(null)
  const [resultado, setResultado] = useState<EventosImportarOut | null>(null)
  const [errorArchivo, setErrorArchivo] = useState<string | null>(null)
  const importar = useMutation({
    mutationFn: importarEventos,
    onSuccess: r => { setResultado(r); void qc.invalidateQueries({ queryKey: qk.de('eventos') }) },
    onError: err => setErrorArchivo(parseApiError(err).message),
  })

  const leer = async (f: File | undefined) => {
    setResultado(null)
    setErrorArchivo(null)
    if (!f) return
    if (f.size > 2_000_000) return setErrorArchivo('El archivo es demasiado grande (máximo 2 MB).')
    try {
      importar.mutate(JSON.parse(await f.text()))
    } catch {
      setErrorArchivo('El archivo no es un JSON válido.')
    }
  }

  return (
    <div className="flex flex-col gap-3">
      <ul className="flex flex-col gap-2">
        {fuentes.fuentes.map(f => {
          const est = f.estado ? ESTADO[f.estado] : null
          const sinConfigurar = !f.configurado || !f.habilitado
          return (
            <li key={f.proveedor} className="rounded-xl border border-app-border p-2.5">
              <div className="flex items-center justify-between gap-2">
                <span className="text-caption font-semibold text-app-text">{f.etiqueta}</span>
                {est && <Etiqueta tono={est.tono}>{est.texto}</Etiqueta>}
              </div>
              <div className="mt-0.5 text-label text-app-text-faint">
                {f.ultima_corrida ? `Última consulta ${fechaHora(f.ultima_corrida + 'Z')}` : 'Nunca consultada'}
                {f.limite_diario != null && ` · ${f.solicitudes_hoy}/${f.limite_diario} consultas hoy`}
                {f.solo_revision && ' · sus resultados van a revisión'}
              </div>
              {f.mensaje && <div className="mt-0.5 text-label text-app-text-dim">{f.mensaje}</div>}
              {sinConfigurar && (
                <div className="mt-1 rounded-lg bg-app-surface-2 p-2 text-label text-app-text-dim">
                  {f.motivo && <div className="font-bold text-app-text">{f.motivo}</div>}
                  {f.ayuda}
                </div>
              )}
            </li>
          )
        })}
      </ul>

      <div className="rounded-xl border border-app-border p-2.5">
        <div className="text-caption font-semibold text-app-text">Importar un calendario</div>
        <p className="mt-0.5 text-label text-app-text-dim">
          Para fechas oficiales sin API (elecciones, reuniones de bancos centrales): un archivo .json con el formato de
          docs/calendario-eventos.md. Reimportarlo actualiza en vez de duplicar.
        </p>
        <input ref={archivo} type="file" accept="application/json,.json" className="hidden" onChange={e => void leer(e.target.files?.[0])} />
        <Button variant="outline" className="mt-2 w-full" loading={importar.isPending} onClick={() => archivo.current?.click()}>Elegir archivo</Button>
        {errorArchivo && <p className="mt-1 text-label text-app-neg">{errorArchivo}</p>}
        {resultado && (
          <div className="mt-1 text-label text-app-text-dim">
            {resultado.recibidos} recibidos: {resultado.nuevos} nuevos, {resultado.actualizados} actualizados, {resultado.sin_cambios} sin cambios
            {resultado.duplicados ? `, ${resultado.duplicados} duplicados de otro evento` : ''}
            {resultado.omitidos ? `, ${resultado.omitidos} descartados por vos` : ''}.
            {resultado.errores.length > 0 && (
              <ul className="mt-1 list-disc pl-4 text-app-warn">{resultado.errores.slice(0, 8).map(e => <li key={e}>{e}</li>)}</ul>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
