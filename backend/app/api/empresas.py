from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.models import Empresa, Usuario, UsuarioEmpresa, VencimientoTributario
from app.schemas.schemas import EmpresaCreate, EmpresaOut, EmpresaCuentasBase, EmpresaComprobantesPorTipo, EmpleadoCreate, EmpleadoOut, EmpresaPerfilTributarioUpdate, VencimientoTributarioCreate
from app.services.auditoria_service import registrar as auditoria_registrar
from app.core.security import usuario_actual, get_empresa_activa, get_current_user, require_superadmin, verificar_permiso_empresa

router = APIRouter(prefix="/empresas", tags=["empresas"])


@router.post("", response_model=EmpresaOut, status_code=201)
def crear_empresa(payload: EmpresaCreate, db: Session = Depends(get_db),
                   usuario: str = Depends(usuario_actual),
                   admin_user: Usuario | None = Depends(get_current_user)):
    existente = db.query(Empresa).filter(Empresa.nit == payload.nit).first()
    if existente:
        raise HTTPException(status_code=409, detail=f"Ya existe una empresa con NIT {payload.nit}.")
    empresa = Empresa(
        nit=payload.nit,
        nombre=payload.nombre,
        tipo_persona=payload.tipo_persona,
        sistema_contable=payload.sistema_contable,
        responsable_iva=payload.responsable_iva,
        regimen_simple=payload.regimen_simple,
        periodicidad_iva=payload.periodicidad_iva,
        agente_retencion=payload.agente_retencion,
        obligado_renta=payload.obligado_renta,
        obligado_exogena=payload.obligado_exogena,
        obligado_ica=payload.obligado_ica,
        municipio_ica=payload.municipio_ica,
    )
    db.add(empresa)
    db.flush()
    if admin_user is not None:
        db.add(UsuarioEmpresa(usuario_id=admin_user.id, empresa_id=empresa.id, rol="contador", permisos_json="{}"))
    auditoria_registrar(db, empresa.id, "Empresa", empresa.id, "creacion_empresa",
                         {"nit": empresa.nit, "nombre": empresa.nombre, "tipo_persona": empresa.tipo_persona}, usuario)
    db.commit()
    db.refresh(empresa)
    return empresa


@router.get("", response_model=list[EmpresaOut])
def listar_empresas(db: Session = Depends(get_db), user: Usuario | None = Depends(get_current_user)):
    q = db.query(Empresa)
    if user is not None and not user.es_superadmin:
        ids = db.query(UsuarioEmpresa.empresa_id).filter(
            UsuarioEmpresa.usuario_id == user.id, UsuarioEmpresa.activo.is_(True)
        )
        q = q.filter(Empresa.id.in_(ids))
    return q.order_by(Empresa.nombre).all()


@router.get("/{empresa_id}", response_model=EmpresaOut)
def obtener_empresa(empresa_id: str, empresa: Empresa = Depends(get_empresa_activa)):
    return empresa


@router.patch("/{empresa_id}/perfil-tributario", response_model=EmpresaOut)
def actualizar_perfil_tributario(empresa_id: str, payload: EmpresaPerfilTributarioUpdate,
                                  db: Session = Depends(get_db),
                                  empresa: Empresa = Depends(get_empresa_activa),
                                  usuario: str = Depends(usuario_actual)):
    if payload.tipo_persona not in ("natural", "juridica"):
        raise HTTPException(status_code=422, detail="tipo_persona debe ser 'natural' o 'juridica'.")
    if payload.periodicidad_iva not in ("no_aplica", "bimestral", "cuatrimestral"):
        raise HTTPException(status_code=422, detail="periodicidad_iva inválida.")
    empresa.tipo_persona = payload.tipo_persona
    empresa.responsable_iva = payload.responsable_iva
    empresa.regimen_simple = payload.regimen_simple
    empresa.periodicidad_iva = "no_aplica" if not payload.responsable_iva else payload.periodicidad_iva
    empresa.agente_retencion = payload.agente_retencion
    empresa.obligado_renta = payload.obligado_renta
    empresa.obligado_exogena = payload.obligado_exogena
    empresa.obligado_ica = payload.obligado_ica
    empresa.municipio_ica = (payload.municipio_ica or "").strip() or None
    auditoria_registrar(db, empresa_id, "Empresa", empresa.id, "perfil_tributario_actualizado", {
        "tipo_persona": empresa.tipo_persona, "responsable_iva": empresa.responsable_iva,
        "regimen_simple": empresa.regimen_simple, "periodicidad_iva": empresa.periodicidad_iva,
        "agente_retencion": empresa.agente_retencion, "obligado_renta": empresa.obligado_renta,
        "obligado_exogena": empresa.obligado_exogena, "obligado_ica": empresa.obligado_ica,
        "municipio_ica": empresa.municipio_ica,
    }, usuario)
    db.commit()
    db.refresh(empresa)
    return empresa


