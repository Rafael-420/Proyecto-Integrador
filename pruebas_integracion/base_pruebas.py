"""
pruebas_integracion/base_pruebas.py
-----------------------------------
Base comun de las pruebas de integracion, sistema, seguridad y red.

A diferencia de las pruebas unitarias (carpeta pruebas/), estas SI se
conectan a un MySQL de verdad, para comprobar lo que un objeto
simulado no puede: que el SQL funcione contra el esquema real, que las
migraciones se apliquen, que las transacciones guarden lo que deben y
que las horas cuadren cuando el servidor esta en UTC, como Railway.

Seguridad de los datos reales
-----------------------------
Las pruebas BORRAN y vuelven a crear la base en cada ejecucion, por eso:

  * Nunca usan las credenciales DB_* del archivo .env (las de Railway).
    Leen solo las variables PRUEBAS_DB_*.
  * Se niegan a correr si el nombre de la base no contiene "prueba" o
    si el servidor parece ser Railway.

Configuracion (en el .env o como variables de entorno; todas opcionales)
-----------------------------------------------------------------------
    PRUEBAS_DB_HOST=localhost
    PRUEBAS_DB_PORT=3306
    PRUEBAS_DB_USER=root
    PRUEBAS_DB_PASSWORD=root
    PRUEBAS_DB_NAME=ing_software_pruebas

El usuario necesita permiso para crear y borrar esa base y para usar
SET GLOBAL (root lo tiene). Durante la ejecucion el servidor de pruebas
se pone en UTC y en modo estricto, igual que Railway, y al terminar se
regresa a como estaba. Funciona con MySQL 8 o 9 y con el MariaDB de XAMPP.

Ejecutar desde la raiz del proyecto:

    python -m unittest discover -s pruebas_integracion -t . -v
"""

from __future__ import annotations

import atexit
import contextlib
import io
import os
import socket
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

CARPETA = Path(__file__).resolve().parent
ESQUEMA_BASE = CARPETA / "esquema_base.sql"

# Migraciones del repositorio, en el orden en que se aplicaron en Railway.
MIGRACIONES = (
    RAIZ / "recursos" / "sql" / "migracion_seguridad.sql",
    RAIZ / "recursos" / "migracion_horario.sql",
    RAIZ / "recursos" / "sql" / "migracion_senal_caja.sql",
    RAIZ / "recursos" / "sql" / "migracion_imagenes_bebidas.sql",
    RAIZ / "recursos" / "sql" / "mene.sql",
    RAIZ / "recursos" / "sql" / "migracion_textos_pedido.sql",
    RAIZ / "recursos" / "sql" / "migracion_utf8mb4.sql",
)

# Tablas con datos de prueba que se vacian antes de cada caso.
TABLAS_DE_DATOS = (
    "bebidas_imagenes",
    "consentimiento_privacidad",
    "detalleventas",
    "generarrecibo",
    "ventas",
    "ingresos_egresos",
    "entradarecibe",
    "entradasproductos",
    "salidasproductos",
    "tipossalidas",
    "generarpedido_detalle",
    "generarpedido",
    "recibospedidos",
    "recibos",
    "productosstock",
    "productos",
    "bebidas",
    "cortecaja",
    "solicitudes_password",
    "intentos_login",
    "cliente",
    "empleado",
    "usuario",
    "dias_cerrados",
)

# Iteraciones PBKDF2 para los usuarios de apoyo que crean las pruebas.
# Son pocas a proposito para que la suite sea rapida; las pruebas de
# seguridad usan el valor real del sistema.
ITERACIONES_DE_APOYO = 1000


