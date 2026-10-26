"""
pruebas/test_servicio_empleados.py
----------------------------------
Pruebas unitarias de servicios/servicio_empleados.py.

Este servicio SI toca MySQL, pero una prueba unitaria no debe depender
de Railway: si la nube esta caida o sin credito, la prueba fallaria por
una causa ajena al codigo. Por eso se sustituye get_connection() por un
objeto simulado (mock) con unittest.mock.patch.

Con el mock se verifica lo que es responsabilidad del servicio:
  - que manda la consulta parametrizada (sin concatenar valores),
  - que convierte el id a entero,
  - que hace commit o rollback segun corresponda,
  - que SIEMPRE cierra cursor y conexion, aun si algo falla
    (importante con el pool de base_datos.py: una conexion sin cerrar
    no regresa al pool y lo termina agotando).

No se verifica que el SQL sea correcto contra el esquema real: eso es
trabajo de las pruebas de integracion.

Ejecutar desde la raiz del proyecto:

    python -m unittest pruebas.test_servicio_empleados -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

_RAIZ = Path(__file__).resolve().parent.parent
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))

from servicios import servicio_empleados  # noqa: E402

# Ruta que se parchea: el nombre tal como lo importo el servicio.
_GET_CONNECTION = "servicios.servicio_empleados.get_connection"

_EMPLEADO = {
    "IdEmpleado": 5,
    "Nombre": "Ana",
    "Apellido": "Lopez",
    "Telefono": "3221234567",
    "Correo": "ana@gmail.com",
    "NombreUsuario": "ana_caja",
}


def _conexion_simulada(fila=None, error_execute=None):
    """Crea una conexion y un cursor falsos ya enlazados."""
    conexion = MagicMock(name="conexion")
    cursor = MagicMock(name="cursor")
    conexion.cursor.return_value = cursor
    cursor.fetchone.return_value = fila
    if error_execute is not None:
        cursor.execute.side_effect = error_execute
    return conexion, cursor


class PruebasObtenerEmpleado(unittest.TestCase):
    """CP-EMP-01 a CP-EMP-04: consulta de perfil de empleado."""

    def test_devuelve_la_fila_encontrada(self):
        conexion, cursor = _conexion_simulada(fila=_EMPLEADO)
        with patch(_GET_CONNECTION, return_value=conexion):
            resultado = servicio_empleados.obtener_empleado_por_id(5)

        self.assertEqual(resultado, _EMPLEADO)
        conexion.cursor.assert_called_once_with(dictionary=True)

    def test_empleado_inexistente_devuelve_none(self):
        conexion, _ = _conexion_simulada(fila=None)
        with patch(_GET_CONNECTION, return_value=conexion):
            self.assertIsNone(servicio_empleados.obtener_empleado_por_id(999))

    def test_consulta_parametrizada_con_id_entero(self):
        """El id llega como texto desde la UI; se debe mandar como int."""
        conexion, cursor = _conexion_simulada(fila=_EMPLEADO)
        with patch(_GET_CONNECTION, return_value=conexion):
            servicio_empleados.obtener_empleado_por_id("5")

        sql, parametros = cursor.execute.call_args.args
        self.assertIn("%s", sql)
        self.assertNotIn("5", sql)
        self.assertEqual(parametros, (5,))

    def test_cierra_conexion_en_exito(self):
        conexion, cursor = _conexion_simulada(fila=_EMPLEADO)
        with patch(_GET_CONNECTION, return_value=conexion):
            servicio_empleados.obtener_empleado_por_id(5)

        cursor.close.assert_called_once()
        conexion.close.assert_called_once()

    def test_cierra_conexion_si_la_consulta_falla(self):
        conexion, cursor = _conexion_simulada(error_execute=RuntimeError("BD caida"))
        with patch(_GET_CONNECTION, return_value=conexion):
            with self.assertRaises(RuntimeError):
                servicio_empleados.obtener_empleado_por_id(5)

        cursor.close.assert_called_once()
        conexion.close.assert_called_once()

    def test_id_invalido_lanza_error_y_cierra(self):
        conexion, cursor = _conexion_simulada()
        with patch(_GET_CONNECTION, return_value=conexion):
            with self.assertRaises(ValueError):
                servicio_empleados.obtener_empleado_por_id("abc")

        cursor.execute.assert_not_called()
        conexion.close.assert_called_once()


class PruebasActualizarPerfil(unittest.TestCase):
    """CP-EMP-05 a CP-EMP-08: edicion del perfil de empleado."""

    def _actualizar(self, conexion, id_empleado=5):
        with patch(_GET_CONNECTION, return_value=conexion):
            servicio_empleados.actualizar_empleado_perfil(
                id_empleado, "Ana", "Lopez", "3221234567", "ana@gmail.com"
            )

    def test_manda_los_parametros_en_orden(self):
        conexion, cursor = _conexion_simulada()
        self._actualizar(conexion, id_empleado="5")

        sql, parametros = cursor.execute.call_args.args
        self.assertTrue(sql.strip().upper().startswith("UPDATE EMPLEADO"))
        self.assertEqual(
            parametros, ("Ana", "Lopez", "3221234567", "ana@gmail.com", 5)
        )

    def test_hace_commit_y_cierra(self):
        conexion, cursor = _conexion_simulada()
        self._actualizar(conexion)

        conexion.commit.assert_called_once()
        conexion.rollback.assert_not_called()
        cursor.close.assert_called_once()
        conexion.close.assert_called_once()

    def test_error_hace_rollback_y_propaga(self):
        """La vista necesita la excepcion para mostrar el mensaje de error."""
        conexion, cursor = _conexion_simulada(error_execute=RuntimeError("Duplicate entry"))
        with self.assertRaises(RuntimeError):
            self._actualizar(conexion)

        conexion.rollback.assert_called_once()
        conexion.commit.assert_not_called()
        conexion.close.assert_called_once()

    def test_sin_conexion_propaga_el_error(self):
        """Si Railway no responde, el error sube sin fallos secundarios."""
        with patch(_GET_CONNECTION, side_effect=ConnectionError("timeout")):
            with self.assertRaises(ConnectionError):
                servicio_empleados.actualizar_empleado_perfil(
                    5, "Ana", "Lopez", "3221234567", "ana@gmail.com"
                )


if __name__ == "__main__":
    unittest.main(verbosity=2)