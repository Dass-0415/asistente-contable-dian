# V10.8.4 — Carga DIAN estable en Render

## Problema corregido
La ruta `POST /empresas/{empresa_id}/documentos/cargar` estaba declarada como `async def`, pero después de recibir los archivos ejecutaba trabajo síncrono y pesado (XML, PDF, pandas/openpyxl, conciliación y SQLAlchemy) dentro del event loop. Durante la carga, el servidor podía dejar de responder al health check `/salud`; en Render esto se observaba como reinicio del servicio y el navegador recibía HTTP 503.

## Cambios
- La carga DIAN ahora es una ruta síncrona (`def`) y FastAPI la ejecuta en su threadpool. El event loop queda libre para `/salud` y para las peticiones livianas.
- Se serializan las cargas pesadas dentro del proceso para evitar dos operaciones simultáneas compitiendo por la RAM/CPU limitada de la instancia Free.
- Se liberan los bytes originales de ZIP/XML/PDF antes de procesar el Excel y se fuerza recolección de memoria en los puntos de mayor consumo.
- Los documentos extraídos ya no retienen copias binarias de XML/PDF una vez que sus campos fueron interpretados. Se conservan nombres, campos, CUFE/CUDE y trazabilidad lógica.
- OCR de PDF se ejecuta página por página en vez de convertir todas las páginas a imágenes simultáneamente, reduciendo el pico de memoria.
- `/salud` ahora es asíncrono y responde directamente desde el event loop.
- SQLAlchemy usa `pool_pre_ping=True` y recicla conexiones PostgreSQL para tolerar mejor conexiones de Neon cerradas durante periodos de inactividad.
- Si la conciliación/BD falla inesperadamente, la transacción hace rollback y el usuario recibe un mensaje que confirma que no quedó una carga parcial.
- Se agregaron logs de inicio/fin de carga con empresa, cantidad de documentos, bytes y duración para diagnóstico en Render.

## Verificaciones realizadas
- Compilación completa de Python.
- Validación de sintaxis del JavaScript del frontend.
- Carga real del Documento Equivalente SPD suministrado por el usuario usando XML + PDF + Excel con `CUFE/CUDE`.
- Verificación de CUDE, número 17742089, naturaleza `documento_equivalente`, dirección `recibida` y total 586553.
- Repetición de la misma carga: permanece un único documento independiente, sin duplicar por CUDE.
- Prueba concurrente: mientras `procesar_carga` permanece ocupado, `/salud` respondió en ~0.002 s.
- Regresión multiempresa: cargas de dos empresas permanecen aisladas.
- Regresión de eliminación: eliminar la carga de una empresa retira sus facturas sin `ForeignKeyViolation` y no toca la otra empresa.

No requiere migración adicional de base de datos.
