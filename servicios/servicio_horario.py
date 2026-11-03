"""Horario laboral e interruptor del servicio de pedidos del menú.

Problema que resuelve: el menú de clientes aceptaba pedidos a cualquier
hora y en días de descanso. Nadie preparaba esas bebidas y, como los
pedidos no recogidos bloquean al cliente, terminaba castigado por algo
que no era su culpa.

Reglas:
  1. El administrador puede pausar el servicio del menú en cualquier
     momento (mantenimiento, falta de insumos, cierre imprevisto) con
     un mensaje para los clientes.
  2. Las fechas registradas en `dias_cerrados` no reciben pedidos.
  3. Cada día de la semana tiene su horario o está marcado como día de
     descanso (`horario_local`).
  4. Los pedidos se dejan de recibir unos minutos antes del cierre
     (`estado_servicio.MinutosAntesCierre`), para que dé tiempo de
     prepararlos y recogerlos.
  5. La caja del local debe estar conectada: mientras un empleado tiene
     la sesión abierta, la aplicación registra cada minuto la hora en
     `estado_servicio.UltimaSenalCaja` (ver servicios/senal_caja.py). Si
     esa señal tiene más de MINUTOS_SENAL_CAJA minutos, el local se
     quedó sin internet o nadie atiende la caja, y no se aceptan pedidos
     que nadie vería.

Con el local cerrado el menú sigue abierto para navegar; solo se
bloquea la creación de pedidos.

La regla vive en `evaluar_estado`, que no toca la base de datos, para
poder probarla con cualquier fecha y hora. `estado_menu` solo reúne los
datos y la llama.
"""

from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta, timezone

from configuracion.base_datos import get_connection
from configuracion.variables import MINUTOS_SENAL_CAJA, ZONA_HORARIA


DIAS_SEMANA = ("Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo")

MARGEN_CIERRE_DEFECTO = 15
MARGEN_CIERRE_MAXIMO = 120
LARGO_MENSAJE_MAXIMO = 200
LARGO_MOTIVO_MAXIMO = 120

# Hasta cuántos días adelante se busca la próxima apertura.
_DIAS_BUSQUEDA = 21

MENSAJE_SERVICIO_PAUSADO = "El servicio de pedidos está pausado por el momento."
MENSAJE_CAJA_DESCONECTADA = (
    "El local no está recibiendo pedidos en este momento. "
    "Intenta de nuevo en unos minutos."
)


# --------------------------------------------------------
# Hora local
# --------------------------------------------------------
def _zona():
    """Zona horaria del local.

    En Windows (y en el APK) zoneinfo necesita el paquete tzdata. Si no
    está, se usa UTC-6 fijo: México no aplica horario de verano desde
    2022, así que el resultado es el mismo en el centro y occidente.
    """
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo(ZONA_HORARIA)
    except Exception:
        return timezone(timedelta(hours=-6), "UTC-06")


def a_hora_local(momento_utc: datetime) -> datetime:
    """Convierte un datetime UTC (con o sin tzinfo) a la hora del local, sin tzinfo."""
    if momento_utc.tzinfo is None:
        momento_utc = momento_utc.replace(tzinfo=timezone.utc)
    return momento_utc.astimezone(_zona()).replace(tzinfo=None, microsecond=0)


def hora_local() -> datetime:
    """Hora actual del local según el reloj de este equipo.

    Es el respaldo de `ahora_servidor`: la zona horaria no depende de la
    configuración del dispositivo, pero el reloj sí.
    """
    return a_hora_local(datetime.now(timezone.utc))


def ahora_servidor(cur) -> datetime:
    """Hora actual del local según el reloj del servidor MySQL.

    UTC_TIMESTAMP() no depende de la zona horaria configurada en el
    servidor, y el cliente no puede adelantar ni atrasar ese reloj. Si
    la consulta falla se usa el reloj del equipo.
    """
    try:
        cur.execute("SELECT UTC_TIMESTAMP() AS Ahora")
        fila = cur.fetchone()
        if isinstance(fila, dict):
            fila = fila.get("Ahora")
        elif isinstance(fila, (tuple, list)):
            fila = fila[0] if fila else None
        if isinstance(fila, datetime):
            return a_hora_local(fila)
    except Exception:
        pass
    return hora_local()


