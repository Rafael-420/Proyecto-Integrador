"""
pruebas_integracion/datos_volumen.py
------------------------------------
Genera una base grande, parecida a la de varios meses de operacion.

La usan dos programas:

  * pruebas_integracion/test_volumen.py  (CP-VOL, con tamanos moderados)
  * pruebas_rendimiento/rendimiento.py    (tamanos mayores y medicion de tiempos)

Los datos se escriben directo en las tablas con executemany, cientos de
filas por instruccion, sin pasar por el codigo que se va a probar. Solo
las fotos de las bebidas se guardan con servicio_imagenes_bebidas,
porque ese servicio es el que las reduce y las parte en trozos.

Que deja en la base (con los valores por omision):

  clientes          1,000 (usuario volNNNN, correo volNNNN@gmail.com)
  pedidos           10 historicos por cliente, entregados o cancelados
  vencidos          300 pedidos "Pedido Realizado" de hace mas de 2 h
                    (clientes 1 a 300)
  recientes         200 pedidos "Pedido Realizado" de hace menos de 1 h
                    (clientes 301 a 500)
  cortes            100 cortes con 20 ventas, 5 egresos y 1 ingreso cada uno
  bebidas           60 en el menu, 20 de ellas con foto
"""

from __future__ import annotations

import io
import time
from dataclasses import dataclass
from datetime import timedelta

from pruebas_integracion import base_pruebas as bp

_NOMBRES_ESTATUS = {3: "Pedido Realizado", 4: "Entregado", 5: "Cancelado"}

_SQL_PEDIDO = (
    "INSERT INTO generarpedido (HoraPedido, FechaPedido, Producto, Total, NumeroMesa, Estatus, "
    "EstatusPedido_IdEstatusPedido, Clientes_Idcliente) VALUES (%s, %s, %s, %s, 1, %s, %s, %s)"
)


@dataclass(frozen=True)
class Volumen:
    clientes: int = 1000
    pedidos_por_cliente: int = 10
    vencidos: int = 300
    recientes: int = 200
    cortes: int = 100
    ventas_por_corte: int = 20
    egresos_por_corte: int = 5
    bebidas: int = 60
    bebidas_con_foto: int = 20

    @property
    def pedidos_totales(self) -> int:
        return self.clientes * self.pedidos_por_cliente + self.vencidos + self.recientes

    @property
    def ventas_totales(self) -> int:
        return self.cortes * self.ventas_por_corte


def foto_de_prueba(lado: int = 600) -> bytes:
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (lado, lado), (190, 120, 210)).save(buffer, "PNG")
    return buffer.getvalue()


def _por_bloques(cur, sql: str, filas: list, tamano: int = 1000) -> None:
    for i in range(0, len(filas), tamano):
        cur.executemany(sql, filas[i : i + tamano])


