-- ============================================================
-- Migración: estatus "No recogido" para pedidos de la app
-- Proyecto: Corallie Bubble
-- ============================================================
--
-- Contexto
-- --------
-- Las bebidas pedidas desde la app se preparan antes de cobrarse, así
-- que un pedido que el cliente nunca recoge es producto perdido. Para
-- controlarlo se agregó un sexto estatus y las reglas que lo usan:
--
--   1. Un solo pedido activo por cliente.
--   2. Máximo 3 productos distintos por pedido.
--   3. Un pedido "No recogido" bloquea al cliente para pedir desde la
--      app; se desbloquea cuando pasa al local a pagarlo.
--
-- Estatus existentes: 1 Pagado, 2 En preparación, 3 Pedido Realizado,
-- 4 Entregado, 5 Cancelado.
--
-- Cómo aplicarla
-- --------------
-- Ejecutar este archivo completo en DBeaver, conectado a la base de
-- Railway. Es idempotente: se puede correr más de una vez sin duplicar
-- el estatus. No modifica pedidos existentes.
-- ============================================================

-- 1. Alta del estatus 6 ---------------------------------------
INSERT INTO estatuspedido (IdEstatusPedido, SituacionPedido)
SELECT 6, 'No recogido'
WHERE NOT EXISTS (
    SELECT 1 FROM estatuspedido WHERE IdEstatusPedido = 6
);

-- 2. Verificación ---------------------------------------------
-- Debe listar los seis estatus, con 'No recogido' al final.
SELECT IdEstatusPedido, SituacionPedido
FROM estatuspedido
ORDER BY IdEstatusPedido;

-- 3. Consulta de apoyo ----------------------------------------
-- Pedidos no recogidos pendientes de pago, por cliente. Es lo que
-- bloquea al cliente en la app y lo que se cobra en el mostrador.
SELECT
    gp.Clientes_Idcliente,
    CONCAT(COALESCE(c.Nombre, ''), ' ', COALESCE(c.Apellido, '')) AS Cliente,
    COUNT(*)              AS PedidosSinRecoger,
    COALESCE(SUM(gp.Total), 0) AS MontoPendiente
FROM generarpedido gp
LEFT JOIN cliente c ON c.IdCliente = gp.Clientes_Idcliente
WHERE gp.EstatusPedido_IdEstatusPedido = 6
GROUP BY gp.Clientes_Idcliente, Cliente
ORDER BY MontoPendiente DESC;