# ------------------------------------------------------------
# 1. Configuracion de la base de pruebas
#    Debe ocurrir ANTES de importar configuracion.variables, que lee
#    DB_* una sola vez al importarse.
# ------------------------------------------------------------
def _leer_config_pruebas() -> dict:
    valores = {}
    try:
        from dotenv import dotenv_values

        # dotenv_values lee el .env SIN cargarlo en el entorno: asi las
        # credenciales DB_* de Railway nunca llegan a estas pruebas.
        valores = {k: v for k, v in dotenv_values(RAIZ / ".env").items() if k.startswith("PRUEBAS_")}
    except Exception:
        valores = {}

    def leer_contrasena() -> str:
        # Una contrasena vacia es valida (Laragon y XAMPP traen root sin
        # contrasena): si la variable existe, se respeta aunque este vacia.
        if "PRUEBAS_DB_PASSWORD" in os.environ:
            return os.environ["PRUEBAS_DB_PASSWORD"]
        if "PRUEBAS_DB_PASSWORD" in valores:
            return valores["PRUEBAS_DB_PASSWORD"] or ""
        return "root"

    def leer(nombre: str, respaldo: str) -> str:
        valor = os.getenv(nombre) or valores.get(nombre) or ""
        return valor.strip() or respaldo

    return {
        "host": leer("PRUEBAS_DB_HOST", "localhost"),
        "port": int(leer("PRUEBAS_DB_PORT", "3306")),
        "user": leer("PRUEBAS_DB_USER", "root"),
        "password": leer_contrasena(),
        "database": leer("PRUEBAS_DB_NAME", "ing_software_pruebas"),
        "ssl_disabled": leer("PRUEBAS_DB_SSL_DISABLED", "0").lower() in ("1", "true", "si", "sí", "yes"),
    }


CONFIG = _leer_config_pruebas()


class DestinoNoPermitido(RuntimeError):
    """La configuracion apunta a una base que no es de pruebas."""


def _verificar_destino(config: dict) -> None:
    nombre = config["database"].lower()
    host = config["host"].lower()
    if "prueba" not in nombre:
        raise DestinoNoPermitido(
            f"La base '{config['database']}' no parece de pruebas. "
            "Su nombre debe contener 'prueba' (por ejemplo ing_software_pruebas), "
            "porque la suite la borra y la vuelve a crear."
        )
    if "railway" in host or "rlwy" in host:
        raise DestinoNoPermitido(
            f"El servidor '{config['host']}' parece ser Railway. "
            "Usa un MySQL local para estas pruebas."
        )


_verificar_destino(CONFIG)

if "configuracion.variables" in sys.modules:
    _ya_cargada = sys.modules["configuracion.variables"]
    if getattr(_ya_cargada, "DB_NAME", None) != CONFIG["database"]:
        raise DestinoNoPermitido(
            "configuracion.variables ya se habia importado con otra base de datos. "
            "Ejecuta la suite de integracion por separado de las pruebas unitarias."
        )

os.environ["DB_HOST"] = CONFIG["host"]
os.environ["DB_PORT"] = str(CONFIG["port"])
os.environ["DB_USER"] = CONFIG["user"]
os.environ["DB_PASSWORD"] = CONFIG["password"]
os.environ["DB_NAME"] = CONFIG["database"]
os.environ["DB_SSL_DISABLED"] = "1" if CONFIG["ssl_disabled"] else "0"
os.environ.setdefault("DB_TIMEOUT_VERIFICACION", "3")

# El proceso corre con la hora del local (Puerto Vallarta, UTC-6) y el
# servidor en UTC, igual que la app real contra Railway. En Windows
# time.tzset no existe y se usa la zona del equipo, que ya es la local.
os.environ.setdefault("TZ", "America/Mexico_City")
if hasattr(time, "tzset"):
    time.tzset()

import mysql.connector  # noqa: E402

from configuracion import base_datos  # noqa: E402
from configuracion import variables  # noqa: E402

assert variables.DB_NAME == CONFIG["database"], "La configuracion de pruebas no se aplico."

# configuracion.variables convierte una contrasena vacia en "root". Si el
# MySQL local no tiene contrasena (Laragon, XAMPP), se corrige aqui para
# que la app de las pruebas se conecte con la misma que la suite.
variables.DB_PASSWORD = CONFIG["password"]
base_datos.DB_PASSWORD = CONFIG["password"]


# ------------------------------------------------------------
# 2. Creacion de la base
# ------------------------------------------------------------
_PREPARADA = False
RESULTADO_MIGRACIONES: list[dict] = []
ZONA_ORIGINAL: str | None = None


def _conectar_servidor(con_base: bool = False):
    parametros = {
        "host": CONFIG["host"],
        "port": CONFIG["port"],
        "user": CONFIG["user"],
        "password": CONFIG["password"],
        "charset": "utf8mb4",
        "connection_timeout": 10,
        "autocommit": True,
    }
    if CONFIG["ssl_disabled"]:
        parametros["ssl_disabled"] = True
    if con_base:
        parametros["database"] = CONFIG["database"]
    return mysql.connector.connect(**parametros)


def separar_sql(texto: str) -> list[str]:
    """Divide un archivo SQL en instrucciones, sin comentarios de linea."""
    lineas = [l for l in texto.splitlines() if l.strip() and not l.strip().startswith("--")]
    return [b.strip() for b in "\n".join(lineas).split(";") if b.strip()]


