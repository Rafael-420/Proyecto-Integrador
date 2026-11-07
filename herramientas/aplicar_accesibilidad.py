"""
herramientas/aplicar_accesibilidad.py
-------------------------------------
Correcciones de accesibilidad (WCAG 2.1 AA) de la lista de cotejo:

  1. Contraste (1.4.3, 1.4.11). El morado de marca #C86DD7 con texto
     blanco da 3.17:1 y WCAG pide 4.5:1. Se cambia por #9C47B5 (5.27:1),
     el mismo tono mas oscuro. El rojo "red" de los errores (4.0:1) pasa
     a #B91C1C (6.47:1).
  2. Texto alternativo (1.1.1). Las fotos de bebidas y el logo dicen que
     son; las imagenes decorativas del login y de la animacion se
     ocultan al lector de pantalla para que no lo llenen de ruido.
  3. Nombre accesible (2.5.3, 4.1.2). Los 6 botones de icono sin
     tooltip reciben uno ("Volver", "Abrir menu", "Cerrar").
  4. Instrucciones (3.3.2). El registro muestra las reglas de la
     contrasena debajo del campo antes de escribirla.

Antes de modificar cada archivo guarda una copia .respaldo junto a el.
Se puede ejecutar varias veces: lo que ya esta cambiado se omite.
Si un archivo tuyo es distinto al esperado, no lo toca y te avisa.

Ejecutar desde la raiz del proyecto:

    python -m herramientas.aplicar_accesibilidad
"""

from __future__ import annotations

import ast
import re
import shutil
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

MORADO_VIEJO = "C86DD7"
MORADO_NUEVO = "9C47B5"
CARPETAS_COLOR = ("vistas", "componentes", "navegacion")
ARCHIVOS_COLOR = ("configuracion/variables.py",)

# Imagenes decorativas: no aportan informacion.
DECORATIVA = "exclude_from_semantics=True"

