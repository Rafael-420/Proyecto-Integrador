"""Conexion unica a MySQL (local o en la nube).

Todas las vistas y servicios deben usar get_connection() desde aqui.

Cambios respecto a la version local:
  - Se agrega el puerto (Railway no usa 3306 en su proxy publico).
  - Se agrega timeout de conexion y charset utf8mb4.
  - Se usa un pool de conexiones para evitar el costo de abrir una
    conexion nueva por cada consulta contra un servidor remoto.
  - Si el pool se agota, se abre una conexion directa como respaldo,
    de modo que el comportamiento nunca es peor que el anterior.

La firma de get_connection() no cambio: el resto del proyecto no
requiere ninguna modificacion.
"""

import mysql.connector
from mysql.connector import pooling

from configuracion.variables import (
    DB_HOST,
    DB_PORT,
    DB_USER,
    DB_PASSWORD,
    DB_NAME,
    DB_SSL_DISABLED,
    DB_USAR_POOL,
    DB_POOL_SIZE,
    DB_TIMEOUT,
)

_NOMBRE_POOL = "corallie_pool"
_pool = None


def _parametros_conexion() -> dict:
    """Arma el diccionario de parametros de conexion."""
    parametros = {
        "host": DB_HOST,
        "port": DB_PORT,
        "user": DB_USER,
        "password": DB_PASSWORD,
        "database": DB_NAME,
        "charset": "utf8mb4",
        "use_unicode": True,
        "connection_timeout": DB_TIMEOUT,
        "autocommit": False,
    }
    if DB_SSL_DISABLED:
        parametros["ssl_disabled"] = True
    return parametros


def _obtener_pool():
    """Crea el pool la primera vez que se necesita."""
    global _pool
    if _pool is None:
        _pool = pooling.MySQLConnectionPool(
            pool_name=_NOMBRE_POOL,
            pool_size=DB_POOL_SIZE,
            pool_reset_session=True,
            **_parametros_conexion(),
        )
    return _pool


def _conexion_directa():
    """Conexion sin pool (comportamiento original)."""
    return mysql.connector.connect(**_parametros_conexion())


def get_connection():
    """Devuelve una conexion lista para usar.

    Recuerda cerrarla siempre con conn.close(); si viene del pool,
    close() la devuelve al pool en lugar de destruirla.
    """
    if not DB_USAR_POOL:
        return _conexion_directa()

    try:
        return _obtener_pool().get_connection()
    except Exception:
        # Pool agotado, no disponible o error al crearlo:
        # se abre una conexion normal para no bloquear la aplicacion.
        return _conexion_directa()


def probar_conexion() -> tuple[bool, str]:
    """Verifica la conexion y devuelve (exito, mensaje).

    Util para diagnosticar la migracion a la nube sin abrir la app.
    """
    conn = None
    cur = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT DATABASE(), VERSION()")
        base, version = cur.fetchone()
        return True, f"Conectado a '{base}' en {DB_HOST}:{DB_PORT} (MySQL {version})"
    except Exception as error:
        return False, f"Error de conexion con {DB_HOST}:{DB_PORT} -> {error}"
    finally:
        try:
            if cur is not None:
                cur.close()
        except Exception:
            pass
        try:
            if conn is not None:
                conn.close()
        except Exception:
            pass
