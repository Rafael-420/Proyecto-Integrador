"""Panel del administrador para el horario del local y el servicio de pedidos.

Desde aquí el administrador controla cuándo pueden pedir los clientes
desde el menú:

  - Pausar o reanudar el servicio de pedidos (mantenimiento, falta de
    insumos, cierre imprevisto) con un mensaje para los clientes.
  - Capturar el horario de cada día de la semana y los días de descanso.
  - Registrar fechas puntuales en las que el local no abre.
  - Definir cuántos minutos antes del cierre se dejan de recibir pedidos.

Con el servicio pausado o fuera de horario, el menú sigue abierto para
navegar; solo se deshabilita el botón de pedir. Las reglas viven en
servicios/servicio_horario.py.
"""

import flet as ft

from componentes.appbar_admin import build_admin_appbar
from componentes.sidebar_admin import admin_layout, build_admin_sidebar
from servicios.servicio_horario import (
    DIAS_SEMANA,
    LARGO_MENSAJE_MAXIMO,
    LARGO_MOTIVO_MAXIMO,
    MARGEN_CIERRE_DEFECTO,
    FechaDuplicada,
    agregar_dia_cerrado,
    eliminar_dia_cerrado,
    formatear_hora,
    guardar_horarios,
    guardar_servicio_menu,
    obtener_configuracion,
    parsear_fecha,
    parsear_hora,
)
from utilidades.flet_compat import abrir_dialogo, cerrar_dialogo, icono, set_error


COLOR_PRINCIPAL = "#C86DD7"
COLOR_FONDO = "#F9F6FB"
COLOR_TEXTO = "#333333"
COLOR_TEXTO_SUAVE = "#666666"
COLOR_VERDE = "#16A34A"
COLOR_VERDE_FONDO = "#F0FDF4"
COLOR_ROJO = "#DC2626"
COLOR_AMBAR_FONDO = "#FFF7ED"


def _show_snack(page: ft.Page, texto: str, ok: bool = True):
    try:
        snack = ft.SnackBar(
            content=ft.Text(texto, color="white"),
            bgcolor="#22C55E" if ok else "#EF4444",
        )
        if hasattr(page, "overlay") and snack not in page.overlay:
            page.overlay.append(snack)
        snack.open = True
        page.update()
    except Exception:
        pass


def _usuario_sesion(page: ft.Page, respaldo: str) -> str:
    """Usuario del administrador guardado al iniciar sesión.

    El router reconstruye esta vista con el nombre genérico
    "Administrador"; el usuario real se guarda en el login.
    """
    try:
        store = getattr(page, "_mem_store", None)
        if isinstance(store, dict) and store.get("admin"):
            return str(store["admin"])
    except Exception:
        pass
    return respaldo or "Administrador"


def _tarjeta(titulo: str, subtitulo: str | None, *controles, relleno: int = 20) -> ft.Container:
    encabezado = [ft.Text(titulo, size=17, weight=ft.FontWeight.BOLD, color=COLOR_TEXTO)]
    if subtitulo:
        encabezado.append(ft.Text(subtitulo, size=13, color=COLOR_TEXTO_SUAVE))
    return ft.Container(
        bgcolor="white",
        border_radius=20,
        padding=relleno,
        border=ft.border.all(1, "#EEE3F3"),
        content=ft.Column(
            controls=[ft.Column(encabezado, spacing=2), *controles],
            spacing=14,
        ),
    )


def _marcar_error(campo: ft.TextField, mensaje: str | None):
    # set_error elige la propiedad que dibuja cada versión de Flet
    # (error_text en 0.28, error en 0.80+).
    set_error(campo, mensaje)


