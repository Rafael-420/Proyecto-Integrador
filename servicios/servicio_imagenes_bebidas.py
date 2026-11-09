"""Fotos de las bebidas guardadas en la base de datos en la nube.

Por qué existe:

  Antes la foto se copiaba a assets/bebidas en el disco de la máquina
  que corría la app y en la tabla `bebidas` solo quedaba la ruta. En
  otro equipo, o en el APK (donde assets es de solo lectura y se arma
  al compilar), la foto no existía y el menú mostraba el emoji.

  Ahora la foto se guarda en la tabla `bebidas_imagenes`
  (recursos/sql/migracion_imagenes_bebidas.sql), así que cualquier
  dispositivo conectado a la base de datos la puede mostrar.

Cómo funciona:

  - Al guardar, la foto se valida (PNG, JPG o WEBP de verdad, no solo
    por la extensión), se gira según la orientación de la cámara y se
    reduce a LADO_MAXIMO px por lado. Una foto de celular de 4 MB queda
    en unos 40-80 KB, lo que mantiene ligero el menú.
  - Al leer, las fotos se guardan en memoria por IdBebida junto con su
    columna Actualizado. Mientras la foto no cambie, no se vuelve a
    descargar de la nube.
  - Si la tabla todavía no existe o no hay internet, las funciones de
    lectura devuelven un diccionario vacío y la vista muestra el emoji
    de respaldo, igual que antes.
"""

from __future__ import annotations

import io
import threading
from pathlib import Path

from configuracion.base_datos import get_connection


# Tamaño final de la foto: las miniaturas del menú miden 44-56 px,
# 600 px deja margen para pantallas de alta densidad sin pesar de más.
LADO_MAXIMO = 600
CALIDAD_JPEG = 82

# Límite del archivo que elige el admin (antes de reducirlo).
BYTES_MAXIMOS_ORIGINAL = 15 * 1024 * 1024
# Límite de lo que se guarda en la base de datos (después de reducirlo).
BYTES_MAXIMOS_GUARDADOS = 1_500_000

# Caché en memoria: IdBebida -> (Actualizado, bytes de la foto)
_cache: dict[int, tuple[object, bytes]] = {}
_candado = threading.Lock()


class ErrorImagen(ValueError):
    """La foto no se puede usar (formato, tamaño o archivo dañado).

    El mensaje está pensado para mostrarse tal cual al administrador.
    """


