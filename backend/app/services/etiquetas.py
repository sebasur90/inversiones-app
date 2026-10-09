"""Etiquetas de los buckets residuales de las agrupaciones por eje.

Viven acá, sin dependencias, para que las compartan los analytics (que las producen) y los
motores puros (que tienen que reconocerlas para no confundirlas con una categoría real: "el
60% de la cartera está en Sin país" no es concentración geográfica, es ficha incompleta).

Una posición entra siempre al total con una de estas etiquetas en vez de quedar afuera del eje:
así cualquier eje suma el patrimonio completo, el mismo que informa la pantalla principal.
"""

SIN_CLASIFICAR = "Sin clasificar"   # sin ficha en la hoja Instrumentos
SIN_SECTOR = "Sin sector"
SIN_PAIS = "Sin país"
SIN_VENCIMIENTO = "Sin vencimiento"  # no vence (acciones, CEDEARs) o no está cargado

# Para los motores que necesitan descartar buckets residuales sin saber de qué eje vienen.
BUCKETS_RESIDUALES = frozenset({SIN_CLASIFICAR, SIN_SECTOR, SIN_PAIS, SIN_VENCIMIENTO})
