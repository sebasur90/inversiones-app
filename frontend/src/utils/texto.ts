/** Sin acentos y en minúsculas: buscar "exposicion" tiene que encontrar "Exposición". Un solo
 *  lugar para este criterio — antes vivía duplicado dentro de `BuscadorGlobal`. */
export function normalizarTexto(texto: string): string {
  return texto.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase()
}