# ------------------------------------------------------------
# Preparación de la foto
# ------------------------------------------------------------
def tipo_por_firma(datos: bytes) -> str | None:
    """Reconoce el formato por los primeros bytes, no por la extensión."""
    if not datos:
        return None
    if datos.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if datos[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if datos[:4] == b"RIFF" and datos[8:12] == b"WEBP":
        return "image/webp"
    return None


def preparar_imagen(datos: bytes) -> tuple[bytes, str]:
    """Valida y reduce la foto. Devuelve (bytes, tipo MIME).

    Lanza ErrorImagen si la foto no sirve.
    """
    if not datos:
        raise ErrorImagen("El archivo está vacío.")

    tipo_original = tipo_por_firma(datos)
    if tipo_original is None:
        raise ErrorImagen("El archivo no es una foto PNG, JPG o WEBP.")

    try:
        from PIL import Image, ImageOps
    except ImportError:  # pragma: no cover - Pillow viene con reportlab
        Image = None

    if Image is None:
        # Sin Pillow no se puede reducir: se guarda tal cual si es ligera.
        if len(datos) > BYTES_MAXIMOS_GUARDADOS:
            raise ErrorImagen("La foto es muy pesada. Usa una de menos de 1.5 MB.")
        return bytes(datos), tipo_original

    try:
        with Image.open(io.BytesIO(datos)) as original:
            imagen = ImageOps.exif_transpose(original)
            tiene_alfa = imagen.mode in ("RGBA", "LA") or (
                imagen.mode == "P" and "transparency" in imagen.info
            )
            imagen = imagen.convert("RGBA" if tiene_alfa else "RGB")
            imagen.thumbnail((LADO_MAXIMO, LADO_MAXIMO))

            salida = io.BytesIO()
            if tiene_alfa:
                # PNG conserva la transparencia (fondos recortados).
                imagen.save(salida, format="PNG", optimize=True)
                tipo = "image/png"
            else:
                imagen.save(
                    salida,
                    format="JPEG",
                    quality=CALIDAD_JPEG,
                    optimize=True,
                    progressive=True,
                )
                tipo = "image/jpeg"
    except Exception:
        raise ErrorImagen("No se pudo leer la foto. Prueba con otra imagen.") from None

    resultado = salida.getvalue()
    if len(resultado) > BYTES_MAXIMOS_GUARDADOS:
        raise ErrorImagen("La foto es muy pesada aun reducida. Prueba con otra imagen.")
    return resultado, tipo


# ------------------------------------------------------------
# Escritura
# ------------------------------------------------------------
def _cerrar_conexion(conn, cur):
    try:
        if cur:
            cur.close()
        if conn:
            conn.close()
    except Exception:
        pass


def _olvidar(id_bebida) -> None:
    with _candado:
        _cache.pop(int(id_bebida), None)


def guardar_imagen_bebida(id_bebida: int, datos: bytes) -> int:
    """Guarda (o reemplaza) la foto de una bebida en la base de datos.

    Devuelve el tamaño final en bytes. Lanza ErrorImagen si la foto no
    sirve, o el error de la base de datos si no se pudo guardar.
    """
    datos_finales, tipo = preparar_imagen(datos)

    conn = None
    cur = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        # REPLACE funciona igual en MySQL 5.7 (local) y 9.4 (Railway).
        # Al reemplazar la fila, Actualizado vuelve a tomar la hora
        # actual y eso invalida la copia en memoria de otros equipos.
        cur.execute(
            """
            REPLACE INTO bebidas_imagenes (IdBebida, Datos, Tipo, Bytes)
            VALUES (%s, %s, %s, %s)
            """,
            (int(id_bebida), datos_finales, tipo, len(datos_finales)),
        )
        # La ruta vieja (assets/bebidas) deja de usarse.
        cur.execute(
            "UPDATE bebidas SET Imagen=NULL WHERE IdBebida=%s",
            (int(id_bebida),),
        )
        conn.commit()
    except Exception:
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        raise
    finally:
        _cerrar_conexion(conn, cur)

    _olvidar(id_bebida)
    return len(datos_finales)


def guardar_imagen_desde_archivo(id_bebida: int, ruta: str) -> int:
    """Lee la foto elegida por el admin y la guarda en la base de datos."""
    archivo = Path(ruta)
    try:
        tamano = archivo.stat().st_size
    except OSError:
        raise ErrorImagen("No se encontró la foto elegida.") from None

    if tamano > BYTES_MAXIMOS_ORIGINAL:
        raise ErrorImagen("La foto pesa más de 15 MB. Elige una más ligera.")

    return guardar_imagen_bebida(id_bebida, archivo.read_bytes())


def eliminar_imagen_bebida(id_bebida: int) -> None:
    """Quita la foto de una bebida (vuelve a mostrarse el emoji)."""
    conn = None
    cur = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM bebidas_imagenes WHERE IdBebida=%s", (int(id_bebida),))
        conn.commit()
    except Exception:
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        raise
    finally:
        _cerrar_conexion(conn, cur)

    _olvidar(id_bebida)


# ------------------------------------------------------------
# Lectura
# ------------------------------------------------------------
def _marcadores(cantidad: int) -> str:
    return ", ".join(["%s"] * cantidad)


def _ids_validos(ids) -> list[int]:
    validos = []
    for valor in ids or []:
        try:
            validos.append(int(valor))
        except (TypeError, ValueError):
            continue
    return sorted(set(validos))


def versiones_imagenes(ids) -> dict[int, object]:
    """IdBebida -> Actualizado, solo de las bebidas que tienen foto.

    Es una consulta ligera: no descarga las fotos.
    """
    ids = _ids_validos(ids)
    if not ids:
        return {}

    conn = None
    cur = None
    try:
        conn = get_connection()
        cur = conn.cursor(dictionary=True)
        cur.execute(
            f"""
            SELECT IdBebida, Actualizado
            FROM bebidas_imagenes
            WHERE IdBebida IN ({_marcadores(len(ids))})
            """,
            tuple(ids),
        )
        filas = cur.fetchall() or []
        return {int(f["IdBebida"]): f["Actualizado"] for f in filas}
    except Exception:
        return {}
    finally:
        _cerrar_conexion(conn, cur)


def obtener_datos_imagenes(versiones: dict) -> dict[int, bytes]:
    """IdBebida -> bytes de la foto.

    `versiones` es IdBebida -> Actualizado (lo que devuelve
    versiones_imagenes o el LEFT JOIN del menú). Solo descarga las
    fotos que no están en memoria o que cambiaron.
    """
    resultado: dict[int, bytes] = {}
    faltantes: list[int] = []

    with _candado:
        for id_bebida, version in (versiones or {}).items():
            if version is None:
                continue
            try:
                id_bebida = int(id_bebida)
            except (TypeError, ValueError):
                continue
            guardada = _cache.get(id_bebida)
            if guardada and guardada[0] == version:
                resultado[id_bebida] = guardada[1]
            else:
                faltantes.append(id_bebida)

    if not faltantes:
        return resultado

    conn = None
    cur = None
    try:
        conn = get_connection()
        cur = conn.cursor(dictionary=True)
        cur.execute(
            f"""
            SELECT IdBebida, Datos, Actualizado
            FROM bebidas_imagenes
            WHERE IdBebida IN ({_marcadores(len(faltantes))})
            """,
            tuple(faltantes),
        )
        filas = cur.fetchall() or []
    except Exception:
        # Sin internet o sin tabla: se devuelve lo que había en memoria
        # y las demás bebidas muestran su emoji.
        return resultado
    finally:
        _cerrar_conexion(conn, cur)

    with _candado:
        for fila in filas:
            datos = fila.get("Datos")
            if not datos:
                continue
            id_bebida = int(fila["IdBebida"])
            datos = bytes(datos)
            _cache[id_bebida] = (fila.get("Actualizado"), datos)
            resultado[id_bebida] = datos
    return resultado


def imagenes_de_bebidas(ids) -> dict[int, bytes]:
    """Atajo para el panel de admin: IdBebida -> bytes de la foto."""
    return obtener_datos_imagenes(versiones_imagenes(ids))


def limpiar_cache() -> None:
    """Vacía la copia en memoria (lo usan las pruebas)."""
    with _candado:
        _cache.clear()