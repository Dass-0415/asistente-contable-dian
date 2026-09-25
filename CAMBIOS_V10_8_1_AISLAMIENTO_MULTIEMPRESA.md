# V10.8.1 – Corrección crítica de aislamiento multiempresa

Esta versión parte de **V10.8 – Inicio rápido + RUT inteligente** y corrige un problema de interfaz que podía mostrar temporalmente información de la empresa anterior después de cambiar de cliente.

## Causa identificada

Los endpoints principales de documentos ya filtraban por `empresa_id`, pero con la carga diferida introducida en V10.8 podían quedar varias consultas asíncronas en curso al mismo tiempo. Si el usuario entraba a Empresa A y cambiaba a Empresa B antes de terminar una consulta de A, la respuesta atrasada de A podía llegar después y volver a pintar la tabla compartida del navegador.

El problema era especialmente visible en documentos cargados, cargas recientes, facturas, panel de clasificación, historial, exportaciones y otros módulos que reutilizan los mismos contenedores de la interfaz.

## Correcciones aplicadas

- Cada cambio de empresa cancela las consultas GET pendientes del cliente anterior mediante `AbortController`.
- Toda respuesta asociada al cliente activo se valida de nuevo antes de entregarse a la interfaz. Si durante la petición cambió la empresa, esa respuesta se descarta.
- Al cambiar de empresa se limpian inmediatamente tablas, indicadores, formularios, archivos seleccionados, IDs de exportación, filtros, periodos, caché de cuentas, datalists y resultados pertenecientes al cliente anterior.
- Las cargas directas que no pasan por el helper genérico (`fetch`) congelan el `empresa_id` al comenzar. Esto cubre carga DIAN, análisis de Excel, importación de balance/historial, inferencia de plantillas y generación de exportaciones.
- Se evita que un archivo seleccionado para Empresa A siga seleccionado al entrar a Empresa B.
- Se evita que una parametrización o cuenta no guardada de Empresa A quede disponible para guardarse accidentalmente en Empresa B.
- Las acciones administrativas sobre empresas no activas (reactivar/eliminar desde el portal) continúan funcionando y no se confunden con el control de contexto visual.

## Refuerzo del backend

Además del arreglo de interfaz, se reforzó el aislamiento del servidor:

- consultas de `Movimiento` relacionadas con facturas ahora incluyen también `Movimiento.empresa_id`;
- lecturas auxiliares de proveedores y usos de plantillas se restringen a la empresa correspondiente;
- después de procesar una carga DIAN se verifica una invariante: la carga no puede haber producido facturas de otra empresa. Si ocurriera una regresión futura, la transacción se revierte y se genera un error en vez de conservar datos cruzados.

## Verificación realizada

Se ejecutó una prueba de aislamiento con dos empresas independientes en una base temporal:

- Empresa A: `solo_A.zip` + `CUFE-A`;
- Empresa B: `solo_B.zip` + `CUFE-B`.

Se verificó por API que `/documentos-cargados`, `/cargas` y `/documentos` de cada empresa devuelven exclusivamente sus propios registros. Resultado: `AISLAMIENTO_MULTIEMPRESA_OK`.

También se validó nuevamente:

- compilación de todo el backend Python;
- sintaxis del JavaScript del frontend con Node;
- ausencia de consultas de facturas sin filtro de empresa en los endpoints activos revisados.

## Base de datos

**No requiere migración nueva.** La corrección conserva la base actual y no mueve, duplica ni borra registros existentes.
