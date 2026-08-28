import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useInversionesContext } from '../context/InversionesContext'
import { getVistaFiscalPorAnio, type VistaFiscalPorAnioOut } from '../api'
import { formatARS, formatUSD } from '../utils'
import ScreenHeader from '../components/layout/ScreenHeader'
import Card from '../components/ui/Card'
import EmptyState from '../components/ui/EmptyState'
import BotonExportarCsv from '../components/ui/BotonExportarCsv'
import { Icon } from '../components/icons/Icons'

function toneClass(v: number): string {
  if (v > 0) return 'text-app-teal'
  if (v < 0) return 'text-app-coral'
  return 'text-app-text'
}

export default function VistaFiscal() {
  const navigate = useNavigate()
  const { carteraSeleccionada, monedaSeleccionada, syncVersion } = useInversionesContext()
  const [datos, setDatos] = useState<VistaFiscalPorAnioOut | null>(null)
  const [loading, setLoading] = useState(true)
  const [expandidos, setExpandidos] = useState<Set<number>>(new Set())

  useEffect(() => {
    let cancelado = false
    setLoading(true)
    getVistaFiscalPorAnio(carteraSeleccionada)
      .then(data => {
        if (!cancelado) setDatos(data)
      })
      .catch(() => {
        if (!cancelado) setDatos(null)
      })
      .finally(() => {
        if (!cancelado) setLoading(false)
      })
    return () => {
      cancelado = true
    }
  }, [carteraSeleccionada, syncVersion])

  const esARS = monedaSeleccionada === 'ARS'
  const fmt = esARS ? formatARS : formatUSD

  const filasCsv = useMemo(
    () => () => {
      if (!datos) return []
      const filas: (string | number)[][] = []
      for (const a of datos.por_anio) {
        filas.push([a.anio, 'TOTAL', '', a.realizado_usd, a.realizado_ars, a.ingresos_usd, a.ingresos_ars, a.comisiones_usd, a.comisiones_ars, a.resultado_usd, a.resultado_ars])
        for (const t of a.por_ticker) {
          filas.push([a.anio, t.ticker, t.nombre, t.realizado_usd, t.realizado_ars, t.ingresos_usd, t.ingresos_ars, t.comisiones_usd, t.comisiones_ars, '', ''])
        }
      }
      return filas
    },
    [datos],
  )

  if (loading) {
    return (
      <div className="pb-4">
        <ScreenHeader title="Vista fiscal" onBack={() => navigate(-1)} />
        <div className="py-20 text-center text-app-text-dim text-[13px]">Cargando…</div>
      </div>
    )
  }

  if (!datos || datos.por_anio.length === 0) {
    return (
      <div className="pb-4">
        <ScreenHeader title="Vista fiscal" onBack={() => navigate(-1)} />
        <EmptyState
          title="Sin resultados por año"
          description="No hay ventas, amortizaciones ni dividendos/cupones registrados en esta cartera."
        />
      </div>
    )
  }

  const total = datos.total
  const totResultado = esARS ? total.resultado_ars : total.resultado_usd

  const toggle = (anio: number) =>
    setExpandidos(prev => {
      const next = new Set(prev)
      if (next.has(anio)) next.delete(anio)
      else next.add(anio)
      return next
    })

  return (
    <div className="pb-4">
      <ScreenHeader title="Vista fiscal" onBack={() => navigate(-1)} />

      <Card className="mb-3">
        <div className="text-[10px] font-bold uppercase tracking-wide text-app-text-faint mb-1">
          Resultado acumulado ({esARS ? 'ARS' : 'USD'})
        </div>
        <div className={`font-mono text-[26px] font-bold tabular-nums ${toneClass(totResultado)}`}>
          {fmt(totResultado)}
        </div>
        <div className="text-[11px] text-app-text-dim mt-1 tabular-nums">
          Realizado {fmt(esARS ? total.realizado_ars : total.realizado_usd)} · Ingresos{' '}
          {fmt(esARS ? total.ingresos_ars : total.ingresos_usd)} · Comisiones{' '}
          {fmt(esARS ? total.comisiones_ars : total.comisiones_usd)}
        </div>
      </Card>

      <div className="flex justify-end mb-2">
        <BotonExportarCsv
          nombre={`vista-fiscal-${carteraSeleccionada || 'consolidado'}`}
          encabezados={[
            'Año', 'Ticker', 'Nombre',
            'Realizado USD', 'Realizado ARS',
            'Ingresos USD', 'Ingresos ARS',
            'Comisiones USD', 'Comisiones ARS',
            'Resultado USD', 'Resultado ARS',
          ]}
          filas={filasCsv}
        />
      </div>

      <div className="flex flex-col gap-2">
        {datos.por_anio.map(a => {
          const abierto = expandidos.has(a.anio)
          const resultado = esARS ? a.resultado_ars : a.resultado_usd
          const realizado = esARS ? a.realizado_ars : a.realizado_usd
          const ingresos = esARS ? a.ingresos_ars : a.ingresos_usd
          const comisiones = esARS ? a.comisiones_ars : a.comisiones_usd
          return (
            <Card key={a.anio} className="!p-0 overflow-hidden">
              <button
                onClick={() => toggle(a.anio)}
                className="w-full flex items-center justify-between px-4 py-3 text-left"
              >
                <div className="flex items-center gap-2">
                  <Icon
                    name="chevron"
                    className={`w-3.5 h-3.5 text-app-text-faint transition-transform ${abierto ? 'rotate-0' : '-rotate-90'}`}
                  />
                  <span className="text-[15px] font-bold text-app-text tabular-nums">{a.anio}</span>
                </div>
                <div className={`font-mono font-bold text-[15px] tabular-nums ${toneClass(resultado)}`}>
                  {fmt(resultado)}
                </div>
              </button>

              <div className="grid grid-cols-3 gap-2 px-4 pb-3 text-center">
                <div>
                  <div className="text-[9.5px] font-bold uppercase tracking-wide text-app-text-faint">Realizado</div>
                  <div className={`font-mono text-[12px] font-semibold tabular-nums ${toneClass(realizado)}`}>{fmt(realizado)}</div>
                </div>
                <div>
                  <div className="text-[9.5px] font-bold uppercase tracking-wide text-app-text-faint">Ingresos</div>
                  <div className="font-mono text-[12px] font-semibold tabular-nums text-app-text">{fmt(ingresos)}</div>
                </div>
                <div>
                  <div className="text-[9.5px] font-bold uppercase tracking-wide text-app-text-faint">Comisiones</div>
                  <div className="font-mono text-[12px] font-semibold tabular-nums text-app-text-dim">{fmt(comisiones)}</div>
                </div>
              </div>

              {abierto && (
                <div className="border-t border-app-border">
                  <div className="grid grid-cols-[1fr_auto_auto_auto] gap-x-3 gap-y-1.5 px-4 py-3 text-[11px]">
                    <div className="text-app-text-faint font-bold uppercase tracking-wide text-[9.5px]">Ticker</div>
                    <div className="text-app-text-faint font-bold uppercase tracking-wide text-[9.5px] text-right">Realizado</div>
                    <div className="text-app-text-faint font-bold uppercase tracking-wide text-[9.5px] text-right">Ingresos</div>
                    <div className="text-app-text-faint font-bold uppercase tracking-wide text-[9.5px] text-right">Comis.</div>
                    {a.por_ticker.map(t => {
                      const r = esARS ? t.realizado_ars : t.realizado_usd
                      const i = esARS ? t.ingresos_ars : t.ingresos_usd
                      const c = esARS ? t.comisiones_ars : t.comisiones_usd
                      return (
                        <div key={t.ticker} className="contents">
                          <button
                            onClick={() => navigate(`/ticker/${encodeURIComponent(t.ticker)}`)}
                            className="text-left min-w-0"
                          >
                            <div className="font-semibold text-app-text truncate">{t.ticker}</div>
                            <div className="text-[9.5px] text-app-text-dim truncate">{t.nombre}</div>
                          </button>
                          <div className={`font-mono tabular-nums text-right ${toneClass(r)}`}>{fmt(r)}</div>
                          <div className="font-mono tabular-nums text-right text-app-text">{fmt(i)}</div>
                          <div className="font-mono tabular-nums text-right text-app-text-dim">{fmt(c)}</div>
                        </div>
                      )
                    })}
                  </div>
                </div>
              )}
            </Card>
          )
        })}
      </div>

      <p className="text-[10.5px] text-app-text-dim mt-3 leading-relaxed">
        <strong>Realizado</strong>: resultado de ventas y amortizaciones del año (costo promedio),
        ya neto de la comisión de esas operaciones. <strong>Ingresos</strong>: dividendos y cupones
        cobrados en el año. <strong>Comisiones</strong>: caja pagada en el año por todas las
        operaciones (informativo — la comisión de compra está capitalizada en el costo y se realiza
        recién al vender; no se resta de <strong>Resultado</strong> = Realizado + Ingresos).
        Referencia interna, no constituye asesoramiento impositivo.
      </p>
    </div>
  )
}
