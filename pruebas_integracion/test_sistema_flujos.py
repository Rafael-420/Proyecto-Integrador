"""
pruebas_integracion/test_sistema_flujos.py
------------------------------------------
CP-SIS: pruebas de sistema de punta a punta sobre la capa de servicios.

Cada caso recorre un flujo completo como lo vive un usuario, con todos
los servicios trabajando juntos contra la misma base real. No cubren la
interfaz de Flet: lo que pasa en pantalla (y el cobro en caja chica,
que todavia vive dentro de vistas/vista_caja_chica.py) se prueba a mano
con los casos del documento de pruebas.

Ejecutar desde la raiz del proyecto:

    python -m unittest pruebas_integracion.test_sistema_flujos -v
"""

from __future__ import annotations

import unittest
from datetime import timedelta

from pruebas_integracion import base_pruebas as bp

from configuracion.base_datos import get_connection
from servicios import servicio_autenticacion as auth
from servicios import servicio_bebidas as bebidas
from servicios import servicio_horario as horario
from servicios import servicio_menu as menu
from servicios import servicio_privacidad as privacidad
from servicios import servicio_sesion as sesion


class _Pagina:
    """Lo minimo de ft.Page que usa servicio_sesion."""


def _registrar_cliente(usuario: str, contrasena: str) -> int:
    """Alta como la hace vista_registro: cuenta, datos y consentimiento juntos."""
    id_usuario = auth.crear_usuario(usuario, contrasena, "CLIENTE")
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO cliente (Nombre, Apellido, Telefono, Correo, Usuario_IdUsuario) "
            "VALUES ('Pedro', 'Perez', '3222089781', 'pedro@gmail.com', %s)",
            (id_usuario,),
        )
        id_cliente = cur.lastrowid
        privacidad.registrar_consentimiento(cur, id_usuario, "registro_cliente")
        conn.commit()
    finally:
        cur.close()
        conn.close()
    return id_cliente


class TestFlujoDelCliente(bp.BaseIntegracion):
    """CP-SIS-01 y 02."""

    def setUp(self):
        super().setUp()
        bebidas.crear_bebida("Té Boba Fresa", 59, "Con perlas", "Milk Tea")
        bebidas.crear_bebida("Matcha Latte", 69, "Premium", "Especialidad")

    def test_cliente_nuevo_se_registra_entra_y_pide(self):
        """CP-SIS-01: registro, inicio de sesion, menu, pedido, estado e historial."""
        id_cliente = _registrar_cliente("pedro10", "Corallie2026")

        resultado = auth.autenticar("pedro10", "Corallie2026")
        self.assertTrue(resultado.exito, resultado.mensaje)
        pagina = _Pagina()
        sesion.iniciar_sesion(pagina, resultado.usuario.id, resultado.usuario.rol)
        self.assertEqual(sesion.ruta_inicio(sesion.rol_actual(pagina)), "/menu")
        self.assertFalse(sesion.puede_acceder(sesion.rol_actual(pagina), "/caja_chica"))

        catalogo = menu.obtener_bebidas()
        self.assertEqual(len(catalogo), 2)
        self.assertEqual(menu.puede_pedir(id_cliente)[0], True)

        bebida = catalogo[0]
        texto = f"{bebida['nombre']} (x2) [Tamaño: Mediano | Boba: 70% | Hielo: 70% | Leche: Entera]"
        pedido_id = menu.insertar_pedido(id_cliente, texto, bebida["precio"] * 2, "Pedro", metodo_pago="Efectivo")

        activo = menu.obtener_pedido_activo(id_cliente)
        self.assertEqual(activo["IdGenerarPedido"], pedido_id)
        self.assertEqual(activo["Estatus"], "Pedido Realizado")
        self.assertEqual([h["IdGenerarPedido"] for h in menu.obtener_historial(id_cliente)], [pedido_id])
        self.assertEqual(bp.contar("consentimiento_privacidad"), 1)

        sesion.cerrar_sesion(pagina)
        self.assertIsNone(sesion.rol_actual(pagina))

    def test_cliente_cancela_y_vuelve_a_pedir(self):
        """CP-SIS-02: cancelar el pedido antes de prepararlo libera al cliente."""
        id_cliente = bp.crear_cliente()["id_cliente"]
        primero = menu.insertar_pedido(id_cliente, "Matcha Latte (x1) [Mediano]", 69, "Ana")
        self.assertFalse(menu.puede_pedir(id_cliente)[0])
        self.assertTrue(menu.cancelar_pedido(id_cliente, primero))
        segundo = menu.insertar_pedido(id_cliente, "Matcha Latte (x1) [Mediano]", 69, "Ana")
        self.assertNotEqual(primero, segundo)


