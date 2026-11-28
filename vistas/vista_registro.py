import flet as ft
import re
from pathlib import Path

# Compatibilidad íconos (Flet nuevo)
if not hasattr(ft, "icons") and hasattr(ft, "Icons"):
    ft.icons = ft.Icons

from configuracion.base_datos import get_connection
from configuracion.variables import ROL_CLIENTE, ROL_EMPLEADO
from servicios import servicio_privacidad as privacidad
from servicios import servicio_seguridad as seguridad
from componentes.dialogo_aviso_privacidad import mostrar_aviso_privacidad
from utilidades.flet_compat import set_error, snack


# -------------------------------------------------------------------
# APARIENCIA (misma línea visual que el login)
# -------------------------------------------------------------------
# Paleta y fuentes copiadas de vistas/vista_login.py. No se importan de
# ahí porque vista_login importa esta vista y se haría un ciclo.
COLOR_FONDO = "#F7F1F8"
COLOR_CARD = "#FBF8FD"
COLOR_MORADO = "#A45CE0"
COLOR_MORADO_CLARO = "#C88CF4"
COLOR_ROSA = "#F65FAE"
COLOR_TEXTO = "#5E5575"
COLOR_PLACEHOLDER = "#958BA8"
COLOR_INPUT_BG = "#FCFAFE"
COLOR_INPUT_BORDER = "#B879F0"
COLOR_ICON_BG = "#EFE6F8"
COLOR_DECOR = "#D3A7F1"
COLOR_ERROR = "#D32F2F"
COLOR_GRIS = "#6B7280"

FUENTE = "Fredoka"            # registradas en main.py (page.fonts)
FUENTE_TITULO = "PliantBlack"

ALIGN_CENTER = (
    getattr(getattr(ft, "alignment", None), "center", None)
    or getattr(getattr(ft, "Alignment", None), "CENTER", None)
)


def _icon(*names):
    """Obtiene íconos compatibles entre versiones de Flet."""
    for name in names:
        for modulo in (getattr(ft, "icons", None), getattr(ft, "Icons", None)):
            value = getattr(modulo, name, None) if modulo is not None else None
            if value is not None:
                return value
    return None


ICON_PERSONA = _icon("PERSON_OUTLINE", "PERSON")
ICON_CORREO = _icon("MAIL_OUTLINE", "EMAIL")
ICON_TELEFONO = _icon("PHONE_OUTLINED", "PHONE")
ICON_USUARIO = _icon("ACCOUNT_CIRCLE_OUTLINED", "ACCOUNT_CIRCLE")
ICON_CANDADO = _icon("LOCK_OUTLINE", "LOCK")
ICON_REGISTRAR = _icon("PERSON_ADD_ALT_1", "PERSON_ADD")
ICON_VOLVER = _icon("ARROW_BACK", "CHEVRON_LEFT")


def _img(nombre_limpio: str, nombre_original: str | None = None) -> str:
    """Imagen decorativa de assets/login (mismos archivos que el login)."""
    base = Path(__file__).parent.parent / "assets" / "login"
    for nombre in (nombre_limpio, nombre_original):
        if nombre and (base / nombre).exists():
            return f"login/{nombre}"
    return f"login/{nombre_limpio}"


