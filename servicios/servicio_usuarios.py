"""Consultas reutilizables para usuario, empleado y cliente."""

from configuracion.base_datos import get_connection

def existe_usuario(nombre_usuario: str, exclude_id_usuario=None) -> bool:
    conn = get_connection(); cur = conn.cursor()
    try:
        if exclude_id_usuario is None:
            cur.execute("SELECT COUNT(*) FROM usuario WHERE NombreUsuario=%s", (nombre_usuario,))
        else:
            cur.execute("SELECT COUNT(*) FROM usuario WHERE NombreUsuario=%s AND IdUsuario<>%s", (nombre_usuario, int(exclude_id_usuario)))
        return (cur.fetchone()[0] or 0) > 0
    finally:
        cur.close(); conn.close()


def existe_dato_personal(tabla: str, campo: str, valor: str, exclude_id=None) -> bool:
    if tabla not in ("empleado", "cliente") or campo not in ("Telefono", "Correo"):
        raise ValueError("Tabla o campo no permitido")
    pk = "IdEmpleado" if tabla == "empleado" else "IdCliente"
    conn = get_connection(); cur = conn.cursor()
    try:
        if exclude_id is None:
            cur.execute(f"SELECT COUNT(*) FROM {tabla} WHERE {campo}=%s", (valor,))
        else:
            cur.execute(f"SELECT COUNT(*) FROM {tabla} WHERE {campo}=%s AND {pk}<>%s", (valor, int(exclude_id)))
        return (cur.fetchone()[0] or 0) > 0
    finally:
        cur.close(); conn.close()

def obtener_empleado_por_id(id_empleado):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute(
        """
        SELECT 
            e.IdEmpleado,
            e.Nombre,
            e.Apellido,
            e.Telefono,
            e.Correo,
            e.Usuario_IdUsuario,
            u.NombreUsuario
        FROM empleado e
        INNER JOIN usuario u ON u.IdUsuario = e.Usuario_IdUsuario
        WHERE e.IdEmpleado = %s
        """,
        (id_empleado,),
    )

    empleado = cursor.fetchone()

    cursor.close()
    conn.close()

    return empleado


def actualizar_empleado_perfil(id_empleado, nombre, apellido, telefono, correo):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        UPDATE empleado
        SET Nombre=%s, Apellido=%s, Telefono=%s, Correo=%s
        WHERE IdEmpleado=%s
        """,
        (nombre, apellido, telefono, correo, id_empleado),
    )

    conn.commit()

    cursor.close()
    conn.close()