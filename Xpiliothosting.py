import subprocess
import sys

try:
    import aiosqlite
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "aiosqlite"])
    import aiosqlite

# ==============================================================================
# CORE LIBRARIES
# ==============================================================================
import asyncio
import logging
import os
import random
import re
import string
import time
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

import aiosqlite
from curl_cffi.requests import AsyncSession

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    FSInputFile
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram import BaseMiddleware

# ==============================================================================
# GLOBAL CONFIGURATIONS
# ==============================================================================

class Config:
    # 🚨 UPDATED TOKEN AND ADMIN ID
    BOT_TOKEN = os.getenv("BOT_TOKEN", "8953813919:AAFKebGgZqCCZwjYwEYCMFiPwmBmtBfO5Uc")
    BOT_USERNAME = "@hostingbyaniket_bot"
    ADMIN_IDS = [8705755564]  # Updated Admin ID
    
    # Payment & VIP Config
    PACKAGES = {
        "1M": {"price": 99, "name": "1 Month", "days": 30},
        "6M": {"price": 499, "name": "6 Months", "days": 180},
        "12M": {"price": 899, "name": "1 Year", "days": 365}
    }
    UPI_ID = "adityaraj5881@okhdfcbank"

    # Hosting & Referral Config
    DEFAULT_REF_CODE = "RAJ282DCA"
    POINTS_PER_REFERRAL = 10
    FREE_TRIAL_DAYS = 1
    REFERRAL_DAYS_BONUS = 2
    REFERRALS_FOR_BONUS = 4
    
    # File Config
    ALLOWED_EXTENSIONS = ['.py', '.zip']
    UPLOAD_DIR = "user_uploads"
    
    # Database & Worker
    DB_FILE = "bot.db"
    WORKER_CONCURRENCY = 2
    
    # Proxy & Network
    PROXY_URL = os.getenv("PROXY_URL", "").strip()
    CATCH_ALL_DOMAIN = os.getenv("CATCH_ALL_DOMAIN", "").strip()
    
    # Watermark
    FOOTER_TEXT = "\n\n⚡ Made by Aniket"

    # Brevistay URLs
    BREVISTAY_BASE_URL = "https://cst.brevistay.com"
    BREVISTAY_WEB_URL = "https://www.brevistay.com"

INDIAN_FIRST_NAMES = [
    "Arjun", "Aarav", "Vihaan", "Vivaan", "Ananya", "Diya", "Aadhya", "Sai", 
    "Rohan", "Siddharth", "Kunal", "Rahul", "Priya", "Neha", "Pooja", "Anjali"
]

INDIAN_LAST_NAMES = [
    "Sharma", "Verma", "Patel", "Kumar", "Singh", "Reddy", "Gupta", "Joshi",
    "Nair", "Menon", "Shetty", "Rao", "Desai", "Mehta", "Choudhury", "Malhotra"
]

