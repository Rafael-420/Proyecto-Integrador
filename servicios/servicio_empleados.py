from configuracion.base_datos import get_connection


def obtener_empleado_por_id(id_empleado):

    conn = None
    cursor = None

    try:
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
                u.NombreUsuario
            FROM empleado e
            INNER JOIN usuario u
                ON u.IdUsuario = e.Usuario_IdUsuario
            WHERE e.IdEmpleado = %s
            """,
            (int(id_empleado),),
        )

        return cursor.fetchone()

    finally:
        try:
            if cursor:
                cursor.close()

            if conn:
                conn.close()

        except:
            pass


def actualizar_empleado_perfil(
    id_empleado,
    nombre,
    apellido,
    telefono,
    correo,
):

    conn = None
    cursor = None

    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            UPDATE empleado
            SET
                Nombre=%s,
                Apellido=%s,
                Telefono=%s,
                Correo=%s
            WHERE IdEmpleado=%s
            """,
            (
                nombre,
                apellido,
                telefono,
                correo,
                int(id_empleado),
            ),
        )

        conn.commit()

    except Exception:

        if conn:
            conn.rollback()

        raise

    finally:

        try:
            if cursor:
                cursor.close()

            if conn:
                conn.close()

        except:
            pass