# Corallie Bubble - Proyecto refactorizado

Estructura aplicada:

- `configuracion/`: conexión y variables globales.
- `componentes/`: sidebars reutilizables.
- `servicios/`: lógica reutilizable y acceso a datos común.
- `validaciones/`: validaciones separadas para formularios.
- `vistas/`: pantallas principales del sistema.
- `navegacion/`: router inicial.

## Ejecutar

1. Importa `recursos/sql/ing_software.sql` en phpMyAdmin.
2. Ajusta usuario y contraseña en `configuracion/variables.py`.
3. Instala dependencias:

```bash
pip install -r requirements.txt
```

4. Ejecuta:

```bash
python main.py
```

## Nota

Se corrigieron importaciones para usar arquitectura por carpetas y se mantuvieron
helpers de compatibilidad para Flet reciente.
