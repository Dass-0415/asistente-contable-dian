from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app.models.models import Empresa, Usuario, UsuarioEmpresa, VencimientoTributario, RutEmpresa
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



def _json_lista(valor: str | None) -> list:
    import json
    try:
        data = json.loads(valor or "[]")
        return data if isinstance(data, list) else []
    except (ValueError, TypeError):
        return []


def _rut_publico(rut: RutEmpresa | None) -> dict | None:
    if rut is None:
        return None
    return {
        "id": rut.id,
        "archivo_nombre": rut.archivo_nombre,
        "numero_formulario": rut.numero_formulario,
        "nit": rut.nit_detectado,
        "dv": rut.dv_detectado,
        "tipo_persona": rut.tipo_persona_detectado,
        "direccion_seccional": rut.direccion_seccional,
        "municipio": rut.municipio,
        "fecha_generacion": rut.fecha_generacion.isoformat() if rut.fecha_generacion else None,
        "actividades": _json_lista(rut.actividades_json),
        "responsabilidades": _json_lista(rut.responsabilidades_json),
        "fuente": rut.fuente_extraccion,
        "analizado_en": rut.analizado_en.isoformat() if rut.analizado_en else None,
        "aplicado_en": rut.aplicado_en.isoformat() if rut.aplicado_en else None,
        "aplicado": rut.aplicado_en is not None,
    }


def _nit_base_para_comparar(nit: str | None) -> str:
    dig = "".join(ch for ch in (nit or "") if ch.isdigit())
    # Si el usuario guardó NIT+DV (muy común), aceptar también la base sin DV.
    return dig


def _nit_coincide(nit_empresa: str, nit_rut: str | None, dv_rut: str | None) -> bool:
    empresa = _nit_base_para_comparar(nit_empresa)
    rut = _nit_base_para_comparar(nit_rut)
    if not empresa or not rut:
        return False
    return empresa == rut or empresa == rut + (dv_rut or "")


@router.get("/{empresa_id}/rut")
def obtener_rut_empresa(empresa_id: str, db: Session = Depends(get_db),
                        empresa: Empresa = Depends(get_empresa_activa)):
    actual = db.query(RutEmpresa).filter(
        RutEmpresa.empresa_id == empresa_id, RutEmpresa.activo.is_(True)
    ).order_by(RutEmpresa.analizado_en.desc()).first()
    historico = db.query(RutEmpresa).filter(
        RutEmpresa.empresa_id == empresa_id
    ).order_by(RutEmpresa.analizado_en.desc()).limit(8).all()
    return {
        "actual": _rut_publico(actual),
        "historial": [
            {
                "id": r.id,
                "archivo_nombre": r.archivo_nombre,
                "fecha_generacion": r.fecha_generacion.isoformat() if r.fecha_generacion else None,
                "analizado_en": r.analizado_en.isoformat() if r.analizado_en else None,
                "aplicado": r.aplicado_en is not None,
                "activo": r.activo,
            }
            for r in historico
        ],
    }


