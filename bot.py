import os
import sys
import re
import logging
from typing import Optional, Tuple
from dotenv import load_dotenv

# Asegurar codificación UTF-8 en consola de Windows
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

import time
from telegram import Update
from telegram.constants import ParseMode
from telegram.error import NetworkError, TimedOut, Conflict, TelegramError
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)
import database
import iban_service

# Cargar variables de entorno desde .env
load_dotenv()

# Configurar logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

def format_currency(amount: float) -> str:
    """Formatea la cantidad a formato europeo con coma decimal (ej. 1.250,50 €)."""
    return f"{amount:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")

def parse_args_amount_note(args: list) -> Tuple[Optional[float], str]:
    """
    Parsea los argumentos del comando para extraer la cantidad y la nota.
    Soporta formatos como: 100, 20.50, 20,50, 100€, etc.
    """
    if not args:
        return None, ""
    
    first_arg = args[0].strip().replace("€", "").replace("eur", "").replace("EUR", "")
    first_arg = first_arg.replace(",", ".")
    
    try:
        amount = float(first_arg)
        if amount <= 0:
            return None, ""
        note = " ".join(args[1:]).strip()
        return round(amount, 2), note
    except ValueError:
        return None, ""

def parse_percentage(args: list) -> Optional[float]:
    """Extrae el porcentaje de los argumentos (ej. 20, 20%, 15.5)."""
    if not args:
        return None
    val_str = args[0].strip().replace("%", "").replace(",", ".")
    try:
        val = float(val_str)
        if val <= 0:
            return None
        return val
    except ValueError:
        return None

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Mensaje de bienvenida y guía paso a paso."""
    chat = update.effective_chat
    cfg = database.get_chat_config(chat.id) if chat else {}

    phone_status = f"✅ `{cfg.get('phone')}`" if cfg.get("phone") else "❌ Falta configurar"
    name_status = f"✅ `{cfg.get('full_name')}`" if cfg.get("full_name") else "❌ Falta configurar"
    iban_status = f"✅ `{cfg.get('bank_name')}`" if cfg.get("iban") else "❌ Falta configurar"

    text = (
        "👋 ¡Hola! Bienvenido a tu **Bot de Notificación y Gestión de Cargas**.\n\n"
        "⚠️ **Requisitos previos antes de cargar:**\n"
        "Debes configurar tus 3 datos iniciales con los siguientes comandos:\n\n"
        f"1️⃣ `/num <teléfono>` (Número Bizum) ➡️ {phone_status}\n"
        f"2️⃣ `/name <nombre completo>` ➡️ {name_status}\n"
        f"3️⃣ `/iban <código IBAN>` ➡️ {iban_status}\n\n"
        "📌 **Comandos una vez configurado:**\n"
        "• `/cg <cantidad>` (o `/carga`): Registra una carga y notifica los datos completos con el nuevo total.\n"
        "• `/pc <porcentaje>`: Calcula el porcentaje indicado sobre el saldo total acumulado.\n"
        "• `/datos`: Consulta los datos que tienes guardados actualmente.\n"
        "• `/total` (o `/saldo`): Consulta el saldo total y número de cargas.\n"
        "• `/historial`: Muestra las últimas operaciones registradas.\n"
        "• `/deshacer`: Cancela la última carga registrada.\n"
        "• `/reset`: Reinicia el contador a cero (`/reset confirmar`)."
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Muestra la ayuda."""
    await start_command(update, context)

