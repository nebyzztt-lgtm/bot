#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Recon & Leads Scraper Module
Multi-phase web reconnaissance and contact lead extraction.
Supports CLI, environment variables, requests session with retries,
Playwright with silent fallback, query string urlencoding, and response caching.
"""

import os
import re
import sys
import time
import json
import csv
import argparse
import datetime
from urllib.parse import urljoin, urlsplit, urlunsplit, urlencode
from typing import Dict, List, Optional, Set, Any, Callable

import requests
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter
from bs4 import BeautifulSoup

# Habilitar soporte de colores ANSI y UTF-8 en Windows
os.system('')
try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

# Configuración por defecto
DEFAULT_BASE = os.getenv("BASE_URL", "https://example.com")
DEFAULT_OUT_DIR = os.getenv("OUT_DIR", "scraper_results")
DEFAULT_DELAY = float(os.getenv("SCRAPER_DELAY", "0.35"))
DEFAULT_TIMEOUT = int(os.getenv("SCRAPER_TIMEOUT", "12"))
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# Rutas estándar de descubrimiento de endpoints, sitemaps y páginas de contacto
SCAN_PATHS = [
    "/robots.txt",
    "/sitemap.xml",
    "/sitemap_index.xml",
    "/feed",
    "/rss",
    "/api",
    "/api/v1",
    "/api/v2",
    "/v1",
    "/v2",
    "/rest",
    "/wp-json/",
    "/swagger.json",
    "/openapi.json",
    "/api-docs",
    "/graphql",
    "/users",
    "/clients",
    "/clientes",
    "/directory",
    "/directorio",
    "/listado",
    "/partners",
    "/team",
    "/equipo",
    "/contacto",
    "/contact",
    "/contact-us",
    "/about",
    "/about-us",
]

# Rutas para paginación limpia en fase 3
PAGINATION_ENDPOINTS = [
    "/api/v1/users",
    "/api/users",
    "/api/clients",
    "/api/v1/clients",
    "/users",
    "/clientes",
    "/directory",
    "/listado",
]

PAGINATION_PARAMS = [
    {"page": "1"},
    {"limit": "100"},
    {"offset": "0"},
    {"search": "a"},
    {"filter": "all"},
]

# Expresiones regulares para extracción
EMAIL_RE = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
PHONE_RE = re.compile(r"(?:\+?\d{1,3}[\s.-]?)?(?:\(?\d{2,4}\)?[\s.-]?)?\d{3,4}[\s.-]?\d{3,4}")
SOCIAL_RE = re.compile(
    r"https?://(?:wa\.me|api\.whatsapp\.com|t\.me|telegram\.me|instagram\.com|twitter\.com|x\.com|linkedin\.com/company|linkedin\.com/in|facebook\.com)/[a-zA-Z0-9_.-]+"
)
API_HINT_RE = re.compile(r"""["'](/(?:api|v\d|rest|graphql|json)[^"']*)["']""", re.IGNORECASE)


class ReconScraper:
    def __init__(
        self,
        base_url: str,
        out_dir: str = DEFAULT_OUT_DIR,
        delay: float = DEFAULT_DELAY,
        timeout: int = DEFAULT_TIMEOUT,
        verify_ssl: bool = True,
        proxy: Optional[str] = None,
        status_callback: Optional[Callable[[str], None]] = None,
    ):
        clean_url = base_url.strip()
        if not clean_url.startswith(("http://", "https://")):
            clean_url = "https://" + clean_url
        self.base_url = clean_url.rstrip("/")

        self.out_dir = out_dir
        self.delay = delay
        self.timeout = timeout
        self.verify_ssl = verify_ssl
        self.proxy = proxy
        self.status_callback = status_callback

        self.seen_urls: Set[str] = set()
        self.found: List[Dict[str, Any]] = []
        self.leads: List[Dict[str, Any]] = []

        # Crear sesión con reintentos configurados
        self.session = requests.Session()
        retries = Retry(
            total=3,
            backoff_factor=0.5,
            status_forcelist=[429, 500, 502, 503, 504],
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retries)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        self.session.headers.update({"User-Agent": DEFAULT_USER_AGENT})

        if self.proxy:
            self.session.proxies.update({
                "http": self.proxy,
                "https": self.proxy,
            })

    def log(self, message: str):
        try:
            print(message)
        except Exception:
            try:
                print(message.encode("ascii", errors="replace").decode("ascii"))
            except Exception:
                pass
        if self.status_callback:
            try:
                self.status_callback(message)
            except Exception:
                pass


    def fetch(self, url: str) -> Optional[requests.Response]:
        """Realiza una petición HTTP segura con retries, timeout y verificación SSL."""
        try:
            return self.session.get(
                url,
                timeout=self.timeout,
                verify=self.verify_ssl,
                allow_redirects=True,
            )
        except Exception as e:
            return None

    def phase1_scan(self):
        """FASE 1: Escaneo de rutas predefinidas y endpoints comunes."""
        self.log(f"[*] FASE 1 — Escaneando {len(SCAN_PATHS)} rutas de descubrimiento...")
        for path in SCAN_PATHS:
            target_url = urljoin(self.base_url + "/", path.lstrip("/"))
            if target_url in self.seen_urls:
                continue
            self.seen_urls.add(target_url)

            resp = self.fetch(target_url)
            if resp and resp.status_code in [200, 201, 206] and len(resp.text) > 0:
                ctype = resp.headers.get("content-type", "").lower()
                tag = "[API]" if "json" in ctype or "xml" in ctype else "[PAGE]"
                self.log(f"  [+] {resp.status_code} {target_url} ({len(resp.text)}B) {tag}")
                self.found.append({
                    "url": target_url,
                    "status": resp.status_code,
                    "tipo": tag,
                    "ctype": ctype,
                    "content": resp.text,  # Guardado para reuso en fase 4
                })
            time.sleep(self.delay)

    def phase2_js_apis(self):
        """FASE 2: Búsqueda de endpoints y APIs en JavaScript (Playwright opcional + parser HTML/JS)."""
        self.log("[*] FASE 2 — Buscando endpoints de APIs y scripts JavaScript...")
        captured_apis = set()

        # 1. Intento con Playwright si está instalado (fallback silencioso)
        playwright_ejecutado = False
        try:
            from playwright.sync_api import sync_playwright  # type: ignore
            self.log("  [+] Playwright detectado, capturando tráfico de red...")
            with sync_playwright() as pw:
                launch_kwargs = {"headless": True}
                if self.proxy:
                    launch_kwargs["proxy"] = {"server": self.proxy}
                browser = pw.chromium.launch(**launch_kwargs)
                page = browser.new_page(user_agent=DEFAULT_USER_AGENT)
                network_urls = []
                page.on("response", lambda r: network_urls.append(r.url))
                try:
                    page.goto(self.base_url, wait_until="networkidle", timeout=20000)
                    time.sleep(1.5)
                except Exception:
                    pass
                finally:
                    browser.close()

                for u in network_urls:
                    if re.search(r"/(api|graphql|rest|json|v\d)", u, re.IGNORECASE):
                        captured_apis.add(u)
                playwright_ejecutado = True
        except ImportError:
            # Fallback silencioso requerido por el usuario
            self.log("  [i] Playwright no instalado (fallback a análisis estático de scripts)")
        except Exception as e:
            self.log(f"  [!] Fallback en Playwright: {e}")

        # 2. Análisis estático de la página principal y scripts vinculados
        try:
            resp_home = self.fetch(self.base_url)
            if resp_home and resp_home.status_code == 200:
                html_text = resp_home.text
                if self.base_url not in self.seen_urls:
                    self.seen_urls.add(self.base_url)
                    self.found.append({
                        "url": self.base_url,
                        "status": 200,
                        "tipo": "[HOME]",
                        "ctype": resp_home.headers.get("content-type", ""),
                        "content": html_text,
                    })

                # Extraer llamadas API con regex en código HTML/inline JS
                for match in API_HINT_RE.findall(html_text):
                    api_full = urljoin(self.base_url + "/", match.lstrip("/"))
                    captured_apis.add(api_full)

                # Inspeccionar <script src="...">
                soup = BeautifulSoup(html_text, "html.parser")
                script_tags = soup.find_all("script", src=True)
                for tag in script_tags[:5]:  # Analizar hasta 5 scripts principales
                    src = tag.get("src", "")
                    js_url = urljoin(self.base_url + "/", src.lstrip("/"))
                    if js_url not in self.seen_urls:
                        self.seen_urls.add(js_url)
                        js_resp = self.fetch(js_url)
                        if js_resp and js_resp.status_code == 200:
                            for match in API_HINT_RE.findall(js_resp.text):
                                api_full = urljoin(self.base_url + "/", match.lstrip("/"))
                                captured_apis.add(api_full)
                        time.sleep(self.delay)
        except Exception as e:
            self.log(f"  [!] Error analizando scripts: {e}")

        # Guardar APIs encontradas deduplicadas
        for api_url in captured_apis:
            if api_url not in self.seen_urls:
                self.seen_urls.add(api_url)
                self.log(f"  [+] API detectada en JS: {api_url}")
                self.found.append({
                    "url": api_url,
                    "status": 200,
                    "tipo": "[JS-API]",
                    "ctype": "api-detected",
                    "content": None,
                })

    def phase3_paginate(self):
        """FASE 3: Paginación y filtros limpios usando urlencode y urlsplit."""
        self.log("[*] FASE 3 — Probando paginación estructurada con urlencode...")
        for base_path in PAGINATION_ENDPOINTS:
            for params in PAGINATION_PARAMS:
                raw_target = urljoin(self.base_url + "/", base_path.lstrip("/"))
                parts = urlsplit(raw_target)
                query_string = urlencode(params)
                clean_target = urlunsplit((parts.scheme, parts.netloc, parts.path, query_string, ""))

                if clean_target in self.seen_urls:
                    continue
                self.seen_urls.add(clean_target)

                resp = self.fetch(clean_target)
                if resp and resp.status_code == 200 and len(resp.text) > 0:
                    ctype = resp.headers.get("content-type", "").lower()
                    if "json" in ctype or "xml" in ctype:
                        self.log(f"  [+] Paginación OK: {clean_target}")
                        self.found.append({
                            "url": clean_target,
                            "status": 200,
                            "tipo": "[PAGINATE]",
                            "ctype": ctype,
                            "content": resp.text,
                        })
                time.sleep(self.delay)

    def phase4_extract(self):
        """FASE 4: Extracción de leads reutilizando el contenido cacheado de found."""
        self.log(f"[*] FASE 4 — Extrayendo leads de {len(self.found)} endpoints (reusando respuestas)...")
        seen_leads_tuples = set()

        for item in self.found:
            url = item["url"]
            text_body = item.get("content")

            # Solo si no se guardó previamente, se descarga (evita baneos)
            if text_body is None:
                resp = self.fetch(url)
                if not resp or resp.status_code != 200:
                    continue
                text_body = resp.text
                item["content"] = text_body
                time.sleep(self.delay)

            # Si es JSON, volcar como texto legible
            if "json" in item.get("ctype", "").lower():
                try:
                    data = json.loads(text_body)
                    text_body = json.dumps(data, ensure_ascii=False)
                except Exception:
                    pass

            # Extraer Emails
            extracted_emails = set(EMAIL_RE.findall(text_body))
            # Filtrar falsos positivos en imágenes o assets
            valid_emails = {
                e for e in extracted_emails
                if not e.endswith((".png", ".jpg", ".jpeg", ".svg", ".webp", ".gif"))
            }

            # Extraer Teléfonos
            extracted_phones = set()
            for cand in PHONE_RE.findall(text_body):
                digits = re.sub(r"\D", "", cand)
                if 9 <= len(digits) <= 15:
                    extracted_phones.add(cand.strip())

            # Extraer Enlaces de Redes Sociales y Mensajería
            extracted_social = set(SOCIAL_RE.findall(text_body))

            if valid_emails or extracted_phones or extracted_social:
                lead_key = (
                    tuple(sorted(list(valid_emails))),
                    tuple(sorted(list(extracted_phones))),
                    tuple(sorted(list(extracted_social))),
                )
                if lead_key not in seen_leads_tuples:
                    seen_leads_tuples.add(lead_key)
                    self.leads.append({
                        "fuente": url,
                        "tipo": item.get("tipo", "[N/A]"),
                        "emails": "; ".join(sorted(valid_emails)),
                        "telefonos": "; ".join(sorted(extracted_phones)),
                        "redes": "; ".join(sorted(extracted_social)),
                    })

    def save_results(self) -> Dict[str, str]:
        """Guarda los resultados con timestamp en la carpeta configurada (OUT_DIR)."""
        os.makedirs(self.out_dir, exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

        endpoints_path = os.path.join(self.out_dir, f"endpoints_{timestamp}.csv")
        leads_path = os.path.join(self.out_dir, f"leads_{timestamp}.csv")
        summary_path = os.path.join(self.out_dir, f"resumen_{timestamp}.txt")

        # 1. Guardar Endpoints CSV
        with open(endpoints_path, "w", newline="", encoding="utf-8") as fp:
            writer = csv.DictWriter(fp, fieldnames=["url", "status", "tipo", "ctype"])
            writer.writeheader()
            for f in self.found:
                writer.writerow({
                    "url": f["url"],
                    "status": f.get("status", 200),
                    "tipo": f.get("tipo", ""),
                    "ctype": f.get("ctype", ""),
                })

        # 2. Guardar Leads CSV
        with open(leads_path, "w", newline="", encoding="utf-8") as fp:
            writer = csv.DictWriter(fp, fieldnames=["fuente", "tipo", "emails", "telefonos", "redes"])
            writer.writeheader()
            for lead in self.leads:
                writer.writerow(lead)

        # 3. Guardar Resumen TXT
        total_emails = set()
        total_phones = set()
        total_social = set()
        for l in self.leads:
            if l.get("emails"):
                for em in l["emails"].split("; "):
                    if em:
                        total_emails.add(em)
            if l.get("telefonos"):
                for ph in l["telefonos"].split("; "):
                    if ph:
                        total_phones.add(ph)
            if l.get("redes"):
                for so in l["redes"].split("; "):
                    if so:
                        total_social.add(so)

        with open(summary_path, "w", encoding="utf-8") as fp:
            fp.write("============================================================\n")
            fp.write(" REPORTE COMPLETO DE RECONOCIMIENTO Y LEADS\n")
            fp.write(f" URL Base: {self.base_url}\n")
            fp.write(f" Fecha: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            fp.write(f" Total Endpoints Encontrados: {len(self.found)}\n")
            fp.write(f" Total Leads Extraídos: {len(self.leads)}\n")
            fp.write(f" Emails Únicos: {len(total_emails)}\n")
            fp.write(f" Teléfonos Únicos: {len(total_phones)}\n")
            fp.write(f" Redes Únicas: {len(total_social)}\n")
            fp.write("============================================================\n\n")

            fp.write("--- CORREOS ELECTRÓNICOS ---\n")
            for em in sorted(total_emails):
                fp.write(f"{em}\n")
            fp.write("\n--- TELÉFONOS ---\n")
            for ph in sorted(total_phones):
                fp.write(f"{ph}\n")
            fp.write("\n--- REDES SOCIALES / MENSAJERÍA ---\n")
            for so in sorted(total_social):
                fp.write(f"{so}\n")

        self.log(f"\n[✓] {len(self.found)} endpoints | {len(self.leads)} leads guardados en '{self.out_dir}'")
        return {
            "endpoints_csv": endpoints_path,
            "leads_csv": leads_path,
            "summary_txt": summary_path,
        }

    def run(self) -> Dict[str, Any]:
        """Ejecuta secuencialmente todas las fases del reconocimiento."""
        self.seen_urls.clear()
        self.found.clear()
        self.leads.clear()

        self.log(f"\n🚀 Iniciando reconocimiento en: {self.base_url}")
        self.phase1_scan()
        self.phase2_js_apis()
        self.phase3_paginate()
        self.phase4_extract()
        files = self.save_results()

        # Resumen consolidado para integración
        all_emails = set()
        all_phones = set()
        all_social = set()
        for lead in self.leads:
            if lead.get("emails"):
                all_emails.update([x.strip() for x in lead["emails"].split("; ") if x.strip()])
            if lead.get("telefonos"):
                all_phones.update([x.strip() for x in lead["telefonos"].split("; ") if x.strip()])
            if lead.get("redes"):
                all_social.update([x.strip() for x in lead["redes"].split("; ") if x.strip()])

        return {
            "base_url": self.base_url,
            "endpoints": self.found,
            "leads": self.leads,
            "files": files,
            "emails": sorted(list(all_emails)),
            "phones": sorted(list(all_phones)),
            "social": sorted(list(all_social)),
            "total_endpoints": len(self.found),
            "total_leads": len(self.leads),
        }


def run_scraper(
    target_url: str,
    out_dir: str = DEFAULT_OUT_DIR,
    delay: float = DEFAULT_DELAY,
    verify_ssl: bool = True,
    proxy: Optional[str] = None,
    status_callback: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    """Función de entrada para ser invocada directamente desde el Bot de Telegram."""
    scraper = ReconScraper(
        base_url=target_url,
        out_dir=out_dir,
        delay=delay,
        verify_ssl=verify_ssl,
        proxy=proxy,
        status_callback=status_callback,
    )
    return scraper.run()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Recon & Leads Web Scraper - Reconocimiento multipaso y extracción de contactos"
    )
    parser.add_argument(
        "url",
        nargs="?",
        default=None,
        help="URL objetivo a escanear (ejemplo: https://tuweb.com). Si no se proporciona, lee de la variable BASE_URL.",
    )
    parser.add_argument(
        "--out-dir",
        default=DEFAULT_OUT_DIR,
        help=f"Directorio de salida para los archivos CSV y TXT (por defecto: {DEFAULT_OUT_DIR})",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=DEFAULT_DELAY,
        help=f"Retardo en segundos entre peticiones (por defecto: {DEFAULT_DELAY})",
    )
    parser.add_argument(
        "--no-verify",
        action="store_true",
        help="Desactiva la verificación de certificados SSL",
    )
    parser.add_argument(
        "--proxy",
        default=None,
        help="Proxy a utilizar (ejemplo: http://usuario:pass@ip:puerto)",
    )

    args = parser.parse_args()

    # Fallback automático: CLI -> Variable de entorno BASE_URL -> Prompt o error
    target_url = args.url or os.getenv("BASE_URL")
    if not target_url:
        print("[!] No se ha especificado ninguna URL.")
        print("    Uso: python scraper.py https://tuweb.com")
        print("    O define la variable de entorno: set BASE_URL=https://tuweb.com")
        sys.exit(1)

    scraper = ReconScraper(
        base_url=target_url,
        out_dir=args.out_dir,
        delay=args.delay,
        verify_ssl=not args.no_verify,
        proxy=args.proxy,
    )
    scraper.run()
