"""Servicio del menú interactivo de clientes.

Este archivo concentra las consultas a base de datos usadas por vista_menu.py.
Así la vista se mantiene más limpia y sólo se encarga de construir la interfaz.
"""

import re
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


# --------------------------------------------------------
# Reglas de pedidos para recoger
# --------------------------------------------------------
# El problema a resolver: clientes que piden por la app y no pasan por
# la bebida. La bebida se prepara antes de cobrar, así que un pedido no
# recogido es producto perdido.
#
# Reglas acordadas por el equipo:
#   1. Un solo pedido activo por cliente.
#   2. Máximo 3 bebidas por pedido, contando cantidades.
#   3. Un pedido "No recogido" bloquea al cliente para pedir por la app;
#      se desbloquea pagando ese pedido en el local.

ESTATUS_PAGADO = 1
ESTATUS_EN_PREPARACION = 2
ESTATUS_PEDIDO_REALIZADO = 3
ESTATUS_ENTREGADO = 4
ESTATUS_CANCELADO = 5
ESTATUS_NO_RECOGIDO = 6  # requiere la migración migracion_no_recogido.sql

ESTATUS_ACTIVOS = (ESTATUS_PAGADO, ESTATUS_EN_PREPARACION, ESTATUS_PEDIDO_REALIZADO)

MAX_BEBIDAS_POR_PEDIDO = 3
MINUTOS_PARA_NO_RECOGIDO = 120

SEPARADOR_PRODUCTOS = " / "


class PedidoNoPermitido(Exception):
    """El cliente no puede registrar este pedido.

    A diferencia de un error técnico, esto es una regla de negocio: la
    vista debe mostrar el mensaje al cliente, no un error del sistema.
    """

    def __init__(self, mensaje: str, motivo: str, detalles: dict | None = None):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.motivo = motivo
        self.detalles = detalles or {}


def contar_bebidas(producto_texto: str) -> int:
    """Cuenta las bebidas del pedido, sumando cantidades.

    El texto del pedido viene como "Taro (x2) [Mediano] / Matcha (x1) [...]",
    así que se suman los (xN). Si una línea no trae cantidad, cuenta como
    una bebida.
    """
    texto = str(producto_texto or "").strip()
    if not texto:
        return 0

    total = 0
    for linea in texto.split(SEPARADOR_PRODUCTOS):
        if not linea.strip():
            continue
        encontrado = re.search(r"\(x\s*(\d+)\)", linea)
        total += int(encontrado.group(1)) if encontrado else 1
    return total


def _adeudo_con_cursor(cur, cliente_id: int) -> tuple[int, float]:
    cur.execute(
        """
        SELECT COUNT(*), COALESCE(SUM(Total), 0)
        FROM generarpedido
        WHERE Clientes_Idcliente = %s
          AND EstatusPedido_IdEstatusPedido = %s
        """,
        (int(cliente_id), ESTATUS_NO_RECOGIDO),
    )
    fila = cur.fetchone() or (0, 0)
    return int(fila[0] or 0), float(fila[1] or 0)


def _pedido_activo_con_cursor(cur, cliente_id: int):
    cur.execute(
        """
        SELECT IdGenerarPedido
        FROM generarpedido
        WHERE Clientes_Idcliente = %s
          AND EstatusPedido_IdEstatusPedido IN (%s, %s, %s)
        ORDER BY IdGenerarPedido DESC
        LIMIT 1
        """,
        (int(cliente_id),) + ESTATUS_ACTIVOS,
    )
    fila = cur.fetchone()
    return int(fila[0]) if fila else None


def _mensaje_adeudo(pedidos: int, total: float) -> str:
    plural = "pedido" if pedidos == 1 else "pedidos"
    return (
        f"Tienes {pedidos} {plural} sin recoger por un monto pendiente de "
        f"$ {total:,.2f}. Pasa al local a pagarlo para volver a pedir desde la app."
    )


def adeudo_pendiente(cliente_id: int) -> dict | None:
    """Monto que el cliente debe por pedidos no recogidos.

    Devuelve None si no debe nada. La vista lo usa para mostrarle el
    aviso antes de que arme el carrito.
    """
    conn = None
    cur = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        pedidos, total = _adeudo_con_cursor(cur, cliente_id)
    except Exception:
        return None
    finally:
        cerrar_conexion(conn, cur)

    if pedidos <= 0:
        return None
    return {"pedidos": pedidos, "total": total, "mensaje": _mensaje_adeudo(pedidos, total)}


def puede_pedir(cliente_id: int) -> tuple[bool, str | None, dict]:
    """Indica si el cliente puede hacer un pedido nuevo desde la app.

    Devuelve (permitido, mensaje, detalles). La vista lo consulta para
    deshabilitar el botón de pedir y explicar el motivo; insertar_pedido
    vuelve a validarlo, porque la vista puede quedar desactualizada.
    """
    conn = None
    cur = None
    try:
        conn = get_connection()
        cur = conn.cursor()

        pedidos, total = _adeudo_con_cursor(cur, cliente_id)
        if pedidos > 0:
            return False, _mensaje_adeudo(pedidos, total), {
                "motivo": "adeudo",
                "pedidos": pedidos,
                "total": total,
            }

        activo = _pedido_activo_con_cursor(cur, cliente_id)
        if activo:
            return False, (
                f"Ya tienes el pedido #{activo} en curso. "
                "Recógelo antes de hacer uno nuevo."
            ), {"motivo": "pedido_activo", "pedido_id": activo}

        return True, None, {"motivo": "ok"}
    except Exception:
        # Ante una falla de conexión no se bloquea al cliente: la
        # validación definitiva ocurre igualmente en insertar_pedido.
        return True, None, {"motivo": "error_conexion"}
    finally:
        cerrar_conexion(conn, cur)


