-- ============================================================
-- pruebas_integracion/esquema_base.sql
-- ------------------------------------------------------------
-- Estructura de la base de datos ANTES de las migraciones, tomada
-- del respaldo ing_software (27).sql (2 de septiembre de 2026).
-- Solo estructura: no lleva datos reales de clientes ni empleados.
--
-- La suite de integracion crea la base de pruebas con este archivo y
-- despues aplica, con herramientas/aplicar_migracion.py, las mismas
-- migraciones de recursos/ que se aplicaron en Railway. Asi se prueba
-- tambien que las migraciones funcionan sobre el esquema original.
--
-- No lo ejecutes sobre la base real: se usa solo en la base
-- ing_software_pruebas, que la suite borra y vuelve a crear.
-- ============================================================

CREATE TABLE `bebidas` (
  `IdBebida` int(11) NOT NULL AUTO_INCREMENT,
  `Nombre` varchar(60) NOT NULL,
  `Precio` double NOT NULL,
  `Descripcion` varchar(255) NOT NULL DEFAULT '',
  `Categoria` varchar(40) NOT NULL DEFAULT 'General',
  `Imagen` varchar(255) DEFAULT NULL,
  `Disponible` tinyint(1) NOT NULL DEFAULT '1',
  PRIMARY KEY (`IdBebida`),
  UNIQUE KEY `uq_bebidas_nombre` (`Nombre`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8;

CREATE TABLE `usuario` (
  `IdUsuario` int(11) NOT NULL AUTO_INCREMENT,
  `NombreUsuario` varchar(45) NOT NULL,
  `Contraseña` varchar(79) NOT NULL,
  `Rol` varchar(20) NOT NULL DEFAULT 'CLIENTE',
  PRIMARY KEY (`IdUsuario`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8;

CREATE TABLE `cliente` (
  `IdCliente` int(11) NOT NULL AUTO_INCREMENT,
  `Nombre` varchar(50) NOT NULL,
  `Apellido` varchar(50) NOT NULL,
  `Telefono` varchar(15) NOT NULL,
  `Correo` varchar(100) NOT NULL,
  `Usuario_IdUsuario` int(11) NOT NULL,
  PRIMARY KEY (`IdCliente`),
  UNIQUE KEY `Correo` (`Correo`),
  KEY `Usuario_IdUsuario` (`Usuario_IdUsuario`),
  CONSTRAINT `cliente_ibfk_1` FOREIGN KEY (`Usuario_IdUsuario`) REFERENCES `usuario` (`IdUsuario`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8;

CREATE TABLE `empleado` (
  `IdEmpleado` int(11) NOT NULL AUTO_INCREMENT,
  `Nombre` varchar(50) NOT NULL,
  `Apellido` varchar(50) NOT NULL,
  `Telefono` varchar(15) NOT NULL,
  `Correo` varchar(100) NOT NULL,
  `Usuario_IdUsuario` int(11) NOT NULL,
  PRIMARY KEY (`IdEmpleado`),
  UNIQUE KEY `Correo` (`Correo`),
  KEY `Usuario_IdUsuario` (`Usuario_IdUsuario`),
  CONSTRAINT `empleado_ibfk_1` FOREIGN KEY (`Usuario_IdUsuario`) REFERENCES `usuario` (`IdUsuario`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8;

CREATE TABLE `cortecaja` (
  `idCorteCaja` int(11) NOT NULL AUTO_INCREMENT,
  `Hora_Inicio` varchar(10) NOT NULL,
  `Hora_Terminar` varchar(10) NOT NULL,
  `Fecha_Inicio` varchar(10) NOT NULL,
  `DineroEnCaja` double NOT NULL,
  `IngresoDia` double NOT NULL,
  `EgresoDIa` double NOT NULL,
  `PlatillosVendidos` int(11) NOT NULL,
  `DineroFinalizar` double NOT NULL,
  `TiempoTrascurrido` int(11) NOT NULL,
  `FechaFinalizar` date NOT NULL,
  `Administrador_idAdministrador` int(11) NOT NULL,
  `IdEmpleado` int(11) DEFAULT NULL,
  PRIMARY KEY (`idCorteCaja`),
  KEY `fk_CorteCaja_Administrador1_idx` (`Administrador_idAdministrador`),
  KEY `idx_cortecaja_idempleado` (`IdEmpleado`),
  CONSTRAINT `fk_cortecaja_empleado` FOREIGN KEY (`IdEmpleado`) REFERENCES `empleado` (`IdEmpleado`) ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8;

CREATE TABLE `ventas` (
  `IdVentas` int(11) NOT NULL AUTO_INCREMENT,
  `Hora` varchar(45) NOT NULL,
  `FechaVenta` date NOT NULL,
  `DetalleVenta` varchar(45) NOT NULL,
  `CorteCaja_idCorteCaja` int(11) NOT NULL,
  PRIMARY KEY (`IdVentas`),
  KEY `fk_Ventas_CorteCaja1_idx` (`CorteCaja_idCorteCaja`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8;

CREATE TABLE `detalleventas` (
  `idDetalleVentas` int(11) NOT NULL AUTO_INCREMENT,
  `Subtotal` float NOT NULL,
  `Impuesto` float NOT NULL,
  `Descuento` float NOT NULL,
  `Total` float NOT NULL,
  `Ventas_IdVentas` int(11) NOT NULL,
  PRIMARY KEY (`idDetalleVentas`),
  KEY `fk_DetalleVentas_Ventas1_idx` (`Ventas_IdVentas`),
  CONSTRAINT `fk_DetalleVentas_Ventas1` FOREIGN KEY (`Ventas_IdVentas`) REFERENCES `ventas` (`IdVentas`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8;

CREATE TABLE `entradarecibe` (
  `IdEntradaProductoa` int(11) NOT NULL,
  `FechaRecibo` date NOT NULL,
  `EmpleadoRecibio` varchar(45) NOT NULL,
  `CorteCaja_idCorteCaja` int(11) NOT NULL,
  PRIMARY KEY (`IdEntradaProductoa`),
  KEY `fk_EntradaRecibe_CorteCaja1_idx` (`CorteCaja_idCorteCaja`),
  CONSTRAINT `fk_EntradaRecibe_CorteCaja1` FOREIGN KEY (`CorteCaja_idCorteCaja`) REFERENCES `cortecaja` (`idCorteCaja`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8;

CREATE TABLE `entradasproductos` (
  `IdEntradasProductos` int(11) NOT NULL AUTO_INCREMENT,
  `Cantidad` int(11) NOT NULL,
  `Fecha` date NOT NULL,
  `Descripcion` varchar(45) NOT NULL,
  `CorteCaja_idCorteCaja` int(11) NOT NULL DEFAULT '1',
  PRIMARY KEY (`IdEntradasProductos`),
  KEY `fk_EntradasProductos_CorteCaja1_idx` (`CorteCaja_idCorteCaja`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8;

CREATE TABLE `estatuspedido` (
  `IdEstatusPedido` int(11) NOT NULL AUTO_INCREMENT,
  `SituacionPedido` varchar(20) NOT NULL,
  PRIMARY KEY (`IdEstatusPedido`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8;

INSERT INTO `estatuspedido` (`IdEstatusPedido`, `SituacionPedido`) VALUES
(1, 'Pagado'),
(2, 'En preparación'),
(3, 'Pedido Realizado'),
(4, 'Entregado'),
(5, 'Cancelado');

CREATE TABLE `generarpedido` (
  `IdGenerarPedido` int(11) NOT NULL AUTO_INCREMENT,
  `HoraPedido` time NOT NULL,
  `FechaPedido` date NOT NULL,
  `Producto` varchar(500) DEFAULT NULL,
  `Observaciones` text,
  `Total` decimal(10,2) DEFAULT NULL,
  `NumeroMesa` int(11) NOT NULL,
  `Estatus` varchar(20) NOT NULL,
  `EstatusPedido_IdEstatusPedido` int(11) NOT NULL,
  `Clientes_Idcliente` int(11) NOT NULL,
  PRIMARY KEY (`IdGenerarPedido`),
  KEY `fk_GenerarPedido_EstatusPedido2_idx` (`EstatusPedido_IdEstatusPedido`),
  KEY `fk_GenerarPedido_Clientes1_idx` (`Clientes_Idcliente`),
  CONSTRAINT `fk_GenerarPedido_EstatusPedido2` FOREIGN KEY (`EstatusPedido_IdEstatusPedido`) REFERENCES `estatuspedido` (`IdEstatusPedido`) ON DELETE NO ACTION ON UPDATE NO ACTION
) ENGINE=InnoDB DEFAULT CHARSET=utf8;

CREATE TABLE `productos` (
  `IdProductos` int(11) NOT NULL AUTO_INCREMENT,
  `Nombre` varchar(30) NOT NULL,
  `Precio` double NOT NULL,
  `FechaCaducidad` int(11) NOT NULL,
  `Descripcion` varchar(45) NOT NULL,
  `Marca` varchar(25) NOT NULL,
  `UnidadMedida` varchar(25) NOT NULL,
  `CorteCaja_idCorteCaja` int(11) NOT NULL DEFAULT '1',
  PRIMARY KEY (`IdProductos`),
  KEY `fk_Productos_CorteCaja1_idx` (`CorteCaja_idCorteCaja`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8;

CREATE TABLE `generarpedido_detalle` (
  `IdGenerarPedidoDetalle` int(11) NOT NULL AUTO_INCREMENT,
  `GenerarPedido_IdGenerarPedido` int(11) NOT NULL,
  `Producto_IdProductos` int(11) DEFAULT NULL,
  `NombreProducto` varchar(100) NOT NULL,
  `Cantidad` int(11) NOT NULL DEFAULT '1',
  `PrecioUnitario` decimal(10,2) NOT NULL DEFAULT '0.00',
  `Subtotal` decimal(10,2) NOT NULL DEFAULT '0.00',
  `Personalizacion` text,
  PRIMARY KEY (`IdGenerarPedidoDetalle`),
  KEY `idx_gpd_pedido` (`GenerarPedido_IdGenerarPedido`),
  KEY `idx_gpd_producto` (`Producto_IdProductos`),
  CONSTRAINT `fk_gpd_pedido` FOREIGN KEY (`GenerarPedido_IdGenerarPedido`) REFERENCES `generarpedido` (`IdGenerarPedido`) ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT `fk_gpd_producto` FOREIGN KEY (`Producto_IdProductos`) REFERENCES `productos` (`IdProductos`) ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8;

CREATE TABLE `generarrecibo` (
  `IdGenerarRecibo` int(11) NOT NULL,
  `FechaRecibo` varchar(45) NOT NULL,
  `HoraRecibo` varchar(45) NOT NULL,
  `descripcion` varchar(45) NOT NULL,
  `Ventas_IdVentas` int(11) NOT NULL,
  PRIMARY KEY (`IdGenerarRecibo`),
  KEY `fk_GenerarRecibo_Ventas1_idx` (`Ventas_IdVentas`),
  CONSTRAINT `fk_GenerarRecibo_Ventas1` FOREIGN KEY (`Ventas_IdVentas`) REFERENCES `ventas` (`IdVentas`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8;

CREATE TABLE `ingresos_egresos` (
  `idMovimiento` int(11) NOT NULL AUTO_INCREMENT,
  `TipoMovimiento` varchar(20) DEFAULT NULL,
  `Monto` decimal(10,2) DEFAULT NULL,
  `Descripcion` text,
  `Fecha` date DEFAULT NULL,
  `Hora` time DEFAULT NULL,
  `CorteCaja_idCorteCaja` int(11) DEFAULT NULL,
  PRIMARY KEY (`idMovimiento`),
  KEY `idx_ingresos_egresos_corte` (`CorteCaja_idCorteCaja`),
  CONSTRAINT `fk_ingresos_egresos_corte` FOREIGN KEY (`CorteCaja_idCorteCaja`) REFERENCES `cortecaja` (`idCorteCaja`) ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8;

CREATE TABLE `productosstock` (
  `IdProductosStock` int(11) NOT NULL AUTO_INCREMENT,
  `Producto_IdProductos` int(11) DEFAULT NULL,
  `Nombre` varchar(45) NOT NULL,
  `Descripcion` varchar(35) NOT NULL,
  `Cantidad` int(11) NOT NULL DEFAULT '0',
  `CorteCaja_idCorteCaja` int(11) NOT NULL,
  `Apariencia` varchar(255) DEFAULT NULL,
  PRIMARY KEY (`IdProductosStock`),
  KEY `fk_ProductosStock_CorteCaja1_idx` (`CorteCaja_idCorteCaja`),
  KEY `idx_productosstock_producto` (`Producto_IdProductos`),
  CONSTRAINT `fk_productosstock_producto` FOREIGN KEY (`Producto_IdProductos`) REFERENCES `productos` (`IdProductos`) ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8;

CREATE TABLE `recibos` (
  `idRecibo` int(11) NOT NULL AUTO_INCREMENT,
  `Producto` varchar(255) NOT NULL,
  `Total` decimal(10,2) NOT NULL,
  `Fecha` date NOT NULL,
  `Hora` time NOT NULL,
  `Usuario` varchar(100) NOT NULL,
  PRIMARY KEY (`idRecibo`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8;

CREATE TABLE `recibospedidos` (
  `IdRecibosPedidos` int(11) NOT NULL AUTO_INCREMENT,
  `Producto` varchar(255) NOT NULL,
  `Total` decimal(10,2) NOT NULL,
  `Fecha` date NOT NULL,
  `Hora` time NOT NULL,
  `Usuario` varchar(100) NOT NULL,
  PRIMARY KEY (`IdRecibosPedidos`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8;

CREATE TABLE `salidasproductos` (
  `IdSalidasProductos` int(11) NOT NULL AUTO_INCREMENT,
  `FechaSalida` date NOT NULL,
  `Detalle` varchar(45) NOT NULL,
  `Cantidad` varchar(45) NOT NULL,
  `CorteCaja_idCorteCaja` int(11) DEFAULT NULL,
  PRIMARY KEY (`IdSalidasProductos`),
  KEY `fk_SalidasProductos_CorteCaja1_idx` (`CorteCaja_idCorteCaja`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8;

CREATE TABLE `solicitudes_password` (
  `IdSolicitud` int(11) NOT NULL AUTO_INCREMENT,
  `IdUsuario` int(11) NOT NULL,
  `NombreUsuario` varchar(50) NOT NULL,
  `TipoCuenta` enum('cliente','empleado') NOT NULL,
  `Correo` varchar(100) NOT NULL,
  `Estado` enum('Pendiente','Atendida') DEFAULT 'Pendiente',
  `FechaSolicitud` datetime DEFAULT CURRENT_TIMESTAMP,
  `PasswordTemporal` varchar(255) DEFAULT NULL,
  `FechaAtencion` datetime DEFAULT NULL,
  PRIMARY KEY (`IdSolicitud`),
  KEY `IdUsuario` (`IdUsuario`),
  CONSTRAINT `solicitudes_password_ibfk_1` FOREIGN KEY (`IdUsuario`) REFERENCES `usuario` (`IdUsuario`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8;

CREATE TABLE `tipossalidas` (
  `idTiposSalidas` int(11) NOT NULL AUTO_INCREMENT,
  `ConceptoSalida` varchar(45) NOT NULL,
  `SalidasProductos_IdSalidasProductos` int(11) NOT NULL,
  PRIMARY KEY (`idTiposSalidas`),
  KEY `fk_TiposSalidas_SalidasProductos1_idx` (`SalidasProductos_IdSalidasProductos`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8;

-- ------------------------------------------------------------
-- Consentimiento del aviso de privacidad.
-- La migracion migracion_privacidad.sql que menciona
-- servicio_privacidad.py no esta en el repositorio; esta tabla se
-- dedujo de la consulta que hace registrar_consentimiento(). Si la
-- version de Railway tiene otras columnas, ajustala aqui.
-- ------------------------------------------------------------
CREATE TABLE `consentimiento_privacidad` (
  `IdConsentimiento` int(11) NOT NULL AUTO_INCREMENT,
  `Usuario_IdUsuario` int(11) NOT NULL,
  `VersionAviso` varchar(20) NOT NULL,
  `Origen` varchar(30) NOT NULL,
  `FechaConsentimiento` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`IdConsentimiento`),
  KEY `idx_consentimiento_usuario` (`Usuario_IdUsuario`),
  CONSTRAINT `fk_consentimiento_usuario` FOREIGN KEY (`Usuario_IdUsuario`) REFERENCES `usuario` (`IdUsuario`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
