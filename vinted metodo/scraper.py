#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
============================================================================
 ING MAX SCRAPER  —  recon + decodificación + leads de ING España
============================================================================
Especializado EXCLUSIVAMENTE en ing.es y su ecosistema.

QUÉ HACE
  FASE 0  Warm-up + cookies (Akamai) + descubrimiento de subdominios ing.es
  FASE 1  Cosecha de sitemaps (robots.txt -> sitemap.xml + /ennaranja/sitemap.xml)
  FASE 2  Descubrimiento AEM (.model.json, .infinity.json, querybuilder) y APIs
  FASE 3  Rastreo masivo de páginas (oficinas, cajeros, productos, prensa, blog)
  FASE 4  CAPA DE DECODIFICACIÓN: base64, base64url, JWT, gzip+b64, hex,
          HTML-entities, URL-encoding, JSON escapado en atributos -> recursivo
  FASE 5  EXTRACCIÓN + VALIDACIÓN: DNI/NIE (dígito de control), CIF, IBAN ES
          (mod-97), teléfonos ES, fechas de nacimiento, emails, personas,
          oficinas completas (dirección, CP, horario, servicios, festivos)
  FASE 6  Volcado a SQLite (ing.db) + CSV + JSON + resumen

  MODO LOGIN (opcional, --login): entra en el Área de Clientes de ING con
  DNI + fecha de nacimiento + clave y captura los JSON de la sesión para
  sacar los datos reales de cada cuenta.

USO
  python ing_max_scraper.py
  python ing_max_scraper.py --limit 80 --workers 20
  python ing_max_scraper.py --no-subdomains --no-aem
  python ing_max_scraper.py --login --dni 12345678Z --fecha 01/01/1985
  python ing_max_scraper.py --proxy http://ip:puerto --no-verify