def marcar_no_recogido(pedido_id: int) -> bool:
    """Marca un pedido como no recogido (lo hace el empleado en caja).

    Solo aplica a pedidos que siguen sin entregarse ni cobrarse.
    """
    conn = None
    cur = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE generarpedido
            SET Estatus = 'No recogido',
                EstatusPedido_IdEstatusPedido = %s
            WHERE IdGenerarPedido = %s
              AND EstatusPedido_IdEstatusPedido = %s
            """,
            (ESTATUS_NO_RECOGIDO, int(pedido_id), ESTATUS_PEDIDO_REALIZADO),
        )
        conn.commit()
        return cur.rowcount > 0
    except Exception:
        if conn:
            conn.rollback()
        return False
    finally:
        cerrar_conexion(conn, cur)


def marcar_no_recogidos_vencidos(minutos: int = MINUTOS_PARA_NO_RECOGIDO) -> int:
    """Marca automáticamente los pedidos que llevan demasiado tiempo sin recogerse.

    Devuelve cuántos pedidos se marcaron. No hay proceso en segundo plano:
    la vista de caja la llama al abrir la lista de pedidos y al cerrar el
    corte, que es cuando importa que la lista esté al día.
    """
    conn = None
    cur = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE generarpedido
            SET Estatus = 'No recogido',
                EstatusPedido_IdEstatusPedido = %s
            WHERE EstatusPedido_IdEstatusPedido = %s
              AND TIMESTAMPADD(MINUTE, %s, TIMESTAMP(FechaPedido, HoraPedido)) < NOW()
            """,
            (ESTATUS_NO_RECOGIDO, ESTATUS_PEDIDO_REALIZADO, int(minutos)),
        )
        conn.commit()
        return int(cur.rowcount or 0)
    except Exception:
        if conn:
            conn.rollback()
        return 0
    finally:
        cerrar_conexion(conn, cur)


def liquidar_no_recogido(pedido_id: int) -> bool:
    """Registra que el cliente pagó en el local un pedido no recogido.

    Es lo que lo desbloquea para volver a pedir desde la app.
    """
    conn = None
    cur = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE generarpedido
            SET Estatus = 'Pagado en mostrador',
                EstatusPedido_IdEstatusPedido = %s
            WHERE IdGenerarPedido = %s
              AND EstatusPedido_IdEstatusPedido = %s
            """,
            (ESTATUS_ENTREGADO, int(pedido_id), ESTATUS_NO_RECOGIDO),
        )
        conn.commit()
        return cur.rowcount > 0
    except Exception:
        if conn:
            conn.rollback()
        return False
    finally:
        cerrar_conexion(conn, cur)


def pedidos_no_recogidos(cliente_id: int | None = None) -> list[dict]:
    """Lista los pedidos no recogidos, para cobrarlos en el local."""
    conn = None
    cur = None
    try:
        conn = get_connection()
        cur = conn.cursor(dictionary=True)
        if cliente_id is None:
            cur.execute(
                """
                SELECT gp.IdGenerarPedido, gp.FechaPedido, gp.HoraPedido, gp.Producto,
                       gp.Total, gp.Clientes_Idcliente,
                       CONCAT(COALESCE(c.Nombre, ''), ' ', COALESCE(c.Apellido, '')) AS Cliente
                FROM generarpedido gp
                LEFT JOIN cliente c ON c.IdCliente = gp.Clientes_Idcliente
                WHERE gp.EstatusPedido_IdEstatusPedido = %s
                ORDER BY gp.FechaPedido ASC, gp.HoraPedido ASC
                """,
                (ESTATUS_NO_RECOGIDO,),
            )
        else:
            cur.execute(
                """
                SELECT gp.IdGenerarPedido, gp.FechaPedido, gp.HoraPedido, gp.Producto,
                       gp.Total, gp.Clientes_Idcliente,
                       CONCAT(COALESCE(c.Nombre, ''), ' ', COALESCE(c.Apellido, '')) AS Cliente
                FROM generarpedido gp
                LEFT JOIN cliente c ON c.IdCliente = gp.Clientes_Idcliente
                WHERE gp.EstatusPedido_IdEstatusPedido = %s
                  AND gp.Clientes_Idcliente = %s
                ORDER BY gp.FechaPedido ASC, gp.HoraPedido ASC
                """,
                (ESTATUS_NO_RECOGIDO, int(cliente_id)),
            )
        return cur.fetchall() or []
    except Exception:
        return []
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

    bebidas = contar_bebidas(producto_texto)
    if bebidas > MAX_BEBIDAS_POR_PEDIDO:
        raise PedidoNoPermitido(
            f"Máximo {MAX_BEBIDAS_POR_PEDIDO} bebidas por pedido; "
            f"tu pedido tiene {bebidas}.",
            motivo="max_bebidas",
            detalles={"bebidas": bebidas, "maximo": MAX_BEBIDAS_POR_PEDIDO},
        )

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

        # Las reglas se revisan con el mismo cursor, justo antes de
        # insertar, para que la vista no pueda saltárselas.
        pedidos_sin_recoger, monto = _adeudo_con_cursor(cur, cliente_id)
        if pedidos_sin_recoger > 0:
            raise PedidoNoPermitido(
                _mensaje_adeudo(pedidos_sin_recoger, monto),
                motivo="adeudo",
                detalles={"pedidos": pedidos_sin_recoger, "total": monto},
            )

        activo = _pedido_activo_con_cursor(cur, cliente_id)
        if activo:
            raise PedidoNoPermitido(
                f"Ya tienes el pedido #{activo} en curso. "
                "Recógelo antes de hacer uno nuevo.",
                motivo="pedido_activo",
                detalles={"pedido_id": activo},
            )

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