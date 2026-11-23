"""
pruebas_integracion/ejecutar_pruebas.py
---------------------------------------
Ejecuta toda la suite de integracion, sistema, seguridad y red, y al
final imprime un resumen con los defectos abiertos.

Desde Visual Studio Code: abre este archivo y presiona el boton
"Run Python File" (triangulo de arriba a la derecha).

Desde la consola, en la raiz del proyecto:

    python pruebas_integracion/ejecutar_pruebas.py

Requisitos: un MySQL local encendido y, si su usuario no es root/root,
las variables PRUEBAS_DB_USER y PRUEBAS_DB_PASSWORD en el .env
(ver base_pruebas.py).
"""

from __future__ import annotations

import os
import sys
import time
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))


def _preparar() -> bool:
    """Crea la base de pruebas antes de cargar los casos.

    Si algo falla (MySQL apagado, contrasena equivocada, una migracion
    con error), se muestra un solo mensaje claro en lugar de un error
    por cada clase de prueba.
    """
    try:
        from pruebas_integracion import base_pruebas

        print(
            "Base de pruebas: "
            f"{base_pruebas.CONFIG['user']}@{base_pruebas.CONFIG['host']}:{base_pruebas.CONFIG['port']}"
            f"/{base_pruebas.CONFIG['database']}"
        )
        base_pruebas.preparar_base()
        return True
    except Exception as error:
        print("\n" + "=" * 70)
        print("NO SE PUDO PREPARAR LA BASE DE PRUEBAS")
        print("=" * 70)
        print(f"{type(error).__name__}: {error}")
        print(
            "\nRevisa que tu MySQL local este encendido y que el .env tenga\n"
            "el usuario y la contrasena de ese MySQL, por ejemplo:\n\n"
            "    PRUEBAS_DB_USER=root\n"
            "    PRUEBAS_DB_PASSWORD=\n\n"
            "(deja PRUEBAS_DB_PASSWORD vacio si tu root no tiene contrasena,\n"
            "como en Laragon o XAMPP)."
        )
        return False


def main() -> int:
    if not _preparar():
        return 1

    cargador = unittest.TestLoader()
    suite = cargador.discover(
        start_dir=str(RAIZ / "pruebas_integracion"),
        pattern="test_*.py",
        top_level_dir=str(RAIZ),
    )

    inicio = time.monotonic()
    resultado = unittest.TextTestRunner(verbosity=2).run(suite)
    segundos = time.monotonic() - inicio

    print("\n" + "=" * 70)
    print("RESUMEN")
    print("=" * 70)
    print(f"Casos ejecutados:            {resultado.testsRun}")
    print(f"Fallas nuevas:               {len(resultado.failures)}")
    print(f"Errores:                     {len(resultado.errors)}")
    print(f"Defectos conocidos abiertos: {len(resultado.expectedFailures)}")
    print(f"Defectos que ya se corrigieron (quita su @expectedFailure): {len(resultado.unexpectedSuccesses)}")
    print(f"Omitidos:                    {len(resultado.skipped)}")
    print(f"Tiempo:                      {segundos:.1f} s")

    if resultado.expectedFailures:
        print("\nDefectos abiertos:")
        for prueba, _detalle in resultado.expectedFailures:
            primera = (prueba.shortDescription() or str(prueba)).splitlines()[0]
            print(f"  - {primera}")

    if resultado.unexpectedSuccesses:
        print("\nYa pasan (actualiza el documento y quita el decorador):")
        for prueba in resultado.unexpectedSuccesses:
            print(f"  - {(prueba.shortDescription() or str(prueba)).splitlines()[0]}")

    _resumen_github(resultado, segundos)
    return 0 if resultado.wasSuccessful() else 1


def _titulo(prueba) -> str:
    return (prueba.shortDescription() or str(prueba)).splitlines()[0]


def _resumen_github(resultado, segundos: float) -> None:
    """En GitHub Actions deja el resumen como tabla en la pagina de la ejecucion.

    GitHub define GITHUB_STEP_SUMMARY con la ruta de un archivo; lo que se
    escribe ahi aparece en la pestana Actions. En la computadora de cada
    quien la variable no existe y esta funcion no hace nada.
    """
    ruta = os.environ.get("GITHUB_STEP_SUMMARY")
    if not ruta:
        return

    estado = "Aprobada" if resultado.wasSuccessful() else "Con fallas"
    lineas = [
        f"## Pruebas de integración, sistema, seguridad y red: {estado}",
        "",
        "| Concepto | Resultado |",
        "|---|---:|",
        f"| Casos ejecutados | {resultado.testsRun} |",
        f"| Fallas nuevas | {len(resultado.failures)} |",
        f"| Errores | {len(resultado.errors)} |",
        f"| Defectos conocidos abiertos | {len(resultado.expectedFailures)} |",
        f"| Defectos que ya se corrigieron | {len(resultado.unexpectedSuccesses)} |",
        f"| Omitidos | {len(resultado.skipped)} |",
        f"| Tiempo | {segundos:.1f} s |",
        "",
    ]
    secciones = (
        ("Fallas nuevas", [p for p, _d in resultado.failures]),
        ("Errores", [p for p, _d in resultado.errors]),
        ("Defectos conocidos abiertos", [p for p, _d in resultado.expectedFailures]),
        ("Ya pasan (quitar su @expectedFailure)", list(resultado.unexpectedSuccesses)),
    )
    for titulo, pruebas in secciones:
        if pruebas:
            lineas.append(f"### {titulo}")
            lineas.append("")
            lineas.extend(f"- {_titulo(p)}" for p in pruebas)
            lineas.append("")
    try:
        with open(ruta, "a", encoding="utf-8") as archivo:
            archivo.write("\n".join(lineas) + "\n")
    except OSError:
        pass


if __name__ == "__main__":
    sys.exit(main())
