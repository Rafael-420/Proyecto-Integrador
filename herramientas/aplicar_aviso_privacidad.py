"""
herramientas/aplicar_aviso_privacidad.py
----------------------------------------
Agrega el aviso de privacidad a TUS archivos locales sin reemplazarlos.

Solo inserta los bloques nuevos en:
  * configuracion/variables.py   (variables PRIVACIDAD_*)
  * vistas/vista_registro.py     (casilla, validacion y consentimiento)

Todo lo demas que tengas en esos archivos se conserva. Antes de
modificar cada archivo guarda una copia .respaldo junto a el.
Se puede ejecutar varias veces: si un cambio ya esta, lo omite.

Ejecutar desde la raiz del proyecto:

    python -m herramientas.aplicar_aviso_privacidad
"""

from __future__ import annotations

import ast
import shutil
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

# ------------------------------------------------------------
# configuracion/variables.py
# ------------------------------------------------------------
BLOQUE_VARIABLES = '''

# ------------------------------------------------------------
# Aviso de privacidad (LFPDPPP, DOF 20-mar-2025)
# Usado por servicios/servicio_privacidad.py
# ------------------------------------------------------------
# Responsable del tratamiento: el equipo del proyecto academico.
PRIVACIDAD_RESPONSABLE = _leer(
    "CORALLIE_PRIVACIDAD_RESPONSABLE",
    "Equipo de desarrollo del Proyecto Aplicado Integrador Corallie Bubble",
)
# Domicilio para oir y recibir notificaciones (obligatorio en el aviso).
# Si se deja vacio, el aviso omite la linea: hay que llenarlo en el .env.
PRIVACIDAD_DOMICILIO = _leer("CORALLIE_PRIVACIDAD_DOMICILIO", "")
# Correo donde se reciben las solicitudes ARCO. Si no se define, se usa
# la cuenta de correo del sistema (CORALLIE_SMTP_USER).
PRIVACIDAD_CORREO = _leer("CORALLIE_PRIVACIDAD_CORREO", SMTP_USER)
'''

# ------------------------------------------------------------
# vistas/vista_registro.py  (texto_buscado, texto_nuevo, marca)
# La marca indica que el cambio ya se aplico.
# ------------------------------------------------------------
CAMBIOS_REGISTRO = [
    (
        "from servicios import servicio_seguridad as seguridad\n",
        "from servicios import servicio_privacidad as privacidad\n"
        "from servicios import servicio_seguridad as seguridad\n"
        "from componentes.dialogo_aviso_privacidad import mostrar_aviso_privacidad\n",
        "import servicio_privacidad as privacidad",
    ),
    (
        '    lbl_msg = ft.Text("", size=13, text_align=ft.TextAlign.CENTER)\n',
        '''    lbl_msg = ft.Text("", size=13, text_align=ft.TextAlign.CENTER)

    # ------------------------------------------------------------------
    # AVISO DE PRIVACIDAD (LFPDPPP)
    # La casilla es obligatoria: sin consentimiento no se crea la cuenta.
    # ------------------------------------------------------------------
    chk_privacidad = ft.Checkbox(value=False, active_color="#C86DD7")
    lbl_error_privacidad = ft.Text("", size=12, color="red", visible=False)

    def alternar_privacidad(e):
        chk_privacidad.value = not chk_privacidad.value
        limpiar_error_privacidad(None)

    def limpiar_error_privacidad(e):
        if chk_privacidad.value:
            lbl_error_privacidad.visible = False
        page.update()

    chk_privacidad.on_change = limpiar_error_privacidad

    bloque_privacidad = ft.Column(
        [
            ft.Text(privacidad.texto_simplificado(), size=12, color="#6B7280"),
            ft.Row(
                [
                    chk_privacidad,
                    ft.Container(
                        content=ft.Text("He leído y acepto el aviso de privacidad", size=13),
                        expand=True,
                        on_click=alternar_privacidad,
                    ),
                ],
                spacing=4,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            ft.TextButton(
                "Leer el aviso de privacidad completo",
                on_click=lambda e: mostrar_aviso_privacidad(page),
            ),
            lbl_error_privacidad,
        ],
        spacing=2,
    )
''',
        "chk_privacidad = ft.Checkbox",
    ),
    (
        '''        if password != password2:
            set_error(txt_pass2, "Las contraseñas no coinciden")
            valido = False
''',
        '''        if password != password2:
            set_error(txt_pass2, "Las contraseñas no coinciden")
            valido = False

        # --- Aviso de privacidad (consentimiento obligatorio)
        error_privacidad = privacidad.mensaje_si_no_acepta(chk_privacidad.value)
        lbl_error_privacidad.value = error_privacidad or ""
        lbl_error_privacidad.visible = error_privacidad is not None
        if error_privacidad:
            valido = False
''',
        "privacidad.mensaje_si_no_acepta",
    ),
    (
        '''                (nombre, apellido, tel, correo, id_usuario),
            )

            conn.commit()
''',
        '''                (nombre, apellido, tel, correo, id_usuario),
            )

            # Constancia del consentimiento, en la misma transacción:
            # si algo falla, no queda ni la cuenta ni el consentimiento.
            origen = "registro_cliente" if tipo == "Cliente" else "registro_empleado"
            privacidad.registrar_consentimiento(cursor, id_usuario, origen)

            conn.commit()
''',
        "privacidad.registrar_consentimiento",
    ),
    (
        "                txt_pass2,\n                lbl_msg,\n",
        "                txt_pass2,\n                bloque_privacidad,\n                lbl_msg,\n",
        "                bloque_privacidad,\n",
    ),
]

