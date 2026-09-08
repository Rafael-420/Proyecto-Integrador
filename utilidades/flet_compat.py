"""Funciones de compatibilidad para distintas versiones de Flet."""

import flet as ft

if not hasattr(ft, "icons") and hasattr(ft, "Icons"):
    ft.icons = ft.Icons

if not hasattr(ft, "animation"):
    ft.animation = ft

ALIGN_CENTER = getattr(getattr(ft, "alignment", None), "center", None) or getattr(ft.Alignment, "CENTER", None)


def icono(*names):
    for name in names:
        try:
            value = getattr(getattr(ft, "icons", None), name, None)
            if value is not None:
                return value
        except Exception:
            pass
        try:
            value = getattr(getattr(ft, "Icons", None), name, None)
            if value is not None:
                return value
        except Exception:
            pass
    return None


def abrir_dialogo(page: ft.Page, control):
    """Abre un AlertDialog (o SnackBar) usando la API oficial de Flet.

    Antes se agregaba el control a page.overlay a mano y se ponía
    control.open = True. Al cerrarlo sólo se ponía open = False, sin
    quitarlo del overlay, así que la ruta modal quedaba a medio cerrar
    en Flutter y la aplicación se congelaba: la barrera invisible seguía
    encima y se tragaba todos los toques.

    Además se fuerza modal = False en los diálogos para que, como espera
    cualquier usuario de móvil, tocar fuera de la ventana la cierre.
    """
    try:
        if isinstance(control, ft.AlertDialog):
            control.modal = False
    except Exception:
        pass

    for metodo in ("open", "show_dialog"):
        try:
            fn = getattr(page, metodo, None)
            if fn is not None:
                fn(control)
                return
        except Exception:
            continue

    try:
        if hasattr(page, "overlay") and control not in page.overlay:
            page.overlay.append(control)
        control.open = True
        page.update()
    except Exception:
        pass


def cerrar_dialogo(page: ft.Page, control):
    """Cierra un diálogo liberando también su ruta modal.

    page.close() es la contraparte correcta de page.open(): quita el
    control del overlay y desmonta la ruta. Mezclar page.open() con un
    simple open = False era justo lo que dejaba la pantalla congelada.
    """
    for metodo in ("close", "pop_dialog"):
        try:
            fn = getattr(page, metodo, None)
            if fn is None:
                continue
            try:
                fn(control)
            except TypeError:
                fn()
            return
        except Exception:
            continue

    try:
        control.open = False
        page.update()
    except Exception:
        pass

    try:
        if hasattr(page, "overlay") and control in page.overlay:
            page.overlay.remove(control)
            page.update()
    except Exception:
        pass


def snack(page: ft.Page, texto: str, ok: bool = True):
    sb = ft.SnackBar(
        content=ft.Text(texto, color="white"),
        bgcolor="#2E7D32" if ok else "#C62828",
    )
    abrir_dialogo(page, sb)