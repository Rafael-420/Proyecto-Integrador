import flet as ft
import re

# Compatibilidad íconos (Flet nuevo)
if not hasattr(ft, "icons") and hasattr(ft, "Icons"):
    ft.icons = ft.Icons

from configuracion.base_datos import get_connection

# -------------------------------------------------------------------
# HELPERS DE BD  (verificación cruzada empleado + cliente)
# -------------------------------------------------------------------
def _existe_dato_persona(campo: str, valor: str, tabla_excluir: str | None = None, id_excluir=None) -> tuple[bool, str | None]:
    """
    Revisa si `valor` ya existe en el campo `campo` (Telefono | Correo)
    buscando en AMBAS tablas (empleado y cliente).
    tabla_excluir + id_excluir se usan en edición para ignorar el propio registro.
    Retorna (existe: bool, mensaje: str | None).
    """
    if campo not in ("Telefono", "Correo"):
        raise ValueError("Campo no permitido")

    conn = None
    cur = None
    try:
        conn = get_connection()
        cur = conn.cursor(dictionary=True)
        for tabla, pk, label in [
            ("empleado", "IdEmpleado", "empleado"),
            ("cliente",  "IdCliente",  "cliente"),
        ]:
            sql    = f"SELECT {pk} FROM {tabla} WHERE {campo}=%s"
            params = [valor]
            if tabla_excluir == tabla and id_excluir is not None:
                sql   += f" AND {pk}<>%s"
                params.append(int(id_excluir))
            sql += " LIMIT 1"
            cur.execute(sql, tuple(params))
            if cur.fetchone():
                nombre_campo = "teléfono" if campo == "Telefono" else "correo"
                return True, f"Ese {nombre_campo} ya está registrado en {label}"
        return False, None
    finally:
        try:
            if cur:  cur.close()
            if conn: conn.close()
        except Exception:
            pass


def _existe_usuario(nombre_usuario: str, exclude_id_usuario=None) -> bool:
    conn = None
    cur  = None
    try:
        conn = get_connection()
        cur  = conn.cursor()
        if exclude_id_usuario is None:
            cur.execute("SELECT COUNT(*) FROM usuario WHERE NombreUsuario=%s", (nombre_usuario,))
        else:
            cur.execute(
                "SELECT COUNT(*) FROM usuario WHERE NombreUsuario=%s AND IdUsuario<>%s",
                (nombre_usuario, int(exclude_id_usuario)),
            )
        row = cur.fetchone()
        return (row[0] or 0) > 0
    finally:
        try:
            if cur:  cur.close()
            if conn: conn.close()
        except Exception:
            pass


