-- ============================================================
-- Corallie Bubble - Migracion de seguridad (autenticacion)
-- Ejecutar UNA sola vez sobre la base de Railway.
-- Compatible con MySQL 8.x / 9.x
-- ============================================================

-- ------------------------------------------------------------
-- 1. Ampliar la columna de contrasena
--    Formato nuevo: pbkdf2_sha256$<iteraciones>$<salt_hex>$<hash_hex>
--    Longitud aproximada: 120 caracteres. VARCHAR(79) es insuficiente.
-- ------------------------------------------------------------
ALTER TABLE `usuario`
  MODIFY `Contraseña` VARCHAR(255) NOT NULL;

-- ------------------------------------------------------------
-- 2. Evitar usuarios duplicados (requisito de integridad del login)
--    Si falla, hay nombres repetidos: limpiarlos antes de reintentar.
-- ------------------------------------------------------------
ALTER TABLE `usuario`
  ADD UNIQUE KEY `uk_usuario_nombre` (`NombreUsuario`);

-- ------------------------------------------------------------
-- 3. Metadatos de seguridad por usuario
-- ------------------------------------------------------------
ALTER TABLE `usuario`
  ADD COLUMN `Activo` TINYINT(1) NOT NULL DEFAULT 1,
  ADD COLUMN `RequiereCambio` TINYINT(1) NOT NULL DEFAULT 0,
  ADD COLUMN `FechaCambioPassword` DATETIME NULL DEFAULT NULL;

-- ------------------------------------------------------------
-- 4. Bitacora de intentos de acceso (control de bloqueo y auditoria)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `intentos_login` (
  `IdIntento`     INT(11)      NOT NULL AUTO_INCREMENT,
  `NombreUsuario` VARCHAR(45)  NOT NULL,
  `Exitoso`       TINYINT(1)   NOT NULL DEFAULT 0,
  `Motivo`        VARCHAR(60)  NULL DEFAULT NULL,
  `Origen`        VARCHAR(45)  NULL DEFAULT NULL,
  `FechaIntento`  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`IdIntento`),
  KEY `idx_intentos_usuario_fecha` (`NombreUsuario`, `FechaIntento`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ------------------------------------------------------------
-- 5. Ampliar la contrasena temporal de solicitudes_password
-- ------------------------------------------------------------
ALTER TABLE `solicitudes_password`
  MODIFY `PasswordTemporal` VARCHAR(255) DEFAULT NULL;

-- ------------------------------------------------------------
-- 6. Marcar los hashes SHA-256 heredados (64 caracteres hexadecimales)
--    para que el verificador los reconozca como formato antiguo.
--    Se re-hashean solos en el siguiente inicio de sesion correcto.
-- ------------------------------------------------------------
UPDATE `usuario`
   SET `Contraseña` = CONCAT('sha256$', `Contraseña`)
 WHERE CHAR_LENGTH(`Contraseña`) = 64
   AND `Contraseña` REGEXP '^[0-9a-fA-F]{64}$';

-- ------------------------------------------------------------
-- 7. Verificacion posterior (consulta de control, no modifica nada)
-- ------------------------------------------------------------
SELECT `IdUsuario`,
       `NombreUsuario`,
       `Rol`,
       CASE
         WHEN `Contraseña` LIKE 'pbkdf2_sha256$%' THEN 'PBKDF2 (seguro)'
         WHEN `Contraseña` LIKE 'sha256$%'        THEN 'SHA-256 heredado'
         ELSE 'TEXTO PLANO (migrar ya)'
       END AS `EstadoPassword`
  FROM `usuario`
 ORDER BY `EstadoPassword`, `NombreUsuario`;