# Modo SQL que usa Railway (el valor por defecto de MySQL 8 y 9). XAMPP
# trae MariaDB sin modo estricto: ahi un texto demasiado largo se
# recorta en silencio en lugar de dar error, y los defectos de largo de
# columna no se verian.
MODO_RAILWAY = (
    "ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,"
    "ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION"
)
MODO_ORIGINAL: str | None = None


def _texto(valor) -> str:
    if isinstance(valor, (bytes, bytearray)):
        return bytes(valor).decode("utf-8", "replace")
    return str(valor)


def _restaurar_servidor() -> None:
    """Regresa la zona horaria y el modo SQL que tenia el servidor."""
    try:
        conn = _conectar_servidor()
        cur = conn.cursor()
        if ZONA_ORIGINAL is not None:
            cur.execute("SET GLOBAL time_zone = %s", (ZONA_ORIGINAL,))
        if MODO_ORIGINAL is not None:
            cur.execute("SET GLOBAL sql_mode = %s", (MODO_ORIGINAL,))
        cur.close()
        conn.close()
    except Exception:
        pass


def _imitar_railway(cur) -> None:
    """Pone el servidor de pruebas en UTC y en modo estricto, como Railway."""
    global ZONA_ORIGINAL, MODO_ORIGINAL
    cur.execute("SELECT @@GLOBAL.time_zone, @@GLOBAL.sql_mode")
    fila = cur.fetchone()
    ZONA_ORIGINAL, MODO_ORIGINAL = _texto(fila[0]), _texto(fila[1])
    atexit.register(_restaurar_servidor)
    try:
        cur.execute("SET GLOBAL time_zone = '+00:00'")
        cur.execute("SET GLOBAL sql_mode = %s", (MODO_RAILWAY,))
    except Exception as error:
        raise RuntimeError(
            "No se pudo poner el MySQL de pruebas en UTC y modo estricto, como Railway. "
            f"El usuario '{CONFIG['user']}' necesita permiso para SET GLOBAL "
            f"(root lo tiene).\nDetalle: {error}"
        ) from None


def verificar_servidor() -> dict:
    """Comprueba, con una conexion nueva, que el servidor imita a Railway."""
    conn = _conectar_servidor()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT TIMESTAMPDIFF(MINUTE, UTC_TIMESTAMP(), NOW()), @@SESSION.time_zone, "
            "@@SESSION.sql_mode, VERSION()"
        )
        diferencia, zona, modo, version = cur.fetchone()
        cur.close()
    finally:
        conn.close()
    return {
        "diferencia_minutos": int(diferencia),
        "zona": _texto(zona),
        "modo": _texto(modo),
        "version": _texto(version),
    }


def aplicar_migracion(ruta: Path) -> dict:
    """Aplica una migracion con la herramienta del proyecto y guarda su salida."""
    from herramientas import aplicar_migracion as herramienta

    salida = io.StringIO()
    with contextlib.redirect_stdout(salida):
        codigo = herramienta.main([str(ruta)])
    return {"archivo": ruta.name, "codigo": codigo, "salida": salida.getvalue()}


