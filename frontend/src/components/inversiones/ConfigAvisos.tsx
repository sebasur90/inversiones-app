import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { getAvisosConfig, guardarAvisosConfig, guardarAvisosDeEstrategia } from '../../api'
import type { AvisoEstrategiaIn, AvisosConfigIn, AvisosConfigOut } from '../../api'
import { qk } from '../../api/queryClient'
import QueryBoundary from '../ui/QueryBoundary'
import { Skeleton } from '../ui/Skeleton'

/** Casilla de aviso: palabra + estado, nunca sólo un color. */
function Casilla({
  etiqueta,
  activa,
  onToggle,
  disabled,
  ayuda,
}: {
  etiqueta: string
  activa: boolean
  onToggle: () => void
  disabled?: boolean
  ayuda?: string
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={activa}
      aria-label={etiqueta}
      title={ayuda}
      disabled={disabled}
      onClick={onToggle}
      className={`inline-flex items-center gap-1.5 rounded-[9px] px-2.5 py-1.5 text-label font-bold transition-colors disabled:opacity-50 ${
        activa
          ? 'bg-app-accent-soft text-app-accent'
          : 'bg-app-surface-2 text-app-text-dim'
      }`}
    >
      <span
        aria-hidden="true"
        className={`w-1.5 h-1.5 rounded-full shrink-0 ${activa ? 'bg-app-accent' : 'bg-app-text-dim'}`}
      />
      {etiqueta}
    </button>
  )
}

const TIPOS_DE_NIVEL: { campo: keyof AvisosConfigIn; etiqueta: string; ayuda: string }[] = [
  {
    campo: 'avisar_stop_loss',
    etiqueta: 'Stop-loss',
    ayuda: 'Cuando una posición cae al límite de pérdida que le fijaste.',
  },
  {
    campo: 'avisar_objetivo',
    etiqueta: 'Objetivo',
    ayuda: 'Cuando una posición llega al precio de venta que le fijaste.',
  },
  {
    campo: 'avisar_compra_zona',
    etiqueta: 'Zona de compra',
    ayuda: 'Cuando un ticker de la watchlist baja al precio de compra que le fijaste.',
  },
]

/**
 * Qué avisa por Telegram: los tres tipos de nivel y, por estrategia, si avisa sus compras, sus
 * ventas o ninguna.
 *
 * Las estrategias arrancan todas apagadas a propósito: los 16 presets del catálogo se siembran
 * solos, y prenderlos todos serían decenas de mensajes por día. Apagar un tipo de nivel, en
 * cambio, **no** deja de seguirlo: el cruce se guarda igual y se silencia, así que volver a
 * prenderlo no manda de golpe todo lo que pasó mientras estaba apagado.
 */
export default function ConfigAvisos() {
  const queryClient = useQueryClient()
  const query = useQuery({ queryKey: qk.de('avisos-config'), queryFn: getAvisosConfig })

  const guardar = (datos: AvisosConfigOut) => {
    queryClient.setQueryData(qk.de('avisos-config'), datos)
    void queryClient.invalidateQueries({ queryKey: qk.de('alertas-estado') })
  }

  const nivelesMutation = useMutation({
    mutationFn: (cambios: AvisosConfigIn) => guardarAvisosConfig(cambios),
    onSuccess: guardar,
  })

  const estrategiaMutation = useMutation({
    mutationFn: ({ id, cambios }: { id: number; cambios: AvisoEstrategiaIn }) =>
      guardarAvisosDeEstrategia(id, cambios),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: qk.de('avisos-config') })
      void queryClient.invalidateQueries({ queryKey: qk.de('alertas-estado') })
    },
  })

  const config = query.data
  const conAviso = config?.estrategias.filter(e => e.notificar_compra || e.notificar_venta).length ?? 0

  return (
    <QueryBoundary
      isLoading={query.isLoading}
      error={query.error}
      onRetry={() => void query.refetch()}
      fallback={<Skeleton className="h-24" />}
    >
      {config && (
        <div className="flex flex-col gap-3">
          <div>
            <div className="text-label font-bold text-app-text-dim uppercase mb-1.5">
              Niveles de precio
            </div>
            <div className="flex flex-wrap gap-1.5">
              {TIPOS_DE_NIVEL.map(({ campo, etiqueta, ayuda }) => (
                <Casilla
                  key={campo}
                  etiqueta={etiqueta}
                  activa={Boolean(config[campo as keyof AvisosConfigOut])}
                  disabled={nivelesMutation.isPending}
                  onToggle={() =>
                    nivelesMutation.mutate({ [campo]: !config[campo as keyof AvisosConfigOut] })
                  }
                  ayuda={ayuda}
                />
              ))}
            </div>
            <div className="text-caption text-app-text-dim mt-1.5">
              Apagar uno deja de mandarlo, pero el nivel se sigue vigilando: al volver a prenderlo
              no llega de golpe todo lo que pasó mientras estaba apagado.
            </div>
          </div>

          <div>
            <div className="text-label font-bold text-app-text-dim uppercase mb-1.5">
              Señales de estrategias
            </div>
            {config.estrategias.length === 0 ? (
              <div className="text-caption text-app-text-dim">
                Todavía no hay estrategias guardadas. Se crean en Análisis técnico.
              </div>
            ) : (
              <>
                <div className="flex flex-col divide-y divide-app-border">
                  {config.estrategias.map(estrategia => (
                    <div
                      key={estrategia.id}
                      className="flex items-center justify-between gap-2 py-2 first:pt-0"
                    >
                      <div className="min-w-0">
                        <div className="text-body text-app-text truncate">{estrategia.nombre}</div>
                        <div className="text-caption text-app-text-dim">
                          {estrategia.ticker ?? 'cualquier ticker'}
                        </div>
                      </div>
                      <div className="flex gap-1.5 shrink-0">
                        <Casilla
                          etiqueta="Compras"
                          activa={estrategia.notificar_compra}
                          disabled={estrategiaMutation.isPending}
                          onToggle={() =>
                            estrategiaMutation.mutate({
                              id: estrategia.id,
                              cambios: { notificar_compra: !estrategia.notificar_compra },
                            })
                          }
                        />
                        <Casilla
                          etiqueta="Ventas"
                          activa={estrategia.notificar_venta}
                          disabled={estrategiaMutation.isPending}
                          onToggle={() =>
                            estrategiaMutation.mutate({
                              id: estrategia.id,
                              cambios: { notificar_venta: !estrategia.notificar_venta },
                            })
                          }
                        />
                      </div>
                    </div>
                  ))}
                </div>
                <div className="text-caption text-app-text-dim mt-1.5">
                  {conAviso === 0
                    ? 'Ninguna estrategia avisa todavía. Mientras no prendas ninguna, el servidor no las calcula.'
                    : `${conAviso} de ${config.estrategias.length} estrategias avisan. Sólo se avisan las señales de las últimas 2 ruedas.`}
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </QueryBoundary>
  )
}