def _nit_digitos(nit: str) -> str:
    return "".join(ch for ch in (nit or "") if ch.isdigit())


def _fecha_ultimo_digito(anio: int, mes: int, tabla: dict[str, int], nit: str):
    from datetime import date
    digitos = _nit_digitos(nit)
    if not digitos:
        return None
    d = digitos[-1]
    dia = tabla.get(d)
    return date(anio, mes, dia) if dia else None


def _fecha_renta_persona_natural_2026(nit: str):
    from datetime import date
    digitos = _nit_digitos(nit)
    if len(digitos) < 2:
        return None
    ultimos = int(digitos[-2:])
    # 00 se trata como el último rango (99-00).
    if ultimos == 0:
        return date(2026, 10, 26)
    fechas = [
        ((1,2),(8,12)),((3,4),(8,13)),((5,6),(8,14)),((7,8),(8,18)),((9,10),(8,19)),
        ((11,12),(8,20)),((13,14),(8,21)),((15,16),(8,24)),((17,18),(8,25)),((19,20),(8,26)),
        ((21,22),(8,27)),((23,24),(8,28)),((25,26),(8,31)),((27,28),(9,1)),((29,30),(9,2)),
        ((31,32),(9,3)),((33,34),(9,4)),((35,36),(9,7)),((37,38),(9,8)),((39,40),(9,9)),
        ((41,42),(9,10)),((43,44),(9,11)),((45,46),(9,14)),((47,48),(9,15)),((49,50),(9,16)),
        ((51,52),(9,17)),((53,54),(9,18)),((55,56),(9,21)),((57,58),(9,22)),((59,60),(9,23)),
        ((61,62),(9,24)),((63,64),(9,25)),((65,66),(9,28)),((67,68),(10,1)),((69,70),(10,2)),
        ((71,72),(10,5)),((73,74),(10,6)),((75,76),(10,7)),((77,78),(10,8)),((79,80),(10,9)),
        ((81,82),(10,13)),((83,84),(10,14)),((85,86),(10,15)),((87,88),(10,16)),((89,90),(10,19)),
        ((91,92),(10,20)),((93,94),(10,21)),((95,96),(10,22)),((97,98),(10,23)),((99,99),(10,26)),
    ]
    for (a,b),(m,d) in fechas:
        if a <= ultimos <= b:
            return date(2026,m,d)
    return None


