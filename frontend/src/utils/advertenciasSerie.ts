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
  // Motivos que deja anotado el pipeline de market data cuando la serie queda vacía: sin esto,
  // "no hay datos históricos" no distingue un problema que se arregla solo del que necesita algo.
  sin_fuente_historica:
    'Ninguna de las fuentes de velas (analisistecnico, Yahoo, IOL) tiene la serie de este ' +
    'símbolo. Se reintenta cada 90 días; el gráfico va a crecer con lo que se acumule de acá en más.',
  escala_desconocida:
    'La serie que devolvió la fuente no concuerda con el precio que muestra la app, así que se ' +
    'descartó para no graficar en otra unidad. Probá refrescar el precio del instrumento.',
  subyacente_sin_subyacente:
    'No se pudo identificar el instrumento subyacente en EE.UU. para este ticker.',
  referencia_degradada:
    'La serie de referencia de este instrumento (el precio en dólares de la acción en EE.UU.) ' +
    'todavía no tiene datos: se muestra la serie local. Se completa en el próximo sync.',
  subyacente_ticker_no_apto:
    'Este instrumento no tiene un subyacente en EE.UU. (es renta fija o un activo local).',
}

/** El texto de un código, o el código tal cual si no está traducido. */
export function textoAdvertenciaSerie(codigo: string): string {
  return TEXTOS[codigo] ?? codigo
}

export function textosAdvertenciasSerie(codigos: string[]): string[] {
  return codigos.map(textoAdvertenciaSerie)
}
