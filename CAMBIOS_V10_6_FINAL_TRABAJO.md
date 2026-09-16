# Asistente Contable DIAN V10.6 — versión de trabajo consolidada

Base: V10.4.1 + mejoras aprobadas + reorganización V10.5 + pendientes cerrados.

## Incluye

- Inicio convertido en portada informativa, con logo y flujo de uso.
- Empresas simplificado para crear/seleccionar los clientes realmente administrados.
- Tipo de persona por cliente: Persona Natural / Persona Jurídica.
- Perfil tributario por cliente: IVA/periodicidad, SIMPLE, retención, renta, exógena, ICA y municipio/distrito.
- Calendario tributario por cliente:
  - vencimientos nacionales DIAN 2026 de IVA, retención, SIMPLE y renta de persona natural según perfil y terminación del NIT;
  - vencimientos territoriales/especiales manuales para ICA/ReteICA u obligaciones cuyo calendario depende de cada jurisdicción/resolución;
  - estados visuales de vencido, vence hoy, próximo y futuro.
- Parametrización contable centralizada en Historial contable.
- Parametrización de comprobantes/tipos documentales centralizada en Exportar.
- Eliminación de una sesión completa de carga DIAN sin afectar cargas anteriores.
- Conserva restricciones de seguridad cuando la carga contiene documentos ya exportados.
- Mantiene el fix de fechas offset-aware/offset-naive de notas crédito V10.4.1.
- Mantiene aprendizaje por historial, niveles de confianza, sugerencias de retenciones, relación de notas crédito/débito, filtros exclusivos y consecutivos por tipo documental.

## Validaciones realizadas

- Alembic: una sola revisión head.
- Migración simulada desde V10.4.1 conservando empresa existente.
- Instalación desde base vacía hasta head.
- Inicio API y frontend: OK.
- Perfil tributario y calendario automático/manual: OK.
- Carga real de 3 ZIP + Excel DIAN: 201 OK, 3 documentos relacionados.
- Eliminación completa de la carga: OK, 3 documentos retirados sin afectar otras sesiones.
- Eliminación de empresa con vencimientos manuales: OK.
- JavaScript: sintaxis válida.
- Python: compilación válida.

## Nota de calendario

El calendario automático se limita a obligaciones nacionales comunes configuradas y verificadas para la vigencia 2026. ICA/ReteICA y obligaciones con reglas especiales o territoriales se registran manualmente por cliente para evitar inventar fechas.
