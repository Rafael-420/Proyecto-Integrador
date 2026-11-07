"""
servicios/servicio_sesion.py
----------------------------
Sesion del usuario y control de acceso por rol.

Problema que resuelve: la app corre en el navegador (WEB_BROWSER) y el
router abria cualquier ruta sin revisar nada. Escribir
http://servidor:8550/admin_usuarios en la barra de direcciones, o usar
el boton "atras" despues de cerrar sesion, mostraba el panel de
administracion sin contrasena (OWASP Top 10 A01, MASVS-AUTH-1).

Reglas:

  * La sesion vive SOLO en la memoria del servidor (page._mem_store).
    En modo web, Flet crea un objeto page distinto por cada pestana del
    navegador, asi que la sesion de una persona no la ve otra.
  * Nunca se lee del almacenamiento del navegador (client_storage /
    shared_preferences): el usuario puede editarlo y, en una caja
    compartida, ahi quedan los datos del usuario anterior.
  * El rol sale de la base de datos al iniciar sesion, nunca del nombre
    de usuario.
  * Ruta no listada en PERMISOS = acceso denegado (lista blanca).
"""

from __future__ import annotations

from configuracion.variables import ROL_ADMIN, ROL_CLIENTE, ROL_EMPLEADO, ROLES_VALIDOS

_CLAVE_SESION = "sesion"

# Datos que el login guarda para las vistas. Se borran al cerrar sesion
# para que el siguiente usuario de la misma caja no los herede.
CLAVES_DE_SESION = (
    _CLAVE_SESION,
    "admin",
    "cliente",
    "cliente_id",
    "corte_id",
    "empleado",
    "empleado_id",
    "rol",
    "usuario_id",
)

RUTAS_PUBLICAS = frozenset({"/", "/registro"})

# Ruta -> roles que pueden abrirla.
PERMISOS: dict[str, frozenset[str]] = {
    "/menu": frozenset({ROL_CLIENTE}),
    "/pos": frozenset({ROL_EMPLEADO}),
    "/inventario": frozenset({ROL_EMPLEADO}),
    "/movimientos": frozenset({ROL_EMPLEADO}),
    "/caja_chica": frozenset({ROL_EMPLEADO}),
    "/admin": frozenset({ROL_ADMIN}),
    "/admin_empleados": frozenset({ROL_ADMIN}),
    "/admin_usuarios": frozenset({ROL_ADMIN}),
    "/admin_bebidas": frozenset({ROL_ADMIN}),
    "/admin_servicio": frozenset({ROL_ADMIN}),
    "/reportes": frozenset({ROL_ADMIN}),
}

# Pantalla de inicio de cada rol.
INICIO_POR_ROL = {
    ROL_ADMIN: "/admin",
    ROL_EMPLEADO: "/pos",
    ROL_CLIENTE: "/menu",
}


# ------------------------------------------------------------
# Memoria del servidor
# ------------------------------------------------------------
def _memoria(page) -> dict:
    store = getattr(page, "_mem_store", None)
    if not isinstance(store, dict):
        store = {}
        page._mem_store = store
    return store


def iniciar_sesion(page, usuario_id: int, rol: str) -> None:
    """Registra al usuario autenticado. Llamar solo despues del login."""
    rol = str(rol or "").upper()
    if rol not in ROLES_VALIDOS:
        raise ValueError(f"Rol no valido: {rol}")
    _memoria(page)[_CLAVE_SESION] = {"usuario_id": int(usuario_id), "rol": rol}


def sesion_actual(page) -> dict | None:
    """Devuelve {'usuario_id', 'rol'} o None si nadie ha iniciado sesion."""
    store = getattr(page, "_mem_store", None)
    if not isinstance(store, dict):
        return None
    sesion = store.get(_CLAVE_SESION)
    if not isinstance(sesion, dict) or sesion.get("rol") not in ROLES_VALIDOS:
        return None
    return sesion


def rol_actual(page) -> str | None:
    sesion = sesion_actual(page)
    return sesion["rol"] if sesion else None


def cerrar_sesion(page) -> None:
    """Borra la sesion de la memoria y del almacenamiento del navegador."""
    store = getattr(page, "_mem_store", None)
    if isinstance(store, dict):
        for clave in CLAVES_DE_SESION:
            store.pop(clave, None)

    # Flet 0.2x: client_storage (sincrono)
    almacen = getattr(page, "client_storage", None)
    if almacen is not None:
        for clave in CLAVES_DE_SESION:
            try:
                almacen.remove(clave)
            except Exception:
                pass

    # Flet 0.8x: shared_preferences (asincrono)
    preferencias = getattr(page, "shared_preferences", None)
    if preferencias is not None and hasattr(page, "run_task"):

        async def _borrar():
            for clave in CLAVES_DE_SESION:
                try:
                    await preferencias.remove(clave)
                except Exception:
                    pass

        try:
            page.run_task(_borrar)
        except Exception:
            pass


# ------------------------------------------------------------
# Control de acceso
# ------------------------------------------------------------
def puede_acceder(rol: str | None, ruta: str) -> bool:
    if ruta in RUTAS_PUBLICAS:
        return True
    permitidos = PERMISOS.get(ruta)
    if permitidos is None:
        return False
    return rol in permitidos


def ruta_inicio(rol: str | None) -> str:
    return INICIO_POR_ROL.get(rol, "/")