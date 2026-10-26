-- ============================================================
-- recursos/sql/migracion_horario.sql
-- ------------------------------------------------------------
-- Horario laboral e interruptor del servicio de pedidos.
--
-- Problema que resuelve: el menu de clientes aceptaba pedidos a
-- cualquier hora y en dias de descanso. Con estas tablas el menu
-- solo recibe pedidos dentro del horario del local, y el
-- administrador puede pausar el servicio (mantenimiento, falta de
-- insumos, cierre imprevisto) sin tocar el codigo.
--
-- Se puede ejecutar varias veces sin duplicar nada:
--
--     python -m herramientas.aplicar_migracion recursos/sql/migracion_horario.sql
-- ============================================================


-- Horario semanal. DiaSemana sigue la convencion de Python
-- (datetime.weekday): 0 = lunes ... 6 = domingo.
CREATE TABLE IF NOT EXISTS horario_local (
    DiaSemana     TINYINT     NOT NULL,
    Abierto       TINYINT(1)  NOT NULL DEFAULT 1,
    HoraApertura  TIME        NOT NULL,
    HoraCierre    TIME        NOT NULL,
    PRIMARY KEY (DiaSemana),
    CONSTRAINT chk_horario_dia CHECK (DiaSemana BETWEEN 0 AND 6),
    CONSTRAINT chk_horario_rango CHECK (HoraCierre > HoraApertura)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


-- Fechas puntuales en las que el local no abre (festivos,
-- vacaciones, cierres imprevistos).
CREATE TABLE IF NOT EXISTS dias_cerrados (
    IdDiaCerrado  INT          NOT NULL AUTO_INCREMENT,
    Fecha         DATE         NOT NULL,
    Motivo        VARCHAR(120) NULL,
    PRIMARY KEY (IdDiaCerrado),
    UNIQUE KEY uq_dias_cerrados_fecha (Fecha)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


-- Interruptor del servicio. Es una tabla de una sola fila (Id = 1).
-- PosActivo queda preparado para cuando se aplique la misma regla al
-- punto de venta, todavia no se usa.
CREATE TABLE IF NOT EXISTS estado_servicio (
    IdEstadoServicio   TINYINT      NOT NULL DEFAULT 1,
    MenuActivo         TINYINT(1)   NOT NULL DEFAULT 1,
    MensajeMenu        VARCHAR(200) NULL,
    MinutosAntesCierre SMALLINT     NOT NULL DEFAULT 15,
    PosActivo          TINYINT(1)   NOT NULL DEFAULT 1,
    ModificadoPor      VARCHAR(80)  NULL,
    FechaModificacion  DATETIME     NULL,
    PRIMARY KEY (IdEstadoServicio),
    CONSTRAINT chk_estado_servicio_unico CHECK (IdEstadoServicio = 1)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


-- Valores iniciales. Son provisionales: el horario real se captura
-- desde la pantalla "Horario y servicio" del administrador.
-- INSERT IGNORE no sobrescribe lo que ya se haya configurado.
INSERT IGNORE INTO horario_local (DiaSemana, Abierto, HoraApertura, HoraCierre) VALUES
    (0, 1, '10:00:00', '21:00:00'),
    (1, 1, '10:00:00', '21:00:00'),
    (2, 1, '10:00:00', '21:00:00'),
    (3, 1, '10:00:00', '21:00:00'),
    (4, 1, '10:00:00', '21:00:00'),
    (5, 1, '10:00:00', '21:00:00'),
    (6, 0, '10:00:00', '21:00:00');

INSERT IGNORE INTO estado_servicio (IdEstadoServicio, MenuActivo, MinutosAntesCierre)
VALUES (1, 1, 15);


-- Verificacion
SELECT DiaSemana, Abierto, HoraApertura, HoraCierre
FROM horario_local
ORDER BY DiaSemana;