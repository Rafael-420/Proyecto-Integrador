"""
pruebas_integracion/test_datos_pedidos.py
-----------------------------------------
CP-DDT: pruebas basadas en datos (data-driven testing) de las reglas
para registrar un pedido.

Los escenarios no estan escritos en el codigo: se leen de
pruebas_integracion/datos/escenarios_pedidos.csv. Cada fila del CSV se
convierte en un caso de prueba independiente (CP-DDT-01, CP-DDT-02...)
con su propia base limpia. Para probar un escenario nuevo basta con
agregar una fila; no hay que programar nada.

Columnas del CSV:

  productos          texto del pedido. {texto:N} genera un pedido valido
                     de exactamente N caracteres.
  total              importe del pedido.
  estado_previo      pedido que el cliente ya tiene: ninguno, realizado,
                     en_preparacion, pagado, entregado, cancelado o
                     no_recogido.
  local              situacion del local: abierto, pausado, dia_cerrado,
                     descanso, caja_desconectada, antes_de_abrir o
                     despues_de_cerrar.
  resultado_esperado aceptado, ValueError o el motivo de rechazo de
                     PedidoNoPermitido (max_bebidas, pedido_activo...).

Ejecutar desde la raiz del proyecto:

    python -m unittest pruebas_integracion.test_datos_pedidos -v
"""

from __future__ import annotations

import csv
import re
import unittest
from pathlib import Path

from pruebas_integracion import base_pruebas as bp

from servicios import servicio_horario as horario
from servicios import servicio_menu as menu

ARCHIVO_DATOS = Path(__file__).resolve().parent / "datos" / "escenarios_pedidos.csv"

ESTATUS_PREVIO = {
    "pagado": 1,
    "en_preparacion": 2,
    "realizado": 3,
    "entregado": 4,
    "cancelado": 5,
    "no_recogido": 6,
}

# Escenarios que hoy fallan por un defecto conocido. Al corregirlo, el
# resumen avisa que la prueba "ya pasa" y el escenario pasa de esta
# lista a REGRESIONES.
DEFECTOS_CONOCIDOS: dict[str, str] = {}

# Escenarios que encontraron un defecto ya corregido. Se quedan como
# prueba de regresion: si el defecto vuelve, fallan.
REGRESIONES = {
    "33": "D-22",  # migracion_utf8mb4.sql
}


COLUMNAS = ("id", "descripcion", "productos", "total", "estado_previo", "local", "resultado_esperado")


class DatosNoEncontrados(Exception):
    """El CSV de escenarios no esta donde se espera o no se puede leer."""


def _explicar_archivo_faltante() -> str:
    """Dice donde se busco el CSV y que archivos parecidos hay."""
    carpeta = ARCHIVO_DATOS.parent
    parecidos = sorted(
        {p for base in (carpeta, carpeta.parent) if base.is_dir() for p in base.glob("escenarios_pedidos*")}
    )
    lineas = [
        "No se encontro el archivo de escenarios:",
        f"    {ARCHIVO_DATOS}",
        "Debe estar en la carpeta 'datos', dentro de pruebas_integracion, y llamarse",
        "exactamente escenarios_pedidos.csv.",
    ]
    if not carpeta.is_dir():
        lineas.append("La carpeta 'datos' no existe: creala dentro de pruebas_integracion.")
    if parecidos:
        lineas.append("Se encontraron estos archivos parecidos (muevelo o cambiale el nombre):")
        lineas.extend(f"    {p}" for p in parecidos)
    return "\n".join(lineas)


def leer_escenarios() -> list[dict]:
    """Lee el CSV de escenarios.

    Acepta el archivo tal como se entrega (UTF-8, separado por comas) y
    tambien como lo guarda Excel en espanol (ANSI, separado por punto y
    coma), para que editarlo en Excel no rompa la prueba.
    """
    if not ARCHIVO_DATOS.is_file():
        raise DatosNoEncontrados(_explicar_archivo_faltante())

    crudo = ARCHIVO_DATOS.read_bytes()
    try:
        texto = crudo.decode("utf-8-sig")
    except UnicodeDecodeError:
        texto = crudo.decode("cp1252")

    primera = texto.splitlines()[0] if texto else ""
    separador = ";" if primera.count(";") > primera.count(",") else ","
    filas = list(csv.DictReader(texto.splitlines(), delimiter=separador))

    faltan = [c for c in COLUMNAS if not filas or c not in filas[0]]
    if faltan:
        raise DatosNoEncontrados(
            f"{ARCHIVO_DATOS} no tiene las columnas {', '.join(faltan)}.\n"
            f"La primera linea debe ser: {','.join(COLUMNAS)}"
        )
    # Excel quita los ceros a la izquierda (01 -> 1): se devuelven.
    for fila in filas:
        if fila["id"].strip().isdigit():
            fila["id"] = f"{int(fila['id']):02d}"
    return filas