def _campo(label: str, icono, **opciones) -> ft.TextField:
    """Campo con el estilo de píldora del login, pero con etiqueta y
    mensaje de error debajo (el login no los necesita, el registro sí)."""
    return ft.TextField(
        label=label,
        prefix_icon=ft.Icon(icono, color=COLOR_MORADO, size=22) if icono is not None else None,
        border_radius=28,
        border_color=COLOR_INPUT_BORDER,
        focused_border_color=COLOR_MORADO,
        border_width=1.6,
        focused_border_width=2.2,
        filled=True,
        fill_color=COLOR_INPUT_BG,
        cursor_color=COLOR_MORADO,
        text_style=ft.TextStyle(font_family=FUENTE, size=16, color=COLOR_TEXTO),
        label_style=ft.TextStyle(font_family=FUENTE, size=15, color=COLOR_PLACEHOLDER),
        hint_style=ft.TextStyle(font_family=FUENTE, size=15, color=COLOR_PLACEHOLDER),
        error_style=ft.TextStyle(font_family=FUENTE, size=12, color=COLOR_ERROR),
        counter_style=ft.TextStyle(font_family=FUENTE, size=11, color=COLOR_PLACEHOLDER),
        **opciones,
    )

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

    txt_nombre   = _campo("Nombre",               ICON_PERSONA,  autofocus=True, max_length=30)
    txt_apellido = _campo("Apellido",             ICON_PERSONA,  max_length=30)
    txt_correo   = _campo("Correo electrónico",   ICON_CORREO,   hint_text="ejemplo@gmail.com", max_length=60,
                          keyboard_type=ft.KeyboardType.EMAIL)
    txt_tel      = _campo("Teléfono",             ICON_TELEFONO, max_length=10, keyboard_type=ft.KeyboardType.NUMBER)
    txt_usuario  = _campo("Nombre de usuario",    ICON_USUARIO,  max_length=20)
    txt_pass     = _campo("Contraseña",           ICON_CANDADO,  password=True, can_reveal_password=True)
    txt_pass2    = _campo("Confirmar contraseña", ICON_CANDADO,  password=True, can_reveal_password=True)

    # Los mensajes de error (sobre todo el de la contraseña) son largos;
    # sin esto se cortaban con "..." en el celular.
    for campo in (txt_nombre, txt_apellido, txt_correo, txt_tel, txt_usuario, txt_pass, txt_pass2):
        campo.error_max_lines = 3

    # Mensaje general junto al botón. En el celular los campos con error
    # pueden quedar fuera de la pantalla; este aviso sí se ve.
    lbl_msg = ft.Text("", size=13, text_align=ft.TextAlign.CENTER, font_family=FUENTE)

    # ------------------------------------------------------------------
    # AVISO DE PRIVACIDAD (LFPDPPP)
    # La casilla es obligatoria: sin consentimiento no se crea la cuenta.
    # ------------------------------------------------------------------
    chk_privacidad = ft.Checkbox(value=False, active_color=COLOR_MORADO)
    lbl_error_privacidad = ft.Text("", size=12, color=COLOR_ERROR, visible=False, font_family=FUENTE)

    def alternar_privacidad(e):
        chk_privacidad.value = not chk_privacidad.value
        limpiar_error_privacidad(None)

    def limpiar_error_privacidad(e):
        if chk_privacidad.value:
            lbl_error_privacidad.visible = False
        page.update()

    chk_privacidad.on_change = limpiar_error_privacidad

    bloque_privacidad = ft.Container(
        bgcolor=COLOR_ICON_BG,
        border_radius=22,
        padding=ft.padding.only(left=16, right=16, top=14, bottom=10),
        content=ft.Column(
            [
                ft.Text(
                    privacidad.texto_simplificado(),
                    size=12,
                    color=COLOR_TEXTO,
                    font_family=FUENTE,
                ),
                ft.Row(
                    [
                        chk_privacidad,
                        ft.Container(
                            content=ft.Text(
                                "He leído y acepto el aviso de privacidad",
                                size=14,
                                color=COLOR_TEXTO,
                                font_family=FUENTE,
                            ),
                            expand=True,
                            on_click=alternar_privacidad,
                        ),
                    ],
                    spacing=4,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Container(
                    padding=ft.padding.only(left=6, bottom=4),
                    on_click=lambda e: mostrar_aviso_privacidad(page),
                    content=ft.Text(
                        "Leer el aviso de privacidad completo",
                        size=13,
                        color=COLOR_MORADO,
                        weight=ft.FontWeight.BOLD,
                        font_family=FUENTE,
                    ),
                ),
                lbl_error_privacidad,
            ],
            spacing=4,
        ),
    )

    # Botón con la misma forma que "Iniciar sesión" del login.
    contenido_boton = ft.Row(
        [
            ft.Icon(ICON_REGISTRAR, color="white", size=24)
            if ICON_REGISTRAR is not None
            else ft.Container(),
            ft.Text("Registrarme", color="white", size=20,
                    weight=ft.FontWeight.BOLD, font_family=FUENTE),
        ],
        alignment=ft.MainAxisAlignment.CENTER,
        spacing=12,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )
    contenido_boton_cargando = ft.Row(
        [
            ft.ProgressRing(width=22, height=22, stroke_width=3, color="white"),
            ft.Text("Registrando...", color="white", size=18,
                    weight=ft.FontWeight.BOLD, font_family=FUENTE),
        ],
        alignment=ft.MainAxisAlignment.CENTER,
        spacing=14,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )
    btn_registrar = ft.Container(
        height=60,
        border_radius=30,
        bgcolor=COLOR_MORADO,
        shadow=ft.BoxShadow(
            blur_radius=14,
            spread_radius=1,
            color="#338E45CC",
            offset=ft.Offset(0, 6),
        ),
        ink=True,
        alignment=ALIGN_CENTER,
        content=contenido_boton,
    )

    # Bandera anti doble envío: con la base de datos en la nube el
    # registro tarda unos segundos (dos consultas de duplicados, el hash
    # de la contraseña y dos INSERT).
    en_proceso = {"value": False}

    def mostrar_mensaje(texto: str, color: str = COLOR_ERROR):
        lbl_msg.value = texto
        lbl_msg.color = color

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

    # Antes los errores se escribían en campo.error_text. En Flet 0.80
    # esa propiedad ya no existe en TextField (ahora es error): Python
    # aceptaba la asignación, pero Flet no la dibujaba, así que ninguna
    # validación aparecía y el botón parecía no hacer nada. set_error
    # usa la propiedad correcta en cada versión.
    def validar_campos() -> bool:
        for campo in [txt_nombre, txt_apellido, txt_correo, txt_tel, txt_usuario, txt_pass, txt_pass2]:
            set_error(campo, None)

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
            set_error(txt_nombre, "Solo letras, mínimo 2 y máximo 30 caracteres")
            valido = False

        # --- Apellido
        if not PATRON_NOMBRE.match(apellido):
            set_error(txt_apellido, "Solo letras, mínimo 2 y máximo 30 caracteres")
            valido = False

        # --- Correo (formato + duplicado cruzado)
        if not PATRON_CORREO.match(correo):
            set_error(txt_correo, "Correo inválido. Ejemplo: usuario@gmail.com")
            valido = False
        else:
            try:
                existe, msg_dup = _existe_dato_persona("Correo", correo)
                if existe:
                    set_error(txt_correo, msg_dup)
                    valido = False
            except Exception:
                pass  # no bloquear por error de BD

        # --- Teléfono (formato + duplicado cruzado)
        if not tel.isdigit() or len(tel) != 10:
            set_error(txt_tel, "El teléfono debe tener exactamente 10 números")
            valido = False
        else:
            try:
                existe, msg_dup = _existe_dato_persona("Telefono", tel)
                if existe:
                    set_error(txt_tel, msg_dup)
                    valido = False
            except Exception:
                pass

        # --- Usuario (formato + duplicado en tabla usuario)
        if not PATRON_USUARIO.match(usuario):
            set_error(txt_usuario, "Usuario de 4 a 20 caracteres, solo letras, números o _")
            valido = False
        # la comprobación de usuario duplicado se hace en registrar() justo antes del INSERT

        # --- Contraseña (politica central de servicio_seguridad)
        politica = seguridad.validar_fortaleza(password, usuario)
        if not politica.valida:
            set_error(txt_pass, politica.mensaje)
            valido = False

        # --- Confirmación
        if password != password2:
            set_error(txt_pass2, "Las contraseñas no coinciden")
            valido = False

        # --- Aviso de privacidad (consentimiento obligatorio)
        error_privacidad = privacidad.mensaje_si_no_acepta(chk_privacidad.value)
        lbl_error_privacidad.value = error_privacidad or ""
        lbl_error_privacidad.visible = error_privacidad is not None
        if error_privacidad:
            valido = False

        if valido:
            mostrar_mensaje("")
        else:
            mostrar_mensaje("Revisa los campos marcados en rojo.")
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
    def bloquear_boton(bloquear: bool):
        btn_registrar.disabled = bloquear
        btn_registrar.content = contenido_boton_cargando if bloquear else contenido_boton
        btn_registrar.bgcolor = COLOR_MORADO_CLARO if bloquear else COLOR_MORADO

    def registrar(e):
        # Primera línea de defensa contra el doble toque.
        if en_proceso["value"]:
            return
        en_proceso["value"] = True
        bloquear_boton(True)
        mostrar_mensaje("Revisando tus datos...", COLOR_GRIS)
        page.update()

        try:
            if not validar_campos():
                return
            if registrar_en_bd():
                return  # ya se navegó al login
        finally:
            en_proceso["value"] = False
            bloquear_boton(False)
            try:
                page.update()
            except Exception:
                pass

    def registrar_en_bd() -> bool:
        """Inserta usuario + cliente/empleado. Devuelve True si se registró."""
        nombre   = txt_nombre.value.strip()
        apellido = txt_apellido.value.strip()
        correo   = txt_correo.value.strip().lower()
        tel      = txt_tel.value.strip()
        usuario  = txt_usuario.value.strip()
        password = txt_pass.value.strip()

        conn = None
        cursor = None
        try:
            conn   = get_connection()
            cursor = conn.cursor()

            # Revisar si el usuario ya existe
            cursor.execute("SELECT IdUsuario FROM usuario WHERE NombreUsuario=%s", (usuario,))
            if cursor.fetchone():
                set_error(txt_usuario, "Ese nombre de usuario ya existe")
                mostrar_mensaje("Ese nombre de usuario ya existe. Elige otro.")
                return False

            # Insertar en usuario
            # La contrasena NUNCA se guarda tal cual: se almacena su hash
            # PBKDF2-SHA256 con sal, generado por servicio_seguridad.
            rol = ROL_CLIENTE if tipo == "Cliente" else ROL_EMPLEADO
            cursor.execute(
                "INSERT INTO usuario (NombreUsuario, Contraseña, Rol) VALUES (%s, %s, %s)",
                (usuario, seguridad.hashear(password), rol),
            )
            id_usuario = cursor.lastrowid

            # Insertar en cliente o empleado
            tabla = "cliente" if tipo == "Cliente" else "empleado"
            cursor.execute(
                f"INSERT INTO {tabla} (Nombre, Apellido, Telefono, Correo, Usuario_IdUsuario) "
                "VALUES (%s, %s, %s, %s, %s)",
                (nombre, apellido, tel, correo, id_usuario),
            )

            # Constancia del consentimiento, en la misma transacción:
            # si algo falla, no queda ni la cuenta ni el consentimiento.
            origen = "registro_cliente" if tipo == "Cliente" else "registro_empleado"
            privacidad.registrar_consentimiento(cursor, id_usuario, origen)

            conn.commit()

            # page.snack_bar ya no existe en Flet 0.80; snack() usa la API
            # de cada versión. El aviso vive en el overlay de la página,
            # así que se sigue viendo después de cambiar al login.
            ir_login()
            snack(page, f"{tipo} registrado correctamente. Ahora puedes iniciar sesión.")
            return True

        except Exception as ex:
            try:
                if conn:
                    conn.rollback()
            except Exception:
                pass
            mostrar_mensaje(f"Error al registrar: {ex}")
            return False
        finally:
            try:
                if cursor:
                    cursor.close()
                if conn:
                    conn.close()
            except Exception:
                pass

    def volver_login(e):
        ir_login()

    # ------------------------------------------------------------------
    # LAYOUT  (misma línea visual que el login: fondo decorado, tarjeta
    # redondeada, campos tipo píldora y botón morado)
    # ------------------------------------------------------------------
    # Responsive: en celular la tarjeta usa el ancho de la pantalla y los
    # campos van uno debajo de otro; en computadora nombre/apellido y las
    # dos contraseñas van lado a lado. Toda la página tiene scroll para
    # poder llegar al botón en pantallas bajas.
    ancho_pagina = getattr(page, "width", None) or 1200
    es_movil = ancho_pagina < 700
    ancho_card = min(640, ancho_pagina - 24)
    padding_card = 20 if es_movil else 38

    def par(campo_a, campo_b):
        if es_movil:
            return ft.Column(
                [campo_a, campo_b],
                spacing=12,
                horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            )
        campo_a.expand = True
        campo_b.expand = True
        return ft.Row(
            [campo_a, campo_b],
            spacing=12,
            vertical_alignment=ft.CrossAxisAlignment.START,
        )

    def seccion(texto):
        return ft.Container(
            padding=ft.padding.only(left=6, top=4),
            content=ft.Text(
                texto,
                size=15,
                color=COLOR_MORADO,
                weight=ft.FontWeight.BOLD,
                font_family=FUENTE,
            ),
        )

    link_volver = ft.Container(
        ink=True,
        border_radius=14,
        padding=ft.padding.symmetric(horizontal=10, vertical=6),
        on_click=volver_login,
        content=ft.Row(
            [
                ft.Icon(ICON_VOLVER, color=COLOR_MORADO, size=22)
                if ICON_VOLVER is not None
                else ft.Container(),
                ft.Text(
                    "¿Ya tienes cuenta? Inicia sesión",
                    color=COLOR_MORADO,
                    size=16,
                    weight=ft.FontWeight.BOLD,
                    font_family=FUENTE,
                ),
            ],
            spacing=10,
            tight=True,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
    )

    card_registro = ft.Container(
        width=ancho_card,
        border_radius=40 if es_movil else 48,
        bgcolor=COLOR_CARD,
        padding=ft.padding.only(
            left=padding_card, right=padding_card, top=26, bottom=26
        ),
        shadow=ft.BoxShadow(
            blur_radius=30,
            spread_radius=2,
            color="#22C86DD7",
            offset=ft.Offset(0, 10),
        ),
        content=ft.Column(
            [
                ft.Column(
                    [
                        ft.Image(src=_img("logo_corallie.png"), width=80 if es_movil else 100),
                        ft.Text(
                            "Corallie Bubble",
                            size=30 if es_movil else 40,
                            color=COLOR_MORADO,
                            font_family=FUENTE_TITULO,
                            text_align=ft.TextAlign.CENTER,
                        ),
                        ft.Row(
                            [
                                ft.Text("›", size=22, color=COLOR_DECOR, font_family=FUENTE),
                                ft.Text(
                                    titulo,
                                    size=21,
                                    color=COLOR_TEXTO,
                                    font_family=FUENTE,
                                    text_align=ft.TextAlign.CENTER,
                                ),
                                ft.Text("‹", size=22, color=COLOR_DECOR, font_family=FUENTE),
                            ],
                            alignment=ft.MainAxisAlignment.CENTER,
                            spacing=12,
                        ),
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=6,
                ),
                seccion("Tus datos"),
                par(txt_nombre, txt_apellido),
                txt_correo,
                txt_tel,
                seccion("Tu cuenta"),
                txt_usuario,
                par(txt_pass, txt_pass2),
                bloque_privacidad,
                lbl_msg,
                btn_registrar,
                ft.Row([link_volver], alignment=ft.MainAxisAlignment.CENTER),
            ],
            spacing=12,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        ),
    )

    # Fondo decorativo: mismas imágenes del login (assets/login). En
    # celular se omiten las que tapan el formulario.
    decoracion = [
        ft.Image(src=_img("mancha_rosa_2.png", "mancha rosa 2.png"), width=420, left=-80, top=-60),
        ft.Image(src=_img("hoja_morada_2.png", "hoja morada 2.png"), width=220, right=-40, top=70),
        ft.Image(src=_img("mancha_rosa_3.png", "mancha rosa 3.png"), width=420, right=-110, bottom=-90),
    ]
    if not es_movil:
        decoracion += [
            ft.Image(src=_img("burbujas.png"), width=76, right=110, top=410),
            ft.Image(src=_img("mancha_blanca.png", "mancha blanca.png"), width=280, left=-60, bottom=30),
            ft.Image(src=_img("burbujas_2.png", "burbujas 2.png"), width=96, left=58, bottom=74),
            ft.Image(src=_img("hoja_1.png"), width=190, right=-38, bottom=220),
        ]

    contenido = ft.Container(
        expand=True,
        bgcolor=COLOR_FONDO,
        content=ft.Stack(
            expand=True,
            controls=decoracion + [
                # Ocupa toda la pantalla (left/right/top/bottom = 0) para
                # que la tarjeta quede centrada y el scroll funcione.
                ft.Container(
                    left=0,
                    right=0,
                    top=0,
                    bottom=0,
                    content=ft.Column(
                        [
                            ft.Container(
                                padding=ft.padding.symmetric(horizontal=12, vertical=20),
                                content=card_registro,
                            )
                        ],
                        expand=True,
                        scroll=ft.ScrollMode.AUTO,
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                ),
            ],
        ),
    )

    btn_registrar.on_click = registrar

    return ft.View(route="/registro", controls=[contenido], bgcolor=COLOR_FONDO, padding=0)