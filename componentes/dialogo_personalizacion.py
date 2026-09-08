"""Diálogo reutilizable para personalizar bebidas del menú."""

import flet as ft

if not hasattr(ft, "icons") and hasattr(ft, "Icons"):
    ft.icons = ft.Icons

if not hasattr(ft, "animation"):
    ft.animation = ft

ALIGN_CENTER = (
    getattr(getattr(ft, "alignment", None), "center", None)
    or getattr(ft.Alignment, "CENTER", None)
)
ALIGN_BOTTOM_CENTER = (
    getattr(getattr(ft, "alignment", None), "bottom_center", None)
    or getattr(ft.Alignment, "BOTTOM_CENTER", None)
)


def obtener_icono(nombre: str, respaldo=None):
    try:
        valor = getattr(ft.icons, nombre)
        return valor if valor is not None else respaldo
    except Exception:
        return respaldo


def _miniatura_encabezado(item: dict):
    """Foto real del producto (si el admin la subió desde Inventario) o
    el emoji de respaldo, con una entrada animada tipo "pop"."""
    imagen = (item.get("imagen") or "").strip()

    contenedor = ft.Container(
        width=44,
        height=44,
        border_radius=16,
        bgcolor="#FBE7F4",
        alignment=ALIGN_CENTER,
        clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
        animate_scale=ft.animation.Animation(260, ft.AnimationCurve.EASE_OUT),
        scale=1,
        content=(
            ft.Image(
                src=imagen,
                width=44,
                height=44,
                fit=ft.BoxFit.COVER,
                error_content=ft.Text(item.get("emoji", "🧋"), size=22),
            )
            if imagen
            else ft.Text(item.get("emoji", "🧋"), size=22)
        ),
    )
    return contenedor


def _crear_chip_extra(nombre_extra: str, precio_extra, activo_inicial: bool, on_toggle):
    """Convierte cada extra en un chip tocable con animación, en vez del
    checkbox plano de antes."""
    icono_check = ft.Icon(
        obtener_icono("CHECK_CIRCLE"),
        size=15,
        color="white",
        visible=activo_inicial,
    )
    texto = ft.Text(
        f"{nombre_extra} (+{precio_extra})",
        size=12,
        weight=ft.FontWeight.BOLD,
        color="white" if activo_inicial else "#6D28D9",
    )

    estado = {"activo": activo_inicial}

    contenedor = ft.Container(
        padding=ft.padding.symmetric(horizontal=12, vertical=9),
        border_radius=999,
        bgcolor="#C86DD7" if activo_inicial else "#F5E8FF",
        border=None if activo_inicial else ft.border.all(1, "#E9D3F5"),
        ink=True,
        animate=ft.animation.Animation(200, ft.AnimationCurve.EASE_OUT),
        animate_scale=ft.animation.Animation(150, ft.AnimationCurve.EASE_OUT),
        content=ft.Row([icono_check, texto], spacing=6, tight=True),
    )

    def click(e=None):
        estado["activo"] = not estado["activo"]
        contenedor.bgcolor = "#C86DD7" if estado["activo"] else "#F5E8FF"
        contenedor.border = None if estado["activo"] else ft.border.all(1, "#E9D3F5")
        icono_check.visible = estado["activo"]
        texto.color = "white" if estado["activo"] else "#6D28D9"
        on_toggle()

    def hover(e):
        contenedor.scale = 1.05 if e.data == "true" else 1
        contenedor.update()

    contenedor.on_click = click
    contenedor.on_hover = hover
    return contenedor, estado