def texto_del_pedido(valor: str) -> str:
    """Devuelve el texto tal cual o genera uno de N caracteres para {texto:N}."""
    generado = re.fullmatch(r"\{texto:(\d+)\}", valor.strip())
    if not generado:
        return valor
    largo = int(generado.group(1))
    inicio, fin = "Taro Milk Tea (x1) [Notas: ", "]"
    return inicio + "a" * (largo - len(inicio) - len(fin)) + fin


def preparar_local(situacion: str, prueba: unittest.TestCase) -> None:
    """Deja el local en la situacion indicada (parte de abierto todo el dia)."""
    ahora = bp.ahora_local()
    hoy = ahora.weekday()
    if situacion == "abierto":
        return
    if situacion == "pausado":
        bp.ejecutar("UPDATE estado_servicio SET MenuActivo = 0, MensajeMenu = NULL")
    elif situacion == "dia_cerrado":
        horario.agregar_dia_cerrado(ahora.date(), "Inventario", hoy=ahora.date())
    elif situacion == "descanso":
        bp.ejecutar("UPDATE horario_local SET Abierto = 0 WHERE DiaSemana = %s", (hoy,))
    elif situacion == "caja_desconectada":
        bp.conectar_caja(hace_minutos=10)
    elif situacion == "antes_de_abrir":
        if ahora.strftime("%H:%M") >= "23:59":
            prueba.skipTest("A las 23:59 no se puede abrir mas tarde el mismo dia.")
        bp.ejecutar(
            "UPDATE horario_local SET HoraApertura = '23:59:00', HoraCierre = '23:59:59' WHERE DiaSemana = %s",
            (hoy,),
        )
    elif situacion == "despues_de_cerrar":
        if ahora.strftime("%H:%M:%S") < "00:00:02":
            prueba.skipTest("A las 00:00 no se puede haber cerrado ya.")
        bp.ejecutar(
            "UPDATE horario_local SET HoraApertura = '00:00:00', HoraCierre = '00:00:01' WHERE DiaSemana = %s",
            (hoy,),
        )
    else:
        raise ValueError(f"Situacion del local desconocida en el CSV: {situacion}")


class TestEscenariosDePedido(bp.BaseIntegracion):
    """CP-DDT: un caso por cada fila de escenarios_pedidos.csv."""

    def ejecutar_escenario(self, fila: dict) -> None:
        cliente = bp.crear_cliente()
        id_cliente = cliente["id_cliente"]

        previo = fila["estado_previo"].strip()
        if previo != "ninguno":
            bp.crear_pedido_directo(id_cliente, estatus=ESTATUS_PREVIO[previo], hace_minutos=300)
        preparar_local(fila["local"].strip(), self)

        productos = texto_del_pedido(fila["productos"])
        total = float(fila["total"])
        esperado = fila["resultado_esperado"].strip()
        antes = bp.contar("generarpedido")

        if esperado == "aceptado":
            pedido = menu.insertar_pedido(id_cliente, productos, total, "Ana")
            guardado = bp.uno(
                "SELECT Producto, EstatusPedido_IdEstatusPedido AS estatus FROM generarpedido WHERE IdGenerarPedido = %s",
                (pedido,),
            )
            self.assertIsNotNone(guardado)
            self.assertEqual(guardado["estatus"], 3)
            self.assertEqual(guardado["Producto"], productos)
            self.assertEqual(bp.contar("generarpedido"), antes + 1)
            return

        if esperado == "ValueError":
            with self.assertRaises(ValueError) as ctx:
                menu.insertar_pedido(id_cliente, productos, total, "Ana")
            self.assertIs(type(ctx.exception), ValueError)
        else:
            with self.assertRaises(menu.PedidoNoPermitido) as ctx:
                menu.insertar_pedido(id_cliente, productos, total, "Ana")
            self.assertEqual(ctx.exception.motivo, esperado)
        self.assertEqual(bp.contar("generarpedido"), antes, "Un pedido rechazado no debe guardarse.")


def _crear_caso(fila: dict):
    def prueba(self):
        self.ejecutar_escenario(fila)

    defecto = DEFECTOS_CONOCIDOS.get(fila["id"])
    regresion = REGRESIONES.get(fila["id"])
    if defecto:
        etiqueta = f" (defecto {defecto})"
    elif regresion:
        etiqueta = f" (regresion {regresion})"
    else:
        etiqueta = ""
    prueba.__doc__ = (
        f"CP-DDT-{fila['id']}{etiqueta}: {fila['descripcion']} -> {fila['resultado_esperado']}."
    )
    return unittest.expectedFailure(prueba) if defecto else prueba


for _fila in leer_escenarios():
    setattr(TestEscenariosDePedido, f"test_escenario_{_fila['id']}", _crear_caso(_fila))


if __name__ == "__main__":
    unittest.main(verbosity=2)