# -------------------------------------------------------------------
# VISTA DE REGISTRO (CLIENTE / EMPLEADO)
# -------------------------------------------------------------------
def RegistroView(page: ft.Page, tipo: str):
    """
    tipo: "Cliente" o "Empleado"
    """

    titulo = f"Registro de {tipo}"

    txt_nombre   = ft.TextField(label="Nombre",              autofocus=True, max_length=30)
    txt_apellido = ft.TextField(label="Apellido",                            max_length=30)
    txt_correo   = ft.TextField(label="Correo electrónico",  hint_text="ejemplo@gmail.com", max_length=60)
    txt_tel      = ft.TextField(label="Teléfono",            max_length=10, keyboard_type=ft.KeyboardType.NUMBER)
    txt_usuario  = ft.TextField(label="Nombre de usuario",   max_length=20)
    txt_pass     = ft.TextField(label="Contraseña",          password=True, can_reveal_password=True)
    txt_pass2    = ft.TextField(label="Confirmar contraseña",password=True, can_reveal_password=True)

    lbl_msg = ft.Text("")

    # ------------------------------------------------------------------
    # LIMPIEZA EN TIEMPO REAL
    # ------------------------------------------------------------------
    def limpiar_en_tiempo_real(e):
        campo = e.control
        if campo in (txt_nombre, txt_apellido):
            campo.value = re.sub(r"[^A-Za-zÁÉÍÓÚáéíóúÑñ\s]", "", campo.value or "")
        elif campo == txt_tel:
            campo.value = re.sub(r"\D", "", campo.value or "")[:10]
        elif campo == txt_usuario:
            campo.value = re.sub(r"[^A-Za-z0-9_]", "", campo.value or "")[:20]
        campo.update()

    txt_nombre.on_change   = limpiar_en_tiempo_real
    txt_apellido.on_change = limpiar_en_tiempo_real
    txt_tel.on_change      = limpiar_en_tiempo_real
    txt_usuario.on_change  = limpiar_en_tiempo_real

    # ------------------------------------------------------------------
    # VALIDACIONES
    # ------------------------------------------------------------------
    PATRON_NOMBRE  = re.compile(r"^[A-Za-zÁÉÍÓÚáéíóúÑñ\s]{2,30}$")
    PATRON_CORREO  = re.compile(r"^[\w\.-]+@(gmail|hotmail|outlook|yahoo)\.com$")
    PATRON_USUARIO = re.compile(r"^[A-Za-z0-9_]{4,20}$")

    def validar_campos() -> bool:
        for campo in [txt_nombre, txt_apellido, txt_correo, txt_tel, txt_usuario, txt_pass, txt_pass2]:
            campo.error_text = None

        nombre   = (txt_nombre.value   or "").strip()
        apellido = (txt_apellido.value or "").strip()
        correo   = (txt_correo.value   or "").strip().lower()
        tel      = (txt_tel.value      or "").strip()
        usuario  = (txt_usuario.value  or "").strip()
        password  = (txt_pass.value    or "").strip()
        password2 = (txt_pass2.value   or "").strip()

        valido = True

        # --- Nombre
        if not PATRON_NOMBRE.match(nombre):
            txt_nombre.error_text = "Solo letras, mínimo 2 y máximo 30 caracteres"
            valido = False

        # --- Apellido
        if not PATRON_NOMBRE.match(apellido):
            txt_apellido.error_text = "Solo letras, mínimo 2 y máximo 30 caracteres"
            valido = False

        # --- Correo (formato + duplicado cruzado)
        if not PATRON_CORREO.match(correo):
            txt_correo.error_text = "Correo inválido. Ejemplo: usuario@gmail.com"
            valido = False
        else:
            try:
                existe, msg_dup = _existe_dato_persona("Correo", correo)
                if existe:
                    txt_correo.error_text = msg_dup
                    valido = False
            except Exception:
                pass  # no bloquear por error de BD

        # --- Teléfono (formato + duplicado cruzado)
        if not tel.isdigit() or len(tel) != 10:
            txt_tel.error_text = "El teléfono debe tener exactamente 10 números"
            valido = False
        else:
            try:
                existe, msg_dup = _existe_dato_persona("Telefono", tel)
                if existe:
                    txt_tel.error_text = msg_dup
                    valido = False
            except Exception:
                pass

        # --- Usuario (formato + duplicado en tabla usuario)
        if not PATRON_USUARIO.match(usuario):
            txt_usuario.error_text = "Usuario de 4 a 20 caracteres, solo letras, números o _"
            valido = False
        # la comprobación de usuario duplicado se hace en registrar() justo antes del INSERT

        # --- Contraseña
        if len(password) < 6:
            txt_pass.error_text = "La contraseña debe tener mínimo 6 caracteres"
            valido = False

        # --- Confirmación
        if password != password2:
            txt_pass2.error_text = "Las contraseñas no coinciden"
            valido = False

        page.update()
        return valido

    # ------------------------------------------------------------------
    # NAVEGACIÓN
    # ------------------------------------------------------------------
    def ir_login():
        from vistas.vista_login import LoginView   # import aquí para evitar ciclo
        page.views.clear()
        page.views.append(LoginView(page))
        page.go("/")
        page.update()

    # ------------------------------------------------------------------
    # REGISTRAR EN LA BD
    # ------------------------------------------------------------------
    def registrar(e):
        if not validar_campos():
            return

        nombre   = txt_nombre.value.strip()
        apellido = txt_apellido.value.strip()
        correo   = txt_correo.value.strip().lower()
        tel      = txt_tel.value.strip()
        usuario  = txt_usuario.value.strip()
        password = txt_pass.value.strip()

        try:
            conn   = get_connection()
            cursor = conn.cursor()

            # Revisar si el usuario ya existe
            cursor.execute("SELECT IdUsuario FROM usuario WHERE NombreUsuario=%s", (usuario,))
            if cursor.fetchone():
                txt_usuario.error_text = "Ese nombre de usuario ya existe"
                page.update()
                return

            # Insertar en usuario
            cursor.execute(
                "INSERT INTO usuario (NombreUsuario, Contraseña) VALUES (%s, %s)",
                (usuario, password),
            )
            id_usuario = cursor.lastrowid

            # Insertar en cliente o empleado
            tabla = "cliente" if tipo == "Cliente" else "empleado"
            cursor.execute(
                f"INSERT INTO {tabla} (Nombre, Apellido, Telefono, Correo, Usuario_IdUsuario) "
                "VALUES (%s, %s, %s, %s, %s)",
                (nombre, apellido, tel, correo, id_usuario),
            )

            conn.commit()

            page.snack_bar       = ft.SnackBar(
                content=ft.Text(f"{tipo} registrado correctamente. Ahora puedes iniciar sesión.")
            )
            page.snack_bar.open  = True
            page.update()

            ir_login()

        except Exception as ex:
            lbl_msg.value = f"Error al registrar: {ex}"
            lbl_msg.color = "red"
            page.update()
        finally:
            try:
                cursor.close()
                conn.close()
            except Exception:
                pass

    def volver_login(e):
        ir_login()

    # ------------------------------------------------------------------
    # LAYOUT
    # ------------------------------------------------------------------
    # --------------------------------------------------------
    # Responsive: ancho fijo de 400px + sin scroll no funcionaba en
    # celular (con 7 campos + botones, el contenido no cabía en la
    # pantalla y no había forma de bajar para llegar al botón).
    # --------------------------------------------------------
    ancho_pagina = getattr(page, "width", None) or 1200
    ancho_form = min(400, ancho_pagina - 32)

    contenido = ft.Container(
        expand=True,
        bgcolor="#F9F6FB",
        alignment=ft.Alignment.CENTER,
        padding=ft.padding.symmetric(horizontal=12, vertical=16),
        content=ft.Column(
            [
                ft.Text("Corallie Bubble", size=26, weight="bold", color="#C86DD7"),
                ft.Text(titulo, size=20),
                txt_nombre,
                txt_apellido,
                txt_correo,
                txt_tel,
                txt_usuario,
                txt_pass,
                txt_pass2,
                ft.ElevatedButton(
                    "Registrarme",
                    bgcolor="#C86DD7",
                    color="white",
                    on_click=registrar,
                ),
                ft.TextButton("Volver al login", on_click=volver_login),
                lbl_msg,
            ],
            spacing=15,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            width=ancho_form,
            scroll=ft.ScrollMode.AUTO,
        ),
    )

    return ft.View(route="/registro", controls=[contenido])
