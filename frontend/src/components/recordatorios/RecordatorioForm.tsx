import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import dayjs from 'dayjs'
import { crearRecordatorio, editarRecordatorio, type Recordatorio, type RecordatorioIn } from '../../api'
import { qk } from '../../api/queryClient'
import { parseApiError } from '../../help/errors/apiErrors'
import Button from '../ui/Button'
import Campo, { CLASE_AREA, CLASE_INPUT } from '../ui/Campo'
import Chip from '../ui/Chip'

const MAX_TICKERS = 20

/**
 * Alta y edición. `inicial` precarga el alta cuando se llega desde otra pantalla (un evento del
 * calendario, un ticker de la watchlist).
 */
export default function RecordatorioForm({ recordatorio, inicial, onListo, onCancelar }: {
  recordatorio?: Recordatorio | null
  inicial?: Partial<RecordatorioIn>
  onListo: (r: Recordatorio) => void
  onCancelar: () => void
}) {
  const qc = useQueryClient()
  const [titulo, setTitulo] = useState(recordatorio?.titulo ?? inicial?.titulo ?? '')
  const [fecha, setFecha] = useState(recordatorio?.fecha ?? inicial?.fecha ?? '')
  const [hora, setHora] = useState(recordatorio?.hora ?? '')
  const [nota, setNota] = useState(recordatorio?.nota ?? inicial?.nota ?? '')
  const [tickers, setTickers] = useState<string[]>(recordatorio?.tickers ?? inicial?.tickers ?? [])
  const [nuevoTicker, setNuevoTicker] = useState('')

  const agregarTicker = () => {
    const t = nuevoTicker.trim().toUpperCase()
    if (t && !tickers.includes(t) && tickers.length < MAX_TICKERS) setTickers([...tickers, t])
    setNuevoTicker('')
  }

  const guardar = useMutation({
    mutationFn: () => {
      // Un ticker escrito y sin confirmar con "+" también cuenta: es lo que se ve en la pantalla al guardar.
      const pendiente = nuevoTicker.trim().toUpperCase()
      const todos = pendiente && !tickers.includes(pendiente) ? [...tickers, pendiente].slice(0, MAX_TICKERS) : tickers
      const body = { titulo: titulo.trim(), fecha, hora: hora || null, nota: nota.trim() || null, tickers: todos }
      return recordatorio ? editarRecordatorio(recordatorio.id, body) : crearRecordatorio({ ...body, evento_id: inicial?.evento_id ?? null })
    },
    onSuccess: r => {
      void qc.invalidateQueries({ queryKey: qk.de('recordatorios') })
      onListo(r)
    },
  })
  const error = guardar.error ? parseApiError(guardar.error) : null
  const valido = titulo.trim() && fecha

  return (
    <form onSubmit={e => { e.preventDefault(); if (valido) guardar.mutate() }}>
      <Campo etiqueta="Qué querés que te recuerde">
        <input value={titulo} onChange={e => setTitulo(e.target.value)} maxLength={200} required className={CLASE_INPUT} placeholder="Ej.: Revisar acciones después de las elecciones" />
      </Campo>
      <div className="grid grid-cols-2 gap-2">
        <Campo etiqueta="Fecha">
          <input type="date" value={fecha} min={recordatorio ? undefined : dayjs().format('YYYY-MM-DD')} onChange={e => setFecha(e.target.value)} required className={CLASE_INPUT} />
        </Campo>
        <Campo etiqueta="Hora (opcional)">
          <input type="time" value={hora} onChange={e => setHora(e.target.value)} className={CLASE_INPUT} />
        </Campo>
      </div>
      <p className="-mt-2 mb-3 text-label text-app-text-faint">Sin hora, avisa a las 9:00. El mensaje puede demorar hasta 5 minutos.</p>
      <Campo etiqueta="Nota (opcional)">
        <textarea value={nota} onChange={e => setNota(e.target.value)} maxLength={1000} rows={3} className={CLASE_AREA} placeholder="Qué mirar, por qué, en qué condiciones entrar…" />
      </Campo>

      <div className="mb-3">
        <span className="text-label font-bold uppercase tracking-wide text-app-text-faint">Tickers (opcional)</span>
        <div className="mt-1 flex gap-2">
          <input value={nuevoTicker} onChange={e => setNuevoTicker(e.target.value.toUpperCase())} maxLength={20}
            onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); agregarTicker() } }}
            className={`${CLASE_INPUT} flex-1`} placeholder="AAPL, GGAL…" aria-label="Ticker" />
          <Button type="button" variant="outline" onClick={agregarTicker} disabled={!nuevoTicker.trim() || tickers.length >= MAX_TICKERS}>+</Button>
        </div>
        {tickers.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1.5">
            {tickers.map(t => <Chip key={t} onRemove={() => setTickers(tickers.filter(x => x !== t))}>{t}</Chip>)}
          </div>
        )}
        <p className="mt-1 text-label text-app-text-faint">El mensaje incluye el último precio guardado de cada uno.</p>
      </div>

      {error && <p className="mb-3 text-caption text-app-neg">{error.message}</p>}
      <div className="flex gap-2">
        <Button type="button" variant="ghost" className="flex-1" onClick={onCancelar}>Cancelar</Button>
        <Button type="submit" className="flex-1" loading={guardar.isPending} disabled={!valido}>{recordatorio ? 'Guardar' : 'Crear recordatorio'}</Button>
      </div>
    </form>
  )
}