def abrir_dialogo_personalizacion(
    page: ft.Page,
    item: dict,
    formatear_dinero,
    on_confirmar,
    cerrar_dialogo,
    abrir_dialogo,
    preparacion_inicial: dict | None = None,
):
    """Abre el formulario para configurar tamaño, azúcar, hielo y extras.

    Args:
        page: Página actual de Flet.
        item: Producto seleccionado.
        formatear_dinero: Función para mostrar precios.
        on_confirmar: Callback que recibe (item, preparacion, precio_final).
            Se llama tanto para agregar un producto nuevo al carrito como
            para guardar cambios sobre uno ya existente (según lo decida
            quien abre el diálogo).
        cerrar_dialogo: Helper para cerrar AlertDialog.
        abrir_dialogo: Helper para abrir AlertDialog.
        preparacion_inicial: si se pasa, el diálogo abre precargado con
            estos valores (modo edición) en vez de los valores por defecto.
    """
    nombre_prod = item.get("nombre", "Producto")
    precio_base = float(item.get("precio", 0))
    descripcion = item.get("descripcion", "")
    modo_edicion = preparacion_inicial is not None
    prep_inicial = preparacion_inicial or {}

    TAMANOS_DIMENSIONES = {
        "Chico": (90, 130),
        "Mediano": (110, 150),
        "Grande": (128, 170),
    }

    dd_tamano = ft.Dropdown(
        label="Tamaño",
        value=prep_inicial.get("tamano", "Mediano"),
        expand=1,
        options=[
            ft.dropdown.Option("Chico"),
            ft.dropdown.Option("Mediano"),
            ft.dropdown.Option("Grande"),
        ],
    )

    boba_inicial = int(prep_inicial.get("boba", prep_inicial.get("azucar", 40)))
    hielo_inicial = int(prep_inicial.get("hielo", 70))
    sl_boba = ft.Slider(min=0, max=100, divisions=10, value=boba_inicial, label="{value}%")
    sl_hielo = ft.Slider(min=0, max=100, divisions=10, value=hielo_inicial, label="{value}%")

    dd_leche = ft.Dropdown(
        label="Tipo de leche",
        value=prep_inicial.get("leche", "Entera"),
        expand=1,
        options=[
            ft.dropdown.Option("Entera"),
            ft.dropdown.Option("Deslactosada"),
            ft.dropdown.Option("Almendra"),
            ft.dropdown.Option("Avena"),
            ft.dropdown.Option("Soya"),
            ft.dropdown.Option("Sin leche"),
        ],
    )

    extras_info = [
        ("Boba extra", 6),
        ("Jelly", 6),
        ("Popping boba", 8),
        ("Crema", 5),
        ("Chispas", 5),
    ]
    toppings_iniciales = set(prep_inicial.get("toppings") or [])

    txt_notas = ft.TextField(
        label="Indicaciones",
        multiline=True,
        min_lines=2,
        max_lines=3,
        hint_text="Ej. sin hielo, extra dulce, poca tapioca...",
        value=prep_inicial.get("notas", ""),
    )

    ancho_ini, alto_ini = TAMANOS_DIMENSIONES.get(dd_tamano.value, (110, 150))
    RATIO_VASO = 873 / 547  # alto / ancho de la imagen real del vaso
    MARGEN_VASO = 22  # espacio extra para que el popote no se corte

    # ------------------------------------------------------------
    # Vaso armado con tus imágenes reales (assets/vaso/*.png), no dibujado.
    # El hielo y la boba son controles fijos que empiezan arriba del vaso
    # (invisibles) y "caen" a su lugar cuando cambian los sliders, gracias
    # a animate_position/animate_opacity de Flet.
    # ------------------------------------------------------------
    RUTA_VASO = "vaso/vaso.png"
    RUTA_HIELO = "vaso/hielo.png"
    RUTA_BOBA = "vaso/boba.png"
    RUTA_SOMBRA = "vaso/sombra.png"

    MAX_HIELOS = 5
    MAX_BOBA = 14
    ANCHO_HIELO_PX, ALTO_HIELO_PX = 30, 32
    ANCHO_BOBA_PX, ALTO_BOBA_PX = 17, 16

    # El vaso es más angosto abajo que arriba (como uno real), así que las
    # posiciones se guardan como (altura, desplazamiento horizontal relativo
    # al centro) y el ancho disponible en cada altura se calcula aparte.
    # Esto evita que hielo/boba "se salgan" de la curva del vaso.
    ANCHO_FRAC_ARRIBA = 0.84
    ANCHO_FRAC_ABAJO = 0.56

    def _ancho_disponible(fy: float) -> float:
        fy_top, fy_bottom = 0.27, 0.93
        t = max(0.0, min(1.0, (fy - fy_top) / (fy_bottom - fy_top)))
        return ANCHO_FRAC_ARRIBA + (ANCHO_FRAC_ABAJO - ANCHO_FRAC_ARRIBA) * t

    def _fx_desde_relativo(fy: float, rel: float) -> float:
        return 0.5 + rel * _ancho_disponible(fy) / 2

    def _oscurecer(color_hex: str, factor: float = 0.72) -> str:
        color_hex = color_hex.lstrip("#")
        r, g, b = int(color_hex[0:2], 16), int(color_hex[2:4], 16), int(color_hex[4:6], 16)
        return f"#{int(r * factor):02X}{int(g * factor):02X}{int(b * factor):02X}"

    # Hielo grande, muy junto y encimado, justo a la altura de la
    # superficie del líquido (como en la referencia), no disperso ni
    # flotando en medio del vaso.
    OFFSETS_HIELO = [
        (0.27, -0.50),
        (0.26, 0.15),
        (0.34, -0.10),
        (0.36, -0.55),
        (0.30, 0.52),
    ]
    ESCALAS_HIELO = [1.05, 1.15, 0.95, 1.0, 0.90]
    ANGULOS_HIELO = [-0.25, 0.30, -0.15, 0.35, -0.20]

    # Boba en una masa pareja de borde a borde, pero SIN salirse del borde
    # rosa/amarillo del vaso: el ancho disponible aquí sale de medir el
    # color real del líquido en tu imagen (ver _ancho_liquido_medido), no
    # de una fórmula inventada — así ninguna perla queda montada sobre el
    # contorno del vaso.
    _PUNTOS_ANCHO_BOBA = [
        (0.70, 0.766), (0.74, 0.757), (0.78, 0.748), (0.82, 0.737),
        (0.85, 0.729), (0.88, 0.720), (0.90, 0.711), (0.92, 0.687),
        (0.93, 0.673), (0.95, 0.623),
    ]
    MARGEN_SEGURIDAD_BOBA = 0.82  # colchón extra para el propio radio de la perla

    def _ancho_liquido_medido(fy: float) -> float:
        puntos = _PUNTOS_ANCHO_BOBA
        if fy <= puntos[0][0]:
            return puntos[0][1]
        if fy >= puntos[-1][0]:
            return puntos[-1][1]
        for (fy0, w0), (fy1, w1) in zip(puntos, puntos[1:]):
            if fy0 <= fy <= fy1:
                t = (fy - fy0) / (fy1 - fy0)
                return w0 + (w1 - w0) * t
        return puntos[-1][1]

    def _fx_boba(fy: float, rel: float) -> float:
        return 0.5 + rel * _ancho_liquido_medido(fy) * MARGEN_SEGURIDAD_BOBA / 2

    OFFSETS_BOBA = [
        (0.73, -0.85), (0.73, -0.28), (0.73, 0.30), (0.73, 0.82),
        (0.79, -0.92), (0.79, -0.45), (0.79, 0.0), (0.79, 0.48), (0.79, 0.90),
        (0.85, -0.70), (0.85, 0.0), (0.85, 0.72),
        (0.90, -0.35), (0.90, 0.35),
    ]
    ESCALAS_BOBA = [
        0.85, 0.88, 0.84, 0.87,
        0.95, 0.92, 0.97, 0.93, 0.90,
        1.05, 1.10, 1.03,
        1.18, 1.20,
    ]
    ANGULOS_BOBA = [
        0.10, -0.15, 0.18, -0.10,
        0.14, -0.18, 0.06, -0.08, 0.16,
        0.20, -0.12, 0.22,
        -0.09, 0.15,
    ]

    def _crear_flotante(ruta: str, ancho_img: int, alto_img: int, angulo: float = 0.0, escala: float = 1.0):
        return ft.Container(
            left=0,
            top=-60,
            width=ancho_img,
            height=alto_img,
            opacity=0,
            scale=escala,
            rotate=ft.Rotate(angle=angulo),
            animate_position=ft.animation.Animation(420, ft.AnimationCurve.EASE_OUT),
            animate_opacity=ft.animation.Animation(280, ft.AnimationCurve.EASE_OUT),
            content=ft.Image(src=ruta, width=ancho_img, height=alto_img, fit=ft.BoxFit.CONTAIN),
        )

    def _crear_onda():
        """Óvalo de color (del tono del líquido) que se asoma justo debajo
        de cada cubito, simulando que el líquido lo rodea en la superficie
        en vez de que el hielo quede flotando encima sin tocar nada."""
        return ft.Container(
            left=0,
            top=-60,
            opacity=0,
            border_radius=999,
            animate_position=ft.animation.Animation(420, ft.AnimationCurve.EASE_OUT),
            animate_opacity=ft.animation.Animation(280, ft.AnimationCurve.EASE_OUT),
        )

    imagen_vaso = ft.Image(src=RUTA_VASO, fit=ft.BoxFit.CONTAIN)

    tinte_liquido = ft.Container(
        bgcolor="#FDF2F8",
        opacity=0.30,
        border_radius=26,
        animate=ft.animation.Animation(280, ft.AnimationCurve.EASE_OUT),
        animate_opacity=ft.animation.Animation(280, ft.AnimationCurve.EASE_OUT),
    )

    # Sombra suave bajo el montón de boba (el hielo usa las "ondas"
    # individuales en vez de una sombra compartida).
    sombra_boba = ft.Container(
        content=ft.Image(src=RUTA_SOMBRA, fit=ft.BoxFit.FILL),
        opacity=0,
        animate_opacity=ft.animation.Animation(280, ft.AnimationCurve.EASE_OUT),
    )

    hielo_ctrls = [
        _crear_flotante(RUTA_HIELO, ANCHO_HIELO_PX, ALTO_HIELO_PX, ANGULOS_HIELO[i], ESCALAS_HIELO[i])
        for i in range(MAX_HIELOS)
    ]
    ondas_hielo = [_crear_onda() for _ in range(MAX_HIELOS)]
    boba_ctrls = [
        _crear_flotante(RUTA_BOBA, ANCHO_BOBA_PX, ALTO_BOBA_PX, ANGULOS_BOBA[i], ESCALAS_BOBA[i])
        for i in range(MAX_BOBA)
    ]

    # Cada onda se dibuja justo antes que su cubito, para que el hielo
    # quede "encima" de su propio reflejo de líquido.
    controles_hielo_con_onda = []
    for onda, cubo in zip(ondas_hielo, hielo_ctrls):
        controles_hielo_con_onda.append(onda)
        controles_hielo_con_onda.append(cubo)

    vaso_stack = ft.Stack(
        controls=[imagen_vaso, tinte_liquido, sombra_boba, *controles_hielo_con_onda, *boba_ctrls]
    )

    vaso_preview = ft.Container(
        content=vaso_stack,
        width=ancho_ini + MARGEN_VASO,
        height=int((ancho_ini + MARGEN_VASO) * RATIO_VASO),
        animate=ft.animation.Animation(320, ft.AnimationCurve.EASE_OUT),
        animate_scale=ft.animation.Animation(320, ft.AnimationCurve.EASE_OUT),
    )

    lbl_precio = ft.Text(
        formatear_dinero(precio_base),
        color="#7C3AED",
        weight=ft.FontWeight.BOLD,
        size=16,
    )
    badge_precio = ft.Container(
        padding=ft.padding.symmetric(horizontal=12, vertical=8),
        border_radius=999,
        bgcolor="#F5E8FF",
        content=lbl_precio,
        animate_scale=ft.animation.Animation(180, ft.AnimationCurve.EASE_OUT),
        scale=1,
    )
    lbl_boba = ft.Text(f"Boba: {boba_inicial}%", size=12, color="#555555")
    lbl_hielo = ft.Text(f"Hielo: {hielo_inicial}%", size=12, color="#555555")
    # ------------------------------------------------------------
    # Extras como chips animados (antes eran checkboxes planos)
    # ------------------------------------------------------------
    estados_extras = {}
    chips_extras = []

    def _al_cambiar_extra():
        refrescar_preview()

    for nombre_extra, precio_extra in extras_info:
        chip_ctrl, estado = _crear_chip_extra(
            nombre_extra, precio_extra, nombre_extra in toppings_iniciales, _al_cambiar_extra
        )
        estados_extras[nombre_extra] = estado
        chips_extras.append(chip_ctrl)

    def calcular_extra():
        total_extra = 0.0
        if dd_tamano.value == "Grande":
            total_extra += 10
        elif dd_tamano.value == "Chico":
            total_extra -= 5

        for nombre_extra, precio_extra in extras_info:
            if estados_extras[nombre_extra]["activo"]:
                total_extra += float(precio_extra)
        return total_extra

    def refrescar_preview(e=None):
        hielo_val = int(sl_hielo.value or 0)
        boba_val = int(sl_boba.value or 0)
        color_vaso = "#FDF2F8"

        nombre_lower = nombre_prod.lower()
        if "matcha" in nombre_lower:
            color_vaso = "#D9F99D"
        elif "chocolate" in nombre_lower:
            color_vaso = "#D6B08C"
        elif "fresa" in nombre_lower:
            color_vaso = "#F9A8D4"
        elif "mango" in nombre_lower:
            color_vaso = "#FCD34D"
        elif "taro" in nombre_lower:
            color_vaso = "#DDD6FE"

        # Tamaño del vaso reacciona con animación al cambiar el dropdown.
        ancho_dip, _ = TAMANOS_DIMENSIONES.get(dd_tamano.value, (110, 150))
        ancho_vaso = ancho_dip + MARGEN_VASO
        alto_vaso = int(ancho_vaso * RATIO_VASO)

        vaso_preview.width = ancho_vaso
        vaso_preview.height = alto_vaso
        vaso_stack.width = ancho_vaso
        vaso_stack.height = alto_vaso
        imagen_vaso.width = ancho_vaso
        imagen_vaso.height = alto_vaso

        # Tinte de color según el sabor, sobre el área donde va el líquido
        # dentro de la imagen real del vaso.
        tinte_liquido.left = ancho_vaso * 0.15
        tinte_liquido.top = alto_vaso * 0.27
        tinte_liquido.width = ancho_vaso * 0.70
        tinte_liquido.height = alto_vaso * 0.60
        tinte_liquido.border_radius = ft.BorderRadius(top_left=6, top_right=6, bottom_left=40, bottom_right=40)
        tinte_liquido.bgcolor = color_vaso

        # Cuántos cubitos/perlas van "servidos" según cada slider (0 a máximo).
        color_onda = _oscurecer(color_vaso)
        num_hielos = round((hielo_val / 100) * MAX_HIELOS)
        for i, ctrl in enumerate(hielo_ctrls):
            fy, rel = OFFSETS_HIELO[i]
            fx = _fx_desde_relativo(fy, rel)
            ancho_efectivo = ANCHO_HIELO_PX * ESCALAS_HIELO[i]
            alto_efectivo = ALTO_HIELO_PX * ESCALAS_HIELO[i]
            centro_x = ancho_vaso * fx
            top_cubo = alto_vaso * fy

            ctrl.left = centro_x - (ANCHO_HIELO_PX / 2)

            onda = ondas_hielo[i]
            onda.width = ancho_efectivo * 1.35
            onda.height = alto_efectivo * 0.45
            onda.left = centro_x - onda.width / 2
            onda.bgcolor = color_onda

            if i < num_hielos:
                ctrl.top = top_cubo
                ctrl.opacity = 1
                # La onda se asoma justo en la base del cubito, como si el
                # líquido lo rodeara ahí (en vez de dejarlo flotando encima).
                onda.top = top_cubo + alto_efectivo * 0.62
                onda.opacity = 0.7
            else:
                ctrl.top = -40
                ctrl.opacity = 0
                onda.top = -40
                onda.opacity = 0

        num_boba = round((boba_val / 100) * MAX_BOBA)
        for i, ctrl in enumerate(boba_ctrls):
            fy, rel = OFFSETS_BOBA[i]
            fx = _fx_boba(fy, rel)
            ctrl.left = ancho_vaso * fx - (ANCHO_BOBA_PX / 2)
            if i < num_boba:
                ctrl.top = alto_vaso * fy
                ctrl.opacity = 1
            else:
                ctrl.top = -40
                ctrl.opacity = 0

        # Sombra compartida bajo el montón de boba.
        sombra_boba.width = ancho_vaso * 0.80
        sombra_boba.height = sombra_boba.width * (90 / 200)
        sombra_boba.left = ancho_vaso * 0.5 - sombra_boba.width / 2
        sombra_boba.top = alto_vaso * 0.90
        sombra_boba.opacity = 0.75 if num_boba > 0 else 0

        precio_final = max(0.0, precio_base + calcular_extra())
        precio_cambio = lbl_precio.value != formatear_dinero(precio_final)
        lbl_precio.value = formatear_dinero(precio_final)
        lbl_boba.value = f"Boba: {boba_val}%"
        lbl_hielo.value = f"Hielo: {hielo_val}%"

        # Pequeño "rebote" en el precio cuando cambia, para que se note.
        if precio_cambio:
            badge_precio.scale = 1.12

        page.update()

        if precio_cambio:
            badge_precio.scale = 1
            badge_precio.update()

    dd_tamano.on_change = refrescar_preview
    dd_leche.on_change = refrescar_preview
    sl_boba.on_change = refrescar_preview
    sl_hielo.on_change = refrescar_preview

    dlg = ft.AlertDialog(modal=True)

    def confirmar_agregado(e=None):
        preparacion = {
            "tamano": dd_tamano.value,
            "boba": int(sl_boba.value),
            "hielo": int(sl_hielo.value),
            "leche": dd_leche.value,
            "toppings": [n for n in estados_extras if estados_extras[n]["activo"]],
            "notas": txt_notas.value or "",
        }
        precio_final = max(0.0, precio_base + calcular_extra())
        on_confirmar(item, preparacion, precio_final)
        cerrar_dialogo(page, dlg)

    dlg.title = ft.Row(
        controls=[
            _miniatura_encabezado(item),
            ft.Column(
                controls=[
                    ft.Text(nombre_prod, size=16, weight=ft.FontWeight.BOLD),
                    ft.Text(descripcion, size=12, color="#666666"),
                ],
                spacing=2,
                expand=True,
            ),
            badge_precio,
        ],
        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
    )

    # ------------------------------------------------------------
    # Layout responsive: en pantallas angostas (celular) el vaso y los
    # controles NO caben lado a lado en una fila de 650px de ancho fijo
    # (eso es justo lo que se veía cortado en el celular). Si la página
    # es angosta, se apilan verticalmente y el ancho se ajusta al celular.
    # ------------------------------------------------------------
    ancho_pagina = getattr(page, "width", None) or 650
    es_movil = ancho_pagina < 700
    ancho_dialogo = min(650, max(300, ancho_pagina - 32)) if es_movil else 650

    columna_vaso = ft.Column(
        controls=[
            ft.Container(height=6),
            vaso_preview,
            ft.Container(height=10),
            lbl_boba,
            lbl_hielo,
        ],
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
    )

    columna_controles = ft.Column(
        controls=[
            ft.Row([dd_tamano, dd_leche], spacing=10),
            ft.Text("Nivel de boba", weight=ft.FontWeight.BOLD, size=12),
            sl_boba,
            ft.Text("Nivel de hielo", weight=ft.FontWeight.BOLD, size=12),
            sl_hielo,
            ft.Divider(),
            ft.Text("Extras", weight=ft.FontWeight.BOLD, size=12),
            ft.Row(chips_extras, spacing=8, wrap=True, run_spacing=8),
            txt_notas,
        ],
        spacing=10,
        scroll=ft.ScrollMode.AUTO,
    )

    if es_movil:
        # Apilado: vaso arriba, controles abajo. Todo el diálogo hace
        # scroll junto (si no, en celulares chicos se corta por abajo).
        dlg.content = ft.Container(
            width=ancho_dialogo,
            height=min(560, (getattr(page, "height", None) or 700) - 160),
            content=ft.Column(
                controls=[columna_vaso, ft.Divider(), columna_controles],
                spacing=10,
                scroll=ft.ScrollMode.AUTO,
            ),
        )
    else:
        dlg.content = ft.Container(
            width=ancho_dialogo,
            content=ft.Row(
                controls=[
                    ft.Container(width=160, content=columna_vaso),
                    ft.VerticalDivider(width=1, color="#F0D4EA"),
                    ft.Container(expand=True, content=columna_controles),
                ],
                spacing=14,
                vertical_alignment=ft.CrossAxisAlignment.START,
            ),
        )

    dlg.actions = [
        ft.TextButton("Cancelar", on_click=lambda e: cerrar_dialogo(page, dlg)),
        ft.ElevatedButton(
            "Guardar cambios" if modo_edicion else "Agregar al carrito",
            bgcolor="#C86DD7",
            color="white",
            icon=obtener_icono("SAVE" if modo_edicion else "ADD_SHOPPING_CART"),
            on_click=confirmar_agregado,
            style=ft.ButtonStyle(animation_duration=180),
        ),
    ]
    dlg.actions_alignment = ft.MainAxisAlignment.END

    refrescar_preview()
    abrir_dialogo(page, dlg)