# --------------------------------------------------------
# Conversión y validación de datos
# --------------------------------------------------------
def a_time(valor) -> time | None:
    """Convierte lo que devuelve MySQL en una columna TIME a datetime.time.

    mysql-connector entrega las columnas TIME como timedelta, no como time.
    """
    if valor is None:
        return None
    if isinstance(valor, time):
        return valor.replace(microsecond=0)
    if isinstance(valor, timedelta):
        segundos = int(valor.total_seconds()) % (24 * 3600)
        return time(segundos // 3600, (segundos % 3600) // 60, segundos % 60)
    if isinstance(valor, str):
        return parsear_hora(valor)
    return None


def parsear_hora(texto: str) -> time:
    """Convierte "9:30", "09:30" o "21:00:00" en datetime.time.

    Lanza ValueError con un mensaje para el administrador si no es válida.
    """
    limpio = str(texto or "").strip()
    encontrado = re.fullmatch(r"(\d{1,2}):(\d{2})(?::(\d{2}))?", limpio)
    if not encontrado:
        raise ValueError("Escribe la hora en formato 24 h, por ejemplo 09:30 o 21:00.")
    horas, minutos = int(encontrado.group(1)), int(encontrado.group(2))
    if horas > 23 or minutos > 59:
        raise ValueError("La hora no es válida: usa de 00:00 a 23:59.")
    return time(horas, minutos)


def parsear_fecha(texto: str) -> date:
    """Convierte "25/12/2026" (o "2026-12-25") en datetime.date."""
    limpio = str(texto or "").strip()
    for formato in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(limpio, formato).date()
        except ValueError:
            continue
    raise ValueError("Escribe la fecha como DD/MM/AAAA, por ejemplo 25/12/2026.")


def validar_horario_dia(abierto: bool, apertura: time, cierre: time) -> None:
    """Revisa un día del horario. Lanza ValueError si no es coherente.

    No se admiten horarios que crucen la medianoche (por ejemplo 18:00 a
    01:00): el local no trabaja así y complicaría todas las reglas.
    """
    if apertura is None or cierre is None:
        raise ValueError("Falta la hora de apertura o de cierre.")
    if abierto and cierre <= apertura:
        raise ValueError("La hora de cierre debe ser posterior a la de apertura.")


def formatear_hora(valor: time | None) -> str:
    return valor.strftime("%H:%M") if valor else ""


# --------------------------------------------------------
# Regla de negocio (sin base de datos)
# --------------------------------------------------------
def _plural_dia(dia_semana: int) -> str:
    """"lunes", "sábados", "domingos"."""
    nombre = DIAS_SEMANA[dia_semana].lower()
    return nombre if nombre.endswith("s") else f"{nombre}s"


def _describir_momento(momento: datetime, ahora: datetime) -> str:
    """"hoy a las 10:00", "mañana a las 10:00", "el lunes a las 10:00"..."""
    hora = momento.strftime("%H:%M")
    dias = (momento.date() - ahora.date()).days
    if dias == 0:
        return f"hoy a las {hora}"
    if dias == 1:
        return f"mañana a las {hora}"
    if dias < 7:
        return f"el {DIAS_SEMANA[momento.weekday()].lower()} a las {hora}"
    return f"el {momento.strftime('%d/%m')} a las {hora}"


def proxima_apertura(ahora: datetime, horarios: dict, dias_cerrados: dict) -> datetime | None:
    """Primer momento posterior a `ahora` en que el local abre.

    Devuelve None si no hay ningún día abierto en las próximas semanas
    (por ejemplo, todos los días marcados como descanso).
    """
    for desplazamiento in range(_DIAS_BUSQUEDA):
        fecha = ahora.date() + timedelta(days=desplazamiento)
        if fecha in dias_cerrados:
            continue
        dia = horarios.get(fecha.weekday())
        if not dia or not dia.get("abierto"):
            continue
        apertura = datetime.combine(fecha, dia["apertura"])
        if apertura > ahora:
            return apertura
    return None


def _cuando_abre(ahora, horarios, dias_cerrados) -> tuple[str, datetime | None]:
    momento = proxima_apertura(ahora, horarios, dias_cerrados)
    if momento is None:
        return "", None
    return f" Abrimos {_describir_momento(momento, ahora)}.", momento


def caja_conectada(ahora: datetime, caja: dict | None) -> bool:
    """True si la caja mandó su señal hace menos de los minutos permitidos.

    caja: {"ultima_senal": datetime | None, "minutos": int}
          None significa que la regla no aplica (migración sin aplicar o
          regla desactivada con MINUTOS_SENAL_CAJA=0).
    """
    if caja is None:
        return True
    minutos = int(caja.get("minutos") or 0)
    if minutos <= 0:
        return True
    ultima = caja.get("ultima_senal")
    if not isinstance(ultima, datetime):
        # Ninguna caja se ha conectado todavía: nadie vería el pedido.
        return False
    return ahora - ultima <= timedelta(minutes=minutos)


def evaluar_estado(
    ahora: datetime,
    horarios: dict,
    dias_cerrados: dict,
    servicio: dict,
    caja: dict | None = None,
) -> dict:
    """Decide si el menú acepta pedidos en el momento `ahora`.

    horarios:      {dia_semana: {"abierto": bool, "apertura": time, "cierre": time}}
    dias_cerrados: {date: motivo}
    servicio:      {"menu_activo": bool, "mensaje": str | None, "margen": int}
    caja:          {"ultima_senal": datetime | None, "minutos": int} o None
                   si la regla de la señal de la caja no aplica.

    Devuelve un diccionario con:
      abierto           True si se pueden hacer pedidos.
      motivo            abierto | servicio_pausado | dia_cerrado | descanso |
                        antes_de_abrir | despues_de_cerrar | sin_horario |
                        caja_desconectada
      mensaje           Texto para el cliente (None si está abierto).
      proxima_apertura  datetime o None.
      cierre_pedidos    Hora límite para pedir hoy (solo si está abierto).
      ahora             El momento evaluado.
    """
    resultado = {
        "abierto": True,
        "motivo": "abierto",
        "mensaje": None,
        "proxima_apertura": None,
        "cierre_pedidos": None,
        "ahora": ahora,
    }

    def cerrado(motivo: str, mensaje: str, con_proxima: bool = True) -> dict:
        proxima = None
        if con_proxima:
            complemento, proxima = _cuando_abre(ahora, horarios, dias_cerrados)
            mensaje = f"{mensaje}{complemento}"
        resultado.update(
            abierto=False,
            motivo=motivo,
            mensaje=mensaje.strip(),
            proxima_apertura=proxima,
        )
        return resultado

    # 1. Interruptor del administrador: tiene prioridad sobre todo.
    #    No se calcula la próxima apertura porque no se sabe cuándo
    #    volverá a encenderlo; el mensaje lo escribe él.
    if not servicio.get("menu_activo", True):
        mensaje = (servicio.get("mensaje") or "").strip() or MENSAJE_SERVICIO_PAUSADO
        return cerrado("servicio_pausado", mensaje, con_proxima=False)

    # La señal de la caja se revisa al final, solo si por horario se
    #    podría pedir: fuera de horario es más útil decirle al cliente
    #    cuándo abrimos que decirle que la caja no está conectada.
    def revisar_caja(respuesta: dict) -> dict:
        if caja_conectada(ahora, caja):
            return respuesta
        respuesta.update(
            abierto=False,
            motivo="caja_desconectada",
            mensaje=MENSAJE_CAJA_DESCONECTADA,
            proxima_apertura=None,
            cierre_pedidos=None,
        )
        return respuesta

    # 2. Sin horario capturado (por ejemplo, la migración aún no se
    #    aplicó): no se bloquea por horario, para no apagar el menú por
    #    un problema de configuración.
    if not horarios:
        resultado["motivo"] = "sin_horario"
        return revisar_caja(resultado)

    hoy = ahora.date()

    # 3. Fechas cerradas (festivos, vacaciones).
    if hoy in dias_cerrados:
        motivo = (dias_cerrados.get(hoy) or "").strip()
        texto = f"Hoy no abrimos: {motivo}." if motivo else "Hoy no abrimos."
        return cerrado("dia_cerrado", texto)

    # 4. Día de descanso semanal.
    dia = horarios.get(ahora.weekday())
    if not dia or not dia.get("abierto"):
        return cerrado("descanso", f"Los {_plural_dia(ahora.weekday())} descansamos.")

    apertura = datetime.combine(hoy, dia["apertura"])
    cierre = datetime.combine(hoy, dia["cierre"])
    margen = max(0, int(servicio.get("margen", MARGEN_CIERRE_DEFECTO) or 0))
    cierre_pedidos = cierre - timedelta(minutes=margen)

    # 5. Todavía no abre.
    if ahora < apertura:
        return cerrado("antes_de_abrir", "Todavía no abrimos.")

    # 6. Ya cerró, o está dentro del margen previo al cierre.
    if ahora >= cierre_pedidos:
        if ahora < cierre and margen > 0:
            texto = (
                f"Dejamos de recibir pedidos {margen} minutos antes de cerrar, "
                "para que tu bebida esté lista a tiempo."
            )
        else:
            texto = "Ya cerramos por hoy."
        return cerrado("despues_de_cerrar", texto)

    resultado["cierre_pedidos"] = cierre_pedidos

    # 7. Con el local en horario, la caja debe estar conectada.
    return revisar_caja(resultado)


# --------------------------------------------------------
# Lectura de la base de datos
# --------------------------------------------------------
def _servicio_desde_fila(fila: dict | None) -> dict:
    fila = fila or {}
    margen = fila.get("MinutosAntesCierre")
    return {
        "menu_activo": bool(fila.get("MenuActivo", 1)),
        "mensaje": fila.get("MensajeMenu"),
        "margen": MARGEN_CIERRE_DEFECTO if margen is None else int(margen),
        "modificado_por": fila.get("ModificadoPor"),
        "fecha_modificacion": fila.get("FechaModificacion"),
    }


def _horarios_desde_filas(filas) -> dict:
    horarios = {}
    for fila in filas or []:
        apertura = a_time(fila.get("HoraApertura"))
        cierre = a_time(fila.get("HoraCierre"))
        if apertura is None or cierre is None:
            continue
        horarios[int(fila["DiaSemana"])] = {
            "abierto": bool(fila.get("Abierto")),
            "apertura": apertura,
            "cierre": cierre,
        }
    return horarios


def _leer_servicio(cur) -> dict:
    cur.execute(
        """
        SELECT MenuActivo, MensajeMenu, MinutosAntesCierre,
               ModificadoPor, FechaModificacion
        FROM estado_servicio
        WHERE IdEstadoServicio = 1
        """
    )
    return _servicio_desde_fila(cur.fetchone())


def _leer_horarios(cur) -> dict:
    cur.execute(
        """
        SELECT DiaSemana, Abierto, HoraApertura, HoraCierre
        FROM horario_local
        ORDER BY DiaSemana
        """
    )
    return _horarios_desde_filas(cur.fetchall())


def _leer_dias_cerrados(cur, desde: date, hasta: date | None = None) -> list[dict]:
    if hasta is None:
        cur.execute(
            """
            SELECT IdDiaCerrado, Fecha, Motivo
            FROM dias_cerrados
            WHERE Fecha >= %s
            ORDER BY Fecha
            """,
            (desde,),
        )
    else:
        cur.execute(
            """
            SELECT IdDiaCerrado, Fecha, Motivo
            FROM dias_cerrados
            WHERE Fecha BETWEEN %s AND %s
            ORDER BY Fecha
            """,
            (desde, hasta),
        )
    return [
        {"id": fila.get("IdDiaCerrado"), "fecha": fila.get("Fecha"), "motivo": fila.get("Motivo")}
        for fila in (cur.fetchall() or [])
    ]


def _como_datetime(valor) -> datetime | None:
    return valor.replace(microsecond=0) if isinstance(valor, datetime) else None


def _leer_caja(cur) -> dict | None:
    """Última señal de la caja. None si la regla no aplica.

    Se lee en una consulta aparte: si la migración de la señal todavía
    no se aplicó (no existen las columnas), la consulta falla aquí y el
    resto del estado del menú se sigue leyendo normalmente.
    """
    if int(MINUTOS_SENAL_CAJA or 0) <= 0:
        return None
    try:
        cur.execute(
            """
            SELECT UltimaSenalCaja
            FROM estado_servicio
            WHERE IdEstadoServicio = 1
            """
        )
        fila = cur.fetchone()
    except Exception:
        return None
    if not isinstance(fila, dict):
        return None
    return {
        "ultima_senal": _como_datetime(fila.get("UltimaSenalCaja")),
        "minutos": int(MINUTOS_SENAL_CAJA),
    }


def ultima_desconexion_caja(cur) -> tuple[datetime, datetime] | None:
    """Último periodo en que la caja estuvo sin señal: (inicio, fin).

    Lo usa el marcado automático de "No recogido" para no castigar al
    cliente por un pedido que estuvo esperando mientras el local no
    tenía internet. None si no hay registro o la migración no se aplicó.
    """
    try:
        cur.execute(
            """
            SELECT InicioDesconexionCaja, FinDesconexionCaja
            FROM estado_servicio
            WHERE IdEstadoServicio = 1
            """
        )
        fila = cur.fetchone()
    except Exception:
        return None
    if isinstance(fila, dict):
        inicio, fin = fila.get("InicioDesconexionCaja"), fila.get("FinDesconexionCaja")
    elif isinstance(fila, (tuple, list)) and len(fila) >= 2:
        inicio, fin = fila[0], fila[1]
    else:
        return None
    inicio, fin = _como_datetime(inicio), _como_datetime(fin)
    if inicio is None or fin is None or fin < inicio:
        return None
    return inicio, fin


def _cerrar(conn, cur):
    try:
        if cur:
            cur.close()
        if conn:
            conn.close()
    except Exception:
        pass


def estado_menu() -> dict:
    """Indica si el menú de clientes acepta pedidos en este momento.

    Usa una sola conexión para la hora del servidor, el interruptor, el
    horario y las fechas cerradas.

    Si la consulta falla (sin conexión, o las tablas todavía no existen)
    devuelve "abierto": no se apaga el menú por un problema técnico, y
    insertar_pedido de todos modos necesita la base de datos.
    """
    conn = None
    cur = None
    try:
        conn = get_connection()
        cur = conn.cursor(dictionary=True)
        ahora = ahora_servidor(cur)
        servicio = _leer_servicio(cur)
        horarios = _leer_horarios(cur)
        cerrados = _leer_dias_cerrados(cur, ahora.date(), ahora.date() + timedelta(days=_DIAS_BUSQUEDA))
        caja = _leer_caja(cur)
    except Exception:
        return {
            "abierto": True,
            "motivo": "error_consulta",
            "mensaje": None,
            "proxima_apertura": None,
            "cierre_pedidos": None,
            "ahora": hora_local(),
        }
    finally:
        _cerrar(conn, cur)

    dias_cerrados = {d["fecha"]: d["motivo"] for d in cerrados if d["fecha"]}
    return evaluar_estado(ahora, horarios, dias_cerrados, servicio, caja)


# --------------------------------------------------------
# Administración
# --------------------------------------------------------
def obtener_configuracion() -> dict:
    """Todo lo que necesita la pantalla del administrador.

    A diferencia de estado_menu, aquí los errores sí se propagan: el
    administrador debe enterarse si, por ejemplo, falta la migración.
    """
    conn = None
    cur = None
    try:
        conn = get_connection()
        cur = conn.cursor(dictionary=True)
        ahora = ahora_servidor(cur)
        servicio = _leer_servicio(cur)
        horarios = _leer_horarios(cur)
        cerrados = _leer_dias_cerrados(cur, ahora.date())
        caja = _leer_caja(cur)
    finally:
        _cerrar(conn, cur)

    dias_cerrados = {d["fecha"]: d["motivo"] for d in cerrados if d["fecha"]}
    return {
        "ahora": ahora,
        "servicio": servicio,
        "horarios": horarios,
        "dias_cerrados": cerrados,
        "caja": caja,
        "estado": evaluar_estado(ahora, horarios, dias_cerrados, servicio, caja),
    }


# --------------------------------------------------------
# Señal de la caja
# --------------------------------------------------------
def registrar_senal_caja() -> bool:
    """Registra que la caja sigue conectada. Devuelve False si no hay conexión.

    Si la señal anterior es más vieja que la tolerancia, la caja estuvo
    desconectada (sin internet, o cerrada): se guarda ese periodo para
    que el marcado automático de "No recogido" no castigue a los
    clientes cuyos pedidos esperaron durante ese tiempo.

    La hora es la del servidor MySQL, no la del equipo de la caja.
    """
    tolerancia = timedelta(minutes=max(1, int(MINUTOS_SENAL_CAJA or 0) or 3))
    conn = None
    cur = None
    try:
        conn = get_connection()
        cur = conn.cursor(dictionary=True)
        ahora = ahora_servidor(cur)
        cur.execute(
            """
            SELECT UltimaSenalCaja
            FROM estado_servicio
            WHERE IdEstadoServicio = 1
            FOR UPDATE
            """
        )
        fila = cur.fetchone() or {}
        anterior = _como_datetime(fila.get("UltimaSenalCaja")) if isinstance(fila, dict) else None

        if anterior is not None and ahora - anterior > tolerancia:
            cur.execute(
                """
                UPDATE estado_servicio
                SET UltimaSenalCaja = %s,
                    InicioDesconexionCaja = %s,
                    FinDesconexionCaja = %s
                WHERE IdEstadoServicio = 1
                """,
                (ahora, anterior, ahora),
            )
        else:
            cur.execute(
                """
                UPDATE estado_servicio
                SET UltimaSenalCaja = %s
                WHERE IdEstadoServicio = 1
                """,
                (ahora,),
            )
        conn.commit()
        return True
    except Exception:
        try:
            if conn:
                conn.rollback()
        except Exception:
            pass
        return False
    finally:
        _cerrar(conn, cur)


def guardar_servicio_menu(activo: bool, mensaje: str | None, margen: int, usuario: str) -> None:
    """Enciende o pausa el menú y guarda el mensaje y el margen de cierre."""
    mensaje = (mensaje or "").strip() or None
    if mensaje and len(mensaje) > LARGO_MENSAJE_MAXIMO:
        raise ValueError(f"El mensaje debe tener máximo {LARGO_MENSAJE_MAXIMO} caracteres.")
    try:
        margen = int(margen)
    except (TypeError, ValueError):
        raise ValueError("Los minutos antes del cierre deben ser un número entero.") from None
    if margen < 0 or margen > MARGEN_CIERRE_MAXIMO:
        raise ValueError(f"Los minutos antes del cierre deben ir de 0 a {MARGEN_CIERRE_MAXIMO}.")

    conn = None
    cur = None
    try:
        conn = get_connection()
        cur = conn.cursor(dictionary=True)
        ahora = ahora_servidor(cur)
        cur.execute(
            """
            INSERT INTO estado_servicio
                (IdEstadoServicio, MenuActivo, MensajeMenu, MinutosAntesCierre,
                 ModificadoPor, FechaModificacion)
            VALUES (1, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                MenuActivo = VALUES(MenuActivo),
                MensajeMenu = VALUES(MensajeMenu),
                MinutosAntesCierre = VALUES(MinutosAntesCierre),
                ModificadoPor = VALUES(ModificadoPor),
                FechaModificacion = VALUES(FechaModificacion)
            """,
            (1 if activo else 0, mensaje, margen, (usuario or "")[:80] or None, ahora),
        )
        conn.commit()
    except Exception:
        if conn:
            conn.rollback()
        raise
    finally:
        _cerrar(conn, cur)


def guardar_horarios(horarios: dict) -> None:
    """Guarda el horario semanal completo en una sola transacción.

    horarios: {dia_semana: {"abierto": bool, "apertura": time, "cierre": time}}
    Se validan los siete días antes de escribir nada.
    """
    if set(horarios) != set(range(7)):
        raise ValueError("El horario debe incluir los siete días de la semana.")
    for dia, datos in horarios.items():
        try:
            validar_horario_dia(datos.get("abierto"), datos.get("apertura"), datos.get("cierre"))
        except ValueError as error:
            raise ValueError(f"{DIAS_SEMANA[dia]}: {error}") from None

    conn = None
    cur = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        for dia in range(7):
            datos = horarios[dia]
            apertura, cierre = datos["apertura"], datos["cierre"]
            if not datos["abierto"] and cierre <= apertura:
                # Un día de descanso conserva horas válidas para que la
                # restricción de la tabla no lo rechace.
                apertura, cierre = time(0, 0), time(23, 59)
            cur.execute(
                """
                INSERT INTO horario_local (DiaSemana, Abierto, HoraApertura, HoraCierre)
                VALUES (%s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    Abierto = VALUES(Abierto),
                    HoraApertura = VALUES(HoraApertura),
                    HoraCierre = VALUES(HoraCierre)
                """,
                (dia, 1 if datos["abierto"] else 0, apertura, cierre),
            )
        conn.commit()
    except Exception:
        if conn:
            conn.rollback()
        raise
    finally:
        _cerrar(conn, cur)


class FechaDuplicada(ValueError):
    """La fecha ya estaba registrada como día cerrado."""


def agregar_dia_cerrado(fecha: date, motivo: str | None, hoy: date | None = None) -> int:
    """Registra una fecha en la que el local no abre. Devuelve su ID."""
    if not isinstance(fecha, date):
        raise ValueError("La fecha no es válida.")
    if hoy is not None and fecha < hoy:
        raise ValueError("La fecha ya pasó.")
    motivo = (motivo or "").strip() or None
    if motivo and len(motivo) > LARGO_MOTIVO_MAXIMO:
        raise ValueError(f"El motivo debe tener máximo {LARGO_MOTIVO_MAXIMO} caracteres.")

    conn = None
    cur = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO dias_cerrados (Fecha, Motivo) VALUES (%s, %s)",
            (fecha, motivo),
        )
        conn.commit()
        return int(cur.lastrowid)
    except Exception as error:
        if conn:
            conn.rollback()
        if getattr(error, "errno", None) == 1062:
            raise FechaDuplicada(f"El {fecha.strftime('%d/%m/%Y')} ya está registrado como cerrado.") from None
        raise
    finally:
        _cerrar(conn, cur)


def eliminar_dia_cerrado(id_dia: int) -> bool:
    """Quita una fecha cerrada. Devuelve True si existía."""
    conn = None
    cur = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM dias_cerrados WHERE IdDiaCerrado = %s", (int(id_dia),))
        conn.commit()
        return cur.rowcount > 0
    except Exception:
        if conn:
            conn.rollback()
        raise
    finally:
        _cerrar(conn, cur)