logging.basicConfig(
    level=logging.INFO, 
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logging.getLogger("curl_cffi").setLevel(logging.WARNING) 
logging.getLogger("aiogram").setLevel(logging.INFO)
logger = logging.getLogger("BrevistayEngine")

# ==============================================================================
# IN-MEMORY CACHE SYSTEM
# ==============================================================================

class MemCache:
    _store: Dict[str, Tuple[Any, Optional[float]]] = {}

    @classmethod
    async def get(cls, key: str) -> Optional[Any]:
        if key in cls._store:
            val, exp = cls._store[key]
            if exp and time.time() > exp:
                del cls._store[key]
                return None
            return val
        return None

    @classmethod
    async def set(cls, key: str, val: Any):
        cls._store[key] = (val, None)

    @classmethod
    async def setex(cls, key: str, ttl: int, val: Any):
        cls._store[key] = (val, time.time() + ttl)

    @classmethod
    async def delete(cls, key: str):
        if key in cls._store:
            del cls._store[key]

    @classmethod
    async def incr(cls, key: str) -> int:
        val = await cls.get(key)
        val = int(val) + 1 if val else 1
        exp = cls._store[key][1] if key in cls._store else None
        cls._store[key] = (str(val), exp)
        return val

    @classmethod
    async def expire(cls, key: str, ttl: int):
        if key in cls._store:
            val = cls._store[key][0]
            cls._store[key] = (val, time.time() + ttl)

# ==============================================================================
# SQLITE DATABASE SCHEMA (UPDATED)
# ==============================================================================

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    points INTEGER DEFAULT 0,
    is_banned INTEGER DEFAULT 0,
    total_processes INTEGER DEFAULT 0,
    joined_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS website_refcodes (
    user_id INTEGER PRIMARY KEY,
    ref_code TEXT NOT NULL,
    added_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS telegram_referrals (
    referred_id INTEGER PRIMARY KEY,
    referrer_id INTEGER,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(referred_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY(referrer_id) REFERENCES users(user_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS processes (
    process_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    mobile TEXT NOT NULL,
    status TEXT DEFAULT 'PENDING',
    logs TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS giftcards (
    code TEXT PRIMARY KEY,
    points INTEGER NOT NULL,
    max_uses INTEGER DEFAULT 1,
    current_uses INTEGER DEFAULT 0,
    created_by INTEGER,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS redemptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT,
    user_id INTEGER,
    redeemed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(code) REFERENCES giftcards(code) ON DELETE CASCADE,
    FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    UNIQUE(code, user_id)
);

CREATE TABLE IF NOT EXISTS bot_settings (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- NEW TABLES FOR VIP & HOSTING
CREATE TABLE IF NOT EXISTS hosting_access (
    user_id INTEGER PRIMARY KEY,
    expiry_date INTEGER NOT NULL, -- Unix timestamp
    is_active INTEGER DEFAULT 1,
    FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    package_id TEXT NOT NULL,
    amount INTEGER NOT NULL,
    utr TEXT NOT NULL,
    status TEXT DEFAULT 'PENDING', -- PENDING, APPROVED, REJECTED
    admin_notes TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
);
"""

class DB:
    @classmethod
    async def init(cls):
        logger.info("Initializing SQLite Database...")
        async with aiosqlite.connect(Config.DB_FILE) as db:
            await db.execute('PRAGMA journal_mode=WAL;')
            await db.executescript(SCHEMA)
            await db.execute("""
                INSERT INTO bot_settings (key, value) 
                VALUES ('maintenance', 'false') 
                ON CONFLICT (key) DO NOTHING;
            """)
            await db.commit()
        logger.info("SQLite Database Initialized Successfully.")

# ==============================================================================
# GLOBAL CURL_CFFI SESSION
# ==============================================================================

class HTTP:
    session: AsyncSession = None

    @classmethod
    async def init(cls):
        logger.info("Initializing Global curl_cffi Session...")
        proxies = None
        if not Config.PROXY_URL:
            logger.info("No proxy added, continuing without proxy.")
        else:
            logger.info(f"Proxy configured: {Config.PROXY_URL}")
            proxies = {"http": Config.PROXY_URL, "https": Config.PROXY_URL}
        
        cls.session = AsyncSession(
            proxies=proxies,
            timeout=30,
            verify=False 
        )
        logger.info("Global curl_cffi Session Initialized.")

    @classmethod
    async def close(cls):
        if cls.session:
            await cls.session.close()

# ==============================================================================
# DATABASE MANAGERS (UPDATED WITH HOSTING & PAYMENTS)
# ==============================================================================

class UserManager:
    @staticmethod
    async def register_user(user_id: int, username: str, first_name: str, referrer_id: Optional[int] = None) -> bool:
        async with aiosqlite.connect(Config.DB_FILE) as db:
            async with db.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,)) as cursor:
                exists = await cursor.fetchone()
                if exists: return False

            await db.execute("INSERT INTO users (user_id, username, first_name) VALUES (?, ?, ?)", (user_id, username, first_name))

            if referrer_id and referrer_id != user_id:
                async with db.execute("SELECT 1 FROM users WHERE user_id = ?", (referrer_id,)) as ref_cursor:
                    if await ref_cursor.fetchone():
                        await db.execute("INSERT INTO telegram_referrals (referred_id, referrer_id) VALUES (?, ?)", (user_id, referrer_id))
                        await db.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (Config.POINTS_PER_REFERRAL, referrer_id))
            await db.commit()
            return True

    @staticmethod
    async def get_user(user_id: int) -> Optional[dict]:
        async with aiosqlite.connect(Config.DB_FILE) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cursor:
                return await cursor.fetchone()

    @staticmethod
    async def update_points(user_id: int, amount: int) -> int:
        async with aiosqlite.connect(Config.DB_FILE) as db:
            await db.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (amount, user_id))
            await db.commit()
            async with db.execute("SELECT points FROM users WHERE user_id = ?", (user_id,)) as cursor:
                res = await cursor.fetchone()
                return res[0] if res else 0

    @staticmethod
    async def is_banned(user_id: int) -> bool:
        cached = await MemCache.get(f"ban:{user_id}")
        if cached is not None: return cached == "1"
        
        async with aiosqlite.connect(Config.DB_FILE) as db:
            async with db.execute("SELECT is_banned FROM users WHERE user_id = ?", (user_id,)) as cursor:
                row = await cursor.fetchone()
                banned = bool(row[0]) if row else False
                await MemCache.setex(f"ban:{user_id}", 300, "1" if banned else "0")
                return banned

    @staticmethod
    async def set_ban_status(user_id: int, is_banned: bool):
        async with aiosqlite.connect(Config.DB_FILE) as db:
            val = 1 if is_banned else 0
            await db.execute("UPDATE users SET is_banned = ? WHERE user_id = ?", (val, user_id))
            await db.commit()
        await MemCache.setex(f"ban:{user_id}", 300, "1" if is_banned else "0")

    # --- NEW HOSTING AND PAYMENTS METHODS ---
    @staticmethod
    async def is_hosting_active(user_id: int) -> bool:
        async with aiosqlite.connect(Config.DB_FILE) as db:
            async with db.execute("SELECT expiry_date FROM hosting_access WHERE user_id = ? AND is_active = 1", (user_id,)) as cur:
                row = await cur.fetchone()
                if not row: return False
                return int(time.time()) < row[0]

    @staticmethod
    async def get_hosting_expiry(user_id: int) -> int:
        async with aiosqlite.connect(Config.DB_FILE) as db:
            async with db.execute("SELECT expiry_date FROM hosting_access WHERE user_id = ?", (user_id,)) as cur:
                row = await cur.fetchone()
                return row[0] if row else 0

    @staticmethod
    async def grant_hosting_access(user_id: int, days_to_add: int):
        current_expiry = await UserManager.get_hosting_expiry(user_id)
        base_time = int(time.time()) if current_expiry < int(time.time()) else current_expiry
        new_expiry = base_time + (days_to_add * 24 * 60 * 60)
        
        async with aiosqlite.connect(Config.DB_FILE) as db:
            await db.execute("""
                INSERT INTO hosting_access (user_id, expiry_date, is_active) 
                VALUES (?, ?, 1) 
                ON CONFLICT (user_id) DO UPDATE SET expiry_date = ?
            """, (user_id, new_expiry, new_expiry))
            await db.commit()

    @staticmethod
    async def get_website_refcode(user_id: int) -> Optional[str]:
        async with aiosqlite.connect(Config.DB_FILE) as db:
            async with db.execute("SELECT ref_code FROM website_refcodes WHERE user_id = ?", (user_id,)) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else None

    @staticmethod
    async def set_website_refcode(user_id: int, ref_code: str):
        async with aiosqlite.connect(Config.DB_FILE) as db:
            await db.execute("""
                INSERT INTO website_refcodes (user_id, ref_code) 
                VALUES (?, ?) ON CONFLICT (user_id) DO UPDATE SET ref_code = ?, added_at = CURRENT_TIMESTAMP
                """, (user_id, ref_code, ref_code)
            )
            await db.commit()

    @staticmethod
    async def remove_website_refcode(user_id: int):
        async with aiosqlite.connect(Config.DB_FILE) as db:
            await db.execute("DELETE FROM website_refcodes WHERE user_id = ?", (user_id,))
            await db.commit()

    @staticmethod
    async def get_leaderboard(limit: int = 10) -> List[dict]:
        async with aiosqlite.connect(Config.DB_FILE) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT u.user_id, u.first_name, u.points, u.total_processes,
                       COUNT(tr.referred_id) as total_referrals
                FROM users u LEFT JOIN telegram_referrals tr ON u.user_id = tr.referrer_id
                GROUP BY u.user_id ORDER BY u.total_processes DESC, total_referrals DESC, u.points DESC LIMIT ?
            """, (limit,)) as cursor:
                return await cursor.fetchall()

    @staticmethod
    async def get_stats(user_id: int) -> dict:
        async with aiosqlite.connect(Config.DB_FILE) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT u.points, u.total_processes, (SELECT COUNT(*) FROM telegram_referrals WHERE referrer_id = ?) as total_refs
                FROM users u WHERE u.user_id = ?
            """, (user_id, user_id)) as cursor:
                return await cursor.fetchone()

class ProcessManager:
    @staticmethod
    async def create_process(user_id: int, mobile: str) -> int:
        async with aiosqlite.connect(Config.DB_FILE) as db:
            cursor = await db.execute("INSERT INTO processes (user_id, mobile, status) VALUES (?, ?, 'PENDING')", (user_id, mobile))
            await db.commit()
            return cursor.lastrowid

    @staticmethod
    async def update_process(process_id: int, status: str, logs: str = None):
        async with aiosqlite.connect(Config.DB_FILE) as db:
            if logs:
                await db.execute("UPDATE processes SET status = ?, logs = COALESCE(logs, '') || ? || '\n', updated_at = CURRENT_TIMESTAMP WHERE process_id = ?", (status, logs, process_id))
            else:
                await db.execute("UPDATE processes SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE process_id = ?", (status, process_id))
            if status == "COMPLETED":
                await db.execute("UPDATE users SET total_processes = total_processes + 1 WHERE user_id = (SELECT user_id FROM processes WHERE process_id = ?)", (process_id,))
            await db.commit()

class AdminManager:
    @staticmethod
    async def get_stats() -> dict:
        async with aiosqlite.connect(Config.DB_FILE) as db:
            stats = {}
            for key, table in [("users", "users"), ("processes", "processes"), ("referrals", "telegram_referrals")]:
                async with db.execute(f"SELECT COUNT(*) FROM {table}") as cursor:
                    stats[key] = (await cursor.fetchone())[0]
            async with db.execute("SELECT COUNT(*) FROM processes WHERE status = 'COMPLETED'") as cursor:
                stats["completed"] = (await cursor.fetchone())[0]
            return stats

    @staticmethod
    async def create_giftcard(points: int, uses: int, admin_id: int) -> str:
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=12))
        async with aiosqlite.connect(Config.DB_FILE) as db:
            await db.execute("INSERT INTO giftcards (code, points, max_uses, created_by) VALUES (?, ?, ?, ?)", (code, points, uses, admin_id))
            await db.commit()
        return code

    @staticmethod
    async def redeem_giftcard(code: str, user_id: int) -> Tuple[bool, str, int]:
        async with aiosqlite.connect(Config.DB_FILE) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM giftcards WHERE code = ?", (code,)) as cursor:
                card = await cursor.fetchone()
                
            if not card: return False, "Invalid gift card code.", 0
            if card['current_uses'] >= card['max_uses']: return False, "This gift card has expired or reached its usage limit.", 0
            
            async with db.execute("SELECT 1 FROM redemptions WHERE code = ? AND user_id = ?", (code, user_id)) as cursor:
                has_redeemed = await cursor.fetchone()
            if has_redeemed: return False, "You have already redeemed this gift card.", 0
            
            await db.execute("INSERT INTO redemptions (code, user_id) VALUES (?, ?)", (code, user_id))
            await db.execute("UPDATE giftcards SET current_uses = current_uses + 1 WHERE code = ?", (code,))
            await db.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (card['points'], user_id))
            await db.commit()
            
            return True, "Successfully redeemed!", card['points']

    # --- NEW PAYMENTS METHOD ---
    @staticmethod
    async def create_payment_request(user_id: int, package_id: str, utr: str) -> int:
        pkg = Config.PACKAGES[package_id]
        async with aiosqlite.connect(Config.DB_FILE) as db:
            cursor = await db.execute(
                "INSERT INTO payments (user_id, package_id, amount, utr) VALUES (?, ?, ?, ?)",
                (user_id, package_id, pkg['price'], utr)
            )
            await db.commit()
            return cursor.lastrowid
            
    @staticmethod
    async def update_payment_status(payment_id: int, status: str, admin_notes: str = ""):
        async with aiosqlite.connect(Config.DB_FILE) as db:
            await db.execute("UPDATE payments SET status = ?, admin_notes = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (status, admin_notes, payment_id))
            await db.commit()

# ==============================================================================
# API CLIENT
# ==============================================================================

class BrevistayClient:
    def __init__(self, process_id: int, ref_code: str):
        self.process_id = process_id
        self.ref_code = ref_code
        self.base_url = Config.BREVISTAY_BASE_URL
        self.web_url = Config.BREVISTAY_WEB_URL
        self.token = None
        self.user_data = {}
        
        self.default_headers = {
            "User-Agent": "okhttp/4.12.0",
            "Accept-Encoding": "gzip",
            "brevi-channel": "ANDROID",
            "brevi-channel-version": "6.0.8",
            "Content-Type": "application/json; charset=UTF-8",
            "Host": "cst.brevistay.com",
            "Connection": "Keep-Alive"
        }
        self.web_headers = {
            "User-Agent": "Mozilla/5.0 (Linux; Android 10; Mobile) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.77 Mobile Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "X-Requested-With": "com.brevistay.customer",
            "Referer": "https://www.brevistay.com/"
        }

    async def _log(self, msg: str):
        logger.info(f"[Process {self.process_id}] {msg}")
        if self.process_id != 0:
            await ProcessManager.update_process(self.process_id, "PROCESSING", f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

    async def _request(self, method: str, url: str, **kwargs) -> dict:
        try:
            if method.upper() == "POST":
                resp = await HTTP.session.post(url, **kwargs)
            else:
                resp = await HTTP.session.get(url, **kwargs)
            
            if "application/json" not in resp.headers.get("Content-Type", "").lower():
                return {"status": "FAILED", "msg": f"Cloudflare / WAF Blocked Request (HTTP {resp.status_code})"}
                
            data = resp.json()
            return data
            
        except Exception as e:
            return {"status": "FAILED", "msg": f"Connection Error: {str(e)}"

    @staticmethod
    def generate_random_name() -> tuple:
        return random.choice(INDIAN_FIRST_NAMES), random.choice(INDIAN_LAST_NAMES)

    @staticmethod
    def generate_random_email(first_name: str, last_name: str, mobile: str) -> str:
        if Config.CATCH_ALL_DOMAIN:
            random_string = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
            return f"{first_name.lower()}{random_string}@{Config.CATCH_ALL_DOMAIN}"
            
        domains = ["gmail.com", "yahoo.com", "outlook.com", "protonmail.com", "hotmail.com"]
        return f"{first_name.lower()}.{last_name.lower()}{mobile[-4:]}{random.randint(100,999)}@{random.choice(domains)}"

    @staticmethod
    def derive_name_from_email(email: str) -> tuple:
        username = email.split("@")[0]
        clean_name = re.sub(r'[^a-zA-Z]', '', username)
        if not clean_name:
            clean_name = "User"
            
        if len(clean_name) >= 6:
            mid = len(clean_name) // 2
            return clean_name[:mid].capitalize(), clean_name[mid:].capitalize()
        else:
            return clean_name.capitalize(), "Kumar"

    async def send_login_otp(self, mobile: str) -> dict:
        url = f"{self.base_url}/app-api/login"
        payload = {"is_otp": 1, "is_password": 0, "mobile": mobile, "otp": 123456, "password": ""}
        return await self._request("POST", url, json=payload, headers=self.default_headers, timeout=15)

    async def login_existing_user(self, mobile: str, otp: str) -> dict:
        url = f"{self.base_url}/app-api/verify-user"
        payload = {
            "channel": "MOBILE", "is_otp": 1, "is_password": 0,
            "mobile": mobile, "otp": int(otp), "ref_code": self.ref_code
        }
        data = await self._request("POST", url, json=payload, headers=self.default_headers, timeout=20)
        if data.get("status") == "SUCCESS":
            self._extract_token(data)
        return data

    async def register_new_user(self, email: str, mobile: str, name: str, last_name: str, otp: str) -> dict:
        url = f"{self.base_url}/app-api/verify-user"
        payload = {
            "channel": "MOBILE", "email": email, "is_otp": 1, "is_password": 0,
            "lastName": last_name, "mobile": int(mobile), "name": name,
            "otp": int(otp), "password": "User@123", "ref_code": self.ref_code
        }
        data = await self._request("POST", url, json=payload, headers=self.default_headers, timeout=20)
        if data.get("status") == "SUCCESS":
            self._extract_token(data)
        return data

    def _extract_token(self, data: dict):
        if "token" in data:
            self.token = data["token"]
            self.user_data = {
                "name": data.get("user_first_name", data.get("name")),
                "email": data.get("user_email_id", data.get("email")),
                "mobile": data.get("user_mobile_number", data.get("mobile")),
                "wallet": data.get("usr_wallet_bal", 0)
            }
            self.default_headers["authorization"] = f"Bearer {self.token}"
            self.web_headers["authorization"] = f"Bearer {self.token}"

    async def get_user_profile(self) -> dict:
        url = f"{self.base_url}/app-api/user-profile"
        return await self._request("POST", url, data="", headers=self.default_headers, timeout=15)

    async def resend_email_verification(self) -> dict:
        url = f"{self.web_url}/cst/app-api/resend_email_verification"
        return await self._request("GET", url, headers=self.web_headers, timeout=15)

# ==============================================================================
# QUEUE & WORKER ENGINE
# ==============================================================================

class TaskEngine:
    queue = None
    workers = []

    @classmethod
    async def start_workers(cls, bot: Bot):
        cls.queue = asyncio.Queue()
        logger.info(f"Starting {Config.WORKER_CONCURRENCY} Background Task Workers...")
        for i in range(Config.WORKER_CONCURRENCY):
            task = asyncio.create_task(cls._worker(i, bot))
            cls.workers.append(task)

    @classmethod
    async def stop_workers(cls):
        for w in cls.workers:
            w.cancel()
        await asyncio.gather(*cls.workers, return_exceptions=True)

    @classmethod
    async def add_task(cls, payload: dict):
        await cls.queue.put(payload)

    @classmethod
    async def _worker(cls, worker_id: int, bot: Bot):
        while True:
            try:
                task = await cls.queue.get()
                await cls._execute_task(task, bot)
                cls.queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Worker {worker_id} Error: {e}")

    @classmethod
    async def _execute_task(cls, task: dict, bot: Bot):
        process_id = task["process_id"]
        user_id = task["user_id"]
        mobile = task["mobile"]
        otp = task["otp"]
        is_registered = task["is_registered"]
        custom_email = task.get("email")
        msg_id = task["msg_id"]
        is_admin = user_id in Config.ADMIN_IDS
        
        await ProcessManager.update_process(process_id, "RUNNING")
        
        ref_code = await UserManager.get_website_refcode(user_id) or Config.DEFAULT_REF_CODE
        client = BrevistayClient(process_id, ref_code)
        final_msg = ""
        
        try:
            await client._log(f"Starting Engine. Target: {mobile}")
            try:
                await bot.edit_message_text(chat_id=user_id, message_id=msg_id, text="🚀 Process Engine Started...\n\n📡 Verifying OTP & Authenticating...")
            except TelegramAPIError: pass

            if is_registered:
                await client._log("Flow: Existing User Login")
                resp = await client.login_existing_user(mobile, otp)
            else:
                await client._log("Flow: New User Registration")
                
                if custom_email:
                    email = custom_email
                    fname, lname = client.derive_name_from_email(email) 
                else:
                    fname, lname = client.generate_random_name()
                    email = client.generate_random_email(fname, lname, mobile)
                
                resp = await client.register_new_user(email, mobile, fname, lname, otp)

            if resp.get("status") == "SUCCESS":
                await client._log("Authentication Successful.")
                try:
                    await bot.edit_message_text(chat_id=user_id, message_id=msg_id, text="⏳ Authentication Success!\n\n📊 Fetching Profile Data...")
                except TelegramAPIError: pass
                
                prof = await client.get_user_profile()
                if prof.get("status") == "SUCCESS":
                    client.user_data["wallet"] = prof.get("usr_wallet_bal", 0)

                try:
                    await bot.edit_message_text(chat_id=user_id, message_id=msg_id, text="⏳ Finalizing...\n\n📨 Triggering Email Verification...")
                except TelegramAPIError: pass
                
                await client.resend_email_verification()

                final_msg = (
                    f"✅ PROCESS COMPLETED SUCCESSFULLY\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"👤 Name: {client.user_data.get('name', 'N/A')}\n"
                    f"📱 Mobile: {client.user_data.get('mobile', mobile)}\n"
                    f"📧 Email: {client.user_data.get('email', 'N/A')}\n"
                    f"🎁 Ref Code Used: {ref_code or 'None'}\n"
                    f"━━━━━━━━━━━━━━━━━━━━{Config.FOOTER_TEXT}"
                )
                await ProcessManager.update_process(process_id, "COMPLETED", "Task finished successfully.")
            else:
                err = resp.get("msg", "Unknown API Error")
                await client._log(f"Authentication Failed: {err}")
                final_msg = f"❌ PROCESS FAILED\n\n⚠️ Error: {err}\n\nPlease try again with a different number.{Config.FOOTER_TEXT}"
                await ProcessManager.update_process(process_id, "FAILED", f"Auth Failed: {err}")

        except Exception as e:
            logger.error(f"Execution Error on Process {process_id}: {e}")
            final_msg = f"❌ CRITICAL ERROR\n\n⚠️ An internal exception occurred during execution.\n\nPlease try again.{Config.FOOTER_TEXT}"
            await ProcessManager.update_process(process_id, "FAILED", f"Exception: {str(e)}")
        
        finally:
            try:
                await bot.edit_message_text(chat_id=user_id, message_id=msg_id, text=final_msg, reply_markup=UI.home_kb())
            except TelegramAPIError:
                await bot.send_message(chat_id=user_id, text=final_msg, reply_markup=UI.home_kb())

# ==============================================================================
# UI BUILDERS
# ==============================================================================

class UI:
    @staticmethod
    def home_kb() -> InlineKeyboardMarkup:
        b = InlineKeyboardBuilder()
        b.button(text="👑 VIP Zone / Buy Access", callback_data="ui_vip_zone")
        b.button(text="📝 Set Ref Code", callback_data="ui_set_ref")
        b.button(text="📤 Upload Script (.py/.zip)", callback_data="ui_upload_script")
        b.button(text="⚡ Start Process", callback_data="ui_start_proc")
        b.button(text="📊 Refer & Leaderboard", callback_data="ui_stats")
        b.adjust(2)
        return b.as_markup()

    @staticmethod
    def package_kb() -> InlineKeyboardMarkup:
        b = InlineKeyboardBuilder()
        for pkg_id, pkg_info in Config.PACKAGES.items():
            b.button(text=f"{pkg_info['name']} - ₹{pkg_info['price']}", callback_data=f"pkg_{pkg_id}")
        b.button(text="⬅ Back", callback_data="ui_home")
        b.adjust(1)
        return b.as_markup()

    @staticmethod
    def back_kb(callback_data: str = "ui_home") -> InlineKeyboardMarkup:
        b = InlineKeyboardBuilder()
        b.button(text="⬅ Back", callback_data=callback_data)
        return b.as_markup()

    @staticmethod
    def cancel_kb() -> InlineKeyboardMarkup:
        b = InlineKeyboardBuilder()
        b.button(text="❌ Cancel", callback_data="ui_home")
        return b.as_markup()

    @staticmethod
    def remove_ref_kb() -> InlineKeyboardMarkup:
        b = InlineKeyboardBuilder()
        b.button(text="🗑 Remove Code", callback_data="action_remove_ref")
        b.button(text="❌ Cancel", callback_data="ui_home")
        b.adjust(1)
        return b.as_markup()
        
    @staticmethod
    def admin_kb() -> InlineKeyboardMarkup:
        b = InlineKeyboardBuilder()
        b.button(text="📊 Statistics", callback_data="adm_stats")
        b.button(text="📢 Broadcast", callback_data="adm_broadcast")
        b.button(text="👮 Users", callback_data="adm_users")
        b.button(text="🎁 Gift Cards", callback_data="adm_gifts")
        b.button(text="⚙️ Maintenance", callback_data="adm_maintenance")
        b.adjust(2)
        return b.as_markup()

# ==============================================================================
# FSM STATES
# ==============================================================================

class UserFlow(StatesGroup):
    wait_ref_code = State()
    wait_mobile = State()
    wait_email = State()
    wait_otp = State()
    wait_utr = State()
    wait_file = State()

class AdminFlow(StatesGroup):
    wait_broadcast = State()
    wait_gift_points = State()
    wait_gift_uses = State()
    wait_user_id = State()
    wait_user_points = State()

# ==============================================================================
# MIDDLEWARES
# ==============================================================================

class AuthMiddleware(BaseMiddleware):
    async def __call__(self, handler: Callable, event: Any, data: Dict[str, Any]) -> Any:
        user = event.from_user
        if not user: return await handler(event, data)

        if await UserManager.is_banned(user.id):
            if isinstance(event, Message): await event.answer("❌ You are banned from using this bot.")
            elif isinstance(event, CallbackQuery): await event.answer("❌ You are banned.", show_alert=True)
            return

        is_admin = user.id in Config.ADMIN_IDS
        if is_admin: return await handler(event, data)

        # Maintenance Check
        m_mode = await MemCache.get("bot:maintenance")
        if m_mode == "1":
            msg = "⚙️ Bot is currently under maintenance. Please try again later."
            if isinstance(event, Message): await event.answer(msg)
            elif isinstance(event, CallbackQuery): await event.answer("Maintenance Break!", show_alert=True)
            return

        # ✅ Hosting Access Check (Non-Admins only)
        if not await UserManager.is_hosting_active(user.id):
            msg = "⛔ Your Hosting Access has expired or is inactive.\n\n🔰 Use /start to check your current plan or buy a new VIP subscription."
            if isinstance(event, Message): await event.answer(msg)
            elif isinstance(event, CallbackQuery): await event.answer("Access Expired! Check /start", show_alert=True)
            return

        # Basic user registration check
        db_user = await UserManager.get_user(user.id)
        if not db_user:
            if isinstance(event, Message) and event.text and event.text.startswith('/start'):
                pass
            else:
                if isinstance(event, Message): await event.answer("⚠️ Please send /start first to register.")
                elif isinstance(event, CallbackQuery): await event.answer("Please send /start first.", show_alert=True)
                return

        return await handler(event, data)

class ThrottlingMiddleware(BaseMiddleware):
    async def __call__(self, handler: Callable, event: Any, data: Dict[str, Any]) -> Any:
        user = event.from_user
        if not user or user.id in Config.ADMIN_IDS: return await handler(event, data)

        key = f"throttle:{user.id}"
        count = await MemCache.incr(key)
        if count == 1: await MemCache.expire(key, 1)
        if count > 3:
            if count == 4 and isinstance(event, Message):
                await event.answer("⚠️ Please slow down! You are sending requests too fast.")
            return

        return await handler(event, data)

# ==============================================================================
# ROUTERS SETUP
# ==============================================================================

router = Router()
router.message.middleware(AuthMiddleware())
router.message.middleware(ThrottlingMiddleware())
router.callback_query.middleware(AuthMiddleware())
router.callback_query.middleware(ThrottlingMiddleware())

# ==============================================================================
# START / HOME HANDLERS
# ==============================================================================

WELCOME_TEXT = lambda name: (
    f"🌶️ Secret Sauce welcomes you, {name}!\n\n"
    f"<b>New Users get 1 Day FREE Hosting!</b>\n"
    f"Invite 4 friends to get +2 Extra Days.\n\n"
    f"Here's the recipe:\n"
    f"1️⃣ Set your <b>Refer Code</b> so we credit the right person\n"
    f"2️⃣ Hit <b>Start Process</b> and drop in fresh numbers\n"
    f"3️⃣ Sit back & let the sauce do its thing 🔥\n\n"
    f"📢 Join us → @rajexpilot\n\n"
    f"⚡ Made by Aniket"
)

@router.message(CommandStart())
async def cmd_start(message: Message, command: Command, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    args = command.args
    ref_id = args if args and args.isdigit() else "none"
    await state.update_data(ref_id=ref_id)

    # Register User and Grant 1 Day Free Trial
    db_user = await UserManager.get_user(user_id)
    if not db_user:
        referrer_id = int(ref_id) if ref_id != "none" and ref_id.isdigit() else None
        await UserManager.register_user(user_id, message.from_user.username, message.from_user.first_name, referrer_id)
        await UserManager.grant_hosting_access(user_id, Config.FREE_TRIAL_DAYS)
        
        # Referral Logic (4 referrals = +2 days)
        if referrer_id and referrer_id != user_id:
            async with aiosqlite.connect(Config.DB_FILE) as db:
                async with db.execute("SELECT COUNT(*) FROM telegram_referrals WHERE referrer_id = ?", (referrer_id,)) as cur:
                    ref_count = (await cur.fetchone())[0]
            
            if ref_count > 0 and ref_count % Config.REFERRALS_FOR_BONUS == 0:
                await UserManager.grant_hosting_access(referrer_id, Config.REFERRAL_DAYS_BONUS)
                try:
                    await message.bot.send_message(
                        referrer_id, 
                        f"🎉 You have reached {ref_count} referrals! You earned {Config.REFERRAL_DAYS_BONUS} extra days of hosting!"
                    )
                except: pass

    await message.answer(WELCOME_TEXT(message.from_user.first_name), reply_markup=UI.home_kb())

@router.callback_query(F.data == "ui_home")
async def cb_home(call: CallbackQuery, state: FSMContext):
    await state.clear()
    text = "🌶️ Secret Sauce | Main Menu:"
    try:
        await call.message.edit_text(text, reply_markup=UI.home_kb())
    except TelegramAPIError:
        pass
    finally:
        await call.answer()

# ==============================================================================
# VIP ZONE / PAYMENTS HANDLERS
# ==============================================================================

@router.callback_query(F.data == "ui_vip_zone")
async def cb_vip_zone(call: CallbackQuery):
    expiry = await UserManager.get_hosting_expiry(call.from_user.id)
    expiry_str = datetime.fromtimestamp(expiry).strftime('%Y-%m-%d') if expiry > time.time() else "Expired"
    
    text = (
        f"👑 <b>VIP SUBSCRIPTION</b> 👑\n\n"
        f"Current Plan Status: {'Active until ' + expiry_str if expiry > time.time() else '❌ Expired / Not Active'}\n"
        f"Get hosting access to continue your OTP processes.\n\n"
        f"💎 <b>Subscription Plans:</b>\n"
        f"1 Month → ₹99\n"
        f"6 Months → ₹499\n"
        f"1 Year → ₹899\n\n"
        f"💳 UPI ID: {Config.UPI_ID}\n\n"
        f"Select a package below:"
    )
    await call.message.edit_text(text, reply_markup=UI.package_kb())

@router.callback_query(F.data.startswith("pkg_"))
async def cb_select_package(call: CallbackQuery, state: FSMContext):
    pkg_id = call.data.split("_")[1]
    pkg = Config.PACKAGES[pkg_id]
    await state.update_data(pkg_id=pkg_id)
    
    text = (
        f"🛒 <b>Selected Plan:</b> {pkg['name']}\n"
        f"💰 Price: <b>₹{pkg['price']}</b>\n"
        f"📅 Duration: {pkg['days']} Days\n\n"
        f"⚠️ <b>Make payment to UPI:</b>\n"
        f"UPI ID: <code>{Config.UPI_ID}</code>\n\n"
        f"📸 Scan the QR or pay via UPI.\n"
        f"After payment, please send the <b>UTR/Transaction ID</b> in a message below."
    )
    try:
        await call.message.delete()
        await call.message.answer_photo(
            photo=FSInputFile("upi_qr.png"), # Make sure you put your QR image here
            caption=text,
            parse_mode=ParseMode.HTML
        )
    except FileNotFoundError:
        await call.message.edit_text(text + "\n\n❌ QR Image not found. Please upload 'upi_qr.png' to bot folder.", parse_mode=ParseMode.HTML)
        
    await state.set_state(UserFlow.wait_utr)

@router.message(StateFilter(UserFlow.wait_utr))
async def proc_utr(message: Message, state: FSMContext):
    utr = message.text.strip()
    if len(utr) < 5:
        return await message.answer("❌ Invalid UTR. Please enter the correct Transaction ID.")
    
    data = await state.get_data()
    pkg_id = data['pkg_id']
    pkg = Config.PACKAGES[pkg_id]
    
    payment_id = await AdminManager.create_payment_request(message.from_user.id, pkg_id, utr)
    await state.clear()
    
    await message.answer(
        f"✅ Payment request submitted!\n\nPackage: {pkg['name']}\nAmount: ₹{pkg['price']}\nUTR: {utr}\n\n⏳ Please wait for Admin Approval.{Config.FOOTER_TEXT}"
    )
    
    # Notify Admins
    for admin_id in Config.ADMIN_IDS:
        try:
            link = f"<a href='tg://user?id={message.from_user.id}'>User</a>"
            await message.bot.send_message(
                chat_id=admin_id,
                text=(
                    f"🛒 <b>NEW PAYMENT REQUEST</b>\n"
                    f"ID: #{payment_id}\n"
                    f"User: {link} ({message.from_user.id})\n"
                    f"Package: {pkg['name']}\n"
                    f"Amount: ₹{pkg['price']}\n"
                    f"UTR: <code>{utr}</code>\n\n"
                    f"Action:"
                ),
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardBuilder().row(
                    InlineKeyboardButton(text="✅ Approve", callback_data=f"adm_pay_app_{payment_id}_{message.from_user.id}_{pkg_id}"),
                    InlineKeyboardButton(text="❌ Reject", callback_data=f"adm_pay_rej_{payment_id}_{message.from_user.id}")
                ).as_markup()
            )
        except Exception as e: pass

# ==============================================================================
# ADMIN PAYMENT APPROVAL
# ==============================================================================

@router.callback_query(F.data.startswith("adm_pay_"))
async def cb_admin_payment_action(call: CallbackQuery):
    if call.from_user.id not in Config.ADMIN_IDS:
        return await call.answer("You are not authorized.", show_alert=True)
        
    parts = call.data.split("_")
    action = parts[3] # "app" or "rej"
    payment_id = int(parts[4])
    user_id = int(parts[5])
    
    if action == "app":
        pkg_id = parts[6]
        pkg = Config.PACKAGES[pkg_id]
        await UserManager.grant_hosting_access(user_id, pkg['days'])
        await AdminManager.update_payment_status(payment_id, "APPROVED")
        await call.message.edit_text("✅ Payment Approved. Hosting Access Granted.", reply_markup=None)
        try:
            await call.bot.send_message(
                chat_id=user_id,
                text=f"✅ <b>PAYMENT APPROVED!</b>\n\nYour subscription for <b>{pkg['name']}</b> is now active.\nEnjoy your free hosting! \n\n{Config.FOOTER_TEXT}",
                parse_mode=ParseMode.HTML
            )
        except: pass
        
    elif action == "rej":
        await AdminManager.update_payment_status(payment_id, "REJECTED")
        await call.message.edit_text("❌ Payment Rejected.", reply_markup=None)
        try:
            await call.bot.send_message(
                chat_id=user_id,
                text="❌ <b>PAYMENT REJECTED</b>\n\nYour payment request was rejected by Admin.\nPlease check your UTR or contact support."
            )
        except: pass
        
    await call.answer()

# ==============================================================================
# ADMIN MANUAL GRANT
# ==============================================================================

@router.message(Command("grant"))
async def cmd_grant(message: Message, command: Command):
    if message.from_user.id not in Config.ADMIN_IDS: return
    if not command.args:
        return await message.answer("Usage: /grant <user_id> <days>")
    
    args = command.args.split()
    if len(args) != 2 or not args[0].isdigit() or not args[1].isdigit():
        return await message.answer("Usage: /grant <user_id> <days>")
        
    user_id, days = int(args[0]), int(args[1])
    await UserManager.grant_hosting_access(user_id, days)
    await message.answer(f"✅ Granted {days} days of hosting to user {user_id}.")
    
    try:
        await message.bot.send_message(
            user_id, 
            f"🎉 <b>Admin Grant!</b>\n\nYou have been given <b>{days} days</b> of hosting access!\n\nHappy automations! \n{Config.FOOTER_TEXT}", 
            parse_mode=ParseMode.HTML
        )
    except: pass

# ==============================================================================
# FILE UPLOAD HANDLER (.py / .zip)
# ==============================================================================

@router.callback_query(F.data == "ui_upload_script")
async def cb_upload_script(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text("📤 <b>Upload your script</b>\n\nSend a <b>.py</b> (Python) or <b>.zip</b> file below.\n\nWe will store it for your worker processes.", reply_markup=UI.cancel_kb())
    await state.set_state(UserFlow.wait_file)

@router.message(F.document & StateFilter(UserFlow.wait_file))
async def handle_upload(message: Message, state: FSMContext):
    doc = message.document
    file_ext = "." + doc.file_name.split(".")[-1]
    
    if file_ext.lower() not in Config.ALLOWED_EXTENSIONS:
        return await message.answer(f"❌ Only {', '.join(Config.ALLOWED_EXTENSIONS)} files are allowed.")
    
    await state.clear()
    os.makedirs(Config.UPLOAD_DIR, exist_ok=True)
    
    file_path = os.path.join(Config.UPLOAD_DIR, f"{message.from_user.id}_{doc.file_name}")
    await message.bot.download_file(file_id=doc.file_id, destination=file_path)
    
    await message.answer(
        f"✅ File uploaded successfully!\n\n📁 File: {doc.file_name}\n📂 Saved to: {file_path}\n\nYou can now run this script via your hosting process.\n\n{Config.FOOTER_TEXT}"
    )

# ==============================================================================
# REFERRAL & LEADERBOARD
# ==============================================================================

@router.callback_query(F.data == "ui_stats")
async def cb_stats(call: CallbackQuery):
    user_stats = await UserManager.get_stats(call.from_user.id)
    leaders = await UserManager.get_leaderboard(10)
    
    text = f"📊 Global Leaderboard 📊\n━━━━━━━━━━━━━━━━━━━━\n"
    for i, l in enumerate(leaders, 1):
        medal = "🥇" if i==1 else "🥈" if i==2 else "🥉" if i==3 else "👤"
        text += f"{medal} {l['first_name'][:15]} | ⚡ {l['total_processes']} | 👥 {l['total_referrals']} | 💎 {l['points']}\n"
        
    text += f"\n━━━━━━━━━━━━━━━━━━━━\nYour Stats:\n💎 Points: {user_stats['points']}\n⚡ Total Runs: {user_stats['total_processes']}\n👥 Total Invites: {user_stats['total_refs']}\n{Config.FOOTER_TEXT}"
    
    try:
        await call.message.edit_text(text, reply_markup=UI.back_kb())
    except TelegramAPIError:
        pass
    finally:
        await call.answer()

@router.callback_query(F.data == "ui_refer")
async def cb_refer(call: CallbackQuery):
    bot_info = await call.bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start={call.from_user.id}"
    stats = await UserManager.get_stats(call.from_user.id)
    
    text = (
        f"🎁 TELEGRAM REFERRAL SYSTEM 🎁\n\n"
        f"💵 Reward: {Config.POINTS_PER_REFERRAL} Points per referral\n"
        f"⚡ Cost: 1 Point = 1 Process\n\n"
        f"👥 Total Referrals: {stats['total_refs']}\n"
        f"💎 Current Points: {stats['points']}\n\n"
        f"🔗 Your Invite Link:\n{ref_link}"
    )
    b = InlineKeyboardBuilder()
    b.button(text="↗️ Share Link", url=f"https://t.me/share/url?url={ref_link}&text=Join%20this%20awesome%20automation%20bot!")
    b.button(text="⬅ Back", callback_data="ui_home")
    b.adjust(1)
    
    try:
        await call.message.edit_text(text, reply_markup=b.as_markup())
    except TelegramAPIError:
        pass
    finally:
        await call.answer()

# ==============================================================================
# SET REFERRAL CODE
# ==============================================================================

@router.callback_query(F.data == "ui_set_ref")
async def cb_set_ref(call: CallbackQuery, state: FSMContext):
    user_id = call.from_user.id
    current_code = await UserManager.get_website_refcode(user_id)
    
    if current_code:
        text = (
            f"⚠️ Referral Code Already Set\n\n"
            f"Your current website referral code is:\n{current_code}\n\n"
            f"This code is injected during the API registration process.\n"
            f"Do you want to remove it to add a new one?"
        )
        await call.message.edit_text(text, reply_markup=UI.remove_ref_kb())
    else:
        text = "📝 Set Target Website Referral Code\n\nPlease enter the exact referral code you want the bot to use during the Brevistay registration process.\n\nSend the code in chat now."
        await call.message.edit_text(text, reply_markup=UI.cancel_kb())
        await state.set_state(UserFlow.wait_ref_code)

@router.callback_query(F.data == "action_remove_ref")
async def cb_remove_ref(call: CallbackQuery, state: FSMContext):
    await UserManager.remove_website_refcode(call.from_user.id)
    await call.answer("Code removed successfully!", show_alert=True)
    text = "📝 Set Target Website Referral Code\n\nPlease enter the exact referral code you want the bot to use.\n\nSend the code in chat now."
    await state.set_state(UserFlow.wait_ref_code)
    await call.message.edit_text(text, reply_markup=UI.cancel_kb())

@router.message(StateFilter(UserFlow.wait_ref_code))
async def process_ref_code(message: Message, state: FSMContext):
    code = message.text.strip()
    if len(code) < 3 or len(code) > 20:
        return await message.answer("❌ Invalid code length. Try again or Cancel.", reply_markup=UI.cancel_kb())
        
    await UserManager.set_website_refcode(message.from_user.id, code)
    await state.clear()
    await message.answer(f"✅ Code Saved Successfully!\n\nYour target referral code is now: {code}", reply_markup=UI.back_kb())

# ==============================================================================
# PROCESS ENGINE
# ==============================================================================

@router.callback_query(F.data == "ui_start_proc")
async def cb_start_process(call: CallbackQuery, state: FSMContext):
    user_id = call.from_user.id
    ref_code = await UserManager.get_website_refcode(user_id) or Config.DEFAULT_REF_CODE

    text = f"⚡ START PROCESS ENGINE ⚡\n━━━━━━━━━━━━━━━━━━━━\nTarget Code: {ref_code}\n━━━━━━━━━━━━━━━━━━━━\n\n📱 Please enter the 10-digit Mobile Number to use for registration/login."
    await call.message.edit_text(text, reply_markup=UI.cancel_kb())
    await state.set_state(UserFlow.wait_mobile)

@router.message(StateFilter(UserFlow.wait_mobile))
async def process_mobile_input(message: Message, state: FSMContext):
    mobile = message.text.strip()
    if not mobile.isdigit() or len(mobile) != 10:
        return await message.answer("❌ Invalid mobile number! Must be exactly 10 digits.", reply_markup=UI.cancel_kb())
        
    await state.update_data(mobile=mobile)
    wait_msg = await message.answer("📡 Sending OTP via Brevistay API...")
    
    user_id = message.from_user.id
    ref_code = await UserManager.get_website_refcode(user_id) or Config.DEFAULT_REF_CODE
    client = BrevistayClient(0, ref_code)
    
    try:
        resp = await client.send_login_otp(mobile)
        
        if str(resp.get("is_otp_sent")) == "1" or resp.get("status") == "SUCCESS":
            is_registered = str(resp.get("is_user_registered")) == "1"

            if is_registered:
                await state.clear()
                await wait_msg.edit_text(
                    f"⚠️ Already Registered!\n\n"
                    f"📱 Number: {mobile}\n"
                    f"👤 Status: Existing User\n\n"
                    f"This number is already registered on Brevistay. Please use a fresh unregistered number.",
                    reply_markup=UI.back_kb()
                )
                return

            await state.update_data(is_registered=False)

            if not Config.CATCH_ALL_DOMAIN:
                text = f"✅ OTP Sent Successfully!\n\n📱 Number: {mobile}\n👤 Status: New User (Registration)\n\n⚠️ Bouncify Protection Active:\nPlease enter a real/valid email address to bypass email verification:"
                await wait_msg.edit_text(text, reply_markup=UI.cancel_kb())
                await state.set_state(UserFlow.wait_email)
            else:
                text = f"✅ OTP Sent Successfully!\n\n📱 Number: {mobile}\n👤 Status: New User (Auto Catch-All)\n\n🔐 Enter the 6-digit OTP received:"
                await wait_msg.edit_text(text, reply_markup=UI.cancel_kb())
                await state.set_state(UserFlow.wait_otp)
        else:
            await state.clear()
            await wait_msg.edit_text(f"❌ Failed to send OTP.\nAPI Response: {resp.get('msg', 'Unknown Error')}", reply_markup=UI.back_kb())
    except Exception as e:
        logger.error(f"OTP Send Error: {e}")
        await state.clear()
        await wait_msg.edit_text("❌ Connection Error. Failed to reach API.", reply_markup=UI.back_kb())

@router.message(StateFilter(UserFlow.wait_email))
async def process_email_input(message: Message, state: FSMContext):
    email = message.text.strip()
    if "@" not in email or "." not in email:
        return await message.answer("❌ Please enter a valid email address format.", reply_markup=UI.cancel_kb())
        
    await state.update_data(email=email)
    await message.answer("🔐 Enter the 6-digit OTP received on your mobile:", reply_markup=UI.cancel_kb())
    await state.set_state(UserFlow.wait_otp)

@router.message(StateFilter(UserFlow.wait_otp))
async def process_otp_input(message: Message, state: FSMContext):
    otp = message.text.strip()
    if not otp.isdigit(): return await message.answer("❌ Invalid OTP format. Enter digits only.", reply_markup=UI.cancel_kb())
        
    data = await state.get_data()
    mobile = data.get("mobile")
    is_registered = data.get("is_registered")
    email = data.get("email")
    user_id = message.from_user.id
    
    process_id = await ProcessManager.create_process(user_id, mobile)
    wait_msg = await message.answer("⚙️ Adding task to background worker pool...")
    
    await TaskEngine.add_task({
        "process_id": process_id, "user_id": user_id, "mobile": mobile,
        "otp": otp, "is_registered": is_registered, "email": email, "msg_id": wait_msg.message_id
    })
    await state.clear()
    await wait_msg.edit_text("⌛ Task Queued!\n\nYour process is running in the background. You will receive live updates here.")

# ==============================================================================
# ADMIN PANEL
# ==============================================================================

@router.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext):
    if message.from_user.id not in Config.ADMIN_IDS: return
    await state.clear()
    await message.answer("👑 ADMINISTRATION PANEL 👑\nSelect an operation:", reply_markup=UI.admin_kb())

@router.callback_query(F.data == "ui_admin_main")
async def cb_admin_main(call: CallbackQuery, state: FSMContext):
    if call.from_user.id not in Config.ADMIN_IDS: return
    await state.clear()
    text = "👑 ADMINISTRATION PANEL 👑\nSelect an operation:"
    try:
        await call.message.edit_text(text, reply_markup=UI.admin_kb())
    except TelegramAPIError:
        pass
    finally:
        await call.answer()

@router.callback_query(F.data == "adm_stats")
async def cb_adm_stats(call: CallbackQuery):
    if call.from_user.id not in Config.ADMIN_IDS: return
    stats = await AdminManager.get_stats()
    text = f"📊 System Statistics\n━━━━━━━━━━━━━━━━━━━━\n👥 Total Users: {stats.get('users',0)}\n🔗 Total Referrals: {stats.get('referrals',0)}\n⚙️ Total Processes: {stats.get('processes',0)}\n✅ Completed Runs: {stats.get('completed',0)}\n⚡ Active Workers: {Config.WORKER_CONCURRENCY}\n📋 Queue Size: {TaskEngine.queue.qsize() if TaskEngine.queue else 0}\n"
    await call.message.edit_text(text, reply_markup=UI.back_kb("ui_admin_main"))

@router.callback_query(F.data == "adm_maintenance")
async def cb_adm_maintenance(call: CallbackQuery):
    if call.from_user.id not in Config.ADMIN_IDS: return
    curr = await MemCache.get("bot:maintenance")
    new_val = "0" if curr == "1" else "1"
    await MemCache.set("bot:maintenance", new_val)
    status = "🔴 ON (Bot Disabled)" if new_val == "1" else "🟢 OFF (Bot Active)"
    await call.answer(f"Maintenance Mode is now {status}", show_alert=True)

@router.callback_query(F.data == "adm_broadcast")
async def cb_adm_broadcast(call: CallbackQuery, state: FSMContext):
    if call.from_user.id not in Config.ADMIN_IDS: return
    await call.message.edit_text("📢 Send the message (Text/Photo/Video) you want to broadcast. Or press Cancel.", reply_markup=UI.back_kb("ui_admin_main"))
    await state.set_state(AdminFlow.wait_broadcast)

@router.message(StateFilter(AdminFlow.wait_broadcast))
async def process_broadcast(message: Message, state: FSMContext):
    await state.clear()
    status_msg = await message.answer("📢 Preparing broadcast...")
    
    users = []
    async with aiosqlite.connect(Config.DB_FILE) as db:
        async with db.execute("SELECT user_id FROM users") as cursor:
            users = await cursor.fetchall()
    
    total, success, failed = len(users), 0, 0
    await status_msg.edit_text(f"📢 Broadcasting to {total} users...\nProgress: 0%")
    
    for i, u in enumerate(users):
        try:
            await message.send_copy(chat_id=u[0])
            success += 1
        except TelegramAPIError: failed += 1
        
        if i % 50 == 0 and i > 0:
            try: await status_msg.edit_text(f"📢 Broadcasting...\nProgress: {int((i/total)*100)}%\nSuccess: {success} | Failed: {failed}")
            except: pass
        await asyncio.sleep(0.05) 
        
    await status_msg.edit_text(f"✅ Broadcast Completed!\n\nTotal: {total}\nDelivered: {success}\nFailed: {failed}", reply_markup=UI.back_kb("ui_admin_main"))

@router.callback_query(F.data == "adm_users")
async def cb_adm_users(call: CallbackQuery, state: FSMContext):
    if call.from_user.id not in Config.ADMIN_IDS: return
    await call.message.edit_text("👮 User Moderation\n\nEnter the Telegram User ID you want to manage:", reply_markup=UI.back_kb("ui_admin_main"))
    await state.set_state(AdminFlow.wait_user_id)

@router.message(StateFilter(AdminFlow.wait_user_id))
async def proc_admin_userid(message: Message, state: FSMContext):
    if not message.text.isdigit(): return await message.answer("User ID must be numeric.")
    target_id = int(message.text)
    user = await UserManager.get_user(target_id)
    
    if not user:
        return await message.answer("❌ User not found in database.", reply_markup=UI.back_kb("adm_users"))
    
    await state.update_data(target_id=target_id)
    b = InlineKeyboardBuilder()
    b.button(text="🟢 Unban User" if user['is_banned'] else "🔴 Ban User", callback_data=f"adm_tgl_ban_{target_id}_{int(user['is_banned'])}")
    b.button(text="💰 Add Points", callback_data=f"adm_add_pts_{target_id}")
    b.button(text="⬅ Back", callback_data="adm_users")
    b.adjust(1)
    
    text = f"👤 User Profile\n\nID: {user['user_id']}\nName: {user['first_name']}\nPoints: {user['points']}\nTotal Runs: {user['total_processes']}\nBanned: {'YES 🔴' if user['is_banned'] else 'NO 🟢'}"
    await message.answer(text, reply_markup=b.as_markup())
    await state.set_state(None)

@router.callback_query(F.data.startswith("adm_tgl_ban_"))
async def cb_tgl_ban(call: CallbackQuery):
    parts = call.data.split("_")
    target_id = int(parts[3])
    currently_banned = bool(int(parts[4]))
    
    await UserManager.set_ban_status(target_id, not currently_banned)
    await call.answer("Ban status updated!", show_alert=True)
    await call.message.delete()
    
@router.callback_query(F.data.startswith("adm_add_pts_"))
async def cb_add_pts(call: CallbackQuery, state: FSMContext):
    target_id = int(call.data.split("_")[3])
    await state.update_data(target_id=target_id)
    await call.message.edit_text("Enter amount of Points to add (e.g. 10):", reply_markup=UI.back_kb("adm_users"))
    await state.set_state(AdminFlow.wait_user_points)

@router.message(StateFilter(AdminFlow.wait_user_points))
async def proc_add_pts(message: Message, state: FSMContext):
    if not message.text.lstrip('-').isdigit(): return await message.answer("Must be a valid integer.")
    data = await state.get_data()
    
    await UserManager.update_points(data['target_id'], int(message.text))
    await state.clear()
    await message.answer(f"✅ Successfully added {message.text} points to User ID {data['target_id']}.", reply_markup=UI.back_kb("adm_users"))

@router.callback_query(F.data == "adm_gifts")
async def cb_adm_gifts(call: CallbackQuery):
    if call.from_user.id not in Config.ADMIN_IDS: return
    b = InlineKeyboardBuilder()
    b.button(text="➕ Create Gift Card", callback_data="adm_gift_create")
    b.button(text="⬅ Back", callback_data="ui_admin_main")
    b.adjust(1)
    await call.message.edit_text("🎁 Gift Card Management", reply_markup=b.as_markup())

@router.callback_query(F.data == "adm_gift_create")
async def cb_adm_gift_create(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text("Enter amount of Points to embed in this Gift Card:", reply_markup=UI.cancel_kb())
    await state.set_state(AdminFlow.wait_gift_points)

@router.message(StateFilter(AdminFlow.wait_gift_points))
async def proc_gift_points(message: Message, state: FSMContext):
    if not message.text.isdigit(): return await message.answer("Numbers only.")
    await state.update_data(pts=int(message.text))
    await message.answer("Enter max number of uses (e.g., 1 for single-use, 100 for multi-use):")
    await state.set_state(AdminFlow.wait_gift_uses)

@router.message(StateFilter(AdminFlow.wait_gift_uses))
async def proc_gift_uses(message: Message, state: FSMContext):
    if not message.text.isdigit(): return await message.answer("Numbers only.")
    data = await state.get_data()
    uses, pts = int(message.text), data['pts']
    code = await AdminManager.create_giftcard(pts, uses, message.from_user.id)
    await state.clear()
    
    text = f"✅ Gift Card Created Successfully!\n\n🎟️ Code: {code}\n💎 Points: {pts}\n🔄 Max Uses: {uses}\n\nUsers can redeem this by sending /redeem {code}"
    await message.answer(text, reply_markup=UI.back_kb("adm_gifts"))

@router.message(Command("redeem"))
async def cmd_redeem(message: Message, command: Command):
    if not command.args: return await message.answer("❌ Usage: /redeem CODE", parse_mode=ParseMode.HTML)
    code = command.args.strip()
    success, msg, pts = await AdminManager.redeem_giftcard(code, message.from_user.id)
    
    if success: await message.answer(f"🎉 Redemption Successful!\n\n{msg}\n💰 You received +{pts} Points!")
    else: await message.answer(f"❌ Redemption Failed\n\n{msg}")

# ==============================================================================
# MAIN RUNNER & LIFECYCLE
# ==============================================================================

async def main():
    logger.info("Initializing Brevistay Engine...")
    
    await DB.init()
    await HTTP.init()
    
    bot = Bot(token=Config.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    
    await TaskEngine.start_workers(bot)
    
    logger.info("Engine is UP and Polling...")
    try:
        await dp.start_polling(bot)
    finally:
        logger.info("Shutting down Engine...")
        await TaskEngine.stop_workers()
        await HTTP.close()
        await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Engine stopped manually.")
    except RuntimeError as e:
        if "Event loop is closed" in str(e):
            logger.warning("Python 3.14 Event loop closed gracefully.")
        else:
            raise e
        
