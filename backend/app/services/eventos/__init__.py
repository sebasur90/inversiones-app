"""Calendario de eventos de mercado: acontecimientos pasados y futuros, noticias que los respaldan,
su relación con los instrumentos y el comportamiento observado del precio alrededor de cada uno.

Ver `docs/calendario-eventos.md`. Los valores válidos de cada campo viven acá, en un solo lugar: los
usan la validación, los schemas y los motores.

Nada de esto toca la fuente de verdad de la cartera (el Google Sheet): son tablas propias de la app.
"""

CATEGORIAS = (
    "elecciones", "politica", "geopolitica", "sanciones_aranceles", "regulacion", "banco_central",
    "dato_macro", "resultados", "corporativo", "crisis_financiera", "tecnologia_sector",
    "materias_primas", "otro",
)
ETIQUETA_CATEGORIA = {
    "elecciones": "Elecciones",
    "politica": "Política",
    "geopolitica": "Geopolítica y conflictos",
    "sanciones_aranceles": "Sanciones y aranceles",
    "regulacion": "Regulación",
    "banco_central": "Bancos centrales",
    "dato_macro": "Datos macro",
    "resultados": "Resultados de empresas",
    "corporativo": "Fusiones y anuncios corporativos",
    "crisis_financiera": "Crisis financieras",
    "tecnologia_sector": "Tecnología y sectores",
    "materias_primas": "Materias primas",
    "otro": "Otros",
}

PRECISIONES = ("exacta", "aproximada", "mes", "anio", "desconocida")
ESTADOS = ("previsto", "confirmado", "en_desarrollo", "concluido", "cancelado", "reprogramado")
VERIFICACIONES = (
    "sin_verificar", "fuente_oficial", "multiples_fuentes", "verificado_usuario", "catalogo_revisar", "rumor",
)
ORIGENES = ("manual", "catalogo", "calendario_oficial", "proveedor", "importacion")
CONFIANZAS = ("alta", "media", "baja")
IMPORTANCIAS = (1, 2, 3)

TIPOS_RELACION = ("directa", "matriz", "sector", "pais", "macro", "materia_prima", "indice", "otra")
METODOS_RELACION = ("manual", "automatico")
ESTADOS_REVISION = ("propuesta", "confirmada", "descartada")

ESTADOS_NOTICIA = ("por_revisar", "asociada", "descartada")

#: Campos de un evento que el usuario puede editar (y que, una vez editados, ningún proveedor pisa).
CAMPOS_EDITABLES = (
    "titulo", "descripcion", "resumen", "notas", "categoria", "subcategoria", "fecha_evento", "fecha_fin",
    "hora_evento", "zona_horaria", "fecha_publicacion", "precision_fecha", "programado", "pais", "region",
    "entidades", "importancia", "estado", "verificacion", "fuente_principal", "url_fuente",
)
