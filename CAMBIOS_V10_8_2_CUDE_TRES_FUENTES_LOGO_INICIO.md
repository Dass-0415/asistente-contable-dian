# V10.8.2 — CUFE/CUDE, documentos equivalentes y logo de inicio

## 1. Identificador fiscal único CUFE/CUDE
- El campo físico histórico `cufe` se conserva por compatibilidad con la base de datos y exportadores, pero la lógica lo trata como **identificador fiscal único** que puede ser CUFE o CUDE.
- El Excel DIAN con encabezado **CUFE/CUDE** se reconoce automáticamente.
- Prioridad de fuentes: **XML > PDF > Excel DIAN**.
- Se conserva en el snapshot de extracción qué identificador reportó cada fuente y cuáles coincidieron.
- Si XML, PDF y/o Excel discrepan, se conserva un solo documento, prevalece la fuente más precisa y el registro queda en revisión con una alerta explícita. No se crean registros separados por cada fuente.

## 2. Duplicados y enriquecimiento de un documento existente
- La coincidencia exacta de CUFE/CUDE dentro de la misma empresa reutiliza el registro ya existente en vez de insertar otra factura.
- Si primero llegó PDF o Excel y posteriormente llega el XML del mismo documento, el registro existente se enriquece con la fuente XML y se conserva como una sola factura.
- El control de duplicados sigue aislado por `empresa_id`.
- Si el documento queda posteriormente verificado por XML + PDF + Excel y no hay otra alerta, puede volver al flujo normal sin quedar artificialmente marcado como duplicado.

## 3. Documento Equivalente Electrónico SPD
- Soporte para UBL de Documento Equivalente Electrónico de Servicios Públicos Domiciliarios (SPD), código DIAN 60.
- Detección por `ProfileID`, `InvoiceTypeCode` y esquema `CUDE`.
- El parser XML lee los campos de cabecera como hijos directos del documento, evitando confundir IDs y fechas presentes dentro de `UBLExtensions`.
- Se extraen correctamente CUDE, número de documento, fecha, vencimiento, emisor, receptor, dirección, total, IVA, líneas, contrato y referencias de pago disponibles.
- El PDF tiene reglas específicas para Documento Equivalente antes de aplicar expresiones genéricas, evitando tomar teléfono o NIT del proveedor tecnológico como datos del emisor.
- Cuando existe XML + PDF, el texto embebido del PDF se usa como segunda fuente de verificación sin activar OCR innecesario.

## 4. Seguridad de pertenencia a empresa
- Un documento se marca como `emitida` cuando la empresa activa coincide con el emisor.
- Se marca como `recibida` cuando coincide con el receptor.
- Si no coincide con ninguno, queda `no_aplica` y requiere revisión; ya no se asume automáticamente que todo documento cuyo emisor sea distinto es una compra de la empresa.

## 5. Interfaz
- La columna y el mapeo visible usan la etiqueta **CUFE/CUDE**.
- En la esquina superior izquierda se retiró el bloque de texto “Asistente Contable DIAN / DIAN → aprendizaje → contabilización → exportación”.
- En su lugar se muestra el logo existente de la aplicación.
- El logo funciona como botón de inicio discreto: con una empresa activa vuelve a su Inicio; sin empresa activa vuelve al portal/listado de empresas.

## Verificaciones realizadas
- Compilación completa del backend Python: OK.
- Sintaxis JavaScript del frontend: OK.
- Documento SPD suministrado: XML y PDF emparejados y leídos como un solo Documento Equivalente con CUDE: OK.
- Carga PDF primero y posterior XML + PDF + Excel: permanece un solo registro y se enriquece: OK.
- Coincidencia del mismo CUDE en XML + PDF + Excel: verificación de tres fuentes: OK.
- CUFE/CUDE discordante en Excel frente a XML/PDF: un solo registro, prioridad XML y estado de revisión: OK.
- Documento cuyo emisor y receptor no corresponden a la empresa activa: `no_aplica` + revisión: OK.

El XML/PDF usados para las pruebas no se incluyen en el proyecto ni quedan como datos de ejemplo, semillas o fixtures.
