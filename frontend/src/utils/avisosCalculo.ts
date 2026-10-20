/**
 * Avisos de "este número no se puede calcular bien". El backend manda un código por moneda
 * (`rendimiento_no_calculable`) y acá se traduce a una frase para el usuario; así el texto vive
 * en un solo lugar y la pantalla nunca muestra un porcentaje con cara de dato cuando el
 * cálculo no tiene sentido.
 */
export type MotivoRendimiento = 'capital_neto_negativo' | 'capital_neto_chico'

const TEXTOS_RENDIMIENTO: Record<MotivoRendimiento, string> = {
  capital_neto_negativo:
    'Recuperaste más de lo que pusiste en neto (ventas mayores que compras): el % sobre el capital ' +
    'no tiene sentido. Mirá la TIR y la ganancia en dinero.',
  capital_neto_chico:
    'Te queda muy poco capital invertido en neto respecto de lo que compraste: el % sobre ese ' +
    'capital se dispara y no es comparable. Mirá la TIR y la ganancia en dinero.',
}

export function avisoRendimiento(
  motivos: Record<string, string> | undefined | null,
  moneda: 'usd' | 'ars' | 'ars_real',
): string | null {
  const motivo = motivos?.[moneda] as MotivoRendimiento | undefined
  return motivo ? TEXTOS_RENDIMIENTO[motivo] ?? null : null
}
