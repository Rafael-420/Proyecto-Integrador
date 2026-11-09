"""
herramientas/migrar_imagenes_bebidas.py
---------------------------------------
Sube a la base de datos en la nube las fotos de bebidas que ya existen
en assets/bebidas (el sistema anterior).

Antes, la foto se copiaba a assets/bebidas en la computadora donde el
admin la subió y en bebidas.Imagen quedaba la ruta ("bebidas/taro.jpg").
Esas fotos solo existen en esa computadora. Este script hay que
ejecutarlo UNA vez, en esa misma computadora, despues de aplicar
recursos/sql/migracion_imagenes_bebidas.sql:

    python -m herramientas.aplicar_migracion recursos/sql/migracion_imagenes_bebidas.sql
    python -m herramientas.migrar_imagenes_bebidas

Por cada bebida con ruta vieja:
  - si el archivo existe, lo reduce y lo guarda en bebidas_imagenes
    (y deja bebidas.Imagen en NULL);
  - si no existe, lo informa y no cambia nada.

No borra ningun archivo de assets/bebidas. Se puede ejecutar varias
veces: las bebidas ya migradas tienen Imagen en NULL y se omiten.
"""

from __future__ import annotations

import sys
from pathlib import Path

from configuracion.base_datos import get_connection
from configuracion.variables import CARPETA_ASSETS
from servicios.servicio_imagenes_bebidas import guardar_imagen_desde_archivo


def _bebidas_con_ruta_vieja() -> list[dict]:
    conexion = get_connection()
    cursor = conexion.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT IdBebida, Nombre, Imagen
            FROM bebidas
            WHERE Imagen IS NOT NULL AND TRIM(Imagen) <> ''
            ORDER BY IdBebida
            """
        )
        return cursor.fetchall() or []
    finally:
        cursor.close()
        conexion.close()


def _ruta_local(ruta_guardada: str) -> Path:
    """'bebidas/taro.jpg' -> <proyecto>/assets/bebidas/taro.jpg"""
    relativa = ruta_guardada.strip().lstrip("/\\")
    return Path(CARPETA_ASSETS) / relativa


def main() -> int:
    try:
        bebidas = _bebidas_con_ruta_vieja()
    except Exception as exc:
        print(f"No se pudo conectar a la base de datos:\n  {exc}")
        return 1

    if not bebidas:
        print("No hay fotos pendientes: ninguna bebida tiene ruta en assets/bebidas.")
        return 0

    print(f"Bebidas con foto en assets/bebidas: {len(bebidas)}\n")
    migradas = no_encontradas = fallidas = 0

    for bebida in bebidas:
        id_bebida = bebida["IdBebida"]
        nombre = bebida["Nombre"]
        archivo = _ruta_local(bebida["Imagen"])

        if not archivo.exists():
            print(f"  [{id_bebida}] {nombre}: NO ENCONTRADA ({archivo})")
            no_encontradas += 1
            continue

        try:
            tamano = guardar_imagen_desde_archivo(id_bebida, str(archivo))
        except Exception as exc:
            print(f"  [{id_bebida}] {nombre}: ERROR -> {exc}")
            fallidas += 1
            continue

        print(f"  [{id_bebida}] {nombre}: OK ({archivo.name} -> {tamano / 1024:.0f} KB en la BD)")
        migradas += 1

    print(
        f"\nResumen: {migradas} migradas, {no_encontradas} no encontradas, "
        f"{fallidas} con error."
    )
    if no_encontradas:
        print(
            "Las no encontradas siguen mostrando el emoji. Ejecuta este script en la\n"
            "computadora donde se subieron, o vuelve a subir la foto desde el panel\n"
            "de administrador (Bebidas > Editar > Cambiar foto)."
        )
    return 0 if fallidas == 0 else 1


if __name__ == "__main__":
    sys.exit(main())