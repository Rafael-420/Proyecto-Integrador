"""Datos personales tapados (teléfono y correo) en las pantallas del admin.

En Control de empleados y Control de usuarios ya no se muestra el teléfono
ni el correo completos:

    Teléfono 3221241532        ->  ••••••1532
    Correo   pedro125@gmail.com ->  ••••o125@gmail.com

En el diálogo de Editar el dato aparece tapado y con un lápiz. Solo si el
administrador toca el lápiz aparece el campo vacío para escribir uno nuevo;
si no, al guardar se conserva el valor que ya estaba en la base de datos,
sin que se haya mostrado nunca en pantalla.
"""

import flet as ft

from utilidades.flet_compat import icono, set_error


PUNTO = "•"
VISIBLES = 4


def enmascarar_telefono(telefono) -> str:
    """Deja ver solo los últimos 4 dígitos."""
    texto = str(telefono or "").strip()
    if not texto:
        return ""
    if len(texto) <= VISIBLES:
        return PUNTO * len(texto)
    return PUNTO * (len(texto) - VISIBLES) + texto[-VISIBLES:]


def enmascarar_correo(correo) -> str:
    """Deja ver los últimos 4 caracteres antes de la @ y el dominio."""
    texto = str(correo or "").strip()
    if not texto:
        return ""
    usuario, arroba, dominio = texto.partition("@")
    if not arroba:
        return enmascarar_telefono(texto)
    if len(usuario) <= VISIBLES:
        visible = PUNTO * max(len(usuario), 1)
    else:
        visible = PUNTO * (len(usuario) - VISIBLES) + usuario[-VISIBLES:]
    return f"{visible}@{dominio}"


class CampoPrivado:
    """Muestra un dato tapado y deja reemplazarlo sin revelarlo.

    Args:
        campo: TextField real donde se escribe el dato nuevo (con sus
            validaciones de siempre). Empieza oculto y vacío.
        valor_actual: Dato guardado en la base de datos.
        enmascarar: enmascarar_telefono o enmascarar_correo.
        extras: Controles que solo deben verse al cambiar el dato (por
            ejemplo, los atajos @gmail.com del correo).
    """

    def __init__(self, campo: ft.TextField, valor_actual, enmascarar, extras=None):
        self.campo = campo
        self.valor_actual = str(valor_actual or "").strip()
        self.extras = list(extras or [])
        self.editando = False

        etiqueta = campo.label or ""
        self.campo.value = ""
        self.campo.visible = False
        for extra in self.extras:
            extra.visible = False

        self.vista = ft.TextField(
            label=etiqueta,
            value=enmascarar(self.valor_actual) or "Sin registrar",
            read_only=True,
            border_radius=12,
            prefix_icon=getattr(campo, "prefix_icon", None),
            suffix=ft.IconButton(
                icon=icono("EDIT"),
                icon_size=18,
                icon_color="#C86DD7",
                tooltip=f"Cambiar {etiqueta.lower()}",
                on_click=self._cambiar,
            ),
        )

        self.btn_conservar = ft.TextButton(
            f"Conservar {etiqueta.lower()} actual",
            icon=icono("UNDO"),
            visible=False,
            on_click=self._conservar,
        )

        self.control = ft.Column(
            [self.vista, self.campo, *self.extras, self.btn_conservar],
            spacing=4,
            tight=True,
        )

    # ------------------------------------------------------------------
    def valor(self) -> str:
        """Lo que se debe guardar: el dato nuevo o, si no se cambió, el actual."""
        if self.editando:
            return self.campo.value or ""
        return self.valor_actual

    def _actualizar(self):
        self.vista.visible = not self.editando
        self.campo.visible = self.editando
        self.btn_conservar.visible = self.editando
        for extra in self.extras:
            extra.visible = self.editando
        try:
            self.control.update()
        except Exception:
            pass

    def _cambiar(self, e=None):
        self.editando = True
        self.campo.value = ""
        self._actualizar()
        try:
            self.campo.focus()
        except Exception:
            pass

    def _conservar(self, e=None):
        self.editando = False
        self.campo.value = ""
        set_error(self.campo)
        self._actualizar()