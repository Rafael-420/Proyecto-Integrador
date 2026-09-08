"""Servicio del menú interactivo de clientes.

Este archivo concentra las consultas a base de datos usadas por vista_menu.py.
Así la vista se mantiene más limpia y sólo se encarga de construir la interfaz.
"""

from datetime import datetime
from configuracion.base_datos import get_connection


# --------------------------------------------------------
# Catálogo (bebidas)
# --------------------------------------------------------
# El catálogo vive en su propia tabla `bebidas` (Nombre, Precio,
# Descripcion, Categoria, Imagen, Disponible), separada de
# `productos`/`productosstock`, que son inventario de materias primas
# (azúcar, leche, toppings) y no bebidas del menú.
#
# Emoji de respaldo por nombre, para cuando la bebida todavía no tiene
# foto subida por el admin.
EMOJIS_POR_NOMBRE = {
    "té boba fresa": "🍓",
    "té boba mango": "🥭",
    "taro milk tea": "🧋",
    "matcha latte": "🍵",
    "chocolate boba": "🍫",
    "smoothie frutos rojos": "🍒",
    "smoothie mango": "🥭",
    "frappé vainilla": "🍦",
}


def obtener_bebidas() -> list[dict]:
    """Obtiene el catálogo de bebidas DISPONIBLES para el menú del cliente.

    Las bebidas marcadas como agotadas (Disponible=0) por el admin no
    aparecen aquí.
    """
    conn = None
    cur = None

    try:
        conn = get_connection()
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT IdBebida, Nombre, Precio, Descripcion, Categoria, Imagen
            FROM bebidas
            WHERE Disponible = 1
            ORDER BY Nombre
            """
        )
        filas = cur.fetchall() or []
    except Exception:
        filas = []
    finally:
        cerrar_conexion(conn, cur)

    bebidas = []
    for fila in filas:
        nombre = str(fila.get("Nombre") or "Producto")
        clave = nombre.strip().lower()
        bebidas.append(
            {
                "id": fila.get("IdBebida"),
                "nombre": nombre,
                "precio": float(fila.get("Precio") or 0),
                "descripcion": str(fila.get("Descripcion") or ""),
                "categoria": str(fila.get("Categoria") or "General"),
                "emoji": EMOJIS_POR_NOMBRE.get(clave, "🧋"),
                "imagen": (fila.get("Imagen") or "").strip() or None,
            }
        )
    return bebidas


def resolver_cliente_id(nombre: str):
    """Busca el ID del cliente usando su nombre.

    Se usa como respaldo cuando la vista no recibe cliente_id desde el login.
    """
    conn = None
    cur = None

    try:
        conn = get_connection()
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT IdCliente, Nombre
            FROM cliente
            WHERE LOWER(TRIM(Nombre)) = LOWER(TRIM(%s))
            ORDER BY IdCliente DESC
            LIMIT 1
            """,
            (nombre,),
        )
        row = cur.fetchone()
        return int(row["IdCliente"]) if row else None
    except Exception:
        return None
    finally:
        cerrar_conexion(conn, cur)


def insertar_pedido(
    cliente_id: int,
    producto_texto: str,
    total: float,
    usuario_nombre: str,
    metodo_pago: str | None = None,
    notas: str | None = None,
) -> int:
    """Registra un pedido del cliente y devuelve el ID generado.

    metodo_pago y notas se guardan en el campo Observaciones (existía en la
    tabla pero no se estaba usando), para no tener que alterar el esquema.
    """
    # Tercera línea de defensa contra el pedido duplicado con Total $0.00:
    # aunque la vista falle, aquí nunca se registra un pedido sin
    # productos o sin importe.
    if not producto_texto or not producto_texto.strip():
        raise ValueError("No se puede registrar un pedido sin productos.")
    if float(total) <= 0:
        raise ValueError("No se puede registrar un pedido con total en cero.")

    conn = None
    cur = None

    partes_observaciones = []
    if metodo_pago:
        partes_observaciones.append(f"Método de pago preferido: {metodo_pago}")
    if notas and notas.strip():
        partes_observaciones.append(f"Notas del cliente: {notas.strip()}")
    observaciones = " | ".join(partes_observaciones) or None

    try:
        conn = get_connection()
        cur = conn.cursor()

        ahora = datetime.now()
        fecha = ahora.date()
        hora = ahora.time().replace(microsecond=0)

        cur.execute(
            """
            INSERT INTO generarpedido
            (
                HoraPedido,
                FechaPedido,
                Producto,
                Observaciones,
                Total,
                NumeroMesa,
                Estatus,
                EstatusPedido_IdEstatusPedido,
                Clientes_Idcliente
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                hora,
                fecha,
                producto_texto,
                observaciones,
                float(total),
                1,
                "Pedido Realizado",
                3,
                int(cliente_id),
            ),
        )
        pedido_id = cur.lastrowid

        registrar_recibo_pedido(cur, producto_texto, total, fecha, hora, usuario_nombre)

        conn.commit()
        return int(pedido_id)

    except Exception:
        if conn:
            conn.rollback()
        raise
    finally:
        cerrar_conexion(conn, cur)


def registrar_recibo_pedido(cursor, producto_texto: str, total: float, fecha, hora, usuario_nombre: str):
    """Intenta registrar el recibo del pedido sin detener el pedido principal."""
    try:
        cursor.execute(
            """
            INSERT INTO recibospedidos
            (Producto, Total, Fecha, Hora, Usuario)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                producto_texto,
                float(total),
                fecha,
                hora,
                usuario_nombre,
            ),
        )
    except Exception:
        pass


