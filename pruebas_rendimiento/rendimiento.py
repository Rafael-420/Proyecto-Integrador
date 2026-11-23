"""
pruebas_rendimiento/rendimiento.py
----------------------------------
Pruebas de rendimiento de Corallie Bubble (CP-REN).

Mide cuatro cosas, en este orden:

  1. Volumen      Tiempo de cada consulta del cliente y del corte de caja
                  con una base grande (20,000 pedidos, 365 cortes).
  2. Carga        10, 25 y 50 clientes a la vez: inician sesion, revisan
                  si pueden pedir, ven el menu, confirman un pedido y
                  consultan su estado. Al terminar se revisa que no falte
                  ni sobre ningun pedido.
  3. Carrera      El mismo cliente confirma desde 20 dispositivos en el
                  mismo instante: solo debe quedar un pedido.
  4. Estres       100, 150 y 200 clientes a la vez, para encontrar el
                  punto donde aparecen errores.
  5. Conexiones   Cuantas copias de la app (una por celular, cada una con
                  su propio pool de conexiones) caben a la vez en el
                  servidor antes de que MySQL responda "Too many connections".

Uso, desde la raiz del proyecto y con el mismo MySQL local de las
pruebas de integracion (ver pruebas_integracion/README.md):

    python pruebas_rendimiento/rendimiento.py            # completo, 2 a 4 minutos
    python pruebas_rendimiento/rendimiento.py --rapido   # version corta, menos de 1 minuto

Desde Visual Studio Code tambien se puede abrir este archivo y presionar
"Run Python File".

Al terminar deja en pruebas_rendimiento/resultados/:

    rendimiento_<modo>_AAAAMMDD_HHMMSS.md    tablas listas para el documento
    rendimiento_<modo>_AAAAMMDD_HHMMSS.csv   cada medicion en una fila

IMPORTANTE: igual que la suite de integracion, este programa BORRA Y
CREA la base de pruebas (ing_software_pruebas) y se niega a correr
contra Railway o contra una base cuyo nombre no contenga "prueba".
"""

from __future__ import annotations

import argparse
import csv
import math
import os
import platform
import random
import sys
import threading
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

# base_pruebas debe importarse antes que cualquier servicio: es la que
# apunta la app a la base de pruebas y revisa que no sea Railway.
from pruebas_integracion import base_pruebas as bp  # noqa: E402
from pruebas_integracion import datos_volumen  # noqa: E402
from pruebas_integracion.datos_volumen import Volumen  # noqa: E402

from mysql.connector import pooling  # noqa: E402

from configuracion import base_datos, variables  # noqa: E402
from servicios import corte_manager  # noqa: E402
from servicios import servicio_autenticacion as autenticacion  # noqa: E402
from servicios import servicio_imagenes_bebidas as imagenes  # noqa: E402
from servicios import servicio_menu as menu  # noqa: E402
from servicios import servicio_seguridad as seguridad  # noqa: E402

CARPETA_RESULTADOS = Path(__file__).resolve().parent / "resultados"
CONTRASENA = "Corallie2026"
PRODUCTO = "Taro Milk Tea (x1) [Tamaño: Mediano]"
TIEMPO_MAXIMO_HILOS = 300  # segundos; si un nivel tarda mas, se reporta como error


# ------------------------------------------------------------
# Configuracion de cada modo
# ------------------------------------------------------------
@dataclass(frozen=True)
class Plan:
    nombre: str
    volumen: Volumen
    repeticiones: int
    niveles_carga: tuple
    rondas: int
    carrera: int
    niveles_estres: tuple


COMPLETO = Plan(
    nombre="completo",
    volumen=Volumen(
        clientes=2000,
        pedidos_por_cliente=10,
        vencidos=300,
        recientes=200,
        cortes=365,
        ventas_por_corte=30,
        egresos_por_corte=5,
        bebidas=60,
        bebidas_con_foto=20,
    ),
    repeticiones=30,
    niveles_carga=(10, 25, 50),
    rondas=3,
    carrera=20,
    niveles_estres=(100, 150, 200),
)

RAPIDO = Plan(
    nombre="rapido",
    volumen=Volumen(),
    repeticiones=10,
    niveles_carga=(5, 10),
    rondas=2,
    carrera=10,
    niveles_estres=(25, 50),
)

# Metas fijadas antes de medir. El nivel de 25 clientes corresponde a una
# hora pico del local con holgura (el local atiende con una sola caja).
META_CONSULTA_MS = 500
META_FLUJO_MS = 2000
META_FLUJO_CLIENTES = 25
META_SIN_ERRORES_HASTA = 50


# ------------------------------------------------------------
# Registro de mediciones
# ------------------------------------------------------------
@dataclass
class Medicion:
    fase: str
    nivel: int
    operacion: str
    ms: float
    ok: bool
    detalle: str = ""


