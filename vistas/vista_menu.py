import json

import flet as ft

from componentes.sidebar_menu import build_menu_sidebar
from componentes.tarjeta_producto import tarjeta_producto
from componentes.dialogo_personalizacion import abrir_dialogo_personalizacion
from componentes.tarjeta_pedido import (
    tarjeta_carrito,
    tarjeta_historial,
    tarjeta_estado,
    tarjeta_mensaje,
)
from servicios.servicio_menu import (
    resolver_cliente_id,
    insertar_pedido,
    obtener_historial,
    obtener_pedido,
    obtener_pedido_activo,
    obtener_bebidas,
    cancelar_pedido,
)
from utilidades.formato import formatear_dinero


# ------------------------------------------------------------
# Compatibilidad Flet 0.80 / 0.81+
# ------------------------------------------------------------
if not hasattr(ft, "icons") and hasattr(ft, "Icons"):
    ft.icons = ft.Icons

if not hasattr(ft, "animation"):
    ft.animation = ft

ALIGN_CENTER = (
    getattr(getattr(ft, "alignment", None), "center", None)
    or getattr(ft.Alignment, "CENTER", None)
)

# ------------------------------------------------------------
# Estilo visual inspirado en la portada Corallie Bubble
# ------------------------------------------------------------
COLOR_MORADO = "#6A4A7C"
COLOR_LILA = "#C86DD7"
COLOR_LILA_OSCURO = "#A855F7"
COLOR_ROSA = "#F472B6"
COLOR_ROSA_FUERTE = "#EC4899"
COLOR_CREMA = "#FFF4EA"
COLOR_FONDO_SUAVE = "#FBF3FF"
COLOR_TEXTO = "#2F2437"
COLOR_TEXTO_SUAVE = "#7C6F86"
FUENTE_TITULO = "Georgia"
FUENTE_BASE = "Trebuchet MS"


def _shadow(blur=24, y=8, color="#00000014"):
    return ft.BoxShadow(
        spread_radius=0,
        blur_radius=blur,
        color=color,
        offset=ft.Offset(0, y),
    )


def _texto_titulo(texto, size=24, color=COLOR_MORADO):
    return ft.Text(
        texto,
        size=size,
        weight=ft.FontWeight.BOLD,
        color=color,
        font_family=FUENTE_TITULO,
    )


def _texto_normal(texto, size=13, color=COLOR_TEXTO_SUAVE, weight=None):
    return ft.Text(
        texto,
        size=size,
        color=color,
        weight=weight,
        font_family=FUENTE_BASE,
    )


def _icon(*names):
    """Obtiene un icono compatible entre versiones de Flet."""
    for name in names:
        try:
            value = getattr(getattr(ft, "icons", None), name, None)
            if value is not None:
                return value
        except Exception:
            pass
        try:
            value = getattr(getattr(ft, "Icons", None), name, None)
            if value is not None:
                return value
        except Exception:
            pass
    return None


def _limpiar_snackbars(page: ft.Page, conservar=None):
    """Quita del overlay únicamente los snackbars ya cerrados.

    Los AlertDialog NO se tocan aquí: quitarlos del overlay mientras su
    ruta modal sigue montada en Flutter deja una barrera invisible
    encima de la pantalla que se traga todos los toques. De eso se
    encarga page.close().
    """
    try:
        if not hasattr(page, "overlay"):
            return
        for viejo in list(page.overlay):
            if viejo is conservar:
                continue
            if isinstance(viejo, ft.SnackBar) and not getattr(viejo, "open", False):
                try:
                    page.overlay.remove(viejo)
                except Exception:
                    pass
    except Exception:
        pass


def _open_dialog(page: ft.Page, dlg: ft.AlertDialog):
    """Abre un diálogo con la API oficial de Flet.

    Se fuerza modal = False para que tocar fuera de la ventana la
    cierre, que es lo que espera cualquier usuario en móvil.
    """
    try:
        if isinstance(dlg, ft.AlertDialog):
            dlg.modal = False
    except Exception:
        pass

    for metodo in ("open", "show_dialog"):
        try:
            fn = getattr(page, metodo, None)
            if fn is not None:
                fn(dlg)
                return
        except Exception:
            continue

    try:
        if hasattr(page, "overlay") and dlg not in page.overlay:
            page.overlay.append(dlg)
        dlg.open = True
        page.update()
    except Exception:
        try:
            page.dialog = dlg
            dlg.open = True
            page.update()
        except Exception:
            pass


def _close_dialog(page: ft.Page, dlg: ft.AlertDialog):
    """Cierra el diálogo y desmonta su ruta modal.

    Antes sólo se ponía open = False, sin quitarlo del overlay. Las
    ventanas se iban acumulando cerradas-pero-montadas y a partir de la
    segunda vez los toques ya no llegaban a nada: el centro de
    notificaciones se abría pero sus tarjetas no respondían, y el botón
    de cerrar dejaba la pantalla congelada.
    """
    for metodo in ("close", "pop_dialog"):
        try:
            fn = getattr(page, metodo, None)
            if fn is None:
                continue
            try:
                fn(dlg)
            except TypeError:
                fn()
            return
        except Exception:
            continue

    try:
        dlg.open = False
        page.update()
    except Exception:
        pass

    try:
        if hasattr(page, "overlay") and dlg in page.overlay:
            page.overlay.remove(dlg)
            page.update()
    except Exception:
        pass


def _show_snack(page: ft.Page, text: str, ok: bool = True):
    snack = ft.SnackBar(
        content=ft.Text(text, color="white"),
        bgcolor="#22C55E" if ok else "#EF4444",
    )
    try:
        _limpiar_snackbars(page, conservar=snack)
        if hasattr(page, "overlay") and snack not in page.overlay:
            page.overlay.append(snack)
        snack.open = True
        page.update()
    except Exception:
        page.snack_bar = snack
        snack.open = True
        page.update()


