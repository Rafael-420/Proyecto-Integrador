"""Variables centrales del proyecto Corallie Bubble.

Las credenciales de base de datos se leen desde variables de entorno
(archivo .env en la raiz del proyecto). Si no existen, se usan los
valores locales de respaldo para poder trabajar sin conexion a la nube.

NUNCA subas el archivo .env al repositorio.
"""

import os
from pathlib import Path

# ------------------------------------------------------------
# Carga del archivo .env (opcional: si no esta python-dotenv,
# el proyecto sigue funcionando con los valores de respaldo)
# ------------------------------------------------------------
try:
    from dotenv import load_dotenv

    _RAIZ_PROYECTO = Path(__file__).resolve().parent.parent
    load_dotenv(_RAIZ_PROYECTO / ".env")
except ImportError:  # pragma: no cover
    pass


def _leer(nombre: str, respaldo: str) -> str:
    """Devuelve la variable de entorno o el valor de respaldo si esta vacia."""
    valor = os.getenv(nombre)
    if valor is None or valor.strip() == "":
        return respaldo
    return valor.strip()


def _leer_int(nombre: str, respaldo: int) -> int:
    try:
        return int(_leer(nombre, str(respaldo)))
    except ValueError:
        return respaldo


def _leer_bool(nombre: str, respaldo: bool) -> bool:
    valor = _leer(nombre, "1" if respaldo else "0").lower()
    return valor in ("1", "true", "yes", "si", "sí", "on")


# ------------------------------------------------------------
# Base de datos
# ------------------------------------------------------------
DB_HOST = _leer("DB_HOST", "localhost")
DB_PORT = _leer_int("DB_PORT", 3306)
DB_USER = _leer("DB_USER", "root")
DB_PASSWORD = _leer("DB_PASSWORD", "root")
DB_NAME = _leer("DB_NAME", "ing_software")

# Railway usa certificados autofirmados. Si la conexion falla con un error
# de SSL, pon DB_SSL_DISABLED=true en el archivo .env
DB_SSL_DISABLED = _leer_bool("DB_SSL_DISABLED", False)

# Pool de conexiones: reduce la latencia al trabajar contra la nube
DB_USAR_POOL = _leer_bool("DB_USAR_POOL", True)
DB_POOL_SIZE = _leer_int("DB_POOL_SIZE", 5)
DB_TIMEOUT = _leer_int("DB_TIMEOUT", 10)


# ------------------------------------------------------------
# Correo (envio de credenciales)
# ------------------------------------------------------------
SMTP_HOST = _leer("CORALLIE_SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = _leer_int("CORALLIE_SMTP_PORT", 587)
SMTP_USER = _leer("CORALLIE_SMTP_USER", "")
SMTP_PASSWORD = _leer("CORALLIE_SMTP_PASSWORD", "")
SMTP_FROM_NAME = _leer("CORALLIE_SMTP_FROM_NAME", "Corallie Bubble")


# ------------------------------------------------------------
# Identidad visual
# ------------------------------------------------------------
COLOR_PRINCIPAL = "#C86DD7"
COLOR_FONDO = "#F9F6FB"


# ------------------------------------------------------------
# Politica de seguridad y autenticacion
# Usada por servicios/servicio_seguridad.py y
# servicios/servicio_autenticacion.py
# ------------------------------------------------------------
# Iteraciones de PBKDF2-SHA256. Mas alto = mas costoso de romper por
# fuerza bruta, pero tambien mas lento al iniciar sesion. 120 000 es
# un punto razonable tanto en escritorio como en el APK.
SEG_ITERACIONES = _leer_int("SEG_ITERACIONES", 120_000)

SEG_LONGITUD_MINIMA = _leer_int("SEG_LONGITUD_MINIMA", 8)
SEG_EXIGIR_LETRA = _leer_bool("SEG_EXIGIR_LETRA", True)
SEG_EXIGIR_DIGITO = _leer_bool("SEG_EXIGIR_DIGITO", True)

# Bloqueo temporal por intentos fallidos
SEG_INTENTOS_MAXIMOS = _leer_int("SEG_INTENTOS_MAXIMOS", 5)
SEG_VENTANA_MINUTOS = _leer_int("SEG_VENTANA_MINUTOS", 15)
SEG_MINUTOS_BLOQUEO = _leer_int("SEG_MINUTOS_BLOQUEO", 15)


# ------------------------------------------------------------
# Roles (coinciden con la columna usuario.Rol)
# ------------------------------------------------------------
ROL_ADMIN = "ADMIN"
ROL_EMPLEADO = "EMPLEADO"
ROL_CLIENTE = "CLIENTE"
ROLES_VALIDOS = (ROL_ADMIN, ROL_EMPLEADO, ROL_CLIENTE)