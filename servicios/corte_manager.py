from datetime import datetime, date
from configuracion.base_datos import get_connection

def abrir_corte(id_empleado: int) -> int:
    now = datetime.now()
    cols = _cortecaja_cols()

    col_h_ini = _pick(cols, ["Hora_Inicio", "HoraInicio"])
    col_h_fin = _pick(cols, ["Hora_Terminar", "Hora_Termino", "HoraFin"])
    col_f_ini = _pick(cols, ["Fecha_Inicio", "Fecha_Inico", "FechaInicio"])
    col_f_fin = _pick(cols, ["FechaFinalizar", "Fecha_Fin", "FechaFin"])
    col_admin = _pick(cols, ["Administrador_idAdministrador", "AdministradorId", "Empleado_idEmpleado"])

    # estas normalmente sí están así
    col_dinero = _pick(cols, ["DineroEnCaja"])
    col_ing = _pick(cols, ["IngresoDia"])
    col_egr = _pick(cols, ["EgresoDIa", "EgresoDia"])
    col_plat = _pick(cols, ["PlatillosVendidos"])
    col_dfin = _pick(cols, ["DineroFinalizar"])
    col_tiempo = _pick(cols, ["TiempoTrascurrido"])

    conn = get_connection()
    cur = conn.cursor()

    sql = f"""
    INSERT INTO cortecaja
    ({col_h_ini}, {col_h_fin}, {col_f_ini}, {col_dinero}, {col_ing}, {col_egr},
     {col_plat}, {col_dfin}, {col_tiempo}, {col_f_fin}, {col_admin})
    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """

    cur.execute(
        sql,
        (
            now.strftime("%H:%M:%S"),
            "00:00",                  # corte abierto
            now.strftime("%Y-%m-%d"), # varchar o date, MySQL lo acepta
            0.0, 0.0, 0.0,
            0, 0.0, 0,
            date.today(),
            int(id_empleado),
        ),
    )

    conn.commit()
    cid = cur.lastrowid
    cur.close()
    conn.close()
    return int(cid)


def _cortecaja_cols():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SHOW COLUMNS FROM cortecaja")
    cols = {r[0] for r in cur.fetchall()}
    cur.close()
    conn.close()
    return cols

def _pick(cols, candidates):
    for c in candidates:
        if c in cols:
            return c
    raise KeyError(f"No encontré columnas esperadas: {candidates}. Disponibles: {sorted(cols)}")


def obtener_info_corte(corte_id: int):
    conn = get_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute(
        """
        SELECT idCorteCaja, Hora_Inicio, Hora_Terminar, Fecha_Inicio, DineroEnCaja,
               IngresoDia, EgresoDIa, PlatillosVendidos, DineroFinalizar, TiempoTrascurrido,
               FechaFinalizar, Administrador_idAdministrador
        FROM cortecaja
        WHERE idCorteCaja=%s
        """,
        (corte_id,),
    )
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row


def resumen_por_corte(corte_id: int):
    """
    Ingresos: sumatoria de detalleventas.Total por ventas.CorteCaja_idCorteCaja
    Egresos: sumatoria de ingresos_egresos.Monto donde TipoMovimiento='Egreso' en la fecha del corte
            (tu tabla ingresos_egresos NO tiene CorteCaja_idCorteCaja)
    """
    info = obtener_info_corte(corte_id)
    fecha = info["Fecha_Inicio"] if info else None  # varchar(10) 'YYYY-MM-DD'

    conn = get_connection()
    cur = conn.cursor(dictionary=True)

    # Ingresos por ventas
    cur.execute(
        """
        SELECT COALESCE(SUM(d.Total), 0) AS ingresos, COUNT(*) AS platillos
        FROM ventas v
        JOIN detalleventas d ON d.Ventas_IdVentas = v.IdVentas
        WHERE v.CorteCaja_idCorteCaja = %s
        """,
        (corte_id,),
    )
    r1 = cur.fetchone() or {"ingresos": 0, "platillos": 0}
    ingresos = float(r1["ingresos"] or 0)
    platillos = int(r1["platillos"] or 0)

    # Egresos por día (porque no hay corte_id en ingresos_egresos)
    if fecha:
        cur.execute(
            """
            SELECT COALESCE(SUM(Monto), 0) AS egresos, COUNT(*) AS movimientos
            FROM ingresos_egresos
            WHERE LOWER(TipoMovimiento)='egreso' AND Fecha = %s
            """,
            (fecha,),
        )
    else:
        cur.execute(
            """
            SELECT 0 AS egresos, 0 AS movimientos
            """
        )

    r2 = cur.fetchone() or {"egresos": 0, "movimientos": 0}
    egresos = float(r2["egresos"] or 0)
    movs = int(r2["movimientos"] or 0)

    cur.close()
    conn.close()

    balance = ingresos - egresos
    return ingresos, egresos, balance, movs, platillos


def cerrar_corte(corte_id: int):
    """
    Cierra el corte actual actualizando:
    Hora_Terminar, FechaFinalizar, IngresoDia, EgresoDIa, PlatillosVendidos, DineroFinalizar, TiempoTrascurrido
    """
    info = obtener_info_corte(corte_id)
    if not info:
        return

    now = datetime.now()
    ingresos, egresos, balance, _movs, platillos = resumen_por_corte(corte_id)

    # tiempo transcurrido (minutos)
    try:
        h_ini = datetime.strptime(info["Hora_Inicio"], "%H:%M:%S")
        h_fin = datetime.strptime(now.strftime("%H:%M:%S"), "%H:%M:%S")
        minutos = int((h_fin - h_ini).total_seconds() // 60)
        if minutos < 0:
            minutos = 0
    except Exception:
        minutos = 0

    dinero_en_caja = float(info.get("DineroEnCaja") or 0)
    dinero_final = dinero_en_caja + balance

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE cortecaja
        SET Hora_Terminar=%s,
            FechaFinalizar=%s,
            IngresoDia=%s,
            EgresoDIa=%s,
            PlatillosVendidos=%s,
            DineroFinalizar=%s,
            TiempoTrascurrido=%s
        WHERE idCorteCaja=%s
        """,
        (
            now.strftime("%H:%M:%S"),
            now.date(),
            ingresos,
            egresos,
            platillos,
            dinero_final,
            minutos,
            corte_id,
        ),
    )
    conn.commit()
    cur.close()
    conn.close()
