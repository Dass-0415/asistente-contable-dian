"""
PDF como fuente SECUNDARIA (sección 6): solo se usa como fuente principal
cuando no existe XML, y como fuente de contraste cuando sí existe XML.
Primero se intenta extraer texto directamente; si no hay texto útil, OCR.
Todo resultado de PDF (con o sin OCR) queda con confianza < 100% y candidato
a revisión cuando es la única fuente.

V10.8.2: soporta CUFE y CUDE, incluido Documento Equivalente Electrónico SPD.
Los patrones específicos de Documento Equivalente se prueban antes de los
genéricos para no confundir teléfono/proveedor tecnológico con número/NIT.
"""
import io
import re
import unicodedata

import pdfplumber
import pytesseract
from pdf2image import convert_from_bytes, pdfinfo_from_bytes


# Patrones genéricos usados como respaldo. Los campos sensibles de Documento
# Equivalente (número, NIT emisor, fecha, CUDE) se resuelven primero en
# ``_buscar_campos`` con rótulos explícitos del formato DIAN.
_PATRONES = {
    "cufe": re.compile(r"(?:CUFE|CUDE|CUFE\s*/\s*CUDE)\s*[:\.\-]?\s*([a-fA-F0-9]{60,110})", re.IGNORECASE),
    "numero_factura": re.compile(r"(?:(?:factura|invoice)\s*(?:electr[oó]nica)?\s*)?(?:n[uú]mero|no\.?|#)\s*[:\.\s]+([A-Z]{0,6}\s?-?\s?\d{2,20})", re.IGNORECASE),
    "nit_emisor": re.compile(r"NIT\s*(?:del\s+emisor)?\s*[:\.\s]*([\d\.]{6,15}-?\d?)", re.IGNORECASE),
    "total": re.compile(r"(?:total\s+documento|total\s+neto\s+documento|valor\s+total|total\s+a\s+pagar|total\s+factura)\s*(?:\(\s*=\s*\)|=)?[^0-9]{0,90}?([0-9][\d\.,]{0,17})", re.IGNORECASE),
    "fecha_emision": re.compile(r"(?:fecha\s+de\s+)?(?:generaci[oó]n|emisi[oó]n|expedici[oó]n)\s*[:\.\s]*(\d{4}-\d{2}-\d{2}|\d{2}[-/]\d{2}[-/]\d{4})", re.IGNORECASE),
    "iva": re.compile(r"(?:Total\s+IVA|IVA)\s*[:\.\s]*\$?\s*([\d\.,]{1,18})", re.IGNORECASE),
}


def _extraer_texto_directo(contenido: bytes) -> str:
    texto = ""
    try:
        with pdfplumber.open(io.BytesIO(contenido)) as pdf:
            for pagina in pdf.pages:
                t = pagina.extract_text() or ""
                texto += t + "\n"
    except Exception:
        return ""
    return texto.strip()


def _extraer_texto_ocr(contenido: bytes) -> str:
    """OCR con memoria acotada: renderiza una página a la vez.

    ``convert_from_bytes`` sin first_page/last_page materializa TODAS las
    páginas como imágenes simultáneamente. En un servidor de 512 MB eso puede
    tumbar el proceso con PDFs escaneados de varias páginas. Aquí conservamos
    la misma resolución, pero nunca retenemos más de una página en RAM.
    """
    try:
        info = pdfinfo_from_bytes(contenido)
        paginas = int(info.get("Pages") or 1)
    except Exception:
        paginas = 1

    partes: list[str] = []
    for pagina in range(1, paginas + 1):
        try:
            imagenes = convert_from_bytes(
                contenido, dpi=200, first_page=pagina, last_page=pagina, thread_count=1
            )
            if not imagenes:
                continue
            partes.append(pytesseract.image_to_string(imagenes[0], lang="spa+eng"))
            imagenes.clear()
        except Exception:
            continue
    return "\n".join(partes).strip()


