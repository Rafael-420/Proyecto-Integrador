"""
utilidades/errores.py
---------------------
Convierte una excepcion en un mensaje que se puede mostrar al usuario.

Antes las pantallas mostraban la excepcion tal cual, por ejemplo:

    Error al guardar: 1054 (42S22): Unknown column 'Contraseña' in 'field list'

Eso revela nombres de tablas, columnas, el motor de base de datos y
rutas internas, informacion util para un atacante (OWASP Top 10 A05,
MASVS-CODE-4). Ahora:

  * Los errores de negocio que escribe el propio equipo (ValueError,
    ErrorAutenticacion, PedidoNoPermitido...) se muestran igual que
    antes, porque ya son mensajes pensados para el usuario.
  * Los errores tecnicos se cambian por un mensaje claro y el detalle
    se imprime en la consola del servidor para poder depurar.

Uso en una vista:

    except Exception as ex:
        _show_snack(page, f"No se pudo guardar: {detalle_seguro(ex)}", ok=False)
"""

from __future__ import annotations

import traceback

# Codigos de MySQL que tienen una explicacion sencilla.
_MENSAJES_MYSQL = {
    1062: "ya existe un registro con esos datos",
    1451: "el registro está en uso por otros datos y no se puede borrar",
    1452: "uno de los datos relacionados ya no existe",
    1406: "uno de los campos es demasiado largo",
    1366: "uno de los campos tiene un formato no válido",
}

_SIN_CONEXION = "no hay conexión con el servidor. Revisa tu internet e intenta de nuevo"
_INESPERADO = "ocurrió un error inesperado. Intenta de nuevo"

# Mensajes en ingles que Python genera al convertir texto a numero.
_CONVERSION_NUMERICA = ("invalid literal for", "could not convert")


def _es_error_de_negocio(ex: BaseException) -> bool:
    # Las excepciones propias del proyecto (ErrorAutenticacion,
    # PedidoNoPermitido, FechaDuplicada...) se definen en estas carpetas.
    modulo = type(ex).__module__ or ""
    if modulo.startswith(("servicios.", "vistas.", "componentes.", "utilidades.")):
        return True
    # ValueError "puro" es el que lanzan las validaciones del equipo. Sus
    # subclases de librerias externas (p. ej. errores de MySQL) no cuentan.
    return type(ex) is ValueError


def _es_error_de_red(ex: BaseException) -> bool:
    try:
        from configuracion.base_datos import es_error_de_red
        return es_error_de_red(ex)
    except Exception:
        return isinstance(ex, (OSError, TimeoutError, ConnectionError))


def detalle_seguro(ex: BaseException) -> str:
    """Texto apto para mostrarse en pantalla a partir de una excepcion."""
    if _es_error_de_negocio(ex):
        texto = str(ex).strip()
        if texto and not texto.lower().startswith(_CONVERSION_NUMERICA):
            return texto
        if texto:
            return "revisa que las cantidades y precios sean números válidos"

    codigo = getattr(ex, "errno", None)
    if codigo in _MENSAJES_MYSQL:
        mensaje = _MENSAJES_MYSQL[codigo]
    elif _es_error_de_red(ex):
        mensaje = _SIN_CONEXION
    else:
        mensaje = _INESPERADO

    # El detalle completo solo va a la consola del servidor.
    print(f"[error] {type(ex).__name__}: {ex}")
    traceback.print_exception(type(ex), ex, ex.__traceback__)
    return mensaje