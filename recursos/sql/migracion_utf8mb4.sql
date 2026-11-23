-- ============================================================
-- recursos/sql/migracion_utf8mb4.sql
-- ------------------------------------------------------------
-- Corrige el defecto D-22 que encontro la prueba basada en datos
-- CP-DDT-33 (pruebas_integracion/test_datos_pedidos.py).
--
-- D-22: las tablas que vienen del respaldo original guardan el texto
--       en utf8mb3, que solo admite caracteres de hasta 3 bytes. Un
--       emoji ocupa 4, asi que un pedido con un emoji en las
--       indicaciones (o un nombre, una descripcion o una nota con
--       emoji) se rechazaba con el error 1366 y no se guardaba.
--
--       La app ya se conecta con utf8mb4; aqui se pasan las tablas
--       a utf8mb4, el juego de caracteres que MySQL recomienda.
--
-- Se usa la colacion utf8mb4_unicode_ci porque existe en MySQL
-- (Railway) y en el MariaDB de XAMPP, y porque, igual que la
-- anterior, no distingue mayusculas ni acentos al comparar. Tambien
-- se pasan a ella las tablas que ya eran utf8mb4 con otra colacion,
-- para que todas comparen igual.
--
-- Notas:
--   * No se pierde ningun dato: todo lo que cabe en utf8mb3 cabe en
--     utf8mb4.
--   * Las columnas TEXT pueden quedar como MEDIUMTEXT: MySQL las
--     agranda para que sigan cabiendo los mismos caracteres.
--   * bebidas_imagenes ya esta en utf8mb4_unicode_ci y solo guarda
--     fotos (BLOB); no se toca para no reescribir las imagenes.
--   * Cada ALTER reescribe su tabla. Con los datos del local tarda
--     segundos, pero conviene aplicarla con el local cerrado y
--     despues de respaldar la base.
--
-- Se puede ejecutar varias veces sin problema:
--
--     python -m herramientas.aplicar_migracion recursos/sql/migracion_utf8mb4.sql
-- ============================================================

-- Las tablas nuevas que se creen sin indicar juego de caracteres
-- tambien quedaran en utf8mb4 (aplica a la base de la conexion).
ALTER DATABASE CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- Tablas con texto que escribe el cliente, el empleado o el administrador
ALTER TABLE `usuario` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER TABLE `cliente` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER TABLE `empleado` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER TABLE `bebidas` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER TABLE `generarpedido` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER TABLE `generarpedido_detalle` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER TABLE `recibospedidos` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER TABLE `ingresos_egresos` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER TABLE `solicitudes_password` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER TABLE `intentos_login` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER TABLE `consentimiento_privacidad` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- Caja, inventario y catalogos
ALTER TABLE `cortecaja` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER TABLE `ventas` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER TABLE `detalleventas` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER TABLE `generarrecibo` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER TABLE `recibos` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER TABLE `entradarecibe` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER TABLE `entradasproductos` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER TABLE `salidasproductos` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER TABLE `tipossalidas` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER TABLE `productos` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER TABLE `productosstock` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER TABLE `estatuspedido` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- Horario y senal de la caja
ALTER TABLE `horario_local` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER TABLE `dias_cerrados` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER TABLE `estado_servicio` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- Verificacion: debe salir vacia. Lista las columnas que todavia no
-- aceptan emojis.
SELECT TABLE_NAME AS tabla, COLUMN_NAME AS columna, CHARACTER_SET_NAME AS juego
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND CHARACTER_SET_NAME IS NOT NULL
  AND CHARACTER_SET_NAME <> 'utf8mb4'
ORDER BY TABLE_NAME, COLUMN_NAME;
