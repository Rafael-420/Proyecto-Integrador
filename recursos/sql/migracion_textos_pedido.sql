-- ============================================================
-- recursos/sql/migracion_textos_pedido.sql
-- ------------------------------------------------------------
-- Corrige dos defectos de largo de texto y uno de datos que
-- encontraron las pruebas de integracion (pruebas_integracion/).
--
-- D-15: recibospedidos.Producto era VARCHAR(255). Un pedido de 3
--       bebidas con todos los extras mide mas, asi que el recibo se
--       perdia en silencio (Railway) o se guardaba recortado (XAMPP).
--
-- D-16: generarpedido.Producto era VARCHAR(500). Con indicaciones
--       largas el pedido fallaba con un error de MySQL. Ademas, la app
--       ahora limita las indicaciones (80 caracteres por bebida y 120
--       en las notas) y servicio_menu rechaza con un mensaje claro un
--       texto de mas de 1500 caracteres.
--
--       Las dos columnas pasan a TEXT: el texto completo del pedido se
--       guarda igual en el pedido y en su recibo.
--
-- D-20: los empleados que dio de alta el administrador quedaron con
--       rol CLIENTE, porque el INSERT no indicaba el rol. Esta
--       instruccion los corrige; solo toca cuentas que estan en la
--       tabla empleado y tienen rol CLIENTE.
--
-- Se puede ejecutar varias veces sin problema:
--
--     python -m herramientas.aplicar_migracion recursos/sql/migracion_textos_pedido.sql
-- ============================================================

ALTER TABLE `generarpedido` MODIFY `Producto` TEXT NULL;

ALTER TABLE `recibospedidos` MODIFY `Producto` TEXT NOT NULL;

UPDATE `usuario` u
JOIN `empleado` e ON e.`Usuario_IdUsuario` = u.`IdUsuario`
SET u.`Rol` = 'EMPLEADO'
WHERE u.`Rol` = 'CLIENTE';