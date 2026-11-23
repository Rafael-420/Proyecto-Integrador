"""
pruebas_integracion/test_integracion_esquema.py
-----------------------------------------------
CP-ESQ: el esquema y las migraciones contra un MySQL real.

Riesgos que se cubren:

  1. Que una migracion de recursos/ falle sobre el esquema original o
     no se pueda volver a ejecutar (la herramienta dice que son
     repetibles).
  2. Que el codigo use tablas o columnas que la base no tiene: con
     objetos simulados ese error nunca aparece.
  3. Que un valor que escribe el codigo no quepa en su columna.

Ejecutar desde la raiz del proyecto:

    python -m unittest pruebas_integracion.test_integracion_esquema -v
"""

from __future__ import annotations

import unittest

from pruebas_integracion import base_pruebas as bp


class TestMigraciones(bp.BaseIntegracion):
    """CP-ESQ-01 a 03."""

    def test_migraciones_se_aplican_sin_error(self):
        """CP-ESQ-01: las migraciones de recursos/ se aplican sobre el esquema original."""
        self.assertEqual(len(bp.RESULTADO_MIGRACIONES), len(bp.MIGRACIONES))
        for resultado in bp.RESULTADO_MIGRACIONES:
            with self.subTest(archivo=resultado["archivo"]):
                self.assertEqual(resultado["codigo"], 0, resultado["salida"])
                self.assertIn("Con error: 0", resultado["salida"])

    def test_migraciones_se_pueden_repetir(self):
        """CP-ESQ-02: ejecutar otra vez cada migracion no produce errores."""
        for ruta in bp.MIGRACIONES:
            with self.subTest(archivo=ruta.name):
                resultado = bp.aplicar_migracion(ruta)
                self.assertEqual(resultado["codigo"], 0, resultado["salida"])
                self.assertIn("Con error: 0", resultado["salida"])

    def test_estatus_de_pedido_completos(self):
        """CP-ESQ-03: existen los seis estatus que usa servicio_menu."""
        filas = bp.consultar("SELECT IdEstatusPedido AS id, SituacionPedido AS nombre FROM estatuspedido ORDER BY 1")
        self.assertEqual(
            [(f["id"], f["nombre"]) for f in filas],
            [
                (1, "Pagado"),
                (2, "En preparación"),
                (3, "Pedido Realizado"),
                (4, "Entregado"),
                (5, "Cancelado"),
                (6, "No recogido"),
            ],
        )


class TestServidorComoRailway(bp.BaseIntegracion):
    """CP-ESQ-11."""

    def test_servidor_en_utc_y_modo_estricto(self):
        """CP-ESQ-11: el servidor de pruebas esta en UTC y en modo estricto, como Railway."""
        servidor = bp.verificar_servidor()
        self.assertLessEqual(abs(servidor["diferencia_minutos"]), 1, servidor)
        self.assertIn("STRICT_TRANS_TABLES", servidor["modo"], servidor)