def _calendario_dian_2026(empresa: Empresa):
    """Genera vencimientos nacionales de uso cotidiano para la etapa restante de 2026.

    Se concentra en IVA, retención, SIMPLE y renta PN, que son las obligaciones
    configurables en el perfil. Territorial (ICA/ReteICA) permanece manual porque
    depende de cada municipio/distrito.
    """
    from datetime import date
    fuente = "DIAN · Calendario Tributario 2026 (Decreto 2229 de 2023 y ajustes publicados por DIAN)"
    sep = {'1':9,'2':10,'3':11,'4':14,'5':15,'6':16,'7':17,'8':18,'9':21,'0':22}
    octu = {'1':9,'2':13,'3':14,'4':15,'5':16,'6':19,'7':20,'8':21,'9':22,'0':23}
    nov = {'1':11,'2':12,'3':13,'4':17,'5':18,'6':19,'7':20,'8':23,'9':24,'0':25}
    dic = {'1':10,'2':11,'3':14,'4':15,'5':16,'6':17,'7':18,'8':21,'9':22,'0':23}
    ene27 = {'1':13,'2':14,'3':15,'4':18,'5':19,'6':20,'7':21,'8':22,'9':25,'0':26}
    items = []
    def add(codigo, obligacion, periodo, fecha):
        if fecha:
            items.append({"id": f"auto:{codigo}:{periodo}", "codigo": codigo, "obligacion": obligacion,
                          "periodo": periodo, "fecha_vencimiento": fecha, "jurisdiccion": "Nacional",
                          "fuente": fuente, "origen": "automatico"})

    if empresa.responsable_iva and empresa.periodicidad_iva != "no_aplica":
        if empresa.periodicidad_iva == "cuatrimestral":
            add("iva_cuatrimestral", "IVA cuatrimestral", "Mayo - agosto 2026", _fecha_ultimo_digito(2026,9,sep,empresa.nit))
            add("iva_cuatrimestral", "IVA cuatrimestral", "Septiembre - diciembre 2026", _fecha_ultimo_digito(2027,1,ene27,empresa.nit))
        else:
            add("iva_bimestral", "IVA bimestral", "Julio - agosto 2026", _fecha_ultimo_digito(2026,9,sep,empresa.nit))
            add("iva_bimestral", "IVA bimestral", "Septiembre - octubre 2026", _fecha_ultimo_digito(2026,11,nov,empresa.nit))
            add("iva_bimestral", "IVA bimestral", "Noviembre - diciembre 2026", _fecha_ultimo_digito(2027,1,ene27,empresa.nit))

    if empresa.agente_retencion:
        add("retefuente", "Retención en la fuente", "Agosto 2026", _fecha_ultimo_digito(2026,9,sep,empresa.nit))
        add("retefuente", "Retención en la fuente", "Septiembre 2026", _fecha_ultimo_digito(2026,10,octu,empresa.nit))
        add("retefuente", "Retención en la fuente", "Octubre 2026", _fecha_ultimo_digito(2026,11,nov,empresa.nit))
        add("retefuente", "Retención en la fuente", "Noviembre 2026", _fecha_ultimo_digito(2026,12,dic,empresa.nit))
        add("retefuente", "Retención en la fuente", "Diciembre 2026", _fecha_ultimo_digito(2027,1,ene27,empresa.nit))

    if empresa.regimen_simple:
        add("simple", "SIMPLE · anticipo bimestral", "Julio - agosto 2026", _fecha_ultimo_digito(2026,9,sep,empresa.nit))
        add("simple", "SIMPLE · anticipo bimestral", "Septiembre - octubre 2026", _fecha_ultimo_digito(2026,11,nov,empresa.nit))
        add("simple", "SIMPLE · anticipo bimestral", "Noviembre - diciembre 2026", _fecha_ultimo_digito(2027,1,ene27,empresa.nit))

    if empresa.tipo_persona == "natural" and empresa.obligado_renta:
        add("renta_pn", "Renta persona natural", "Año gravable 2025", _fecha_renta_persona_natural_2026(empresa.nit))

    return items


def _estado_vencimiento(fecha):
    from datetime import date
    dias = (fecha - date.today()).days
    if dias < 0:
        return "vencido", dias
    if dias == 0:
        return "vence_hoy", dias
    if dias <= 7:
        return "proximo", dias
    return "futuro", dias


@router.get("/{empresa_id}/calendario-tributario")
def calendario_tributario(empresa_id: str, db: Session = Depends(get_db),
                           empresa: Empresa = Depends(get_empresa_activa)):
    auto = _calendario_dian_2026(empresa)
    manuales = db.query(VencimientoTributario).filter(
        VencimientoTributario.empresa_id == empresa_id, VencimientoTributario.activo.is_(True)
    ).all()
    items = list(auto)
    for v in manuales:
        items.append({
            "id": v.id, "codigo": "manual", "obligacion": v.obligacion, "periodo": v.periodo,
            "fecha_vencimiento": v.fecha_vencimiento, "jurisdiccion": v.jurisdiccion,
            "fuente": v.fuente, "origen": "manual",
        })
    for item in items:
        estado, dias = _estado_vencimiento(item["fecha_vencimiento"])
        item["estado"] = estado
        item["dias"] = dias
    items.sort(key=lambda x: x["fecha_vencimiento"])
    return {
        "items": items,
        "advertencias": (
            (["ICA/ReteICA y otros tributos territoriales deben cargarse con la fecha oficial de la jurisdicción correspondiente."] if empresa.obligado_ica else [])
            + (["La información exógena está marcada como obligación, pero su fecha depende de la resolución/formato aplicable; agrégala como vencimiento manual cuando corresponda."] if empresa.obligado_exogena else [])
        ),
        "perfil": {
            "tipo_persona": empresa.tipo_persona, "responsable_iva": empresa.responsable_iva,
            "periodicidad_iva": empresa.periodicidad_iva, "agente_retencion": empresa.agente_retencion,
            "regimen_simple": empresa.regimen_simple, "obligado_renta": empresa.obligado_renta,
            "obligado_exogena": empresa.obligado_exogena, "obligado_ica": empresa.obligado_ica,
            "municipio_ica": empresa.municipio_ica,
        },
    }