@router.post("/{empresa_id}/rut/analizar", status_code=201)
async def analizar_rut_empresa(empresa_id: str, archivo: UploadFile = File(...),
                               db: Session = Depends(get_db),
                               empresa: Empresa = Depends(get_empresa_activa),
                               usuario: str = Depends(usuario_actual)):
    """Analiza un RUT PDF y guarda solo su estructura tributaria, no el PDF."""
    import hashlib
    import json
    from datetime import date
    from app.services.rut_extraction_service import analizar_rut_pdf

    nombre = (archivo.filename or "RUT.pdf").strip()[:300]
    if not nombre.lower().endswith(".pdf"):
        raise HTTPException(status_code=422, detail="El RUT debe cargarse en formato PDF.")
    contenido = await archivo.read(10 * 1024 * 1024 + 1)
    if not contenido:
        raise HTTPException(status_code=422, detail="El archivo está vacío.")
    if not contenido.lstrip().startswith(b"%PDF-"):
        raise HTTPException(status_code=422, detail="El archivo seleccionado no contiene un PDF válido.")
    if len(contenido) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="El RUT supera el límite de 10 MB.")

    analisis = analizar_rut_pdf(contenido)
    if not analisis.get("valido"):
        raise HTTPException(status_code=422, detail="No se pudo reconocer un RUT DIAN legible en este PDF.")
    if not _nit_coincide(empresa.nit, analisis.get("nit"), analisis.get("dv")):
        detectado = (analisis.get("nit") or "") + (("-" + analisis.get("dv")) if analisis.get("dv") else "")
        raise HTTPException(
            status_code=422,
            detail=f"El NIT detectado en el RUT ({detectado or 'no identificado'}) no coincide con el cliente seleccionado ({empresa.nit}).",
        )

    sha = hashlib.sha256(contenido).hexdigest()
    anterior = db.query(RutEmpresa).filter(
        RutEmpresa.empresa_id == empresa_id, RutEmpresa.activo.is_(True)
    ).order_by(RutEmpresa.analizado_en.desc()).first()

    # Si es exactamente el mismo documento, no duplicar el historial.
    if anterior and anterior.archivo_sha256 == sha:
        pub = _rut_publico(anterior)
        pub["advertencias"] = analisis.get("advertencias", [])
        pub["sugerencias_perfil"] = analisis.get("sugerencias_perfil", {})
        return {"rut": pub, "comparacion": {"sin_cambios": True, "agregadas": [], "retiradas": []}, "reutilizado": True}

    anteriores = {x.get("codigo") for x in _json_lista(anterior.responsabilidades_json)} if anterior else set()
    nuevas = {x.get("codigo") for x in analisis.get("responsabilidades", [])}
    comparacion = {
        "sin_cambios": anteriores == nuevas if anterior else False,
        "agregadas": sorted(x for x in (nuevas - anteriores) if x),
        "retiradas": sorted(x for x in (anteriores - nuevas) if x),
    }

    if anterior:
        anterior.activo = False

    fecha_generacion = None
    if analisis.get("fecha_generacion"):
        try:
            fecha_generacion = date.fromisoformat(analisis["fecha_generacion"])
        except ValueError:
            pass

    rut = RutEmpresa(
        empresa_id=empresa_id,
        archivo_nombre=nombre,
        archivo_sha256=sha,
        numero_formulario=analisis.get("numero_formulario"),
        nit_detectado=analisis.get("nit"),
        dv_detectado=analisis.get("dv"),
        tipo_persona_detectado=analisis.get("tipo_persona"),
        direccion_seccional=analisis.get("direccion_seccional"),
        municipio=analisis.get("municipio"),
        fecha_generacion=fecha_generacion,
        actividades_json=json.dumps(analisis.get("actividades", []), ensure_ascii=False),
        responsabilidades_json=json.dumps(analisis.get("responsabilidades", []), ensure_ascii=False),
        fuente_extraccion=analisis.get("fuente") or "pdf_texto",
        activo=True,
    )
    db.add(rut)
    db.flush()
    auditoria_registrar(db, empresa_id, "RutEmpresa", rut.id, "rut_analizado", {
        "archivo": nombre,
        "numero_formulario": rut.numero_formulario,
        "responsabilidades": sorted(x for x in nuevas if x),
        "fuente": rut.fuente_extraccion,
    }, usuario)
    db.commit()
    db.refresh(rut)
    pub = _rut_publico(rut)
    pub["advertencias"] = analisis.get("advertencias", [])
    pub["sugerencias_perfil"] = analisis.get("sugerencias_perfil", {})
    return {"rut": pub, "comparacion": comparacion, "reutilizado": False}


@router.post("/{empresa_id}/rut/{rut_id}/aplicar", response_model=EmpresaOut)
def aplicar_rut_a_perfil(empresa_id: str, rut_id: str, db: Session = Depends(get_db),
                         empresa: Empresa = Depends(get_empresa_activa),
                         usuario: str = Depends(usuario_actual)):
    """Aplica únicamente lo que el RUT permite afirmar de forma directa."""
    from datetime import datetime, timezone
    rut = db.query(RutEmpresa).filter(
        RutEmpresa.empresa_id == empresa_id, RutEmpresa.id == rut_id, RutEmpresa.activo.is_(True)
    ).first()
    if not rut:
        raise HTTPException(status_code=404, detail="RUT analizado no encontrado o ya reemplazado.")

    codigos = {x.get("codigo") for x in _json_lista(rut.responsabilidades_json)}
    if rut.tipo_persona_detectado in {"natural", "juridica"}:
        empresa.tipo_persona = rut.tipo_persona_detectado
    empresa.responsable_iva = "48" in codigos
    empresa.regimen_simple = "47" in codigos
    empresa.agente_retencion = bool({"07", "09", "15"} & codigos)
    empresa.obligado_renta = "05" in codigos
    empresa.obligado_exogena = "14" in codigos
    if not empresa.responsable_iva:
        empresa.periodicidad_iva = "no_aplica"
    elif empresa.periodicidad_iva not in {"bimestral", "cuatrimestral"}:
        # No inferir periodicidad desde el RUT. Se deja explícitamente pendiente.
        empresa.periodicidad_iva = "no_aplica"
    # ICA/ReteICA no se toca: el RUT nacional no basta para activarlo.
    rut.aplicado_en = datetime.now(timezone.utc)
    auditoria_registrar(db, empresa_id, "RutEmpresa", rut.id, "rut_aplicado_perfil", {
        "responsabilidades": sorted(x for x in codigos if x),
        "periodicidad_iva_conservada": empresa.periodicidad_iva,
        "ica_no_modificado": True,
    }, usuario)
    db.commit()
    db.refresh(empresa)
    return empresa


