# Asistente Contable DIAN — V10.4

Base: V10.3 estable. Esta versión conserva el cargue rápido, cargos/descuentos/propinas, Total DIAN, estados de proceso, trazabilidad y exportación SIIGO existentes.

## Cambios aprobados implementados

1. **Aprendizaje contable por historial de cada empresa y tercero**
   - Prioridad: empresa + proveedor/tercero + historial real.
   - El concepto/ítem XML solo afina la sugerencia cuando existe evidencia repetida; referencias aisladas no mandan la clasificación.
   - Si la evidencia es insuficiente no se asigna una cuenta automáticamente.

2. **Confianza de sugerencias y clasificación masiva**
   - Niveles: alta, media y baja.
   - Solo las sugerencias de alta confianza pueden entrar en la generación masiva automática.
   - Media/baja quedan en revisión.

3. **Retenciones sugeridas de forma conservadora**
   - Usa historial técnico real de la misma empresa, tercero y cuenta/contexto.
   - Prioriza evidencia de la misma vigencia; evidencia antigua o inestable baja la confianza.
   - ReteFuente, ReteICA y ReteIVA requieren confirmación del usuario; confianza baja nunca se aplica.
   - Los valores originales DIAN no se sobrescriben.
   - Si se cambia una retención después de generar una partida no exportada, la partida anterior se invalida y debe regenerarse.

4. **Bandeja de excepciones mejorada**
   - Motivos de revisión más claros: historial insuficiente, cuenta/contrapartida, diferencia DIAN, nota sin documento origen, tercero sin identificar, etc.
   - Filtro documental exclusivo: elegir Factura reemplaza Nota Crédito, etc.; no se acumulan selecciones anteriores.
   - Recibidas y emitidas conservan estados de filtro separados sin arrastrar el tipo documental entre vistas.

5. **Relación Nota Crédito/Débito con factura original**
   - Prioridad: CUFE/CUDE referenciado en UBL, luego prefijo-folio y finalmente evidencia auxiliar de tercero/fecha/valor.
   - Solo se relaciona automáticamente cuando la evidencia es clara.
   - Si es ambiguo queda para revisión y puede confirmarse manualmente.

6. **Numeración SIIGO independiente por tipo documental**
   - Factura, Nota Crédito, Nota Débito, documento equivalente, etc. usan secuencias internas separadas.
   - Cada tipo configurado con numeración interna solicita su propio número inicial solo para esa exportación.
   - Si un tipo usa **Folio DIAN**, no se pide consecutivo interno y se toma el folio del documento.
   - Los consecutivos internos siguen sin memoria entre exportaciones.

## Despliegue

- Nueva migración Alembic `d2e4f6a8b001` aditiva; conserva datos existentes.
- `render.yaml` ya no declara una PostgreSQL gratuita de Render. La aplicación usa la `DATABASE_URL` de Neon configurada como secreto en Render.