@router.post("/{empresa_id}/calendario-tributario/manual", status_code=201)
def crear_vencimiento_manual(empresa_id: str, payload: VencimientoTributarioCreate,
                              db: Session = Depends(get_db), empresa: Empresa = Depends(get_empresa_activa),
                              usuario: str = Depends(usuario_actual)):
    if not payload.obligacion.strip():
        raise HTTPException(status_code=422, detail="La obligación es obligatoria.")
    v = VencimientoTributario(
        empresa_id=empresa_id, obligacion=payload.obligacion.strip(), periodo=(payload.periodo or "").strip() or None,
        fecha_vencimiento=payload.fecha_vencimiento, jurisdiccion=(payload.jurisdiccion or "").strip() or None,
        fuente=(payload.fuente or "").strip() or None,
    )
    db.add(v)
    db.flush()
    auditoria_registrar(db, empresa_id, "VencimientoTributario", v.id, "vencimiento_tributario_creado", {
        "obligacion": v.obligacion, "periodo": v.periodo, "fecha": v.fecha_vencimiento.isoformat(),
        "jurisdiccion": v.jurisdiccion,
    }, usuario)
    db.commit()
    return {"id": v.id, "creado": True}


@router.delete("/{empresa_id}/calendario-tributario/manual/{vencimiento_id}")
def eliminar_vencimiento_manual(empresa_id: str, vencimiento_id: str, db: Session = Depends(get_db),
                                 empresa: Empresa = Depends(get_empresa_activa),
                                 usuario: str = Depends(usuario_actual)):
    v = db.query(VencimientoTributario).filter(
        VencimientoTributario.empresa_id == empresa_id, VencimientoTributario.id == vencimiento_id
    ).first()
    if not v:
        raise HTTPException(status_code=404, detail="Vencimiento no encontrado.")
    resumen = {"obligacion": v.obligacion, "periodo": v.periodo, "fecha": v.fecha_vencimiento.isoformat()}
    db.delete(v)
    auditoria_registrar(db, empresa_id, "VencimientoTributario", vencimiento_id, "vencimiento_tributario_eliminado", resumen, usuario)
    db.commit()
    return {"eliminado": True}


@router.patch("/{empresa_id}/cuentas-base", response_model=EmpresaOut)
def configurar_cuentas_base(empresa_id: str, payload: EmpresaCuentasBase, db: Session = Depends(get_db),
                             empresa: Empresa = Depends(get_empresa_activa),
                             usuario: str = Depends(usuario_actual)):
    """
    Configura las cuentas de proveedores/caja/banco/IVA/retenciones de la
    empresa (sección 38). Nunca se asumen por defecto: sin esto, la
    partida doble se niega a generarse si la factura las necesita
    (sección 37, "nunca inventar cuentas").
    """
    from app.services.historial_service import get_or_create_cuenta

    campo_a_columna = {
        "cuenta_proveedores": "cuenta_proveedores_id",
        "cuenta_caja": "cuenta_caja_id",
        "cuenta_banco": "cuenta_banco_id",
        "cuenta_iva_descontable": "cuenta_iva_descontable_id",
        "cuenta_retefuente": "cuenta_retefuente_id",
        "cuenta_reteica": "cuenta_reteica_id",
        "cuenta_reteiva": "cuenta_reteiva_id",
        "cuenta_inc": "cuenta_inc_id",
        "cuenta_ingresos": "cuenta_ingresos_id",
        "cuenta_clientes": "cuenta_clientes_id",
        "cuenta_iva_generado": "cuenta_iva_generado_id",
        "cuenta_nomina": "cuenta_nomina_id",
        "cuenta_salario": "cuenta_salario_id",
        "cuenta_auxilio_transporte": "cuenta_auxilio_transporte_id",
        "cuenta_nomina_por_pagar": "cuenta_nomina_por_pagar_id",
        "cuenta_salud_por_pagar": "cuenta_salud_por_pagar_id",
        "cuenta_pension_por_pagar": "cuenta_pension_por_pagar_id",
        "cuenta_cesantias": "cuenta_cesantias_id",
        "cuenta_cesantias_por_pagar": "cuenta_cesantias_por_pagar_id",
        "cuenta_intereses_cesantias": "cuenta_intereses_cesantias_id",
        "cuenta_intereses_cesantias_por_pagar": "cuenta_intereses_cesantias_por_pagar_id",
        "cuenta_prima": "cuenta_prima_id",
        "cuenta_prima_por_pagar": "cuenta_prima_por_pagar_id",
        "cuenta_vacaciones": "cuenta_vacaciones_id",
        "cuenta_vacaciones_por_pagar": "cuenta_vacaciones_por_pagar_id",
        "cuenta_arl": "cuenta_arl_id",
        "cuenta_arl_por_pagar": "cuenta_arl_por_pagar_id",
        "cuenta_caja_compensacion": "cuenta_caja_compensacion_id",
        "cuenta_caja_compensacion_por_pagar": "cuenta_caja_compensacion_por_pagar_id",
    }
    cambios = payload.model_dump(exclude_none=True)
    for campo, codigo in cambios.items():
        cuenta = get_or_create_cuenta(db, empresa_id, codigo)
        setattr(empresa, campo_a_columna[campo], cuenta.id)

    auditoria_registrar(db, empresa_id, "Empresa", empresa.id, "configurar_cuentas_base", cambios, usuario)
    db.commit()
    db.refresh(empresa)
    return empresa


