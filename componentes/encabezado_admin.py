"""Encabezado de las pantallas de control (empleados y clientes).

Título arriba y, debajo, el buscador junto al botón de alta. En pantallas
angostas el botón baja a su propio renglón y ocupa todo el ancho.

Antes cada pantalla armaba su propio encabezado. En "Control de usuarios"
era un Row donde un espacio vacío y el buscador peleaban por el mismo
ancho: el buscador quedaba de unos 70 px y la etiqueta "Buscar
usuario/cliente" se partía en tres renglones.
"""

import flet as ft

from utilidades.flet_compat import icono


COLOR_LILA = "#C86DD7"
COLOR_BORDE = "#E9D5F5"
COLOR_TEXTO_SUAVE = "#6B7280"
ALTO_CONTROL = 48


def preparar_buscador(campo: ft.TextField, pista: str) -> ft.TextField:
    """Le da al TextField del buscador el estilo del encabezado.

    Se modifica el mismo campo que creó la pantalla (ya tiene su
    on_change para filtrar), así que no cambia nada de la búsqueda.
    """
    campo.label = None
    campo.hint_text = pista
    campo.expand = False
    campo.filled = True
    campo.bgcolor = "white"
    campo.border_radius = 14
    campo.border_color = COLOR_BORDE
    campo.focused_border_color = COLOR_LILA
    campo.cursor_color = COLOR_LILA
    campo.text_size = 14
    campo.height = ALTO_CONTROL
    campo.content_padding = ft.Padding(left=12, top=14, right=12, bottom=14)
    campo.prefix_icon = icono("SEARCH")
    return campo


def encabezado_con_busqueda(
    titulo: str,
    buscador: ft.TextField,
    pista_busqueda: str,
    texto_boton: str | None = None,
    al_crear=None,
) -> ft.Control:
    """Título + buscador. Si texto_boton es None no se pone botón de alta
    y el buscador ocupa todo el ancho."""
    preparar_buscador(buscador, pista_busqueda)

    if not texto_boton:
        return ft.Column(
            spacing=12,
            controls=[
                ft.Text(
                    titulo,
                    size=22,
                    weight="bold",
                    color=COLOR_LILA,
                    max_lines=2,
                    overflow=ft.TextOverflow.ELLIPSIS,
                ),
                buscador,
            ],
            # STRETCH: el buscador ocupa todo el ancho del panel.
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        )

    boton = ft.ElevatedButton(
        content=ft.Text(
            texto_boton,
            size=14,
            weight="bold",
            no_wrap=True,
            text_align=ft.TextAlign.CENTER,
        ),
        icon=icono("PERSON_ADD", "ADD"),
        bgcolor=COLOR_LILA,
        color="white",
        height=ALTO_CONTROL,
        on_click=al_crear,
        style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=14)),
    )

    return ft.Column(
        spacing=12,
        controls=[
            ft.Text(
                titulo,
                size=22,
                weight="bold",
                color=COLOR_LILA,
                max_lines=2,
                overflow=ft.TextOverflow.ELLIPSIS,
            ),
            ft.ResponsiveRow(
                spacing=10,
                run_spacing=10,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    # Las columnas de Flet se calculan con el ancho de la
                    # PÁGINA, no del contenedor (que pierde el ancho del
                    # sidebar); por eso el botón lleva más columnas de lo
                    # que parecería necesario.
                    ft.Container(col={"xs": 12, "md": 7, "lg": 8, "xxl": 9}, content=buscador),
                    ft.Container(
                        col={"xs": 12, "md": 5, "lg": 4, "xxl": 3},
                        content=ft.Column(
                            [boton],
                            tight=True,
                            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                        ),
                    ),
                ],
            ),
        ],
    )