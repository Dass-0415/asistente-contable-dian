# V10.8.5 — Corrección de conexión Neon durante carga DIAN

## Causa real identificada
La V10.8.2 empezó a contrastar también el PDF asociado a cada XML para validar CUFE/CUDE con XML + PDF + Excel. Eso alargó la fase de lectura previa al guardado. Las dependencias de autenticación y empresa ya habían abierto una sesión/conexión SQLAlchemy antes de esa fase. Mientras se procesaban los archivos (o mientras una carga esperaba el lock de otra), esa conexión quedaba ociosa y Neon podía cerrar el socket.

La V10.8.4 corrigió el bloqueo del health check de Render, pero `pool_pre_ping` no podía recuperar una conexión que ya estaba prestada a la Session desde antes del procesamiento. El resultado observado fue `psycopg2.OperationalError: SSL connection has been closed unexpectedly` en el primer `INSERT INTO cargas_documentos_dian`.

## Corrección
- Después de validar autenticación, permisos y empresa se conserva únicamente `empresa.nit`, que es el dato requerido por el parser.
- La Session devuelve inmediatamente su conexión al pool antes de leer XML/PDF/Excel o esperar el lock de carga.
- Al comenzar la fase transaccional, la misma Session adquiere una conexión nueva. `pool_pre_ping=True` la valida en ese momento.
- Se mantienen el procesamiento fuera del event loop, `/salud` disponible, el control de memoria, el aislamiento multiempresa y la validación XML + PDF + Excel por CUFE/CUDE.
- No se relaja ninguna llave foránea ni se modifica Neon manualmente.

## Regresión que evita
La carga ya no depende de que una conexión obtenida durante la autenticación sobreviva todo el tiempo de lectura de documentos. Esto vuelve a separar correctamente dos fases: (1) extracción/conciliación de archivos y (2) transacción de base de datos.

No requiere migración de base de datos.