class TestFlujoNoRecogido(bp.BaseIntegracion):
    """CP-SIS-03."""

    def test_pedido_olvidado_bloquea_y_se_paga_en_el_local(self):
        """CP-SIS-03: pide, no recoge, se marca solo, queda bloqueado, paga en el local y vuelve a pedir."""
        id_cliente = bp.crear_cliente()["id_cliente"]
        pedido = menu.insertar_pedido(id_cliente, "Taro Milk Tea (x1) [Mediano]", 65, "Ana")

        # Pasaron 3 horas sin que el cliente recogiera su bebida.
        bp.ejecutar(
            "UPDATE generarpedido SET FechaPedido = %s, HoraPedido = %s WHERE IdGenerarPedido = %s",
            (
                (bp.ahora_local() - timedelta(hours=3)).date(),
                (bp.ahora_local() - timedelta(hours=3)).time().replace(microsecond=0),
                pedido,
            ),
        )
        self.assertEqual(menu.marcar_no_recogidos_vencidos(), 1)

        permitido, mensaje, _detalles = menu.puede_pedir(id_cliente)
        self.assertFalse(permitido)
        self.assertIn("65.00", mensaje)
        pendientes = menu.pedidos_no_recogidos()
        self.assertEqual([p["IdGenerarPedido"] for p in pendientes], [pedido])

        self.assertTrue(menu.liquidar_no_recogido(pedido))
        self.assertTrue(menu.puede_pedir(id_cliente)[0])
        menu.insertar_pedido(id_cliente, "Taro Milk Tea (x1) [Mediano]", 65, "Ana")


class TestFlujoDelAdministrador(bp.BaseIntegracion):
    """CP-SIS-04 y 05."""

    def test_pausa_y_reanuda_el_servicio(self):
        """CP-SIS-04: el admin pausa el menu, el cliente no puede pedir, lo reanuda y si puede."""
        admin = auth.crear_usuario("admin1", "Corallie2026", "ADMIN")
        resultado = auth.autenticar("admin1", "Corallie2026")
        self.assertEqual(resultado.usuario.id, admin)
        self.assertEqual(sesion.ruta_inicio(resultado.usuario.rol), "/admin")
        self.assertTrue(sesion.puede_acceder(resultado.usuario.rol, "/admin_servicio"))

        id_cliente = bp.crear_cliente()["id_cliente"]
        horario.guardar_servicio_menu(False, "Volvemos en 30 minutos", 0, "admin1")
        permitido, mensaje, _ = menu.puede_pedir(id_cliente)
        self.assertFalse(permitido)
        self.assertEqual(mensaje, "Volvemos en 30 minutos")

        horario.guardar_servicio_menu(True, None, 0, "admin1")
        self.assertTrue(menu.puede_pedir(id_cliente)[0])

    def test_bebida_agotada_desaparece_del_menu_del_cliente(self):
        """CP-SIS-05: el admin agota una bebida y el cliente deja de verla."""
        taro = bebidas.crear_bebida("Taro Milk Tea", 65, "", "Especialidad")
        bebidas.crear_bebida("Matcha Latte", 69, "", "Especialidad")
        bebidas.marcar_disponibilidad(taro, False)
        self.assertEqual([b["nombre"] for b in menu.obtener_bebidas()], ["Matcha Latte"])


class TestFlujoDeRecuperacion(bp.BaseIntegracion):
    """CP-SIS-06."""

    def test_olvido_su_contrasena(self):
        """CP-SIS-06: solicita, el admin atiende, entra con la temporal, la cambia y entra con la nueva."""
        empleado = bp.crear_empleado()
        solicitud = auth.registrar_solicitud(empleado["usuario"], "juan@gmail.com", "empleado")
        _usuario, _correo, temporal = auth.atender_solicitud(solicitud)

        resultado = auth.autenticar(empleado["usuario"], temporal)
        self.assertTrue(resultado.exito)
        self.assertTrue(resultado.usuario.requiere_cambio)
        self.assertEqual(sesion.ruta_inicio(resultado.usuario.rol), "/pos")

        cambio = auth.cambiar_contrasena(empleado["id_usuario"], temporal, "MiNueva2026")
        self.assertTrue(cambio.exito, cambio.mensaje)
        final = auth.autenticar(empleado["usuario"], "MiNueva2026")
        self.assertTrue(final.exito)
        self.assertFalse(final.usuario.requiere_cambio)
        self.assertFalse(auth.autenticar(empleado["usuario"], temporal).exito)


if __name__ == "__main__":
    unittest.main(verbosity=2)