# 🤖 BOT DE TELEGRAM - AUTOFILL CHECKER (EDGE)

Sistema automatizado de chequeo de pasarelas de pago y formularios web mediante **Selenium Edge WebDriver**, controlado de forma 100% interactiva a través de un **Bot de Telegram** con interfaz visual en modo consola robótica, negrita monoespaciada y soporte de proxies rotativos/residenciales de **DataImpulse**.

---

## ⚡ Características Principales

1. **Chequeo Masivo de Tarjetas (+100 tarjetas)**
   - Sin restricciones de tamaño: permite chequear lotes grandes de tarjetas secuencialmente de forma desatendida.
   - Detecta automáticamente el estado del pago evaluando redirecciones (`Redireccionando...`), denegaciones y errores.

2. **Acciones Rápidas al Detectar una VÁLIDA**
   - Cuando una tarjeta es válida, el bot detiene el lote y envía el enlace de redirección capturado junto a dos botones interactivos:
     - 🌐 **Nueva URL:** Permite ingresar de inmediato un nuevo enlace de pago.
     - ⚡ **Generar:** Extrae los **primeros 10 caracteres** de la tarjeta válida y genera **30 tarjetas aleatorias** basadas en ese mismo BIN.

3. **Generador Integrado de Tarjetas (`/gen`)**
   - Permite generar tandas de 30 tarjetas a partir de cualquier prefijo de 10 dígitos.
   - Incorpora validación matemática con el **Algoritmo de Luhn** (Módulo 10) para el 16º dígito de control.
   - Formato estándar listo para copiar con un solo toque: `NUMERO|MM|AA|CVV`.

4. **Exportación de Válidas en TXT (`/valid`)**
   - Descarga directa en Telegram del archivo `validas.txt` con todas las tarjetas válidas acumuladas.
   - Persistencia automática en disco y aislamiento de datos por usuario.

5. **Soporte de Proxies DataImpulse y HTTP**
   - Integración nativa de proxies con autenticación de usuario y contraseña en Selenium Edge.
   - Admite pegar directamente el comando `curl -x` de DataImpulse o formato estándar `usuario:password@host:port`.
   - Botón directo **🛡️ Proxies** disponible desde el menú de inicio `/start`.

6. **Estética Robótica y Modo Independiente**
   - Todos los mensajes están diseñados con **tipografía monoespaciada robótica** y **negrita** (`<b><code>...</code></b>`), organizados en marcos limpios.
   - Cada usuario de Telegram dispone de su propia URL y configuración de proxy independiente en `user_data.json`.

---

## 📋 Lista de Comandos de Telegram

| Comando | Descripción |
| :--- | :--- |
| **`/start`** | Mensaje de bienvenida, guía de comandos y botón interactivo para **Configurar Proxies**. |
| **`/chk`** | Inicia el asistente interactivo para enviar tarjetas y comenzar el chequeo. |
| **`/chk <tarjetas>`** | Inicia el chequeo directamente pasando las tarjetas en el mismo mensaje. |
| **`/gen <10_dígitos>`** | Genera 30 tarjetas aleatorias con algoritmo de Luhn verificado a partir de los 10 dígitos. |
| **`/gen`** | Asistente interactivo que solicita los 10 dígitos base para generar 30 tarjetas. |
| **`/valid`** | Envía un documento descargable `validas.txt` con todas las tarjetas válidas registradas. |
| **`/proxy`** | Muestra el proxy actual o abre el asistente para configurarlo / eliminarlo. |
| **`/proxy <cadena>`** | Configura directamente el proxy pasando el enlace o comando curl. |
| **`/url <nueva_url>`** | Guarda o actualiza tu enlace de pago personal para futuros chequeos. |
| **`/url`** | Muestra la URL de pago actualmente configurada en tu usuario. |
| **`/stop`** | Detiene de inmediato el proceso de chequeo en curso y cierra el navegador. |

---

## 🛡️ Configuración de Proxies (DataImpulse)

Puedes configurar tu proxy de tres formas sencillas:

1. Pulsando el botón **`🛡️ Proxies`** que aparece al enviar **`/start`**.
2. Escribiendo **`/proxy`** y enviando la dirección que te indique el bot.
3. Escribiendo **`/proxy <tu_proxy>`** directamente.

### Formatos Admitidos

El analizador inteligente procesa automáticamente cualquiera de las siguientes estructuras:

* **Comando curl directo de DataImpulse:**
  ```bash
  curl -x http://9a6dc7641e60bd9ad507:242b4b6ca788f743@gw.dataimpulse.com:823
  ```
* **Formato URL:**
  ```text
  http://9a6dc7641e60bd9ad507:242b4b6ca788f743@gw.dataimpulse.com:823
  ```
* **Formato IP:PUERTO:USUARIO:PASSWORD:**
  ```text
  gw.dataimpulse.com:823:9a6dc7641e60bd9ad507:242b4b6ca788f743
  ```

---

## 🚀 Instalación y Puesta en Marcha

### Requisitos Previos

- **Windows 10 / 11** con **Microsoft Edge** instalado.
- **Python 3.10+** (incluye `pip`).

### Dependencias

Instala los módulos necesarios:
```bash
pip install python-telegram-bot selenium
```

### Iniciar el Bot

Puedes arrancar el bot de dos maneras:

1. **Haciendo doble clic** en el archivo:
   ```text
   INICIAR_BOT_TELEGRAM.bat
   ```
2. **O desde la terminal:**
   ```bash
   python telegram_bot.py
   ```

---

## 📁 Estructura del Proyecto

```text
vinted metodo/
├── INICIAR_BOT_TELEGRAM.bat   # Script rápido para iniciar el bot en Windows
├── telegram_bot.py           # Código fuente principal del bot de Telegram y Selenium
├── autofill.py               # Motor alternativo para ejecución en consola local
├── user_data.json            # Base de datos local (URLs y proxies aislados por usuario)
├── validas.txt               # Registro histórico de tarjetas válidas encontradas
├── a.txt                     # Archivo de tarjetas por defecto
├── debug.log                 # Registro de eventos y depuración en tiempo real
└── README.md                 # Esta documentación
```

---

## ⚙️ Formato de Tarjetas Admitido

El bot detecta tarjetas en cualquiera de los formatos estándar:
```text
4150070033612022|03|29|458
4150070033612022/03/2029/458
4150070033612022 03 29 458
41500700336120220329458
```
Cada línea contiene:
- **16 dígitos:** Número de tarjeta de crédito/débito.
- **4 dígitos:** Fecha de vencimiento (`MMAA` o `MM/AA`).
- **3 dígitos:** Código de seguridad CVV/CVC.