def cargar(volumen: Volumen = Volumen()) -> float:
    """Llena la base de pruebas. Devuelve los segundos que tardo.

    Requiere una base vacia (bp.limpiar_datos()). Los IdCliente quedan
    del 1 al numero de clientes, en orden.
    """
    if volumen.vencidos + volumen.recientes > volumen.clientes:
        raise ValueError("Cada pedido vencido o reciente necesita un cliente distinto.")

    inicio = time.monotonic()
    ahora = bp.ahora_local().replace(microsecond=0)
    conn = bp._conectar_servidor(con_base=True)
    cur = conn.cursor()
    clientes = range(1, volumen.clientes + 1)

    # Clientes. La contrasena no importa: estas cuentas no inician sesion.
    _por_bloques(
        cur,
        "INSERT INTO usuario (IdUsuario, NombreUsuario, `Contraseña`, Rol) VALUES (%s, %s, 'x', 'CLIENTE')",
        [(c, f"vol{c:05d}") for c in clientes],
    )
    _por_bloques(
        cur,
        "INSERT INTO cliente (IdCliente, Nombre, Apellido, Telefono, Correo, Usuario_IdUsuario) "
        "VALUES (%s, 'Cliente', %s, '3221234567', %s, %s)",
        [(c, f"V{c:05d}", f"vol{c:05d}@gmail.com", c) for c in clientes],
    )

    def pedido(cliente: int, estatus: int, momento) -> tuple:
        return (
            momento.time(),
            momento.date(),
            "Taro Milk Tea (x1) [Mediano]",
            65.0,
            _NOMBRES_ESTATUS[estatus],
            estatus,
            cliente,
        )

    # Historial: dias anteriores, cada cliente con su propia hora.
    _por_bloques(
        cur,
        _SQL_PEDIDO,
        [
            pedido(c, 4 if k % 3 else 5, ahora - timedelta(days=k + 1, seconds=c))
            for c in clientes
            for k in range(volumen.pedidos_por_cliente)
        ],
    )
    # Vencidos: entre 2.5 y 6.5 horas de antiguedad.
    _por_bloques(
        cur,
        _SQL_PEDIDO,
        [pedido(i + 1, 3, ahora - timedelta(minutes=150 + i % 240)) for i in range(volumen.vencidos)],
    )
    # Recientes: entre 5 y 55 minutos de antiguedad.
    _por_bloques(
        cur,
        _SQL_PEDIDO,
        [
            pedido(volumen.vencidos + i + 1, 3, ahora - timedelta(minutes=5 + i % 50))
            for i in range(volumen.recientes)
        ],
    )

    # Cortes de caja con sus ventas y movimientos.
    _por_bloques(
        cur,
        "INSERT INTO cortecaja (idCorteCaja, Hora_Inicio, Hora_Terminar, Fecha_Inicio, DineroEnCaja, IngresoDia, "
        "EgresoDIa, PlatillosVendidos, DineroFinalizar, TiempoTrascurrido, FechaFinalizar, "
        "Administrador_idAdministrador) VALUES (%s, '08:00:00', '00:00', %s, 500, 0, 0, 0, 0, 0, %s, 1)",
        [
            (c + 1, (ahora - timedelta(days=c)).strftime("%Y-%m-%d"), (ahora - timedelta(days=c)).date())
            for c in range(volumen.cortes)
        ],
    )
    ventas = [
        (c * volumen.ventas_por_corte + v + 1, (ahora - timedelta(days=c)).date(), c + 1)
        for c in range(volumen.cortes)
        for v in range(volumen.ventas_por_corte)
    ]
    _por_bloques(
        cur,
        "INSERT INTO ventas (IdVentas, Hora, FechaVenta, DetalleVenta, CorteCaja_idCorteCaja) "
        "VALUES (%s, '12:00:00', %s, 'Taro', %s)",
        ventas,
    )
    _por_bloques(
        cur,
        "INSERT INTO detalleventas (Subtotal, Impuesto, Descuento, Total, Ventas_IdVentas) VALUES (%s, 0, 0, %s, %s)",
        [(50 + (v % 7) * 5, 50 + (v % 7) * 5, v) for v, _fecha, _corte in ventas],
    )
    _por_bloques(
        cur,
        "INSERT INTO ingresos_egresos (TipoMovimiento, Monto, Descripcion, Fecha, Hora, CorteCaja_idCorteCaja) "
        "VALUES (%s, %s, 'volumen', CURDATE(), CURTIME(), %s)",
        [("Egreso", 10 + e, c + 1) for c in range(volumen.cortes) for e in range(volumen.egresos_por_corte)]
        + [("Ingreso", 100, c + 1) for c in range(volumen.cortes)],
    )

    # Menu.
    _por_bloques(
        cur,
        "INSERT INTO bebidas (IdBebida, Nombre, Precio, Descripcion, Categoria, Disponible) "
        "VALUES (%s, %s, 65, '', 'Volumen', 1)",
        [(b + 1, f"Bebida volumen {b + 1:02d}") for b in range(volumen.bebidas)],
    )
    conn.commit()
    cur.close()
    conn.close()

    from servicios import servicio_imagenes_bebidas as imagenes

    foto = foto_de_prueba()
    for b in range(volumen.bebidas_con_foto):
        imagenes.guardar_imagen_bebida(b + 1, foto)
    imagenes.limpiar_cache()

    return time.monotonic() - inicio
