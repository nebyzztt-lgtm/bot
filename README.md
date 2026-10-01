# 🤖 Bot de Cargas para Telegram (@cargasespanabot)

Bot diseñado para registrar notificaciones de cargas, calcular automáticamente el importe total acumulado, calcular porcentajes sobre el total (`/pc`), y vincular automáticamente los datos de pago (Teléfono Bizum, Nombre completo, IBAN y detección automática de Banco).

---

## 🚀 Cómo ponerlo en marcha

Para iniciar el bot:
1. Haz doble clic en **`iniciar_bot.bat`**, o
2. Ejecuta en la terminal:
   ```bash
   python bot.py
   ```

---

## 🔐 Configuración Inicial Requerida (Paso Previo)

Antes de poder registrar cargas con `/cg`, el bot exige configurar los siguientes 3 datos:

| Comando | Descripción | Ejemplo |
| :--- | :--- | :--- |
| `/num <teléfono>` | Registra el número de teléfono / Bizum | `/num 612345678` |
| `/name <nombre>` | Registra el nombre completo | `/name Juan Pérez Gómez` |
| `/iban <IBAN>` | Registra el IBAN y detecta de qué banco es mediante API | `/iban ES91 2100 0418 4502 0005 1332` |
| `/datos` | Muestra el perfil con los datos guardados | `/datos` |

---

## 📱 Comandos de Operación

| Comando | Descripción | Ejemplo |
| :--- | :--- | :--- |
| `/cg <cantidad>` | Registra la carga y muestra el total acumulado junto a los datos del titular y banco | `/cg 100` o `/cg 20` |
| `/pc <porcentaje>` | Calcula el porcentaje sobre el saldo total acumulado | `/pc 20` o `/pc 15%` |
| `/total` o `/saldo` | Muestra el total acumulado actual y número de operaciones | `/total` |
| `/historial [n]` | Muestra las últimas cargas registradas con fecha y usuario | `/historial 5` |
| `/deshacer` | Cancela la última carga registrada (por si te equivocas) | `/deshacer` |
| `/reset` | Reinicia el acumulador a cero (requiere confirmación) | `/reset confirmar` |
| `/ayuda` | Muestra la lista de comandos e instrucciones | `/ayuda` |

---

## 💡 Ejemplos de Funcionamiento

### 1. Configuración de datos:
```text
/num 612345678
/name Pedro Gómez
/iban ES91 2100 0418 4502 0005 1332
```
El bot confirmará el IBAN y el banco detectado:
```text
✅ IBAN verificado y guardado con éxito
━━━━━━━━━━━━━━━━━━━━
💳 IBAN: ES91 2100 0418 4502 0005 1332
🏦 Banco: CaixaBank
━━━━━━━━━━━━━━━━━━━━
```

### 2. Registro de carga:
```text
/cg 100
```
Respuesta del bot:
```text
✅ Carga Registrada con Éxito
━━━━━━━━━━━━━━━━━━━━
➕ Cargado: 100,00 €
💰 Total acumulado: 100,00 €
📦 Nº de cargas: 1
━━━━━━━━━━━━━━━━━━━━
👤 Nombre completo: Pedro Gómez
📱 Bizum / Teléfono: 612345678
🏦 Banco: CaixaBank
💳 IBAN: ES91 2100 0418 4502 0005 1332
━━━━━━━━━━━━━━━━━━━━
```

### 3. Siguiente carga acumulada:
```text
/cg 20
```
Respuesta del bot:
```text
✅ Carga Registrada con Éxito
━━━━━━━━━━━━━━━━━━━━
➕ Cargado: 20,00 €
💰 Total acumulado: 120,00 €
📦 Nº de cargas: 2
━━━━━━━━━━━━━━━━━━━━
👤 Nombre completo: Pedro Gómez
📱 Bizum / Teléfono: 612345678
🏦 Banco: CaixaBank
💳 IBAN: ES91 2100 0418 4502 0005 1332
━━━━━━━━━━━━━━━━━━━━
```

### 4. Cálculo de porcentaje:
```text
/pc 20
```
Respuesta del bot:
```text
📊 Cálculo de Porcentaje
━━━━━━━━━━━━━━━━━━━━
💰 Saldo total acumulado: 120,00 €
🔢 Porcentaje solicitado: 20 %
━━━━━━━━━━━━━━━━━━━━
💵 Resultado (20 %): 24,00 €
📉 Saldo restante: 96,00 €
━━━━━━━━━━━━━━━━━━━━
```