@router.get("/{empresa_id}/inicio")
def inicio_empresa(empresa_id: str, db: Session = Depends(get_db),
                   empresa: Empresa = Depends(get_empresa_activa)):
    """Resumen liviano del inicio: solo agregados SQL y próximos vencimientos."""
    from datetime import date
    from app.models.models import Factura, Exportacion, ImportacionHistorico, EstadoFactura

    filas = db.query(Factura.estado, func.count(Factura.id)).filter(
        Factura.empresa_id == empresa_id
    ).group_by(Factura.estado).all()
    conteos = {(estado.value if hasattr(estado, "value") else str(estado)): int(cantidad) for estado, cantidad in filas}
    total = sum(conteos.values())
    contabilizados = conteos.get("contabilizada", 0) + conteos.get("exportada", 0)
    revision = sum(conteos.get(x, 0) for x in ("pendiente_revision", "pendiente_clasificacion", "error", "duplicada"))
    pendientes = total - contabilizados - conteos.get("duplicada", 0)

    historial = db.query(func.coalesce(func.sum(ImportacionHistorico.registros_validos), 0)).filter(
        ImportacionHistorico.empresa_id == empresa_id
    ).scalar() or 0
    exportaciones = db.query(func.count(Exportacion.id)).filter(Exportacion.empresa_id == empresa_id).scalar() or 0
    ultima_imp = db.query(ImportacionHistorico.importado_en).filter(
        ImportacionHistorico.empresa_id == empresa_id
    ).order_by(ImportacionHistorico.importado_en.desc()).first()
    ultima_exp = db.query(Exportacion.creado_en).filter(
        Exportacion.empresa_id == empresa_id
    ).order_by(Exportacion.creado_en.desc()).first()

    items = list(_calendario_dian_2026(empresa))
    manuales = db.query(VencimientoTributario).filter(
        VencimientoTributario.empresa_id == empresa_id,
        VencimientoTributario.activo.is_(True),
        VencimientoTributario.fecha_vencimiento >= date.today(),
    ).order_by(VencimientoTributario.fecha_vencimiento).limit(8).all()
    for v in manuales:
        items.append({
            "id": v.id, "codigo": "manual", "obligacion": v.obligacion, "periodo": v.periodo,
            "fecha_vencimiento": v.fecha_vencimiento, "jurisdiccion": v.jurisdiccion,
            "fuente": v.fuente, "origen": "manual",
        })
    proximos = []
    for item in items:
        if item["fecha_vencimiento"] < date.today():
            continue
        estado, dias = _estado_vencimiento(item["fecha_vencimiento"])
        item = dict(item)
        item["estado"], item["dias"] = estado, dias
        proximos.append(item)
    proximos.sort(key=lambda x: x["fecha_vencimiento"])
    proximos = proximos[:5]

    rut = db.query(RutEmpresa).filter(
        RutEmpresa.empresa_id == empresa_id, RutEmpresa.activo.is_(True)
    ).order_by(RutEmpresa.analizado_en.desc()).first()
    alertas = []
    if rut is None:
        alertas.append({"tipo": "info", "texto": "RUT no cargado. Es opcional; puedes analizarlo desde Perfil tributario para detectar responsabilidades."})
    elif rut.aplicado_en is None:
        alertas.append({"tipo": "warning", "texto": "Hay un RUT analizado pendiente de confirmar y aplicar al perfil tributario."})
    if empresa.responsable_iva and empresa.periodicidad_iva not in {"bimestral", "cuatrimestral"}:
        alertas.append({"tipo": "warning", "texto": "Responsable de IVA: confirma la periodicidad bimestral o cuatrimestral."})
    if empresa.obligado_ica and not (empresa.municipio_ica or "").strip():
        alertas.append({"tipo": "warning", "texto": "ICA está activo, pero falta indicar el municipio o distrito."})
    if empresa.obligado_exogena:
        alertas.append({"tipo": "info", "texto": "La fecha de información exógena depende de la resolución y formatos aplicables; valida el vencimiento del año."})

    return {
        "estadisticas": {
            "documentos": total,
            "pendientes": max(0, pendientes),
            "contabilizados": contabilizados,
            "revision": revision,
            "historial": int(historial),
            "exportaciones": int(exportaciones),
        },
        "ultima_importacion": ultima_imp[0].isoformat() if ultima_imp and ultima_imp[0] else None,
        "ultima_exportacion": ultima_exp[0].isoformat() if ultima_exp and ultima_exp[0] else None,
        "proximos_vencimientos": proximos,
        "alertas": alertas,
        "rut": _rut_publico(rut),
    }


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
        ParametrizacionCuentaSiigo, HistorialTecnicoSiigo, ExportacionFactura, UsuarioEmpresa, ReglaCuentaControl, VencimientoTributario, RutEmpresa,
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
    db.query(RutEmpresa).filter(RutEmpresa.empresa_id == empresa_id).delete()
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
