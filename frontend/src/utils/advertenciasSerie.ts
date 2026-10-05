/**
 * Las advertencias de una serie técnica, en palabras.
 *
 * El backend las manda como códigos (`serie_con_huecos`, `posible_split`…) y la UI las mostraba
 * crudas, unidas por " · ". Un código no le dice nada a nadie, y la de split menos que ninguna:
 * es justamente la que necesita explicar por qué el gráfico tiene un escalón.
 */
const TEXTOS: Record<string, string> = {
  serie_con_huecos: 'La serie tiene días sin precio: el gráfico une los extremos del hueco.',
  moneda_mixta: 'La serie mezcla monedas distintas; compará con cuidado.',
  posible_split:
    'Hay un salto compatible con un split no ajustado: el precio cambia de escala de un día al ' +
    'otro sin que haya pasado nada. Los indicadores lo leen como un movimiento real.',
  un_solo_punto: 'Este ticker tiene un solo precio registrado: no alcanza para graficar.',
  sin_serie: 'Todavía no hay datos históricos para este ticker.',
}

/** El texto de un código, o el código tal cual si no está traducido. */
export function textoAdvertenciaSerie(codigo: string): string {
  return TEXTOS[codigo] ?? codigo
}

export function textosAdvertenciasSerie(codigos: string[]): string[] {
  return codigos.map(textoAdvertenciaSerie)
}
