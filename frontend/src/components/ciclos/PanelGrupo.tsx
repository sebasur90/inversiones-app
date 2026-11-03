import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, XAxis, YAxis } from 'recharts'
import type { CicloGrupoPanorama } from '../../api'
import InfoTooltip from '../../help/components/InfoTooltip'
import Button from '../ui/Button'
import Modal from '../ui/Modal'
import { fechaCorta } from '../../utils/fechas'
import BadgeCuadrante from './BadgeCuadrante'
import MetricasGrupo from './MetricasGrupo'
import { fmtPct } from './constantes'

interface Props {
  grupo: CicloGrupoPanorama | null
  benchmarkNombre: string | null
  onClose: () => void
  onVerDetalle: (id: string) => void
}

const HORIZONTES = ['1M', '3M', '6M', '1A', '3A']

/** Al tocar un punto del mapa: dónde está, cómo viene rindiendo y cómo se movió en las últimas semanas. */
export default function PanelGrupo({ grupo, benchmarkNombre, onClose, onVerDetalle }: Props) {
  if (!grupo) return null
  const rrg = grupo.rrg
  const tray = rrg.trayectoria ?? []
  return (
    <Modal open onClose={onClose} title={grupo.nombre}>
      <div className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <BadgeCuadrante cuadrante={rrg.actual?.cuadrante} pendiente={!!rrg.pendiente && rrg.pendiente.cuadrante === rrg.actual?.cuadrante} />
          <span className="text-label text-app-text-dim">
            medido con {grupo.proxy ?? 'su serie'} · contra {benchmarkNombre ?? 'sin referencia'}
          </span>
        </div>

        {rrg.estado !== 'ok' && (
          <div className="rounded-lg border border-app-warn/30 bg-app-warn/10 px-2.5 py-2 text-caption text-app-text-dim">
            {rrg.motivo ?? 'Sin datos suficientes para ubicar a este grupo en el mapa.'}
          </div>
        )}

        {rrg.cuadrante_confirmado && rrg.cuadrante_confirmado !== rrg.actual?.cuadrante && (
          <p className="text-caption text-app-text-dim">
            El último estado <InfoTooltip term="ciclos_cambio_confirmado" label="confirmado" /> fue <BadgeCuadrante cuadrante={rrg.cuadrante_confirmado} />; el actual
            todavía no se sostuvo varias semanas.
          </p>
        )}

        <MetricasGrupo rrg={rrg} rendimientos={grupo.rendimientos} riesgo={grupo.riesgo} tendencia={grupo.tendencia} />

        <div>
          <div className="text-label font-bold uppercase text-app-text-faint mb-1">Rendimiento por horizonte</div>
          <div className="grid grid-cols-5 gap-1 text-center">
            {HORIZONTES.map(h => {
              const c = grupo.rendimientos[h]
              return (
                <div key={h} className="rounded-lg border border-app-border px-1 py-1.5">
                  <div className="text-label text-app-text-faint font-bold">{h}</div>
                  <div className={`font-mono tabular-nums text-label ${c?.absoluto == null ? 'text-app-text-faint' : c.absoluto >= 0 ? 'text-app-pos' : 'text-app-neg'}`}>
                    {fmtPct(c?.absoluto, 1)}
                  </div>
                  <div className="font-mono tabular-nums text-label text-app-text-faint" title="Relativo a la referencia">
                    {fmtPct(c?.relativo, 1)}
                  </div>
                </div>
              )
            })}
          </div>
          <div className="text-label text-app-text-faint mt-1">Arriba el absoluto; abajo, relativo a la referencia. «—» = sin datos suficientes.</div>
        </div>

        {tray.length > 1 && (
          <div>
            <div className="text-label font-bold uppercase text-app-text-faint mb-1">
              <InfoTooltip term="ciclos_trayectoria" label="Posición en las últimas semanas" />
            </div>
            <ResponsiveContainer width="100%" height={120}>
              <LineChart data={tray} margin={{ top: 4, right: 6, left: 0, bottom: 0 }}>
                <CartesianGrid stroke="#1c1f2a" strokeDasharray="3 3" />
                <XAxis dataKey="fecha" tick={{ fontSize: 10, fill: '#94a3b8' }} tickFormatter={(f: string) => `${f.slice(8, 10)}/${f.slice(5, 7)}`} minTickGap={24} />
                <YAxis tick={{ fontSize: 10, fill: '#94a3b8' }} width={30} domain={['auto', 'auto']} tickFormatter={(v: number) => v.toFixed(0)} />
                <ReferenceLine y={100} stroke="#64748b" />
                <Line type="monotone" dataKey="rs_ratio" stroke="#60a5fa" strokeWidth={2} dot={{ r: 2 }} isAnimationActive={false} />
                <Line type="monotone" dataKey="rs_momentum" stroke="#fbbf24" strokeWidth={2} dot={{ r: 2 }} isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
            <div className="text-label text-app-text-faint">Azul: fortaleza relativa · Ámbar: momentum relativo · 100 = neutral</div>
          </div>
        )}

        <div className="text-label text-app-text-faint">
          Último dato: {grupo.ultima_fecha ? fechaCorta(grupo.ultima_fecha) : 'sin datos'} ·{' '}
          {grupo.tipo_rendimiento === 'total' ? 'retorno total' : 'retorno de precio'}
          {grupo.nota ? ` · ${grupo.nota}` : ''}
        </div>

        <Button variant="outline" onClick={() => onVerDetalle(grupo.id)}>
          Ver ficha completa
        </Button>
      </div>
    </Modal>
  )
}
