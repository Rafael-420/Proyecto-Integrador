-- ============================================================
-- recursos/sql/migracion_imagenes_bebidas.sql
-- ------------------------------------------------------------
-- Fotos de las bebidas guardadas en la base de datos en la nube.
--
-- Problema que resuelve: antes la foto se copiaba a assets/bebidas
-- en el disco de la computadora que corria la app, y en la tabla
-- bebidas solo quedaba la ruta ("bebidas/taro.jpg"). Esa carpeta no
-- esta en el repositorio ni en otros equipos, y en el APK la carpeta
-- assets se empaqueta al compilar y es de solo lectura. Resultado: en
-- cualquier otro dispositivo la foto no aparecia.
--
-- Con esta tabla la foto (ya reducida a 600 px por lado) vive en
-- MySQL, junto con el resto del catalogo, y cualquier dispositivo
-- conectado a la base de datos la puede mostrar.
--
--   - Va en una tabla aparte y no como columna de bebidas para que
--     las consultas del catalogo no carguen las fotos cuando no se
--     necesitan.
--   - Actualizado sirve como "version" de la foto: la app guarda las
--     fotos en memoria y solo las vuelve a descargar si cambia.
--   - ON DELETE CASCADE: al eliminar la bebida se elimina su foto.
--   - La columna bebidas.Imagen (ruta vieja) se conserva como
--     respaldo; al guardar una foto nueva se deja en NULL.
--
-- Se puede ejecutar varias veces (si la tabla ya existe, se omite):
--
--     python -m herramientas.aplicar_migracion recursos/sql/migracion_imagenes_bebidas.sql
-- ============================================================


CREATE TABLE bebidas_imagenes (
    IdBebida    INT          NOT NULL,
    Datos       MEDIUMBLOB   NOT NULL,
    Tipo        VARCHAR(20)  NOT NULL DEFAULT 'image/jpeg',
    Bytes       INT          NOT NULL DEFAULT 0,
    Actualizado DATETIME(6)  NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (IdBebida),
    CONSTRAINT fk_bebidas_imagenes_bebida
        FOREIGN KEY (IdBebida) REFERENCES bebidas (IdBebida)
        ON DELETE CASCADE
) ENGINE=InnoDB;


-- Verificacion: cuantas bebidas hay y cuantas ya tienen foto en la BD
-- (justo despues de crear la tabla, FotosEnBD vale 0).
SELECT
    (SELECT COUNT(*) FROM bebidas)          AS Bebidas,
    (SELECT COUNT(*) FROM bebidas_imagenes) AS FotosEnBD;