# (archivo, texto buscado, texto nuevo). El texto nuevo contiene el
# buscado, asi que si ya esta aplicado se detecta y se omite.
CAMBIOS: list[tuple[str, str, str]] = [
    # --- 2. Texto alternativo -------------------------------------------
    (
        "componentes/tarjeta_producto.py",
        "            src=imagen,\n            width=54,\n",
        "            src=imagen,\n"
        '            semantics_label=f"Foto de {item.get(\'nombre\', \'la bebida\')}",\n'
        "            width=54,\n",
    ),
    (
        "componentes/dialogo_personalizacion.py",
        "src=imagen,\n                width=44,",
        'src=imagen,\n                semantics_label=f"Foto de {item.get(\'nombre\', \'la bebida\')}",\n                width=44,',
    ),
    (
        "componentes/dialogo_personalizacion.py",
        "src=ruta, width=ancho_img, height=alto_img, fit=ft.BoxFit.CONTAIN,",
        f"src=ruta, width=ancho_img, height=alto_img, fit=ft.BoxFit.CONTAIN, {DECORATIVA},",
    ),
    (
        "componentes/dialogo_personalizacion.py",
        "        src=RUTA_VASO,\n        fit=ft.BoxFit.CONTAIN,\n",
        "        src=RUTA_VASO,\n"
        '        semantics_label="Vista previa de tu bebida",\n'
        "        fit=ft.BoxFit.CONTAIN,\n",
    ),
    (
        "componentes/dialogo_personalizacion.py",
        "src=RUTA_SOMBRA, fit=ft.BoxFit.FILL",
        f"src=RUTA_SOMBRA, fit=ft.BoxFit.FILL, {DECORATIVA}",
    ),
    (
        "vistas/vista_admin_bebidas.py",
        "ft.Image(src=imagen, width=56, height=56, fit=ft.BoxFit.COVER,",
        'ft.Image(src=imagen, width=56, height=56, fit=ft.BoxFit.COVER, '
        'semantics_label=f"Foto de {b.get(\'Nombre\', \'la bebida\')}",',
    ),
    (
        "vistas/vista_admin_bebidas.py",
        "ft.Image(src=imagen_actual, width=48, height=48, fit=ft.BoxFit.COVER, border_radius=14)",
        'ft.Image(src=imagen_actual, width=48, height=48, fit=ft.BoxFit.COVER, border_radius=14, '
        'semantics_label="Foto actual de la bebida")',
    ),
    (
        "vistas/vista_login.py",
        'src=_img("logo_corallie.png"),',
        'src=_img("logo_corallie.png"), semantics_label="Logo de Corallie Bubble",',
    ),
    (
        "vistas/vista_login.py",
        'src=_img("separador.png"),',
        f'src=_img("separador.png"), {DECORATIVA},',
    ),
] + [
    # Fondo decorativo del login: manchas, hojas, burbujas y personaje.
    ("vistas/vista_login.py", f"src=_img({args}),", f"src=_img({args}), {DECORATIVA},")
    for args in (
        '"mancha_rosa_2.png", "mancha rosa 2.png"',
        '"hoja_morada_2.png", "hoja morada 2.png"',
        '"burbujas.png"',
        '"mancha_blanca.png", "mancha blanca.png"',
        '"burbujas_2.png", "burbujas 2.png"',
        '"hoja_1.png"',
        '"mancha_rosa_3.png", "mancha rosa 3.png"',
        '"personaje_bubble.png"',
    )
] + [
    # --- 3. Nombre accesible de los botones de icono ----------------------
    (
        "componentes/sidebar.py",
        'icon=ICON_MENU, icon_color="white", on_click=toggle_sidebar',
        'icon=ICON_MENU, icon_color="white", tooltip="Abrir menú", on_click=toggle_sidebar',
    ),
    (
        "vistas/vista_caja_chica.py",
        'icon=ICON_BACK, icon_color="white", on_click=volver_caja',
        'icon=ICON_BACK, icon_color="white", tooltip="Volver a caja", on_click=volver_caja',
    ),
    (
        "vistas/vista_caja_chica.py",
        'icon=ICON_BACK, icon_color="white", on_click=volver_pos',
        'icon=ICON_BACK, icon_color="white", tooltip="Volver al punto de venta", on_click=volver_pos',
    ),
    (
        "vistas/vista_inventario.py",
        'icon=ICON_BACK, icon_color="white", on_click=volver_pos',
        'icon=ICON_BACK, icon_color="white", tooltip="Volver al punto de venta", on_click=volver_pos',
    ),
    (
        "vistas/vista_movimientos.py",
        'icon=ICON_BACK, icon_color="white", on_click=volver_pos',
        'icon=ICON_BACK, icon_color="white", tooltip="Volver al punto de venta", on_click=volver_pos',
    ),
    (
        "vistas/vista_menu.py",
        'icon=_icon("CLOSE"), on_click=lambda ev: _close_dialog(page, dlg_notif)',
        'icon=_icon("CLOSE"), tooltip="Cerrar", on_click=lambda ev: _close_dialog(page, dlg_notif)',
    ),
    # --- 4. Reglas de la contrasena antes de escribirla -------------------
    (
        "vistas/vista_registro.py",
        '    txt_pass2    = ft.TextField(label="Confirmar contraseña",password=True, can_reveal_password=True)\n',
        '    txt_pass2    = ft.TextField(label="Confirmar contraseña",password=True, can_reveal_password=True)\n'
        "    # WCAG 3.3.2: las reglas se ven antes de escribir, no solo al fallar.\n"
        "    poner_ayuda(txt_pass, seguridad.describir_reglas())\n",
    ),
    (
        "vistas/vista_registro.py",
        "from utilidades.flet_compat import ",
        "from utilidades.flet_compat import poner_ayuda, ",
    ),
]

