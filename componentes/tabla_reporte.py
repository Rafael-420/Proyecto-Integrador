"""Tablas de la pantalla de reportes.

Antes los reportes usaban ft.DataTable dentro de un Row con scroll
horizontal. En el celular eso se veía mal: cada fila medía hasta 90 px
de alto, solo cabían dos columnas y el resto quedaba escondido detrás
de un scroll horizontal que casi nadie descubre (en "Más vendidos" no
se veían Unidades ni Ingreso).

Este componente dibuja lo mismo de dos formas:

  - Escritorio: una tabla compacta con encabezado lila, filas alternadas
    y números alineados a la derecha. Las columnas reparten el ancho
    disponible (flex), así que no hace falta scroll horizontal.
  - Celular: una tarjeta por registro. El dato principal va como título,
    el dato destacado (por ejemplo el ingreso) a la derecha, y el resto
    en pares etiqueta/valor debajo.

Con muchas filas se muestran por páginas ("Ver más").

Uso:

    columnas = [
        ColumnaReporte("Producto", flex=3, principal=True),
        ColumnaReporte("Órdenes", alinear="der"),
        ColumnaReporte("Ingreso", alinear="der", destacada=True),
    ]
    filas = [["Taro Milk Tea", "4", "$ 260.00"], ...]
    control = tabla_reporte(page, columnas, filas)
"""

from __future__ import annotations

import flet as ft

from componentes.layout_sidebar import es_pantalla_angosta
from utilidades.flet_compat import set_texto_boton

COLOR_LILA = "#C86DD7"
COLOR_LILA_OSCURO = "#6B21A8"
COLOR_LILA_SUAVE = "#F3E9F7"
COLOR_FILA_ALTERNA = "#FCF8FE"
COLOR_BORDE = "#EADCF0"
COLOR_TEXTO = "#3A2E42"
COLOR_TEXTO_SUAVE = "#7A6C85"

FILAS_POR_PAGINA = 20


# ------------------------------------------------------------
# Compatibilidad entre versiones de Flet
# ------------------------------------------------------------
def _relleno(horizontal=0, vertical=0):
    try:
        return ft.Padding(left=horizontal, top=vertical, right=horizontal, bottom=vertical)
    except Exception:
        return horizontal


def _borde(ancho, color):
    try:
        lado = ft.BorderSide(ancho, color)
        return ft.Border(top=lado, right=lado, bottom=lado, left=lado)
    except Exception:
        return None


def _borde_inferior(ancho, color):
    try:
        return ft.Border(bottom=ft.BorderSide(ancho, color))
    except Exception:
        return None


_DERECHA = ft.Alignment(1, 0)
_IZQUIERDA = ft.Alignment(-1, 0)


# ------------------------------------------------------------
# Definición de columnas y celdas
# ------------------------------------------------------------
class ColumnaReporte:
    """Una columna de la tabla.

    flex:      cuánto ancho ocupa en escritorio, en proporción a las demás.
    alinear:   "izq" o "der" (los números van a la derecha).
    principal: es el título de la tarjeta en el celular.
    destacada: en el celular va a la derecha del título, en grande.
    en_movil:  False para no mostrarla en las tarjetas del celular (por
               ejemplo, el número de posición, que ya se ve por el orden).
    """

    def __init__(self, titulo: str, flex: int = 1, alinear: str = "izq",
                 principal: bool = False, destacada: bool = False, en_movil: bool = True):
        self.titulo = titulo
        self.flex = flex
        self.alinear = alinear
        self.principal = principal
        self.destacada = destacada
        self.en_movil = en_movil