@dataclass
class Registro:
    mediciones: list = field(default_factory=list)
    _candado: threading.Lock = field(default_factory=threading.Lock)

    def agregar(self, medicion: Medicion) -> None:
        with self._candado:
            self.mediciones.append(medicion)

    def de(self, fase: str, nivel: int | None = None, operacion: str | None = None) -> list:
        return [
            m
            for m in self.mediciones
            if m.fase == fase
            and (nivel is None or m.nivel == nivel)
            and (operacion is None or m.operacion == operacion)
        ]


def percentil(valores: list, p: float) -> float:
    """Percentil por rango mas cercano: el valor que deja debajo el p % de las mediciones."""
    if not valores:
        return float("nan")
    ordenados = sorted(valores)
    indice = max(0, math.ceil(p / 100 * len(ordenados)) - 1)
    return ordenados[indice]


def estadisticas(mediciones: list) -> dict:
    tiempos = [m.ms for m in mediciones if m.ok]
    return {
        "n": len(mediciones),
        "ok": len(tiempos),
        "errores": len(mediciones) - len(tiempos),
        "p50": percentil(tiempos, 50),
        "p95": percentil(tiempos, 95),
        "max": max(tiempos) if tiempos else float("nan"),
    }


def describir_error(error: BaseException) -> str:
    codigo = getattr(error, "errno", None)
    texto = (getattr(error, "msg", None) or str(error) or "").splitlines()[0][:120]
    return f"{type(error).__name__}{f' {codigo}' if codigo else ''}: {texto}"


def medir(registro: Registro, fase: str, nivel: int, operacion: str, funcion, validar=None):
    """Ejecuta funcion(), guarda cuanto tardo y si el resultado es correcto.

    Varias funciones de la app no lanzan la excepcion cuando falla la base
    (devuelven [] o None para no romper la pantalla). Por eso cada medicion
    lleva su validacion: un menu vacio cuenta como error aunque no truene.
    """
    inicio = time.perf_counter()
    try:
        resultado = funcion()
    except Exception as error:  # noqa: BLE001 - se registra cualquier falla
        ms = (time.perf_counter() - inicio) * 1000
        registro.agregar(Medicion(fase, nivel, operacion, ms, False, describir_error(error)))
        return False, None
    ms = (time.perf_counter() - inicio) * 1000
    motivo = validar(resultado) if validar else ""
    registro.agregar(Medicion(fase, nivel, operacion, ms, not motivo, motivo or ""))
    return not motivo, resultado


# ------------------------------------------------------------
# Utilidades de servidor
# ------------------------------------------------------------
class Monitor:
    """Conexion aparte para leer contadores del servidor."""

    def __init__(self):
        self.conn = bp._conectar_servidor(con_base=True)

    def valor(self, sql: str) -> str | None:
        cur = self.conn.cursor()
        try:
            cur.execute(sql)
            fila = cur.fetchone()
            return None if fila is None else str(fila[-1])
        finally:
            cur.close()

    def consultas(self) -> int:
        return int(self.valor("SHOW GLOBAL STATUS LIKE 'Questions'") or 0)

    def reiniciar_maximo_conexiones(self) -> bool:
        try:
            cur = self.conn.cursor()
            cur.execute("FLUSH STATUS")
            cur.close()
            return True
        except Exception:
            return False

    def maximo_conexiones_usadas(self) -> int | None:
        valor = self.valor("SHOW GLOBAL STATUS LIKE 'Max_used_connections'")
        return int(valor) if valor is not None else None

    def conexiones_abiertas(self) -> int:
        return int(self.valor("SHOW GLOBAL STATUS LIKE 'Threads_connected'") or 0)

    def cerrar(self) -> None:
        try:
            self.conn.close()
        except Exception:
            pass


def viajes_a_la_base(monitor: Monitor, funcion) -> int:
    """Cuantas instrucciones manda la app al servidor en una llamada.

    Sirve para estimar el tiempo con internet de por medio: cada
    instruccion es un viaje de ida y vuelta al servidor.
    """
    antes = monitor.consultas()
    funcion()
    despues = monitor.consultas()
    return max(0, despues - antes - 1)  # el -1 descuenta la segunda lectura del contador


class Clientes:
    """Reparte clientes que no tienen pedidos en curso ni adeudos."""

    def __init__(self, volumen: Volumen):
        self._siguiente = volumen.vencidos + volumen.recientes + 1
        self._ultimo = volumen.clientes

    def tomar(self, cantidad: int) -> list:
        if self._siguiente + cantidad - 1 > self._ultimo:
            raise RuntimeError("La base de volumen no tiene suficientes clientes libres para este nivel.")
        bloque = list(range(self._siguiente, self._siguiente + cantidad))
        self._siguiente += cantidad
        return bloque


def usuario_de(cliente: int) -> str:
    return f"vol{cliente:05d}"


