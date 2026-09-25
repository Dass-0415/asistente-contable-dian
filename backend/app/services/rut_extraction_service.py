"""Extracción estructurada del RUT DIAN.

El RUT se usa como una fuente opcional para ayudar a parametrizar el perfil
tributario de una empresa. El servicio NO decide periodicidades ni obligaciones
territoriales: esas requieren reglas y/o confirmación del contador.

Por privacidad y rendimiento, el resultado conserva únicamente información
tributaria necesaria (NIT, tipo de persona, seccional, municipio, actividades y
responsabilidades). No guarda correo, teléfono, dirección ni representantes.
"""
from __future__ import annotations

import io
import re
import unicodedata
from datetime import date, datetime
from typing import Any

import pdfplumber


_RESP_RE = re.compile(r"^\s*(\d{1,2})\s*-\s*(.+?)\s*$", re.MULTILINE)
_RESP_NOMBRES = {
    "05": "Impuesto sobre la renta y complementarios · régimen ordinario",
    "07": "Retención en la fuente a título de renta",
    "09": "Retención en la fuente en el impuesto sobre las ventas",
    "13": "Gran contribuyente",
    "14": "Informante de exógena",
    "15": "Autorretenedor",
    "42": "Obligado a llevar contabilidad",
    "47": "Régimen Simple de Tributación - SIMPLE",
    "48": "Impuesto sobre las ventas - IVA",
    "52": "Facturador electrónico",
    "55": "Informante de Beneficiarios Finales",
}
_FORM_RE = re.compile(r"4\.\s*N[uú]mero de formulario\s+([0-9 ]{8,})", re.IGNORECASE)
_GENERATED_RE = re.compile(
    r"Fecha generaci[oó]n documento PDF:\s*(\d{2})-(\d{2})-(\d{4})",
    re.IGNORECASE,
)


def _normalizar(texto: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", texto or "")
        if not unicodedata.combining(c)
    ).lower()


def _texto_pdf(contenido: bytes) -> tuple[str, str]:
    """Extrae texto del PDF. OCR solo se usa como último recurso."""
    paginas: list[str] = []
    try:
        with pdfplumber.open(io.BytesIO(contenido)) as pdf:
            # El perfil tributario está en la hoja 1; leer como máximo 3 hojas
            # evita trabajo innecesario en anexos atípicos.
            for pagina in pdf.pages[:3]:
                paginas.append(pagina.extract_text(x_tolerance=1.5, y_tolerance=3) or "")
    except Exception:
        paginas = []
    texto = "\n".join(paginas).strip()
    normal = _normalizar(texto)
    if len(texto) >= 80 and ("registro unico tributario" in normal or "responsabilidades, calidades y atributos" in normal):
        return texto, "pdf_texto"

    # RUT escaneado: intentar OCR únicamente en la primera página.
    try:
        import pytesseract
        from pdf2image import convert_from_bytes
        imgs = convert_from_bytes(contenido, dpi=180, first_page=1, last_page=1)
        if imgs:
            try:
                ocr = pytesseract.image_to_string(imgs[0], lang="spa+eng")
            except Exception:
                ocr = pytesseract.image_to_string(imgs[0])
            if ocr and len(ocr.strip()) > len(texto):
                return ocr.strip(), "pdf_ocr"
    except Exception:
        pass
    return texto, "pdf_texto"


def _digits(value: str) -> str:
    return "".join(ch for ch in (value or "") if ch.isdigit())