async def num_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Configura el número de teléfono / Bizum."""
    chat = update.effective_chat
    if not chat:
        return

    if not context.args:
        await update.message.reply_text(
            "⚠️ **Uso del comando:** `/num <teléfono>`\n\n"
            "Ejemplo:\n"
            "`/num 612345678`\n"
            "`/num +34 654 98 76 54`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    phone = " ".join(context.args).strip()
    database.set_chat_phone(chat.id, phone)

    is_complete, missing, cfg = database.is_config_complete(chat.id)
    response = (
        "✅ **Teléfono Bizum guardado correctamente:**\n"
        f"📱 `{phone}`\n\n"
    )
    if is_complete:
        response += "🎉 **¡Todos tus datos están listos!** Ya puedes empezar a registrar cargas usando `/cg <cantidad>`."
    else:
        response += "📌 **Faltan por configurar:**\n" + "\n".join(f"• {m}" for m in missing)

    await update.message.reply_text(response, parse_mode=ParseMode.MARKDOWN)

async def name_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Configura el nombre completo."""
    chat = update.effective_chat
    if not chat:
        return

    if not context.args:
        await update.message.reply_text(
            "⚠️ **Uso del comando:** `/name <nombre completo>`\n\n"
            "Ejemplo:\n"
            "`/name Juan Pérez Martínez`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    full_name = " ".join(context.args).strip()
    database.set_chat_name(chat.id, full_name)

    is_complete, missing, cfg = database.is_config_complete(chat.id)
    response = (
        "✅ **Nombre completo guardado correctamente:**\n"
        f"👤 `{full_name}`\n\n"
    )
    if is_complete:
        response += "🎉 **¡Todos tus datos están listos!** Ya puedes empezar a registrar cargas usando `/cg <cantidad>`."
    else:
        response += "📌 **Faltan por configurar:**\n" + "\n".join(f"• {m}" for m in missing)

    await update.message.reply_text(response, parse_mode=ParseMode.MARKDOWN)

async def iban_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Configura el IBAN y detecta automáticamente de qué banco es."""
    chat = update.effective_chat
    if not chat:
        return

    if not context.args:
        await update.message.reply_text(
            "⚠️ **Uso del comando:** `/iban <código IBAN>`\n\n"
            "Ejemplo:\n"
            "`/iban ES91 2100 0418 4502 0005 1332`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    raw_iban = "".join(context.args).strip()
    ok, formatted_iban, bank_name, api_source = await iban_service.resolve_bank_name(raw_iban)

    if not ok:
        await update.message.reply_text(
            f"❌ **IBAN no válido según la API:**\n"
            f"• Motivo: {bank_name}\n"
            f"• Verificación: `{api_source}`\n\n"
            "Por favor, revisa el número de cuenta e inténtalo de nuevo.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # Guardar en base de datos
    database.set_chat_iban(chat.id, formatted_iban, bank_name)

    is_complete, missing, cfg = database.is_config_complete(chat.id)
    response = (
        "✅ **IBAN Verificado por API y Guardado**\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"🌐 **Consulta API:** `{api_source}` (Status: Válido ✅)\n"
        f"💳 **IBAN:** `{formatted_iban}`\n"
        f"🏦 **Banco Detectado:** `{bank_name}`\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
    )
    if is_complete:
        response += "🎉 **¡Todos tus datos están configurados!** Ya puedes registrar cargas usando `/cg <cantidad>`."
    else:
        response += "📌 **Faltan por configurar:**\n" + "\n".join(f"• {m}" for m in missing)

    await update.message.reply_text(response, parse_mode=ParseMode.MARKDOWN)

async def datos_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Muestra los datos configurados actualmente."""
    chat = update.effective_chat
    if not chat:
        return

    cfg = database.get_chat_config(chat.id)
    phone = cfg.get("phone") or "_(No configurado - usa /num)_"
    name = cfg.get("full_name") or "_(No configurado - usa /name)_"
    iban = cfg.get("iban") or "_(No configurado - usa /iban)_"
    bank = cfg.get("bank_name") or "_(No detectado)_"

    text = (
        "📋 **Tus Datos Registrados:**\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 **Nombre completo:** {name}\n"
        f"📱 **Teléfono Bizum:** {phone}\n"
        f"💳 **IBAN:** {iban}\n"
        f"🏦 **Banco:** {bank}\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "💡 Puedes modificar cualquier dato cuando quieras volviendo a enviar el comando correspondiente."
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def pc_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Calcula el porcentaje indicado sobre el saldo total acumulado."""
    chat = update.effective_chat
    if not chat:
        return

    percentage = parse_percentage(context.args)
    if percentage is None:
        await update.message.reply_text(
            "⚠️ **Uso del comando:** `/pc <porcentaje>`\n\n"
            "Ejemplos:\n"
            "• `/pc 20` (calcula el 20% del total acumulado)\n"
            "• `/pc 15.5`\n"
            "• `/pc 50%`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    total, count = database.get_total(chat.id)
    if total <= 0 or count == 0:
        await update.message.reply_text(
            "ℹ️ No hay saldo acumulado actualmente para calcular el porcentaje.\n"
            "Registra primero una carga con `/cg <cantidad>`.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    calculated_amount = round((total * percentage) / 100.0, 2)
    remaining_amount = round(total - calculated_amount, 2)

    pct_str = f"{percentage:g} %"

    response = (
        "📊 **Cálculo de Porcentaje**\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 **Saldo total acumulado:** `{format_currency(total)}`\n"
        f"🔢 **Porcentaje solicitado:** `{pct_str}`\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"💵 **Resultado ({pct_str}):** `{format_currency(calculated_amount)}`\n"
        f"📉 **Saldo restante:** `{format_currency(remaining_amount)}`\n"
        "━━━━━━━━━━━━━━━━━━━━"
    )
    await update.message.reply_text(response, parse_mode=ParseMode.MARKDOWN)

async def carga_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Registra una carga y responde con la notificación y datos completos."""
    chat = update.effective_chat
    user = update.effective_user
    if not chat:
        return

    # Verificar si están los 3 datos obligatorios configurados
    is_complete, missing, cfg = database.is_config_complete(chat.id)
    if not is_complete:
        msg = (
            "⚠️ **No puedes registrar cargas todavía.**\n\n"
            "Antes debes configurar tus datos obligatorios:\n\n"
        )
        msg += f"1️⃣ `/num <teléfono>` (Bizum) ➡️ {'✅ Guardado' if cfg.get('phone') else '❌ Pendiente'}\n"
        msg += f"2️⃣ `/name <nombre completo>` ➡️ {'✅ Guardado' if cfg.get('full_name') else '❌ Pendiente'}\n"
        msg += f"3️⃣ `/iban <código IBAN>` ➡️ {'✅ Guardado' if cfg.get('iban') else '❌ Pendiente'}\n\n"
        msg += "👉 Completa los datos pendientes para poder registrar tu carga."
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
        return

    amount, note = parse_args_amount_note(context.args)
    if amount is None:
        await update.message.reply_text(
            "⚠️ **Formato incorrecto.**\n"
            "Debes indicar la cantidad a cargar.\n\n"
            "Ejemplos:\n"
            "`/cg 100`\n"
            "`/cg 20`\n"
            "`/cg 45.50 Depósito cliente`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # Extraer información del usuario en Telegram
    user_id = user.id if user else None
    username = f"@{user.username}" if user and user.username else None
    full_name_tg = user.full_name if user else "Desconocido"

    # Registrar en base de datos
    carga_id, total, count = database.add_carga(
        chat_id=chat.id,
        user_id=user_id,
        username=username,
        full_name=full_name_tg,
        amount=amount,
        note=note
    )

    note_line = f"\n📝 *Nota:* _{note}_" if note else ""

    response = (
        "✅ **Carga Registrada con Éxito**\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"➕ **Cargado:** `{format_currency(amount)}`\n"
        f"💰 **Total acumulado:** `{format_currency(total)}`\n"
        f"📦 **Nº de cargas:** `{count}`{note_line}\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 **Nombre completo:** `{cfg.get('full_name')}`\n"
        f"📱 **Bizum / Teléfono:** `{cfg.get('phone')}`\n"
        f"🏦 **Banco:** `{cfg.get('bank_name')}`\n"
        f"💳 **IBAN:** `{cfg.get('iban')}`\n"
        "━━━━━━━━━━━━━━━━━━━━"
    )

    await update.message.reply_text(response, parse_mode=ParseMode.MARKDOWN)

async def total_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Muestra el total acumulado actual del chat."""
    chat = update.effective_chat
    if not chat:
        return

    total, count = database.get_total(chat.id)
    
    if count == 0:
        await update.message.reply_text(
            "ℹ️ No hay cargas registradas todavía.\n"
            "Usa `/cg <cantidad>` para registrar la primera.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    response = (
        "📊 **Estado de Cargas**\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 **Total acumulado:** `{format_currency(total)}`\n"
        f"📦 **Total de cargas:** `{count}`\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "💡 Usa `/pc <porcentaje>` para calcular un porcentaje sobre este total.\n"
        "💡 Usa `/historial` para ver las últimas operaciones."
    )
    await update.message.reply_text(response, parse_mode=ParseMode.MARKDOWN)

async def historial_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Muestra el historial de las últimas cargas registradas."""
    chat = update.effective_chat
    if not chat:
        return

    limit = 10
    if context.args and context.args[0].isdigit():
        limit = min(max(1, int(context.args[0])), 30)

    rows = database.get_historial(chat.id, limit=limit)
    total, count = database.get_total(chat.id)

    if not rows:
        await update.message.reply_text("ℹ️ El historial está vacío.")
        return

    lines = [f"📋 **Últimas {len(rows)} cargas:**", "━━━━━━━━━━━━━━━━━━━━"]
    for i, r in enumerate(rows, 1):
        who = r["username"] or r["full_name"] or "Anon"
        date_str = r["created_at"].split()[0] + " " + r["created_at"].split()[1][:5]
        note_str = f" - _{r['note']}_" if r["note"] else ""
        lines.append(f"{i}. `+{format_currency(r['amount'])}` | {date_str} | {who}{note_str}")

    lines.append("━━━━━━━━━━━━━━━━━━━━")
    lines.append(f"💰 **Total Acumulado:** `{format_currency(total)}` ({count} cargas)")

    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)

async def deshacer_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Elimina la última carga registrada."""
    chat = update.effective_chat
    if not chat:
        return

    deleted = database.delete_last_carga(chat.id)
    if not deleted:
        await update.message.reply_text("⚠️ No hay ninguna carga para deshacer.")
        return

    new_total, new_count = database.get_total(chat.id)
    response = (
        "🗑️ **Última carga deshecha**\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"❌ Se eliminó: `{format_currency(deleted['amount'])}`\n"
        f"💰 **Nuevo total acumulado:** `{format_currency(new_total)}`\n"
        f"📦 Cargas restantes: `{new_count}`"
    )
    await update.message.reply_text(response, parse_mode=ParseMode.MARKDOWN)

async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Reinicia el total acumulado."""
    chat = update.effective_chat
    if not chat:
        return

    if not context.args or context.args[0].lower() != "confirmar":
        await update.message.reply_text(
            "⚠️ **¿Estás seguro de reiniciar el contador a 0 €?**\n\n"
            "Esto borrará el historial de cargas de este chat (tus datos /num, /name, /iban se mantienen).\n"
            "Para confirmar el reinicio escribe:\n"
            "`/reset confirmar`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    deleted_count = database.reset_cargas(chat.id)
    await update.message.reply_text(
        f"🔄 **Contador reiniciado con éxito**\n"
        f"Se han eliminado `{deleted_count}` registros de carga.\n"
        f"💰 **Total actual:** `0,00 €`",
        parse_mode=ParseMode.MARKDOWN
    )

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Registra cualquier error que ocurra durante la ejecución sin detener el bot."""
    logger.error("Error capturado en el bot:", exc_info=context.error)

def main() -> None:
    """Punto de entrada principal para iniciar el bot en modo 24/7 siempre operativo."""
    if not TOKEN or TOKEN == "TU_TELEGRAM_BOT_TOKEN_AQUI":
        print("\n" + "="*60)
        print("ERROR: TELEGRAM_BOT_TOKEN no está configurado.")
        print("Abre el archivo .env y pega tu token del bot obtenido de @BotFather.")
        print("="*60 + "\n")
        return

    # Inicializar la base de datos
    database.init_db()

    # Construir aplicación
    app = Application.builder().token(TOKEN).build()

    # Manejador global de excepciones para que nunca se caiga
    app.add_error_handler(error_handler)

    # Handlers para configuración inicial obligatoria
    app.add_handler(CommandHandler(["num", "telefono", "bizum"], num_command))
    app.add_handler(CommandHandler(["name", "nombre"], name_command))
    app.add_handler(CommandHandler(["iban", "cuenta"], iban_command))
    app.add_handler(CommandHandler(["datos", "perfil"], datos_command))

    # Handlers para cálculos y operaciones
    app.add_handler(CommandHandler(["start", "ayuda", "help"], start_command))
    app.add_handler(CommandHandler(["cg", "carga"], carga_command))
    app.add_handler(CommandHandler(["pc", "porcentaje"], pc_command))
    app.add_handler(CommandHandler(["total", "saldo"], total_command))
    app.add_handler(CommandHandler(["historial", "history"], historial_command))
    app.add_handler(CommandHandler(["deshacer", "borrar_ultima"], deshacer_command))
    app.add_handler(CommandHandler(["reset", "reiniciar"], reset_command))

    print("====================================================")
    print("Bot de Cargas con IBAN, Banco y Porcentajes")
    print("Estado: MODO SIEMPRE OPERATIVO (24/7)")
    print("Escuchando mensajes en Telegram...")
    print("====================================================")

    # Bucle de reintento automático para mantener el bot siempre activo
    while True:
        try:
            app.run_polling(drop_pending_updates=True)
            break
        except (NetworkError, TimedOut) as e:
            logger.warning(f"Aviso de red: {e}. Reconectando en 5 segundos...")
            time.sleep(5)
        except Conflict:
            logger.warning("Sesión anterior de Telegram cerrándose. Reintentando en 8 segundos...")
            time.sleep(8)
        except KeyboardInterrupt:
            print("\nBot detenido manualmente por el usuario.")
            break
        except Exception as e:
            logger.error(f"Excepción capturada: {e}. Reiniciando en 5 segundos...")
            time.sleep(5)

if __name__ == "__main__":
    main()
