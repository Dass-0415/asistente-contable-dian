# V10.6.2 – Corrección IVA generado/descontable

## Problema corregido
La reorganización de módulos había dejado sin interfaz la parametrización de cuentas base generales, entre ellas IVA descontable e IVA generado. Además, la selección automática de IVA podía quedar ambigua cuando existían varias cuentas 2408 o bases mixtas.

## Cambios
- Restaurada en Historial contable la sección **Cuentas contables de respaldo**.
- Se pueden configurar IVA descontable, IVA generado, proveedores/clientes, caja/banco, retenciones, INC e ingresos.
- Cada factura con IVA muestra el **IVA detectado** y una casilla opcional **Cuenta IVA descontable / Cuenta IVA generado**.
- La cuenta IVA elegida manualmente tiene prioridad absoluta sobre la sugerencia automática.
- Una cuenta IVA escrita manualmente puede crearse por código aunque todavía no exista en el catálogo aprendido.
- Mejorada la selección automática por polaridad (generado vs descontable), evitando usar una cuenta del IVA contrario.
- El XML conserva como base gravable la base real de TaxSubtotal para IVA cuando existe, mejorando facturas con partidas gravadas y excluidas mezcladas.
- Los mensajes de parametrización de nómina apuntan al módulo actual: Historial contable.

## Pruebas
- Compra $100.000 + IVA $19.000: gasto D 100.000 + IVA descontable D 19.000 + proveedor C 119.000: OK.
- Venta $100.000 + IVA $19.000: ingreso C 100.000 + IVA generado C 19.000 + cliente D 119.000: OK.
- Override manual de IVA con cuenta distinta: respetado y balanceado: OK.
- Factura mixta con subtotal 150.000, base IVA 100.000 e IVA 19.000: base gravable detectada correctamente: OK.
- Exportación: conserva línea de IVA como movimiento independiente: OK.
- Python, JavaScript, migraciones, /salud y /app: OK.