def preparar_base() -> None:
    """Borra y crea la base de pruebas con el esquema y las migraciones.

    Se ejecuta una sola vez por proceso, aunque la llamen todas las clases.
    """
    global _PREPARADA
    if _PREPARADA:
        return

    try:
        conn = _conectar_servidor()
    except Exception as error:
        raise RuntimeError(
            "No se pudo conectar al MySQL de pruebas "
            f"({CONFIG['user']}@{CONFIG['host']}:{CONFIG['port']}).\n"
            "Revisa que MySQL este encendido y define PRUEBAS_DB_USER y "
            f"PRUEBAS_DB_PASSWORD en el .env.\nDetalle: {error}"
        ) from None

    cur = conn.cursor()

    # Servidor en UTC y en modo estricto, como Railway. Al terminar se
    # regresa a como estaba.
    _imitar_railway(cur)
    servidor = verificar_servidor()
    if abs(servidor["diferencia_minutos"]) > 1 or "STRICT_TRANS_TABLES" not in servidor["modo"]:
        raise RuntimeError(
            "El MySQL de pruebas no quedo como Railway (UTC y modo estricto): "
            f"diferencia con UTC = {servidor['diferencia_minutos']} min, "
            f"zona = {servidor['zona']}, modo = {servidor['modo']}, version = {servidor['version']}."
        )

    nombre = CONFIG["database"]
    cur.execute(f"DROP DATABASE IF EXISTS `{nombre}`")
    cur.execute(f"CREATE DATABASE `{nombre}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
    cur.execute(f"USE `{nombre}`")
    for instruccion in separar_sql(ESQUEMA_BASE.read_text(encoding="utf-8")):
        cur.execute(instruccion)
    cur.close()
    conn.close()

    # Conexiones nuevas: el pool debe nacer despues del cambio de zona.
    reiniciar_pool()

    RESULTADO_MIGRACIONES.clear()
    for ruta in MIGRACIONES:
        resultado = aplicar_migracion(ruta)
        RESULTADO_MIGRACIONES.append(resultado)
        if resultado["codigo"] != 0:
            raise RuntimeError(
                f"La migracion {resultado['archivo']} no se pudo aplicar a la base de pruebas.\n"
                + resultado["salida"][-1500:]
            )

    _PREPARADA = True


def reiniciar_pool() -> None:
    """Descarta el pool de conexiones para que el siguiente uso lo cree de nuevo."""
    base_datos._pool = None


# ------------------------------------------------------------
# 3. Acceso directo a la base (independiente del codigo probado)
# ------------------------------------------------------------
def consultar(sql: str, parametros: tuple = ()) -> list[dict]:
    conn = _conectar_servidor(con_base=True)
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(sql, parametros)
        filas = cur.fetchall()
        cur.close()
        return filas
    finally:
        conn.close()


def uno(sql: str, parametros: tuple = ()) -> dict | None:
    filas = consultar(sql, parametros)
    return filas[0] if filas else None


def ejecutar(sql: str, parametros: tuple = ()) -> int:
    """Ejecuta un INSERT/UPDATE/DELETE y devuelve lastrowid (o filas afectadas)."""
    conn = _conectar_servidor(con_base=True)
    try:
        cur = conn.cursor()
        cur.execute(sql, parametros)
        resultado = cur.lastrowid or cur.rowcount
        cur.close()
        return int(resultado or 0)
    finally:
        conn.close()


def limpiar_datos() -> None:
    """Vacia las tablas de datos y deja el local abierto todo el dia."""
    conn = _conectar_servidor(con_base=True)
    try:
        cur = conn.cursor()
        cur.execute("SET FOREIGN_KEY_CHECKS = 0")
        for tabla in TABLAS_DE_DATOS:
            cur.execute(f"DELETE FROM `{tabla}`")
        cur.execute("SET FOREIGN_KEY_CHECKS = 1")
        cur.close()
    finally:
        conn.close()

    try:
        from servicios import servicio_imagenes_bebidas

        servicio_imagenes_bebidas.limpiar_cache()
    except Exception:
        pass

    abrir_local_todo_el_dia()
    conectar_caja()


def abrir_local_todo_el_dia() -> None:
    """Horario de 00:00 a 23:59:59 los siete dias, servicio encendido, sin margen."""
    for dia in range(7):
        ejecutar(
            "REPLACE INTO horario_local (DiaSemana, Abierto, HoraApertura, HoraCierre) "
            "VALUES (%s, 1, '00:00:00', '23:59:59')",
            (dia,),
        )
    ejecutar(
        "UPDATE estado_servicio SET MenuActivo = 1, MensajeMenu = NULL, MinutosAntesCierre = 0, "
        "InicioDesconexionCaja = NULL, FinDesconexionCaja = NULL WHERE IdEstadoServicio = 1"
    )


def ahora_local() -> datetime:
    """Hora del local segun el reloj del servidor (la que usa la app)."""
    from servicios.servicio_horario import a_hora_local

    fila = uno("SELECT UTC_TIMESTAMP() AS ahora")
    return a_hora_local(fila["ahora"])


def conectar_caja(hace_minutos: float = 0) -> None:
    """Simula que la caja mando su señal hace `hace_minutos` minutos."""
    momento = ahora_local() - timedelta(minutes=hace_minutos)
    ejecutar(
        "UPDATE estado_servicio SET UltimaSenalCaja = %s WHERE IdEstadoServicio = 1",
        (momento.replace(microsecond=0),),
    )


# ------------------------------------------------------------
# 4. Datos de apoyo
# ------------------------------------------------------------
_contador = 0


def _siguiente() -> int:
    global _contador
    _contador += 1
    return _contador


def crear_usuario_directo(nombre_usuario: str, contrasena: str, rol: str = "CLIENTE", hashear: bool = True) -> int:
    from servicios import servicio_seguridad

    valor = servicio_seguridad.hashear(contrasena, ITERACIONES_DE_APOYO) if hashear else contrasena
    return ejecutar(
        "INSERT INTO usuario (NombreUsuario, `Contraseña`, Rol) VALUES (%s, %s, %s)",
        (nombre_usuario, valor, rol),
    )


def crear_cliente(nombre: str = "Ana", apellido: str = "Lopez", contrasena: str = "Corallie2026") -> dict:
    n = _siguiente()
    usuario = f"cliente{n}"
    id_usuario = crear_usuario_directo(usuario, contrasena, "CLIENTE")
    id_cliente = ejecutar(
        "INSERT INTO cliente (Nombre, Apellido, Telefono, Correo, Usuario_IdUsuario) VALUES (%s, %s, %s, %s, %s)",
        (nombre, apellido, f"32210{n:05d}", f"cliente{n}@gmail.com", id_usuario),
    )
    return {"id_usuario": id_usuario, "id_cliente": id_cliente, "usuario": usuario, "nombre": nombre}


def crear_empleado(nombre: str = "Juan", apellido: str = "Perez", contrasena: str = "Corallie2026") -> dict:
    n = _siguiente()
    usuario = f"empleado{n}"
    id_usuario = crear_usuario_directo(usuario, contrasena, "EMPLEADO")
    id_empleado = ejecutar(
        "INSERT INTO empleado (Nombre, Apellido, Telefono, Correo, Usuario_IdUsuario) VALUES (%s, %s, %s, %s, %s)",
        (nombre, apellido, f"32220{n:05d}", f"empleado{n}@gmail.com", id_usuario),
    )
    return {"id_usuario": id_usuario, "id_empleado": id_empleado, "usuario": usuario}


def crear_pedido_directo(
    id_cliente: int,
    estatus: int = 3,
    hace_minutos: float = 0,
    total: float = 65.0,
    producto: str = "Taro Milk Tea (x1) [Tamaño: Mediano]",
) -> int:
    """Pedido escrito directo en la tabla, con la hora que se necesite."""
    nombres = {1: "Pagado", 2: "En preparación", 3: "Pedido Realizado", 4: "Entregado", 5: "Cancelado", 6: "No recogido"}
    momento = (ahora_local() - timedelta(minutes=hace_minutos)).replace(microsecond=0)
    return ejecutar(
        "INSERT INTO generarpedido (HoraPedido, FechaPedido, Producto, Observaciones, Total, NumeroMesa, "
        "Estatus, EstatusPedido_IdEstatusPedido, Clientes_Idcliente) VALUES (%s, %s, %s, NULL, %s, 1, %s, %s, %s)",
        (momento.time(), momento.date(), producto, total, nombres[estatus], estatus, id_cliente),
    )


def estatus_de(pedido_id: int) -> int:
    fila = uno("SELECT EstatusPedido_IdEstatusPedido AS e FROM generarpedido WHERE IdGenerarPedido = %s", (pedido_id,))
    return int(fila["e"]) if fila else 0


def contar(tabla: str, where: str = "1=1", parametros: tuple = ()) -> int:
    fila = uno(f"SELECT COUNT(*) AS n FROM `{tabla}` WHERE {where}", parametros)
    return int(fila["n"])


# ------------------------------------------------------------
# 5. Sin conexion
# ------------------------------------------------------------
def _puerto_libre() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@contextlib.contextmanager
def sin_conexion():
    """Hace que la app no pueda llegar a la base, como si no hubiera internet.

    Apunta la conexion a un puerto local cerrado: el sistema operativo
    rechaza la conexion de inmediato (error 2003), igual que cuando el
    servidor no es alcanzable.
    """
    puerto_original = base_datos.DB_PORT
    host_original = base_datos.DB_HOST
    base_datos.DB_HOST = "127.0.0.1"
    base_datos.DB_PORT = _puerto_libre()
    reiniciar_pool()
    try:
        yield
    finally:
        base_datos.DB_HOST = host_original
        base_datos.DB_PORT = puerto_original
        reiniciar_pool()


# ------------------------------------------------------------
# 6. Clase base
# ------------------------------------------------------------
import unittest  # noqa: E402


class BaseIntegracion(unittest.TestCase):
    """Crea la base una vez y deja los datos limpios antes de cada caso."""

    maxDiff = None

    @classmethod
    def setUpClass(cls):
        preparar_base()

    def setUp(self):
        limpiar_datos()
