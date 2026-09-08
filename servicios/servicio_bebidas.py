"""Servicio de administración del catálogo de bebidas (menú del cliente).

Importante: esto NO es lo mismo que `productos`/`productosstock`. Esas
tablas son inventario de materias primas (azúcar, leche, toppings). Este
archivo administra la tabla `bebidas`, que es el catálogo real del menú
que el cliente ve, y que solo el admin puede crear/editar/marcar como
agotado.
"""

import re
import shutil
from pathlib import Path
from configuracion.base_datos import get_connection


CARPETA_IMAGENES_BEBIDAS = Path("assets") / "bebidas"


def _cerrar_conexion(conn, cur):
    try:
        if cur:
            cur.close()
        if conn:
            conn.close()
    except Exception:
        pass


def _slug_archivo(texto: str) -> str:
    """Convierte el nombre de una bebida en un nombre de archivo seguro."""
    texto = (texto or "").strip().lower()
    texto = re.sub(r"[^a-z0-9]+", "_", texto).strip("_")
    return texto or "bebida"


def guardar_archivo_imagen_bebida(origen_path: str, nombre_bebida: str) -> str | None:
    """Copia la foto elegida a assets/bebidas y devuelve la ruta relativa
    (para usar como src en ft.Image), o None si no se pudo copiar."""
    try:
        CARPETA_IMAGENES_BEBIDAS.mkdir(parents=True, exist_ok=True)
        extension = Path(origen_path).suffix.lower() or ".png"
        nombre_archivo = f"{_slug_archivo(nombre_bebida)}{extension}"
        destino = CARPETA_IMAGENES_BEBIDAS / nombre_archivo
        shutil.copy(origen_path, destino)
        return f"bebidas/{nombre_archivo}"
    except Exception:
        return None


def listar_bebidas_admin() -> list[dict]:
    """Lista todas las bebidas (disponibles y agotadas) para el panel admin."""
    conn = None
    cur = None
    try:
        conn = get_connection()
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT IdBebida, Nombre, Precio, Descripcion, Categoria, Imagen, Disponible
            FROM bebidas
            ORDER BY Nombre ASC
            """
        )
        return cur.fetchall() or []
    except Exception:
        return []
    finally:
        _cerrar_conexion(conn, cur)


def existe_bebida(nombre: str, exclude_id=None) -> bool:
    conn = None
    cur = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        if exclude_id:
            cur.execute(
                "SELECT COUNT(*) FROM bebidas WHERE LOWER(TRIM(Nombre)) = LOWER(TRIM(%s)) AND IdBebida <> %s",
                (nombre, int(exclude_id)),
            )
        else:
            cur.execute(
                "SELECT COUNT(*) FROM bebidas WHERE LOWER(TRIM(Nombre)) = LOWER(TRIM(%s))",
                (nombre,),
            )
        row = cur.fetchone()
        return (row[0] or 0) > 0
    except Exception:
        return False
    finally:
        _cerrar_conexion(conn, cur)


def crear_bebida(nombre: str, precio: float, descripcion: str, categoria: str) -> int:
    conn = None
    cur = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO bebidas (Nombre, Precio, Descripcion, Categoria, Disponible)
            VALUES (%s, %s, %s, %s, 1)
            """,
            (nombre, float(precio), descripcion, categoria),
        )
        conn.commit()
        return int(cur.lastrowid)
    except Exception:
        if conn:
            conn.rollback()
        raise
    finally:
        _cerrar_conexion(conn, cur)


def editar_bebida(id_bebida: int, nombre: str, precio: float, descripcion: str, categoria: str):
    conn = None
    cur = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE bebidas
            SET Nombre=%s, Precio=%s, Descripcion=%s, Categoria=%s
            WHERE IdBebida=%s
            """,
            (nombre, float(precio), descripcion, categoria, int(id_bebida)),
        )
        conn.commit()
    except Exception:
        if conn:
            conn.rollback()
        raise
    finally:
        _cerrar_conexion(conn, cur)


def guardar_imagen_bebida(id_bebida: int, ruta_relativa: str):
    conn = None
    cur = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "UPDATE bebidas SET Imagen=%s WHERE IdBebida=%s",
            (ruta_relativa, int(id_bebida)),
        )
        conn.commit()
    except Exception:
        if conn:
            conn.rollback()
    finally:
        _cerrar_conexion(conn, cur)


def marcar_disponibilidad(id_bebida: int, disponible: bool):
    """Marca una bebida como agotada (False) o disponible (True).

    No se borra: sigue existiendo para historial/reportes, solo deja de
    aparecer en el menú del cliente mientras esté agotada.
    """
    conn = None
    cur = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "UPDATE bebidas SET Disponible=%s WHERE IdBebida=%s",
            (1 if disponible else 0, int(id_bebida)),
        )
        conn.commit()
    except Exception:
        if conn:
            conn.rollback()
    finally:
        _cerrar_conexion(conn, cur)


def eliminar_bebida(id_bebida: int):
    conn = None
    cur = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM bebidas WHERE IdBebida=%s", (int(id_bebida),))
        conn.commit()
    except Exception:
        if conn:
            conn.rollback()
        raise
    finally:
        _cerrar_conexion(conn, cur)
