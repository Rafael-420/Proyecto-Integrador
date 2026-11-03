-- ============================================================
-- recursos/sql/migracion_senal_caja.sql
-- ------------------------------------------------------------
-- Señal de "sigo aqui" de la caja.
--
-- Problema que resuelve: la base de datos esta en la nube. Si el
-- local se queda sin internet, el cliente podia seguir pidiendo
-- desde su celular, pero en la caja nadie veia el pedido. La
-- bebida no se preparaba y el pedido terminaba como "No recogido",
-- bloqueando al cliente sin que fuera su culpa.
--
-- Con estas columnas:
--   - La caja registra cada minuto la hora en UltimaSenalCaja.
--   - Si esa hora tiene mas de 3 minutos (CORALLIE_MINUTOS_SENAL_CAJA),
--     el menu de clientes se puede ver pero no acepta pedidos.
--   - InicioDesconexionCaja / FinDesconexionCaja guardan el ultimo
--     periodo sin señal, para que el marcado automatico de
--     "No recogido" no castigue pedidos que esperaron en ese tiempo.
--
-- Requiere migracion_horario.sql (tabla estado_servicio).
--
-- MySQL no admite "ADD COLUMN IF NOT EXISTS", por eso cada columna
-- va en su propia instruccion: si ya existe, el script la omite y
-- continua. Se puede ejecutar varias veces:
--
--     python -m herramientas.aplicar_migracion recursos/sql/migracion_senal_caja.sql
-- ============================================================


ALTER TABLE estado_servicio
    ADD COLUMN UltimaSenalCaja DATETIME NULL;

ALTER TABLE estado_servicio
    ADD COLUMN InicioDesconexionCaja DATETIME NULL;

ALTER TABLE estado_servicio
    ADD COLUMN FinDesconexionCaja DATETIME NULL;


-- La fila unica del interruptor debe existir para que la caja pueda
-- registrar su señal. INSERT IGNORE no toca la configuracion actual.
INSERT IGNORE INTO estado_servicio (IdEstadoServicio, MenuActivo, MinutosAntesCierre)
VALUES (1, 1, 15);


-- Verificacion: las tres columnas nuevas deben aparecer (en NULL hasta
-- que un empleado inicie sesion en la caja).
SELECT IdEstadoServicio, MenuActivo, UltimaSenalCaja,
       InicioDesconexionCaja, FinDesconexionCaja
FROM estado_servicio;