ARCHIVOS_NUEVOS = (
    "servicios/servicio_privacidad.py",
    "componentes/dialogo_aviso_privacidad.py",
)


def _respaldar(ruta: Path) -> None:
    respaldo = ruta.with_suffix(ruta.suffix + ".respaldo")
    if not respaldo.exists():
        shutil.copy2(ruta, respaldo)


def _guardar(ruta: Path, texto: str) -> None:
    ast.parse(texto)  # nunca dejar un archivo con error de sintaxis
    _respaldar(ruta)
    ruta.write_text(texto, encoding="utf-8")


def aplicar_variables(ruta: Path) -> str:
    texto = ruta.read_text(encoding="utf-8")
    if "PRIVACIDAD_RESPONSABLE" in texto:
        return "ya estaba aplicado"
    if "SMTP_USER" not in texto or "def _leer(" not in texto:
        raise RuntimeError("no encontre SMTP_USER ni _leer(); revisa el archivo a mano")
    _guardar(ruta, texto.rstrip("\n") + "\n" + BLOQUE_VARIABLES)
    return "bloque agregado al final"


def aplicar_registro(ruta: Path) -> str:
    texto = ruta.read_text(encoding="utf-8")
    aplicados, omitidos, faltantes = 0, 0, []

    for numero, (buscado, nuevo, marca) in enumerate(CAMBIOS_REGISTRO, start=1):
        if marca in texto:
            omitidos += 1
            continue
        apariciones = texto.count(buscado)
        if apariciones != 1:
            faltantes.append(f"cambio {numero} ({apariciones} coincidencias)")
            continue
        texto = texto.replace(buscado, nuevo)
        aplicados += 1

    if faltantes:
        raise RuntimeError(
            "tu archivo es distinto al del repositorio en: "
            + ", ".join(faltantes)
            + ". No modifique nada; mandame tu vista_registro.py."
        )
    if aplicados:
        _guardar(ruta, texto)
    return f"{aplicados} cambios aplicados, {omitidos} ya estaban"


def main() -> int:
    errores = 0

    for relativa in ARCHIVOS_NUEVOS:
        if not (RAIZ / relativa).exists():
            print(f"[FALTA] {relativa}: copialo al proyecto antes de ejecutar este script")
            errores += 1
    if errores:
        return 1

    for relativa, funcion in (
        ("configuracion/variables.py", aplicar_variables),
        ("vistas/vista_registro.py", aplicar_registro),
    ):
        try:
            print(f"[OK]    {relativa}: {funcion(RAIZ / relativa)}")
        except Exception as exc:
            print(f"[ERROR] {relativa}: {exc}")
            errores += 1

    return 1 if errores else 0


if __name__ == "__main__":
    sys.exit(main())