class Celda:
    """Valor de una celda con formato opcional.

    color: color del texto.
    fondo: si se indica, el valor se dibuja como etiqueta (píldora)
           con ese fondo, por ejemplo para estados "Crítico" / "Correcto".
    barra: número de 0 a 1; dibuja una barra de proporción debajo del
           texto (por ejemplo, ventas de un producto contra el más vendido).
    """

    def __init__(self, texto, color: str | None = None, fondo: str | None = None,
                 negrita: bool = False, barra: float | None = None, max_lineas: int = 2):
        self.texto = "" if texto is None else str(texto)
        self.color = color
        self.fondo = fondo
        self.negrita = negrita
        self.barra = barra
        self.max_lineas = max_lineas


def _como_celda(valor) -> Celda:
    return valor if isinstance(valor, Celda) else Celda(valor)


# ------------------------------------------------------------
# Dibujo de una celda
# ------------------------------------------------------------
def _contenido_celda(celda: Celda, alinear: str, tamano: int = 13) -> ft.Control:
    alineacion_texto = ft.TextAlign.RIGHT if alinear == "der" else ft.TextAlign.LEFT

    if celda.fondo:
        return ft.Container(
            bgcolor=celda.fondo,
            border_radius=999,
            padding=_relleno(10, 3),
            content=ft.Text(
                celda.texto,
                size=12,
                weight=ft.FontWeight.BOLD,
                color=celda.color or COLOR_TEXTO,
                no_wrap=True,
            ),
        )

    texto = ft.Text(
        celda.texto,
        size=tamano,
        color=celda.color or COLOR_TEXTO,
        weight=ft.FontWeight.BOLD if celda.negrita else None,
        text_align=alineacion_texto,
        max_lines=celda.max_lineas,
        overflow=ft.TextOverflow.ELLIPSIS,
    )
    if celda.barra is None:
        return texto

    return ft.Column(
        controls=[
            texto,
            ft.ProgressBar(
                value=max(0.0, min(1.0, float(celda.barra))),
                color=COLOR_LILA,
                bgcolor=COLOR_LILA_SUAVE,
                bar_height=6,
                border_radius=4,
            ),
        ],
        spacing=6,
        tight=True,
    )


# ------------------------------------------------------------
# Escritorio: tabla compacta
# ------------------------------------------------------------
def _celda_tabla(columna: ColumnaReporte, contenido: ft.Control) -> ft.Container:
    return ft.Container(
        expand=columna.flex,
        alignment=_DERECHA if columna.alinear == "der" else _IZQUIERDA,
        content=contenido,
    )


def _tabla_escritorio(columnas, filas) -> list[ft.Control]:
    encabezado = ft.Container(
        bgcolor=COLOR_LILA_SUAVE,
        padding=_relleno(16, 12),
        content=ft.Row(
            spacing=16,
            controls=[
                _celda_tabla(
                    c,
                    ft.Text(
                        c.titulo.upper(),
                        size=11,
                        weight=ft.FontWeight.BOLD,
                        color=COLOR_LILA_OSCURO,
                        text_align=ft.TextAlign.RIGHT if c.alinear == "der" else ft.TextAlign.LEFT,
                    ),
                )
                for c in columnas
            ],
        ),
    )

    renglones = [encabezado]
    for indice, fila in enumerate(filas):
        renglones.append(
            ft.Container(
                bgcolor=COLOR_FILA_ALTERNA if indice % 2 else "white",
                padding=_relleno(16, 10),
                border=_borde_inferior(1, COLOR_BORDE),
                content=ft.Row(
                    spacing=16,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        _celda_tabla(c, _contenido_celda(_como_celda(valor), c.alinear))
                        for c, valor in zip(columnas, fila)
                    ],
                ),
            )
        )
    return renglones


# ------------------------------------------------------------
# Celular: una tarjeta por registro
# ------------------------------------------------------------
def _dato_compacto(columna: ColumnaReporte, celda: Celda) -> ft.Control:
    """"Órdenes 11" en una sola línea; los estados van como etiqueta."""
    if celda.fondo:
        return _contenido_celda(celda, "izq")
    return ft.Row(
        controls=[
            ft.Text(columna.titulo, size=11, color=COLOR_TEXTO_SUAVE),
            ft.Text(
                celda.texto,
                size=12,
                weight=ft.FontWeight.BOLD,
                color=celda.color or COLOR_TEXTO,
                max_lines=celda.max_lineas,
                overflow=ft.TextOverflow.ELLIPSIS,
            ),
        ],
        spacing=4,
        tight=True,
    )


