# V10.8 – Inicio rápido + RUT inteligente

Esta versión parte de **V10.7 Reorganización visual verificada** y conserva su estructura de despliegue.

## 1. Apertura de empresas mucho más liviana

Antes, al pulsar **Entrar** el navegador esperaba de forma secuencial múltiples consultas: cuentas, centros de costo, comprobantes, empleados, aprendizaje, periodos, exportaciones, calendario, cargas y además descargaba listados completos de documentos para calcular el dashboard.

Ahora:

- Al entrar a una empresa se abre inmediatamente el espacio de trabajo.
- El Inicio usa un único endpoint liviano: `GET /empresas/{id}/inicio`.
- Los indicadores de documentos se calculan con agregados SQL (`COUNT/GROUP BY`), sin descargar todas las facturas al navegador.
- Historial, cuentas, empleados, comprobantes, periodos y exportaciones se cargan **solo cuando el usuario entra al módulo que los necesita**.
- Al abrir Recibidas/Emitidas se determina primero el periodo más reciente, para evitar una consulta inicial innecesaria de todo el histórico.

## 2. Nuevo Inicio

El Inicio muestra:

- pendientes;
- contabilizados;
- documentos por revisar;
- registros de historial aprendidos;
- exportaciones;
- próximos 5 vencimientos;
- alertas de parametrización tributaria;
- estado del RUT.

## 3. Cargue opcional del RUT DIAN

En **Clientes → Perfil tributario** se agregó **RUT DIAN (opcional)**.

Flujo:

1. Seleccionar PDF del RUT.
2. Pulsar **Analizar RUT**.
3. El sistema valida que el NIT corresponda al cliente seleccionado.
4. Extrae y presenta para revisión:
   - tipo de persona;
   - dirección seccional;
   - municipio informado en el RUT;
   - actividades CIIU;
   - responsabilidades, calidades y atributos.
5. El contador pulsa **Confirmar y aplicar al perfil** si está de acuerdo.

El programa **no modifica el perfil automáticamente al subir el archivo**.

## 4. Responsabilidades que puede trasladar al perfil

A partir de los códigos efectivamente presentes en el RUT se actualizan, cuando el usuario confirma:

- 05: renta ordinaria;
- 07 / 09 / 15: obligación relacionada con retenciones/autoretención;
- 14: información exógena;
- 47: Régimen Simple;
- 48: IVA.

Además se conservan y muestran otros códigos detectados, por ejemplo 42, 52 y 55, aunque todavía no tengan un campo booleano independiente en el perfil.

### Importante

- El RUT **no determina por sí solo** si el IVA es bimestral o cuatrimestral. Esa periodicidad queda para validación del contador.
- El RUT nacional **no activa ICA/ReteICA automáticamente**. La obligación territorial sigue siendo configurable.

## 5. Privacidad y almacenamiento

El PDF se procesa en memoria y **no se guarda** en el almacenamiento de documentos del aplicativo.

Se conserva en base de datos únicamente información tributaria estructurada necesaria para el perfil: NIT/DV detectados, formulario, tipo de persona, seccional, municipio, actividades, responsabilidades, fecha de generación y hash del archivo.

No se almacenan desde el RUT para esta función: correo, teléfono, dirección física ni datos de representantes.

## 6. Historial de RUT

La nueva tabla `ruts_empresa` conserva las versiones analizadas por empresa y permite detectar códigos agregados o retirados respecto del RUT anterior. Solo una versión queda marcada como activa.

Migración nueva:

`b2c3d4e5f6a7_rut_empresa_historial.py`

El `entrypoint.sh` ya ejecuta `alembic upgrade head`, por lo que Render aplicará la migración automáticamente al desplegar.

## Verificaciones realizadas

- Cadena completa de migraciones en SQLite hasta el nuevo `head`.
- Análisis real de un RUT DIAN de prueba para comprobar estructura de PDF.
- Validación de NIT empresa ↔ RUT.
- Extracción de actividades y responsabilidades.
- Aplicación confirmada del RUT al perfil tributario.
- Endpoint de Inicio rápido.
- Compilación Python completa.
- Validación sintáctica del JavaScript del frontend con Node.
