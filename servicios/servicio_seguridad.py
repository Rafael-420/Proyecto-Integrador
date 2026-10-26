"""
servicios/servicio_seguridad.py
-------------------------------
Hashing y verificacion de contrasenas.

Algoritmo: PBKDF2-HMAC-SHA256 con sal aleatoria de 16 bytes.
Solo usa la biblioteca estandar (hashlib, secrets, hmac), por lo que
funciona igual en escritorio y en el empaquetado movil sin dependencias
nativas adicionales.

Formato almacenado en usuario.Contraseña:
    pbkdf2_sha256$<iteraciones>$<sal_hex>$<hash_hex>

Formatos heredados que se siguen reconociendo (y se migran solos):
    sha256$<64 hex>   -> hash SHA-256 sin sal de la version anterior
    <64 hex>          -> mismo caso, sin prefijo
    <texto plano>     -> contrasenas guardadas sin cifrar
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import unicodedata
from dataclasses import dataclass

from configuracion.variables import (
    SEG_ITERACIONES,
    SEG_LONGITUD_MINIMA,
    SEG_EXIGIR_LETRA,
    SEG_EXIGIR_DIGITO,
)

ALGORITMO = "pbkdf2_sha256"
PREFIJO_HEREDADO = "sha256$"
_LONGITUD_SAL = 16
_HEX_64 = re.compile(r"^[0-9a-fA-F]{64}$")

# Alfabeto sin caracteres ambiguos (0/O, 1/l/I) para contrasenas temporales
_ALFABETO_TEMPORAL = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"


# ------------------------------------------------------------
# Normalizacion
# ------------------------------------------------------------
def _normalizar(contrasena: str) -> bytes:
    """Normaliza Unicode (NFKC) para que acentos y ñ se comparen igual
    sin importar el teclado o el sistema operativo del usuario."""
    if contrasena is None:
        contrasena = ""
    return unicodedata.normalize("NFKC", str(contrasena)).encode("utf-8")


# ------------------------------------------------------------
# Hashing
# ------------------------------------------------------------
def hashear(contrasena: str, iteraciones: int | None = None) -> str:
    """Genera el hash PBKDF2 listo para guardar en la base de datos."""
    iteraciones = int(iteraciones or SEG_ITERACIONES)
    sal = secrets.token_bytes(_LONGITUD_SAL)
    derivado = hashlib.pbkdf2_hmac("sha256", _normalizar(contrasena), sal, iteraciones)
    return f"{ALGORITMO}${iteraciones}${sal.hex()}${derivado.hex()}"


def _verificar_pbkdf2(contrasena: str, almacenado: str) -> bool:
    try:
        _, iteraciones_txt, sal_hex, hash_hex = almacenado.split("$", 3)
        iteraciones = int(iteraciones_txt)
        sal = bytes.fromhex(sal_hex)
        esperado = bytes.fromhex(hash_hex)
    except (ValueError, TypeError):
        return False

    calculado = hashlib.pbkdf2_hmac("sha256", _normalizar(contrasena), sal, iteraciones)
    return hmac.compare_digest(calculado, esperado)


def _verificar_sha256(contrasena: str, hash_hex: str) -> bool:
    calculado = hashlib.sha256(_normalizar(contrasena)).hexdigest()
    return hmac.compare_digest(calculado, hash_hex.lower())


def _verificar_plano(contrasena: str, almacenado: str) -> bool:
    return hmac.compare_digest(_normalizar(contrasena), _normalizar(almacenado))


@dataclass(frozen=True)
class ResultadoVerificacion:
    valida: bool
    requiere_rehash: bool
    formato: str


def verificar(contrasena: str, almacenado: str) -> ResultadoVerificacion:
    """Verifica una contrasena contra cualquiera de los formatos soportados.

    `requiere_rehash` indica que el registro debe actualizarse a PBKDF2
    aprovechando que en este momento se conoce la contrasena en claro.
    """
    almacenado = (almacenado or "").strip()

    if not almacenado:
        return ResultadoVerificacion(False, False, "vacio")

    if almacenado.startswith(ALGORITMO + "$"):
        valida = _verificar_pbkdf2(contrasena, almacenado)
        return ResultadoVerificacion(valida, valida and _iteraciones_desactualizadas(almacenado), ALGORITMO)

    if almacenado.startswith(PREFIJO_HEREDADO):
        valida = _verificar_sha256(contrasena, almacenado[len(PREFIJO_HEREDADO):])
        return ResultadoVerificacion(valida, valida, "sha256")

    if _HEX_64.match(almacenado):
        valida = _verificar_sha256(contrasena, almacenado)
        return ResultadoVerificacion(valida, valida, "sha256")

    valida = _verificar_plano(contrasena, almacenado)
    return ResultadoVerificacion(valida, valida, "texto_plano")


def _iteraciones_desactualizadas(almacenado: str) -> bool:
    try:
        iteraciones = int(almacenado.split("$", 3)[1])
    except (ValueError, IndexError):
        return True
    return iteraciones < int(SEG_ITERACIONES)


def es_formato_seguro(almacenado: str) -> bool:
    """True solo si el valor guardado ya usa PBKDF2."""
    return bool(almacenado) and str(almacenado).startswith(ALGORITMO + "$")


def describir_formato(almacenado: str) -> str:
    """Etiqueta legible para reportes de auditoria."""
    almacenado = (almacenado or "").strip()
    if almacenado.startswith(ALGORITMO + "$"):
        return "PBKDF2-SHA256 (seguro)"
    if almacenado.startswith(PREFIJO_HEREDADO) or _HEX_64.match(almacenado):
        return "SHA-256 sin sal (heredado)"
    if not almacenado:
        return "Vacio"
    return "Texto plano (inseguro)"


# ------------------------------------------------------------
# Politica de contrasenas
# ------------------------------------------------------------
@dataclass(frozen=True)
class ResultadoPolitica:
    valida: bool
    errores: tuple

    @property
    def mensaje(self) -> str:
        return " ".join(self.errores)


def validar_fortaleza(contrasena: str, nombre_usuario: str = "") -> ResultadoPolitica:
    """Valida la contrasena contra la politica del proyecto."""
    contrasena = contrasena or ""
    errores = []

    minimo = int(SEG_LONGITUD_MINIMA)
    if len(contrasena) < minimo:
        errores.append(f"Debe tener al menos {minimo} caracteres.")
    if len(contrasena) > 128:
        errores.append("No puede exceder 128 caracteres.")
    if SEG_EXIGIR_LETRA and not any(c.isalpha() for c in contrasena):
        errores.append("Debe incluir al menos una letra.")
    if SEG_EXIGIR_DIGITO and not any(c.isdigit() for c in contrasena):
        errores.append("Debe incluir al menos un numero.")
    if contrasena != contrasena.strip():
        errores.append("No debe iniciar ni terminar con espacios.")
    if nombre_usuario and contrasena.lower() == str(nombre_usuario).lower():
        errores.append("No puede ser igual al nombre de usuario.")
    if contrasena.lower() in _COMUNES:
        errores.append("Es una contrasena demasiado comun.")

    return ResultadoPolitica(not errores, tuple(errores))


_COMUNES = {
    "12345678", "123456789", "1234567890", "password", "password1",
    "contrasena", "contraseña", "qwertyui", "admin123", "administrador",
    "corallie", "bubbletea", "iloveyou", "abc12345", "11111111",
}


def evaluar_nivel(contrasena: str) -> tuple[int, str]:
    """Devuelve (0-4, etiqueta) para pintar un indicador visual en la UI."""
    contrasena = contrasena or ""
    puntos = 0
    if len(contrasena) >= 8:
        puntos += 1
    if len(contrasena) >= 12:
        puntos += 1
    if any(c.isalpha() for c in contrasena) and any(c.isdigit() for c in contrasena):
        puntos += 1
    if any(not c.isalnum() for c in contrasena):
        puntos += 1
    etiquetas = ("Muy debil", "Debil", "Aceptable", "Fuerte", "Muy fuerte")
    return puntos, etiquetas[puntos]


# ------------------------------------------------------------
# Contrasenas temporales
# ------------------------------------------------------------
def generar_contrasena_temporal(longitud: int = 10) -> str:
    """Genera una contrasena temporal legible que cumple la politica."""
    longitud = max(int(longitud), int(SEG_LONGITUD_MINIMA))
    while True:
        candidata = "".join(secrets.choice(_ALFABETO_TEMPORAL) for _ in range(longitud))
        if validar_fortaleza(candidata).valida:
            return candidata


def generar_token(longitud_bytes: int = 32) -> str:
    """Token aleatorio en hexadecimal (recuperacion, sesiones, etc.)."""
    return secrets.token_hex(longitud_bytes)