============================================================================
"""

from __future__ import annotations

import os
import re
import sys
import csv
import json
import time
import base64
import gzip
import html
import zlib
import random
import sqlite3
import argparse
import datetime
import threading
import concurrent.futures as cf
from urllib.parse import (
    urljoin, urlsplit, urlunsplit, urlencode, unquote, unquote_plus,
)
from typing import Any, Callable, Dict, Iterable, List, Optional, Set, Tuple

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET

# ---------------------------------------------------------------------------
# Consola UTF-8 / ANSI en Windows
# ---------------------------------------------------------------------------
os.system("")
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# ---------------------------------------------------------------------------
# CONFIGURACIÓN
# ---------------------------------------------------------------------------
BASE = "https://www.ing.es"
DEFAULT_OUT_DIR = os.getenv("ING_OUT", "ing_leads")
DEFAULT_DELAY = float(os.getenv("ING_DELAY", "0.15"))
DEFAULT_TIMEOUT = int(os.getenv("ING_TIMEOUT", "18"))
DEFAULT_WORKERS = int(os.getenv("ING_WORKERS", "14"))

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.6 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
]

SITEMAPS = [
    f"{BASE}/sitemap.xml",
    f"{BASE}/ennaranja/sitemap.xml",
]

# Rutas específicas ING (productos, corporativo, oficinas, AEM, APIs)
ING_PATHS = [
    "/robots.txt", "/sitemap.xml", "/.well-known/security.txt",
    "/oficinas-cajeros", "/oficinas-cajeros/oficinas", "/oficinas-cajeros/cajeros",
    "/oficinas-cajeros/buscador-oficinas", "/oficinas-cajeros/buscador-cajeros",
    "/oficinas-cajeros/espacios-ing",
    "/contacto", "/chat-online", "/hazte-cliente",
    "/sobre-ing", "/sobre-ing/preguntas-frecuentes", "/sobre-ing/sala-prensa",
    "/sobre-ing/informacion-legal", "/sobre-ing/trabaja-con-nosotros/ofertas-empleo",
    "/sobre-ing/reclamacion-oficial", "/sobre-ing/concurso-acreedores",
    "/sobre-ing/politica-de-denuncias-de-ing", "/sobre-ing/mapa-sitio",
    "/cuentas-ing", "/cuenta-nomina-ing", "/cuenta-naranja", "/cuenta-mini",
    "/tarjetas-ing", "/hipotecas", "/prestamos-personales", "/seguros",
    "/fondos-inversion", "/fondos-inversion/listado-fondos",
    "/planes-pensiones", "/planes-pensiones/todos-los-planes",
    "/broker", "/broker/acciones", "/broker/etfs",
    "/privacidad-ing", "/politica-menores", "/cookies", "/privacidad-cookies",
    "/seguridad-internet", "/bienestar-digital", "/afiliacion-creadores",
    "/responsable-disclosure", "/accesibilidad",
    # AEM / APIs / dev
    "/bin/querybuilder.json?path=/content&type=cq:Page&p.limit=50",
    "/content.1.json", "/content.infinity.json", "/content.model.json",
    "/hippogenoma/navigation/26",
    "/wc/ing-cms-component-library/es6/public/assets/js/lit-components-loader.js",
    "/hippotealium/utag.sync.js",
]

# Candidatos de subdominios ING a probar siempre
KNOWN_SUBDOMAINS = [
    "www.ing.es", "ing.ingdirect.es", "banca.ingdirect.es",
    "api.ing.es", "assets.ing.es", "cdn.ing.es",
    "www.ingdirect.es", "cookies.resources.ingdirect.es",
]

# ---------------------------------------------------------------------------
# REGEX
# ---------------------------------------------------------------------------
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(
    r"(?:\+34[\s.\-]?)?(?:\(?\d{2,3}\)?[\s.\-]?)?\d{3}[\s.\-]?\d{2}[\s.\-]?\d{2}"
)
DNI_RE = re.compile(r"\b(?:\d{8}[A-HJ-NP-TV-Z]|[XYZ]\d{7}[A-HJ-NP-TV-Z])\b", re.I)
CIF_RE = re.compile(r"\b[ABCDEFGHJNPQRSUVW]-?\d{7}-?[0-9A-J]\b", re.I)
IBAN_RE = re.compile(r"\bES\d{2}(?:[ ]?\d{4}){5}\b", re.I)
CP_RE = re.compile(r"\b(0[1-9]\d{3}|[1-4]\d{4}|5[0-2]\d{3})\b")
DATE_RE = re.compile(
    r"\b(\d{1,2}[/\-.]\d{1,2}[/\-.]\d{4}|\d{4}-\d{2}-\d{2}|"
    r"\d{1,2}\s+de\s+[a-záéíóúñ]+\s+de\s+\d{4})\b",
    re.IGNORECASE,
)
B64_RE = re.compile(r"[A-Za-z0-9+/]{16,}={0,2}")
B64URL_RE = re.compile(r"[A-Za-z0-9_-]{20,}={0,2}")
JWT_RE = re.compile(r"[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{5,}")
HEX_RE = re.compile(r"\b(?:0x)?([0-9a-fA-F]{24,})\b")
SOCIAL_RE = re.compile(
    r"https?://(?:www\.)?"
    r"(?:facebook\.com|twitter\.com|x\.com|instagram\.com|youtube\.com|"
    r"tiktok\.com|linkedin\.com|wa\.me|t\.me)"
    r"/[A-Za-z0-9_.@\-/%]+",
    re.I,
)
ESC_JSON_ATTR_RE = re.compile(r"(?:\{&quot;|\[&quot;|\{&#34;|\[&#34;)")

DNI_LETTERS = "TRWAGMYFPDXBNJZSQVHLCKE"
MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}

MAX_BODY = 600_000
MAX_DECODE_DEPTH = 3

# ---------------------------------------------------------------------------
# VALIDADORES REALES
# ---------------------------------------------------------------------------

def dni_valid(raw: str) -> bool:
    """Valida DNI/NIE español con su dígito de control."""
    s = re.sub(r"[\s\-.]", "", raw).upper()
    if re.fullmatch(r"\d{8}[A-Z]", s):
        return DNI_LETTERS[int(s[:8]) % 23] == s[8]
    if re.fullmatch(r"[XYZ]\d{7}[A-Z]", s):
        num = {"X": "0", "Y": "1", "Z": "2"}[s[0]] + s[1:8]
        return DNI_LETTERS[int(num) % 23] == s[8]
    return False


def cif_valid(raw: str) -> bool:
    """Valida CIF español con su dígito de control."""
    s = re.sub(r"[\s\-.]", "", raw).upper()
    m = re.fullmatch(r"([ABCDEFGHJNPQRSUVW])(\d{7})([0-9A-J])", s)
    if not m:
        return False
    letra, digitos, control = m.groups()
    suma = 0
    for i, ch in enumerate(digitos):
        d = int(ch)
        if i % 2 == 0:
            d *= 2
            suma += d - 9 if d > 9 else d
        else:
            suma += d
    esperado = (10 - (suma % 10)) % 10
    letra_ctrl = "JABCDEFGHI"[esperado]
    if letra in "ABEH":
        return control == str(esperado)
    if letra in "KPQS":
        return control == letra_ctrl
    return control in (str(esperado), letra_ctrl)


def iban_valid(raw: str) -> bool:
    """Valida IBAN con el algoritmo módulo 97 (ISO 13616)."""
    s = re.sub(r"\s", "", raw).upper()
    if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{11,30}", s):
        return False
    reordenado = s[4:] + s[:4]
    try:
        num = "".join(str(int(c, 36)) for c in reordenado)
        return int(num) % 97 == 1
    except Exception:
        return False


def phone_valid(raw: str) -> Optional[str]:
    """Normaliza y valida teléfono español (9 dígitos, prefijo 5-9)."""
    d = re.sub(r"\D", "", raw)
    if d.startswith("0034"):
        d = d[4:]
    if d.startswith("34") and len(d) == 11:
        d = d[2:]
    if len(d) == 9 and d[0] in "56789":
        return d
    return None


def date_normalize(raw: str) -> Optional[str]:
    """Normaliza fechas a ISO (YYYY-MM-DD) y valida rango razonable."""
    s = raw.strip().lower()
    m = re.fullmatch(r"(\d{1,2})\s+de\s+([a-záéíóúñ]+)\s+de\s+(\d{4})", s)
    if m:
        d, mes, y = int(m.group(1)), MESES.get(m.group(2)), int(m.group(3))
        if mes:
            return f"{y:04d}-{mes:02d}-{d:02d}"
        return None
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y-%m-%d", "%Y/%m/%d"):
        try:
            dt = datetime.datetime.strptime(s, fmt)
            if 1900 <= dt.year <= datetime.datetime.now().year:
                return dt.strftime("%Y-%m-%d")
        except Exception:
            continue
    return None


# ---------------------------------------------------------------------------
# CAPA DE DECODIFICACIÓN ("desencriptar")
# ---------------------------------------------------------------------------

def _printable_ratio(s: str) -> float:
    if not s:
        return 0.0
    ok = sum(1 for c in s if c.isprintable() or c in "\n\r\t")
    return ok / len(s)


def _dec_b64(s: str) -> Optional[str]:
    s2 = s.strip()
    pad = (-len(s2)) % 4
    try:
        raw = base64.b64decode(s2 + "=" * pad, validate=False)
    except Exception:
        return None
    for enc in ("utf-8", "latin-1"):
        try:
            txt = raw.decode(enc)
            if _printable_ratio(txt) > 0.90 and len(txt) >= 4:
                return txt
        except Exception:
            continue
    return None


def _dec_b64url(s: str) -> Optional[str]:
    s2 = s.strip()
    pad = (-len(s2)) % 4
    try:
        raw = base64.urlsafe_b64decode(s2 + "=" * pad)
    except Exception:
        return None
    try:
        txt = raw.decode("utf-8")
        if _printable_ratio(txt) > 0.90 and len(txt) >= 4:
            return txt
    except Exception:
        pass
    return None


def _dec_gzip_b64(s: str) -> Optional[str]:
    s2 = s.strip()
    pad = (-len(s2)) % 4
    try:
        raw = base64.b64decode(s2 + "=" * pad)
    except Exception:
        return None
    for fn in (gzip.decompress, zlib.decompress):
        try:
            txt = fn(raw).decode("utf-8", errors="replace")
            if _printable_ratio(txt) > 0.85:
                return txt
        except Exception:
            continue
    return None


def _dec_hex(s: str) -> Optional[str]:
    h = s[2:] if s.lower().startswith("0x") else s
    if len(h) % 2:
        return None
    try:
        txt = bytes.fromhex(h).decode("utf-8", errors="replace")
    except Exception:
        return None
    return txt if _printable_ratio(txt) > 0.85 and len(txt) >= 4 else None


def _dec_jwt(token: str) -> Optional[str]:
    parts = token.split(".")
    if len(parts) != 3:
        return None
    out = {}
    for i, name in enumerate(("header", "payload")):
        d = _dec_b64url(parts[i])
        if d:
            try:
                out[name] = json.loads(d)
            except Exception:
                out[name] = d
    return json.dumps(out, ensure_ascii=False) if out else None


def decode_blob(text: str, depth: int = 0) -> List[Dict[str, str]]:
    """Aplica todas las capas de decodificación de forma recursiva."""
    found: List[Dict[str, str]] = []
    if depth > MAX_DECODE_DEPTH or not text:
        return found
    seen: Set[str] = set()

    def push(tipo: str, original: str, decodificado: Optional[str]):
        if not decodificado or decodificado in seen:
            return
        seen.add(decodificado)
        found.append({
            "tipo": tipo,
            "original": original[:300],
            "decodificado": decodificado[:20000],
        })
        if depth < MAX_DECODE_DEPTH:
            found.extend(decode_blob(decodificado, depth + 1))

    # 1) HTML entities (clave: JSON escapado en atributos ING)
    unesc = html.unescape(text)
    if unesc != text and ESC_JSON_ATTR_RE.search(text):
        push("html-entities", text[:200], unesc)

    # 2) URL-encoding
    if "%" in text:
        try:
            ud = unquote_plus(text)
            if ud != text and _printable_ratio(ud) > 0.85:
                push("url-decode", text[:200], ud)
        except Exception:
            pass

    # 3) JWT
    for tok in set(JWT_RE.findall(text)):
        j = _dec_jwt(tok)
        if j:
            push("jwt", tok, j)

    # 4) base64 / base64url
    for cand in set(B64_RE.findall(text)):
        if len(cand) < 20 or cand in seen:
            continue
        if not re.search(r"[+/=]", cand) and not re.search(r"[A-Z]", cand):
            continue
        for tipo, fn in (("base64-gzip", _dec_gzip_b64), ("base64", _dec_b64)):
            d = fn(cand)
            if d and _printable_ratio(d) > 0.85:
                push(tipo, cand, d)
                break
    for cand in set(B64URL_RE.findall(text)):
        if len(cand) < 24:
            continue
        d = _dec_b64url(cand)
        if d and _printable_ratio(d) > 0.85 and re.search(r"[{}\[\]:,]", d):
            push("base64url", cand, d)

    # 5) hex
    for cand in set(HEX_RE.findall(text)):
        d = _dec_hex(cand)
        if d and re.search(r"[a-zA-Z]{3,}", d):
            push("hex", cand, d)

    return found


def extract_escaped_json(html_text: str) -> List[Any]:
    """Extrae y parsea JSON escapado dentro de atributos HTML (patrón ING)."""
    out: List[Any] = []
    soup = BeautifulSoup(html_text, "html.parser")
    for tag in soup.find_all(True):
        for attr, value in tag.attrs.items():
            if isinstance(value, list):
                value = " ".join(value)
            if not isinstance(value, str) or len(value) < 8:
                continue
            if not ESC_JSON_ATTR_RE.search(value):
                continue
            try:
                parsed = json.loads(html.unescape(value))
            except Exception:
                continue
            if isinstance(parsed, (list, dict)):
                out.append({"tag": tag.name, "attr": attr, "json": parsed})
    # <script> con JSON embebido
    for sc in soup.find_all("script"):
        body = sc.string or sc.get_text() or ""
        if len(body) < 20:
            continue
        for var in ("__NEXT_DATA__", "__INITIAL_STATE__", "utag_data",
                    "didomiConfig", "ING_CONFIG"):
            m = re.search(rf"{var}\s*=\s*(\{{.*?\}}|\{{.*\}});", body, re.S)
            if m:
                try:
                    out.append({"tag": "script", "attr": var,
                                "json": json.loads(m.group(1))})
                except Exception:
                    pass
    return out


def walk_json(obj: Any, path: str = "") -> List[Tuple[str, str]]:
    """Recorre un JSON y devuelve pares (ruta, valor) con claves de interés."""
    KEYS = {
        "email", "correo", "mail", "telefono", "teléfono", "phone", "movil",
        "móvil", "mobile", "nombre", "name", "apellido", "apellidos", "surname",
        "dni", "nif", "nie", "cif", "iban", "cuenta", "account", "oficina",
        "office", "direccion", "dirección", "address", "cp", "postal",
        "ciudad", "city", "provincia", "province", "fecha", "date",
        "nacimiento", "birth", "titular", "holder", "saldo", "balance",
        "importe", "amount", "producto", "product", "contrato", "cliente",
        "customer", "id", "lat", "lng", "latitude", "longitude", "horario",
        "servicios", "tipo", "type", "cargo", "puesto", "jobtitle",
    }
    out: List[Tuple[str, str]] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            key = str(k).lower()
            p = f"{path}.{k}" if path else str(k)
            if isinstance(v, (str, int, float)) and key in KEYS and str(v).strip():
                out.append((p, str(v).strip()))
            elif isinstance(v, (dict, list)):
                out.extend(walk_json(v, p))
    elif isinstance(obj, list):
        for i, v in enumerate(obj[:400]):
            out.extend(walk_json(v, f"{path}[{i}]"))
    return out


# ---------------------------------------------------------------------------
# SCRAPER
# ---------------------------------------------------------------------------
class IngScraper:
    def __init__(
        self,
        out_dir: str = DEFAULT_OUT_DIR,
        delay: float = DEFAULT_DELAY,
        timeout: int = DEFAULT_TIMEOUT,
        workers: int = DEFAULT_WORKERS,
        verify_ssl: bool = True,
        proxy: Optional[str] = None,
        use_subdomains: bool = True,
        use_aem: bool = True,
        limit: Optional[int] = None,
        max_pages: int = 4000,
        status_callback: Optional[Callable[[str], None]] = None,
    ):
        self.out_dir = out_dir
        self.delay = delay
        self.timeout = timeout
        self.workers = max(1, workers)
        self.verify_ssl = verify_ssl
        self.proxy = proxy
        self.use_subdomains = use_subdomains
        self.use_aem = use_aem
        self.limit = limit
        self.max_pages = max_pages
        self.status_callback = status_callback

        self._lock = threading.Lock()
        self.seen: Set[str] = set()
        self.pages: List[Dict[str, Any]] = []
        self.oficinas: List[Dict[str, Any]] = []
        self.contactos: Dict[str, Dict[str, str]] = {}
        self.personas: List[Dict[str, str]] = []
        self.documentos: List[Dict[str, str]] = []
        self.decoded: List[Dict[str, str]] = []
        self.json_fields: List[Dict[str, str]] = []
        self.visited = 0

        self.session = requests.Session()
        retries = Retry(total=3, backoff_factor=0.6, backoff_max=10,
                        status_forcelist=[429, 500, 502, 503, 504],
                        allowed_methods=frozenset(["GET"]))
        ad = HTTPAdapter(max_retries=retries, pool_connections=40, pool_maxsize=40)
        self.session.mount("https://", ad)
        self.session.mount("http://", ad)
        self.session.headers.update({
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "es-ES,es;q=0.9,en;q=0.6",
            "Accept-Encoding": "gzip, deflate, br",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Cache-Control": "no-cache",
        })
        if self.proxy:
            self.session.proxies.update({"http": self.proxy, "https": self.proxy})

    # -- infra -------------------------------------------------------------
    def log(self, msg: str):
        try:
            print(msg)
        except Exception:
            print(msg.encode("ascii", "replace").decode("ascii"))
        if self.status_callback:
            try:
                self.status_callback(msg)
            except Exception:
                pass

    def fetch(self, url: str, timeout: Optional[int] = None) -> Optional[requests.Response]:
        if self.delay:
            time.sleep(self.delay * random.uniform(0.4, 1.3))
        try:
            return self.session.get(url, timeout=timeout or self.timeout,
                                    verify=self.verify_ssl, allow_redirects=True)
        except Exception:
            return None

    @staticmethod
    def _text(r: requests.Response) -> str:
        try:
            return r.text
        except Exception:
            return r.content.decode("utf-8", "replace")

    def _claim(self, url: str) -> bool:
        with self._lock:
            if url in self.seen:
                return False
            if self.visited >= self.max_pages:
                return False
            self.seen.add(url)
            self.visited += 1
            return True

    def _fetch_many(self, urls: Iterable[str]) -> Dict[str, requests.Response]:
        urls = [u for u in dict.fromkeys(urls) if self._claim(u)]
        out: Dict[str, requests.Response] = {}
        def work(u: str):
            r = self.fetch(u)
            if r is not None and r.status_code in (200, 203, 206) and self._text(r):
                with self._lock:
                    out[u] = r
        with cf.ThreadPoolExecutor(max_workers=self.workers) as ex:
            list(ex.map(work, urls))
        return out

    # -- fase 0 ------------------------------------------------------------
    def phase0_warmup(self):
        self.log("[*] FASE 0 — warm-up + cookies (Akamai) + subdominios")
        r = self.fetch(BASE + "/", timeout=25)
        if r is not None:
            self.log(f"  [+] Home {r.status_code} — cookies: {len(self.session.cookies)}")
        if not self.use_subdomains:
            return
        subs: Set[str] = set(KNOWN_SUBDOMAINS)
        cr = self.fetch("https://crt.sh/?q=%25.ing.es&output=json", timeout=45)
        if cr is not None and cr.status_code == 200:
            try:
                for e in json.loads(cr.text):
                    for n in str(e.get("name_value", "")).split("\n"):
                        n = n.strip().lower().lstrip("*.")
                        if n.endswith("ing.es"):
                            subs.add(n)
            except Exception:
                pass
        subs = {s for s in subs if not any(x in s for x in
                ("akam", "metrics", "test.", "pre.", "dev."))}
        self.log(f"  [+] {len(subs)} hosts ing.es a probar")
        urls = [f"https://{s}/" for s in sorted(subs)]
        res = self._fetch_many(urls)
        for u, r in res.items():
            self.log(f"  [+] host OK: {u} ({r.status_code})")
        self.hosts = sorted({urlsplit(u).netloc for u in res})
        if BASE.split("//")[1] not in self.hosts:
            self.hosts.insert(0, BASE.split("//")[1])

    # -- fase 1: sitemaps --------------------------------------------------
    def phase1_sitemaps(self) -> List[str]:
        self.log("[*] FASE 1 — cosechando sitemaps de ING")
        urls: List[str] = []
        queue = list(SITEMAPS)
        seen_sm: Set[str] = set()

        while queue and len(seen_sm) < 30:
            sm = queue.pop(0)
            if sm in seen_sm:
                continue
            seen_sm.add(sm)
            r = self.fetch(sm, timeout=30)
            if r is None or r.status_code != 200:
                continue
            body = self._text(r)
            if sm.endswith(".gz") or body[:2] == "\x1f\x8b":
                try:
                    body = gzip.decompress(r.content).decode("utf-8", "replace")
                except Exception:
                    pass
            locs = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", body, re.I)
            if "<sitemapindex" in body.lower():
                for c in locs:
                    queue.append(c.strip())
                self.log(f"  [+] index {sm} -> {len(locs)} sitemaps")
            else:
                for u in locs:
                    u = html.unescape(u.strip())
                    if u.startswith("http"):
                        urls.append(u.split("#")[0])
                self.log(f"  [+] {sm} -> {len(locs)} URLs")

        # clasificar: oficinas/cajeros primero, luego el resto
        uniq = list(dict.fromkeys(urls))
        ofi = [u for u in uniq if "/oficinas-cajeros/" in u and u.count("/") >= 5]
        resto = [u for u in uniq if u not in set(ofi)]
        random.shuffle(resto)
        ordered = ofi + resto
        if self.limit:
            ordered = ordered[: self.limit]
        self.log(f"  [=] {len(ordered)} URLs ({len(ofi)} de oficinas/cajeros)")
        return ordered

    # -- fase 2: AEM + APIs ------------------------------------------------
    def phase2_aem(self):
        if not self.use_aem:
            self.log("[*] FASE 2 — AEM DESACTIVADO")
            return
        self.log("[*] FASE 2 — descubrimiento AEM (.model.json/.infinity.json/querybuilder)")
        cands: List[str] = []
        for p in ("/content", "/content/ing", "/content/ing/es", "/content/dam"):
            for suf in (".model.json", ".infinity.json", ".1.json", ".2.json"):
                cands.append(BASE + p + suf)
        cands.append(BASE + "/bin/querybuilder.json?path=/content&type=cq:Page&p.limit=100")
        cands.append(BASE + "/bin/querybuilder.json?path=/content/dam&p.limit=100")
        cands.append(BASE + "/hippogenoma/navigation/26.json")
        cands += [BASE + p for p in ING_PATHS if p.endswith(".json")]

        res = self._fetch_many(cands)
        for u, r in res.items():
            ctype = r.headers.get("content-type", "").lower()
            if "json" in ctype or u.endswith(".json"):
                self.log(f"  [+] AEM/API OK: {u}")
                self._register(u, "aem-json", self._text(r))

    # -- fase 3: rastreo ---------------------------------------------------
    def phase3_crawl(self, urls: List[str]):
        self.log(f"[*] FASE 3 — rastreando {len(urls)} páginas (workers={self.workers})")
        batch = 60
        done = 0
        for i in range(0, len(urls), batch):
            chunk = urls[i:i + batch]
            res = self._fetch_many(chunk)
            for u, r in res.items():
                ctype = r.headers.get("content-type", "").lower()
                tipo = "json" if "json" in ctype else ("xml" if "xml" in ctype else "html")
                self._register(u, tipo, self._text(r))
            done += len(chunk)
            self.log(f"  [~] {done}/{len(urls)} procesadas · {len(self.pages)} guardadas")

        # rutas fijas ING que no estén ya
        fijas = [urljoin(BASE + "/", p.lstrip("/")) for p in ING_PATHS]
        res = self._fetch_many(fijas)
        for u, r in res.items():
            ctype = r.headers.get("content-type", "").lower()
            tipo = "json" if "json" in ctype else "html"
            self._register(u, tipo, self._text(r))

    def _register(self, url: str, tipo: str, body: str):
        with self._lock:
            self.pages.append({
                "url": url, "tipo": tipo, "body": body[:MAX_BODY],
                "dominio": urlsplit(url).netloc,
            })

    # -- fase 4+5: decode + extract ---------------------------------------
    def phase45_process(self):
        self.log(f"[*] FASE 4/5 — decodificando y extrayendo de {len(self.pages)} recursos")
        seen_leads: Set[Tuple] = set()

        for page in self.pages:
            url, tipo, body = page["url"], page["tipo"], page["body"]
            if not body:
                continue

            emails: Set[str] = set()
            phones: Set[str] = set()
            socials: Set[str] = set()
            nombres: Set[str] = set()
            dnis: Set[str] = set()
            cifs: Set[str] = set()
            ibans: Set[str] = set()
            fechas: Set[str] = set()
            local_decoded: List[Dict[str, str]] = []

            # ---- capa de decodificación ----
            local_decoded.extend(decode_blob(body))

            # ---- JSON escapado en atributos ----
            json_objs: List[Any] = []
            if tipo == "html":
                try:
                    for item in extract_escaped_json(body):
                        json_objs.append(item["json"])
                        local_decoded.append({
                            "tipo": f"attr-json:{item['tag']}@{item['attr']}",
                            "original": str(item["json"])[:300],
                            "decodificado": json.dumps(item["json"], ensure_ascii=False)[:8000],
                        })
                except Exception:
                    pass

            # ---- JSON nativo ----
            if tipo == "json":
                try:
                    json_objs.append(json.loads(body))
                except Exception:
                    pass

            # ---- walker de JSON ----
            for obj in json_objs:
                for path, val in walk_json(obj):
                    kl = path.lower()
                    with self._lock:
                        self.json_fields.append({"url": url, "campo": path, "valor": val[:200]})
                    if "mail" in kl and EMAIL_RE.fullmatch(val):
                        emails.add(val.lower())
                    elif any(x in kl for x in ("telefono", "teléfono", "phone", "movil", "móvil")):
                        p = phone_valid(val)
                        if p:
                            phones.add(p)
                    elif any(x in kl for x in ("dni", "nif", "nie")):
                        if dni_valid(val):
                            dnis.add(val.upper())
                    elif "cif" in kl:
                        if cif_valid(val):
                            cifs.add(val.upper())
                    elif "iban" in kl or "cuenta" in kl:
                        if iban_valid(val):
                            ibans.add(re.sub(r"\s", "", val).upper())
                    elif any(x in kl for x in ("fecha", "date", "nacimiento", "birth")):
                        d = date_normalize(val)
                        if d:
                            fechas.add(d)
                    elif "name" in kl or "nombre" in kl or "titular" in kl:
                        if 3 < len(val) < 70 and " " in val:
                            nombres.add(val.strip())

            # ---- texto enriquecido con decodificados ----
            blob = body + "\n" + "\n".join(d["decodificado"] for d in local_decoded)

            soup = None
            visible = blob
            if tipo == "html":
                try:
                    soup = BeautifulSoup(body, "html.parser")
                    for bad in soup(["script", "style", "noscript"]):
                        bad.decompose()
                    visible = soup.get_text(" ", strip=True)
                    for a in soup.find_all("a", href=True):
                        href = str(a["href"]).strip()
                        if href.lower().startswith("mailto:"):
                            e = href[7:].split("?")[0]
                            if EMAIL_RE.fullmatch(e):
                                emails.add(e.lower())
                        elif href.lower().startswith("tel:"):
                            p = phone_valid(href[4:])
                            if p:
                                phones.add(p)
                    for tag in soup.find_all("script", type="application/ld+json"):
                        try:
                            ld = json.loads(tag.string or "{}")
                        except Exception:
                            continue
                        for node in (ld if isinstance(ld, list) else [ld]):
                            if not isinstance(node, dict):
                                continue
                            nm = node.get("name")
                            if nm and isinstance(nm, str):
                                nombres.add(nm)
                            tel = node.get("telephone")
                            if isinstance(tel, str):
                                p = phone_valid(tel)
                                if p:
                                    phones.add(p)
                            em = node.get("email")
                            if isinstance(em, str) and EMAIL_RE.fullmatch(em):
                                emails.add(em.lower())
                except Exception:
                    visible = blob

            for e in EMAIL_RE.findall(blob):
                e = e.strip(".,;:").lower()
                if EMAIL_RE.fullmatch(e) and not e.endswith(
                        (".png", ".jpg", ".svg", ".webp", ".gif")):
                    emails.add(e)
            for raw in PHONE_RE.findall(visible):
                p = phone_valid(raw)
                if p:
                    phones.add(p)
            for s in SOCIAL_RE.findall(blob):
                socials.add(s.rstrip(".,;)"))
            for d in DNI_RE.findall(blob):
                if dni_valid(d):
                    dnis.add(d.upper())
            for c in CIF_RE.findall(blob):
                if cif_valid(c):
                    cifs.add(c.upper())
            for i in IBAN_RE.findall(blob):
                if iban_valid(i):
                    ibans.add(re.sub(r"\s", "", i).upper())
            for f in DATE_RE.findall(visible):
                d = date_normalize(f)
                if d:
                    fechas.add(d)

            # ---- oficina estructurada ----
            ofi = None
            if "/oficinas-cajeros/" in url and url.count("/") >= 5:
                ofi = self._parse_oficina(url, soup, visible)
                if ofi:
                    with self._lock:
                        self.oficinas.append(ofi)
                    if ofi.get("telefono"):
                        phones.add(ofi["telefono"])

            # ---- guardar decodificados ----
            if local_decoded:
                with self._lock:
                    for d in local_decoded[:60]:
                        self.decoded.append({"url": url, **d})

            # ---- guardar leads ----
            key = (tuple(sorted(emails)), tuple(sorted(phones)), tuple(sorted(dnis)))
            if key in seen_leads:
                continue
            seen_leads.add(key)

            if emails or phones or dnis or cifs or ibans or socials or nombres or ofi:
                with self._lock:
                    for e in emails:
                        self.contactos.setdefault(e, {"tipo": "email", "fuente": url})
                    for p in phones:
                        self.contactos.setdefault("tel:" + p, {"tipo": "telefono", "fuente": url})
                    for s in socials:
                        self.contactos.setdefault(s, {"tipo": "red", "fuente": url})
                    for n in nombres:
                        self.personas.append({"persona": n, "fuente": url})
                    for d in dnis:
                        self.documentos.append({"documento": d, "tipo": "DNI/NIE", "fuente": url})
                    for c in cifs:
                        self.documentos.append({"documento": c, "tipo": "CIF", "fuente": url})
                    for i in ibans:
                        self.documentos.append({"documento": i, "tipo": "IBAN", "fuente": url})
                    for f in fechas:
                        self.documentos.append({"documento": f, "tipo": "fecha", "fuente": url})

    def _parse_oficina(self, url: str, soup, visible: str) -> Optional[Dict[str, Any]]:
        parts = urlsplit(url).path.strip("/").split("/")
        provincia = parts[1].replace("-", " ").title() if len(parts) > 1 else ""
        slug = parts[2] if len(parts) > 2 else ""
        tipo = "cajero" if slug.startswith("cajero") else "oficina"

        nombre = ""
        direccion = ""
        cp = ""
        ciudad = ""
        if soup is not None:
            h = soup.find(["h1", "h2"])
            if h:
                nombre = h.get_text(" ", strip=True)
            if not nombre and soup.title:
                nombre = (soup.title.string or "").split("|")[0].strip()
            # patrón dirección ING: "Calle X, 28005, Madrid"
            m = re.search(
                r"([A-ZÁÉÍÓÚÑ][^,\n]{4,70}?),\s*(\d{5}),\s*([A-Za-zÁÉÍÓÚÑáéíóúñ\s]{3,40})",
                visible,
            )
            if m:
                direccion, cp, ciudad = m.group(1).strip(), m.group(2), m.group(3).strip()
            else:
                m2 = re.search(r"([A-ZÁÉÍÓÚÑ][^,\n]{4,70}?),\s*(\d{5})", visible)
                if m2:
                    direccion, cp = m2.group(1).strip(), m2.group(2)

        tel = None
        m = re.search(r"\+34[\s.]?\d{2,3}[\s.]?\d{2,3}[\s.]?\d{2}[\s.]?\d{2}", visible)
        if m:
            tel = phone_valid(m.group(0))

        horario = "; ".join(
            l for l in re.split(r"(?<=[.h])\s", visible)
            if re.search(r"lunes|martes|miércoles|jueves|viernes|s[áa]bado", l, re.I)
        )[:400]

        if not (direccion or tel):
            return None
        return {
            "nombre": nombre, "tipo": tipo, "provincia": provincia,
            "direccion": direccion, "cp": cp, "ciudad": ciudad,
            "telefono": tel, "horario": horario, "url": url,
        }

    # -- fase 6: guardado --------------------------------------------------
    def save(self) -> Dict[str, str]:
        os.makedirs(self.out_dir, exist_ok=True)
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        db_path = os.path.join(self.out_dir, "ing.db")
        ofi_csv = os.path.join(self.out_dir, f"oficinas_{ts}.csv")
        con_csv = os.path.join(self.out_dir, f"contactos_{ts}.csv")
        per_csv = os.path.join(self.out_dir, f"personas_{ts}.csv")
        doc_csv = os.path.join(self.out_dir, f"documentos_{ts}.csv")
        dec_csv = os.path.join(self.out_dir, f"decodificados_{ts}.csv")
        json_path = os.path.join(self.out_dir, f"ing_leads_{ts}.json")
        txt_path = os.path.join(self.out_dir, f"resumen_{ts}.txt")

        # --- SQLite ---
        con = sqlite3.connect(db_path)
        cur = con.cursor()
        cur.executescript("""
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS oficinas(
            id INTEGER PRIMARY KEY, url TEXT UNIQUE, nombre TEXT, tipo TEXT,
            provincia TEXT, direccion TEXT, cp TEXT, ciudad TEXT,
            telefono TEXT, horario TEXT);
        CREATE TABLE IF NOT EXISTS contactos(
            id INTEGER PRIMARY KEY, contacto TEXT UNIQUE, tipo TEXT, fuente TEXT);
        CREATE TABLE IF NOT EXISTS personas(
            id INTEGER PRIMARY KEY, persona TEXT, fuente TEXT,
            UNIQUE(persona, fuente));
        CREATE TABLE IF NOT EXISTS documentos(
            id INTEGER PRIMARY KEY, documento TEXT, tipo TEXT, fuente TEXT,
            UNIQUE(documento, tipo, fuente));
        CREATE TABLE IF NOT EXISTS decodificados(
            id INTEGER PRIMARY KEY, url TEXT, tipo TEXT, original TEXT, decodificado TEXT);
        CREATE TABLE IF NOT EXISTS campos_json(
            id INTEGER PRIMARY KEY, url TEXT, campo TEXT, valor TEXT);
        CREATE TABLE IF NOT EXISTS paginas(
            id INTEGER PRIMARY KEY, url TEXT UNIQUE, tipo TEXT, dominio TEXT);
        """)
        cur.executemany(
            "INSERT OR IGNORE INTO oficinas(url,nombre,tipo,provincia,direccion,cp,ciudad,telefono,horario)"
            " VALUES(?,?,?,?,?,?,?,?,?)",
            [(o["url"], o["nombre"], o["tipo"], o["provincia"], o["direccion"],
              o["cp"], o["ciudad"], o["telefono"], o["horario"]) for o in self.oficinas])
        cur.executemany("INSERT OR IGNORE INTO contactos(contacto,tipo,fuente) VALUES(?,?,?)",
                        [(c, m["tipo"], m["fuente"]) for c, m in self.contactos.items()])
        cur.executemany("INSERT OR IGNORE INTO personas(persona,fuente) VALUES(?,?)",
                        [(p["persona"], p["fuente"]) for p in self.personas])
        cur.executemany("INSERT OR IGNORE INTO documentos(documento,tipo,fuente) VALUES(?,?,?)",
                        [(d["documento"], d["tipo"], d["fuente"]) for d in self.documentos])
        cur.executemany("INSERT INTO decodificados(url,tipo,original,decodificado) VALUES(?,?,?,?)",
                        [(d["url"], d["tipo"], d["original"], d["decodificado"]) for d in self.decoded])
        cur.executemany("INSERT INTO campos_json(url,campo,valor) VALUES(?,?,?)",
                        [(j["url"], j["campo"], j["valor"]) for j in self.json_fields])
        cur.executemany("INSERT OR IGNORE INTO paginas(url,tipo,dominio) VALUES(?,?,?)",
                        [(p["url"], p["tipo"], p["dominio"]) for p in self.pages])
        con.commit()
        con.close()

        # --- CSV ---
        def dump(path: str, rows: List[Dict[str, Any]], fields: List[str]):
            with open(path, "w", newline="", encoding="utf-8") as fp:
                w = csv.DictWriter(fp, fieldnames=fields, extrasaction="ignore")
                w.writeheader()
                for r in rows:
                    w.writerow(r)

        dump(ofi_csv, self.oficinas,
             ["nombre", "tipo", "provincia", "direccion", "cp", "ciudad", "telefono", "horario", "url"])
        dump(con_csv, [{"contacto": c, **m} for c, m in self.contactos.items()],
             ["contacto", "tipo", "fuente"])
        dump(per_csv, self.personas, ["persona", "fuente"])
        dump(doc_csv, self.documentos, ["documento", "tipo", "fuente"])
        dump(dec_csv, self.decoded, ["url", "tipo", "original", "decodificado"])

        with open(json_path, "w", encoding="utf-8") as fp:
            json.dump({
                "generado": datetime.datetime.now().isoformat(),
                "oficinas": self.oficinas,
                "contactos": [{"contacto": c, **m} for c, m in self.contactos.items()],
                "personas": self.personas[:5000],
                "documentos": self.documentos[:5000],
                "decodificados": self.decoded[:2000],
            }, fp, ensure_ascii=False, indent=2)

        emails = sorted(c for c, m in self.contactos.items() if m["tipo"] == "email")
        phones = sorted(c[4:] for c, m in self.contactos.items() if m["tipo"] == "telefono")
        socials = sorted(c for c, m in self.contactos.items() if m["tipo"] == "red")
        dni_ok = sorted({d["documento"] for d in self.documentos if d["tipo"] == "DNI/NIE"})
        cif_ok = sorted({d["documento"] for d in self.documentos if d["tipo"] == "CIF"})
        iban_ok = sorted({d["documento"] for d in self.documentos if d["tipo"] == "IBAN"})
        dec_tipos: Dict[str, int] = {}
        for d in self.decoded:
            dec_tipos[d["tipo"].split(":")[0]] = dec_tipos.get(d["tipo"].split(":")[0], 0) + 1

        with open(txt_path, "w", encoding="utf-8") as fp:
            fp.write("=" * 68 + "\n ING MAX SCRAPER — INFORME\n")
            fp.write(f" Fecha: {datetime.datetime.now():%Y-%m-%d %H:%M:%S}\n")
            fp.write(f" Páginas analizadas: {len(self.pages)}\n")
            fp.write(f" Oficinas/cajeros: {len(self.oficinas)}\n")
            fp.write(f" Contactos únicos: {len(self.contactos)}\n")
            fp.write(f" Personas detectadas: {len(self.personas)}\n")
            fp.write(f" DNI/NIE válidos: {len(dni_ok)}\n")
            fp.write(f" CIF válidos: {len(cif_ok)}\n")
            fp.write(f" IBAN válidos: {len(iban_ok)}\n")
            fp.write(f" Blobs decodificados: {len(self.decoded)} {dec_tipos}\n")
            fp.write("=" * 68 + "\n\n")
            fp.write("--- OFICINAS / CAJEROS ---\n")
            for o in self.oficinas:
                fp.write(f"  {o['tipo'].upper():8} {o['nombre']} | {o['direccion']} "
                         f"{o['cp']} {o['ciudad']} ({o['provincia']}) | tel: {o['telefono']}\n")
            fp.write("\n--- EMAILS ---\n" + "\n".join(emails))
            fp.write("\n\n--- TELÉFONOS ---\n" + "\n".join(phones))
            fp.write("\n\n--- REDES ---\n" + "\n".join(socials))
            fp.write("\n\n--- DNI/NIE VÁLIDOS ---\n" + "\n".join(dni_ok))
            fp.write("\n\n--- CIF VÁLIDOS ---\n" + "\n".join(cif_ok))
            fp.write("\n\n--- IBAN VÁLIDOS ---\n" + "\n".join(iban_ok))

        self.log(f"\n[✓] {len(self.oficinas)} oficinas · {len(emails)} emails · "
                 f"{len(phones)} teléfonos · {len(self.decoded)} blobs decodificados")
        self.log(f"[✓] SQLite: {db_path}")
        return {"db": db_path, "oficinas": ofi_csv, "contactos": con_csv,
                "personas": per_csv, "documentos": doc_csv,
                "decodificados": dec_csv, "json": json_path, "resumen": txt_path}

    # -- runner ------------------------------------------------------------
    def run(self) -> Dict[str, Any]:
        self.log("\n" + "=" * 68)
        self.log(" ING MAX SCRAPER — arrancando")
        self.log("=" * 68)
        self.phase0_warmup()
        urls = self.phase1_sitemaps()
        self.phase2_aem()
        self.phase3_crawl(urls)
        self.phase45_process()
        files = self.save()
        return {
            "paginas": len(self.pages),
            "oficinas": self.oficinas,
            "contactos": self.contactos,
            "personas": self.personas,
            "documentos": self.documentos,
            "decodificados": self.decoded,
            "files": files,
        }


# ---------------------------------------------------------------------------
# MODO LOGIN — Área de Clientes ING (opcional, Playwright)
# ---------------------------------------------------------------------------
def login_area_clientes(
    dni: str,
    fecha_nacimiento: str,
    clave: Optional[str] = None,
    out_dir: str = DEFAULT_OUT_DIR,
    headless: bool = False,
) -> Optional[str]:
    """
    Entra en el Área de Clientes de ING y captura TODAS las respuestas JSON
    de la sesión (posiciones, cuentas, titular, etc.).

    ING pide: DNI/NIE + fecha de nacimiento + clave de acceso (+ OTP).
    Si no pasas clave, se te pedirá por consola.

    Requiere: pip install playwright && playwright install chromium
    """
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except ImportError:
        print("[!] Playwright no instalado: pip install playwright && playwright install chromium")
        return None

    os.makedirs(out_dir, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    dump_path = os.path.join(out_dir, f"area_clientes_{ts}.json")
    capturados: List[Dict[str, Any]] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=headless)
        ctx = browser.new_context(
            user_agent=random.choice(USER_AGENTS),
            locale="es-ES", viewport={"width": 1440, "height": 900},
        )
        page = ctx.new_page()

        def on_response(resp):
            try:
                ctype = resp.headers.get("content-type", "")
                if "json" in ctype and "ing" in resp.url:
                    capturados.append({"url": resp.url, "json": resp.json()})
            except Exception:
                pass

        page.on("response", on_response)
        page.goto("https://www.ing.es/hippogenoma/navigation/26",
                  wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(4000)

        def fill_first(patterns: List[str], value: str) -> bool:
            for pat in patterns:
                try:
                    loc = page.locator(
                        f"input[name*='{pat}' i], input[id*='{pat}' i], "
                        f"input[placeholder*='{pat}' i]"
                    ).first
                    if loc.count() > 0 and loc.is_visible():
                        loc.fill(value)
                        return True
                except Exception:
                    continue
            return False

        fill_first(["nif", "dni", "documento", "usuario", "user"], dni)
        fill_first(["fecha", "nacimiento", "birth", "date"], fecha_nacimiento)
        if clave:
            try:
                pw_input = page.locator("input[type='password']").first
                if pw_input.count() > 0:
                    pw_input.fill(clave)
            except Exception:
                pass

        if not headless:
            print("[·] Revisa el navegador: acepta cookies, completa la clave/OTP "
                  "y pulsa Enter cuando estés dentro del Área de Clientes.")
            input()

        page.wait_for_timeout(5000)
        # navegar a posiciones y cuentas para forzar sus XHR
        for path in ("/hippogenoma/navigation/26", ):
            try:
                page.goto(f"https://www.ing.es{path}", wait_until="networkidle", timeout=40000)
                page.wait_for_timeout(4000)
            except Exception:
                pass

        with open(dump_path, "w", encoding="utf-8") as fp:
            json.dump(capturados, fp, ensure_ascii=False, indent=2)

        # extraer campos útiles de todo lo capturado
        campos: List[Dict[str, str]] = []
        for cap in capturados:
            for path, val in walk_json(cap["json"]):
                campos.append({"url": cap["url"], "campo": path, "valor": val})
        campos_path = os.path.join(out_dir, f"area_clientes_campos_{ts}.csv")
        with open(campos_path, "w", newline="", encoding="utf-8") as fp:
            w = csv.DictWriter(fp, fieldnames=["url", "campo", "valor"])
            w.writeheader()
            w.writerows(campos)

        browser.close()

    print(f"[✓] {len(capturados)} respuestas JSON capturadas -> {dump_path}")
    print(f"[✓] {len(campos)} campos -> {campos_path}")
    return dump_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(
        description="ING MAX SCRAPER — recon, decodificación y leads de ing.es",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    ap.add_argument("--out-dir", default=DEFAULT_OUT_DIR)
    ap.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    ap.add_argument("--delay", type=float, default=DEFAULT_DELAY)
    ap.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    ap.add_argument("--limit", type=int, default=None, help="Limitar nº de URLs del sitemap")
    ap.add_argument("--max-pages", type=int, default=4000)
    ap.add_argument("--no-subdomains", action="store_true")
    ap.add_argument("--no-aem", action="store_true")
    ap.add_argument("--no-verify", action="store_true")
    ap.add_argument("--proxy", default=None)
    ap.add_argument("--login", action="store_true", help="Modo Área de Clientes")
    ap.add_argument("--dni", default=None)
    ap.add_argument("--fecha", default=None, help="Fecha de nacimiento DD/MM/AAAA")
    ap.add_argument("--clave", default=None)
    ap.add_argument("--headless", action="store_true")

    args = ap.parse_args()

    if args.login:
        if not args.dni or not args.fecha:
            print("[!] El modo --login requiere --dni y --fecha (DD/MM/AAAA)")
            sys.exit(1)
        login_area_clientes(args.dni, args.fecha, args.clave,
                            args.out_dir, args.headless)
        return

    sc = IngScraper(
        out_dir=args.out_dir, delay=args.delay, timeout=args.timeout,
        workers=args.workers, verify_ssl=not args.no_verify, proxy=args.proxy,
        use_subdomains=not args.no_subdomains, use_aem=not args.no_aem,
        limit=args.limit, max_pages=args.max_pages,
    )
    res = sc.run()
    print("\n--- RESUMEN ---")
    print(f"Páginas:      {res['paginas']}")
    print(f"Oficinas:     {len(res['oficinas'])}")
    print(f"Contactos:    {len(res['contactos'])}")
    print(f"Personas:     {len(res['personas'])}")
    print(f"Documentos:   {len(res['documentos'])}")
    print(f"Decodificados:{len(res['decodificados'])}")
    print(f"Archivos:     {res['files']}")


if __name__ == "__main__":
    main()