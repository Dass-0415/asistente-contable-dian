"""
Extracción de datos desde XML-UBL de facturas electrónicas DIAN.

El XML es SIEMPRE la fuente principal cuando existe (sección 5) porque
contiene información estructurada — nunca se reemplaza por lo que diga
un PDF cuando hay XML disponible.

Misma lógica que el extractor de facturas ya construido (single-file
HTML), portada a Python: búsqueda de elementos por nombre local
(ignorando el prefijo de namespace), porque el prefijo varía entre
proveedores tecnológicos aunque la estructura UBL sea la misma.
"""
from datetime import datetime
from typing import Optional
from xml.etree import ElementTree as ET


def _local(tag: str) -> str:
    return tag.split("}")[-1] if "}" in tag else tag


def _find_all(root, local_name: str):
    return [el for el in root.iter() if _local(el.tag) == local_name]


def _first_child(root, local_name: str):
    for child in list(root):
        if _local(child.tag) == local_name:
            return child
    return None


def _children(root, local_name: str):
    """Solo hijos DIRECTOS. Evita sumar totales del encabezado y de las líneas a la vez."""
    if root is None:
        return []
    return [child for child in list(root) if _local(child.tag) == local_name]


def _text(root, local_name: str) -> str:
    found = _find_all(root, local_name)
    return found[0].text.strip() if found and found[0].text else ""


def _direct_text(root, local_name: str) -> str:
    """Texto de un hijo DIRECTO del documento.

    En documentos equivalentes (p. ej. SPD) las UBLExtensions pueden traer
    muchos ``ID``/``IssueDate`` antes del encabezado UBL real. Para campos de
    cabecera nunca debemos tomar el primer nodo homónimo de todo el árbol.
    """
    node = _first_child(root, local_name)
    return node.text.strip() if node is not None and node.text else ""


def _direct_node(root, local_name: str):
    return _first_child(root, local_name)


def _amount(parent, local_name: str) -> float:
    if parent is None:
        return 0.0
    node = _first_child(parent, local_name)
    if node is None or not node.text:
        return 0.0
    try:
        return float(node.text)
    except ValueError:
        return 0.0


def _desempaquetar_raiz(root):
    """Si el XML viene envuelto en un AttachedDocument con el documento real
    embebido como CDATA, devuelve el documento interno; si no, la raíz tal cual."""
    tag_raiz = _local(root.tag)
    if tag_raiz in ("Invoice", "CreditNote", "DebitNote", "ApplicationResponse"):
        return root, tag_raiz
    for desc in _find_all(root, "Description"):
        if not desc.text:
            continue
        for candidato in ("Invoice", "CreditNote", "DebitNote"):
            if f"<{candidato}" in desc.text or f":{candidato}" in desc.text:
                try:
                    interno = ET.fromstring(desc.text)
                    return interno, _local(interno.tag)
                except ET.ParseError:
                    continue
    return root, tag_raiz


def clasificar_documento_xml(contenido: bytes) -> dict:
    """
    Identifica QUÉ TIPO de documento electrónico es antes de intentar
    extraer datos de factura de él. Esto evita dos errores graves:
    1) Tratar un "Application Response" (acuse de recibo del proceso
       RADIAN — no es una factura, no tiene información contable) como
       si fuera una factura real.
    2) Tratar una Nómina Electrónica Individual (esquema XML totalmente
       distinto al de factura, con datos de empleado/conceptos de
       nómina) con el parser de facturas, lo que produciría datos
       basura o incorrectos.
    Devuelve {"naturaleza": ..., "raiz": nodo_xml_a_usar} donde
    naturaleza es una de: "factura", "nota_credito", "nota_debito",
    "acuse_recibo", "nomina", "desconocido".
    """
    try:
        root = ET.fromstring(contenido)
    except ET.ParseError as e:
        return {"naturaleza": "invalido", "error": f"XML mal formado: {e}", "raiz": None}

    tag_original = _local(root.tag)
    if "nomina" in tag_original.lower() or "payroll" in tag_original.lower():
        return {"naturaleza": "nomina", "error": None, "raiz": root}

    raiz, tag = _desempaquetar_raiz(root)
    mapa = {
        "Invoice": "factura",
        "CreditNote": "nota_credito",
        "DebitNote": "nota_debito",
        "ApplicationResponse": "acuse_recibo",
    }
    naturaleza = mapa.get(tag, "desconocido")
    # DIAN conserva la raíz UBL ``Invoice`` para varios Documentos Equivalentes.
    # Se distinguen por ProfileID/InvoiceTypeCode/CUDE, no por la etiqueta raíz.
    if tag == "Invoice":
        profile = _direct_text(raiz, "ProfileID")
        type_code = _direct_text(raiz, "InvoiceTypeCode")
        uuid_node = _direct_node(raiz, "UUID")
        scheme = str(uuid_node.attrib.get("schemeName", "")) if uuid_node is not None else ""
        if "documento equivalente" in profile.lower() or type_code == "60" or "CUDE" in scheme.upper():
            naturaleza = "documento_equivalente"
    return {"naturaleza": naturaleza, "error": None, "raiz": raiz}


