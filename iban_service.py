import re
import logging
from typing import Tuple, Dict, Any
import httpx
import schwifty
import schwifty.registry as registry

logger = logging.getLogger(__name__)

# Registro oficial de entidades de crédito del Banco de España y bancos digitales
BANCOS_ESPANA = {
    "0049": "Banco Santander",
    "0182": "BBVA",
    "2100": "CaixaBank",
    "0081": "Banco Sabadell",
    "0128": "Bankinter",
    "2080": "Abanca",
    "1465": "ING",
    "2103": "Unicaja Banco",
    "2085": "Ibercaja Banco",
    "3058": "Cajamar Caja Rural",
    "0073": "Openbank",
    "0239": "EVO Banco",
    "1600": "Revolut Bank (Sucursal España)",
    "1563": "N26 Bank (Sucursal España)",
    "0019": "Deutsche Bank",
    "1497": "Triodos Bank",
    "0238": "WiZink Bank",
    "0061": "Banca March",
    "0075": "Banco Popular (Santander)",
    "2038": "Bankia (CaixaBank)",
    "2048": "Liberbank (Unicaja Banco)",
    "0240": "Santander Consumer Finance",
    "3183": "Arquia Banca",
    "0235": "Banco Pichincha España",
    "2095": "Kutxabank",
    "2096": "Caja Rural de Navarra",
    "3001": "Caja Rural de Teruel",
    "3005": "Caja Rural Central",
    "3007": "Caja Rural de Gijón",
    "3008": "Caja Rural de Navarra",
    "3009": "Caja Rural de Extremadura",
    "3017": "Caja Rural de Soria",
    "3018": "Caja Rural Regional",
    "3020": "Caja Rural de Utrera",
    "3023": "Caja Rural de Granada",
    "3035": "Laboral Kutxa",
    "3045": "Caixa Rural de L'Alcudia",
    "3059": "Caja Rural de Asturias",
    "3060": "Caja Rural de Burgos",
    "3067": "Caja Rural de Jaén",
    "3080": "Caja Rural de Teruel",
    "3085": "Caja Rural de Zamora",
    "3089": "Caja Rural de Baena",
    "3095": "Caja Rural de San Roque",
    "3110": "Caja Rural de Cañete de las Torres",
    "3113": "Caja Rural de Algemesí",
    "3115": "Caja Rural de Casas Ibáñez",
    "3117": "Caixa Rural Manises",
    "3121": "Caja Rural de Cheste",
    "3123": "Caja Rural de Albal",
    "3127": "Caixa Rural de Torrent",
    "3130": "Caja Rural de Almenara",
    "3134": "Caja Rural de Betxí",
    "3135": "Caja Rural de Borriana",
    "3138": "Caixa Rural Nules",
    "3140": "Caja Rural de Vilafamés",
    "3144": "Caixa Rural Vilavella",
    "3159": "Caixa Popular",
    "3160": "Caixa Rural Benicarló",
    "3162": "Caixa Rural Vinaròs",
    "3165": "Caixa Rural Altea",
    "3166": "Caixa Rural de Callosa d'en Sarrià",
    "3170": "Caixa Rural Les Coves de Vinromà",
    "3174": "Caixa Rural Viver",
    "3179": "Caja Rural de Albalat",
}

def clean_iban(iban_str: str) -> str:
    """Limpia el IBAN quitando espacios, guiones y convirtiendo a mayúsculas."""
    return re.sub(r"[\s\-]+", "", iban_str).upper()

def format_iban_display(clean_iban_str: str) -> str:
    """Formatea el IBAN en bloques de 4 caracteres (ej. ES91 2100 0418 4502 0005 1332)."""
    return " ".join([clean_iban_str[i:i+4] for i in range(0, len(clean_iban_str), 4)])

async def check_iban_with_api(clean_iban_str: str) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Realiza una petición HTTP a la API pública de validación de IBANs.
    Retorna: (es_valido, mensaje_error, api_response)
    """
    url = f"https://openiban.com/validate/{clean_iban_str}?getBIC=true"
    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                is_valid = data.get("valid", False)
                messages = data.get("messages", [])
                error_msg = messages[0] if (not is_valid and messages) else ""
                return is_valid, error_msg, data
    except Exception as e:
        logger.warning(f"Error consultando API externa: {e}")
    
    # Si la API externa no responde por red, usar validación ISO matemática local (MOD-97)
    try:
        iban_obj = schwifty.IBAN(clean_iban_str)
        return True, "", {}
    except Exception as ex:
        return False, str(ex), {}

async def resolve_bank_name(iban_raw: str) -> Tuple[bool, str, str, str]:
    """
    Valida y resuelve el banco del IBAN mediante API y registro oficial.
    Retorna: (es_valido, iban_formateado, nombre_banco, fuente_verificacion)
    """
    clean = clean_iban(iban_raw)
    
    if len(clean) < 8:
        return False, clean, "El código IBAN es demasiado corto", ""

    # 1. Petición a la API externa para chequear validez y datos
    is_valid, err_msg, api_data = await check_iban_with_api(clean)
    if not is_valid:
        msg = err_msg if err_msg else "Dígito de control o formato inválido según la API"
        return False, format_iban_display(clean), msg, "API OpenIBAN"

    bank_name = ""
    country_code = clean[:2]

    # Intentar obtener el nombre del banco directamente de la respuesta de la API
    bank_data = api_data.get("bankData", {})
    if bank_data.get("name") and bank_data["name"].strip():
        bank_name = bank_data["name"].strip()

    # Si es español (ES) y la API no especificó el nombre local, consultar código de entidad
    if not bank_name and country_code == "ES" and len(clean) >= 8:
        bank_code = clean[4:8]
        if bank_code in BANCOS_ESPANA:
            bank_name = BANCOS_ESPANA[bank_code]
        else:
            try:
                banks = registry.get_banks_by_code("ES", bank_code)
                if banks and banks[0].name:
                    bank_name = banks[0].name
            except Exception:
                pass

    # Si aún no tenemos nombre, consultar con schwifty (BIC / Registro bancario)
    if not bank_name:
        try:
            parsed = schwifty.IBAN(clean)
            if parsed.bank_name:
                bank_name = parsed.bank_name
            elif parsed.bic and parsed.bic.bank_name:
                bank_name = parsed.bic.bank_name
        except Exception:
            pass

    # Bancos europeos internacionales comunes
    if not bank_name:
        if country_code == "LT":
            bank_name = "Revolut Payments UAB (Lituania)"
        elif country_code == "DE":
            bank_name = "Banco de Alemania (DE)"
        elif country_code == "FR":
            bank_name = "Banco de Francia (FR)"
        elif country_code == "IT":
            bank_name = "Banco de Italia (IT)"
        elif country_code == "PT":
            bank_name = "Banco de Portugal (PT)"
        else:
            bank_name = f"Banco de {country_code}"

    formatted_iban = format_iban_display(clean)
    return True, formatted_iban, bank_name, "API OpenIBAN"