@router.patch("/{empresa_id}/modo-contable", response_model=EmpresaOut)
def configurar_modo_contable(empresa_id: str, modo: str, db: Session = Depends(get_db),
                              empresa: Empresa = Depends(get_empresa_activa),
                              usuario: str = Depends(usuario_actual)):
    """
    "mixto" (por defecto): las facturas recibidas se contabilizan como
    gasto y las emitidas como ingreso, cada una con sus propias cuentas
    — el caso normal de una empresa que compra y también vende.
    "solo_gastos": TODO se contabiliza por el lado de gasto, sin
    importar si la DIAN marcó el documento como emitido o recibido —
    pensado para una persona natural que solo usa el sistema para
    llevar sus propios gastos y no tiene (ni necesita) cuentas de
    ingresos/clientes configuradas.
    """
    if modo not in ("mixto", "solo_gastos"):
        raise HTTPException(status_code=422, detail="modo debe ser 'mixto' o 'solo_gastos'.")
    empresa.modo_contable = modo
    auditoria_registrar(db, empresa_id, "Empresa", empresa.id, "configurar_modo_contable", {"modo": modo}, usuario)
    db.commit()
    db.refresh(empresa)
    return empresa


@router.get("/{empresa_id}/cuentas-base")
def obtener_cuentas_base(empresa_id: str, db: Session = Depends(get_db),
                          empresa: Empresa = Depends(get_empresa_activa)):
    from app.models.models import CuentaContable

    def resolver(cuenta_id):
        if not cuenta_id:
            return None
        c = db.get(CuentaContable, cuenta_id)
        return {"codigo": c.codigo, "nombre": c.nombre} if c else None

    return {
        "cuenta_proveedores": resolver(empresa.cuenta_proveedores_id),
        "cuenta_caja": resolver(empresa.cuenta_caja_id),
        "cuenta_banco": resolver(empresa.cuenta_banco_id),
        "cuenta_iva_descontable": resolver(empresa.cuenta_iva_descontable_id),
        "cuenta_retefuente": resolver(empresa.cuenta_retefuente_id),
        "cuenta_reteica": resolver(empresa.cuenta_reteica_id),
        "cuenta_reteiva": resolver(empresa.cuenta_reteiva_id),
        "cuenta_inc": resolver(empresa.cuenta_inc_id),
        "cuenta_ingresos": resolver(empresa.cuenta_ingresos_id),
        "cuenta_clientes": resolver(empresa.cuenta_clientes_id),
        "cuenta_iva_generado": resolver(empresa.cuenta_iva_generado_id),
        "cuenta_nomina": resolver(empresa.cuenta_nomina_id),
        "cuenta_salario": resolver(empresa.cuenta_salario_id),
        "cuenta_auxilio_transporte": resolver(empresa.cuenta_auxilio_transporte_id),
        "cuenta_nomina_por_pagar": resolver(empresa.cuenta_nomina_por_pagar_id),
        "cuenta_salud_por_pagar": resolver(empresa.cuenta_salud_por_pagar_id),
        "cuenta_pension_por_pagar": resolver(empresa.cuenta_pension_por_pagar_id),
        "cuenta_cesantias": resolver(empresa.cuenta_cesantias_id),
        "cuenta_cesantias_por_pagar": resolver(empresa.cuenta_cesantias_por_pagar_id),
        "cuenta_intereses_cesantias": resolver(empresa.cuenta_intereses_cesantias_id),
        "cuenta_intereses_cesantias_por_pagar": resolver(empresa.cuenta_intereses_cesantias_por_pagar_id),
        "cuenta_prima": resolver(empresa.cuenta_prima_id),
        "cuenta_prima_por_pagar": resolver(empresa.cuenta_prima_por_pagar_id),
        "cuenta_vacaciones": resolver(empresa.cuenta_vacaciones_id),
        "cuenta_vacaciones_por_pagar": resolver(empresa.cuenta_vacaciones_por_pagar_id),
        "cuenta_arl": resolver(empresa.cuenta_arl_id),
        "cuenta_arl_por_pagar": resolver(empresa.cuenta_arl_por_pagar_id),
        "cuenta_caja_compensacion": resolver(empresa.cuenta_caja_compensacion_id),
        "cuenta_caja_compensacion_por_pagar": resolver(empresa.cuenta_caja_compensacion_por_pagar_id),
    }


