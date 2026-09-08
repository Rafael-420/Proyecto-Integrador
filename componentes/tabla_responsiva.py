"""Tabla que se adapta al ancho de la pantalla.

En escritorio dibuja un ft.DataTable normal, como siempre.
En pantallas angostas (celular) dibuja una tarjeta por registro, para
no obligar al usuario a arrastrar la tabla de lado a lado.

Motivo: las tablas del panel de administración tienen 7 columnas. En un
celular sólo caben dos a la vez, así que para leer un dato había que
hacer scroll horizontal y se perdía de vista a quién pertenecía la fila.
Además, el criterio 1.4.10 (Reflow) de la WCAG 2.1 pide que el contenido
no exija desplazamiento horizontal a 320 px de ancho.

Uso típico:

    tabla = TablaResponsiva(
        page,
        columnas=[
            ColumnaTabla("ID", "IdCliente", icono="TAG"),
            ColumnaTabla("Nombre", "Nombre", en_tarjeta=False),
            ColumnaTabla("Teléfono", "Telefono", icono="PHONE"),
        ],
        acciones=[
            AccionTabla("Editar", abrir_editar, icono="EDIT"),
            AccionTabla("Eliminar", confirmar_eliminar, icono="DELETE", peligrosa=True),
        ],
        titulo=lambda f: f"{f.get('Nombre','')} {f.get('Apellido','')}".strip(),
        subtitulo=lambda f: f"{f.get('NombreUsuario','')} · #{f.get('IdCliente','')}",
    )
    ...
    tabla.actualizar(lista_de_registros)

y se coloca `tabla.control` dentro del layout.
"""

import flet as ft


# Compatibilidad de íconos entre versiones de Flet
if not hasattr(ft, "icons") and hasattr(ft, "Icons"):
    ft.icons = ft.Icons


def _icono(*nombres):
    """Devuelve el primer ícono que exista en esta versión de Flet."""
    for nombre in nombres:
        for contenedor in (getattr(ft, "icons", None), getattr(ft, "Icons", None)):
            valor = getattr(contenedor, nombre, None) if contenedor else None
            if valor is not None:
                return valor
    return None


def _relleno(left=0, top=0, right=0, bottom=0):
    """Padding compatible: ft.padding.only/symmetric desaparecieron en Flet 0.8x."""
    try:
        return ft.Padding(left=left, top=top, right=right, bottom=bottom)
    except Exception:
        return None


def _margen(left=0, top=0, right=0, bottom=0):
    try:
        return ft.Margin(left=left, top=top, right=right, bottom=bottom)
    except Exception:
        return None


def _borde_completo(ancho, color):
    try:
        lado = ft.BorderSide(ancho, color)
        return ft.Border(top=lado, right=lado, bottom=lado, left=lado)
    except Exception:
        return None


def _borde_superior(ancho, color):
    try:
        return ft.Border(top=ft.BorderSide(ancho, color))
    except Exception:
        return None


def _centro():
    try:
        return ft.Alignment(0, 0)
    except Exception:
        return getattr(getattr(ft, "alignment", None), "center", None)


COLOR_LILA = "#C86DD7"
COLOR_LILA_SUAVE = "#F3E9F7"
COLOR_TEXTO = "#3A2E42"
COLOR_TEXTO_SUAVE = "#7A6C85"
COLOR_BORDE = "#EADCF0"
COLOR_PELIGRO = "#DC2626"

# Debajo de este ancho se usan tarjetas en lugar de tabla.
UMBRAL_MOVIL = 700


class ColumnaTabla:
    """Una columna de la tabla / un renglón de la tarjeta.

    Args:
        titulo: Encabezado visible.
        valor: Clave del diccionario, o función que recibe la fila.
        icono: Nombre del ícono de Flet para la vista de tarjeta.
        en_tarjeta: Si es False, el dato no se repite en el detalle de la
            tarjeta (útil cuando ya aparece en el título o el subtítulo).
    """

    def __init__(self, titulo: str, valor, icono: str | None = None, en_tarjeta: bool = True):
        self.titulo = titulo
        self.valor = valor
        self.icono = icono
        self.en_tarjeta = en_tarjeta

    def leer(self, fila: dict) -> str:
        try:
            if callable(self.valor):
                return str(self.valor(fila) or "")
            return str(fila.get(self.valor, "") or "")
        except Exception:
            return ""


class AccionTabla:
    """Un botón de acción por registro.

    Args:
        texto: Etiqueta del botón.
        on_click: Función que recibe la fila completa.
        icono: Nombre del ícono de Flet.
        peligrosa: Si es True se pinta en rojo (eliminar, cancelar...).
    """

    def __init__(self, texto: str, on_click, icono: str | None = None, peligrosa: bool = False):
        self.texto = texto
        self.on_click = on_click
        self.icono = icono
        self.peligrosa = peligrosa


