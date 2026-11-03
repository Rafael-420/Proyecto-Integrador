"""Señal de "sigo aquí" de la caja.

Problema que resuelve: la base de datos está en la nube (Railway), no en
el local. Si el local se queda sin internet, el cliente puede seguir
pidiendo desde su celular, pero en la caja nadie ve el pedido: no se
prepara, el cliente llega y no hay bebida, y el pedido terminaba como
"No recogido" bloqueando al cliente sin que fuera su culpa.

Cómo funciona:
  1. Cuando un empleado inicia sesión, esta sesión registra la hora en
     la base de datos cada SEGUNDOS_ENTRE_SENALES (por defecto 60 s).
  2. El menú de clientes revisa esa hora antes de aceptar pedidos
     (servicio_horario.evaluar_estado). Si la última señal tiene más de
     MINUTOS_SENAL_CAJA minutos, el menú se puede ver pero no se puede
     pedir.
  3. Al cerrar sesión, al cerrar la ventana o al perder internet, la
     señal deja de llegar y el menú se bloquea solo. Cuando vuelve la
     conexión, la señal se reanuda y el menú se desbloquea solo.

La señal corre en un hilo aparte: no toca la interfaz salvo para avisar
al empleado cuando la conexión se pierde o regresa.
"""

from __future__ import annotations

import threading

from configuracion.variables import SEGUNDOS_ENTRE_SENALES
from servicios.servicio_horario import registrar_senal_caja

# Nombre del atributo donde cada sesión (page) guarda su señal activa.
_ATRIBUTO = "_senal_caja_detener"

# Aunque se configure un valor menor, no se consulta la base de datos
# más de una vez cada 10 segundos por caja.
_SEGUNDOS_MINIMOS = 10

MENSAJE_SIN_CONEXION = (
    "Se perdió la conexión a internet. Mientras no regrese, el menú de "
    "clientes no acepta pedidos nuevos."
)
MENSAJE_RECONECTADO = "Conexión restablecida. El menú de clientes ya puede recibir pedidos."


def _avisar(page, texto: str, ok: bool) -> None:
    """Muestra un aviso al empleado. Nunca interrumpe la señal si falla."""
    try:
        import flet as ft

        aviso = ft.SnackBar(
            content=ft.Text(texto, color="white"),
            bgcolor="#22C55E" if ok else "#EF4444",
            duration=6000,
        )
        try:
            page.open(aviso)
            return
        except Exception:
            pass
        if hasattr(page, "overlay") and aviso not in page.overlay:
            page.overlay.append(aviso)
        aviso.open = True
        page.update()
    except Exception:
        pass


def _vigilar_cierre(page) -> None:
    """Detiene la señal cuando se cierra la ventana o la pestaña.

    Se instala una sola vez por página y se encadena a los manejadores
    que ya tuviera, para no reemplazarlos.
    """
    if getattr(page, "_senal_caja_vigilada", False) is True:
        return

    for evento in ("on_disconnect", "on_close"):
        try:
            anterior = getattr(page, evento, None)
        except Exception:
            continue

        def manejador(e=None, _anterior=anterior):
            detener_senal_caja(page)
            if callable(_anterior):
                try:
                    _anterior(e)
                except Exception:
                    pass

        try:
            setattr(page, evento, manejador)
        except Exception:
            pass

    try:
        page._senal_caja_vigilada = True
    except Exception:
        pass


def iniciar_senal_caja(page) -> None:
    """Empieza a mandar la señal de esta sesión de caja.

    Si ya había una señal para esta misma página, la reemplaza: así un
    segundo inicio de sesión no deja dos hilos mandando la señal.
    """
    detener_senal_caja(page)

    detener = threading.Event()
    estado = {"conectado": True}
    intervalo = max(_SEGUNDOS_MINIMOS, int(SEGUNDOS_ENTRE_SENALES or 60))

    def ciclo():
        while not detener.is_set():
            conectado = registrar_senal_caja()
            if detener.is_set():
                break
            # Solo se avisa cuando cambia el estado, no en cada intento.
            if conectado != estado["conectado"]:
                estado["conectado"] = conectado
                if conectado:
                    _avisar(page, MENSAJE_RECONECTADO, ok=True)
                else:
                    _avisar(page, MENSAJE_SIN_CONEXION, ok=False)
            detener.wait(intervalo)

    try:
        setattr(page, _ATRIBUTO, detener)
    except Exception:
        pass
    _vigilar_cierre(page)

    threading.Thread(target=ciclo, name="senal_caja", daemon=True).start()


def detener_senal_caja(page) -> None:
    """Deja de mandar la señal (cierre de sesión)."""
    detener = getattr(page, _ATRIBUTO, None)
    if isinstance(detener, threading.Event):
        detener.set()
    try:
        setattr(page, _ATRIBUTO, None)
    except Exception:
        pass
