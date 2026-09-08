"""Componentes reutilizables para carrito, historial y estado de pedidos."""

import flet as ft

if not hasattr(ft, "icons") and hasattr(ft, "Icons"):
    ft.icons = ft.Icons

ALIGN_CENTER = (
    getattr(getattr(ft, "alignment", None), "center", None)
    or getattr(ft.Alignment, "CENTER", None)
)


def obtener_icono(nombre: str, respaldo=None):
    try:
        valor = getattr(ft.icons, nombre)
        return valor if valor is not None else respaldo
    except Exception:
        return respaldo


def chip(texto: str, color_bg: str = "#F7E8FF", color_txt: str = "#6D28D9"):
    return ft.Container(
        padding=ft.padding.symmetric(horizontal=10, vertical=5),
        border_radius=999,
        bgcolor=color_bg,
        content=ft.Text(texto, size=11, color=color_txt, weight=ft.FontWeight.BOLD),
    )


def section_card(content):
    """Contenedor blanco estándar para secciones del menú."""
    return ft.Container(
        bgcolor="white",
        border_radius=22,
        padding=16,
        border=ft.border.all(1, "#F3D7EC"),
        shadow=ft.BoxShadow(
            spread_radius=0,
            blur_radius=18,
            color="#00000010",
            offset=ft.Offset(0, 6),
        ),
        content=content,
    )


