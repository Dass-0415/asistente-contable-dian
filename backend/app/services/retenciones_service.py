"""Sugerencias conservadoras de retenciones a partir del historial real de la empresa.

No altera los valores DIAN originales. Las sugerencias solo se vuelven contables
cuando el usuario las confirma explícitamente.
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from statistics import median
from typing import Optional

from sqlalchemy.orm import Session

from app.models.models import Empresa, Factura, HistorialTecnicoSiigo


def _nit(v) -> str:
    return re.sub(r"\D", "", str(v or ""))


def _codigo(v) -> str:
    s = str(v or "").strip()
    return s.ljust(10, "0") if s.isdigit() and len(s) <= 10 else s


def _valores(row: HistorialTecnicoSiigo) -> dict:
    try:
        return json.loads(row.valores_columnas_json or "{}")
    except Exception:
        return {}


def _dc(row: HistorialTecnicoSiigo) -> str:
    for k, v in _valores(row).items():
        nk = " ".join(str(k or "").upper().replace("É", "E").split())
        if "DEBITO O CREDITO" in nk or "DÉBITO O CRÉDITO" in nk:
            return str(v or "").strip().upper()[:1]
    return ""


def _valor(row: HistorialTecnicoSiigo) -> float:
    for k, v in _valores(row).items():
        nk = " ".join(str(k or "").upper().split())
        if "VALOR DE LA SECUENCIA" in nk:
            try:
                txt = str(v).replace(" ", "").replace("$", "")
                if "," in txt and "." in txt:
                    txt = txt.replace(".", "").replace(",", ".")
                elif "," in txt:
                    txt = txt.replace(",", ".")
                return abs(float(txt))
            except Exception:
                return 0.0
    return 0.0


def _tipo_retencion(codigo: str, dc: str, direccion: str) -> Optional[str]:
    c = str(codigo or "")
    if direccion == "emitida":
        if dc != "D":
            return None
        if c.startswith("135515"): return "retefuente"
        if c.startswith("135517"): return "reteiva"
        if c.startswith("135518"): return "reteica"
        return None
    if dc != "C":
        return None
    if c.startswith("2365"): return "retefuente"
    if c.startswith("2367"): return "reteiva"
    if c.startswith("2368"): return "reteica"
    return None


def _nivel_confianza(usos: int, dispersion: float, mismo_anio: bool) -> tuple[str, int]:
    if usos >= 3 and dispersion <= 0.002 and mismo_anio:
        return "alta", 95
    if usos >= 2 and dispersion <= 0.005 and mismo_anio:
        return "alta", 88
    if usos >= 2 and dispersion <= 0.01:
        return "media", 72
    if usos >= 1 and dispersion <= 0.005 and mismo_anio:
        return "media", 65
    return "baja", 40


def retenciones_efectivas(factura: Factura) -> dict[str, float]:
    """Combina la fuente DIAN con retenciones contables confirmadas por el usuario.

    La fuente DIAN nunca se sobrescribe. Una retención confirmada solo reemplaza
    el mismo tipo para efectos de la partida contable.
    """
    try:
        base = json.loads(factura.retenciones_json or "{}")
    except Exception:
        base = {}
    try:
        contables = json.loads(getattr(factura, "retenciones_contables_json", None) or "{}")
    except Exception:
        contables = {}
    salida = {k: float(base.get(k, 0) or 0) for k in ("retefuente", "reteica", "reteiva")}
    for k in salida:
        if k in contables:
            salida[k] = float(contables.get(k, 0) or 0)
    return salida


def sugerir_retenciones(db: Session, empresa: Empresa, factura: Factura,
                         cuenta_principal_codigo: Optional[str] = None) -> dict:
    """Sugiere retenciones usando comprobantes históricos del mismo tercero.

    Se prioriza evidencia del mismo año de la factura (vigencia práctica). Si la
    evidencia es antigua o inestable, la confianza baja y la interfaz exige
    revisión humana. No se hardcodean tarifas tributarias generales que puedan
    cambiar por concepto/municipio/vigencia.
    """
    existentes = retenciones_efectivas(factura)
    nit_obj = _nit(factura.tercero_nit)
    if not nit_obj:
        return {"sugerencias": [], "motivo": "Sin NIT de tercero identificado."}

    filas = db.query(HistorialTecnicoSiigo).filter(HistorialTecnicoSiigo.empresa_id == empresa.id).all()
    if not filas:
        return {"sugerencias": [], "motivo": "Sin historial SIIGO suficiente para sugerir retenciones."}

    # Agrupar por comprobante histórico.
    grupos = defaultdict(list)
    for r in filas:
        if not r.numero_documento:
            continue
        grupos[(str(r.tipo_comprobante or ""), str(r.codigo_comprobante or ""), str(r.numero_documento))].append(r)

    direccion = factura.direccion_documento or "recibida"
    anio_doc = factura.fecha_emision.year if factura.fecha_emision else None
    evidencia = defaultdict(list)
    cuenta_obj = _codigo(cuenta_principal_codigo) if cuenta_principal_codigo else ""

    for g in grupos.values():
        # El tercero puede estar en varias líneas del comprobante; basta una coincidencia.
        if not any(_nit(r.nit) == nit_obj for r in g):
            continue

        # Si se conoce la cuenta principal, exigir que aparezca en el comprobante.
        if cuenta_obj and not any(_codigo(r.cuenta_codigo) == cuenta_obj for r in g):
            continue

        if direccion == "emitida":
            principales = [r for r in g if str(r.cuenta_codigo or "").startswith("4") and _dc(r) == "C"]
        else:
            principales = [r for r in g if str(r.cuenta_codigo or "")[:1] in ("5", "6", "7") and _dc(r) == "D"]
        if not principales:
            continue
        principal_val = max((_valor(r) for r in principales), default=0.0)
        iva_val = max((_valor(r) for r in g if str(r.cuenta_codigo or "").startswith("2408")), default=0.0)
        if principal_val <= 0:
            continue

        for r in g:
            tipo = _tipo_retencion(str(r.cuenta_codigo or ""), _dc(r), direccion)
            if not tipo:
                continue
            rv = _valor(r)
            if rv <= 0:
                continue
            base = iva_val if tipo == "reteiva" and iva_val > 0 else principal_val
            if base <= 0:
                continue
            tasa = rv / base
            # Evitar aprender líneas que claramente no parecen una retención porcentual.
            if tasa <= 0 or tasa > 0.50:
                continue
            mismo_anio = bool(anio_doc and r.fecha_documento and r.fecha_documento.year == anio_doc)
            evidencia[tipo].append({"tasa": tasa, "mismo_anio": mismo_anio, "fecha": r.fecha_documento})

    sugerencias = []
    for tipo in ("retefuente", "reteica", "reteiva"):
        if float(existentes.get(tipo, 0) or 0) > 0:
            continue
        obs = evidencia.get(tipo) or []
        if not obs:
            continue
        tasas = sorted(x["tasa"] for x in obs)
        tasa = float(median(tasas))
        dispersion = (max(tasas) - min(tasas)) if len(tasas) > 1 else 0.0
        hay_mismo_anio = any(x["mismo_anio"] for x in obs)
        nivel, puntaje = _nivel_confianza(len(obs), dispersion, hay_mismo_anio)
        alerta_regimen = ""
        # El RST puede cambiar el tratamiento según el tipo de retención/operación.
        # No se elimina evidencia histórica ni se asume una regla legal universal:
        # se fuerza revisión humana antes de aplicar retefuente/reteica en compras.
        if empresa.regimen_simple and direccion != "emitida" and tipo in ("retefuente", "reteica"):
            if nivel == "alta":
                nivel, puntaje = "media", min(puntaje, 70)
            alerta_regimen = " Empresa en SIMPLE/RST: revisar tratamiento vigente antes de confirmar."

        if tipo == "reteiva":
            base_actual = float(factura.iva or 0)
        else:
            base_actual = float(factura.base_gravable or factura.subtotal or 0)
        if base_actual <= 0:
            continue
        valor = round(base_actual * tasa, 2)
        if valor <= 0:
            continue
        sugerencias.append({
            "tipo": tipo,
            "base": round(base_actual, 2),
            "tarifa": round(tasa * 100, 4),
            "valor": valor,
            "nivel_confianza": nivel,
            "puntaje_confianza": puntaje,
            "observaciones_historicas": len(obs),
            "evidencia_mismo_anio": hay_mismo_anio,
            "motivo": (
                f"Historial del mismo tercero: {len(obs)} comprobante(s) con una tarifa cercana a {round(tasa*100,4)}%. "
                + ("Hay evidencia de la misma vigencia." if hay_mismo_anio else "La evidencia es de otra vigencia; requiere revisión.")
                + alerta_regimen
            ),
        })

    return {
        "sugerencias": sugerencias,
        "motivo": "Sugerencias basadas en historial real de esta empresa y este tercero.",
        "retenciones_fuente": {k: float(v or 0) for k, v in existentes.items()},
    }
