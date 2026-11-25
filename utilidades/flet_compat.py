"""Funciones de compatibilidad para distintas versiones de Flet."""

import re

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

# ------------------------------------------------------------
# Mensajes de error en campos de formulario
# ------------------------------------------------------------
# Flet cambió el nombre de la propiedad: hasta 0.2x el TextField usaba
# error_text (str) y en las versiones nuevas FormFieldControl usa error,
# que acepta texto o un control. Usar el nombre viejo tumba la app con
# "'TextField' object has no attribute 'error_text'".
#
# Estas funciones escriben y leen el error sin importar la versión, para
# que las vistas no tengan que saber en cuál se está ejecutando.

def _atributo_error(campo) -> str:
    """Nombre de la propiedad que este control dibuja como error.

    Antes se intentaba asignar error_text y, si "no fallaba", se daba
    por bueno. Pero en Flet 0.80 la asignación NO falla: Python guarda
    el atributo en el objeto, Flet no lo envía y el mensaje nunca se
    ve. Por eso las validaciones del registro no aparecían.

    Se decide por lo que declara la CLASE del control:
      - Flet 0.28: TextField declara error_text (y error); se dibuja
        error_text.
      - Flet 0.80+: TextField solo declara error; Dropdown todavía
        declara error_text.
    """
    if hasattr(type(campo), "error_text"):
        return "error_text"
    return "error"


def _asignar(campo, atributo, valor) -> bool:
    """Intenta asignar el atributo y confirma que quedó puesto."""
    try:
        setattr(campo, atributo, valor)
    except Exception:
        return False
    try:
        return getattr(campo, atributo, "sin valor") == valor
    except Exception:
        return False


def set_error(campo, mensaje=None):
    """Marca (o limpia, con mensaje None) el error de un campo.

    La propiedad se elige según lo que declara la clase del control
    (ver _atributo_error); si asignarla falla, se intenta la otra.
    """
    if campo is None:
        return

    texto = mensaje if mensaje else None

    principal = _atributo_error(campo)
    respaldo = "error" if principal == "error_text" else "error_text"
    for atributo in (principal, respaldo):
        if _asignar(campo, atributo, texto):
            return

    # Última opción: al menos que el mensaje se vea en algún lado.
    try:
        campo.helper_text = texto
    except Exception:
        pass


def get_error(campo):
    """Devuelve el mensaje de error del campo, o None si no tiene."""
    if campo is None:
        return None
    try:
        valor = getattr(campo, _atributo_error(campo), None)
    except Exception:
        valor = None
    return valor or None


# ------------------------------------------------------------
# Texto de botones
# ------------------------------------------------------------
# Hasta Flet 0.2x el texto de un botón vivía en .text; desde 0.80 vive
# en .content. Asignar .text en 0.80 no falla, pero el botón no cambia.

def set_texto_boton(boton, texto: str):
    """Cambia el texto visible de un botón en cualquier versión de Flet."""
    if boton is None:
        return
    atributo = "text" if hasattr(type(boton), "text") else "content"
    try:
        setattr(boton, atributo, texto)
    except Exception:
        pass

# ------------------------------------------------------------
# Menús desplegables (Dropdown)
# ------------------------------------------------------------
# Hasta Flet 0.28 el Dropdown avisaba el cambio con on_change; desde 0.80
# ese evento ya no existe y se llama on_select. Asignar on_change en 0.80
# no falla, pero nunca se ejecuta: por eso el precio no cambiaba al
# elegir otro tamaño y el campo de efectivo no se ocultaba al elegir
# tarjeta.

def al_seleccionar(dropdown, manejador):
    """Ejecuta `manejador` cuando cambia la opción, en cualquier versión de Flet."""
    if dropdown is None:
        return
    for evento in ("on_select", "on_change"):
        if hasattr(type(dropdown), evento):
            try:
                setattr(dropdown, evento, manejador)
            except Exception:
                pass


# ------------------------------------------------------------
# Campos de dinero: solo números
# ------------------------------------------------------------
_NO_NUMERICO = re.compile(r"[^0-9.]")


def limpiar_monto(texto: str, decimales: int = 2) -> str:
    """Deja solo dígitos y un punto decimal, con máximo `decimales` decimales."""
    limpio = _NO_NUMERICO.sub("", str(texto or ""))  # la coma de miles se descarta
    if "." in limpio:
        entero, resto = limpio.split(".", 1)
        limpio = entero + "." + resto.replace(".", "")[:decimales]
    return limpio


def solo_numeros(campo, al_cambiar=None, decimales: int = 2):
    """Hace que un TextField acepte únicamente cantidades de dinero.

    Dos capas:
      1. input_filter (Flet 0.2x y 0.80+): el teclado ni siquiera escribe
         letras ni símbolos.
      2. Limpieza en on_change: cubre lo que el filtro deja pasar (pegar
         texto, dos puntos decimales, más de dos decimales) y versiones
         de Flet sin input_filter.

    `al_cambiar` se ejecuta después de limpiar el valor (por ejemplo, para
    recalcular el cambio).
    """
    if campo is None:
        return

    filtro = getattr(ft, "InputFilter", None)
    if filtro is not None:
        try:
            campo.input_filter = filtro(regex_string=r"[0-9.]", allow=True, replacement_string="")
        except Exception:
            pass
    try:
        campo.keyboard_type = ft.KeyboardType.NUMBER
    except Exception:
        pass

    def manejador(e=None):
        valor = campo.value or ""
        limpio = limpiar_monto(valor, decimales)
        if limpio != valor:
            campo.value = limpio
            try:
                campo.update()
            except Exception:
                pass
        if al_cambiar is not None:
            al_cambiar(e)

    campo.on_change = manejador