@router.patch("/{empresa_id}/comprobantes-por-tipo", response_model=EmpresaOut)
def configurar_comprobantes_por_tipo(empresa_id: str, payload: EmpresaComprobantesPorTipo, db: Session = Depends(get_db),
                                      empresa: Empresa = Depends(get_empresa_activa),
                                      usuario: str = Depends(usuario_actual)):
    """
    Define el tipo de comprobante (texto libre, según la parametrización
    propia de cada empresa en su software) que debe usarse al exportar
    según la clasificación real del documento — nunca uno solo para todo.
    """
    cambios = payload.model_dump(exclude_none=True)
    for campo, valor in cambios.items():
        setattr(empresa, campo, valor)
    auditoria_registrar(db, empresa_id, "Empresa", empresa.id, "configurar_comprobantes_por_tipo", cambios, usuario)
    db.commit()
    db.refresh(empresa)
    return empresa


@router.get("/{empresa_id}/comprobantes-por-tipo")
def obtener_comprobantes_por_tipo(empresa_id: str, db: Session = Depends(get_db),
                                   empresa: Empresa = Depends(get_empresa_activa)):
    return {
        "comprobante_factura_recibida": empresa.comprobante_factura_recibida,
        "comprobante_factura_emitida": empresa.comprobante_factura_emitida,
        "comprobante_nota_credito": empresa.comprobante_nota_credito,
        "comprobante_nota_debito": empresa.comprobante_nota_debito,
        "comprobante_nomina": empresa.comprobante_nomina,
        "comprobante_documento_equivalente": empresa.comprobante_documento_equivalente,
    }


@router.patch("/{empresa_id}/desactivar", response_model=EmpresaOut)
def desactivar_empresa(empresa_id: str, db: Session = Depends(get_db),
                        empresa: Empresa = Depends(get_empresa_activa), usuario: str = Depends(usuario_actual)):
    """
    Opción segura y reversible: la empresa deja de aparecer como
    utilizable (ninguna ruta que dependa de get_empresa_activa la
    aceptará) pero sus datos NO se borran — se puede reactivar en
    cualquier momento. Pensada para "esto no debí crearlo así" sin
    perder nada por si acaso.
    """
    empresa.activa = False
    auditoria_registrar(db, empresa_id, "Empresa", empresa.id, "empresa_desactivada", {}, usuario)
    db.commit()
    db.refresh(empresa)
    return empresa


