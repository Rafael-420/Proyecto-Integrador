"""Verifica la conexion a la base de datos y el estado de las tablas.

Ejecutar desde la raiz del proyecto:

    python verificar_conexion.py

No modifica nada: solo consulta.
"""

from configuracion.base_datos import get_connection, probar_conexion
from configuracion.variables import DB_HOST, DB_PORT, DB_NAME, DB_USER

TABLAS_ESPERADAS = [
    "bebidas",
    "cliente",
    "cortecaja",
    "detalleventas",
    "empleado",
    "entradarecibe",
    "entradasproductos",
    "estatuspedido",
    "generarpedido",
    "generarpedido_detalle",
    "generarrecibo",
    "ingresos_egresos",
    "productos",
    "productosstock",
    "recibos",
    "recibospedidos",
    "salidasproductos",
    "solicitudes_password",
    "tipossalidas",
    "usuario",
    "ventas",
]


def _linea(texto: str = "") -> None:
    print(texto)


def main() -> None:
    _linea("=" * 60)
    _linea("VERIFICACION DE BASE DE DATOS - Corallie Bubble")
    _linea("=" * 60)
    _linea(f"Host    : {DB_HOST}:{DB_PORT}")
    _linea(f"Usuario : {DB_USER}")
    _linea(f"Base    : {DB_NAME}")
    _linea()

    exito, mensaje = probar_conexion()
    _linea(mensaje)
    if not exito:
        _linea()
        _linea("Revisa el archivo .env y que el servicio MySQL este activo.")
        return

    conn = None
    cur = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SHOW TABLES")
        encontradas = sorted(fila[0] for fila in cur.fetchall())

        _linea()
        _linea(f"Tablas encontradas: {len(encontradas)} de {len(TABLAS_ESPERADAS)}")
        _linea("-" * 60)

        faltantes = [t for t in TABLAS_ESPERADAS if t not in encontradas]
        extra = [t for t in encontradas if t not in TABLAS_ESPERADAS]

        for tabla in encontradas:
            cur.execute(f"SELECT COUNT(*) FROM `{tabla}`")
            total = cur.fetchone()[0]
            _linea(f"  {tabla:<25} {total:>6} registros")

        _linea("-" * 60)
        if faltantes:
            _linea(f"FALTAN estas tablas: {', '.join(faltantes)}")
            _linea("Vuelve a importar ing_software_railway.sql")
        else:
            _linea("Todas las tablas esperadas estan presentes.")

        if extra:
            _linea(f"Tablas adicionales (no esperadas): {', '.join(extra)}")

        # Comprobacion puntual del catalogo de bebidas
        if "bebidas" in encontradas:
            cur.execute("SELECT COUNT(*) FROM bebidas WHERE Disponible = 1")
            _linea(f"Bebidas disponibles en el menu: {cur.fetchone()[0]}")

    except Exception as error:
        _linea(f"Error al consultar las tablas: {error}")
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

    _linea("=" * 60)


if __name__ == "__main__":
    main()
