"""
servicios/servicio_privacidad.py
--------------------------------
Aviso de privacidad y registro del consentimiento.

Cumple con la Ley Federal de Proteccion de Datos Personales en
Posesion de los Particulares (LFPDPPP), publicada en el DOF el
20 de marzo de 2025:

  * Art. 15: contenido minimo del aviso integral (responsable,
    datos que se recaban, finalidades, medios ARCO, cambios).
  * Art. 16: aviso simplificado, el que se muestra junto a la
    casilla del registro.
  * Art. 35: el aviso debe decir si hay transferencias; aqui no las
    hay, y se informan los proveedores que solo alojan o envian datos.

La autoridad ya no es el INAI: sus funciones pasaron a la Secretaria
Anticorrupcion y Buen Gobierno (SABG).

El texto vive aqui (y no en la vista) para poder probarlo, versionarlo
y reutilizarlo en cualquier pantalla que necesite mostrar el aviso.
"""

from __future__ import annotations

from configuracion.variables import (
    PRIVACIDAD_CORREO,
    PRIVACIDAD_DOMICILIO,
    PRIVACIDAD_RESPONSABLE,
)

# Cambiar la version cada vez que cambie el contenido del aviso, para
# saber que version acepto cada usuario.
VERSION_AVISO = "1.0"
FECHA_AVISO = "noviembre de 2026"

# Error de MySQL "la tabla no existe" (migracion aun no aplicada).
_ERROR_TABLA_INEXISTENTE = 1146

ORIGENES_VALIDOS = ("registro_cliente", "registro_empleado")


# ------------------------------------------------------------
# Texto del aviso
# ------------------------------------------------------------
def _medio_arco() -> str:
    if PRIVACIDAD_CORREO:
        return f"escribiendo al correo {PRIVACIDAD_CORREO}"
    return "solicitándolo por escrito en el local o con el administrador del sistema"


def texto_simplificado() -> str:
    """Aviso corto que acompana a la casilla de aceptacion (Art. 16)."""
    return (
        f"{PRIVACIDAD_RESPONSABLE} usará tu nombre, correo y teléfono para crear "
        "tu cuenta, atender tus pedidos y mantener segura la aplicación. "
        "No vendemos ni compartimos tus datos."
    )


def secciones_aviso() -> list[tuple[str, list[str]]]:
    """Aviso integral (Art. 15) como lista de (titulo, parrafos)."""
    responsable = [f"{PRIVACIDAD_RESPONSABLE} es responsable del tratamiento de tus datos personales."]
    if PRIVACIDAD_DOMICILIO:
        responsable.append(f"Domicilio para oír y recibir notificaciones: {PRIVACIDAD_DOMICILIO}.")
    responsable.append(
        "Corallie Bubble es un proyecto académico; los datos se usan solo para operar la aplicación."
    )

    return [
        ("Quién es responsable de tus datos", responsable),
        (
            "Qué datos recabamos",
            [
                "Datos de identificación y contacto: nombre, apellido, correo electrónico y teléfono.",
                "Datos de la cuenta: nombre de usuario y contraseña. La contraseña se guarda "
                "cifrada (hash PBKDF2-SHA256); nadie del equipo puede leerla.",
                "Datos de uso: pedidos realizados, su estado y los intentos de inicio de sesión.",
                "No recabamos datos personales sensibles.",
            ],
        ),
        (
            "Para qué los usamos",
            [
                "Crear y administrar tu cuenta.",
                "Recibir, preparar y entregar tus pedidos, y cobrar los pedidos no recogidos.",
                "Enviarte por correo una contraseña temporal cuando pidas recuperar tu acceso.",
                "Proteger tu cuenta: bloqueo temporal por intentos fallidos y bitácora de accesos.",
                "En el caso de empleados, registrar las ventas y cortes de caja que realizan.",
                "Estas finalidades son necesarias para darte el servicio. No usamos tus datos "
                "para publicidad ni para fines distintos sin pedirte de nuevo tu consentimiento.",
            ],
        ),
        (
            "Con quién los compartimos",
            [
                "No transferimos tus datos personales a terceros.",
                "La base de datos se aloja en Railway (servicio en la nube) y los correos se envían "
                "a través de Gmail. Estos proveedores solo guardan o transmiten la información "
                "por cuenta nuestra y no pueden usarla para sus propios fines.",
            ],
        ),
        (
            "Tus derechos ARCO",
            [
                "Puedes acceder a tus datos, rectificarlos, cancelarlos u oponerte a su uso, "
                "así como revocar tu consentimiento, " + _medio_arco() + ".",
                "Indica tu nombre de usuario, el derecho que quieres ejercer y un medio para "
                "responderte. Te contestaremos dentro de los plazos que marca la ley.",
                "Si consideras que no atendimos tu solicitud, puedes acudir a la Secretaría "
                "Anticorrupción y Buen Gobierno, autoridad en materia de protección de datos.",
            ],
        ),
        (
            "Cuánto tiempo los conservamos",
            [
                "Mientras tu cuenta esté activa. Al cancelarla, eliminamos tus datos salvo los "
                "registros de ventas que deban conservarse para la contabilidad del local.",
            ],
        ),
        (
            "Cambios a este aviso",
            [
                "Cualquier cambio se mostrará en la aplicación antes de que surta efecto. "
                f"Versión {VERSION_AVISO}, {FECHA_AVISO}.",
            ],
        ),
    ]


# ------------------------------------------------------------
# Consentimiento
# ------------------------------------------------------------
def mensaje_si_no_acepta(aceptado: bool) -> str | None:
    """Devuelve el error a mostrar si no se marco la casilla, o None."""
    if aceptado is True:
        return None
    return "Debes aceptar el aviso de privacidad para crear tu cuenta."


def registrar_consentimiento(cursor, id_usuario: int, origen: str) -> bool:
    """Guarda que el usuario acepto el aviso vigente.

    Recibe el cursor de la transaccion del registro para que el
    consentimiento y la cuenta se guarden juntos (o ninguno).

    Devuelve False sin interrumpir el registro si la tabla aun no
    existe (falta aplicar recursos/sql/migracion_privacidad.sql).
    Cualquier otro error se propaga para que el registro haga rollback.
    """
    if origen not in ORIGENES_VALIDOS:
        raise ValueError(f"Origen de consentimiento no valido: {origen}")

    try:
        cursor.execute(
            "INSERT INTO consentimiento_privacidad "
            "(Usuario_IdUsuario, VersionAviso, Origen) VALUES (%s, %s, %s)",
            (int(id_usuario), VERSION_AVISO, origen),
        )
    except Exception as exc:
        if getattr(exc, "errno", None) == _ERROR_TABLA_INEXISTENTE:
            return False
        raise
    return True