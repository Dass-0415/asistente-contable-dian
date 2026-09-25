# V10.6.3 – Corrección IVA y perfil tributario

Correcciones:
- La cuenta manual de IVA descontable/generado aparece siempre que el documento tenga IVA.
- La cuenta manual de IVA tiene prioridad incluso si el perfil del cliente quedó marcado como no responsable de IVA.
- Si no se fuerza una cuenta manual, se conserva el tratamiento según el perfil tributario del cliente.
- Se muestra una advertencia en la factura cuando existe IVA pero el perfil del cliente dice “No responsable de IVA”.
- Se mantiene la lógica automática existente para clientes correctamente marcados como responsables de IVA.

Caso validado:
Factura FG-859: subtotal 1.566.000, IVA 297.540, total 1.863.540.
El sistema ya permite separar el IVA manualmente en una cuenta descontable en lugar de absorberlo obligatoriamente en el gasto.