def dar_contrasena_real(clientes: list, hash_real: str) -> None:
    """Pone a esos clientes una contrasena PBKDF2 real (en la carga, IdUsuario = IdCliente)."""
    marcadores = ", ".join(["%s"] * len(clientes))
    bp.ejecutar(
        f"UPDATE usuario SET `Contraseña` = %s WHERE IdUsuario IN ({marcadores})",
        (hash_real, *clientes),
    )


# ------------------------------------------------------------
# Fase 1: volumen
# ------------------------------------------------------------
def fase_volumen(plan: Plan, registro: Registro, monitor: Monitor, clientes: Clientes, hash_real: str) -> list:
    volumen = plan.volumen
    azar = random.Random(2026)
    libres = clientes.tomar(plan.repeticiones)
    recientes = list(range(volumen.vencidos + 1, volumen.vencidos + volumen.recientes + 1))
    con_login = libres[0]
    dar_contrasena_real([con_login], hash_real)

    filas = []

    # El primer barrido marca los vencidos; se mide una sola vez.
    ok, marcados = medir(
        registro, "volumen", 0, f"Marcar {volumen.vencidos} pedidos vencidos como no recogidos",
        menu.marcar_no_recogidos_vencidos,
        lambda r: "" if r == volumen.vencidos else f"marco {r}, se esperaban {volumen.vencidos}",
    )

    def menu_sin_cache():
        imagenes.limpiar_cache()
        return menu.obtener_bebidas()

    def menu_completo(r):
        if len(r) != volumen.bebidas:
            return f"menu con {len(r)} bebidas"
        if sum(1 for b in r if b["imagen_datos"]) != volumen.bebidas_con_foto:
            return "faltan fotos"
        return ""

    casos = [
        ("Ver menú (fotos sin caché)", menu_sin_cache, menu_completo),
        ("Ver menú (fotos en caché)", menu.obtener_bebidas, menu_completo),
        (
            "Historial del cliente (últimos 25)",
            lambda: menu.obtener_historial(azar.choice(libres), 25),
            lambda r: "" if len(r) == min(25, volumen.pedidos_por_cliente) else f"{len(r)} pedidos",
        ),
        (
            "Estado del pedido en curso",
            lambda: menu.obtener_pedido_activo(azar.choice(recientes)),
            lambda r: "" if r else "no encontro el pedido",
        ),
        (
            "Revisar si puede pedir",
            lambda: menu.puede_pedir(azar.choice(libres)),
            lambda r: "" if r[0] and r[2].get("motivo") == "ok" else f"motivo {r[2].get('motivo')}",
        ),
        (
            "Revisar adeudo",
            lambda: menu.adeudo_pendiente(azar.randint(1, volumen.vencidos)),
            lambda r: "" if r and r["pedidos"] == 1 else "adeudo no encontrado",
        ),
        (
            "Resumen de un corte de caja",
            lambda: corte_manager.resumen_por_corte(azar.randint(1, volumen.cortes)),
            lambda r: "" if r[4] == volumen.ventas_por_corte else f"{r[4]} ventas",
        ),
        (
            "Barrido de no recogidos (sin pendientes)",
            menu.marcar_no_recogidos_vencidos,
            lambda r: "" if r == 0 else f"marco {r}",
        ),
        (
            f"Inicio de sesión (PBKDF2, {variables.SEG_ITERACIONES:,} iteraciones)",
            lambda: autenticacion.autenticar(usuario_de(con_login), CONTRASENA),
            lambda r: "" if r.exito else f"rechazado: {r.motivo}",
        ),
    ]

    for nombre, funcion, validar in casos:
        funcion()  # calentamiento: crea el pool y llena caches como en uso normal
        viajes = viajes_a_la_base(monitor, funcion)
        for _ in range(plan.repeticiones):
            medir(registro, "volumen", 0, nombre, funcion, validar)
        filas.append((nombre, viajes))
    return filas