# Funciones nuevas que se agregan al final de su archivo.
AGREGADOS: list[tuple[str, str, str]] = [
    (
        "servicios/servicio_seguridad.py",
        "def describir_reglas(",
        '''

def describir_reglas() -> str:
    """Reglas de la contrasena en una linea, para mostrarlas al usuario
    ANTES de que escriba (WCAG 3.3.2). Sale de la misma configuracion
    que validar_fortaleza, asi que nunca se contradicen."""
    partes = [f"Mínimo {int(SEG_LONGITUD_MINIMA)} caracteres"]
    if SEG_EXIGIR_LETRA and SEG_EXIGIR_DIGITO:
        partes.append("con al menos una letra y un número")
    elif SEG_EXIGIR_LETRA:
        partes.append("con al menos una letra")
    elif SEG_EXIGIR_DIGITO:
        partes.append("con al menos un número")
    return ", ".join(partes) + "."
''',
    ),
    (
        "utilidades/flet_compat.py",
        "def poner_ayuda(",
        '''

# ------------------------------------------------------------
# Texto de ayuda bajo un campo
# ------------------------------------------------------------
# Flet 0.2x usa helper_text; Flet 0.80 lo renombro a helper. Igual que
# con los errores, se decide por lo que declara la clase del control.

def poner_ayuda(campo, texto: str | None):
    """Muestra un texto de ayuda permanente debajo del campo."""
    if campo is None:
        return
    atributo = "helper_text" if hasattr(type(campo), "helper_text") else "helper"
    respaldo = "helper" if atributo == "helper_text" else "helper_text"
    for nombre in (atributo, respaldo):
        if _asignar(campo, nombre, texto):
            return
''',
    ),
]


def _guardar(ruta: Path, texto: str) -> None:
    ast.parse(texto)  # nunca dejar un archivo con error de sintaxis
    respaldo = ruta.with_suffix(ruta.suffix + ".respaldo")
    if not respaldo.exists():
        shutil.copy2(ruta, respaldo)
    ruta.write_text(texto, encoding="utf-8")


def _cambiar_colores(texto: str) -> str:
    # Incluye las variantes con transparencia (#C86DD722, #C86DD733).
    texto = re.sub(MORADO_VIEJO, MORADO_NUEVO, texto, flags=re.IGNORECASE)
    return texto.replace('"red"', '"#B91C1C"')


def aplicar_colores() -> int:
    rutas = [RAIZ / a for a in ARCHIVOS_COLOR]
    for carpeta in CARPETAS_COLOR:
        rutas += sorted((RAIZ / carpeta).glob("*.py"))
    cambiados = 0
    for ruta in rutas:
        original = ruta.read_text(encoding="utf-8")
        nuevo = _cambiar_colores(original)
        if nuevo != original:
            _guardar(ruta, nuevo)
            cambiados += 1
    return cambiados


def aplicar_cambios() -> tuple[int, int, list[str]]:
    aplicados, omitidos, fallas = 0, 0, []
    textos: dict[Path, str] = {}

    for relativa, buscado, nuevo in CAMBIOS:
        ruta = RAIZ / relativa
        texto = textos.setdefault(ruta, ruta.read_text(encoding="utf-8"))
        if nuevo in texto:
            omitidos += 1
            continue
        if texto.count(buscado) != 1:
            fallas.append(f"{relativa}: no encontre una sola vez «{buscado[:60]}»")
            continue
        textos[ruta] = texto.replace(buscado, nuevo)
        aplicados += 1

    for relativa, marca, bloque in AGREGADOS:
        ruta = RAIZ / relativa
        texto = textos.setdefault(ruta, ruta.read_text(encoding="utf-8"))
        if marca in texto:
            omitidos += 1
            continue
        textos[ruta] = texto.rstrip("\n") + "\n" + bloque
        aplicados += 1

    if fallas:
        return 0, omitidos, fallas  # no se escribe nada si algo no cuadra

    for ruta, texto in textos.items():
        if texto != ruta.read_text(encoding="utf-8"):
            _guardar(ruta, texto)
    return aplicados, omitidos, fallas


def main() -> int:
    aplicados, omitidos, fallas = aplicar_cambios()
    if fallas:
        print("[ERROR] Tu copia es distinta a la esperada. No modifique nada:")
        for falla in fallas:
            print("        " + falla)
        print("        Mandame esos archivos para ajustar el script.")
        return 1
    print(f"[OK] Texto alternativo, tooltips y ayudas: {aplicados} aplicados, {omitidos} ya estaban")
    print(f"[OK] Colores: {aplicar_colores()} archivos actualizados")
    return 0


if __name__ == "__main__":
    sys.exit(main())