"""
servicios/servicio_autenticacion.py
-----------------------------------
Toda la logica de inicio de sesion del sistema en un solo lugar.

Reemplaza la consulta anterior del tipo:

    SELECT * FROM usuario
     WHERE NombreUsuario = %s AND Contraseña = %s

que aceptaba tanto texto plano como hash y era vulnerable.
Ahora el usuario se busca por nombre y la contrasena se compara
en memoria contra el hash, con:

  * hashing PBKDF2-SHA256 con sal por usuario
  * migracion transparente de los registros antiguos al iniciar sesion
  * bloqueo temporal tras varios intentos fallidos
  * bitacora de intentos en la tabla intentos_login
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from configuracion.base_datos import cursor_bd
from configuracion.variables import (
    ROLES_VALIDOS,
    ROL_CLIENTE,
    SEG_INTENTOS_MAXIMOS,
    SEG_VENTANA_MINUTOS,
    SEG_MINUTOS_BLOQUEO,
)
from servicios import servicio_seguridad as seguridad

# La columna lleva ñ: se referencia siempre entre acentos graves.
_COL_PASS = "`Contraseña`"


# ------------------------------------------------------------
# Resultados
# ------------------------------------------------------------
@dataclass
class Usuario:
    id: int
    nombre_usuario: str
    rol: str
    requiere_cambio: bool = False
    nombre_completo: str = ""
    correo: str = ""

    @property
    def es_admin(self) -> bool:
        return self.rol.upper() == "ADMIN"

    @property
    def es_empleado(self) -> bool:
        return self.rol.upper() == "EMPLEADO"

    @property
    def es_cliente(self) -> bool:
        return self.rol.upper() == "CLIENTE"


@dataclass
class ResultadoLogin:
    exito: bool
    mensaje: str = ""
    usuario: Usuario | None = None
    motivo: str = ""
    minutos_restantes: int = 0
    intentos_restantes: int = 0
    detalles: dict = field(default_factory=dict)

    def __bool__(self) -> bool:
        return self.exito


class ErrorAutenticacion(Exception):
    """Error controlado de la capa de autenticacion."""


# ------------------------------------------------------------
# Bitacora de intentos y bloqueo
# ------------------------------------------------------------
def _registrar_intento(nombre_usuario: str, exitoso: bool, motivo: str = "", origen: str = "app") -> None:
    try:
        with cursor_bd(diccionario=False, commit=True) as cur:
            cur.execute(
                "INSERT INTO intentos_login (NombreUsuario, Exitoso, Motivo, Origen) "
                "VALUES (%s, %s, %s, %s)",
                (str(nombre_usuario)[:45], 1 if exitoso else 0, motivo[:60], origen[:45]),
            )
    except Exception:
        # La bitacora nunca debe impedir el inicio de sesion.
        pass


def _limpiar_intentos(nombre_usuario: str) -> None:
    try:
        with cursor_bd(diccionario=False, commit=True) as cur:
            cur.execute(
                "DELETE FROM intentos_login WHERE NombreUsuario = %s AND Exitoso = 0",
                (nombre_usuario,),
            )
    except Exception:
        pass


def estado_bloqueo(nombre_usuario: str) -> tuple[bool, int, int]:
    """Devuelve (bloqueado, minutos_restantes, intentos_restantes)."""
    maximos = int(SEG_INTENTOS_MAXIMOS)
    ventana = int(SEG_VENTANA_MINUTOS)
    bloqueo = int(SEG_MINUTOS_BLOQUEO)
    desde = datetime.now() - timedelta(minutes=ventana)

    try:
        with cursor_bd() as cur:
            cur.execute(
                "SELECT COUNT(*) AS fallidos, MAX(FechaIntento) AS ultimo "
                "FROM intentos_login "
                "WHERE NombreUsuario = %s AND Exitoso = 0 AND FechaIntento >= %s",
                (nombre_usuario, desde),
            )
            fila = cur.fetchone() or {}
    except Exception:
        return False, 0, maximos

    fallidos = int(fila.get("fallidos") or 0)
    ultimo = fila.get("ultimo")

    if fallidos < maximos:
        return False, 0, max(maximos - fallidos, 0)

    if not isinstance(ultimo, datetime):
        return True, bloqueo, 0

    liberacion = ultimo + timedelta(minutes=bloqueo)
    if datetime.now() >= liberacion:
        _limpiar_intentos(nombre_usuario)
        return False, 0, maximos

    restantes = int((liberacion - datetime.now()).total_seconds() // 60) + 1
    return True, restantes, 0


# ------------------------------------------------------------
# Consultas de apoyo
# ------------------------------------------------------------
def _columnas_usuario() -> set:
    """Detecta que columnas opcionales existen ya en la tabla usuario,
    para que el codigo funcione con o sin la migracion aplicada."""
    try:
        with cursor_bd() as cur:
            cur.execute("SHOW COLUMNS FROM usuario")
            return {str(f.get("Field")) for f in cur.fetchall()}
    except Exception:
        return {"IdUsuario", "NombreUsuario", "Contraseña", "Rol"}


def _buscar_usuario(nombre_usuario: str) -> dict | None:
    with cursor_bd() as cur:
        cur.execute(
            f"SELECT IdUsuario, NombreUsuario, {_COL_PASS} AS Password, Rol "
            "FROM usuario WHERE NombreUsuario = %s LIMIT 1",
            (nombre_usuario,),
        )
        return cur.fetchone()


def _datos_persona(id_usuario: int) -> tuple[str, str]:
    """Devuelve (nombre_completo, correo) buscando en empleado y cliente."""
    for tabla in ("empleado", "cliente"):
        try:
            with cursor_bd() as cur:
                cur.execute(
                    f"SELECT Nombre, Apellido, Correo FROM {tabla} "
                    "WHERE Usuario_IdUsuario = %s LIMIT 1",
                    (id_usuario,),
                )
                fila = cur.fetchone()
            if fila:
                nombre = f"{fila.get('Nombre', '')} {fila.get('Apellido', '')}".strip()
                return nombre, str(fila.get("Correo") or "")
        except Exception:
            continue
    return "", ""


def _actualizar_hash(id_usuario: int, contrasena_clara: str) -> None:
    """Re-hashea con PBKDF2 aprovechando un inicio de sesion valido."""
    try:
        nuevo = seguridad.hashear(contrasena_clara)
        with cursor_bd(diccionario=False, commit=True) as cur:
            cur.execute(
                f"UPDATE usuario SET {_COL_PASS} = %s WHERE IdUsuario = %s",
                (nuevo, id_usuario),
            )
    except Exception:
        # Si falla la migracion el usuario igual entra; se reintenta la proxima vez.
        pass


def _requiere_cambio(id_usuario: int, columnas: set) -> bool:
    if "RequiereCambio" not in columnas:
        return False
    try:
        with cursor_bd() as cur:
            cur.execute(
                "SELECT RequiereCambio FROM usuario WHERE IdUsuario = %s",
                (id_usuario,),
            )
            fila = cur.fetchone() or {}
        return bool(fila.get("RequiereCambio"))
    except Exception:
        return False


def _esta_activo(id_usuario: int, columnas: set) -> bool:
    if "Activo" not in columnas:
        return True
    try:
        with cursor_bd() as cur:
            cur.execute("SELECT Activo FROM usuario WHERE IdUsuario = %s", (id_usuario,))
            fila = cur.fetchone() or {}
        return bool(fila.get("Activo", 1))
    except Exception:
        return True


# ------------------------------------------------------------
# Autenticacion
# ------------------------------------------------------------
def autenticar(nombre_usuario: str, contrasena: str, origen: str = "app") -> ResultadoLogin:
    """Punto de entrada del login.

    Uso en la vista:
        resultado = servicio_autenticacion.autenticar(usuario, password)
        if resultado.exito:
            ir_a_menu(resultado.usuario)
        else:
            mostrar_error(resultado.mensaje)
    """
    nombre_usuario = (nombre_usuario or "").strip()
    contrasena = contrasena or ""

    if not nombre_usuario or not contrasena:
        return ResultadoLogin(
            False,
            "Escribe tu usuario y tu contrasena.",
            motivo="campos_vacios",
        )

    bloqueado, minutos, intentos_restantes = estado_bloqueo(nombre_usuario)
    if bloqueado:
        return ResultadoLogin(
            False,
            f"Cuenta bloqueada temporalmente por seguridad. "
            f"Intenta de nuevo en {minutos} minuto(s).",
            motivo="bloqueado",
            minutos_restantes=minutos,
        )

    try:
        fila = _buscar_usuario(nombre_usuario)
    except Exception as exc:
        return ResultadoLogin(
            False,
            "No se pudo contactar la base de datos. Revisa tu conexion.",
            motivo="error_conexion",
            detalles={"error": str(exc)},
        )

    if not fila:
        # Se calcula un hash falso para que el tiempo de respuesta sea
        # similar al de un usuario existente (evita enumerar usuarios).
        seguridad.verificar(contrasena, seguridad.hashear("valor_inexistente"))
        _registrar_intento(nombre_usuario, False, "usuario_inexistente", origen)
        _, _, restantes = estado_bloqueo(nombre_usuario)
        return ResultadoLogin(
            False,
            "Usuario o contrasena incorrectos.",
            motivo="credenciales_invalidas",
            intentos_restantes=restantes,
        )

    verificacion = seguridad.verificar(contrasena, fila.get("Password"))

    if not verificacion.valida:
        _registrar_intento(nombre_usuario, False, "password_incorrecta", origen)
        _, minutos, restantes = estado_bloqueo(nombre_usuario)
        mensaje = "Usuario o contrasena incorrectos."
        if 0 < restantes <= 2:
            mensaje += f" Te quedan {restantes} intento(s) antes del bloqueo."
        return ResultadoLogin(
            False,
            mensaje,
            motivo="credenciales_invalidas",
            intentos_restantes=restantes,
            minutos_restantes=minutos,
        )

    columnas = _columnas_usuario()
    id_usuario = int(fila["IdUsuario"])

    if not _esta_activo(id_usuario, columnas):
        _registrar_intento(nombre_usuario, False, "cuenta_inactiva", origen)
        return ResultadoLogin(
            False,
            "Esta cuenta esta desactivada. Contacta al administrador.",
            motivo="inactiva",
        )

    # Migracion transparente del formato antiguo
    if verificacion.requiere_rehash:
        _actualizar_hash(id_usuario, contrasena)

    nombre_completo, correo = _datos_persona(id_usuario)

    usuario = Usuario(
        id=id_usuario,
        nombre_usuario=str(fila["NombreUsuario"]),
        rol=str(fila.get("Rol") or ROL_CLIENTE).upper(),
        requiere_cambio=_requiere_cambio(id_usuario, columnas),
        nombre_completo=nombre_completo,
        correo=correo,
    )

    _limpiar_intentos(nombre_usuario)
    _registrar_intento(nombre_usuario, True, "ok", origen)

    return ResultadoLogin(
        True,
        f"Bienvenido, {usuario.nombre_completo or usuario.nombre_usuario}.",
        usuario=usuario,
        motivo="ok",
        detalles={"formato_previo": verificacion.formato},
    )


# ------------------------------------------------------------
# Alta y mantenimiento de cuentas
# ------------------------------------------------------------
def existe_usuario(nombre_usuario: str) -> bool:
    try:
        with cursor_bd() as cur:
            cur.execute(
                "SELECT 1 FROM usuario WHERE NombreUsuario = %s LIMIT 1",
                ((nombre_usuario or "").strip(),),
            )
            return cur.fetchone() is not None
    except Exception:
        return False


def crear_usuario(
    nombre_usuario: str,
    contrasena: str,
    rol: str = ROL_CLIENTE,
    requiere_cambio: bool = False,
) -> int:
    """Crea un usuario con la contrasena ya hasheada. Devuelve el IdUsuario."""
    nombre_usuario = (nombre_usuario or "").strip()
    rol = (rol or ROL_CLIENTE).upper()

    if not nombre_usuario:
        raise ErrorAutenticacion("El nombre de usuario no puede estar vacio.")
    if len(nombre_usuario) > 45:
        raise ErrorAutenticacion("El nombre de usuario excede 45 caracteres.")
    if rol not in ROLES_VALIDOS:
        raise ErrorAutenticacion(f"Rol no valido: {rol}.")

    politica = seguridad.validar_fortaleza(contrasena, nombre_usuario)
    if not politica.valida:
        raise ErrorAutenticacion(politica.mensaje)

    if existe_usuario(nombre_usuario):
        raise ErrorAutenticacion("Ese nombre de usuario ya esta registrado.")

    columnas = _columnas_usuario()
    campos = ["NombreUsuario", "Contraseña", "Rol"]
    valores = [nombre_usuario, seguridad.hashear(contrasena), rol]

    if "RequiereCambio" in columnas:
        campos.append("RequiereCambio")
        valores.append(1 if requiere_cambio else 0)
    if "FechaCambioPassword" in columnas:
        campos.append("FechaCambioPassword")
        valores.append(datetime.now())

    lista_campos = ", ".join(f"`{c}`" for c in campos)
    marcadores = ", ".join(["%s"] * len(valores))

    with cursor_bd(diccionario=False, commit=True) as cur:
        cur.execute(
            f"INSERT INTO usuario ({lista_campos}) VALUES ({marcadores})",
            tuple(valores),
        )
        return int(cur.lastrowid)


def cambiar_contrasena(
    id_usuario: int,
    contrasena_actual: str,
    contrasena_nueva: str,
) -> ResultadoLogin:
    """Cambio de contrasena verificando la anterior."""
    with cursor_bd() as cur:
        cur.execute(
            f"SELECT NombreUsuario, {_COL_PASS} AS Password FROM usuario "
            "WHERE IdUsuario = %s LIMIT 1",
            (id_usuario,),
        )
        fila = cur.fetchone()

    if not fila:
        return ResultadoLogin(False, "El usuario no existe.", motivo="inexistente")

    if not seguridad.verificar(contrasena_actual, fila["Password"]).valida:
        return ResultadoLogin(False, "La contrasena actual no es correcta.", motivo="password_incorrecta")

    if contrasena_actual == contrasena_nueva:
        return ResultadoLogin(False, "La nueva contrasena debe ser distinta a la actual.", motivo="repetida")

    politica = seguridad.validar_fortaleza(contrasena_nueva, fila["NombreUsuario"])
    if not politica.valida:
        return ResultadoLogin(False, politica.mensaje, motivo="politica")

    _guardar_password(id_usuario, contrasena_nueva, requiere_cambio=False)
    return ResultadoLogin(True, "Contrasena actualizada correctamente.", motivo="ok")


def restablecer_contrasena(id_usuario: int, contrasena_nueva: str, forzar_cambio: bool = True) -> None:
    """Restablecimiento hecho por un administrador (sin pedir la anterior)."""
    politica = seguridad.validar_fortaleza(contrasena_nueva)
    if not politica.valida:
        raise ErrorAutenticacion(politica.mensaje)
    _guardar_password(id_usuario, contrasena_nueva, requiere_cambio=forzar_cambio)


def _guardar_password(id_usuario: int, contrasena: str, requiere_cambio: bool) -> None:
    columnas = _columnas_usuario()
    asignaciones = [f"{_COL_PASS} = %s"]
    valores = [seguridad.hashear(contrasena)]

    if "RequiereCambio" in columnas:
        asignaciones.append("`RequiereCambio` = %s")
        valores.append(1 if requiere_cambio else 0)
    if "FechaCambioPassword" in columnas:
        asignaciones.append("`FechaCambioPassword` = %s")
        valores.append(datetime.now())

    valores.append(id_usuario)

    with cursor_bd(diccionario=False, commit=True) as cur:
        cur.execute(
            f"UPDATE usuario SET {', '.join(asignaciones)} WHERE IdUsuario = %s",
            tuple(valores),
        )


def desbloquear_usuario(nombre_usuario: str) -> None:
    """Accion manual del administrador para liberar una cuenta bloqueada."""
    _limpiar_intentos((nombre_usuario or "").strip())


def historial_intentos(nombre_usuario: str = "", limite: int = 50) -> list:
    """Bitacora para el modulo de auditoria del administrador."""
    sql = (
        "SELECT NombreUsuario, Exitoso, Motivo, Origen, FechaIntento "
        "FROM intentos_login "
    )
    parametros: tuple = ()
    if nombre_usuario:
        sql += "WHERE NombreUsuario = %s "
        parametros = (nombre_usuario,)
    sql += "ORDER BY FechaIntento DESC LIMIT %s"
    parametros = parametros + (int(limite),)

    try:
        with cursor_bd() as cur:
            cur.execute(sql, parametros)
            return cur.fetchall()
    except Exception:
        return []


def auditar_contrasenas() -> list:
    """Lista el estado del hash de cada usuario (reporte de seguridad)."""
    try:
        with cursor_bd() as cur:
            cur.execute(
                f"SELECT IdUsuario, NombreUsuario, Rol, {_COL_PASS} AS Password FROM usuario"
            )
            filas = cur.fetchall()
    except Exception:
        return []

    reporte = []
    for fila in filas:
        reporte.append(
            {
                "IdUsuario": fila["IdUsuario"],
                "NombreUsuario": fila["NombreUsuario"],
                "Rol": fila["Rol"],
                "Estado": seguridad.describir_formato(fila.get("Password")),
                "Seguro": seguridad.es_formato_seguro(fila.get("Password")),
            }
        )
    return reporte


# ------------------------------------------------------------
# Solicitudes de recuperacion de contrasena
# ------------------------------------------------------------
def registrar_solicitud(nombre_usuario: str, correo: str, tipo_cuenta: str = "cliente") -> int:
    """Registra una solicitud de restablecimiento (tabla solicitudes_password)."""
    nombre_usuario = (nombre_usuario or "").strip()

    with cursor_bd() as cur:
        cur.execute(
            "SELECT IdUsuario FROM usuario WHERE NombreUsuario = %s LIMIT 1",
            (nombre_usuario,),
        )
        fila = cur.fetchone()

    if not fila:
        raise ErrorAutenticacion("No existe una cuenta con ese nombre de usuario.")

    tipo = tipo_cuenta if tipo_cuenta in ("cliente", "empleado") else "cliente"

    with cursor_bd(diccionario=False, commit=True) as cur:
        cur.execute(
            "INSERT INTO solicitudes_password "
            "(IdUsuario, NombreUsuario, TipoCuenta, Correo, Estado) "
            "VALUES (%s, %s, %s, %s, 'Pendiente')",
            (int(fila["IdUsuario"]), nombre_usuario, tipo, (correo or "").strip()),
        )
        return int(cur.lastrowid)


def atender_solicitud(id_solicitud: int) -> tuple[str, str, str]:
    """Genera una contrasena temporal, la aplica y marca la solicitud.

    Devuelve (nombre_usuario, correo, contrasena_temporal_en_claro)
    para que la capa de correo la envie. La contrasena en claro NO se
    almacena en la base de datos: solo se guarda su hash.
    """
    with cursor_bd() as cur:
        cur.execute(
            "SELECT IdUsuario, NombreUsuario, Correo FROM solicitudes_password "
            "WHERE IdSolicitud = %s LIMIT 1",
            (id_solicitud,),
        )
        fila = cur.fetchone()

    if not fila:
        raise ErrorAutenticacion("La solicitud no existe.")

    temporal = seguridad.generar_contrasena_temporal()
    _guardar_password(int(fila["IdUsuario"]), temporal, requiere_cambio=True)

    with cursor_bd(diccionario=False, commit=True) as cur:
        cur.execute(
            "UPDATE solicitudes_password "
            "SET Estado = 'Atendida', PasswordTemporal = %s, FechaAtencion = %s "
            "WHERE IdSolicitud = %s",
            (seguridad.hashear(temporal), datetime.now(), id_solicitud),
        )

    return str(fila["NombreUsuario"]), str(fila.get("Correo") or ""), temporal