# ------------------------------------------------------------
# Fases 2 y 4: carga y estres
# ------------------------------------------------------------
def cliente_simulado(
    cliente: int,
    fase: str,
    nivel: int,
    rondas: int,
    con_login: bool,
    bebidas: int,
    registro: Registro,
    barrera: threading.Barrier,
) -> None:
    usuario = usuario_de(cliente)
    try:
        barrera.wait(timeout=60)
    except threading.BrokenBarrierError:
        registro.agregar(Medicion(fase, nivel, "Flujo de pedido", 0, False, "no arranco a tiempo"))
        return

    if con_login:
        ok, _ = medir(
            registro, fase, nivel, "Inicio de sesión",
            lambda: autenticacion.autenticar(usuario, CONTRASENA),
            lambda r: "" if r.exito else f"rechazado: {r.motivo}",
        )
        if not ok:
            registro.agregar(Medicion(fase, nivel, "Flujo de pedido", 0, False, "no pudo iniciar sesion"))
            return

    for _ in range(rondas):
        inicio = time.perf_counter()
        pasos_ok = True
        pedido_id = None

        ok, _ = medir(
            registro, fase, nivel, "Revisar si puede pedir",
            lambda: menu.puede_pedir(cliente),
            # puede_pedir responde "si" ante una falla de conexion para no
            # bloquear al cliente; aqui eso cuenta como error.
            lambda r: "" if r[0] and r[2].get("motivo") == "ok" else f"motivo {r[2].get('motivo')}",
        )
        pasos_ok &= ok
        if ok:
            ok, _ = medir(
                registro, fase, nivel, "Ver menú",
                menu.obtener_bebidas,
                lambda r: "" if len(r) == bebidas else f"menu con {len(r)} bebidas",
            )
            pasos_ok &= ok
        if pasos_ok:
            ok, pedido_id = medir(
                registro, fase, nivel, "Confirmar pedido",
                lambda: menu.insertar_pedido(cliente, PRODUCTO, 65.0, usuario, "Efectivo"),
                lambda r: "" if r and int(r) > 0 else "sin id de pedido",
            )
            pasos_ok &= ok
        if pasos_ok:
            ok, _ = medir(
                registro, fase, nivel, "Ver estado del pedido",
                lambda: menu.obtener_pedido_activo(cliente),
                lambda r: "" if r and r["IdGenerarPedido"] == pedido_id else "no aparece el pedido",
            )
            pasos_ok &= ok

        ms = (time.perf_counter() - inicio) * 1000
        registro.agregar(
            Medicion(fase, nivel, "Flujo de pedido", ms, pasos_ok, "" if pasos_ok else "fallo un paso")
        )
        if not pasos_ok:
            return
        if rondas > 1:
            # Se cancela para que el mismo cliente pueda volver a pedir en la
            # siguiente ronda (un solo pedido activo por cliente).
            medir(
                registro, fase, nivel, "Cancelar pedido",
                lambda: menu.cancelar_pedido(cliente, pedido_id),
                lambda r: "" if r else "no se cancelo",
            )


def ejecutar_nivel(
    fase: str, nivel: int, clientes: list, rondas: int, con_login: bool, bebidas: int,
    registro: Registro, monitor: Monitor,
) -> dict:
    ultimo_id = int(bp.uno("SELECT COALESCE(MAX(IdGenerarPedido), 0) AS m FROM generarpedido")["m"])
    reinicio = monitor.reiniciar_maximo_conexiones()
    barrera = threading.Barrier(len(clientes) + 1)
    hilos = [
        threading.Thread(
            target=cliente_simulado,
            args=(c, fase, nivel, rondas, con_login, bebidas, registro, barrera),
            daemon=True,
        )
        for c in clientes
    ]
    for hilo in hilos:
        hilo.start()
    barrera.wait(timeout=60)
    inicio = time.perf_counter()
    limite = inicio + TIEMPO_MAXIMO_HILOS
    for hilo in hilos:
        hilo.join(timeout=max(0.1, limite - time.perf_counter()))
    segundos = time.perf_counter() - inicio
    colgados = sum(1 for h in hilos if h.is_alive())

    marcadores = ", ".join(["%s"] * len(clientes))
    nuevos = bp.uno(
        f"SELECT COUNT(*) AS total, COUNT(DISTINCT Clientes_Idcliente) AS clientes "
        f"FROM generarpedido WHERE IdGenerarPedido > %s AND Clientes_Idcliente IN ({marcadores})",
        (ultimo_id, *clientes),
    )
    excedidos = bp.uno(
        "SELECT COUNT(*) AS n FROM (SELECT Clientes_Idcliente FROM generarpedido "
        f"WHERE IdGenerarPedido > %s AND Clientes_Idcliente IN ({marcadores}) "
        "GROUP BY Clientes_Idcliente HAVING COUNT(*) > %s) AS t",
        (ultimo_id, *clientes, rondas),
    )
    confirmados = sum(1 for m in registro.de(fase, nivel, "Confirmar pedido") if m.ok)
    return {
        "segundos": segundos,
        "colgados": colgados,
        "conexiones_max": monitor.maximo_conexiones_usadas() if reinicio else None,
        "pedidos_bd": int(nuevos["total"]),
        "clientes_bd": int(nuevos["clientes"]),
        "excedidos": int(excedidos["n"]),
        "confirmados": confirmados,
        "esperados": len(clientes) * rondas,
    }