class TestEsquemaQueUsaElCodigo(bp.BaseIntegracion):
    """CP-ESQ-04 a 08."""

    TABLAS = (
        "usuario", "cliente", "empleado", "bebidas", "bebidas_imagenes",
        "generarpedido", "estatuspedido", "recibospedidos", "cortecaja",
        "ventas", "detalleventas", "ingresos_egresos", "productos",
        "productosstock", "entradasproductos", "salidasproductos",
        "solicitudes_password", "intentos_login", "horario_local",
        "dias_cerrados", "estado_servicio", "consentimiento_privacidad",
    )

    def _columnas(self, tabla: str) -> dict:
        filas = bp.consultar(
            "SELECT COLUMN_NAME AS col, DATA_TYPE AS tipo, CHARACTER_MAXIMUM_LENGTH AS largo "
            "FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s",
            (tabla,),
        )
        return {f["col"]: f for f in filas}

    def test_existen_las_tablas_que_usa_el_codigo(self):
        """CP-ESQ-04: todas las tablas consultadas por servicios y vistas existen."""
        existentes = {
            f["t"] for f in bp.consultar(
                "SELECT TABLE_NAME AS t FROM information_schema.TABLES WHERE TABLE_SCHEMA = DATABASE()"
            )
        }
        faltantes = [t for t in self.TABLAS if t not in existentes]
        self.assertEqual(faltantes, [])

    def test_columnas_de_seguridad_en_usuario(self):
        """CP-ESQ-05: usuario tiene las columnas de la migracion y la contrasena cabe en 255."""
        columnas = self._columnas("usuario")
        for nombre in ("Activo", "RequiereCambio", "FechaCambioPassword"):
            self.assertIn(nombre, columnas)
        self.assertEqual(columnas["Contraseña"]["largo"], 255)

        from servicios import servicio_seguridad

        self.assertLessEqual(len(servicio_seguridad.hashear("Corallie2026")), 255)

    def test_corte_manager_encuentra_sus_columnas(self):
        """CP-ESQ-06: los nombres que busca corte_manager existen en cortecaja."""
        from servicios import corte_manager

        columnas = corte_manager._cortecaja_cols()
        for candidatos in (
            ["Hora_Inicio", "HoraInicio"],
            ["Hora_Terminar", "Hora_Termino", "HoraFin"],
            ["Fecha_Inicio", "Fecha_Inico", "FechaInicio"],
            ["FechaFinalizar", "Fecha_Fin", "FechaFin"],
            ["Administrador_idAdministrador", "AdministradorId", "Empleado_idEmpleado"],
            ["EgresoDIa", "EgresoDia"],
        ):
            with self.subTest(candidatos=candidatos):
                corte_manager._pick(columnas, candidatos)

    def test_columnas_de_la_senal_de_caja(self):
        """CP-ESQ-07: estado_servicio tiene las columnas de la señal y una sola fila."""
        columnas = self._columnas("estado_servicio")
        for nombre in ("UltimaSenalCaja", "InicioDesconexionCaja", "FinDesconexionCaja", "MinutosAntesCierre"):
            self.assertIn(nombre, columnas)
        self.assertEqual(bp.contar("estado_servicio"), 1)

    def test_textos_de_estatus_caben_en_la_columna(self):
        """CP-ESQ-08: los textos de estatus que escribe el codigo caben en generarpedido.Estatus."""
        largo = self._columnas("generarpedido")["Estatus"]["largo"]
        textos = (
            "Pedido Realizado", "En preparación", "Listo para entrega",
            "Pagado en mostrador", "No recogido", "Cancelado", "Pagado",
        )
        for texto in textos:
            with self.subTest(texto=texto):
                self.assertLessEqual(len(texto), largo)


class TestIntegridadReferencial(bp.BaseIntegracion):
    """CP-ESQ-09, 10 y 12."""

    def test_los_textos_aceptan_emojis(self):
        """CP-ESQ-12 (regresion D-22): todas las columnas de texto usan utf8mb4 y guardan un emoji completo."""
        fuera = bp.consultar(
            "SELECT TABLE_NAME AS tabla, COLUMN_NAME AS columna, CHARACTER_SET_NAME AS juego "
            "FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() "
            "AND CHARACTER_SET_NAME IS NOT NULL AND CHARACTER_SET_NAME <> 'utf8mb4' "
            "ORDER BY TABLE_NAME, COLUMN_NAME"
        )
        self.assertEqual(
            fuera, [], "Estas columnas no aceptan emojis: "
            + ", ".join(f"{f['tabla']}.{f['columna']} ({f['juego']})" for f in fuera)
        )

        # Un nombre de cliente y una bebida con emojis se guardan completos
        cliente = bp.crear_cliente(nombre="Ana \U0001F49C")
        bp.ejecutar(
            "INSERT INTO bebidas (Nombre, Precio, Descripcion, Categoria, Disponible) "
            "VALUES (%s, 65, %s, 'Prueba', 1)",
            ("Taro \U0001F9CB", "Con perlas \U0001F60B"),
        )
        self.assertEqual(
            bp.uno("SELECT Nombre FROM cliente WHERE IdCliente = %s", (cliente["id_cliente"],))["Nombre"],
            "Ana \U0001F49C",
        )
        bebida = bp.uno("SELECT Nombre, Descripcion FROM bebidas WHERE Categoria = 'Prueba'")
        self.assertEqual((bebida["Nombre"], bebida["Descripcion"]), ("Taro \U0001F9CB", "Con perlas \U0001F60B"))

    def test_borrar_usuario_borra_su_cliente(self):
        """CP-ESQ-09: ON DELETE CASCADE de usuario a cliente."""
        cliente = bp.crear_cliente()
        bp.ejecutar("DELETE FROM usuario WHERE IdUsuario = %s", (cliente["id_usuario"],))
        self.assertEqual(bp.contar("cliente", "IdCliente = %s", (cliente["id_cliente"],)), 0)

    def test_no_se_acepta_un_estatus_inexistente(self):
        """CP-ESQ-10: la llave foranea rechaza un pedido con estatus 99."""
        import mysql.connector

        cliente = bp.crear_cliente()
        with self.assertRaises(mysql.connector.Error):
            bp.ejecutar(
                "INSERT INTO generarpedido (HoraPedido, FechaPedido, Producto, Total, NumeroMesa, Estatus, "
                "EstatusPedido_IdEstatusPedido, Clientes_Idcliente) VALUES (CURTIME(), CURDATE(), 'x', 10, 1, 'x', 99, %s)",
                (cliente["id_cliente"],),
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
