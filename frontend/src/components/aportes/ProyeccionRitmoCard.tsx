import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import type { AporteProyeccionRitmo } from '../../api'
import Card from '../ui/Card'
import Button from '../ui/Button'
import Segmented from '../ui/Segmented'
import InfoTooltip from '../../help/components/InfoTooltip'
import { formatUSD } from '../../utils'

const ORIGEN_TEXTO: Record<string, string> = {
  promedio_12: 'tu promedio de los últimos 12 meses',
  promedio_6: 'tu promedio de los últimos 6 meses',
  promedio_3: 'tu promedio de los últimos 3 meses',
  promedio_historico: 'tu promedio histórico',
}

/** "Si mantengo este ritmo": suma de aportes a 1/3/5/10 años, sin rendimiento.
 *
 *  No es una predicción y la tarjeta lo dice con todas las letras. El escenario de aumento sólo
 *  muestra plata aportada de más, nunca ganancias hipotéticas. */
export default function ProyeccionRitmoCard({ proyeccion }: { proyeccion: AporteProyeccionRitmo }) {
  const navigate = useNavigate()
  const [escenario, setEscenario] = useState('base')

  if (proyeccion.origen === 'insuficiente' || proyeccion.ritmo_mensual_usd == null) {
    return (
      <Card className="mb-4">
        <h3 className="text-body font-bold text-app-text mb-1">🚀 Si mantenés este ritmo</h3>
        <div className="text-caption text-app-text-dim">
          Todavía no hay un ritmo de aportes del que partir: con algunos meses de historial vas a
          ver acá cuánto llegarías a aportar.
        </div>
      </Card>
    )
  }

  const opciones = [
    { value: 'base', label: 'Tu ritmo' },
    ...proyeccion.escenarios_aumento.map(e => ({
      value: e.clave,
      label: `+${formatUSD(e.delta_mensual_usd)}`,
    })),
  ]
  const elegido = proyeccion.escenarios_aumento.find(e => e.clave === escenario)
  const horizontes = elegido ? elegido.horizontes : proyeccion.horizontes
  const ritmo = elegido ? elegido.ritmo_resultante_usd : proyeccion.ritmo_mensual_usd

  return (
    <Card className="mb-4">
      <div className="flex items-center justify-between gap-2 mb-1">
        <h3 className="text-body font-bold text-app-text">
          <InfoTooltip term="aportes_proyeccion_ritmo" label="🚀 Si mantenés este ritmo" />
        </h3>
      </div>
      <div className="text-caption text-app-text-dim mb-3">
        Partiendo de{' '}
        <span className="font-mono font-semibold text-app-text">{formatUSD(ritmo)}</span> por mes
        {!elegido && ORIGEN_TEXTO[proyeccion.origen] && <> · {ORIGEN_TEXTO[proyeccion.origen]}</>}
      </div>

      {proyeccion.escenarios_aumento.length > 0 && (
        <div className="mb-3">
          <Segmented options={opciones} value={escenario} onChange={setEscenario} />
        </div>
      )}

      <div className="grid grid-cols-2 gap-2">
        {horizontes.map(h => (
          <div key={h.anios} className="bg-app-surface-2 rounded-[13px] px-2.5 py-2">
            <div className="text-label font-bold uppercase tracking-wide text-app-text-faint">
              {h.anios} {h.anios === 1 ? 'año' : 'años'}
            </div>
            <div className="font-mono text-strong font-bold tabular-nums text-app-text">
              {formatUSD(h.total_usd)}
            </div>
            {h.extra_usd != null && (
              <div className="text-label text-app-pos">+{formatUSD(h.extra_usd)} aportados</div>
            )}
          </div>
        ))}
      </div>

      <div className="text-label text-app-text-faint mt-3">{proyeccion.disclaimer}</div>

      <Button
        variant="outline"
        className="w-full mt-3"
        onClick={() => navigate('/simulador', { state: { aporteMensualUsd: ritmo } })}
      >
        Simular con rendimiento
      </Button>
    </Card>
  )
}
