# V10.8.3 — Corrección de eliminación de cargas DIAN

## Problema corregido
Al usar **Eliminar esta carga**, PostgreSQL/Neon podía responder con `ForeignKeyViolation` porque `cargas_documentos_dian` se intentaba eliminar mientras todavía existían filas de `facturas` con `carga_id` apuntando a esa carga.

## Cambio aplicado
La eliminación ahora se ejecuta explícitamente en orden hijo → padre:

1. valida que la carga pertenezca a la empresa activa;
2. bloquea la operación si detecta referencias cruzadas de otra empresa;
3. retira las relaciones operativas de exportación, conservando la trazabilidad histórica;
4. libera referencias de posibles duplicados dentro de la misma empresa;
5. elimina movimientos contables de los documentos de la carga;
6. elimina las facturas pertenecientes a esa carga;
7. fuerza el `flush` de esas eliminaciones;
8. verifica que ya no queden facturas referenciando la carga;
9. solo entonces elimina `cargas_documentos_dian`;
10. registra la auditoría y confirma la transacción.

Si PostgreSQL detecta otra dependencia no prevista, la transacción hace `rollback` y devuelve un mensaje controlado: **no se borra parcialmente la información**.

## Seguridad multiempresa
Todos los borrados operativos conservan el filtro por `empresa_id`. Si existe una referencia anómala desde otra empresa hacia la carga seleccionada, la eliminación se bloquea en lugar de tocar datos del otro cliente.

## Migraciones
No requiere migración de base de datos.

## Verificaciones realizadas
- Compilación Python completa: OK.
- Prueba con llave foránea activa: carga + factura se eliminan en orden correcto.
- Prueba de aislamiento: eliminar una carga de Empresa A no afecta la carga ni la factura de Empresa B.
- Prueba de referencia cruzada anómala: la operación se bloquea con HTTP 409 y conserva ambos registros.