def _preparacion_a_texto(prep: dict) -> str:
    """Convierte la personalización del producto en texto legible."""
    partes = []

    if prep.get("tamano"):
        partes.append(f"Tamaño: {prep['tamano']}")
    if prep.get("boba") is not None:
        partes.append(f"Boba: {prep['boba']}%")
    if prep.get("hielo") is not None:
        partes.append(f"Hielo: {prep['hielo']}%")
    if prep.get("leche"):
        partes.append(f"Leche: {prep['leche']}")

    toppings = prep.get("toppings") or []
    if toppings:
        partes.append("Extras: " + ", ".join(toppings))

    notas = (prep.get("notas") or "").strip()
    if notas:
        partes.append(f"Notas: {notas}")

    return " | ".join(partes) if partes else "Preparación estándar"


def _cart_key(nombre_bebida: str, prep: dict) -> str:
    """Genera una clave única para juntar productos iguales con la misma preparación."""
    extras = tuple(sorted(prep.get("toppings") or []))
    return str(
        (
            nombre_bebida.strip().lower(),
            prep.get("tamano", ""),
            prep.get("boba", ""),
            prep.get("hielo", ""),
            prep.get("leche", ""),
            extras,
            (prep.get("notas") or "").strip().lower(),
        )
    )


def menu_interactivo_view(page: ft.Page, nombre: str, cliente_id: int | None = None):
    """Vista del menú interactivo para clientes."""

    # --------------------------------------------------------
    # Configuración general
    # --------------------------------------------------------
    page.title = "Corallie Bubble - Menú Interactivo"
    page.theme_mode = ft.ThemeMode.LIGHT

    if cliente_id is None:
        try:
            store = getattr(page, "_mem_store", None)
            if isinstance(store, dict) and store.get("cliente_id"):
                cliente_id = int(store.get("cliente_id"))
        except Exception:
            cliente_id = None

    cliente_id = cliente_id or resolver_cliente_id(nombre)

    # --------------------------------------------------------
    # Datos del menú
    # --------------------------------------------------------
    # Antes esta lista vivía hardcodeada aquí. Ahora sale de la tabla
    # `productos` en la base de datos (vía servicio_menu.obtener_bebidas),
    # igual que hace vista_inventario con sus productos.
    bebidas = obtener_bebidas()

    # --------------------------------------------------------
    # Estado interno
    # --------------------------------------------------------
    carrito = {}
    ultimo_pedido = {"id": None}
    # Bandera anti doble envío: con la base de datos en la nube el INSERT
    # tarda 1-2 segundos, así que la interfaz se queda "quieta" y el
    # cliente alcanza a pulsar dos veces "Confirmar pedido". Eso generaba
    # un segundo pedido con el carrito ya vaciado (Total $0.00).
    pedido_en_proceso = {"value": False}
    seccion_actual = {"value": "menu"}
    categoria_actual = {"value": "Todos"}
    notificaciones_leidas = set()

    # --------------------------------------------------------
    # Persistencia de notificaciones leídas
    # --------------------------------------------------------
    # Guarda las notificaciones leídas por cliente para evitar que,
    # al cerrar sesión y volver a entrar, pedidos antiguos aparezcan
    # otra vez como mensajes nuevos.
    CLAVE_NOTIF_LEIDAS = f"menu_notificaciones_leidas_cliente_{cliente_id or 'sin_cliente'}"

    def cargar_notificaciones_leidas_guardadas():
        try:
            store = getattr(page, "_mem_store", None)
            if isinstance(store, dict) and CLAVE_NOTIF_LEIDAS in store:
                raw = store.get(CLAVE_NOTIF_LEIDAS) or ""
                return set(str(raw).split("|")) if raw else set()
        except Exception:
            pass

        try:
            if hasattr(page, "client_storage"):
                raw = page.client_storage.get(CLAVE_NOTIF_LEIDAS) or ""
                return set(str(raw).split("|")) if raw else set()
        except Exception:
            pass

        return set()

    def guardar_notificaciones_leidas():
        raw = "|".join(sorted([str(x) for x in notificaciones_leidas if str(x).strip()]))

        try:
            store = getattr(page, "_mem_store", None)
            if not isinstance(store, dict):
                page._mem_store = {}
            page._mem_store[CLAVE_NOTIF_LEIDAS] = raw
        except Exception:
            pass

        try:
            if hasattr(page, "client_storage"):
                page.client_storage.set(CLAVE_NOTIF_LEIDAS, raw)
        except Exception:
            pass

    def marcar_historial_actual_como_leido_al_entrar():
        # Al iniciar sesión, los pedidos que ya existían no deben contarse como nuevos.
        if cliente_id is None:
            return

        try:
            for row in obtener_historial(cliente_id, 30) or []:
                notificaciones_leidas.add(str(row.get("IdGenerarPedido")))
            guardar_notificaciones_leidas()
        except Exception:
            pass

    notificaciones_leidas.update(cargar_notificaciones_leidas_guardadas())
    marcar_historial_actual_como_leido_al_entrar()

    # --------------------------------------------------------
    # Persistencia del carrito
    # --------------------------------------------------------
    # Antes el carrito vivía sólo en memoria (variable local): si el
    # cliente recargaba la página o se le caía la conexión, lo perdía
    # por completo. Ahora se guarda por cliente, igual que las
    # notificaciones leídas.
    CLAVE_CARRITO = f"menu_carrito_cliente_{cliente_id or 'sin_cliente'}"

    def cargar_carrito_guardado() -> dict:
        raw = None
        try:
            store = getattr(page, "_mem_store", None)
            if isinstance(store, dict) and CLAVE_CARRITO in store:
                raw = store.get(CLAVE_CARRITO)
        except Exception:
            raw = None

        if not raw:
            try:
                if hasattr(page, "client_storage"):
                    raw = page.client_storage.get(CLAVE_CARRITO)
            except Exception:
                raw = None

        if not raw:
            return {}

        try:
            datos = json.loads(raw)
            return datos if isinstance(datos, dict) else {}
        except Exception:
            return {}

    def guardar_carrito():
        raw = json.dumps(carrito)

        try:
            store = getattr(page, "_mem_store", None)
            if not isinstance(store, dict):
                page._mem_store = {}
            page._mem_store[CLAVE_CARRITO] = raw
        except Exception:
            pass

        try:
            if hasattr(page, "client_storage"):
                page.client_storage.set(CLAVE_CARRITO, raw)
        except Exception:
            pass

    carrito.update(cargar_carrito_guardado())

    # --------------------------------------------------------
    # Controles principales
    # --------------------------------------------------------
    txt_search = ft.TextField(
        hint_text="Buscar bebida...",
        border_radius=22,
        filled=True,
        bgcolor="white",
        border_color="#EED7F4",
        focused_border_color=COLOR_LILA,
        prefix_icon=_icon("SEARCH"),
        expand=True,
        height=48,
        text_style=ft.TextStyle(font_family=FUENTE_BASE, color=COLOR_TEXTO),
        hint_style=ft.TextStyle(font_family=FUENTE_BASE, color=COLOR_TEXTO_SUAVE),
    )

    lbl_total = ft.Text(
        "Total: $ 0.00",
        size=16,
        weight=ft.FontWeight.BOLD,
        color=COLOR_LILA_OSCURO,
    )

    lbl_confirmacion_pedido = ft.Text(
        "",
        size=13,
        color="#16A34A",
        weight=ft.FontWeight.BOLD,
        font_family=FUENTE_BASE,
        visible=True,
        max_lines=1,
        overflow=ft.TextOverflow.ELLIPSIS,
    )

    # El aviso "Pedido #N confirmado" vive en su propia fila, arriba del
    # total y del botón. Antes compartía fila con el botón "Realizar
    # pedido" y en pantallas angostas (celular/tablet) lo empujaba fuera
    # del área visible: el cliente ya no podía hacer un pedido nuevo.
    contenedor_confirmacion = ft.Container(
        bgcolor="#F0FDF4",
        border_radius=14,
        padding=ft.padding.symmetric(horizontal=14, vertical=8),
        border=ft.border.all(1, "#BBF7D0"),
        visible=False,
        content=ft.Row(
            controls=[
                ft.Icon(_icon("CHECK_CIRCLE", "CHECK"), color="#16A34A", size=18),
                lbl_confirmacion_pedido,
            ],
            spacing=6,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            tight=True,
        ),
    )

    titulo_seccion = _texto_titulo("Menú", size=24)
    subtitulo_seccion = _texto_normal("Elige y personaliza tus bebidas.", size=13)

    menu_list = ft.GridView(
        runs_count=2,
        max_extent=340,
        child_aspect_ratio=1.4,
        spacing=14,
        run_spacing=14,
        padding=ft.padding.only(bottom=8),
    )
    carrito_list = ft.Column(spacing=12, scroll=ft.ScrollMode.AUTO, expand=True, tight=True)
    historial_list = ft.Column(spacing=12, scroll=ft.ScrollMode.AUTO, expand=True, tight=True)
    estado_panel = ft.Column(spacing=12, scroll=ft.ScrollMode.AUTO, expand=True, tight=True)

    main_switcher = ft.AnimatedSwitcher(
        content=menu_list,
        duration=320,
        reverse_duration=220,
        transition=ft.AnimatedSwitcherTransition.FADE,
        switch_in_curve=ft.AnimationCurve.EASE_OUT,
        switch_out_curve=ft.AnimationCurve.EASE_IN,
        expand=False,
    )

    # --------------------------------------------------------
    # Funciones de cálculo
    # --------------------------------------------------------
    def calcular_total() -> float:
        total = 0.0
        for item in carrito.values():
            total += float(item.get("precio", 0)) * int(item.get("qty", 0))
        return total

    def contar_carrito() -> int:
        try:
            return sum(int(item.get("qty", 0)) for item in carrito.values())
        except Exception:
            return 0

    def actualizar_total():
        lbl_total.value = f"Total: {formatear_dinero(calcular_total())}"

    def refrescar_pagina():
        actualizar_total()
        try:
            actualizar_badge_notificaciones()
        except Exception:
            pass
        page.update()

    # --------------------------------------------------------
    # Menú
    # --------------------------------------------------------
    def abrir_personalizacion(producto: dict):
        abrir_dialogo_personalizacion(
            page=page,
            item=producto,
            formatear_dinero=formatear_dinero,
            on_confirmar=lambda prod, prep, precio: agregar_al_carrito(prod, prep, precio),
            cerrar_dialogo=_close_dialog,
            abrir_dialogo=_open_dialog,
        )

    def abrir_edicion_carrito(key: str):
        """Reabre el diálogo de personalización precargado para editar
        un producto que ya está en el carrito, en vez de tener que
        eliminarlo y agregarlo de nuevo desde cero."""
        item_actual = carrito.get(key)
        if not item_actual:
            return

        producto_ref = next(
            (b for b in bebidas if b["nombre"] == item_actual.get("nombre")),
            None,
        ) or {
            "nombre": item_actual.get("nombre", "Producto"),
            "precio": item_actual.get("precio", 0),
            "descripcion": "",
            "categoria": "",
            "emoji": "🧋",
        }

        def al_confirmar_edicion(producto, preparacion, precio_final):
            qty_actual = item_actual.get("qty", 1)
            carrito.pop(key, None)

            nueva_key = _cart_key(producto.get("nombre", "Producto"), preparacion)
            if nueva_key in carrito:
                carrito[nueva_key]["qty"] += qty_actual
            else:
                carrito[nueva_key] = {
                    "nombre": producto.get("nombre", "Producto"),
                    "precio": precio_final,
                    "qty": qty_actual,
                    "prep": preparacion,
                }

            guardar_carrito()
            build_carrito()
            refrescar_pagina()
            _show_snack(page, "Bebida actualizada en el carrito.")

        abrir_dialogo_personalizacion(
            page=page,
            item=producto_ref,
            formatear_dinero=formatear_dinero,
            on_confirmar=al_confirmar_edicion,
            cerrar_dialogo=_close_dialog,
            abrir_dialogo=_open_dialog,
            preparacion_inicial=item_actual.get("prep"),
        )

    def render_menu(e=None):
        texto = (txt_search.value or "").strip().lower()
        categoria = categoria_actual["value"]
        menu_list.controls.clear()

        productos_filtrados = [
            bebida for bebida in bebidas
            if (categoria == "Todos" or bebida["categoria"] == categoria)
            and (
                not texto
                or texto in bebida["nombre"].lower()
                or texto in bebida["descripcion"].lower()
                or texto in bebida["categoria"].lower()
            )
        ]

        if not productos_filtrados:
            menu_list.controls.append(
                tarjeta_mensaje("🔎", "No se encontraron bebidas con esa búsqueda.")
            )
        else:
            for bebida in productos_filtrados:
                menu_list.controls.append(
                    tarjeta_producto(
                        item=bebida,
                        formatear_dinero=formatear_dinero,
                        abrir_personalizacion=abrir_personalizacion,
                    )
                )

        # Solo actualizar cuando viene de un evento real, por ejemplo búsqueda.
        # En la primera carga todavía no conviene actualizar porque la vista aún no está montada.
        if e is not None:
            page.update()

    txt_search.on_change = render_menu

    # --------------------------------------------------------
    # Carrito
    # --------------------------------------------------------
    def agregar_al_carrito(producto: dict, preparacion: dict, precio_final: float):
        nombre_prod = producto.get("nombre", "Producto")
        key = _cart_key(nombre_prod, preparacion)

        if key not in carrito:
            carrito[key] = {
                "nombre": nombre_prod,
                "precio": precio_final,
                "qty": 1,
                "prep": preparacion,
            }
        else:
            carrito[key]["qty"] += 1

        guardar_carrito()
        build_carrito()
        refrescar_pagina()
        _show_snack(page, f"{nombre_prod} agregado al carrito")

    def build_carrito():
        carrito_list.controls.clear()

        if not carrito:
            carrito_list.controls.append(
                tarjeta_mensaje("🛒", "Tu carrito está vacío.")
            )
            return

        for key, item in list(carrito.items()):

            def sumar(e=None, k=key):
                if k in carrito:
                    carrito[k]["qty"] += 1
                guardar_carrito()
                build_carrito()
                refrescar_pagina()

            def restar(e=None, k=key):
                if k in carrito:
                    carrito[k]["qty"] -= 1
                    if carrito[k]["qty"] <= 0:
                        carrito.pop(k, None)
                guardar_carrito()
                build_carrito()
                refrescar_pagina()

            def eliminar(e=None, k=key):
                carrito.pop(k, None)
                guardar_carrito()
                build_carrito()
                refrescar_pagina()

            def editar(e=None, k=key):
                abrir_edicion_carrito(k)

            carrito_list.controls.append(
                tarjeta_carrito(
                    item=item,
                    sumar=sumar,
                    restar=restar,
                    eliminar=eliminar,
                    editar=editar,
                    formatear_dinero=formatear_dinero,
                    preparacion_a_texto=_preparacion_a_texto,
                )
            )

    # --------------------------------------------------------
    # Pedido
    # --------------------------------------------------------
    def checkout(e=None):
        if pedido_en_proceso["value"]:
            _show_snack(page, "Tu pedido anterior todavía se está registrando...", ok=False)
            return

        if cliente_id is None:
            _show_snack(
                page,
                "No se pudo identificar tu cuenta de cliente. Cierra sesión e inicia de nuevo.",
                ok=False,
            )
            return

        if not carrito:
            _show_snack(page, "Tu carrito está vacío.", ok=False)
            return

        # Antes el pedido se registraba directo, sin preguntar nada. Ahora
        # se confirma primero el método de pago y notas opcionales.
        dd_metodo_pago = ft.Dropdown(
            label="Método de pago",
            value="Efectivo",
            options=[
                ft.dropdown.Option("Efectivo"),
                ft.dropdown.Option("Tarjeta"),
            ],
        )
        txt_notas_generales = ft.TextField(
            label="Notas para tu pedido (opcional)",
            multiline=True,
            min_lines=2,
            max_lines=3,
            hint_text="Ej. para llevar, sin popote...",
        )

        dlg_confirmar = ft.AlertDialog(modal=True)

        btn_confirmar = ft.ElevatedButton(
            "Confirmar pedido",
            bgcolor=COLOR_LILA,
            color="white",
            icon=_icon("PAYMENT"),
        )
        btn_cancelar = ft.TextButton(
            "Cancelar",
            on_click=lambda ev: _close_dialog(page, dlg_confirmar),
        )

        def confirmar(ev=None):
            # Primera línea de defensa contra el doble toque: en cuanto se
            # pulsa, el botón queda deshabilitado y ya no puede volver a
            # disparar el evento aunque el INSERT tarde varios segundos.
            if pedido_en_proceso["value"] or btn_confirmar.disabled:
                return

            pedido_en_proceso["value"] = True
            btn_confirmar.disabled = True
            btn_confirmar.text = "Registrando..."
            btn_cancelar.disabled = True
            page.update()

            try:
                _close_dialog(page, dlg_confirmar)
                registrar_pedido_final(
                    metodo_pago=dd_metodo_pago.value,
                    notas=txt_notas_generales.value,
                )
            finally:
                pedido_en_proceso["value"] = False

        btn_confirmar.on_click = confirmar

        dlg_confirmar.title = ft.Text("Confirmar pedido")
        dlg_confirmar.content = ft.Container(
            width=400,
            content=ft.Column(
                controls=[
                    ft.Text(
                        f"Total a pagar: {formatear_dinero(calcular_total())}",
                        weight=ft.FontWeight.BOLD,
                        color="#7C3AED",
                        size=16,
                    ),
                    dd_metodo_pago,
                    txt_notas_generales,
                ],
                tight=True,
                spacing=12,
            ),
        )
        dlg_confirmar.actions = [
            btn_cancelar,
            btn_confirmar,
        ]
        dlg_confirmar.actions_alignment = ft.MainAxisAlignment.END
        _open_dialog(page, dlg_confirmar)

    def registrar_pedido_final(metodo_pago: str, notas: str):
        # Segunda línea de defensa: aunque el evento se dispare dos veces,
        # el segundo intento encuentra el carrito ya vacío y no inserta
        # nada. Así se evita el pedido fantasma con Total $0.00.
        if not carrito:
            _show_snack(
                page,
                "Tu carrito está vacío, no se registró ningún pedido nuevo.",
                ok=False,
            )
            return

        detalle_productos = []
        for item in carrito.values():
            detalle_productos.append(
                f"{item['nombre']} (x{item['qty']}) [{_preparacion_a_texto(item['prep'])}]"
            )

        producto_texto = " / ".join(detalle_productos)
        total = calcular_total()

        try:
            pedido_id = insertar_pedido(
                cliente_id=cliente_id,
                producto_texto=producto_texto,
                total=total,
                usuario_nombre=nombre,
                metodo_pago=metodo_pago,
                notas=notas,
            )

            ultimo_pedido["id"] = pedido_id

            # El pedido recién creado sí debe aparecer como nuevo hasta que el cliente lo abra.
            pedido_id_str = str(pedido_id)
            if pedido_id_str in notificaciones_leidas:
                notificaciones_leidas.remove(pedido_id_str)
            guardar_notificaciones_leidas()

            lbl_confirmacion_pedido.value = f"Pedido #{pedido_id} confirmado"
            contenedor_confirmacion.visible = True
            carrito.clear()
            guardar_carrito()
            build_carrito()
            build_historial()
            build_estado()
            actualizar_total()
            actualizar_badge_notificaciones()
            set_tab("estado")
            page.update()
        except Exception as ex:
            _show_snack(page, f"Error al registrar pedido: {ex}", ok=False)

    # --------------------------------------------------------
    # Historial
    # --------------------------------------------------------
    def abrir_detalle_pedido(row: dict):
        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text(f"Pedido #{row.get('IdGenerarPedido')}"),
            content=ft.Container(
                width=520,
                content=ft.Column(
                    controls=[
                        ft.Text(
                            f"Fecha: {row.get('FechaPedido')}  Hora: {row.get('HoraPedido')}",
                            size=12,
                            color="#666666",
                        ),
                        ft.Text(
                            f"Total: {formatear_dinero(row.get('Total') or 0)}",
                            size=15,
                            weight=ft.FontWeight.BOLD,
                            color="#7C3AED",
                        ),
                        ft.Divider(),
                        ft.Text(str(row.get("Producto") or ""), size=12),
                    ],
                    tight=True,
                    spacing=10,
                ),
            ),
            actions=[
                ft.TextButton("Cerrar", on_click=lambda e: _close_dialog(page, dlg))
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        _open_dialog(page, dlg)

    def build_historial():
        historial_list.controls.clear()

        if cliente_id is None:
            historial_list.controls.append(
                tarjeta_mensaje("⚠️", "No se pudo identificar tu cuenta de cliente.")
            )
            return

        rows = obtener_historial(cliente_id, 30)
        if not rows:
            historial_list.controls.append(
                tarjeta_mensaje("🧾", "No hay historial todavía.")
            )
            return

        for row in rows:
            historial_list.controls.append(
                tarjeta_historial(
                    row=row,
                    abrir_detalle=abrir_detalle_pedido,
                    formatear_dinero=formatear_dinero,
                )
            )

    # --------------------------------------------------------
    # Estado
    # --------------------------------------------------------
    def cancelar_pedido_actual(pedido_id):
        def confirmar(ev=None):
            _close_dialog(page, dlg)
            ok = cancelar_pedido(cliente_id, pedido_id)
            if ok:
                if ultimo_pedido["id"] == pedido_id:
                    ultimo_pedido["id"] = None
                build_estado()
                build_historial()
                actualizar_badge_notificaciones()
                _show_snack(page, f"Pedido #{pedido_id} cancelado.")
            else:
                _show_snack(
                    page,
                    "Ya no fue posible cancelar este pedido (probablemente ya está en preparación).",
                    ok=False,
                )

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("¿Cancelar pedido?"),
            content=ft.Text(f"Se cancelará el pedido #{pedido_id}. Esta acción no se puede deshacer."),
            actions=[
                ft.TextButton("No, mantenerlo", on_click=lambda ev: _close_dialog(page, dlg)),
                ft.ElevatedButton("Sí, cancelar", bgcolor="#EF4444", color="white", on_click=confirmar),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        _open_dialog(page, dlg)

    def build_estado():
        estado_panel.controls.clear()

        pedido_id_actual = ultimo_pedido["id"]

        # Si la sesión no tiene un pedido reciente en memoria (por ejemplo,
        # el cliente cerró sesión y volvió a entrar), se busca en la BD el
        # pedido más reciente que todavía siga activo.
        if not pedido_id_actual and cliente_id is not None:
            activo = obtener_pedido_activo(cliente_id)
            if activo:
                pedido_id_actual = activo.get("IdGenerarPedido")
                ultimo_pedido["id"] = pedido_id_actual

        if not pedido_id_actual:
            estado_panel.controls.append(
                tarjeta_mensaje("📦", "Aún no tienes pedidos en curso.")
            )
            return

        row = obtener_pedido(cliente_id, pedido_id_actual)
        if not row:
            estado_panel.controls.append(
                tarjeta_mensaje("⚠️", "No se pudo cargar el pedido actual.")
            )
            return

        puede_cancelar = row.get("EstatusPedido_IdEstatusPedido") == 3

        estado_panel.controls.append(
            tarjeta_estado(
                row=row,
                formatear_dinero=formatear_dinero,
                puede_cancelar=puede_cancelar,
                cancelar=lambda ev, pid=pedido_id_actual: cancelar_pedido_actual(pid),
            )
        )

    # --------------------------------------------------------
    # Navegación interna
    # --------------------------------------------------------
    def set_tab(tab_key: str):
        seccion_actual["value"] = tab_key

        if tab_key == "menu":
            titulo_seccion.value = "Menú"
            subtitulo_seccion.value = "Elige y personaliza tus bebidas."
            txt_search.visible = True
            main_switcher.content = menu_list

        elif tab_key == "carrito":
            titulo_seccion.value = "Carrito"
            subtitulo_seccion.value = "Revisa tus bebidas antes de realizar el pedido."
            txt_search.visible = False
            build_carrito()
            main_switcher.content = carrito_list

        elif tab_key == "historial":
            titulo_seccion.value = "Historial"
            subtitulo_seccion.value = "Consulta tus pedidos registrados."
            txt_search.visible = False
            build_historial()
            main_switcher.content = historial_list

        elif tab_key == "estado":
            titulo_seccion.value = "Estado"
            subtitulo_seccion.value = "Revisa el estado de tu pedido más reciente."
            txt_search.visible = False
            build_estado()
            main_switcher.content = estado_panel

        try:
            hero_banner.visible = tab_key == "menu"
            categorias_row.visible = tab_key == "menu"
        except Exception:
            pass

        page.update()

    def cerrar_sesion(e=None):
        from vistas.vista_login import LoginView

        page.views.clear()
        page.views.append(LoginView(page))
        page.go("/")
        page.update()

    # --------------------------------------------------------
    # Centro de notificaciones
    # --------------------------------------------------------
    def _id_notificacion_pedido(row: dict) -> str:
        # Se usa únicamente el ID del pedido para comparar siempre como texto.
        return str(row.get("IdGenerarPedido"))

    def contar_notificaciones() -> int:
        total = 0
        if contar_carrito() > 0 and "carrito" not in notificaciones_leidas:
            total += 1
        try:
            if cliente_id is not None:
                for row in (obtener_historial(cliente_id, 30) or []):
                    if _id_notificacion_pedido(row) not in notificaciones_leidas:
                        total += 1
        except Exception:
            pass
        return total

    badge_notificaciones = ft.Text(
        str(contar_notificaciones()),
        size=10,
        color="white",
        weight=ft.FontWeight.BOLD,
        font_family=FUENTE_BASE,
    )

    badge_notificaciones_box = ft.Container()

    def actualizar_badge_notificaciones():
        total = contar_notificaciones()
        badge_notificaciones.value = str(total)
        try:
            badge_notificaciones_box.visible = total > 0
        except Exception:
            pass

    def crear_notificacion(icono, titulo, descripcion, tiempo, color, accion, notificacion_id: str):
        leida = str(notificacion_id) in notificaciones_leidas

        def seleccionar_notificacion(ev=None):
            # Se marca como leída y se guarda ANTES de tocar la interfaz.
            notificaciones_leidas.add(str(notificacion_id))
            guardar_notificaciones_leidas()
            actualizar_badge_notificaciones()

            # Antes se hacía card.update() y page.update() aquí mismo,
            # justo cuando el diálogo estaba a punto de desmontarse: la
            # actualización se perdía o dejaba la ruta a medias. Ahora
            # sólo se cambia el estilo en memoria; la tarjeta ya se
            # dibuja gris la próxima vez que se abre el centro.
            try:
                card.bgcolor = "#E5E7EB"
                card.opacity = 0.55
                card.border = ft.border.all(1, "#D1D5DB")
            except Exception:
                pass

            # La acción se encarga de cerrar el centro y abrir lo que toque.
            accion(ev)

        card = ft.Container(
            bgcolor="#F3F4F6" if leida else "white",
            opacity=0.62 if leida else 1,
            border_radius=24,
            padding=14,
            border=ft.border.all(1, "#E5E7EB" if leida else "#EED7F4"),
            shadow=_shadow(18, 6, "#6A4A7C12"),
            ink=True,
            on_click=seleccionar_notificacion,
            animate=ft.animation.Animation(220, ft.AnimationCurve.EASE_OUT),
            content=ft.Row(
                controls=[
                    ft.Container(
                        width=48,
                        height=48,
                        border_radius=18,
                        bgcolor=color,
                        alignment=ALIGN_CENTER,
                        content=ft.Text(icono, size=23),
                    ),
                    ft.Column(
                        controls=[
                            ft.Text(titulo, size=14, weight=ft.FontWeight.BOLD, color=COLOR_TEXTO, font_family=FUENTE_BASE),
                            ft.Text(descripcion, size=12, color=COLOR_TEXTO_SUAVE, font_family=FUENTE_BASE, max_lines=2, overflow=ft.TextOverflow.ELLIPSIS),
                            ft.Text(tiempo, size=11, color="#9B8AA5", font_family=FUENTE_BASE),
                        ],
                        spacing=2,
                        expand=True,
                    ),
                    ft.Icon(_icon("CHEVRON_RIGHT", "KEYBOARD_ARROW_RIGHT"), color=COLOR_LILA),
                ],
                spacing=12,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )

        def hover(e):
            card.scale = 1.015 if e.data == "true" else 1
            if not (card.opacity and card.opacity < 1):
                card.bgcolor = "#FFF9FD" if e.data == "true" else "white"
            card.update()

        card.on_hover = hover
        return card

    def abrir_centro_notificaciones(e=None):
        notificaciones = []

        if contar_carrito() > 0:
            notificaciones.append(
                crear_notificacion(
                    "🛒",
                    "Carrito pendiente",
                    f"Tienes {contar_carrito()} bebida(s) listas para confirmar.",
                    "Ahora",
                    "#FCE7F3",
                    lambda ev=None: (_close_dialog(page, dlg_notif), set_tab("carrito")),
                    "carrito",
                )
            )

        rows = []
        try:
            if cliente_id is not None:
                rows = obtener_historial(cliente_id, 30) or []
        except Exception:
            rows = []

        for row in rows:
            estado = str(row.get("Estatus") or "Pedido Realizado")
            pedido_id = row.get("IdGenerarPedido")
            estado_lower = estado.lower()

            if "listo" in estado_lower:
                icono, color, descripcion = "✅", "#DCFCE7", "Tu bebida está lista para recoger."
            elif "prepar" in estado_lower:
                icono, color, descripcion = "🧋", "#F3E8FF", "Nuestros baristas están preparando tu bebida."
            elif "entreg" in estado_lower:
                icono, color, descripcion = "🎉", "#FEF3C7", "Pedido entregado. Esperamos que lo disfrutes."
            elif "cobrad" in estado_lower:
                icono, color, descripcion = "💳", "#E0F2FE", "Tu pago fue registrado correctamente."
            else:
                icono, color, descripcion = "📦", "#FCE7F3", "Tu pedido fue recibido correctamente."

            notificaciones.append(
                crear_notificacion(
                    icono,
                    f"Pedido #{pedido_id} - {estado}",
                    descripcion,
                    f"{row.get('FechaPedido')}  {row.get('HoraPedido')}",
                    color,
                    lambda ev=None, r=row: (_close_dialog(page, dlg_notif), abrir_detalle_pedido(r)),
                    _id_notificacion_pedido(row),
                )
            )

        if not notificaciones:
            notificaciones.append(tarjeta_mensaje("🔔", "Aún no tienes notificaciones."))

        dlg_notif = ft.AlertDialog(
            modal=True,
            title=ft.Row(
                controls=[
                    ft.Text("🔔", size=20),
                    _texto_titulo("Centro de notificaciones", size=20),
                    ft.Container(expand=True),
                    ft.IconButton(icon=_icon("CLOSE"), on_click=lambda ev: _close_dialog(page, dlg_notif)),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            content=ft.Container(
                width=560,
                height=520,
                content=ft.Column(
                    controls=[
                        _texto_normal("Todo lo relacionado con tu menú, carrito y estados de pedidos.", size=12),
                        ft.Row(
                            controls=[
                                ft.Container(
                                    border_radius=18,
                                    padding=ft.padding.symmetric(horizontal=12, vertical=8),
                                    bgcolor=COLOR_LILA,
                                    content=ft.Text("Todas", color="white", weight=ft.FontWeight.BOLD, font_family=FUENTE_BASE),
                                ),
                                ft.Container(
                                    border_radius=18,
                                    padding=ft.padding.symmetric(horizontal=12, vertical=8),
                                    bgcolor="#F8EDFF",
                                    content=ft.Text("Pedidos", color=COLOR_LILA_OSCURO, weight=ft.FontWeight.BOLD, font_family=FUENTE_BASE),
                                ),
                                ft.Container(
                                    border_radius=18,
                                    padding=ft.padding.symmetric(horizontal=12, vertical=8),
                                    bgcolor="#F8EDFF",
                                    content=ft.Text("Carrito", color=COLOR_LILA_OSCURO, weight=ft.FontWeight.BOLD, font_family=FUENTE_BASE),
                                ),
                            ],
                            spacing=8,
                            scroll=ft.ScrollMode.AUTO,
                        ),
                        ft.Column(controls=notificaciones, spacing=12, scroll=ft.ScrollMode.AUTO, expand=True),
                        ft.ElevatedButton(
                            "Ver todos mis pedidos",
                            icon=_icon("RECEIPT_LONG", "HISTORY"),
                            bgcolor=COLOR_ROSA_FUERTE,
                            color="white",
                            on_click=lambda ev: (_close_dialog(page, dlg_notif), set_tab("historial")),
                            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=20), padding=18),
                        ),
                    ],
                    spacing=12,
                    expand=True,
                ),
            ),
            actions_alignment=ft.MainAxisAlignment.END,
        )
        _open_dialog(page, dlg_notif)

    # --------------------------------------------------------
    # Sidebar
    # --------------------------------------------------------
    sidebar = build_menu_sidebar(
        page=page,
        nombre=nombre,
        cliente_id=cliente_id,
        ir_menu=lambda e=None: set_tab("menu"),
        ir_carrito=lambda e=None: set_tab("carrito"),
        ir_historial=lambda e=None: set_tab("historial"),
        ir_estado=lambda e=None: set_tab("estado"),
        cerrar_sesion_real=cerrar_sesion,
        get_current_tab=lambda: seccion_actual["value"],
        get_cart_count=contar_carrito,
    )

    # --------------------------------------------------------
    # Layout visual
    # --------------------------------------------------------
    # Tarjeta superior tipo portada: tonos suaves, formas redondeadas y tipografía serif.
    hero_banner = ft.Container(
        height=160,
        border_radius=32,
        padding=ft.padding.symmetric(horizontal=28, vertical=22),
        bgcolor="#FBE7F4",
        border=ft.border.all(1, "#F2D4E6"),
        shadow=_shadow(30, 10, "#6A4A7C18"),
        animate=ft.animation.Animation(320, ft.AnimationCurve.EASE_OUT),
        content=ft.Stack(
            controls=[
                ft.Container(
                    right=-30,
                    top=-40,
                    width=190,
                    height=190,
                    border_radius=95,
                    bgcolor="#E9C7F3",
                    opacity=0.65,
                ),
                ft.Container(
                    right=80,
                    bottom=-60,
                    width=170,
                    height=120,
                    border_radius=60,
                    bgcolor=COLOR_CREMA,
                    opacity=0.85,
                ),
                ft.Container(
                    left=-55,
                    bottom=-75,
                    width=150,
                    height=150,
                    border_radius=75,
                    bgcolor="#D7B8E8",
                    opacity=0.55,
                ),
                ft.Row(
                    controls=[
                        ft.Column(
                            controls=[
                                _texto_titulo(f"¡Hola, {nombre}!", size=30, color=COLOR_MORADO),
                                _texto_normal("¿Qué té boba delicioso vas a pedir hoy?", size=15, color=COLOR_TEXTO),
                                ft.Row(
                                    controls=[
                                        ft.ElevatedButton(
                                            "Explorar menú",
                                            icon=_icon("LOCAL_CAFE", "RESTAURANT_MENU"),
                                            bgcolor=COLOR_ROSA_FUERTE,
                                            color="white",
                                            on_click=lambda e: set_tab("menu"),
                                            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=22), padding=18),
                                        ),
                                        ft.OutlinedButton(
                                            "Mis pedidos",
                                            icon=_icon("RECEIPT_LONG", "HISTORY"),
                                            on_click=lambda e: set_tab("historial"),
                                            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=22), padding=18),
                                        ),
                                    ],
                                    spacing=12,
                                ),
                            ],
                            spacing=10,
                            expand=True,
                        ),
                        ft.Container(
                            width=120,
                            height=120,
                            border_radius=40,
                            bgcolor=COLOR_FONDO_SUAVE,
                            alignment=ALIGN_CENTER,
                            shadow=_shadow(24, 8, "#EC489933"),
                            content=ft.Text("🧋", size=62),
                            animate_scale=ft.Animation(260, ft.AnimationCurve.EASE_OUT),
                        ),
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            ],
        ),
    )

    # Antes estos chips eran puramente decorativos (sin on_click) y ni
    # siquiera coincidían con las categorías reales de las bebidas. Ahora
    # se generan a partir de las categorías presentes en el catálogo y
    # sí filtran el grid al hacer clic.
    EMOJIS_CATEGORIA = {
        "Todos": "🧋",
        "Milk Tea": "🍓",
        "Especialidad": "🍵",
        "Clásicos": "🍫",
        "Smoothies": "🍒",
        "Frappés": "🍦",
        "General": "✨",
    }

    chips_categorias = []  # (contenedor, texto_ctrl, nombre_cat)

    def _repintar_categorias():
        for contenedor, texto_ctrl, nombre_cat in chips_categorias:
            seleccionado = nombre_cat == categoria_actual["value"]
            contenedor.bgcolor = COLOR_LILA if seleccionado else "white"
            contenedor.border = None if seleccionado else ft.border.all(1, "#EED7F4")
            contenedor.shadow = _shadow(20, 6, "#C86DD733") if seleccionado else None
            texto_ctrl.color = "white" if seleccionado else COLOR_TEXTO

    def _construir_chip_categoria(nombre_cat: str, emoji_cat: str):
        texto_ctrl = ft.Text(
            nombre_cat, color=COLOR_TEXTO, weight=ft.FontWeight.BOLD, font_family=FUENTE_BASE
        )

        def click(e=None, cat=nombre_cat):
            categoria_actual["value"] = cat
            _repintar_categorias()
            render_menu(e=True)

        contenedor = ft.Container(
            border_radius=22,
            padding=ft.padding.symmetric(horizontal=16, vertical=12),
            bgcolor="white",
            border=ft.border.all(1, "#EED7F4"),
            ink=True,
            on_click=click,
            content=ft.Row([ft.Text(emoji_cat), texto_ctrl], spacing=8),
        )
        chips_categorias.append((contenedor, texto_ctrl, nombre_cat))
        return contenedor

    nombres_categorias = ["Todos"]
    for _bebida in bebidas:
        _cat = _bebida["categoria"]
        if _cat not in nombres_categorias:
            nombres_categorias.append(_cat)

    categorias_row = ft.Row(
        controls=[
            _construir_chip_categoria(cat, EMOJIS_CATEGORIA.get(cat, "✨"))
            for cat in nombres_categorias
        ],
        spacing=10,
        scroll=ft.ScrollMode.AUTO,
    )
    _repintar_categorias()

    badge_notificaciones_box.right = 2
    badge_notificaciones_box.top = 2
    badge_notificaciones_box.width = 22
    badge_notificaciones_box.height = 22
    badge_notificaciones_box.border_radius = 11
    badge_notificaciones_box.bgcolor = COLOR_ROSA_FUERTE
    badge_notificaciones_box.alignment = ALIGN_CENTER
    badge_notificaciones_box.content = badge_notificaciones

    btn_notificaciones = ft.Container(
        width=58,
        height=58,
        border_radius=22,
        bgcolor="white",
        alignment=ALIGN_CENTER,
        ink=True,
        on_click=abrir_centro_notificaciones,
        shadow=_shadow(24, 8, "#6A4A7C22"),
        animate_scale=ft.Animation(200, ft.AnimationCurve.EASE_OUT),
        content=ft.Stack(
            controls=[
                ft.Container(
                    alignment=ALIGN_CENTER,
                    content=ft.Icon(_icon("NOTIFICATIONS", "NOTIFICATIONS_NONE"), color=COLOR_MORADO, size=27),
                ),
                badge_notificaciones_box,
            ],
        ),
    )

    def hover_notificaciones(e):
        btn_notificaciones.scale = 1.08 if e.data == "true" else 1
        btn_notificaciones.update()

    btn_notificaciones.on_hover = hover_notificaciones

    header = ft.Container(
        padding=ft.padding.symmetric(horizontal=22, vertical=14),
        bgcolor=COLOR_FONDO_SUAVE,
        border=ft.border.only(bottom=ft.border.BorderSide(1, "#F2D4E6")),
        content=ft.Row(
            controls=[
                ft.Container(
                    width=60,
                    height=60,
                    border_radius=22,
                    bgcolor="#FBE7F4",
                    alignment=ALIGN_CENTER,
                    shadow=_shadow(18, 5, "#C86DD722"),
                    content=ft.Text("🧋", size=32),
                ),
                ft.Column(
                    controls=[
                        _texto_titulo("Corallie Bubble", size=22, color=COLOR_ROSA_FUERTE),
                        _texto_normal("Menú Interactivo", size=12),
                    ],
                    spacing=0,
                    expand=True,
                ),
                btn_notificaciones,
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
    )
    body = ft.Container(
        expand=True,
        padding=ft.padding.only(left=14, right=14, top=10, bottom=8),
        content=ft.Column(
            controls=[
                hero_banner,
                categorias_row,
                ft.Row(
                    controls=[
                        ft.Column([titulo_seccion, subtitulo_seccion], spacing=2, expand=True),
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                txt_search,
                main_switcher,
            ],
            spacing=14,
            scroll=ft.ScrollMode.AUTO,
        ),
    )

    bottom_bar = ft.Container(
        padding=ft.padding.symmetric(horizontal=18, vertical=14),
        bgcolor="#FFFFFF",
        border=ft.border.only(top=ft.border.BorderSide(1, "#F2D4E6")),
        shadow=_shadow(20, -4, "#6A4A7C0D"),
        content=ft.Column(
            controls=[
                contenedor_confirmacion,
                ft.Row(
                    controls=[
                        ft.Row(
                            controls=[
                                ft.Text("🛒", size=18),
                                lbl_total,
                            ],
                            spacing=8,
                            expand=True,
                        ),
                        ft.ElevatedButton(
                            "Realizar pedido",
                            bgcolor=COLOR_LILA,
                            color="white",
                            icon=_icon("PAYMENT"),
                            on_click=checkout,
                            style=ft.ButtonStyle(
                                shape=ft.RoundedRectangleBorder(radius=18),
                                padding=18,
                            ),
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            ],
            spacing=10,
            tight=True,
        ),
    )

    contenido_principal = ft.Column(
        controls=[
            header,
            body,
            bottom_bar,
        ],
        expand=True,
        spacing=0,
    )

    layout = ft.Row(
        controls=[
            sidebar,
            contenido_principal,
        ],
        expand=True,
        spacing=0,
        vertical_alignment=ft.CrossAxisAlignment.STRETCH,
    )

    # --------------------------------------------------------
    # Primera carga
    # --------------------------------------------------------
    render_menu()
    build_carrito()
    build_historial()
    build_estado()
    actualizar_total()
    actualizar_badge_notificaciones()

    return ft.View(
        route="/menu",
        controls=[layout],
        bgcolor=COLOR_FONDO_SUAVE,
        padding=0,
    )