def _tarjeta_movil(columnas, fila) -> ft.Container:
    """Tarjeta compacta: título y dato destacado arriba, el resto en una
    línea de datos cortos que se acomoda en renglones si no cabe."""
    principal = next((i for i, c in enumerate(columnas) if c.principal), 0)
    destacada = next((i for i, c in enumerate(columnas) if c.destacada), None)

    encabezado = [
        ft.Container(
            expand=True,
            content=_contenido_celda(_como_celda(fila[principal]), "izq", tamano=14),
        )
    ]
    if destacada is not None:
        celda = _como_celda(fila[destacada])
        if celda.fondo:
            encabezado.append(_contenido_celda(celda, "der"))
        else:
            encabezado.append(
                ft.Text(
                    celda.texto,
                    size=15,
                    weight=ft.FontWeight.BOLD,
                    color=celda.color or COLOR_LILA_OSCURO,
                )
            )

    datos = [
        _dato_compacto(columna, _como_celda(valor))
        for i, (columna, valor) in enumerate(zip(columnas, fila))
        if i not in (principal, destacada) and columna.en_movil
    ]

    controles = [
        ft.Row(
            controls=encabezado,
            spacing=10,
            vertical_alignment=ft.CrossAxisAlignment.START,
        )
    ]
    if datos:
        controles.append(ft.Row(controls=datos, spacing=14, run_spacing=6, wrap=True))

    return ft.Container(
        bgcolor="white",
        border_radius=16,
        border=_borde(1, COLOR_BORDE),
        padding=_relleno(14, 12),
        content=ft.Column(controls=controles, spacing=8),
    )


# ------------------------------------------------------------
# API
# ------------------------------------------------------------
def tabla_reporte(page: ft.Page, columnas: list[ColumnaReporte], filas: list[list],
                  texto_vacio: str = "Sin registros para mostrar en este rango.",
                  por_pagina: int = FILAS_POR_PAGINA) -> ft.Control:
    """Devuelve la tabla (escritorio) o la lista de tarjetas (celular)."""
    if not filas:
        return ft.Container(
            bgcolor="#FBF5FF",
            border_radius=14,
            padding=12,
            content=ft.Text(texto_vacio, size=13, color=COLOR_TEXTO_SUAVE),
        )

    movil = es_pantalla_angosta(page)
    estado = {"mostradas": min(por_pagina, len(filas))}
    contenedor = ft.Column(spacing=10 if movil else 0)

    btn_mas = ft.TextButton("Ver más")

    def pintar():
        visibles = filas[: estado["mostradas"]]
        if movil:
            controles = [_tarjeta_movil(columnas, fila) for fila in visibles]
        else:
            controles = [
                ft.Container(
                    border_radius=14,
                    border=_borde(1, COLOR_BORDE),
                    clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
                    content=ft.Column(_tabla_escritorio(columnas, visibles), spacing=0),
                )
            ]

        restantes = len(filas) - estado["mostradas"]
        if restantes > 0:
            set_texto_boton(btn_mas, f"Ver {min(por_pagina, restantes)} más ({restantes} restantes)")
            controles.append(ft.Row([btn_mas], alignment=ft.MainAxisAlignment.CENTER))
        contenedor.controls = controles

    def ver_mas(e=None):
        estado["mostradas"] = min(len(filas), estado["mostradas"] + por_pagina)
        pintar()
        try:
            page.update()
        except Exception:
            pass

    btn_mas.on_click = ver_mas
    pintar()
    return contenedor