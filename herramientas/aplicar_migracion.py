"""
herramientas/aplicar_migracion.py
---------------------------------
Ejecuta recursos/sql/migracion_seguridad.sql usando la misma conexion
que el resto del sistema (la del archivo .env).

Es tolerante a repeticiones: si una columna o un indice ya existe,
lo informa y continua con la siguiente instruccion en lugar de abortar.

Ejecutar desde la raiz del proyecto:

    python -m herramientas.aplicar_migracion
"""

from __future__ import annotations

import sys
from pathlib import Path

from configuracion.base_datos import get_connection

RUTA_SQL = Path("recursos") / "sql" / "migracion_seguridad.sql"

# Errores de MySQL que significan "esto ya estaba aplicado"
_YA_APLICADO = {
    1060: "la columna ya existe",
    1061: "el indice ya existe",
    1050: "la tabla ya existe",
    1091: "el objeto no existe (ya se habia quitado)",
}


def _separar_instrucciones(texto: str) -> list[str]:
    """Divide el archivo en instrucciones, ignorando comentarios."""
    lineas = []
    for linea in texto.splitlines():
        limpia = linea.strip()
        if not limpia or limpia.startswith("--"):
            continue
        lineas.append(linea)

    instrucciones = []
    for bloque in "\n".join(lineas).split(";"):
        bloque = bloque.strip()
        if bloque:
            instrucciones.append(bloque)
    return instrucciones


def _resumen(instruccion: str) -> str:
    return " ".join(instruccion.split())[:70]


def main() -> int:
    ruta = RUTA_SQL if RUTA_SQL.exists() else Path(__file__).resolve().parent.parent / RUTA_SQL

    if not ruta.exists():
        print(f"No se encontro el archivo {RUTA_SQL}.")
        print("Ejecuta el script desde la raiz del proyecto (donde esta main.py).")
        return 1

    instrucciones = _separar_instrucciones(ruta.read_text(encoding="utf-8"))
    print(f"Archivo: {ruta}")
    print(f"Instrucciones a ejecutar: {len(instrucciones)}\n")

    try:
        conexion = get_connection()
    except Exception as exc:
        print(f"No se pudo conectar a la base de datos:\n  {exc}")
        return 1

    cursor = conexion.cursor(dictionary=True)
    aplicadas = omitidas = fallidas = 0

    for numero, instruccion in enumerate(instrucciones, start=1):
        etiqueta = _resumen(instruccion)
        try:
            cursor.execute(instruccion)

            # La ultima instruccion es un SELECT de verificacion
            if cursor.with_rows:
                filas = cursor.fetchall()
                print(f"[{numero}] Reporte de verificacion:")
                for fila in filas:
                    print(
                        "     {:<4} {:<20} {:<10} {}".format(
                            fila.get("IdUsuario", ""),
                            str(fila.get("NombreUsuario", ""))[:20],
                            str(fila.get("Rol", ""))[:10],
                            fila.get("EstadoPassword", ""),
                        )
                    )
            else:
                print(f"[{numero}] OK      {etiqueta}")

            conexion.commit()
            aplicadas += 1

        except Exception as exc:
            codigo = getattr(exc, "errno", None)
            if codigo in _YA_APLICADO:
                print(f"[{numero}] OMITIDA {etiqueta}")
                print(f"          ({_YA_APLICADO[codigo]})")
                omitidas += 1
                conexion.rollback()
            else:
                print(f"[{numero}] ERROR   {etiqueta}")
                print(f"          {exc}")
                fallidas += 1
                conexion.rollback()

    cursor.close()
    conexion.close()

    print(f"\nAplicadas: {aplicadas} | Omitidas: {omitidas} | Con error: {fallidas}")

    if fallidas:
        print("\nRevisa los errores antes de continuar.")
        return 1

    print("\nSiguiente paso:")
    print("  python -m herramientas.migrar_contrasenas            (reporte)")
    print("  python -m herramientas.migrar_contrasenas --aplicar  (escribe)")
    return 0


if __name__ == "__main__":
    sys.exit(main())