# ------------------------------------------------------------
# Fase 3: carrera
# ------------------------------------------------------------
def fase_carrera(plan: Plan, registro: Registro, clientes: Clientes) -> dict:
    cliente = clientes.tomar(1)[0]
    barrera = threading.Barrier(plan.carrera)
    resultados = Counter()
    candado = threading.Lock()

    def confirmar():
        barrera.wait(timeout=60)
        inicio = time.perf_counter()
        try:
            menu.insertar_pedido(cliente, PRODUCTO, 65.0, usuario_de(cliente), "Efectivo")
            clave = "aceptado"
        except menu.PedidoNoPermitido as rechazo:
            clave = f"rechazado ({rechazo.motivo})"
        except Exception as error:  # noqa: BLE001
            clave = describir_error(error)
        ms = (time.perf_counter() - inicio) * 1000
        with candado:
            resultados[clave] += 1
        esperado = clave == "aceptado" or clave.startswith("rechazado")
        registro.agregar(Medicion("carrera", plan.carrera, "Confirmar pedido", ms, esperado, clave))

    hilos = [threading.Thread(target=confirmar, daemon=True) for _ in range(plan.carrera)]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join(timeout=TIEMPO_MAXIMO_HILOS)
    en_curso = bp.contar(
        "generarpedido", "Clientes_Idcliente = %s AND EstatusPedido_IdEstatusPedido IN (1, 2, 3)", (cliente,)
    )
    return {"dispositivos": plan.carrera, "resultados": dict(resultados), "en_curso": en_curso}


# ------------------------------------------------------------
# Fase 5: conexiones
# ------------------------------------------------------------
def fase_conexiones(monitor: Monitor) -> dict:
    """Simula celulares con la app instalada: cada copia abre su propio pool.

    mysql-connector abre las DB_POOL_SIZE conexiones del pool en cuanto
    se crea, y quedan abiertas mientras la app siga abierta.
    """
    maximo = int(monitor.valor("SHOW VARIABLES LIKE 'max_connections'") or 0)
    abiertas_antes = monitor.conexiones_abiertas()
    pools = []
    error = ""
    limite = maximo // max(1, variables.DB_POOL_SIZE) + 10
    try:
        for numero in range(1, limite + 1):
            try:
                pools.append(
                    pooling.MySQLConnectionPool(
                        pool_name=f"celular_{numero}",
                        pool_size=variables.DB_POOL_SIZE,
                        pool_reset_session=True,
                        **base_datos._parametros_conexion(),
                    )
                )
            except Exception as falla:  # noqa: BLE001
                error = describir_error(falla)
                break
        abiertas_maximo = monitor.conexiones_abiertas()
    finally:
        for pool in pools:
            try:
                pool._remove_connections()
            except Exception:
                pass
    return {
        "max_connections": maximo,
        "abiertas_antes": abiertas_antes,
        "abiertas_maximo": abiertas_maximo,
        "celulares": len(pools),
        "pool": variables.DB_POOL_SIZE,
        "error": error,
    }


# ------------------------------------------------------------
# Reporte
# ------------------------------------------------------------
def ms(valor: float) -> str:
    if valor != valor:  # NaN
        return "—"
    return f"{valor:,.0f}" if valor >= 100 else f"{valor:,.1f}"


