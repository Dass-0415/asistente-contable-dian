# V10.4.1 — corrección de carga con notas crédito/débito

Corrección puntual sobre V10.4.

## Problema corregido
Durante `Cargar y relacionar`, la relación automática entre notas crédito/débito y su factura original podía comparar una fecha con zona horaria contra otra sin zona horaria. Python genera `TypeError: can't compare offset-naive and offset-aware datetimes`, devolviendo HTTP 500 y haciendo rollback de toda la carga.

## Corrección
- Para comparar proximidad entre documentos se usa el día calendario de emisión (`date`) en lugar de comparar directamente objetos `datetime` con configuraciones de zona horaria distintas.
- El orden auxiliar de candidatos usa igualmente fecha calendario, evitando el mismo error durante el `sort`.
- No se cambió la lógica de DIAN, SIIGO, cargue rápido, retenciones, filtros, confianza, consecutivos ni la relación por CUFE/prefijo-folio.

## Verificaciones
- Python compileall: OK.
- Prueba con factura `datetime` sin zona horaria + nota con UTC: OK.
- Prueba con candidatos mezclando fechas aware/naive/None: OK.
- `/salud`: 200.
- `/app/`: 200.
