import type { CicloGrupoPanorama } from '../../api'
import { fmtPct } from './constantes'
import BadgeCuadrante from './BadgeCuadrante'

/** Un grupo en una lista: estado de rotación, rendimiento de 1 año y qué tanto le ganó o perdió a la referencia. */
export default function TarjetaGrupo({ g, padre, onClick }: { g: CicloGrupoPanorama; padre?: string | null; onClick: () => void }) {
  const r = g.rendimientos['1A']
  const tono = (v: number | null | undefined) => (v == null ? 'text-app-text-faint' : v >= 0 ? 'text-app-pos' : 'text-app-neg')
  return (
    <button type="button" onClick={onClick} className="w-full rounded-xl border border-app-border bg-app-surface px-3 py-2.5 text-left active:scale-[0.99]">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="text-caption font-semibold text-app-text truncate">{g.nombre}</div>
          <div className="text-label text-app-text-faint truncate">
            {g.proxy ?? 'sintético'}
            {padre ? ` · dentro de ${padre}` : ''}
            {g.lista_curada ? ' · lista curada' : ''}
          </div>
        </div>
        {g.rrg.estado === 'ok' ? (
          <BadgeCuadrante cuadrante={g.rrg.actual?.cuadrante} pendiente={!!g.rrg.pendiente && g.rrg.pendiente.cuadrante === g.rrg.actual?.cuadrante} />
        ) : (
          <span className="text-label text-app-text-faint text-right max-w-[140px]">{g.rrg.estado === 'sin_datos' ? 'Sin datos' : g.rrg.estado === 'desactualizado' ? 'Desactualizado' : 'Historia insuficiente'}</span>
        )}
      </div>
      <div className="flex items-center gap-4 mt-1.5 text-label">
        <span className="text-app-text-faint">
          1A <b className={`font-mono tabular-nums ${tono(r?.absoluto)}`}>{fmtPct(r?.absoluto)}</b>
        </span>
        <span className="text-app-text-faint">
          vs. ref. <b className={`font-mono tabular-nums ${tono(r?.relativo)}`}>{fmtPct(r?.relativo)}</b>
        </span>
      </div>
    </button>
  )
}