def _extraer_identificacion(texto: str) -> tuple[str | None, str | None, str | None]:
    """Devuelve NIT base, DV y dirección seccional desde la cabecera DIAN."""
    lineas = texto.splitlines()
    for i, line in enumerate(lineas):
        if "Número de Identificación Tributaria" not in line and "Numero de Identificacion Tributaria" not in _normalizar(line):
            continue
        # La línea siguiente del RUT DIAN contiene NIT + DV y luego el nombre
        # de la seccional. Evitamos leer códigos posteriores de otros campos.
        for cand in lineas[i + 1:i + 4]:
            m = re.match(
                r"^\s*([0-9.\-\s]{8,40}?)\s+"
                r"([A-Za-zÁÉÍÓÚÜÑáéíóúüñ].+?)\s+(?:\d\s+){1,2}\d?\s*$",
                cand,
            )
            if not m:
                continue
            todos = _digits(m.group(1))
            if len(todos) < 8:
                continue
            return todos[:-1], todos[-1], m.group(2).strip()
    return None, None, None


def _extraer_tipo_persona(texto: str) -> str | None:
    n = _normalizar(texto)
    if "persona juridica" in n:
        return "juridica"
    if "persona natural o sucesion iliquida" in n or "persona natural" in n:
        return "natural"
    return None


def _extraer_razon_social(texto: str) -> str | None:
    lineas = [x.strip() for x in texto.splitlines()]
    for i, line in enumerate(lineas):
        if re.match(r"^35\.\s*Raz[oó]n social", line, re.IGNORECASE):
            for cand in lineas[i + 1:i + 4]:
                if cand and not re.match(r"^\d+\.", cand) and cand.upper() not in {"UBICACIÓN", "UBICACION"}:
                    return cand[:200]
    return None


def _extraer_municipio(texto: str) -> str | None:
    # La primera línea debajo del encabezado de UBICACIÓN normalmente sigue:
    # COLOMBIA ... <Departamento> ... <Municipio> 0 0 1
    lineas = [x.strip() for x in texto.splitlines()]
    for i, line in enumerate(lineas):
        if line.upper() in {"UBICACIÓN", "UBICACION"}:
            for cand in lineas[i + 1:i + 7]:
                if cand.startswith("COLOMBIA"):
                    # Estructura usual: COLOMBIA 1 6 9 <depto> <cod depto 2>
                    # <municipio> <cod municipio 3>. Los códigos cambian por ciudad.
                    m = re.match(
                        r"^COLOMBIA\s+(?:\d\s+){2}\d\s+(.+?)\s+"
                        r"\d\s+\d\s+(.+?)\s+\d\s+\d\s+\d\s*$",
                        cand, re.IGNORECASE,
                    )
                    if m:
                        return re.sub(r"\s+", " ", m.group(2)).strip() or None
    return None


def _extraer_responsabilidades(texto: str) -> list[dict[str, str]]:
    # Limitar al bloque correspondiente para no confundir otros códigos del RUT.
    inicio = texto.find("Responsabilidades, Calidades y Atributos")
    bloque = texto[inicio:] if inicio >= 0 else texto
    fin = bloque.find("Usuarios aduaneros")
    if fin >= 0:
        bloque = bloque[:fin]
    vistos: set[str] = set()
    out: list[dict[str, str]] = []
    for codigo, nombre in _RESP_RE.findall(bloque):
        codigo = codigo.zfill(2)
        if codigo in vistos:
            continue
        # Evita capturar fechas/códigos sueltos que no tengan descripción textual.
        if not re.search(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]", nombre):
            continue
        nombre = re.sub(r"\s+", " ", nombre).strip(" .")
        nombre = _RESP_NOMBRES.get(codigo, nombre)
        vistos.add(codigo)
        out.append({"codigo": codigo, "nombre": nombre[:180]})
    return out


def _parse_fecha_yyyymmdd(d: str) -> str | None:
    if len(d) != 8:
        return None
    try:
        return datetime.strptime(d, "%Y%m%d").date().isoformat()
    except ValueError:
        return None