@router.patch("/{empresa_id}/reactivar", response_model=EmpresaOut)
def reactivar_empresa(empresa_id: str, db: Session = Depends(get_db), usuario: str = Depends(usuario_actual),
                       user: Usuario | None = Depends(get_current_user)):
    verificar_permiso_empresa(db, user, empresa_id, "empresa_administrar")
    empresa = db.query(Empresa).filter(Empresa.id == empresa_id).first()
    if not empresa:
        raise HTTPException(status_code=404, detail="Empresa no encontrada.")
    empresa.activa = True
    auditoria_registrar(db, empresa_id, "Empresa", empresa.id, "empresa_reactivada", {}, usuario)
    db.commit()
    db.refresh(empresa)
    return empresa


@router.delete("/{empresa_id}")
def eliminar_empresa(empresa_id: str, confirmar: bool = False, db: Session = Depends(get_db),
                      usuario: str = Depends(usuario_actual), user: Usuario | None = Depends(get_current_user)):
    verificar_permiso_empresa(db, user, empresa_id, "empresa_administrar")
    """
    Elimina la empresa y TODO lo que le pertenece (cuentas, proveedores,
    facturas, movimientos, historial, reglas, centros de costo,
    plantillas, exportaciones, cargas y auditoría) — irreversible. Exige
    confirmar=true a propósito, para que nunca sea un clic accidental.
    Si solo fue un error reciente sin datos reales todavía, considera
    mejor "desactivar" (reversible) en vez de esto.
    """
    from app.models.models import (
        CuentaContable, Proveedor, CentroCosto, ReglaContable, ImportacionHistorico,
        HistorialContable, CargaDocumentosDian, Factura, Movimiento, PlantillaExportacion,
        Exportacion, Auditoria, Empleado, ConfiguracionComprobanteSiigo, ConsecutivoSiigo,
        ParametrizacionCuentaSiigo, HistorialTecnicoSiigo, ExportacionFactura, UsuarioEmpresa, ReglaCuentaControl, VencimientoTributario,
    )

    empresa = db.query(Empresa).filter(Empresa.id == empresa_id).first()
    if not empresa:
        raise HTTPException(status_code=404, detail="Empresa no encontrada.")
    if not confirmar:
        raise HTTPException(
            status_code=422,
            detail="Esta acción borra TODOS los datos de la empresa (facturas, historial, exportaciones, "
                   "auditoría) de forma irreversible. Vuelve a llamar con ?confirmar=true si estás seguro, "
                   "o usa 'desactivar' si prefieres algo reversible.",
        )

    resumen = {"nit": empresa.nit, "nombre": empresa.nombre, "tipo_persona": empresa.tipo_persona}

    # Se limpian primero las referencias de Empresa hacia CuentaContable
    # (cuenta_proveedores_id, etc.) para poder borrar las cuentas después
    # sin violar la llave foránea.
    for campo in ("cuenta_proveedores_id", "cuenta_caja_id", "cuenta_banco_id", "cuenta_iva_descontable_id",
                  "cuenta_retefuente_id", "cuenta_reteica_id", "cuenta_reteiva_id", "cuenta_inc_id",
                  "cuenta_ingresos_id", "cuenta_clientes_id", "cuenta_iva_generado_id", "cuenta_nomina_id"):
        setattr(empresa, campo, None)
    db.flush()

    db.query(UsuarioEmpresa).filter(UsuarioEmpresa.empresa_id == empresa_id).delete()
    db.query(ExportacionFactura).filter(ExportacionFactura.empresa_id == empresa_id).delete()
    db.query(ParametrizacionCuentaSiigo).filter(ParametrizacionCuentaSiigo.empresa_id == empresa_id).delete()
    db.query(HistorialTecnicoSiigo).filter(HistorialTecnicoSiigo.empresa_id == empresa_id).delete()
    db.query(ReglaCuentaControl).filter(ReglaCuentaControl.empresa_id == empresa_id).delete()
    db.query(ConsecutivoSiigo).filter(ConsecutivoSiigo.empresa_id == empresa_id).delete()
    db.query(ConfiguracionComprobanteSiigo).filter(ConfiguracionComprobanteSiigo.empresa_id == empresa_id).delete()
    db.query(VencimientoTributario).filter(VencimientoTributario.empresa_id == empresa_id).delete()
    db.query(Movimiento).filter(Movimiento.empresa_id == empresa_id).delete()
    db.query(HistorialContable).filter(HistorialContable.empresa_id == empresa_id).delete()
    db.query(Factura).filter(Factura.empresa_id == empresa_id).delete()
    db.query(CargaDocumentosDian).filter(CargaDocumentosDian.empresa_id == empresa_id).delete()
    db.query(ImportacionHistorico).filter(ImportacionHistorico.empresa_id == empresa_id).delete()
    db.query(Exportacion).filter(Exportacion.empresa_id == empresa_id).delete()
    db.query(PlantillaExportacion).filter(PlantillaExportacion.empresa_id == empresa_id).delete()
    db.query(ReglaContable).filter(ReglaContable.empresa_id == empresa_id).delete()
    db.query(Proveedor).filter(Proveedor.empresa_id == empresa_id).delete()
    db.query(Empleado).filter(Empleado.empresa_id == empresa_id).delete()
    db.query(CentroCosto).filter(CentroCosto.empresa_id == empresa_id).delete()
    db.query(CuentaContable).filter(CuentaContable.empresa_id == empresa_id).delete()
    db.query(Auditoria).filter(Auditoria.empresa_id == empresa_id).delete()

    db.delete(empresa)
    db.commit()
    return {"eliminada": True, "id": empresa_id, "resumen": resumen}


