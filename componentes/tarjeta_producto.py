"""Componente reutilizable para mostrar productos del menú.

Versión compacta: tarjetas cuadradas para usarse dentro de GridView.
"""

import flet as ft

# Compatibilidad entre versiones recientes de Flet
if not hasattr(ft, "icons") and hasattr(ft, "Icons"):
    ft.icons = ft.Icons

if not hasattr(ft, "animation"):
    ft.animation = ft

ALIGN_CENTER = (
    getattr(getattr(ft, "alignment", None), "center", None)
    or getattr(ft.Alignment, "CENTER", None)
)


def obtener_icono(nombre: str, respaldo=None):
    """Obtiene un icono de Flet sin romper compatibilidad entre versiones."""
    try:
        valor = getattr(ft.icons, nombre)
        return valor if valor is not None else respaldo
    except Exception:
        return respaldo


def chip(texto: str, color_bg: str = "#F7E8FF", color_txt: str = "#6D28D9"):
    """Etiqueta visual pequeña usada para precio o categoría."""
    return ft.Container(
        padding=ft.padding.symmetric(horizontal=10, vertical=5),
        border_radius=999,
        bgcolor=color_bg,
        content=ft.Text(
            texto,
            size=11,
            color=color_txt,
            weight=ft.FontWeight.BOLD,
        ),
    )


def _miniatura_producto(item: dict):
    """Muestra la foto real del producto si el admin subió una desde
    Inventario; si no hay foto, cae de vuelta al emoji de siempre."""
    imagen = (item.get("imagen") or "").strip()

    if imagen:
        contenido = ft.Image(
            src=imagen,
            width=54,
            height=54,
            fit=ft.BoxFit.COVER,
            border_radius=18,
            error_content=ft.Text(item.get("emoji", "🧋"), size=26),
        )
    else:
        contenido = ft.Text(item.get("emoji", "🧋"), size=26)

    return ft.Container(
        width=54,
        height=54,
        border_radius=18,
        bgcolor="#FFE7F5",
        alignment=ALIGN_CENTER,
        clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
        content=contenido,
    )


def tarjeta_producto(item: dict, formatear_dinero, abrir_personalizacion):
    """Crea una tarjeta cuadrada para una bebida/producto, con una ligera
    animación al pasar el cursor (se levanta un poco y resalta la sombra)."""
    tarjeta = ft.Container(
        bgcolor="white",
        border_radius=24,
        border=ft.border.all(1, "#F3D7EC"),
        padding=14,
        animate=ft.animation.Animation(220, ft.AnimationCurve.EASE_OUT),
        animate_scale=ft.animation.Animation(220, ft.AnimationCurve.EASE_OUT),
        shadow=ft.BoxShadow(
            spread_radius=0,
            blur_radius=14,
            color="#00000010",
            offset=ft.Offset(0, 6),
        ),
        content=ft.Column(
            controls=[
                ft.Row(
                    controls=[
                        _miniatura_producto(item),
                        ft.Column(
                            controls=[
                                ft.Text(
                                    item.get("nombre", "Producto"),
                                    size=15,
                                    weight=ft.FontWeight.BOLD,
                                    color="#222222",
                                    max_lines=2,
                                    overflow=ft.TextOverflow.ELLIPSIS,
                                ),
                                ft.Text(
                                    item.get("categoria", "General"),
                                    size=11,
                                    color="#7C3AED",
                                    max_lines=1,
                                    overflow=ft.TextOverflow.ELLIPSIS,
                                ),
                            ],
                            spacing=2,
                            expand=True,
                        ),
                    ],
                    spacing=10,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Text(
                    item.get("descripcion", ""),
                    size=12,
                    color="#555555",
                    max_lines=3,
                    overflow=ft.TextOverflow.ELLIPSIS,
                ),
                ft.Container(expand=True),
                ft.Row(
                    controls=[
                        chip(formatear_dinero(item.get("precio", 0)), "#F5E8FF", "#7C3AED"),
                        ft.ElevatedButton(
                            "Personalizar",
                            bgcolor="#C86DD7",
                            color="white",
                            icon=obtener_icono("TUNE"),
                            on_click=lambda e, producto=item: abrir_personalizacion(producto),
                            style=ft.ButtonStyle(
                                shape=ft.RoundedRectangleBorder(radius=18),
                                padding=ft.padding.symmetric(horizontal=12, vertical=10),
                                animation_duration=180,
                            ),
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            ],
            spacing=10,
            expand=True,
        ),
    )

    def hover(e):
        if e.data == "true":
            tarjeta.scale = 1.02
            tarjeta.shadow = ft.BoxShadow(
                spread_radius=0,
                blur_radius=22,
                color="#C86DD733",
                offset=ft.Offset(0, 10),
            )
            tarjeta.border = ft.border.all(1, "#E9B8F0")
        else:
            tarjeta.scale = 1
            tarjeta.shadow = ft.BoxShadow(
                spread_radius=0,
                blur_radius=14,
                color="#00000010",
                offset=ft.Offset(0, 6),
            )
            tarjeta.border = ft.border.all(1, "#F3D7EC")
        tarjeta.update()

    tarjeta.on_hover = hover
    return tarjeta
