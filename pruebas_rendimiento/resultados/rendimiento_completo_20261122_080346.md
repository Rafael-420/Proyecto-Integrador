# Resultados de rendimiento — Corallie Bubble

- Fecha: 2026-11-22 08:03
- Modo: completo
- Equipo: Windows 11, 12 núcleos, Python 3.12.1
- Servidor: MySQL 10.4.32-MariaDB (local, UTC y modo estricto como Railway)
- Pool de la app: 5 conexiones; contraseñas con PBKDF2 de 600,000 iteraciones
- Base de volumen: 2,000 clientes, 20,500 pedidos, 365 cortes con 10,950 ventas, 60 bebidas (20 con foto). Se cargó en 1.8 s.

## Metas

| Meta | Resultado | ¿Se cumple? |
|---|---|---|
| Consultas con la base grande: p95 < 500 ms (sin contar el inicio de sesión) | peor p95 = 3.5 ms, errores = 0 | Sí |
| Flujo de pedido con 25 clientes a la vez: p95 < 2 s | p95 = 525 ms | Sí |
| Sin errores con hasta 50 clientes a la vez | errores = 0 | Sí |
| Ningún pedido se pierde ni se duplica bajo carga | la base coincide con lo confirmado | Sí |
| Un solo pedido aunque se confirme desde 20 dispositivos a la vez | pedidos en curso = 1 | Sí |

## 1. Volumen: tiempo de cada consulta con la base grande

30 repeticiones por operación. "Viajes" son las instrucciones que la app manda al servidor; la última columna suma 50 ms de internet por viaje a la mediana local (estimación, ver notas).

| Operación | Viajes | p50 (ms) | p95 (ms) | Máx (ms) | Errores | Estimado con 50 ms de red (ms) |
|---|---:|---:|---:|---:|---:|---:|
| Marcar 300 pedidos vencidos como no recogidos (una vez) | — | 10.4 | — | — | 0 | — |
| Ver menú (fotos sin caché) | 8 | 1.6 | 2.1 | 2.3 | 0 | 402 |
| Ver menú (fotos en caché) | 4 | 0.9 | 1.3 | 1.3 | 0 | 201 |
| Historial del cliente (últimos 25) | 4 | 0.5 | 0.7 | 1.0 | 0 | 200 |
| Estado del pedido en curso | 4 | 0.4 | 0.6 | 0.7 | 0 | 200 |
| Revisar si puede pedir | 13 | 2.8 | 3.5 | 11.0 | 0 | 653 |
| Revisar adeudo | 4 | 0.7 | 1.1 | 1.2 | 0 | 201 |
| Resumen de un corte de caja | 5 | 0.8 | 1.8 | 2.3 | 0 | 251 |
| Barrido de no recogidos (sin pendientes) | 7 | 1.3 | 1.7 | 1.7 | 0 | 351 |
| Inicio de sesión (PBKDF2, 600,000 iteraciones) | 38 | 288 | 355 | 435 | 0 | 2,188 |

## 2. Carga: clientes haciendo su pedido al mismo tiempo

Cada cliente inicia sesión y repite 3 veces el flujo: revisar si puede pedir, ver el menú, confirmar el pedido y ver su estado (entre rondas cancela el pedido para poder pedir otra vez). Todos arrancan en el mismo instante y comparten un solo proceso, como en la versión web.

| Clientes a la vez | Flujos | Errores | Flujo p50 (ms) | Flujo p95 (ms) | Flujo máx (ms) | Login p50 (ms) | Login p95 (ms) | Pedidos por segundo | Conexiones máx. en MySQL |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 10 | 30 | 0 | 47.9 | 71.2 | 82.0 | 1,752 | 1,799 | 15.0 | 11 |
| 25 | 75 | 0 | 242 | 525 | 680 | 3,885 | 3,948 | 15.3 | 26 |
| 50 | 150 | 0 | 478 | 1,241 | 1,861 | 8,029 | 8,211 | 14.8 | 51 |

Tiempo de cada paso (p95, ms):

| Paso | 10 clientes | 25 clientes | 50 clientes |
|---|---:|---:|---:|
| Inicio de sesión | 1,799 | 3,948 | 8,211 |
| Revisar si puede pedir | 39.9 | 345 | 736 |
| Ver menú | 12.6 | 26.0 | 62.0 |
| Confirmar pedido | 40.1 | 322 | 640 |
| Ver estado del pedido | 6.4 | 18.1 | 9.5 |
| Cancelar pedido | 8.9 | 13.7 | 12.5 |

Integridad de los datos después de cada nivel:

| Clientes a la vez | Pedidos esperados | Confirmados por la app | Registrados en la base | Clientes con pedidos de más |
|---:|---:|---:|---:|---:|
| 10 | 30 | 30 | 30 | 0 |
| 25 | 75 | 75 | 75 | 0 |
| 50 | 150 | 150 | 150 | 0 |

## 3. Carrera: el mismo cliente confirma desde varios dispositivos a la vez

- Dispositivos: 20
- Respuestas: aceptado: 1, rechazado (pedido_activo): 19
- Pedidos en curso del cliente al terminar: 1 (debe ser 1)

## 4. Estrés: más clientes de los que el local espera

Cada cliente hace el flujo una vez, sin iniciar sesión, todos en el mismo instante.

| Clientes a la vez | Flujos completos | Errores | Flujo p50 (ms) | Flujo p95 (ms) | Conexiones máx. en MySQL | Errores encontrados |
|---:|---:|---:|---:|---:|---:|---|
| 100 | 100 de 100 | 0 | 637 | 983 | 101 | ninguno |
| 150 | 150 de 150 | 0 | 1,018 | 1,457 | 151 | ninguno |
| 200 | 190 de 200 | 10 | 1,122 | 1,593 | 152 | motivo error_conexion (8); menu con 0 bebidas (2) |

## 5. Capacidad de conexiones: la app instalada en cada celular

Cada copia de la app abre su propio pool de 5 conexiones al conectarse y las mantiene abiertas. El servidor acepta hasta 151 conexiones (max_connections).

- Conexiones ya abiertas antes de la prueba: 1
- Copias de la app conectadas a la vez antes del primer rechazo: **30**
- Conexiones abiertas en ese momento: 151
- Respuesta del servidor a la siguiente copia: DatabaseError 1040: Too many connections

## Notas para interpretar los números

- Los tiempos se midieron contra un MySQL en el mismo equipo, sin internet de por medio. Con Railway cada viaje a la base suma la latencia de la red; la columna "Estimado" de la tabla 1 lo aproxima con 50 ms por viaje (se puede cambiar con --latencia-red-ms).
- p50 es la mediana; p95 es el tiempo dentro del cual terminó el 95 % de las veces.
- En las fases de carga y estrés todos los clientes comparten un proceso y un pool, como en la versión web de Flet. La fase 5 mide el caso de la app instalada en cada celular, donde cada copia tiene su propio pool.
- El inicio de sesión es lento a propósito: PBKDF2 hace costoso adivinar contraseñas. Ocupa el procesador, así que varios inicios de sesión a la vez se forman en fila según los núcleos del equipo (12 aquí).