def obtener_historial(cliente_id: int, limit: int = 25) -> list[dict]:
    """Obtiene los últimos pedidos de un cliente."""
    conn = None
    cur = None

    try:
        conn = get_connection()
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT
                IdGenerarPedido,
                HoraPedido,
                FechaPedido,
                Producto,
                Observaciones,
                Total,
                Estatus,
                EstatusPedido_IdEstatusPedido
            FROM generarpedido
            WHERE Clientes_Idcliente = %s
            ORDER BY IdGenerarPedido DESC
            LIMIT %s
            """,
            (int(cliente_id), int(limit)),
        )
        return cur.fetchall() or []
    except Exception:
        return []
    finally:
        cerrar_conexion(conn, cur)


def obtener_pedido(cliente_id: int, pedido_id: int):
    """Obtiene un pedido específico del cliente."""
    conn = None
    cur = None

    try:
        conn = get_connection()
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT
                IdGenerarPedido,
                HoraPedido,
                FechaPedido,
                Producto,
                Observaciones,
                Total,
                Estatus,
                EstatusPedido_IdEstatusPedido
            FROM generarpedido
            WHERE IdGenerarPedido = %s
              AND Clientes_Idcliente = %s
            LIMIT 1
            """,
            (int(pedido_id), int(cliente_id)),
        )
        return cur.fetchone()
    except Exception:
        return None
    finally:
        cerrar_conexion(conn, cur)


def obtener_pedido_activo(cliente_id: int):
    """Obtiene el pedido más reciente que aún no ha sido entregado ni cancelado.

    Se usa para que la pestaña "Estado" siga mostrando el pedido en curso
    aunque el cliente haya cerrado sesión y vuelto a entrar (antes sólo se
    recordaba mientras duraba la sesión, en la variable ultimo_pedido).
    """
    conn = None
    cur = None

    try:
        conn = get_connection()
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT
                IdGenerarPedido,
                HoraPedido,
                FechaPedido,
                Producto,
                Observaciones,
                Total,
                Estatus,
                EstatusPedido_IdEstatusPedido
            FROM generarpedido
            WHERE Clientes_Idcliente = %s
              AND EstatusPedido_IdEstatusPedido IN (1, 2, 3)
            ORDER BY IdGenerarPedido DESC
            LIMIT 1
            """,
            (int(cliente_id),),
        )
        return cur.fetchone()
    except Exception:
        return None
    finally:
        cerrar_conexion(conn, cur)


def cancelar_pedido(cliente_id: int, pedido_id: int) -> bool:
    """Cancela un pedido, sólo si todavía no se ha empezado a preparar
    (EstatusPedido_IdEstatusPedido = 3, "Pedido Realizado").

    Devuelve True si se canceló, False si ya no era posible (por ejemplo
    porque el empleado ya lo tomó, cobró o entregó).
    """
    conn = None
    cur = None

    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE generarpedido
            SET Estatus = 'Cancelado',
                EstatusPedido_IdEstatusPedido = 5
            WHERE IdGenerarPedido = %s
              AND Clientes_Idcliente = %s
              AND EstatusPedido_IdEstatusPedido = 3
            """,
            (int(pedido_id), int(cliente_id)),
        )
        conn.commit()
        return cur.rowcount > 0
    except Exception:
        if conn:
            conn.rollback()
        return False
    finally:
        cerrar_conexion(conn, cur)


def cerrar_conexion(conn, cur):
    """Cierra cursor y conexión de forma segura."""
    try:
        if cur:
            cur.close()
        if conn:
            conn.close()
    except Exception:
        pass