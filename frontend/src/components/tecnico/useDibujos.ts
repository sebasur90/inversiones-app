import { useCallback, useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { qk } from '../../api/queryClient'
import {
  borrarDibujo, crearDibujo, getDibujos, type DibujoIn, type DibujoOut, type TipoDibujo, type VarianteSerie,
} from '../../api'
import { parseApiError } from '../../help/errors/apiErrors'

export interface PuntoDibujo {
  fecha: string
  precio: number
}

/** Todo lo que el gráfico necesita para dibujar a mano: los dibujos guardados, la herramienta
 * elegida, el primer punto de un dibujo de dos y cuál está seleccionado. Vive en la pantalla (no en
 * el gráfico) para que sobreviva al pasar a pantalla completa, donde se monta otro gráfico. */
export interface ControlDibujos {
  lista: DibujoOut[]
  herramienta: TipoDibujo | null
  elegirHerramienta: (t: TipoDibujo | null) => void
  /** El primer toque de una línea de tendencia o de un Fibonacci, a la espera del segundo. */
  primerPunto: PuntoDibujo | null
  /** Un toque en modo dibujo: arma el dibujo y lo guarda cuando tiene todos sus puntos. */
  tocarPunto: (punto: PuntoDibujo) => void
  seleccionado: number | null
  seleccionar: (id: number | null) => void
  borrarSeleccionado: () => void
  guardando: boolean
  /** Último error del servidor (o `null`). */
  error: string | null
}

/** Un dibujo existe sobre una serie concreta: `variante` es la que muestra el gráfico. */
export function useDibujos(ticker: string | null, variante: VarianteSerie | undefined): ControlDibujos {
  const queryClient = useQueryClient()
  const [herramienta, setHerramienta] = useState<TipoDibujo | null>(null)
  const [primerPunto, setPrimerPunto] = useState<PuntoDibujo | null>(null)
  const [seleccionado, setSeleccionado] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)

  const clave = qk.de('tecnico-dibujos', ticker, variante)
  const consulta = useQuery({
    queryKey: clave,
    queryFn: () => getDibujos(ticker as string, variante as VarianteSerie),
    enabled: ticker !== null && variante !== undefined,
  })

  // Otro ticker u otra serie: lo que se estaba armando o seleccionado era de otra cosa.
  useEffect(() => {
    setHerramienta(null)
    setPrimerPunto(null)
    setSeleccionado(null)
    setError(null)
  }, [ticker, variante])

  const crear = useMutation({
    mutationFn: (body: DibujoIn) => crearDibujo(ticker as string, body),
    onSuccess: async nuevo => {
      await queryClient.invalidateQueries({ queryKey: clave })
      setSeleccionado(nuevo.id)
      setError(null)
    },
    onError: e => setError(parseApiError(e).message),
  })

  const borrar = useMutation({
    mutationFn: (id: number) => borrarDibujo(ticker as string, id),
    onSuccess: async () => {
      setSeleccionado(null)
      await queryClient.invalidateQueries({ queryKey: clave })
    },
    onError: e => setError(parseApiError(e).message),
  })

  const elegirHerramienta = useCallback((t: TipoDibujo | null) => {
    setHerramienta(t)
    setPrimerPunto(null)
    setSeleccionado(null)
    setError(null)
  }, [])

  const tocarPunto = useCallback((punto: PuntoDibujo) => {
    if (!herramienta || !variante) return
    if (herramienta === 'horizontal') {
      crear.mutate({ variante, tipo: 'horizontal', fecha1: punto.fecha, precio1: punto.precio, fecha2: null, precio2: null })
      setHerramienta(null)
      return
    }
    if (!primerPunto) {
      setPrimerPunto(punto)
      setError(null)
      return
    }
    // Un doble clic de mouse manda dos toques en la misma barra: el segundo se ignora en vez de
    // pedirle al servidor un dibujo de un solo día.
    if (punto.fecha === primerPunto.fecha) return
    crear.mutate({
      variante, tipo: herramienta, fecha1: primerPunto.fecha, precio1: primerPunto.precio,
      fecha2: punto.fecha, precio2: punto.precio,
    })
    setPrimerPunto(null)
    setHerramienta(null)
  }, [crear, herramienta, primerPunto, variante])

  const borrarSeleccionado = useCallback(() => {
    if (seleccionado != null) borrar.mutate(seleccionado)
  }, [borrar, seleccionado])

  const lista = consulta.data ?? []
  return {
    lista,
    herramienta,
    elegirHerramienta,
    primerPunto,
    tocarPunto,
    // Si el dibujo seleccionado ya no existe (se borró desde otro lado), no queda seleccionado nada.
    seleccionado: seleccionado != null && lista.some(d => d.id === seleccionado) ? seleccionado : null,
    seleccionar: setSeleccionado,
    borrarSeleccionado,
    guardando: crear.isPending || borrar.isPending,
    error,
  }
}
