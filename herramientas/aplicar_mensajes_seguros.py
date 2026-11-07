"""
herramientas/aplicar_mensajes_seguros.py
----------------------------------------
Cambia los mensajes de error de las pantallas para que no muestren la
excepcion tecnica (tablas, columnas, rutas internas) al usuario.

En cada linea que muestra una excepcion en pantalla reemplaza:

    f"No se pudo guardar: {ex}"   ->  f"No se pudo guardar: {detalle_seguro(ex)}"
    ft.Text(str(ex))              ->  ft.Text(detalle_seguro(ex))

y agrega el import de utilidades.errores. Las lineas con print() no se
tocan (la consola del servidor si debe ver el detalle).

Antes de modificar cada archivo guarda una copia .respaldo junto a el.
Se puede ejecutar varias veces: lo que ya esta cambiado se omite.

Ejecutar desde la raiz del proyecto:

    python -m herramientas.aplicar_mensajes_seguros
"""

from __future__ import annotations

import ast
import re
import shutil
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
CARPETAS = ("vistas", "componentes")
IMPORT = "from utilidades.errores import detalle_seguro\n"

# {ex} dentro de un f-string y str(ex) con los nombres que usa el proyecto
# para la excepcion capturada.
_PATRON_LLAVES = re.compile(r"\{(e|ex|exc|err|error)\}")
_PATRON_STR = re.compile(r"\bstr\((e|ex|exc|err)\)")


def _cambiar_linea(linea: str) -> str:
    if "print(" in linea or "detalle_seguro(" in linea:
        return linea
    linea = _PATRON_LLAVES.sub(r"{detalle_seguro(\1)}", linea)
    return _PATRON_STR.sub(r"detalle_seguro(\1)", linea)


def _agregar_import(texto: str) -> str:
    if IMPORT.strip() in texto:
        return texto
    arbol = ast.parse(texto)
    ultimo = 0
    for nodo in arbol.body:
        if isinstance(nodo, (ast.Import, ast.ImportFrom)):
            ultimo = nodo.end_lineno
        elif ultimo:
            break
    lineas = texto.splitlines(keepends=True)
    lineas.insert(ultimo, IMPORT)
    return "".join(lineas)


def procesar(ruta: Path) -> int:
    original = ruta.read_text(encoding="utf-8")
    lineas = original.splitlines(keepends=True)
    nuevas = [_cambiar_linea(l) for l in lineas]
    cambios = sum(1 for a, b in zip(lineas, nuevas) if a != b)
    if not cambios:
        return 0

    texto = _agregar_import("".join(nuevas))
    ast.parse(texto)  # nunca dejar un archivo con error de sintaxis

    respaldo = ruta.with_suffix(ruta.suffix + ".respaldo")
    if not respaldo.exists():
        shutil.copy2(ruta, respaldo)
    ruta.write_text(texto, encoding="utf-8")
    return cambios


def main() -> int:
    if not (RAIZ / "utilidades" / "errores.py").exists():
        print("[FALTA] utilidades/errores.py: copialo al proyecto antes de ejecutar este script")
        return 1

    total = 0
    for carpeta in CARPETAS:
        for ruta in sorted((RAIZ / carpeta).glob("*.py")):
            try:
                cambios = procesar(ruta)
            except Exception as exc:
                print(f"[ERROR] {ruta.relative_to(RAIZ)}: {exc}")
                return 1
            if cambios:
                print(f"[OK]    {ruta.relative_to(RAIZ)}: {cambios} mensajes")
                total += cambios
    print(f"Listo: {total} mensajes cambiados.")
    return 0


if __name__ == "__main__":
    sys.exit(main())