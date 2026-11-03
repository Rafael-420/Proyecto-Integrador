"""Acomoda un sidebar junto al contenido de una pantalla.

Lo usan el sidebar del administrador (componentes/sidebar_admin.py), el
del empleado (componentes/sidebar.py) y el del menú de clientes
(componentes/sidebar_menu.py), para que todos se comporten igual:

  - Pantalla angosta (celular): el sidebar arranca plegado como un riel
    de íconos. Al abrirlo se monta ENCIMA del contenido, como el menú
    lateral de cualquier app de celular, en lugar de quitarle ancho. Un
    velo oscuro cubre el resto de la pantalla y, al tocarlo, el sidebar
    se vuelve a esconder.
  - Pantalla ancha (escritorio): el sidebar va al lado del contenido,
    como siempre; ahí sí hay espacio para los dos.

Cada sidebar se registra al construirse (registrar_sidebar) y cada
pantalla arma su layout con layout_con_sidebar.
"""

import flet as ft

ANCHO_PANTALLA_ANGOSTA = 700

# layout_con_sidebar necesita controlar el sidebar (saber si está
# abierto, cerrarlo y enterarse cuando cambia). Se guarda aquí por id()
# en lugar de en sidebar.data porque en Flet 0.8x `data` se envía al
# cliente y no admite funciones. layout_con_sidebar saca la entrada con
# pop(), así que el registro no crece.
_REGISTRO = {}


def es_pantalla_angosta(page: ft.Page) -> bool:
    ancho = getattr(page, "width", None)
    return bool(ancho and ancho < ANCHO_PANTALLA_ANGOSTA)


def color_velo():
    """Negro semitransparente, compatible con Flet 0.2x y 0.8x."""
    for contenedor in (getattr(ft, "Colors", None), getattr(ft, "colors", None)):
        try:
            return contenedor.with_opacity(0.35, contenedor.BLACK)
        except Exception:
            continue
    return "#59000000"


def registrar_sidebar(sidebar, *, angosto, ancho_riel, esta_colapsado, colapsar, escuchar):
    """Guarda lo que layout_con_sidebar necesita saber del sidebar.

    esta_colapsado: función sin argumentos que dice si está plegado.
    colapsar:       función que lo pliega (recibe el evento, opcional).
    escuchar:       función que recibe un oyente; el sidebar llama al
                    oyente con True/False cada vez que se pliega o abre.
    """
    _REGISTRO[id(sidebar)] = {
        "angosto": angosto,
        "ancho_riel": ancho_riel,
        "esta_colapsado": esta_colapsado,
        "colapsar": colapsar,
        "escuchar": escuchar,
    }


def layout_con_sidebar(
    page: ft.Page,
    sidebar: ft.Control,
    contenido: ft.Control,
    espaciado=None,
    alineacion_vertical=None,
) -> ft.Control:
    """Devuelve el control que acomoda el sidebar y el contenido.

    espaciado y alineacion_vertical: solo aplican en escritorio, al Row
    de sidebar + contenido (los que usaba cada pantalla; None deja los
    valores de Flet).
    """
    info = _REGISTRO.pop(id(sidebar), None)

    if info is None or not info["angosto"]:
        opciones = {"expand": True}
        if espaciado is not None:
            opciones["spacing"] = espaciado
        if alineacion_vertical is not None:
            opciones["vertical_alignment"] = alineacion_vertical
        return ft.Row([sidebar, contenido], **opciones)

    velo = ft.Container(
        left=0,
        top=0,
        right=0,
        bottom=0,
        bgcolor=color_velo(),
        visible=not info["esta_colapsado"](),
        on_click=info["colapsar"],
    )

    def al_cambiar(colapsado: bool):
        velo.visible = not colapsado

    info["escuchar"](al_cambiar)

    return ft.Stack(
        expand=True,
        controls=[
            # El contenido empieza después del riel plegado: el riel
            # nunca tapa nada y el contenido conserva su ancho.
            ft.Container(content=contenido, left=info["ancho_riel"], top=0, right=0, bottom=0),
            velo,
            # top/bottom/left anclan el sidebar al costado y lo estiran
            # a todo el alto de la pantalla.
            ft.Container(content=sidebar, left=0, top=0, bottom=0),
        ],
    )