"""Validaciones comunes para formularios de personas."""

import re

RE_NOMBRE   = re.compile(r"^[A-Za-zÁÉÍÓÚáéíóúÑñÜü ]{2,}$")
RE_CORREO   = re.compile(r"^[\w\.-]+@(gmail|hotmail|outlook|yahoo)\.com$")
RE_USUARIO  = re.compile(r"^[A-Za-z0-9_]{4,}$")


def limpiar(valor: str) -> str:
    return " ".join(str(valor or "").strip().split())


def validar_nombre(valor: str, campo: str = "Nombre", max_len: int = 30) -> tuple:
    """
    Retorna (ok: bool, mensaje: str | None, texto_limpio: str).
    Requiere mínimo 2 letras, solo letras y espacios, máximo max_len.
    """
    texto = limpiar(valor)
    if not texto:
        return False, f"Ingresa {campo.lower()}", texto
    if len(texto) < 2:
        return False, f"Mínimo 2 caracteres", texto
    if len(texto) > max_len:
        return False, f"Máximo {max_len} caracteres", texto
    if not RE_NOMBRE.match(texto):
        return False, "Solo letras y espacios", texto
    return True, None, texto


def validar_telefono(valor: str, max_len: int = 10) -> tuple:
    """Exactamente max_len dígitos."""
    texto = limpiar(valor)
    if not texto:
        return False, "Ingresa el teléfono", texto
    if not texto.isdigit():
        return False, "Solo números", texto
    if len(texto) != max_len:
        return False, f"El teléfono debe tener exactamente {max_len} números", texto
    return True, None, texto


def validar_correo(valor: str) -> tuple:
    """
    Solo acepta dominios: gmail, hotmail, outlook, yahoo (.com).
    Retorna el correo en minúsculas.
    """
    texto = limpiar(valor).lower()
    if not texto:
        return False, "Ingresa el correo", texto
    if not RE_CORREO.match(texto):
        return False, "Correo inválido. Ejemplo: usuario@gmail.com", texto
    return True, None, texto


def validar_usuario(valor: str, max_len: int = 20) -> tuple:
    """
    4–max_len caracteres, solo letras, números o guión bajo.
    """
    texto = limpiar(valor)
    if not texto:
        return False, "Ingresa nombre de usuario", texto
    if len(texto) < 4:
        return False, "Mínimo 4 caracteres", texto
    if len(texto) > max_len:
        return False, f"Máximo {max_len} caracteres", texto
    if not RE_USUARIO.match(texto):
        return False, "Solo letras, números o _ (sin espacios)", texto
    return True, None, texto


def validar_password(valor: str, obligatorio: bool = True) -> tuple:
    """Mínimo 6 caracteres cuando es obligatorio."""
    texto = str(valor or "").strip()
    if not texto and not obligatorio:
        return True, None, None
    if len(texto) < 6:
        return False, "La contraseña debe tener mínimo 6 caracteres", texto
    return True, None, texto
