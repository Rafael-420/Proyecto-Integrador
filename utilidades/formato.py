"""Utilidades de formato para el proyecto Corallie Bubble."""

from datetime import date, datetime


def formatear_dinero(valor) -> str:
    """Convierte un valor numérico a formato de dinero mexicano."""
    try:
        return f"$ {float(valor):,.2f}"
    except (TypeError, ValueError):
        return "$ 0.00"


def formatear_fecha(valor) -> str:
    """Devuelve una fecha en formato YYYY-MM-DD."""
    if not valor:
        return ""

    if isinstance(valor, (date, datetime)):
        return valor.strftime("%Y-%m-%d")

    return str(valor)


def formatear_hora(valor) -> str:
    """Devuelve una hora como texto legible."""
    if not valor:
        return ""

    if isinstance(valor, datetime):
        return valor.strftime("%H:%M:%S")

    return str(valor)


def limpiar_texto(valor: str) -> str:
    """Quita espacios sobrantes de un texto."""
    return " ".join(str(valor or "").strip().split())