def _normalizar_texto(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", texto or "") if not unicodedata.combining(c)).lower()


def _detectar_naturaleza(texto: str) -> str:
    t = _normalizar_texto(texto)
    if "nota credito" in t or "credit note" in t or re.search(r"\b91\s*[-:]?\s*nota", t):
        return "nota_credito"
    if "nota debito" in t or "debit note" in t or re.search(r"\b92\s*[-:]?\s*nota", t):
        return "nota_debito"
    if "documento equivalente" in t or "documento soporte" in t:
        return "documento_equivalente"
    return "factura"


def _primero(texto: str, patrones: list[re.Pattern]) -> str:
    for patron in patrones:
        m = patron.search(texto)
        if m:
            return m.group(1).strip()
    return ""


def _buscar_campos(texto: str) -> dict:
    campos = {}
    naturaleza = _detectar_naturaleza(texto)
    campos["naturaleza_documento"] = naturaleza

    # Identificador fiscal único. En Documentos Equivalentes la representación
    # gráfica usa CUDE; en factura electrónica usa CUFE. Ambos alimentan el
    # mismo campo lógico de deduplicación (``cufe`` por compatibilidad histórica).
    identificador = _primero(texto, [
        re.compile(r"C[oó]digo\s+[uú]nico\s+de\s+Documentos?\s+Equivalente[^:\n]*[-–—]?\s*CUDE\s*:\s*([a-fA-F0-9]{60,110})", re.IGNORECASE),
        re.compile(r"\bCUDE\s*:\s*([a-fA-F0-9]{60,110})", re.IGNORECASE),
        re.compile(r"\bCUFE\s*/\s*CUDE\s*:\s*([a-fA-F0-9]{60,110})", re.IGNORECASE),
        re.compile(r"\bCUFE\s*:\s*([a-fA-F0-9]{60,110})", re.IGNORECASE),
    ])
    if identificador:
        campos["cufe"] = identificador
        campos["identificador_fiscal"] = identificador
        if re.search(r"\bCUDE\b", texto, re.IGNORECASE) and naturaleza == "documento_equivalente":
            campos["tipo_identificador_fiscal"] = "CUDE"
        elif re.search(r"\bCUNE\b", texto, re.IGNORECASE):
            campos["tipo_identificador_fiscal"] = "CUNE"
        else:
            campos["tipo_identificador_fiscal"] = "CUFE"

    # Formato gráfico de Documento Equivalente: estos rótulos son inequívocos
    # y deben ganar sobre regex genéricos que pueden capturar teléfono o NIT del
    # proveedor tecnológico al final del PDF.
    numero = _primero(texto, [
        re.compile(r"N[uú]mero\s+de\s+documento\s*:\s*([A-Z0-9\-]+)", re.IGNORECASE),
        _PATRONES["numero_factura"],
    ])
    if numero:
        campos["numero_factura"] = numero

    nit = _primero(texto, [
        re.compile(r"NIT\s+del\s+emisor\s*:\s*([\d\.\-]+)", re.IGNORECASE),
        re.compile(r"NitFac\s*:\s*([\d\.\-]+)", re.IGNORECASE),
        _PATRONES["nit_emisor"],
    ])
    if nit:
        campos["nit_emisor"] = nit

    # Adquiriente/receptor en representaciones gráficas de Documento Equivalente.
    # Se acota la búsqueda a su bloque para no confundir el número del documento
    # electrónico del encabezado con la identificación del cliente.
    bloque_adquiriente = re.search(
        r"Datos\s+del\s+Adquiriente(?:/Consumidor)?(?P<bloque>.{0,1400}?)(?:Detalles\s+de\s+productos|Detalle|Productos|$)",
        texto, re.IGNORECASE | re.DOTALL
    )
    if bloque_adquiriente:
        b = bloque_adquiriente.group("bloque")
        m_nom = re.search(r"Raz[oó]n\s+social\s*:\s*([^\n\r]+)", b, re.IGNORECASE)
        m_id = re.search(r"N[uú]mero\s+de\s+documento\s*:\s*([\d.\-]+)", b, re.IGNORECASE)
        if m_nom:
            campos["nombre_receptor"] = m_nom.group(1).strip()
        if m_id:
            campos["nit_receptor"] = m_id.group(1).strip()

    fecha = _primero(texto, [
        re.compile(r"Fecha\s+de\s+Generaci[oó]n\s*:\s*(\d{4}-\d{2}-\d{2}|\d{2}[-/]\d{2}[-/]\d{4})", re.IGNORECASE),
        _PATRONES["fecha_emision"],
    ])
    if fecha:
        campos["fecha_emision"] = fecha

    total = _primero(texto, [
        re.compile(r"Total\s+documento\s*(?:\(\s*=\s*\))?\s*(?:COP)?\s*\$?\s*([0-9][\d\.,]{0,17})", re.IGNORECASE | re.DOTALL),
        re.compile(r"Total\s+neto\s+documento\s*(?:\(\s*=\s*\))?\s*([0-9][\d\.,]{0,17})", re.IGNORECASE),
        _PATRONES["total"],
    ])
    if total:
        campos["total"] = total

    iva = _primero(texto, [_PATRONES["iva"]])
    if iva:
        campos["iva"] = iva

    # Metadatos útiles de SPD; no son necesarios para deduplicar, pero mejoran
    # la lectura cuando el PDF es la única fuente disponible.
    extras = {
        "numero_pago": [re.compile(r"N[uú]mero\s+de\s+pago\s*:\s*([A-Z0-9\-]+)", re.IGNORECASE)],
        "fecha_vencimiento": [re.compile(r"Fecha\s+de\s+Vencimiento\s+SPD\s*:\s*(\d{4}-\d{2}-\d{2}|\d{2}[-/]\d{2}[-/]\d{4})", re.IGNORECASE)],
        "fecha_periodo_servicio": [re.compile(r"[UÚ]ltima\s+fecha\s+de\s+pago\s*:\s*(\d{4}-\d{2}-\d{2}|\d{2}[-/]\d{2}[-/]\d{4})", re.IGNORECASE)],
        "numero_contrato": [re.compile(r"N[°ºo]?\s*de\s+Contrato\s*:?\s*([A-Z0-9\-]+)", re.IGNORECASE)],
        "forma_pago_texto": [re.compile(r"Forma\s+de\s+pago\s*:\s*([^\n\r]+)", re.IGNORECASE)],
        "medio_pago_texto": [re.compile(r"Medio\s+de\s+pago\s*:\s*([^\n\r]+)", re.IGNORECASE)],
    }
    for campo, patrones in extras.items():
        valor = _primero(texto, patrones)
        if valor:
            campos[campo] = valor

    if naturaleza == "documento_equivalente":
        t = _normalizar_texto(texto)
        if "documento equivalente electronico spd" in t or re.search(r"\bspd\b", t):
            campos["subtipo_documento"] = "SPD"
        campos.setdefault("tipo_identificador_fiscal", "CUDE" if campos.get("cufe") else "")

    # En notas crédito/débito el encabezado puede usar "Nota Crédito No.".
    if not campos.get("numero_factura") and naturaleza in {"nota_credito", "nota_debito"}:
        m = re.search(r"nota\s+(?:cr[eé]dito|d[eé]bito)(?:\s+electr[oó]nica)?\s*(?:n[uú]mero|no\.?|#)?\s*[:.\-]?\s*([A-Z]{1,10}[- ]?\d{1,20})", texto, re.IGNORECASE)
        if m:
            campos["numero_factura"] = m.group(1).strip()
    return campos


def extraer_factura_pdf(contenido: bytes, permitir_ocr: bool = True) -> dict:
    """Extrae campos de una representación gráfica DIAN."""
    texto = _extraer_texto_directo(contenido)
    fuente = "pdf_texto"
    if len(texto) < 30 and permitir_ocr:
        texto = _extraer_texto_ocr(contenido)
        fuente = "pdf_ocr"

    campos = _buscar_campos(texto)
    claves_confianza = ("cufe", "numero_factura", "nit_emisor", "total", "fecha_emision", "iva")
    encontrados = sum(1 for campo in claves_confianza if campos.get(campo) not in (None, ""))
    confianza = round(encontrados * 100.0 / len(claves_confianza), 1)
    if fuente == "pdf_ocr":
        confianza = round(confianza * 0.8, 1)

    return {
        "fuente": fuente,
        "campos": campos,
        "confianza": confianza,
        "texto_bruto": texto[:5000],
    }