def _extraer_nit_party(party) -> str:
    """
    El NIT de un Party en UBL colombiano casi siempre está en
    PartyIdentification/ID, pero algunos proveedores tecnológicos lo
    ponen (o lo repiten) en PartyTaxScheme/CompanyID en su lugar — se
    prueban ambas ubicaciones antes de darlo por vacío, para no perder
    el dato si el XML usa la variante menos común.
    """
    party_ids = _find_all(party, "PartyIdentification")
    if party_ids:
        id_node = _first_child(party_ids[0], "ID")
        if id_node is not None and id_node.text and id_node.text.strip():
            return id_node.text.strip()
    tax_schemes = _find_all(party, "PartyTaxScheme")
    if tax_schemes:
        company_id = _first_child(tax_schemes[0], "CompanyID")
        if company_id is not None and company_id.text and company_id.text.strip():
            return company_id.text.strip()
    return ""


def extraer_factura_xml(contenido: bytes) -> dict:
    """
    Devuelve un dict con:
      ok: bool
      error: str | None
      campos: dict de datos extraídos
      campos_presentes: list[str] — para el cálculo de confianza
    El XML válido siempre reporta 100% de confianza estructural
    (sección 7) porque, si el parseo tuvo éxito, los campos que trae
    son exactos — no hay "adivinanza" involucrada.
    """
    try:
        root = ET.fromstring(contenido)
    except ET.ParseError as e:
        return {"ok": False, "error": f"XML mal formado: {e}", "campos": {}, "campos_presentes": []}

    invoice_root, _tag = _desempaquetar_raiz(root)
    naturaleza_raiz = {"Invoice": "factura", "CreditNote": "nota_credito", "DebitNote": "nota_debito"}.get(_tag, "factura")

    # CABECERA: siempre hijos directos. Un SPD puede traer dentro de
    # UBLExtensions ID=1, ID=2..., fechas de inicio del servicio, etc. antes
    # del ID/IssueDate reales del documento.
    numero = _direct_text(invoice_root, "ID")
    uuid_node = _direct_node(invoice_root, "UUID")
    cufe = uuid_node.text.strip() if uuid_node is not None and uuid_node.text else ""
    uuid_scheme = str(uuid_node.attrib.get("schemeName", "")) if uuid_node is not None else ""
    fecha = _direct_text(invoice_root, "IssueDate")
    hora = _direct_text(invoice_root, "IssueTime")
    profile_id = _direct_text(invoice_root, "ProfileID")
    customization_id = _direct_text(invoice_root, "CustomizationID")
    invoice_type_code = _direct_text(invoice_root, "InvoiceTypeCode")
    due_date = _direct_text(invoice_root, "DueDate")
    tax_point_date = _direct_text(invoice_root, "TaxPointDate")
    numero_pago = _direct_text(invoice_root, "AccountingCostCode")
    moneda = _direct_text(invoice_root, "DocumentCurrencyCode")

    es_documento_equivalente = (
        _tag == "Invoice" and (
            "documento equivalente" in profile_id.lower()
            or invoice_type_code == "60"
            or "CUDE" in uuid_scheme.upper()
        )
    )
    if es_documento_equivalente:
        naturaleza_raiz = "documento_equivalente"
    subtipo_documento = "SPD" if "SPD" in profile_id.upper() else ""
    if "CUDE" in uuid_scheme.upper() or es_documento_equivalente:
        tipo_identificador_fiscal = "CUDE"
    elif "CUNE" in uuid_scheme.upper():
        tipo_identificador_fiscal = "CUNE"
    else:
        tipo_identificador_fiscal = "CUFE"

    supplier = None
    suppliers = _find_all(invoice_root, "AccountingSupplierParty")
    # Algunos XML DIAN repiten AccountingSupplierParty dentro de extensiones
    # técnicas antes del Party contable real. Elegimos el primer bloque que
    # realmente tenga identificación tributaria; si ninguno la trae, usamos
    # el primero como respaldo.
    for sp in suppliers:
        if _extraer_nit_party(sp):
            supplier = sp
            break
    if supplier is None and suppliers:
        supplier = suppliers[0]
    nit_emisor, nombre_emisor, direccion_emisor = "", "", ""
    if supplier is not None:
        nit_emisor = _extraer_nit_party(supplier)
        reg_names = _find_all(supplier, "RegistrationName")
        if reg_names and reg_names[0].text:
            nombre_emisor = reg_names[0].text.strip()
        if not nombre_emisor:
            names = _find_all(supplier, "Name")
            if names and names[0].text:
                nombre_emisor = names[0].text.strip()
        # Variantes UBL reales: factura común suele usar PostalAddress;
        # Documento Equivalente SPD usa PhysicalLocation/Address y también
        # RegistrationAddress dentro de PartyTaxScheme.
        direcciones = (_find_all(supplier, "PostalAddress")
                       + _find_all(supplier, "Address")
                       + _find_all(supplier, "RegistrationAddress"))
        for addr in direcciones:
            partes = []
            line = _first_child(addr, "AddressLine")
            if line is not None:
                l = _first_child(line, "Line")
                if l is not None and l.text:
                    partes.append(l.text.strip())
            street = _first_child(addr, "StreetName")
            if street is not None and street.text and street.text.strip() not in partes:
                partes.append(street.text.strip())
            city = _first_child(addr, "CityName")
            if city is not None and city.text:
                partes.append(city.text.strip())
            if partes:
                direccion_emisor = ", ".join(p for p in partes if p)
                break

    receptor = None
    receptores = _find_all(invoice_root, "AccountingCustomerParty")
    for rp in receptores:
        if _extraer_nit_party(rp):
            receptor = rp
            break
    if receptor is None and receptores:
        receptor = receptores[0]
    nit_receptor, nombre_receptor = "", ""
    if receptor is not None:
        nit_receptor = _extraer_nit_party(receptor)
        reg_names = _find_all(receptor, "RegistrationName")
        if reg_names and reg_names[0].text:
            nombre_receptor = reg_names[0].text.strip()

    legal_total = None
    for lt in _find_all(invoice_root, "LegalMonetaryTotal"):
        legal_total = lt
        break
    line_extension = _amount(legal_total, "LineExtensionAmount")
    tax_exclusive = _amount(legal_total, "TaxExclusiveAmount")
    tax_inclusive = _amount(legal_total, "TaxInclusiveAmount")
    allowance_total = _amount(legal_total, "AllowanceTotalAmount")
    charge_total = _amount(legal_total, "ChargeTotalAmount")
    prepaid = _amount(legal_total, "PrepaidAmount")
    rounding = _amount(legal_total, "PayableRoundingAmount")
    payable = _amount(legal_total, "PayableAmount")

    # Cargos y descuentos GLOBALES declarados explícitamente en UBL.
    # Se leen solo los AllowanceCharge DIRECTOS del documento: los de las
    # líneas ya afectan LineExtensionAmount y sumarlos otra vez duplicaría
    # el valor. Además del total conservamos motivo/base/porcentaje para que
    # la interfaz pueda explicar QUÉ produjo la diferencia (p. ej. SERVICIO
    # o PROPINA) en vez de descubrirla únicamente por resta matemática.
    descuento_directo = recargo_directo = 0.0
    ajustes_globales = []
    for ac in _children(invoice_root, "AllowanceCharge"):
        indicador = (_text(ac, "ChargeIndicator") or "").strip().lower()
        monto = _amount(ac, "Amount")
        razon = (_text(ac, "AllowanceChargeReason") or "").strip()
        base = _amount(ac, "BaseAmount")
        porcentaje = _amount(ac, "MultiplierFactorNumeric")
        if indicador in ("true", "1"):
            recargo_directo += monto
            tipo_ajuste = "cargo"
        elif indicador in ("false", "0"):
            descuento_directo += monto
            tipo_ajuste = "descuento"
        else:
            # Si el XML no informa ChargeIndicator no adivinamos su signo.
            # Se conserva para revisión, pero no se suma a ningún total.
            tipo_ajuste = "indeterminado"
        ajustes_globales.append({
            "tipo": tipo_ajuste,
            "descripcion": razon or ("CARGO" if tipo_ajuste == "cargo" else "DESCUENTO" if tipo_ajuste == "descuento" else "AJUSTE"),
            "valor": monto,
            "base": base,
            "porcentaje": porcentaje,
        })
    if not allowance_total:
        allowance_total = descuento_directo
    if not charge_total:
        charge_total = recargo_directo

    iva_total = rf_total = ri_total = rv_total = inc_total = 0.0
    iva_base_total = 0.0

    def _tax_scheme(st):
        schemes = _find_all(st, "TaxScheme")
        if not schemes:
            return "", ""
        id_node = _first_child(schemes[0], "ID")
        name_node = _first_child(schemes[0], "Name")
        tax_id = id_node.text.strip() if id_node is not None and id_node.text else ""
        tax_name = name_node.text.strip().upper() if name_node is not None and name_node.text else ""
        return tax_id, tax_name

    def _clasificar_impuesto(tax_id: str, tax_name: str, retencion: bool = False) -> str:
        nombre = (tax_name or "").upper()
        codigo = str(tax_id or "").strip()
        if retencion:
            if codigo == "05" or "RETEIVA" in nombre or ("RET" in nombre and "IVA" in nombre):
                return "reteiva"
            if codigo == "07" or "RETEICA" in nombre or ("RET" in nombre and "ICA" in nombre):
                return "reteica"
            if codigo == "06" or "RETEFUENTE" in nombre or "RENTA" in nombre or "FUENTE" in nombre:
                return "retefuente"
        if codigo == "04" or "INC" in nombre or "CONSUMO" in nombre:
            return "inc"
        if codigo == "03" or ("ICA" in nombre and "RETE" not in nombre):
            return "ica"
        if codigo == "01" or "IVA" in nombre or "VAT" in nombre:
            return "iva"
        return "iva" if not retencion else "retefuente"

    # UBL repite a menudo TaxTotal dentro de cada línea. Antes se recorría
    # todo el árbol y se sumaba encabezado + líneas, duplicando el IVA.
    # Usamos únicamente los TaxTotal DIRECTOS del documento; si un proveedor
    # excepcional no trae total de encabezado, recién entonces consolidamos
    # los totales directos de las líneas.
    tax_totals = _children(invoice_root, "TaxTotal")
    if not tax_totals:
        lineas_para_impuestos = (_children(invoice_root, "InvoiceLine")
                                 + _children(invoice_root, "CreditNoteLine")
                                 + _children(invoice_root, "DebitNoteLine"))
        tax_totals = [tt for linea in lineas_para_impuestos for tt in _children(linea, "TaxTotal")]

    for tt in tax_totals:
        subtotals = _children(tt, "TaxSubtotal")
        if not subtotals:
            iva_total += _amount(tt, "TaxAmount")
            continue
        for st in subtotals:
            tax_id, tax_name = _tax_scheme(st)
            amt = _amount(st, "TaxAmount")
            clase = _clasificar_impuesto(tax_id, tax_name, retencion=False)
            if clase == "inc":
                inc_total += amt
            elif clase == "ica":
                ri_total += amt
            else:
                iva_total += amt
                iva_base_total += _amount(st, "TaxableAmount")

    withholding_totals = _children(invoice_root, "WithholdingTaxTotal")
    if not withholding_totals:
        lineas_para_ret = (_children(invoice_root, "InvoiceLine")
                           + _children(invoice_root, "CreditNoteLine")
                           + _children(invoice_root, "DebitNoteLine"))
        withholding_totals = [wt for linea in lineas_para_ret for wt in _children(linea, "WithholdingTaxTotal")]

    for wt in withholding_totals:
        subtotals = _children(wt, "TaxSubtotal")
        # Algunos XML solo traen TaxAmount sin subtotales: no se puede
        # adivinar el tipo de retención, por lo que se conserva como retefuente
        # (comportamiento histórico) sin sumarlo más de una vez.
        if not subtotals:
            rf_total += _amount(wt, "TaxAmount")
            continue
        for st in subtotals:
            tax_id, tax_name = _tax_scheme(st)
            amt = _amount(st, "TaxAmount")
            clase = _clasificar_impuesto(tax_id, tax_name, retencion=True)
            if clase == "reteica":
                ri_total += amt
            elif clase == "reteiva":
                rv_total += amt
            else:
                rf_total += amt

    conceptos = []
    lineas_xml = (_find_all(invoice_root, "InvoiceLine")
                  + _find_all(invoice_root, "CreditNoteLine")
                  + _find_all(invoice_root, "DebitNoteLine"))
    for line in lineas_xml:
        item = None
        for it in _find_all(line, "Item"):
            item = it
            break
        descripcion, codigo = "", ""
        if item is not None:
            d = _first_child(item, "Description")
            if d is not None and d.text:
                descripcion = d.text.strip()
            for sid in _find_all(item, "StandardItemIdentification"):
                idn = _first_child(sid, "ID")
                if idn is not None and idn.text:
                    codigo = idn.text.strip()
                break
        price_amt = 0.0
        for price in _find_all(line, "Price"):
            price_amt = _amount(price, "PriceAmount")
            break
        qty_node = _first_child(line, "InvoicedQuantity")
        conceptos.append({
            "codigo": codigo,
            "descripcion": descripcion or "(sin descripción)",
            "cantidad": float(qty_node.text) if qty_node is not None and qty_node.text else 0.0,
            "valor_unitario": price_amt,
            "subtotal": _amount(line, "LineExtensionAmount"),
        })

    # Referencia de una nota crédito/débito a la factura original.
    # En UBL suele venir en BillingReference/InvoiceDocumentReference.
    referencia_numero = ""
    referencia_cufe = ""
    for br in _find_all(invoice_root, "BillingReference"):
        ref = _first_child(br, "InvoiceDocumentReference")
        if ref is None:
            refs = _find_all(br, "InvoiceDocumentReference")
            ref = refs[0] if refs else None
        if ref is None:
            continue
        idn = _first_child(ref, "ID")
        uuid = _first_child(ref, "UUID")
        if idn is not None and idn.text:
            referencia_numero = idn.text.strip()
        if uuid is not None and uuid.text:
            referencia_cufe = uuid.text.strip()
        if referencia_numero or referencia_cufe:
            break

    forma_pago = ""
    medio_pago = ""
    fecha_vencimiento_pago = due_date
    for pm in _children(invoice_root, "PaymentMeans"):
        payment_id = _first_child(pm, "ID")
        code = _first_child(pm, "PaymentMeansCode")
        due = _first_child(pm, "PaymentDueDate")
        if payment_id is not None and payment_id.text:
            forma_pago = payment_id.text.strip()
        if code is not None and code.text:
            medio_pago = code.text.strip()
        if due is not None and due.text:
            fecha_vencimiento_pago = due.text.strip()
        break

    contrato = ""
    if receptor is not None:
        contrato = _direct_text(receptor, "CustomerAssignedAccountID")

    campos = {
        "numero_factura": numero,
        # ``cufe`` se conserva por compatibilidad de BD/API, pero representa
        # el identificador fiscal único: CUFE o CUDE según el documento.
        "cufe": cufe,
        "identificador_fiscal": cufe,
        "tipo_identificador_fiscal": tipo_identificador_fiscal,
        "perfil_dian": profile_id,
        "customization_id": customization_id,
        "codigo_documento_dian": invoice_type_code,
        "subtipo_documento": subtipo_documento,
        "fecha_emision": fecha,
        "hora_emision": hora,
        "fecha_vencimiento": fecha_vencimiento_pago,
        "fecha_periodo_servicio": tax_point_date,
        "numero_pago": numero_pago,
        "numero_contrato": contrato,
        "nit_emisor": nit_emisor,
        "nombre_emisor": nombre_emisor,
        "direccion_emisor": direccion_emisor,
        "nit_receptor": nit_receptor,
        "nombre_receptor": nombre_receptor,
        "subtotal": line_extension,
        "base_gravable": iva_base_total or tax_exclusive,
        "iva": iva_total,
        "inc": inc_total,
        "retenciones": {"retefuente": rf_total, "reteica": ri_total, "reteiva": rv_total},
        # El valor final a contabilizar es PayableAmount cuando existe.
        # Esto incorpora redondeos/ajustes que TaxInclusiveAmount puede no traer.
        "total": payable or tax_inclusive,
        "valor_a_pagar": payable or tax_inclusive,
        "total_antes_pago": tax_inclusive,
        "descuento_total": allowance_total,
        "recargo_total": charge_total,
        "ajustes_globales": ajustes_globales,
        "redondeo_total": rounding,
        "prepago_total": prepaid,
        "forma_pago": forma_pago,
        "medio_pago": medio_pago,
        "moneda": moneda or "COP",
        "conceptos": conceptos,
        "naturaleza_documento": naturaleza_raiz,
        "documento_referencia_numero": referencia_numero,
        "documento_referencia_cufe": referencia_cufe,
    }
    campos_presentes = [k for k, v in campos.items() if v not in ("", 0, 0.0, [], {}, None)]

    if not numero and not cufe and not conceptos:
        return {"ok": False, "error": "No se reconoció estructura UBL de factura/nota crédito/nota débito en el archivo.",
                "campos": {}, "campos_presentes": []}

    return {"ok": True, "error": None, "campos": campos, "campos_presentes": campos_presentes}