# ------------------------------------------------------------- Empleados --
@router.get("/{empresa_id}/empleados", response_model=list[EmpleadoOut])
def listar_empleados(empresa_id: str, db: Session = Depends(get_db),
                      empresa: Empresa = Depends(get_empresa_activa)):
    from app.models.models import Empleado
    return db.query(Empleado).filter(Empleado.empresa_id == empresa_id).order_by(Empleado.nombre).all()


@router.post("/{empresa_id}/empleados", response_model=EmpleadoOut, status_code=201)
def crear_empleado(empresa_id: str, payload: EmpleadoCreate, db: Session = Depends(get_db),
                    empresa: Empresa = Depends(get_empresa_activa), usuario: str = Depends(usuario_actual)):
    """
    Ficha de empleado, reutilizable en cualquier empresa que use el
    sistema (nunca datos fijos de una empresa en particular). Solo el
    NIT es obligatorio — el resto de campos (afiliaciones) se pueden
    completar después; mientras falten, las líneas de pasivo que
    dependan de ellos simplemente no se generan.
    """
    from app.models.models import Empleado
    existente = db.query(Empleado).filter(Empleado.empresa_id == empresa_id, Empleado.nit == payload.nit).first()
    if existente:
        raise HTTPException(status_code=409, detail=f"Ya existe un empleado con NIT {payload.nit} en esta empresa.")
    empleado = Empleado(empresa_id=empresa_id, **payload.model_dump())
    db.add(empleado)
    auditoria_registrar(db, empresa_id, "Empleado", empleado.id, "empleado_creado", payload.model_dump(), usuario)
    db.commit()
    db.refresh(empleado)
    return empleado


@router.patch("/{empresa_id}/empleados/{empleado_id}", response_model=EmpleadoOut)
def actualizar_empleado(empresa_id: str, empleado_id: str, payload: EmpleadoCreate, db: Session = Depends(get_db),
                         empresa: Empresa = Depends(get_empresa_activa), usuario: str = Depends(usuario_actual)):
    from app.models.models import Empleado
    empleado = db.query(Empleado).filter(Empleado.empresa_id == empresa_id, Empleado.id == empleado_id).first()
    if not empleado:
        raise HTTPException(status_code=404, detail="Empleado no encontrado en esta empresa.")
    for campo, valor in payload.model_dump().items():
        setattr(empleado, campo, valor)
    auditoria_registrar(db, empresa_id, "Empleado", empleado.id, "empleado_actualizado", payload.model_dump(), usuario)
    db.commit()
    db.refresh(empleado)
    return empleado


@router.delete("/{empresa_id}/empleados/{empleado_id}")
def eliminar_empleado(empresa_id: str, empleado_id: str, db: Session = Depends(get_db),
                       empresa: Empresa = Depends(get_empresa_activa), usuario: str = Depends(usuario_actual)):
    from app.models.models import Empleado
    empleado = db.query(Empleado).filter(Empleado.empresa_id == empresa_id, Empleado.id == empleado_id).first()
    if not empleado:
        raise HTTPException(status_code=404, detail="Empleado no encontrado en esta empresa.")
    db.delete(empleado)
    auditoria_registrar(db, empresa_id, "Empleado", empleado_id, "empleado_eliminado", {}, usuario)
    db.commit()
    return {"eliminado": True, "id": empleado_id}