class TablaResponsiva:
    def __init__(
        self,
        page: ft.Page,
        columnas: list,
        acciones: list | None = None,
        titulo=None,
        subtitulo=None,
        iniciales=None,
        umbral_movil: int = UMBRAL_MOVIL,
        mensaje_vacio: str = "No hay registros para mostrar.",
    ):
        self.page = page
        self.columnas = columnas
        self.acciones = list(acciones or [])
        self.fn_titulo = titulo
        self.fn_subtitulo = subtitulo
        self.fn_iniciales = iniciales
        self.umbral_movil = umbral_movil
        self.mensaje_vacio = mensaje_vacio

        self.filas: list = []
        self._expandidas: set = set()

        self.tabla = ft.DataTable(
            columns=[ft.DataColumn(ft.Text(c.titulo)) for c in columnas]
                    + ([ft.DataColumn(ft.Text("Acciones"))] if self.acciones else []),
            rows=[],
            border_radius=12,
            heading_row_color=COLOR_LILA_SUAVE,
            data_row_min_height=52,
            data_row_max_height=90,
            column_spacing=18,
        )

        self.contenedor_tarjetas = ft.Column(controls=[], spacing=10, tight=True)

        self.control = ft.Container(expand=True, padding=0)

        self._enganchar_resize()
        self._render()

    # ------------------------------------------------------------------
    # Detección de ancho
    # ------------------------------------------------------------------
    def es_movil(self) -> bool:
        ancho = getattr(self.page, "width", None)
        if not ancho:
            return False
        try:
            return float(ancho) < self.umbral_movil
        except Exception:
            return False

    def _enganchar_resize(self):
        """Se suscribe al cambio de tamaño sin pisar un handler previo."""
        anterior = getattr(self.page, "on_resized", None)

        def al_redimensionar(e=None):
            if anterior is not None and anterior is not al_redimensionar:
                try:
                    anterior(e)
                except Exception:
                    pass
            try:
                self._render()
            except Exception:
                pass

        try:
            self.page.on_resized = al_redimensionar
        except Exception:
            pass

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------
    def actualizar(self, filas: list):
        self.filas = list(filas or [])
        # Con pocos registros las tarjetas se muestran ya desplegadas;
        # con muchos se muestran plegadas para que la lista siga siendo
        # recorrible de un vistazo.
        self._expandidas = set(range(len(self.filas))) if len(self.filas) <= 3 else set()
        self._render()

    # ------------------------------------------------------------------
    # Construcción de la vista
    # ------------------------------------------------------------------
    def _render(self):
        movil = self.es_movil()

        # La tabla vive sobre una superficie blanca; las tarjetas ya son
        # blancas, así que en móvil el fondo se deja transparente para
        # que no se pierdan contra el contenedor.
        self.control.bgcolor = None if (movil and self.filas) else "white"
        self.control.border_radius = 18
        self.control.padding = 0 if (movil and self.filas) else 12

        if not self.filas:
            self.control.content = self._vista_vacia()
        elif movil:
            self._llenar_tarjetas()
            self.control.content = ft.ListView(
                controls=[self.contenedor_tarjetas],
                expand=True,
                padding=_relleno(right=4),
            )
        else:
            self._llenar_tabla()
            self.control.content = ft.ListView(
                controls=[
                    ft.Row(
                        [ft.Container(content=self.tabla, padding=6)],
                        scroll=ft.ScrollMode.AUTO,
                    )
                ],
                expand=True,
            )

        for control in (self.control, self.page):
            try:
                control.update()
                break
            except Exception:
                continue

    def _vista_vacia(self):
        return ft.Container(
            alignment=_centro(),
            padding=30,
            content=ft.Column(
                controls=[
                    ft.Icon(_icono("INBOX", "SEARCH_OFF"), size=38, color=COLOR_TEXTO_SUAVE),
                    ft.Text(self.mensaje_vacio, size=13, color=COLOR_TEXTO_SUAVE),
                ],
                spacing=8,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                tight=True,
            ),
        )

    # ------------------------------------------------------------------
    # Escritorio: DataTable
    # ------------------------------------------------------------------
    def _llenar_tabla(self):
        filas_tabla = []
        for fila in self.filas:
            celdas = [ft.DataCell(ft.Text(col.leer(fila))) for col in self.columnas]

            if self.acciones:
                botones = []
                for accion in self.acciones:
                    def click(e, a=accion, f=fila):
                        a.on_click(f)

                    botones.append(
                        ft.TextButton(
                            accion.texto,
                            on_click=click,
                            style=ft.ButtonStyle(
                                color=COLOR_PELIGRO if accion.peligrosa else None
                            ),
                        )
                    )
                celdas.append(ft.DataCell(ft.Row(botones, spacing=4)))

            filas_tabla.append(ft.DataRow(cells=celdas))

        self.tabla.rows = filas_tabla

    # ------------------------------------------------------------------
    # Móvil: una tarjeta por registro
    # ------------------------------------------------------------------
    def _texto_titulo(self, fila: dict) -> str:
        if self.fn_titulo:
            try:
                return str(self.fn_titulo(fila) or "")
            except Exception:
                pass
        for col in self.columnas:
            valor = col.leer(fila)
            if valor:
                return valor
        return "Registro"

    def _texto_subtitulo(self, fila: dict) -> str:
        if self.fn_subtitulo:
            try:
                return str(self.fn_subtitulo(fila) or "")
            except Exception:
                pass
        return ""

    def _texto_iniciales(self, fila: dict) -> str:
        if self.fn_iniciales:
            try:
                return str(self.fn_iniciales(fila) or "")[:2].upper()
            except Exception:
                pass
        titulo = self._texto_titulo(fila)
        partes = [p for p in titulo.split() if p]
        if len(partes) >= 2:
            return (partes[0][:1] + partes[1][:1]).upper()
        return titulo[:2].upper() if titulo else "--"

    def _llenar_tarjetas(self):
        self.contenedor_tarjetas.controls = [
            self._crear_tarjeta(indice, fila) for indice, fila in enumerate(self.filas)
        ]

    def _crear_tarjeta(self, indice: int, fila: dict):
        abierta = indice in self._expandidas

        chevron = ft.Icon(
            _icono("EXPAND_LESS", "KEYBOARD_ARROW_UP") if abierta
            else _icono("EXPAND_MORE", "KEYBOARD_ARROW_DOWN"),
            color=COLOR_TEXTO_SUAVE,
            size=22,
        )

        def alternar(e=None):
            if indice in self._expandidas:
                self._expandidas.discard(indice)
            else:
                self._expandidas.add(indice)
            self._llenar_tarjetas()
            try:
                self.contenedor_tarjetas.update()
            except Exception:
                self._render()

        encabezado = ft.Container(
            on_click=alternar,
            ink=True,
            border_radius=12,
            content=ft.Row(
                controls=[
                    ft.Container(
                        width=38,
                        height=38,
                        border_radius=19,
                        bgcolor=COLOR_LILA_SUAVE,
                        alignment=_centro(),
                        content=ft.Text(
                            self._texto_iniciales(fila),
                            size=13,
                            weight=ft.FontWeight.BOLD,
                            color=COLOR_LILA,
                        ),
                    ),
                    ft.Column(
                        controls=[
                            ft.Text(
                                self._texto_titulo(fila),
                                size=15,
                                weight=ft.FontWeight.BOLD,
                                color=COLOR_TEXTO,
                                max_lines=1,
                                overflow=ft.TextOverflow.ELLIPSIS,
                            ),
                            ft.Text(
                                self._texto_subtitulo(fila),
                                size=12,
                                color=COLOR_TEXTO_SUAVE,
                                max_lines=1,
                                overflow=ft.TextOverflow.ELLIPSIS,
                            ),
                        ],
                        spacing=1,
                        expand=True,
                    ),
                    chevron,
                ],
                spacing=10,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )

        contenido = [encabezado]

        if abierta:
            renglones = []
            for col in self.columnas:
                if not col.en_tarjeta:
                    continue
                valor = col.leer(fila)
                if not valor:
                    continue
                etiqueta = [ft.Text(col.titulo, size=13, color=COLOR_TEXTO_SUAVE)]
                if col.icono:
                    etiqueta.insert(0, ft.Icon(_icono(col.icono), size=15, color=COLOR_TEXTO_SUAVE))

                renglones.append(
                    ft.Row(
                        controls=[
                            ft.Row(etiqueta, spacing=6, tight=True),
                            ft.Text(
                                valor,
                                size=13,
                                color=COLOR_TEXTO,
                                text_align=ft.TextAlign.RIGHT,
                                max_lines=1,
                                overflow=ft.TextOverflow.ELLIPSIS,
                                expand=True,
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=12,
                    )
                )

            if renglones:
                contenido.append(
                    ft.Container(
                        margin=_margen(top=8),
                        padding=_relleno(top=8),
                        border=_borde_superior(1, COLOR_BORDE),
                        content=ft.Column(renglones, spacing=5, tight=True),
                    )
                )

            if self.acciones:
                botones = []
                for accion in self.acciones:
                    def click(e, a=accion, f=fila):
                        a.on_click(f)

                    color = COLOR_PELIGRO if accion.peligrosa else COLOR_LILA
                    botones.append(
                        ft.OutlinedButton(
                            accion.texto,
                            icon=_icono(accion.icono) if accion.icono else None,
                            on_click=click,
                            expand=True,
                            style=ft.ButtonStyle(
                                color=color,
                                side=ft.BorderSide(1, color),
                                shape=ft.RoundedRectangleBorder(radius=10),
                                padding=14,
                            ),
                        )
                    )
                contenido.append(
                    ft.Container(
                        margin=_margen(top=10),
                        content=ft.Row(botones, spacing=8),
                    )
                )

        return ft.Container(
            bgcolor="white",
            border_radius=12,
            border=_borde_completo(1, COLOR_BORDE),
            padding=_relleno(left=14, right=14, top=12, bottom=12),
            content=ft.Column(contenido, spacing=0, tight=True),
        )