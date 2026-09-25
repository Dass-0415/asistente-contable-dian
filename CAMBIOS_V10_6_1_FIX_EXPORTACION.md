# V10.6.1 – Fix exportación

Se corrigió una regresión en `PlantillaOut`: el esquema de una plantilla de exportación estaba exigiendo por error el campo `tipo_persona`, que pertenece exclusivamente a Empresa.

El error producía HTTP 500 al abrir/preparar la plantilla automática SIIGO antes de exportar.

Pruebas realizadas:
- `PlantillaOut` serializa correctamente una plantilla SIIGO sin `tipo_persona`.
- Endpoint `/empresas/{id}/plantillas/siigo-automatica`: HTTP 200.
- Migraciones Alembic desde base vacía: OK.
- Python: compilación OK.
- JavaScript del frontend: sintaxis OK.