def admin_servicio_view(page: ft.Page, nombre: str) -> ft.View:
    usuario_admin = _usuario_sesion(page, nombre)

    # Responsive, igual que en inventario: menos relleno en el celular y
    # filas que se acomodan en columnas (ResponsiveRow) en lugar de
    # anchos fijos. En el celular el sidebar se abre encima del
    # contenido (admin_layout), así que el contenido conserva su ancho.
    ancho_pagina = getattr(page, "width", None) or 1200
    es_movil = ancho_pagina < 700
    relleno = 14 if es_movil else 20

    contenido = ft.Column(spacing=16, scroll=ft.ScrollMode.AUTO, expand=True)

    def actualizar():
        try:
            page.update()
        except Exception:
            pass

    def confirmar(titulo: str, mensaje: str, texto_boton: str, al_aceptar):
        dlg = ft.AlertDialog(
            title=ft.Text(titulo),
            content=ft.Text(mensaje),
        )

        def aceptar(e=None):
            cerrar_dialogo(page, dlg)
            al_aceptar()

        dlg.actions = [
            ft.TextButton("Cancelar", on_click=lambda e: cerrar_dialogo(page, dlg)),
            ft.ElevatedButton(texto_boton, bgcolor=COLOR_PRINCIPAL, color="white", on_click=aceptar),
        ]
        dlg.actions_alignment = ft.MainAxisAlignment.END
        abrir_dialogo(page, dlg)

    # --------------------------------------------------------
    # Estado actual
    # --------------------------------------------------------
    def tarjeta_estado(config: dict) -> ft.Container:
        estado = config["estado"]
        ahora = config["ahora"]
        hora_texto = f"{DIAS_SEMANA[ahora.weekday()]} {ahora.strftime('%d/%m/%Y %H:%M')}"

        if estado["abierto"]:
            if estado["motivo"] == "sin_horario":
                detalle = "No hay horario capturado: el menú recibe pedidos a cualquier hora."
            else:
                detalle = f"Los clientes pueden pedir hasta las {formatear_hora(estado['cierre_pedidos'].time())}."
            titulo, color, fondo, emoji = "Recibiendo pedidos", COLOR_VERDE, COLOR_VERDE_FONDO, "🟢"
        else:
            detalle = f"Los clientes ven: «{estado['mensaje']}»"
            titulo, color, fondo, emoji = "Sin recibir pedidos", COLOR_ROJO, COLOR_AMBAR_FONDO, "🔴"

        # Antes el emoji, el texto y el botón iban en una sola fila; con
        # poco ancho el texto se mostraba una letra por renglón. Ahora el
        # título va en su propio renglón y el detalle ocupa todo el ancho.
        return ft.Container(
            bgcolor=fondo,
            border_radius=20,
            padding=relleno,
            border=ft.border.all(1, "#EEE3F3"),
            content=ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            ft.Text(
                                "Menú de clientes",
                                size=12,
                                weight=ft.FontWeight.BOLD,
                                color=COLOR_TEXTO_SUAVE,
                                expand=True,
                            ),
                            ft.IconButton(
                                icon=icono("REFRESH", "AUTORENEW"),
                                tooltip="Actualizar",
                                on_click=recargar,
                            ),
                        ],
                        spacing=4,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Text(
                        f"{emoji} {titulo}",
                        size=17,
                        weight=ft.FontWeight.BOLD,
                        color=color,
                    ),
                    ft.Text(detalle, size=13, color=COLOR_TEXTO),
                    ft.Text(f"Hora del local: {hora_texto}", size=12, color=COLOR_TEXTO_SUAVE),
                ],
                spacing=4,
            ),
        )

    # --------------------------------------------------------
    # Interruptor del servicio
    # --------------------------------------------------------
    def tarjeta_servicio(config: dict) -> ft.Container:
        servicio = config["servicio"]

        sw_activo = ft.Switch(
            value=servicio["menu_activo"],
            active_color=COLOR_PRINCIPAL,
        )
        # El texto va aparte del Switch para que pueda partirse en
        # renglones; como etiqueta del Switch se cortaba en pantalla angosta.
        fila_switch = ft.Row(
            controls=[
                sw_activo,
                ft.Text("Recibir pedidos desde el menú", size=14, color=COLOR_TEXTO, expand=True),
            ],
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
        txt_mensaje = ft.TextField(
            label="Mensaje para los clientes",
            hint_text="Ej. Cerrado por mantenimiento, volvemos a las 4 pm.",
            value=servicio.get("mensaje") or "",
            max_length=LARGO_MENSAJE_MAXIMO,
            multiline=True,
            min_lines=1,
            max_lines=3,
        )
        txt_margen = ft.TextField(
            label="Minutos antes del cierre",
            value=str(servicio.get("margen", MARGEN_CIERRE_DEFECTO)),
            keyboard_type=ft.KeyboardType.NUMBER,
        )

        ultimo_cambio = []
        if servicio.get("fecha_modificacion"):
            fecha = servicio["fecha_modificacion"]
            texto_fecha = fecha.strftime("%d/%m/%Y %H:%M") if hasattr(fecha, "strftime") else str(fecha)
            quien = servicio.get("modificado_por") or "—"
            ultimo_cambio.append(
                ft.Text(f"Último cambio: {quien}, {texto_fecha}", size=12, color=COLOR_TEXTO_SUAVE)
            )

        def guardar_ahora():
            _marcar_error(txt_margen, None)
            _marcar_error(txt_mensaje, None)
            try:
                guardar_servicio_menu(
                    bool(sw_activo.value),
                    txt_mensaje.value,
                    (txt_margen.value or "").strip() or 0,
                    usuario_admin,
                )
            except ValueError as error:
                campo = txt_mensaje if "mensaje" in str(error).lower() else txt_margen
                _marcar_error(campo, str(error))
                actualizar()
                return
            except Exception as error:
                _show_snack(page, f"No se pudo guardar: {error}", ok=False)
                return

            _show_snack(
                page,
                "Servicio de pedidos activo." if sw_activo.value else "Servicio de pedidos pausado.",
            )
            recargar()

        def guardar(e=None):
            if servicio["menu_activo"] and not sw_activo.value:
                confirmar(
                    "Pausar pedidos del menú",
                    "Los clientes podrán ver el menú pero no hacer pedidos hasta que "
                    "lo vuelvas a activar. Los pedidos que ya están hechos se siguen "
                    "atendiendo con normalidad.",
                    "Pausar pedidos",
                    guardar_ahora,
                )
            else:
                guardar_ahora()

        return _tarjeta(
            "Servicio de pedidos del menú",
            "Pausa los pedidos en cualquier momento, sin importar el horario.",
            fila_switch,
            txt_mensaje,
            ft.Column(
                controls=[
                    txt_margen,
                    ft.Text(
                        "Tiempo antes de cerrar en que se dejan de recibir pedidos.",
                        size=12,
                        color=COLOR_TEXTO_SUAVE,
                    ),
                ],
                spacing=4,
            ),
            *ultimo_cambio,
            ft.Row(
                controls=[
                    ft.ElevatedButton(
                        "Guardar",
                        icon=icono("SAVE"),
                        bgcolor=COLOR_PRINCIPAL,
                        color="white",
                        on_click=guardar,
                    )
                ],
                alignment=ft.MainAxisAlignment.END,
            ),
            relleno=relleno,
        )

    # --------------------------------------------------------
    # Horario semanal
    # --------------------------------------------------------
    def tarjeta_horario(config: dict) -> ft.Container:
        horarios = config["horarios"]
        filas = []
        campos = {}

        for dia in range(7):
            datos = horarios.get(dia) or {"abierto": False, "apertura": None, "cierre": None}
            txt_abre = ft.TextField(
                label="Abre",
                value=formatear_hora(datos["apertura"]) or "10:00",
                dense=True,
                disabled=not datos["abierto"],
                col={"xs": 6, "md": 4},
            )
            txt_cierra = ft.TextField(
                label="Cierra",
                value=formatear_hora(datos["cierre"]) or "21:00",
                dense=True,
                disabled=not datos["abierto"],
                col={"xs": 6, "md": 4},
            )
            chk = ft.Checkbox(
                label=DIAS_SEMANA[dia],
                value=datos["abierto"],
                col={"xs": 12, "md": 4},
            )

            def al_cambiar(e=None, a=txt_abre, c=txt_cierra, k=chk):
                a.disabled = not k.value
                c.disabled = not k.value
                actualizar()

            chk.on_change = al_cambiar
            campos[dia] = (chk, txt_abre, txt_cierra)
            # Con espacio: día y horas en una fila. En el celular: el día
            # arriba y las dos horas debajo, mitad y mitad.
            filas.append(
                ft.ResponsiveRow(
                    controls=[chk, txt_abre, txt_cierra],
                    spacing=10,
                    run_spacing=4,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                )
            )

        def guardar(e=None):
            nuevos = {}
            hay_error = False
            for dia, (chk, txt_abre, txt_cierra) in campos.items():
                _marcar_error(txt_abre, None)
                _marcar_error(txt_cierra, None)
                horas = {}
                respaldos = {"apertura": "10:00", "cierre": "21:00"}
                for clave, campo in (("apertura", txt_abre), ("cierre", txt_cierra)):
                    try:
                        horas[clave] = parsear_hora(campo.value)
                    except ValueError as error:
                        if chk.value:
                            _marcar_error(campo, str(error))
                            hay_error = True
                        else:
                            # En un día de descanso las horas no se usan.
                            horas[clave] = parsear_hora(respaldos[clave])
                if len(horas) == 2 and chk.value and horas["cierre"] <= horas["apertura"]:
                    _marcar_error(txt_cierra, "Debe ser después de la apertura")
                    hay_error = True
                nuevos[dia] = {"abierto": bool(chk.value), **horas}

            if hay_error:
                _show_snack(page, "Revisa las horas marcadas en rojo.", ok=False)
                actualizar()
                return

            try:
                guardar_horarios(nuevos)
            except ValueError as error:
                _show_snack(page, str(error), ok=False)
                return
            except Exception as error:
                _show_snack(page, f"No se pudo guardar el horario: {error}", ok=False)
                return

            _show_snack(page, "Horario guardado.")
            recargar()

        return _tarjeta(
            "Horario semanal",
            "Desmarca los días de descanso. Usa formato de 24 horas, por ejemplo 09:30 o 21:00.",
            *filas,
            ft.Row(
                controls=[
                    ft.ElevatedButton(
                        "Guardar",
                        icon=icono("SAVE"),
                        bgcolor=COLOR_PRINCIPAL,
                        color="white",
                        on_click=guardar,
                    )
                ],
                alignment=ft.MainAxisAlignment.END,
            ),
            relleno=relleno,
        )

    # --------------------------------------------------------
    # Días cerrados
    # --------------------------------------------------------
    def tarjeta_dias_cerrados(config: dict) -> ft.Container:
        hoy = config["ahora"].date()

        txt_fecha = ft.TextField(
            label="Fecha",
            hint_text="DD/MM/AAAA",
            keyboard_type=ft.KeyboardType.DATETIME,
            dense=True,
            col={"xs": 12, "md": 4},
        )
        txt_motivo = ft.TextField(
            label="Motivo (opcional)",
            hint_text="Ej. Día festivo, vacaciones",
            max_length=LARGO_MOTIVO_MAXIMO,
            dense=True,
            col={"xs": 12, "md": 5},
        )

        def agregar(e=None):
            _marcar_error(txt_fecha, None)
            try:
                fecha = parsear_fecha(txt_fecha.value)
                agregar_dia_cerrado(fecha, txt_motivo.value, hoy=hoy)
            except (ValueError, FechaDuplicada) as error:
                _marcar_error(txt_fecha, str(error))
                actualizar()
                return
            except Exception as error:
                _show_snack(page, f"No se pudo agregar la fecha: {error}", ok=False)
                return

            _show_snack(page, f"El {fecha.strftime('%d/%m/%Y')} quedó marcado como cerrado.")
            recargar()

        def quitar(dia: dict):
            def hacer():
                try:
                    eliminar_dia_cerrado(dia["id"])
                except Exception as error:
                    _show_snack(page, f"No se pudo quitar la fecha: {error}", ok=False)
                    return
                _show_snack(page, "Fecha quitada.")
                recargar()

            confirmar(
                "Quitar día cerrado",
                f"El {dia['fecha'].strftime('%d/%m/%Y')} el menú volverá a recibir pedidos según el horario.",
                "Quitar",
                hacer,
            )

        lista = []
        for dia in config["dias_cerrados"]:
            fecha = dia["fecha"]
            texto = f"{DIAS_SEMANA[fecha.weekday()]} {fecha.strftime('%d/%m/%Y')}"
            if dia.get("motivo"):
                texto += f" · {dia['motivo']}"
            lista.append(
                ft.Row(
                    controls=[
                        ft.Text("📅", size=16),
                        ft.Text(texto, size=14, color=COLOR_TEXTO, expand=True),
                        ft.IconButton(
                            icon=icono("DELETE_OUTLINE", "DELETE"),
                            icon_color=COLOR_ROJO,
                            tooltip="Quitar",
                            on_click=lambda e, d=dia: quitar(d),
                        ),
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                )
            )
        if not lista:
            lista.append(ft.Text("No hay fechas cerradas próximas.", size=13, color=COLOR_TEXTO_SUAVE))

        return _tarjeta(
            "Días cerrados",
            "Festivos, vacaciones o cierres imprevistos. Esos días el menú no recibe pedidos.",
            # Antes era un Row con wrap y un campo con expand=True: esa
            # combinación no tiene ancho definido y Flutter dibujaba un
            # recuadro gris en lugar del formulario.
            ft.ResponsiveRow(
                controls=[
                    txt_fecha,
                    txt_motivo,
                    ft.Container(
                        col={"xs": 12, "md": 3},
                        content=ft.ElevatedButton(
                            "Agregar",
                            icon=icono("ADD"),
                            bgcolor=COLOR_PRINCIPAL,
                            color="white",
                            on_click=agregar,
                        ),
                    ),
                ],
                spacing=10,
                run_spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.START,
            ),
            *lista,
            relleno=relleno,
        )

    # --------------------------------------------------------
    # Carga
    # --------------------------------------------------------
    def recargar(e=None):
        contenido.controls.clear()
        try:
            config = obtener_configuracion()
        except Exception as error:
            contenido.controls.append(
                _tarjeta(
                    "No se pudo leer la configuración",
                    "Verifica la conexión y que se haya aplicado la migración "
                    "recursos/sql/migracion_horario.sql.",
                    ft.Text(str(error), size=12, color=COLOR_ROJO, selectable=True),
                    ft.ElevatedButton("Reintentar", on_click=recargar),
                    relleno=relleno,
                )
            )
            actualizar()
            return

        contenido.controls.extend(
            [
                tarjeta_estado(config),
                tarjeta_servicio(config),
                tarjeta_horario(config),
                tarjeta_dias_cerrados(config),
            ]
        )
        actualizar()

    # --------------------------------------------------------
    # Navegación / layout
    # --------------------------------------------------------
    def ir_inicio(e=None):
        from vistas.vista_admin import admin_view
        page.views.append(admin_view(page, nombre))
        page.go("/admin")
        page.update()

    def ir_control_empleados(e=None):
        from vistas.vista_admin_empleados import admin_empleados_view
        page.views.append(admin_empleados_view(page, nombre))
        page.go("/admin_empleados")
        page.update()

    def ir_control_usuarios(e=None):
        from vistas.vista_admin_usuarios import admin_usuarios_view
        page.views.append(admin_usuarios_view(page, nombre))
        page.go("/admin_usuarios")
        page.update()

    def ir_reportes(e=None):
        from vistas.vista_generar_reportes import generar_reportes_view
        page.views.append(generar_reportes_view(page, nombre))
        page.go("/reportes")
        page.update()

    def ir_bebidas(e=None):
        from vistas.vista_admin_bebidas import admin_bebidas_view
        page.views.append(admin_bebidas_view(page, nombre))
        page.go("/admin_bebidas")
        page.update()

    def cerrar_sesion(e=None):
        from vistas.vista_login import LoginView
        page.views.clear()
        page.views.append(LoginView(page))
        page.go("/")
        page.update()

    sidebar = build_admin_sidebar(
        page=page,
        nombre=nombre,
        ir_inicio=ir_inicio,
        ir_control_empleados=ir_control_empleados,
        ir_control_usuarios=ir_control_usuarios,
        cerrar_sesion_real=cerrar_sesion,
        ir_reportes=ir_reportes,
        ir_bebidas=ir_bebidas,
        ir_servicio=lambda e: recargar(),
    )

    header = ft.Column(
        controls=[
            ft.Text("Horario y servicio", size=20, weight=ft.FontWeight.BOLD, color=COLOR_PRINCIPAL),
            ft.Text(
                "Controla cuándo pueden hacer pedidos los clientes desde el menú.",
                size=13,
                color=COLOR_TEXTO_SUAVE,
            ),
        ],
        spacing=2,
    )

    main_content = ft.Container(
        expand=True,
        bgcolor=COLOR_FONDO,
        padding=12 if es_movil else 20,
        content=ft.Column(controls=[header, contenido], expand=True, spacing=14),
    )

    layout = admin_layout(page, sidebar, main_content)

    recargar()

    return ft.View(
        route="/admin_servicio",
        appbar=build_admin_appbar(page, "Corallie Bubble - Admin"),
        controls=[layout],
        bgcolor=COLOR_FONDO,
        padding=0,
    )