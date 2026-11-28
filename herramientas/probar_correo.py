"""Diagnóstico del envío de correo (contraseña provisional).

Prueba, con los mismos datos del archivo .env que usa la aplicación,
si la computadora puede conectarse al servidor de correo e iniciar
sesión. No envía ningún correo: solo se conecta, inicia sesión y cierra.

Prueba dos formas:
  - Puerto 587 con STARTTLS (la que usa hoy la aplicación).
  - Puerto 465 con SSL directo.

Se puede ejecutar con el botón "Run" de VS Code o desde la raíz:

    python -m herramientas.probar_correo
"""

from __future__ import annotations

import smtplib
import socket
import ssl
import sys
from pathlib import Path

# Permite correrlo también con el botón "Run" de VS Code o con
# "python herramientas/probar_correo.py": agrega la raíz del proyecto
# a la ruta de búsqueda para que encuentre el paquete configuracion.
RAIZ_PROYECTO = Path(__file__).resolve().parent.parent
if str(RAIZ_PROYECTO) not in sys.path:
    sys.path.insert(0, str(RAIZ_PROYECTO))

from configuracion.variables import SMTP_HOST, SMTP_PASSWORD, SMTP_PORT, SMTP_USER

TIEMPO_MAXIMO = 15


def _ocultar(texto: str) -> str:
    if not texto:
        return "(vacío)"
    if "@" in texto:
        nombre, dominio = texto.split("@", 1)
        return f"{nombre[:2]}***@{dominio}"
    return f"{len(texto)} caracteres"


def _probar_puerto(host: str, puerto: int) -> bool:
    print(f"\n[1] ¿Se abre el puerto {puerto} de {host}?")
    try:
        with socket.create_connection((host, puerto), timeout=TIEMPO_MAXIMO):
            print("    Sí, el puerto responde.")
            return True
    except OSError as exc:
        print(f"    NO: {exc}")
        print("    La red, el firewall o el antivirus están bloqueando este puerto.")
        return False


def _probar_starttls(host: str, puerto: int) -> None:
    print(f"\n[2] Conexión STARTTLS en el puerto {puerto} (como la aplicación)")
    try:
        with smtplib.SMTP(host, puerto, timeout=TIEMPO_MAXIMO) as server:
            server.ehlo()
            server.starttls(context=ssl.create_default_context())
            server.ehlo()
            server.login(SMTP_USER, SMTP_PASSWORD)
        print("    OK: conexión e inicio de sesión correctos.")
    except smtplib.SMTPAuthenticationError as exc:
        print(f"    Conecta, pero el usuario o la contraseña no sirven: {exc.smtp_code} {exc.smtp_error!r}")
        print("    En Gmail se necesita una 'contraseña de aplicación' de 16 letras, no la contraseña normal.")
    except smtplib.SMTPServerDisconnected as exc:
        print(f"    FALLO: {exc}")
        print("    El servidor (o algo en medio, como un antivirus) cortó la conexión.")
    except (OSError, smtplib.SMTPException) as exc:
        print(f"    FALLO: {type(exc).__name__}: {exc}")


def _probar_ssl(host: str) -> None:
    print("\n[3] Conexión SSL directa en el puerto 465")
    try:
        with smtplib.SMTP_SSL(host, 465, timeout=TIEMPO_MAXIMO, context=ssl.create_default_context()) as server:
            server.login(SMTP_USER, SMTP_PASSWORD)
        print("    OK: conexión e inicio de sesión correctos.")
    except smtplib.SMTPAuthenticationError as exc:
        print(f"    Conecta, pero el usuario o la contraseña no sirven: {exc.smtp_code} {exc.smtp_error!r}")
    except (OSError, smtplib.SMTPException) as exc:
        print(f"    FALLO: {type(exc).__name__}: {exc}")


def main() -> int:
    print("Datos leídos del .env")
    print(f"    Servidor  : {SMTP_HOST}")
    print(f"    Puerto    : {SMTP_PORT}")
    print(f"    Usuario   : {_ocultar(SMTP_USER)}")
    print(f"    Contraseña: {_ocultar(SMTP_PASSWORD)}")

    if SMTP_PORT == 465:
        print("\n¡OJO! El .env tiene el puerto 465, pero la aplicación usa STARTTLS,")
        print("que solo funciona con el 587. Esa combinación da justo el error")
        print("'Connection unexpectedly closed'. Cambia CORALLIE_SMTP_PORT a 587.")

    if not SMTP_USER or not SMTP_PASSWORD:
        print("\nFaltan CORALLIE_SMTP_USER o CORALLIE_SMTP_PASSWORD en el .env.")
        return 1

    if _probar_puerto(SMTP_HOST, 587):
        _probar_starttls(SMTP_HOST, 587)
    if _probar_puerto(SMTP_HOST, 465):
        _probar_ssl(SMTP_HOST)

    print("\nListo. Mándame lo que salió en pantalla (no incluye tu contraseña).")
    return 0


if __name__ == "__main__":
    sys.exit(main())