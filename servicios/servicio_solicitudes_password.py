"""Solicitudes de contraseña provisional que atiende el administrador.

Antes esta lógica vivía dentro de vistas/vista_admin.py, así que la
campana de notificaciones solo existía en la pantalla de inicio. Ahora
la usa componentes/appbar_admin.py en todas las pantallas del
administrador.

Flujo: el usuario pide restablecer su contraseña (servicio de
autenticación registra la solicitud como 'Pendiente'); el administrador
la ve en la campana, genera una contraseña provisional, se envía al
correo del usuario y la solicitud queda 'Atendida'.
"""

from __future__ import annotations

import secrets
import smtplib
import ssl
import string
from email.message import EmailMessage
from time import monotonic

from configuracion.base_datos import get_connection
from configuracion.variables import (
    SMTP_FROM_NAME,
    SMTP_HOST,
    SMTP_PASSWORD,
    SMTP_PORT,
    SMTP_USER,
)
from servicios import servicio_seguridad as seguridad

# La campana se dibuja en cada pantalla de admin. Para no consultar la
# base de datos en la nube cada vez que se cambia de pantalla, el número
# de pendientes se reutiliza unos segundos. Al abrir el panel o atender
# una solicitud siempre se consulta de nuevo.
SEGUNDOS_CACHE_CONTEO = 30
_cache_conteo = {"valor": 0, "momento": None}
_tabla_verificada = {"valor": False}


def _cerrar(conn, cur):
    try:
        if cur:
            cur.close()
        if conn:
            conn.close()
    except Exception:
        pass


def asegurar_tabla_solicitudes() -> None:
    """Crea la tabla si no existe. Solo se intenta una vez por ejecución."""
    if _tabla_verificada["valor"]:
        return
    conn = None
    cur = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS solicitudes_password (
                IdSolicitud INT AUTO_INCREMENT PRIMARY KEY,
                IdUsuario INT NOT NULL,
                NombreUsuario VARCHAR(100) NOT NULL,
                TipoCuenta VARCHAR(30) NULL,
                Correo VARCHAR(120) NULL,
                Estado VARCHAR(30) NOT NULL DEFAULT 'Pendiente',
                PasswordTemporal VARCHAR(255) NULL,
                FechaSolicitud DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FechaAtencion DATETIME NULL
            )
            """
        )
        conn.commit()
        _tabla_verificada["valor"] = True
    except Exception:
        pass
    finally:
        _cerrar(conn, cur)


def obtener_solicitudes_pendientes() -> list[dict]:
    """Solicitudes que el administrador todavía no atiende."""
    asegurar_tabla_solicitudes()
    conn = None
    cur = None
    try:
        conn = get_connection()
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT
                IdSolicitud,
                IdUsuario,
                NombreUsuario,
                TipoCuenta,
                Correo,
                Estado,
                FechaSolicitud
            FROM solicitudes_password
            WHERE Estado = 'Pendiente'
            ORDER BY IdSolicitud DESC
            """
        )
        filas = cur.fetchall() or []
    except Exception:
        filas = []
    finally:
        _cerrar(conn, cur)

    _cache_conteo["valor"] = len(filas)
    _cache_conteo["momento"] = monotonic()
    return filas


def contar_pendientes(forzar: bool = False) -> int:
    """Número de solicitudes pendientes para el globo rojo de la campana."""
    momento = _cache_conteo["momento"]
    if not forzar and momento is not None and monotonic() - momento < SEGUNDOS_CACHE_CONTEO:
        return _cache_conteo["valor"]
    return len(obtener_solicitudes_pendientes())


def generar_password_temporal(longitud: int = 10) -> str:
    """Genera una contraseña temporal que cumple la política del sistema."""
    caracteres = string.ascii_letters + string.digits
    while True:
        candidata = "CB-" + "".join(secrets.choice(caracteres) for _ in range(longitud))
        if seguridad.validar_fortaleza(candidata).valida:
            return candidata


def enviar_correo_temporal(destinatario: str, nombre_usuario: str, password_temporal: str) -> None:
    """Envía la contraseña provisional al correo del usuario."""
    if not SMTP_USER or not SMTP_PASSWORD:
        raise Exception(
            "No está configurado el correo SMTP. Configura CORALLIE_SMTP_USER y "
            "CORALLIE_SMTP_PASSWORD en el archivo .env de la raíz del proyecto."
        )

    msg = EmailMessage()
    msg["Subject"] = "Contraseña temporal - Corallie Bubble"
    msg["From"] = f"{SMTP_FROM_NAME} <{SMTP_USER}>"
    msg["To"] = destinatario
    msg.set_content(
        f"Hola, {nombre_usuario}.\n\n"
        "Se generó una contraseña temporal para acceder a Corallie Bubble.\n\n"
        f"Usuario: {nombre_usuario}\n"
        f"Contraseña temporal: {password_temporal}\n\n"
        "Por seguridad, cambia tu contraseña después de iniciar sesión.\n\n"
        "Atentamente,\nCorallie Bubble"
    )

    context = ssl.create_default_context()
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls(context=context)
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.send_message(msg)


def marcar_solicitud_atendida(id_solicitud: int, password_temporal: str) -> None:
    """Guarda la contraseña provisional (hasheada) y cierra la solicitud.

    El usuario queda marcado para cambiarla al iniciar sesión.
    """
    password_hash = seguridad.hashear(password_temporal)
    conn = None
    cur = None
    try:
        conn = get_connection()
        conn.start_transaction()
        cur = conn.cursor()

        cur.execute(
            """
            SELECT IdUsuario
            FROM solicitudes_password
            WHERE IdSolicitud=%s AND Estado='Pendiente'
            LIMIT 1
            """,
            (int(id_solicitud),),
        )
        row = cur.fetchone()
        if not row:
            raise Exception("La solicitud ya fue atendida o no existe.")

        id_usuario = int(row[0])

        cur.execute(
            """
            UPDATE usuario
            SET Contraseña=%s,
                RequiereCambio=1
            WHERE IdUsuario=%s
            """,
            (password_hash, id_usuario),
        )

        cur.execute(
            """
            UPDATE solicitudes_password
            SET Estado='Atendida',
                PasswordTemporal=%s,
                FechaAtencion=NOW()
            WHERE IdSolicitud=%s
            """,
            (password_hash, int(id_solicitud)),
        )

        conn.commit()
    except Exception:
        if conn:
            conn.rollback()
        raise
    finally:
        _cerrar(conn, cur)
        # El conteo cambió: la próxima campana debe consultar de nuevo.
        _cache_conteo["momento"] = None