def tarjeta_carrito(item: dict, sumar, restar, eliminar, editar, formatear_dinero, preparacion_a_texto):
    """Tarjeta individual para un producto agregado al carrito."""
    return section_card(
        ft.Column(
            controls=[
                ft.Row(
                    controls=[
                        ft.Text(
                            item.get("nombre", "Producto"),
                            size=15,
                            weight=ft.FontWeight.BOLD,
                            color="#222222",
                            expand=True,
                        ),
                        ft.Text(
                            formatear_dinero(item.get("precio", 0)),
                            size=14,
                            weight=ft.FontWeight.BOLD,
                            color="#7C3AED",
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
                ft.Text(
                    preparacion_a_texto(item.get("prep", {})),
                    size=11,
                    color="#666666",
                ),
                ft.Row(
                    controls=[
                        ft.Row(
                            controls=[
                                ft.Container(
                                    width=36,
                                    height=36,
                                    border_radius=12,
                                    bgcolor="#F5E8FF",
                                    alignment=ALIGN_CENTER,
                                    ink=True,
                                    on_click=restar,
                                    content=ft.Text(
                                        "-",
                                        size=20,
                                        weight=ft.FontWeight.BOLD,
                                        color="#7C3AED",
                                        text_align=ft.TextAlign.CENTER,
                                    ),
                                ),
                                ft.Text(
                                    str(item.get("qty", 1)),
                                    width=24,
                                    text_align=ft.TextAlign.CENTER,
                                    weight=ft.FontWeight.BOLD,
                                ),
                                ft.Container(
                                    width=36,
                                    height=36,
                                    border_radius=12,
                                    bgcolor="#F5E8FF",
                                    alignment=ALIGN_CENTER,
                                    ink=True,
                                    on_click=sumar,
                                    content=ft.Text(
                                        "+",
                                        size=20,
                                        weight=ft.FontWeight.BOLD,
                                        color="#7C3AED",
                                        text_align=ft.TextAlign.CENTER,
                                    ),
                                ),
                            ],
                            spacing=8,
                        ),
                        ft.Row(
                            controls=[
                                ft.TextButton("Editar", on_click=editar),
                                ft.TextButton("Eliminar", on_click=eliminar),
                            ],
                            spacing=0,
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
            ],
            spacing=8,
        )
    )


def tarjeta_historial(row: dict, abrir_detalle, formatear_dinero):
    """Tarjeta para mostrar un pedido dentro del historial."""
    return section_card(
        ft.Column(
            controls=[
                ft.Row(
                    controls=[
                        ft.Text(
                            f"Pedido #{row.get('IdGenerarPedido')}",
                            weight=ft.FontWeight.BOLD,
                            expand=True,
                        ),
                        chip(str(row.get("Estatus") or "Sin estatus")),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
                ft.Text(
                    f"{row.get('FechaPedido')}  {row.get('HoraPedido')}",
                    size=12,
                    color="#666666",
                ),
                ft.Row(
                    controls=[
                        ft.Text(
                            formatear_dinero(row.get("Total") or 0),
                            color="#7C3AED",
                            weight=ft.FontWeight.BOLD,
                        ),
                        ft.TextButton("Ver detalle", on_click=lambda e, pedido=row: abrir_detalle(pedido)),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
            ],
            spacing=8,
        )
    )


TIEMPOS_ESTIMADOS = {
    "pedido realizado": "⏱️ Tiempo estimado: 15-20 minutos.",
    "pagado": "⏱️ Tiempo estimado: 8-10 minutos.",
    "prepar": "⏱️ Tiempo estimado: 8-10 minutos.",
    "listo": "✅ ¡Ya puedes pasar a recogerlo!",
    "entreg": "🎉 Pedido entregado. ¡Gracias por tu compra!",
    "cancelad": "🚫 Este pedido fue cancelado.",
}


def _tiempo_estimado(estatus: str) -> str:
    estatus_lower = (estatus or "").strip().lower()
    for clave, texto in TIEMPOS_ESTIMADOS.items():
        if clave in estatus_lower:
            return texto
    return "Estamos actualizando el estado de tu pedido."


def tarjeta_estado(row: dict, formatear_dinero, puede_cancelar: bool = False, cancelar=None):
    """Tarjeta que muestra el estado del último pedido.

    puede_cancelar / cancelar controlan si se muestra el botón para
    cancelar el pedido (sólo aplica mientras aún no se empieza a preparar).
    """
    controles = [
        ft.Row(
            controls=[
                ft.Text(
                    f"Pedido #{row.get('IdGenerarPedido')}",
                    size=16,
                    weight=ft.FontWeight.BOLD,
                    expand=True,
                ),
                chip(str(row.get("Estatus") or "Sin estatus")),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        ),
        ft.Text(
            f"Fecha: {row.get('FechaPedido')}  Hora: {row.get('HoraPedido')}",
            size=12,
            color="#666666",
        ),
        ft.Text(
            _tiempo_estimado(row.get("Estatus")),
            size=12,
            color="#7C3AED",
            weight=ft.FontWeight.BOLD,
        ),
        ft.Text(
            f"Total: {formatear_dinero(row.get('Total') or 0)}",
            size=16,
            color="#7C3AED",
            weight=ft.FontWeight.BOLD,
        ),
        ft.Divider(),
        ft.Text("Detalle del pedido", size=13, weight=ft.FontWeight.BOLD),
        ft.Text(str(row.get("Producto") or ""), size=12, color="#444444"),
    ]

    observaciones = str(row.get("Observaciones") or "").strip()
    if observaciones:
        controles.append(
            ft.Text(observaciones, size=12, color="#666666")
        )

    if puede_cancelar and cancelar is not None:
        controles.append(ft.Divider())
        controles.append(
            ft.OutlinedButton(
                "Cancelar pedido",
                icon=obtener_icono("CLOSE"),
                style=ft.ButtonStyle(color="#EF4444"),
                on_click=lambda e: cancelar(e),
            )
        )

    return section_card(ft.Column(controls=controles, spacing=8))


def tarjeta_mensaje(icono: str, mensaje: str):
    """Tarjeta sencilla para estados vacíos o mensajes informativos."""
    return section_card(
        ft.Row(
            controls=[
                ft.Text(icono, size=20),
                ft.Text(mensaje, size=14, color="#555555", expand=True),
            ],
            spacing=10,
        )
    )
