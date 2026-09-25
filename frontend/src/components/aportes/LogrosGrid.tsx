import { useState } from 'react'
import type { AporteLogro } from '../../api'
import Card from '../ui/Card'
import Button from '../ui/Button'
import BarraProgreso from '../ui/BarraProgreso'
import InfoTooltip from '../../help/components/InfoTooltip'
import { formatUSD } from '../../utils'
import { mesCorto } from './comun'

const VISIBLES_POR_DEFECTO = 6

function valorTexto(logro: AporteLogro, valor: number): string {
  return logro.unidad === 'usd' ? formatUSD(valor) : String(Math.round(valor))
}

function LogroFila({ logro }: { logro: AporteLogro }) {
  const bloqueadoSinObjetivo = logro.bloqueado_por_falta_objetivo && !logro.desbloqueado

  return (
    <div
      className={`rounded-[13px] border px-2.5 py-2.5 ${
        logro.desbloqueado
          ? 'bg-app-surface border-app-border'
          : 'bg-app-surface-2/40 border-app-border-soft'
      }`}
    >
      <div className="flex items-start gap-2">
        <span
          className={`text-title leading-none ${logro.desbloqueado ? '' : 'grayscale opacity-40'}`}
          aria-hidden="true"
        >
          {logro.emoji}
        </span>
        <div className="min-w-0 flex-1">
          <div className={`text-caption font-bold ${logro.desbloqueado ? 'text-app-text' : 'text-app-text-dim'}`}>
            {logro.titulo}
          </div>
          {logro.desbloqueado ? (
            <div className="text-label text-app-text-faint">
              ✓ Conseguido{logro.fecha ? ` · ${mesCorto(logro.fecha)}` : ''}
            </div>
          ) : bloqueadoSinObjetivo ? (
            <div className="text-label text-app-text-faint">Definí un objetivo mensual para medirlo</div>
          ) : (
            <>
              <div className="mt-1">
                <BarraProgreso pct={logro.progreso_pct} alto="fino" />
              </div>
              <div className="text-label text-app-text-faint mt-1 font-mono tabular-nums">
                {valorTexto(logro, logro.actual ?? 0)} / {valorTexto(logro, logro.objetivo)}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}

/** Logros conseguidos y por conseguir. Los bloqueados muestran su progreso real: la idea es que
 *  se vea lo que falta, no que se escondan. */
export default function LogrosGrid({ logros }: { logros: AporteLogro[] }) {
  const [verTodos, setVerTodos] = useState(false)

  const conseguidos = logros.filter(l => l.desbloqueado).length
  const visibles = verTodos ? logros : logros.slice(0, VISIBLES_POR_DEFECTO)

  return (
    <Card className="mb-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-body font-bold text-app-text">
          <InfoTooltip term="aportes_logros" label="🏅 Logros" />
        </h3>
        <span className="font-mono text-caption tabular-nums text-app-text-dim">
          {conseguidos} / {logros.length}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-2">
        {visibles.map(l => (
          <LogroFila key={l.clave} logro={l} />
        ))}
      </div>

      {logros.length > VISIBLES_POR_DEFECTO && (
        <Button variant="ghost" className="w-full mt-2" onClick={() => setVerTodos(v => !v)}>
          {verTodos ? 'Ver menos' : `Ver los ${logros.length}`}
        </Button>
      )}
    </Card>
  )
}
