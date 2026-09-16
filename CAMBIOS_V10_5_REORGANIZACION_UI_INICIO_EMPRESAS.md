# V10.5 – Reorganización de Inicio / Empresas / Historial / Exportación

## Cambios implementados

1. **Inicio reemplaza al antiguo Resumen**
   - Ahora es una pantalla de presentación de la aplicación.
   - Se agregó el logo del Asistente Contable DIAN.
   - Se incluyó guía visual del flujo de trabajo y accesos rápidos.
   - Se mantiene únicamente un bloque liviano de “Empresa activa” como contexto.

2. **Módulo Empresas simplificado**
   - Se conserva para crear, listar, activar y administrar solo las empresas/clientes que realmente se usarán.
   - Se agregó campo **Tipo de persona**: `Persona jurídica` / `Persona natural`.
   - Se agregó ficha básica de la empresa activa.

3. **Parametrización contable movida a Historial contable**
   - Aprendizaje contable.
   - Cuentas de nómina y provisiones.
   - Empleados.
   - Centros de costo.

4. **Parametrización documental movida a Exportar**
   - La configuración de **Comprobantes por tipo de documento** ahora está dentro de Exportar.

5. **Backend / modelo de datos**
   - Se agregó el campo `tipo_persona` en empresas.
   - Se actualizó esquema, API y migración Alembic.

## Archivos clave
- `frontend/index.html`
- `frontend/assets/logo_asistente_contable_dian.png`
- `backend/app/models/models.py`
- `backend/app/schemas/schemas.py`
- `backend/app/api/empresas.py`
- `backend/alembic/versions/f1b2c3d4e5f6_tipo_persona_en_empresa.py`
