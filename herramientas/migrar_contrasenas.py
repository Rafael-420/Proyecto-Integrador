"""
herramientas/migrar_contrasenas.py
----------------------------------
Script de un solo uso: convierte a PBKDF2 las contrasenas guardadas en
texto plano y marca las heredadas de SHA-256.

  * Texto plano  -> se re-hashea directamente (se conoce el valor original).
  * SHA-256      -> no se puede revertir; se le antepone el prefijo
                    'sha256$' y se migra sola cuando el usuario
                    inicie sesion correctamente.

Ejecutar desde la raiz del proyecto:

    python -m herramientas.migrar_contrasenas            # solo reporte
    python -m herramientas.migrar_contrasenas --aplicar  # escribe cambios
"""

from __future__ import annotations

import argparse
import sys

from configuracion.base_datos import cursor_bd
from servicios import servicio_seguridad as seguridad

_COL_PASS = "`Contraseña`"


def _leer_usuarios() -> list:
    with cursor_bd() as cur:
        cur.execute(
            f"SELECT IdUsuario, NombreUsuario, Rol, {_COL_PASS} AS Password "
            "FROM usuario ORDER BY IdUsuario"
        )
        return cur.fetchall()


def _clasificar(valor: str) -> str:
    valor = (valor or "").strip()
    if seguridad.es_formato_seguro(valor):
        return "seguro"
    if valor.startswith(seguridad.PREFIJO_HEREDADO):
        return "heredado"
    if len(valor) == 64 and all(c in "0123456789abcdefABCDEF" for c in valor):
        return "sha256_sin_prefijo"
    if not valor:
        return "vacio"
    return "texto_plano"


def _verificar_columna() -> bool:
    """Confirma que la columna ya acepta 255 caracteres."""
    with cursor_bd() as cur:
        cur.execute("SHOW COLUMNS FROM usuario LIKE 'Contraseña'")
        fila = cur.fetchone()
    if not fila:
        print("No se encontro la columna 'Contraseña' en la tabla usuario.")
        return False
    tipo = str(fila.get("Type", "")).lower()
    if "varchar(255)" not in tipo:
        print(
            f"La columna sigue como {tipo}. Ejecuta primero "
            "recursos/sql/migracion_seguridad.sql antes de continuar."
        )
        return False
    return True


def main() -> int:
    analizador = argparse.ArgumentParser(description="Migracion de contrasenas a PBKDF2.")
    analizador.add_argument(
        "--aplicar",
        action="store_true",
        help="Escribe los cambios. Sin esta bandera solo muestra el reporte.",
    )
    argumentos = analizador.parse_args()

    try:
        usuarios = _leer_usuarios()
    except Exception as exc:
        print(f"No se pudo leer la tabla usuario: {exc}")
        return 1

    if argumentos.aplicar and not _verificar_columna():
        return 1

    resumen = {"seguro": 0, "heredado": 0, "sha256_sin_prefijo": 0, "texto_plano": 0, "vacio": 0}
    pendientes = []

    print("\n{:<6} {:<20} {:<10} {}".format("Id", "Usuario", "Rol", "Estado"))
    print("-" * 70)

    for fila in usuarios:
        estado = _clasificar(fila.get("Password"))
        resumen[estado] += 1
        print(
            "{:<6} {:<20} {:<10} {}".format(
                fila["IdUsuario"],
                str(fila["NombreUsuario"])[:20],
                str(fila["Rol"])[:10],
                seguridad.describir_formato(fila.get("Password")),
            )
        )
        if estado in ("texto_plano", "sha256_sin_prefijo"):
            pendientes.append((fila, estado))

    print("-" * 70)
    print(
        f"Seguros: {resumen['seguro']} | "
        f"Heredados marcados: {resumen['heredado']} | "
        f"SHA-256 sin marcar: {resumen['sha256_sin_prefijo']} | "
        f"Texto plano: {resumen['texto_plano']} | "
        f"Vacios: {resumen['vacio']}"
    )

    if not pendientes:
        print("\nNo hay nada que migrar.")
        return 0

    if not argumentos.aplicar:
        print(f"\n{len(pendientes)} registro(s) por migrar.")
        print("Vuelve a ejecutar con --aplicar para escribir los cambios.")
        return 0

    convertidos = 0
    marcados = 0

    for fila, estado in pendientes:
        actual = str(fila.get("Password") or "")
        if estado == "texto_plano":
            nuevo = seguridad.hashear(actual)
            convertidos += 1
        else:
            nuevo = seguridad.PREFIJO_HEREDADO + actual
            marcados += 1

        try:
            with cursor_bd(diccionario=False, commit=True) as cur:
                cur.execute(
                    f"UPDATE usuario SET {_COL_PASS} = %s WHERE IdUsuario = %s",
                    (nuevo, fila["IdUsuario"]),
                )
        except Exception as exc:
            print(f"  Fallo en IdUsuario={fila['IdUsuario']}: {exc}")

    print(f"\nContrasenas re-hasheadas a PBKDF2: {convertidos}")
    print(f"Hashes SHA-256 marcados (migran al siguiente login): {marcados}")
    print("\nRecuerda: las contrasenas en texto plano que estaban en el volcado SQL")
    print("del repositorio deben considerarse comprometidas. Restablecelas.")
    return 0


if __name__ == "__main__":
    sys.exit(main())