def _extraer_actividades(texto: str) -> list[dict[str, Any]]:
    """Extrae CIIU principal/secundaria/otras del bloque de clasificación.

    El PDF DIAN suele renderizar la fila como dígitos separados por espacios:
    CIIU(4)+fecha(8)+CIIU(4)+fecha(8)+otras CIIU(4...).
    """
    lineas = texto.splitlines()
    idx = next((i for i, l in enumerate(lineas) if "46. Código" in l or "46. Codigo" in _normalizar(l)), None)
    if idx is None:
        return []
    for cand in lineas[idx + 1:idx + 5]:
        digs = _digits(cand)
        if len(digs) < 12:
            continue
        pos = 0
        principal = digs[pos:pos + 4]; pos += 4
        fecha_principal = digs[pos:pos + 8]; pos += 8
        out: list[dict[str, Any]] = []
        if len(principal) == 4:
            out.append({"tipo": "principal", "codigo": principal, "fecha_inicio": _parse_fecha_yyyymmdd(fecha_principal)})
        if len(digs) >= pos + 12:
            secundaria = digs[pos:pos + 4]; pos += 4
            fecha_sec = digs[pos:pos + 8]; pos += 8
            if len(secundaria) == 4 and secundaria != "0000":
                out.append({"tipo": "secundaria", "codigo": secundaria, "fecha_inicio": _parse_fecha_yyyymmdd(fecha_sec)})
        n = 1
        while len(digs) >= pos + 4 and n <= 2:
            cod = digs[pos:pos + 4]; pos += 4
            if cod and cod != "0000":
                out.append({"tipo": f"otra_{n}", "codigo": cod, "fecha_inicio": None})
                n += 1
        return out
    return []


def _extraer_formulario(texto: str) -> str | None:
    m = _FORM_RE.search(texto)
    if not m:
        return None
    val = _digits(m.group(1))
    return val[:30] or None


def _extraer_fecha_generacion(texto: str) -> str | None:
    m = _GENERATED_RE.search(texto)
    if not m:
        return None
    try:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1))).isoformat()
    except ValueError:
        return None


def analizar_rut_pdf(contenido: bytes) -> dict[str, Any]:
    texto, fuente = _texto_pdf(contenido)
    normal = _normalizar(texto)
    es_rut = (
        "responsabilidades, calidades y atributos" in normal
        and "numero de identificacion tributaria" in normal
    )
    if not es_rut:
        return {
            "valido": False,
            "fuente": fuente,
            "advertencias": ["El PDF no parece corresponder a un RUT DIAN legible."],
        }

    nit, dv, seccional = _extraer_identificacion(texto)
    responsabilidades = _extraer_responsabilidades(texto)
    codigos = {x["codigo"] for x in responsabilidades}
    tipo_persona = _extraer_tipo_persona(texto)

    sugerencias = {
        "tipo_persona": tipo_persona,
        "responsable_iva": "48" in codigos,
        "regimen_simple": "47" in codigos,
        "agente_retencion": bool({"07", "09", "15"} & codigos),
        "obligado_renta": "05" in codigos,
        "obligado_exogena": "14" in codigos,
    }
    advertencias: list[str] = []
    if "48" in codigos:
        advertencias.append("El RUT confirma responsabilidad de IVA, pero no determina por sí solo la periodicidad bimestral o cuatrimestral.")
    advertencias.append("ICA/ReteICA y demás obligaciones territoriales no se activan automáticamente desde el RUT nacional.")
    if fuente == "pdf_ocr":
        advertencias.append("El RUT fue leído mediante OCR; revisa los datos detectados antes de aplicarlos.")

    return {
        "valido": True,
        "fuente": fuente,
        "numero_formulario": _extraer_formulario(texto),
        "nit": nit,
        "dv": dv,
        "tipo_persona": tipo_persona,
        "razon_social": _extraer_razon_social(texto),
        "direccion_seccional": seccional,
        "municipio": _extraer_municipio(texto),
        "fecha_generacion": _extraer_fecha_generacion(texto),
        "actividades": _extraer_actividades(texto),
        "responsabilidades": responsabilidades,
        "sugerencias_perfil": sugerencias,
        "advertencias": advertencias,
    }