def armar_reporte(plan: Plan, contexto: dict, registro: Registro, volumen_filas: list, carga: dict,
                  carrera: dict, estres: dict, conexiones: dict, latencia_red: float) -> tuple[str, list]:
    lineas = []
    metas = []
    v = plan.volumen

    lineas.append("# Resultados de rendimiento — Corallie Bubble")
    lineas.append("")
    lineas.append(f"- Fecha: {contexto['fecha']}")
    lineas.append(f"- Modo: {plan.nombre}")
    lineas.append(f"- Equipo: {contexto['equipo']}")
    lineas.append(f"- Servidor: MySQL {contexto['mysql']} (local, UTC y modo estricto como Railway)")
    lineas.append(f"- Pool de la app: {variables.DB_POOL_SIZE} conexiones; contraseñas con PBKDF2 de {variables.SEG_ITERACIONES:,} iteraciones")
    lineas.append(
        f"- Base de volumen: {v.clientes:,} clientes, {v.pedidos_totales:,} pedidos, {v.cortes} cortes con "
        f"{v.ventas_totales:,} ventas, {v.bebidas} bebidas ({v.bebidas_con_foto} con foto). "
        f"Se cargó en {contexto['segundos_carga']:.1f} s."
    )
    lineas.append("")

    # ---- 1. Volumen
    lineas.append("## 1. Volumen: tiempo de cada consulta con la base grande")
    lineas.append("")
    lineas.append(f"{plan.repeticiones} repeticiones por operación. \"Viajes\" son las instrucciones que la app manda al servidor; "
                  f"la última columna suma {latencia_red:.0f} ms de internet por viaje a la mediana local (estimación, ver notas).")
    lineas.append("")
    lineas.append(f"| Operación | Viajes | p50 (ms) | p95 (ms) | Máx (ms) | Errores | Estimado con {latencia_red:.0f} ms de red (ms) |")
    lineas.append("|---|---:|---:|---:|---:|---:|---:|")
    marcado = registro.de("volumen", 0)
    marcado = [m for m in marcado if m.operacion.startswith("Marcar")]
    for m in marcado:
        lineas.append(f"| {m.operacion} (una vez) | — | {ms(m.ms)} | — | — | {0 if m.ok else 1} | — |")
    peor_consulta = 0.0
    for nombre, viajes in volumen_filas:
        e = estadisticas(registro.de("volumen", 0, nombre))
        estimado = e["p50"] + viajes * latencia_red
        lineas.append(
            f"| {nombre} | {viajes} | {ms(e['p50'])} | {ms(e['p95'])} | {ms(e['max'])} | {e['errores']} | {ms(estimado)} |"
        )
        if not nombre.startswith("Inicio de sesión") and e["p95"] == e["p95"]:
            peor_consulta = max(peor_consulta, e["p95"])
    errores_volumen = sum(1 for m in registro.de("volumen") if not m.ok)
    metas.append((
        f"Consultas con la base grande: p95 < {META_CONSULTA_MS} ms (sin contar el inicio de sesión)",
        f"peor p95 = {ms(peor_consulta)} ms, errores = {errores_volumen}",
        peor_consulta < META_CONSULTA_MS and errores_volumen == 0,
    ))
    lineas.append("")

    # ---- 2. Carga
    lineas.append("## 2. Carga: clientes haciendo su pedido al mismo tiempo")
    lineas.append("")
    lineas.append(
        f"Cada cliente inicia sesión y repite {plan.rondas} veces el flujo: revisar si puede pedir, ver el menú, "
        "confirmar el pedido y ver su estado (entre rondas cancela el pedido para poder pedir otra vez). "
        "Todos arrancan en el mismo instante y comparten un solo proceso, como en la versión web."
    )
    lineas.append("")
    lineas.append("| Clientes a la vez | Flujos | Errores | Flujo p50 (ms) | Flujo p95 (ms) | Flujo máx (ms) | Login p50 (ms) | Login p95 (ms) | Pedidos por segundo | Conexiones máx. en MySQL |")
    lineas.append("|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    errores_hasta_meta = 0
    flujo_meta = None
    for nivel, info in carga.items():
        flujo = estadisticas(registro.de("carga", nivel, "Flujo de pedido"))
        login = estadisticas(registro.de("carga", nivel, "Inicio de sesión"))
        errores = sum(1 for m in registro.de("carga", nivel) if not m.ok) + info["colgados"]
        por_segundo = info["confirmados"] / info["segundos"] if info["segundos"] else 0
        lineas.append(
            f"| {nivel} | {flujo['n']} | {errores} | {ms(flujo['p50'])} | {ms(flujo['p95'])} | {ms(flujo['max'])} | "
            f"{ms(login['p50'])} | {ms(login['p95'])} | {por_segundo:.1f} | {info['conexiones_max'] if info['conexiones_max'] is not None else 'n/d'} |"
        )
        if nivel <= META_SIN_ERRORES_HASTA:
            errores_hasta_meta += errores
        if nivel == META_FLUJO_CLIENTES:
            flujo_meta = flujo
    lineas.append("")
    lineas.append("Tiempo de cada paso (p95, ms):")
    lineas.append("")
    pasos = ["Inicio de sesión", "Revisar si puede pedir", "Ver menú", "Confirmar pedido", "Ver estado del pedido", "Cancelar pedido"]
    lineas.append("| Paso | " + " | ".join(f"{n} clientes" for n in carga) + " |")
    lineas.append("|---|" + "---:|" * len(carga))
    for paso in pasos:
        valores = [ms(estadisticas(registro.de("carga", n, paso))["p95"]) for n in carga]
        lineas.append(f"| {paso} | " + " | ".join(valores) + " |")
    lineas.append("")
    lineas.append("Integridad de los datos después de cada nivel:")
    lineas.append("")
    lineas.append("| Clientes a la vez | Pedidos esperados | Confirmados por la app | Registrados en la base | Clientes con pedidos de más |")
    lineas.append("|---:|---:|---:|---:|---:|")
    integridad_ok = True
    for nivel, info in carga.items():
        lineas.append(f"| {nivel} | {info['esperados']} | {info['confirmados']} | {info['pedidos_bd']} | {info['excedidos']} |")
        integridad_ok &= info["pedidos_bd"] == info["confirmados"] and info["excedidos"] == 0
    lineas.append("")
    if flujo_meta is not None:
        metas.append((
            f"Flujo de pedido con {META_FLUJO_CLIENTES} clientes a la vez: p95 < {META_FLUJO_MS / 1000:.0f} s",
            f"p95 = {ms(flujo_meta['p95'])} ms",
            flujo_meta["p95"] < META_FLUJO_MS and flujo_meta["errores"] == 0,
        ))
    else:
        metas.append((
            f"Flujo de pedido con {META_FLUJO_CLIENTES} clientes a la vez: p95 < {META_FLUJO_MS / 1000:.0f} s",
            "no se midió en este modo", None,
        ))
    metas.append((
        f"Sin errores con hasta {META_SIN_ERRORES_HASTA} clientes a la vez",
        f"errores = {errores_hasta_meta}",
        errores_hasta_meta == 0,
    ))
    metas.append((
        "Ningún pedido se pierde ni se duplica bajo carga",
        "la base coincide con lo confirmado" if integridad_ok else "hay diferencias (ver tabla)",
        integridad_ok,
    ))

    # ---- 3. Carrera
    lineas.append("## 3. Carrera: el mismo cliente confirma desde varios dispositivos a la vez")
    lineas.append("")
    detalle = ", ".join(f"{clave}: {n}" for clave, n in sorted(carrera["resultados"].items()))
    carrera_ok = carrera["resultados"].get("aceptado", 0) == 1 and carrera["en_curso"] == 1
    lineas.append(f"- Dispositivos: {carrera['dispositivos']}")
    lineas.append(f"- Respuestas: {detalle}")
    lineas.append(f"- Pedidos en curso del cliente al terminar: {carrera['en_curso']} (debe ser 1)")
    lineas.append("")
    metas.append((
        f"Un solo pedido aunque se confirme desde {carrera['dispositivos']} dispositivos a la vez",
        f"pedidos en curso = {carrera['en_curso']}",
        carrera_ok,
    ))

    # ---- 4. Estres
    lineas.append("## 4. Estrés: más clientes de los que el local espera")
    lineas.append("")
    lineas.append("Cada cliente hace el flujo una vez, sin iniciar sesión, todos en el mismo instante.")
    lineas.append("")
    lineas.append("| Clientes a la vez | Flujos completos | Errores | Flujo p50 (ms) | Flujo p95 (ms) | Conexiones máx. en MySQL | Errores encontrados |")
    lineas.append("|---:|---:|---:|---:|---:|---:|---|")
    for nivel, info in estres.items():
        flujo = estadisticas(registro.de("estres", nivel, "Flujo de pedido"))
        fallas = Counter(m.detalle for m in registro.de("estres", nivel) if not m.ok and m.operacion != "Flujo de pedido")
        tipos = "; ".join(f"{texto} ({n})" for texto, n in fallas.most_common(3)) or "ninguno"
        lineas.append(
            f"| {nivel} | {flujo['ok']} de {flujo['n']} | {flujo['errores'] + info['colgados']} | {ms(flujo['p50'])} | {ms(flujo['p95'])} | "
            f"{info['conexiones_max'] if info['conexiones_max'] is not None else 'n/d'} | {tipos} |"
        )
    lineas.append("")

    # ---- 5. Conexiones
    lineas.append("## 5. Capacidad de conexiones: la app instalada en cada celular")
    lineas.append("")
    lineas.append(
        f"Cada copia de la app abre su propio pool de {conexiones['pool']} conexiones al conectarse y las mantiene abiertas. "
        f"El servidor acepta hasta {conexiones['max_connections']} conexiones (max_connections)."
    )
    lineas.append("")
    lineas.append(f"- Conexiones ya abiertas antes de la prueba: {conexiones['abiertas_antes']}")
    lineas.append(f"- Copias de la app conectadas a la vez antes del primer rechazo: **{conexiones['celulares']}**")
    lineas.append(f"- Conexiones abiertas en ese momento: {conexiones['abiertas_maximo']}")
    lineas.append(f"- Respuesta del servidor a la siguiente copia: {conexiones['error'] or 'no hubo rechazo dentro del límite probado'}")
    lineas.append("")

    # ---- Metas
    resumen = ["## Metas", "", "| Meta | Resultado | ¿Se cumple? |", "|---|---|---|"]
    for meta, resultado, cumple in metas:
        texto = "Sí" if cumple else ("No medido" if cumple is None else "No")
        resumen.append(f"| {meta} | {resultado} | {texto} |")
    resumen.append("")

    notas = [
        "## Notas para interpretar los números",
        "",
        "- Los tiempos se midieron contra un MySQL en el mismo equipo, sin internet de por medio. "
        "Con Railway cada viaje a la base suma la latencia de la red; la columna \"Estimado\" de la tabla 1 lo aproxima "
        f"con {latencia_red:.0f} ms por viaje (se puede cambiar con --latencia-red-ms).",
        "- p50 es la mediana; p95 es el tiempo dentro del cual terminó el 95 % de las veces.",
        "- En las fases de carga y estrés todos los clientes comparten un proceso y un pool, como en la versión web de Flet. "
        "La fase 5 mide el caso de la app instalada en cada celular, donde cada copia tiene su propio pool.",
        "- El inicio de sesión es lento a propósito: PBKDF2 hace costoso adivinar contraseñas. Ocupa el procesador, así que "
        f"varios inicios de sesión a la vez se forman en fila según los núcleos del equipo ({os.cpu_count()} aquí).",
    ]
    return "\n".join(lineas[:9] + resumen + lineas[9:] + notas) + "\n", metas


def guardar(reporte: str, registro: Registro, modo: str) -> tuple[Path, Path]:
    CARPETA_RESULTADOS.mkdir(parents=True, exist_ok=True)
    # El modo y los segundos van en el nombre para que una corrida no
    # reemplace a otra hecha en el mismo minuto.
    sello = datetime.now().strftime("%Y%m%d_%H%M%S")
    ruta_md = CARPETA_RESULTADOS / f"rendimiento_{modo}_{sello}.md"
    ruta_csv = CARPETA_RESULTADOS / f"rendimiento_{modo}_{sello}.csv"
    ruta_md.write_text(reporte, encoding="utf-8")
    with ruta_csv.open("w", newline="", encoding="utf-8-sig") as archivo:
        escritor = csv.writer(archivo)
        escritor.writerow(["fase", "nivel", "operacion", "ms", "ok", "detalle"])
        for m in registro.mediciones:
            escritor.writerow([m.fase, m.nivel, m.operacion, f"{m.ms:.2f}", "si" if m.ok else "no", m.detalle])
    resumen_github = os.environ.get("GITHUB_STEP_SUMMARY")
    if resumen_github:
        with open(resumen_github, "a", encoding="utf-8") as archivo:
            archivo.write(reporte + "\n")
    return ruta_md, ruta_csv


# ------------------------------------------------------------
# Programa principal
# ------------------------------------------------------------
def main(argv: list | None = None) -> int:
    parser = argparse.ArgumentParser(description="Pruebas de rendimiento de Corallie Bubble (base local de pruebas).")
    parser.add_argument("--rapido", action="store_true", help="version corta (base mas chica y menos clientes)")
    parser.add_argument("--latencia-red-ms", type=float, default=50.0,
                        help="ms de internet por viaje a la base para la columna de estimacion (por omision 50)")
    args = parser.parse_args(argv)
    plan = RAPIDO if args.rapido else COMPLETO

    print(f"Base de pruebas: {bp.CONFIG['user']}@{bp.CONFIG['host']}:{bp.CONFIG['port']}/{bp.CONFIG['database']}")
    print(f"Modo: {plan.nombre}\n")
    bp.preparar_base()
    bp.limpiar_datos()

    registro = Registro()
    monitor = Monitor()
    try:
        contexto = {
            "fecha": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "equipo": f"{platform.system()} {platform.release()}, {os.cpu_count()} núcleos, Python {platform.python_version()}",
            "mysql": monitor.valor("SELECT VERSION()"),
        }

        print("1/5 Cargando la base de volumen...")
        contexto["segundos_carga"] = datos_volumen.cargar(plan.volumen)
        clientes = Clientes(plan.volumen)
        hash_real = seguridad.hashear(CONTRASENA)

        print("    Midiendo consultas...")
        volumen_filas = fase_volumen(plan, registro, monitor, clientes, hash_real)

        print("2/5 Carga con clientes simultaneos...")
        carga = {}
        for nivel in plan.niveles_carga:
            bloque = clientes.tomar(nivel)
            dar_contrasena_real(bloque, hash_real)
            carga[nivel] = ejecutar_nivel("carga", nivel, bloque, plan.rondas, True, plan.volumen.bebidas, registro, monitor)
            print(f"    {nivel} clientes: {carga[nivel]['segundos']:.1f} s")

        print("3/5 Carrera del mismo cliente...")
        carrera = fase_carrera(plan, registro, clientes)

        print("4/5 Estres...")
        estres = {}
        for nivel in plan.niveles_estres:
            bloque = clientes.tomar(nivel)
            estres[nivel] = ejecutar_nivel("estres", nivel, bloque, 1, False, plan.volumen.bebidas, registro, monitor)
            print(f"    {nivel} clientes: {estres[nivel]['segundos']:.1f} s")

        print("5/5 Capacidad de conexiones...")
        bp.reiniciar_pool()
        conexiones = fase_conexiones(monitor)
    finally:
        monitor.cerrar()

    reporte, metas = armar_reporte(plan, contexto, registro, volumen_filas, carga, carrera, estres, conexiones, args.latencia_red_ms)
    ruta_md, ruta_csv = guardar(reporte, registro, plan.nombre)
    print("\n" + reporte)
    print(f"Reporte: {ruta_md}")
    print(f"Mediciones: {ruta_csv}")
    incumplidas = [meta for meta, _r, cumple in metas if cumple is False]
    if incumplidas:
        print("\nMetas no cumplidas:")
        for meta in incumplidas:
            print(f"  - {meta}")
    return 0


if __name__ == "__main__":
    sys.exit(main())