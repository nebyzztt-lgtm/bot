import sqlite3
from datetime import datetime
from typing import List, Dict, Optional, Tuple

DB_PATH = "cargas.db"

def init_db(db_path: str = DB_PATH) -> None:
    """Inicializa la base de datos y crea las tablas si no existen."""
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cargas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                user_id INTEGER,
                username TEXT,
                full_name TEXT,
                amount REAL NOT NULL,
                note TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_chat_id ON cargas(chat_id)")

        # Tabla para guardar datos requeridos antes de cargar: teléfono, nombre, iban y banco
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chat_config (
                chat_id INTEGER PRIMARY KEY,
                phone TEXT DEFAULT '',
                full_name TEXT DEFAULT '',
                iban TEXT DEFAULT '',
                bank_name TEXT DEFAULT '',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
    finally:
        conn.close()

def get_chat_config(chat_id: int, db_path: str = DB_PATH) -> Dict[str, str]:
    """Obtiene la configuración del perfil para este chat."""
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT phone, full_name, iban, bank_name FROM chat_config WHERE chat_id = ?", (chat_id,))
        row = cursor.fetchone()
        if row:
            return dict(row)
        return {"phone": "", "full_name": "", "iban": "", "bank_name": ""}
    finally:
        conn.close()

def set_chat_phone(chat_id: int, phone: str, db_path: str = DB_PATH) -> None:
    """Guarda o actualiza el número de teléfono / Bizum para el chat."""
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO chat_config (chat_id, phone, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(chat_id) DO UPDATE SET phone = excluded.phone, updated_at = CURRENT_TIMESTAMP
        """, (chat_id, phone))
        conn.commit()
    finally:
        conn.close()

def set_chat_name(chat_id: int, full_name: str, db_path: str = DB_PATH) -> None:
    """Guarda o actualiza el nombre completo para el chat."""
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO chat_config (chat_id, full_name, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(chat_id) DO UPDATE SET full_name = excluded.full_name, updated_at = CURRENT_TIMESTAMP
        """, (chat_id, full_name))
        conn.commit()
    finally:
        conn.close()

def set_chat_iban(chat_id: int, iban: str, bank_name: str, db_path: str = DB_PATH) -> None:
    """Guarda o actualiza el IBAN y banco detectado para el chat."""
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO chat_config (chat_id, iban, bank_name, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(chat_id) DO UPDATE SET iban = excluded.iban, bank_name = excluded.bank_name, updated_at = CURRENT_TIMESTAMP
        """, (chat_id, iban, bank_name))
        conn.commit()
    finally:
        conn.close()

def is_config_complete(chat_id: int, db_path: str = DB_PATH) -> Tuple[bool, List[str], Dict[str, str]]:
    """
    Verifica si los 3 datos requeridos (/num, /name, /iban) están completos.
    Retorna: (esta_completo, lista_campos_faltantes, config_dict)
    """
    cfg = get_chat_config(chat_id, db_path)
    missing = []
    if not cfg.get("phone"):
        missing.append("📱 /num (Número de teléfono / Bizum)")
    if not cfg.get("full_name"):
        missing.append("👤 /name (Nombre completo)")
    if not cfg.get("iban"):
        missing.append("💳 /iban (Código IBAN)")
    
    return (len(missing) == 0), missing, cfg

def add_carga(
    chat_id: int,
    user_id: Optional[int],
    username: Optional[str],
    full_name: Optional[str],
    amount: float,
    note: str = "",
    db_path: str = DB_PATH
) -> Tuple[int, float, int]:
    """
    Registra una nueva carga.
    Retorna: (id_de_la_carga, total_acumulado, total_registros)
    """
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO cargas (chat_id, user_id, username, full_name, amount, note, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (chat_id, user_id, username, full_name, amount, note, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        carga_id = cursor.lastrowid

        # Calcular nuevo total
        cursor.execute("SELECT COALESCE(SUM(amount), 0), COUNT(*) FROM cargas WHERE chat_id = ?", (chat_id,))
        total, count = cursor.fetchone()
        conn.commit()
        return carga_id, round(float(total), 2), count
    finally:
        conn.close()

def get_total(chat_id: int, db_path: str = DB_PATH) -> Tuple[float, int]:
    """Retorna (total_acumulado, numero_de_cargas) para un chat."""
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COALESCE(SUM(amount), 0), COUNT(*) FROM cargas WHERE chat_id = ?", (chat_id,))
        total, count = cursor.fetchone()
        return round(float(total), 2), count
    finally:
        conn.close()

def get_historial(chat_id: int, limit: int = 10, db_path: str = DB_PATH) -> List[Dict]:
    """Retorna las ultimas N cargas del chat."""
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, user_id, username, full_name, amount, note, created_at
            FROM cargas
            WHERE chat_id = ?
            ORDER BY id DESC
            LIMIT ?
        """, (chat_id, limit))
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()

def delete_last_carga(chat_id: int, db_path: str = DB_PATH) -> Optional[Dict]:
    """Elimina y retorna la última carga registrada en el chat."""
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, user_id, username, full_name, amount, note, created_at
            FROM cargas
            WHERE chat_id = ?
            ORDER BY id DESC
            LIMIT 1
        """, (chat_id,))
        row = cursor.fetchone()
        if not row:
            return None
        
        last_carga = dict(row)
        cursor.execute("DELETE FROM cargas WHERE id = ?", (last_carga["id"],))
        conn.commit()
        return last_carga
    finally:
        conn.close()

def reset_cargas(chat_id: int, db_path: str = DB_PATH) -> int:
    """Borra todas las cargas de un chat y devuelve la cantidad eliminada."""
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM cargas WHERE chat_id = ?", (chat_id,))
        count = cursor.fetchone()[0]
        cursor.execute("DELETE FROM cargas WHERE chat_id = ?", (chat_id,))
        conn.commit()
        return count
    finally:
        conn.close()
