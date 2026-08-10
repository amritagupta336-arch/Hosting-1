# ====================================================
#               MADE BY ANIKET
#     PRIME HOSTING SERVER v4.0 (ANDROID - UPI ONLY)
# ====================================================

import os
import sys
import sqlite3
import subprocess
import time
import random
import string
import threading
import zipfile
from datetime import datetime, timedelta
from telebot import TeleBot, types

# ==================== CONFIGURATION ====================
BOT_TOKEN = "8953813919:AAFKebGgZqCCZwjYwEYCMFiPwmBmtBfO5Uc"
BOT_USERNAME = "hostingbyaniket_bot"
ADMIN_ID = "8705755564"
ADMIN_USERNAME = "aniket9308"
CHANNEL_USERNAME = "aniket8757tg"

FREE_LIMIT = 2          # Free users get 2 bots (they also get 1 day trial)
PRIME_LIMIT = 5
HOST_DIR = "hosted_files"
MAX_LOG_SIZE_MB = 5

# ✅ UPI & QR
UPI_ID = "adityaraj5881@oksbi"
QR_IMAGE_PATH = "upi_qr.jpg"   # Place a QR image in the bot folder

# ✅ Prime Packages
PACKAGES = {
    "1_month":  {"label": "1 Month",  "days": 30,  "price": 99},
    "6_months": {"label": "6 Months", "days": 180, "price": 499},
    "1_year":   {"label": "1 Year",   "days": 365, "price": 899},
}

os.makedirs(HOST_DIR, exist_ok=True)

# ⚡ Multi-Threaded Bot
bot = TeleBot(BOT_TOKEN, threaded=True, num_threads=50)

# ==================== DATABASE ====================
def get_db():
    conn = sqlite3.connect("hosting_data.db", check_same_thread=False, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA busy_timeout=30000;")
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            is_prime INTEGER DEFAULT 0,
            prime_expire TEXT DEFAULT NULL,
            referred_by INTEGER DEFAULT NULL,
            referral_count INTEGER DEFAULT 0,
            trial_used INTEGER DEFAULT 0
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS hosted_bots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            filename TEXT,
            filepath TEXT,
            entry_file TEXT,       -- for zip: path to main .py
            logpath TEXT,
            pid INTEGER DEFAULT NULL,
            status TEXT DEFAULT 'stopped',
            auto_guard INTEGER DEFAULT 1,
            speed_boost INTEGER DEFAULT 0
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS prime_codes (
            code TEXT PRIMARY KEY,
            days INTEGER
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS pending_payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            package TEXT,
            days INTEGER,
            amount INTEGER,
            utr TEXT,
            status TEXT DEFAULT 'pending',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

init_db()

# ==================== HELPERS ====================
def register_user(user_id, ref_by=None):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
    if not c.fetchone():
        # New user gets 1 day free trial
        trial_days = 1
        expire = (datetime.now() + timedelta(days=trial_days)).strftime("%Y-%m-%d %H:%M:%S")
        if ref_by and ref_by != user_id:
            c.execute("INSERT INTO users (user_id, referred_by, is_prime, prime_expire, trial_used) VALUES (?, ?, 1, ?, 1)", 
                      (user_id, ref_by, expire))
            c.execute("UPDATE users SET referral_count = referral_count + 1 WHERE user_id = ?", (ref_by,))
            # Check referral rewards: 4 referrals = 2 days
            c.execute("SELECT referral_count FROM users WHERE user_id = ?", (ref_by,))
            ref_row = c.fetchone()
            if ref_row and ref_row['referral_count'] % 4 == 0:
                add_prime_days(ref_by, 2)
                try:
                    bot.send_message(ref_by, "🎉 **Referral Bonus!** You earned 2 days of FREE Prime VIP for 4 invites.")
                except:
                    pass
        else:
            c.execute("INSERT INTO users (user_id, is_prime, prime_expire, trial_used) VALUES (?, 1, ?, 1)", (user_id, expire))
        conn.commit()
    else:
        # If user already exists but trial not used, we don't add again
        pass
    conn.close()

def is_prime_user(user_id):
    if str(user_id) == ADMIN_ID:
        return True
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT is_prime, prime_expire FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    if row and row['is_prime'] == 1:
        if row['prime_expire']:
            try:
                expire_date = datetime.strptime(row['prime_expire'], "%Y-%m-%d %H:%M:%S")
                if datetime.now() > expire_date:
                    c.execute("UPDATE users SET is_prime = 0, prime_expire = NULL WHERE user_id = ?", (user_id,))
                    conn.commit()
                    conn.close()
                    return False
            except:
                pass
        conn.close()
        return True
    conn.close()
    return False

def add_prime_days(user_id, days):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT prime_expire FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    now = datetime.now()
    if row and row['prime_expire']:
        try:
            current_expire = datetime.strptime(row['prime_expire'], "%Y-%m-%d %H:%M:%S")
            new_expire = (current_expire if current_expire > now else now) + timedelta(days=days)
        except:
            new_expire = now + timedelta(days=days)
    else:
        new_expire = now + timedelta(days=days)
    expire_str = new_expire.strftime("%Y-%m-%d %H:%M:%S")
    c.execute("UPDATE users SET is_prime = 1, prime_expire = ? WHERE user_id = ?", (expire_str, user_id))
    conn.commit()
    conn.close()

def send_or_edit(chat_id, text, reply_markup=None, message_id=None, parse_mode="Markdown"):
    if message_id:
        try:
            bot.edit_message_text(text, chat_id, message_id, parse_mode=parse_mode, reply_markup=reply_markup)
            return
        except:
            pass
    bot.send_message(chat_id, text, parse_mode=parse_mode, reply_markup=reply_markup)

# Process alive check (no psutil)
def is_process_alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False

# ==================== CRASH GUARD ====================
def crash_guard_worker():
    while True:
        try:
            conn = get_db()
            c = conn.cursor()
            c.execute("SELECT * FROM hosted_bots WHERE status = 'running'")
            running_bots = c.fetchall()
            for b in running_bots:
                pid = b['pid']
                bot_id = b['id']
                user_id = b['user_id']
                filepath = b['filepath']  # entry file
                logpath = b['logpath']
                # log rotation
                if os.path.exists(logpath) and os.path.getsize(logpath) > MAX_LOG_SIZE_MB * 1024 * 1024:
                    try:
                        with open(logpath, 'w', encoding='utf-8') as f:
                            f.write(f"--- [LOG RESET AT {datetime.now()}] ---\n")
                    except:
                        pass
                is_alive = False
                if pid:
                    is_alive = is_process_alive(pid)
                if not is_alive:
                    if is_prime_user(user_id) and b['auto_guard'] == 1:
                        try:
                            log_file = open(logpath, 'a', encoding='utf-8')
                            log_file.write(f"\n--- [AUTO RESTART AT {datetime.now()}] ---\n")
                            log_file.flush()
                            proc = subprocess.Popen(
                                [sys.executable, "-u", filepath],
                                stdout=log_file,
                                stderr=log_file,
                                cwd=os.path.dirname(filepath)
                            )
                            log_file.close()
                            c.execute("UPDATE hosted_bots SET pid = ? WHERE id = ?", (proc.pid, bot_id))
                            conn.commit()
                        except Exception:
                            c.execute("UPDATE hosted_bots SET status = 'stopped', pid = NULL WHERE id = ?", (bot_id,))
                            conn.commit()
                    else:
                        c.execute("UPDATE hosted_bots SET status = 'stopped', pid = NULL WHERE id = ?", (bot_id,))
                        conn.commit()
            conn.close()
        except:
            pass
        time.sleep(10)

guard_thread = threading.Thread(target=crash_guard_worker, daemon=True)
guard_thread.start()

# ==================== KEYBOARDS ====================
def main_menu_keyboard(user_id):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📤 Upload Bot (.py/.zip)", callback_data="upload_info"),
        types.InlineKeyboardButton("📱 My Hosted Bots", callback_data="my_bots")
    )
    markup.add(types.InlineKeyboardButton("💎 PRIME VIP ZONE 🌟", callback_data="prime_zone"))
    markup.add(
        types.InlineKeyboardButton("👥 Referral Program", callback_data="referral_info"),
        types.InlineKeyboardButton("🎟️ Redeem Coupon", callback_data="claim_code")
    )
    markup.add(
        types.InlineKeyboardButton("📊 Server Status", callback_data="server_stats"),
        types.InlineKeyboardButton("❓ Help & Guide", callback_data="help_guide")
    )
    markup.add(
        types.InlineKeyboardButton("📢 Official Channel", url=f"https://t.me/{CHANNEL_USERNAME}"),
        types.InlineKeyboardButton("📞 Admin Support", url=f"https://t.me/{ADMIN_USERNAME}")
    )
    if str(user_id) == ADMIN_ID:
        markup.add(types.InlineKeyboardButton("⚙️ Admin Control Panel", callback_data="admin_panel"))
    return markup

def prime_zone_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=2)
    # Package buttons
    for key, pkg in PACKAGES.items():
        markup.add(types.InlineKeyboardButton(f"📦 {pkg['label']} – ₹{pkg['price']}", callback_data=f"buy_{key}"))
    markup.add(
        types.InlineKeyboardButton("⏳ Subscription Status", callback_data="prime_expire_check"),
        types.InlineKeyboardButton("🎁 Gift Prime to Friend", callback_data="gift_prime")
    )
    markup.add(types.InlineKeyboardButton("🎟️ Redeem Coupon", callback_data="claim_code"))
    markup.add(types.InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu"))
    return markup

# ==================== COMMANDS ====================
@bot.message_handler(commands=['start'])
def start_cmd(message):
    user_id = message.from_user.id
    ref_by = None
    text_args = message.text.split()
    if len(text_args) > 1 and text_args[1].startswith("ref_"):
        try:
            ref_by = int(text_args[1].replace("ref_", ""))
        except:
            pass
    register_user(user_id, ref_by)
    is_prime = is_prime_user(user_id)
    user_name = message.from_user.first_name or "User"
    badge = "👑 PRIME VIP MEMBER" if is_prime else "FREE STANDARD USER"
    limit_info = f"🚀 Hosting Limit: {PRIME_LIMIT} Bots" if is_prime else f"📦 Hosting Limit: {FREE_LIMIT} Bot"
    welcome_msg = (
        f"🎬 **Made by ANIKET** 🎬\n"
        f"👑 **PRIME HOSTING SERVER v4.0** 👑\n\n"
        f"✨ **Welcome, {user_name}!**\n\n"
        f"👤 **User Profile:**\n"
        f" ├ 🏷️ Name: `{user_name}`\n"
        f" ├ 🆔 ID: `{user_id}`\n"
        f" └ 💎 Status: **{badge}**\n\n"
        f"⚡ **Services:**\n"
        f" ├ {limit_info}\n"
        f" └ 🛡️ Crash Guard: {'24/7 Enabled' if is_prime else 'Prime Only'}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👇 **Select an option:**"
    )
    bot.send_message(message.chat.id, welcome_msg, parse_mode="Markdown", reply_markup=main_menu_keyboard(user_id))

@bot.message_handler(commands=['genkey'])
def gen_key_cmd(message):
    if str(message.from_user.id) != ADMIN_ID:
        return
    try:
        days = int(message.text.split()[1])
    except:
        days = 30
    code = "PRIME-" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT INTO prime_codes (code, days) VALUES (?, ?)", (code, days))
    conn.commit()
    conn.close()
    bot.reply_to(message, f"🎟️ **Prime Code Generated:**\n`{code}` ({days} Days)", parse_mode="Markdown")

@bot.message_handler(commands=['giveprime'])
def giveprime_cmd(message):
    if str(message.from_user.id) != ADMIN_ID:
        return
    parts = message.text.split()
    if len(parts) < 3:
        bot.reply_to(message, "Usage: /giveprime <user_id> <days>")
        return
    try:
        uid = int(parts[1])
        days = int(parts[2])
        add_prime_days(uid, days)
        bot.reply_to(message, f"✅ Added {days} Prime days to user {uid}.")
    except Exception as e:
        bot.reply_to(message, f"❌ Error: {e}")

# ==================== FILE UPLOAD HANDLER ====================
@bot.message_handler(content_types=['document'])
def handle_document(message):
    user_id = message.from_user.id
    register_user(user_id)
    file_name = message.document.file_name
    if not file_name.endswith(('.py', '.zip')):
        bot.reply_to(message, "❌ **Invalid File Format!** Please upload a `.py` or `.zip` file.")
        return

    is_prime = is_prime_user(user_id)
    max_allowed = PRIME_LIMIT if is_prime else FREE_LIMIT

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) as count FROM hosted_bots WHERE user_id = ?", (user_id,))
    current_count = c.fetchone()['count']
    if current_count >= max_allowed:
        conn.close()
        bot.reply_to(message, f"⚠️ **Limit Reached!** Max {max_allowed} bot(s). Upgrade to Prime for more.")
        return

    file_info = bot.get_file(message.document.file_id)
    downloaded_file = bot.download_file(file_info.file_path)

    user_dir = os.path.join(os.getcwd(), HOST_DIR, str(user_id))
    os.makedirs(user_dir, exist_ok=True)

    # Save uploaded file
    base_path = os.path.join(user_dir, file_name)
    with open(base_path, 'wb') as f:
        f.write(downloaded_file)

    entry_file = None
    final_filepath = base_path
    logpath = base_path + ".log"

    if file_name.endswith('.zip'):
        # Extract zip
        extract_dir = os.path.join(user_dir, file_name.replace('.zip', ''))
        os.makedirs(extract_dir, exist_ok=True)
        with zipfile.ZipFile(base_path, 'r') as zip_ref:
            zip_ref.extractall(extract_dir)
        # Find main .py file (first .py not __init__)
        py_files = [f for f in os.listdir(extract_dir) if f.endswith('.py') and f != '__init__.py']
        if not py_files:
            bot.reply_to(message, "❌ No Python file found inside zip.")
            return
        entry_file = os.path.join(extract_dir, py_files[0])
        final_filepath = entry_file
        # remove the zip? optional
        # os.remove(base_path)  # optional
    else:
        # .py file
        entry_file = base_path
        final_filepath = base_path

    # Insert or update bot record
    c.execute("SELECT id FROM hosted_bots WHERE user_id = ? AND filename = ?", (user_id, file_name))
    existing = c.fetchone()
    if existing:
        c.execute("UPDATE hosted_bots SET filepath = ?, entry_file = ?, logpath = ?, status='stopped', pid=NULL WHERE id = ?",
                  (final_filepath, entry_file, logpath, existing['id']))
    else:
        c.execute("INSERT INTO hosted_bots (user_id, filename, filepath, entry_file, logpath, status) VALUES (?, ?, ?, ?, ?, 'stopped')",
                  (user_id, file_name, final_filepath, entry_file, logpath))
    conn.commit()
    conn.close()

    # Show management button
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("⚙️ Manage Bot", callback_data="my_bots"))
    bot.reply_to(message, f"✅ **{file_name}** uploaded successfully!\nClick below to manage it.", reply_markup=markup)

# ==================== CALLBACK HANDLERS ====================
@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    try:
        bot.answer_callback_query(call.id)
    except:
        pass

    user_id = call.from_user.id
    chat_id = call.message.chat.id
    msg_id = call.message.message_id

    # ---------- NAVIGATION ----------
    if call.data == "main_menu":
        send_or_edit(chat_id, "🏠 **Main Navigation:**", main_menu_keyboard(user_id), msg_id)

    elif call.data == "prime_zone":
        status = "👑 PRIME VIP MEMBER" if is_prime_user(user_id) else "FREE PLAN USER"
        msg = (
            f"👑 **PRIME VIP ZONE** 👑\n"
            f"🎬 *Made by ANIKET*\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"👤 **Status:** {status}\n\n"
            f"🔥 **Packages:**\n"
            f" └ Select a plan below.\n"
            f"💳 **Payment:** UPI only"
        )
        send_or_edit(chat_id, msg, prime_zone_keyboard(), msg_id)

    elif call.data == "upload_info":
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu"))
        send_or_edit(chat_id, "📥 **Send your `.py` or `.zip` file directly in this chat.**", markup, msg_id)

    elif call.data == "referral_info":
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT referral_count FROM users WHERE user_id = ?", (user_id,))
        row = c.fetchone()
        ref_count = row['referral_count'] if row else 0
        conn.close()
        ref_link = f"https://t.me/{BOT_USERNAME}?start=ref_{user_id}"
        msg = (
            f"👥 **Referral Program**\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"Invite friends to earn FREE Prime VIP!\n\n"
            f"🔗 **Your Link:**\n`{ref_link}`\n\n"
            f"📊 **Referrals:** `{ref_count}`\n"
            f"🎁 **Reward:** 2 days Prime per 4 invites."
        )
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu"))
        send_or_edit(chat_id, msg, markup, msg_id)

    elif call.data == "server_stats":
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) as total FROM hosted_bots")
        total_bots = c.fetchone()['total']
        c.execute("SELECT COUNT(*) as running FROM hosted_bots WHERE status='running'")
        running_bots = c.fetchone()['running']
        conn.close()
        msg = (
            f"🖥️ **Server Status**\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"🤖 **Total Bots:** `{total_bots}`\n"
            f"🟢 **Running:** `{running_bots}`"
        )
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔄 Refresh", callback_data="server_stats"))
        markup.add(types.InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu"))
        send_or_edit(chat_id, msg, markup, msg_id)

    elif call.data == "help_guide":
        help_msg = (
            f"❓ **Help & Guide**\n\n"
            f"1️⃣ Upload `.py` or `.zip`.\n"
            f"2️⃣ Go to **My Hosted Bots**.\n"
            f"3️⃣ Press ▶️ **Start Bot**.\n"
            f"4️⃣ Check **Logs** if errors occur.\n"
            f"5️⃣ For dependencies, ask admin to install."
        )
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu"))
        send_or_edit(chat_id, help_msg, markup, msg_id)

    elif call.data == "claim_code":
        m = bot.send_message(chat_id, "🎟️ **Enter your Prime Coupon Code:**")
        bot.register_next_step_handler(m, process_claim_code)

    elif call.data == "gift_prime":
        if not is_prime_user(user_id):
            bot.send_message(chat_id, "❌ Only Prime members can gift access.")
            return
        m = bot.send_message(chat_id, "🎁 **Enter target user's Numeric Telegram ID:**")
        bot.register_next_step_handler(m, process_gift_prime)

    elif call.data == "prime_expire_check":
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT prime_expire FROM users WHERE user_id = ?", (user_id,))
        row = c.fetchone()
        conn.close()
        if is_prime_user(user_id):
            expire_str = row['prime_expire'] if row and row['prime_expire'] else "Unlimited (Admin)"
            msg = f"🌟 **Prime Active!**\n⏳ Expires: `{expire_str}`"
        else:
            msg = "❌ No active Prime subscription."
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔙 Prime Zone", callback_data="prime_zone"))
        send_or_edit(chat_id, msg, markup, msg_id)

    # ---------- BUY PACKAGE ----------
    elif call.data.startswith("buy_"):
        pkg_key = call.data.split("_", 1)[1]
        pkg = PACKAGES.get(pkg_key)
        if not pkg:
            return
        # Show payment details with QR
        caption = (
            f"💳 **Payment for {pkg['label']}**\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"💰 **Amount:** ₹{pkg['price']}\n"
            f"📲 **UPI ID:** `{UPI_ID}`\n\n"
            f"📌 **Steps:**\n"
            f"1️⃣ Scan QR or pay to UPI ID.\n"
            f"2️⃣ Copy your **Transaction ID (UTR)**.\n"
            f"3️⃣ Click **'I have paid'** below and send UTR.\n\n"
            f"📞 Admin: @{ADMIN_USERNAME}"
        )
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("✅ I have paid – Send UTR", callback_data=f"send_utr_{pkg_key}"))
        markup.add(types.InlineKeyboardButton("🔙 Prime Zone", callback_data="prime_zone"))
        # Send QR image if exists, else just text
        if os.path.exists(QR_IMAGE_PATH):
            with open(QR_IMAGE_PATH, 'rb') as img:
                bot.send_photo(chat_id, img, caption=caption, reply_markup=markup)
        else:
            send_or_edit(chat_id, caption, markup, msg_id)

    elif call.data.startswith("send_utr_"):
        pkg_key = call.data.split("_", 2)[2]
        pkg = PACKAGES.get(pkg_key)
        if not pkg:
            return
        # Store package info in user session
        bot.send_message(chat_id, f"📝 **Please send your UTR (Transaction ID)** for the {pkg['label']} plan (₹{pkg['price']}).")
        # We'll use next_step_handler to capture UTR
        bot.register_next_step_handler(call.message, process_utr, pkg_key)

    # ---------- ADMIN PANEL ----------
    elif call.data == "admin_panel":
        if str(user_id) != ADMIN_ID:
            return
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) as u FROM users")
        u_cnt = c.fetchone()['u']
        c.execute("SELECT COUNT(*) as p FROM users WHERE is_prime=1")
        p_cnt = c.fetchone()['p']
        c.execute("SELECT COUNT(*) as b FROM hosted_bots")
        b_cnt = c.fetchone()['b']
        c.execute("SELECT COUNT(*) as pend FROM pending_payments WHERE status='pending'")
        pend_cnt = c.fetchone()['pend']
        conn.close()
        msg = (
            f"⚙️ **Admin Panel**\n"
            f"👥 Users: `{u_cnt}`\n"
            f"💎 Prime: `{p_cnt}`\n"
            f"🤖 Bots: `{b_cnt}`\n"
            f"⏳ Pending Payments: `{pend_cnt}`"
        )
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("📋 Pending Payments", callback_data="admin_pending"))
        markup.add(types.InlineKeyboardButton("📦 Install pyrogram & tgcrypto", callback_data="admin_install_deps"))
        markup.add(types.InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu"))
        send_or_edit(chat_id, msg, markup, msg_id)

    elif call.data == "admin_pending":
        if str(user_id) != ADMIN_ID:
            return
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT * FROM pending_payments WHERE status='pending' ORDER BY id DESC")
        rows = c.fetchall()
        conn.close()
        if not rows:
            bot.send_message(chat_id, "✅ No pending payments.")
            return
        for row in rows:
            markup = types.InlineKeyboardMarkup()
            markup.add(
                types.InlineKeyboardButton("✅ Approve", callback_data=f"apppay_{row['id']}"),
                types.InlineKeyboardButton("❌ Reject", callback_data=f"rejpay_{row['id']}")
            )
            msg = (
                f"🧾 **Payment #{row['id']}**\n"
                f"👤 User: `{row['user_id']}`\n"
                f"📦 Package: {row['package']}\n"
                f"💵 Amount: ₹{row['amount']}\n"
                f"🆔 UTR: `{row['utr']}`\n"
                f"📅 Time: {row['created_at']}"
            )
            bot.send_message(chat_id, msg, reply_markup=markup)

    elif call.data.startswith("apppay_"):
        if str(user_id) != ADMIN_ID:
            return
        pay_id = int(call.data.split("_")[1])
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT * FROM pending_payments WHERE id = ?", (pay_id,))
        row = c.fetchone()
        if row:
            # Add prime days
            add_prime_days(row['user_id'], row['days'])
            c.execute("UPDATE pending_payments SET status='approved' WHERE id = ?", (pay_id,))
            conn.commit()
            try:
                bot.send_message(row['user_id'], f"✅ **Payment Approved!** Your {row['package']} plan is active. Enjoy Prime VIP!")
            except:
                pass
            bot.answer_callback_query(call.id, "✅ Approved")
        conn.close()
        # Refresh admin panel
        bot.send_message(chat_id, "✅ Approved.")

    elif call.data.startswith("rejpay_"):
        if str(user_id) != ADMIN_ID:
            return
        pay_id = int(call.data.split("_")[1])
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT user_id FROM pending_payments WHERE id = ?", (pay_id,))
        row = c.fetchone()
        if row:
            c.execute("UPDATE pending_payments SET status='rejected' WHERE id = ?", (pay_id,))
            conn.commit()
            try:
                bot.send_message(row['user_id'], "❌ **Payment Rejected.** Please contact admin.")
            except:
                pass
            bot.answer_callback_query(call.id, "❌ Rejected")
        conn.close()
        bot.send_message(chat_id, "❌ Rejected.")

    elif call.data == "admin_install_deps":
        if str(user_id) != ADMIN_ID:
            return
        bot.send_message(chat_id, "⏳ Installing `pyrogram` and `tgcrypto`...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "pyrogram", "tgcrypto"])
            bot.send_message(chat_id, "✅ **Installation complete!**")
        except Exception as e:
            bot.send_message(chat_id, f"❌ Installation failed: {e}")

    # ---------- MY BOTS ----------
    elif call.data == "my_bots":
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT * FROM hosted_bots WHERE user_id = ?", (user_id,))
        bots = c.fetchall()
        conn.close()
        if not bots:
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu"))
            send_or_edit(chat_id, "❌ No bots uploaded.", markup, msg_id)
            return
        markup = types.InlineKeyboardMarkup()
        for b in bots:
            is_alive = False
            if b['status'] == 'running' and b['pid']:
                is_alive = is_process_alive(b['pid'])
            icon = "🟢" if is_alive else "🔴"
            markup.add(types.InlineKeyboardButton(f"{icon} {b['filename']}", callback_data=f"manage_{b['id']}"))
        markup.add(types.InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu"))
        send_or_edit(chat_id, "⚙️ **Select a bot:**", markup, msg_id)

    elif call.data.startswith("manage_"):
        bot_id = int(call.data.split("_")[1])
        render_bot_control(chat_id, bot_id, msg_id)

    elif call.data.startswith("startbot_"):
        bot_id = int(call.data.split("_")[1])
        start_bot_action(chat_id, bot_id, msg_id)

    elif call.data.startswith("stopbot_"):
        bot_id = int(call.data.split("_")[1])
        stop_bot_action(chat_id, bot_id, msg_id)

    elif call.data.startswith("logbot_"):
        bot_id = int(call.data.split("_")[1])
        show_logs_action(chat_id, bot_id, msg_id)

    elif call.data.startswith("clearlog_"):
        bot_id = int(call.data.split("_")[1])
        clear_logs_action(chat_id, bot_id, msg_id)

    elif call.data.startswith("piplist_"):
        bot_id = int(call.data.split("_")[1])
        show_pip_action(chat_id, bot_id, msg_id)

    elif call.data.startswith("delbot_"):
        bot_id = int(call.data.split("_")[1])
        delete_bot_action(chat_id, bot_id, msg_id)

# ==================== BOT CONTROL FUNCTIONS ====================
def render_bot_control(chat_id, bot_id, msg_id=None):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM hosted_bots WHERE id = ?", (bot_id,))
    b = c.fetchone()
    conn.close()
    if not b:
        bot.send_message(chat_id, "❌ Bot not found.")
        return
    is_running = False
    if b['status'] == 'running' and b['pid'] and is_process_alive(b['pid']):
        is_running = True
    status_icon = "🟢 Running" if is_running else "🔴 Stopped"
    msg = (
        f"🤖 **Bot Control Panel**\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"📄 File: `{b['filename']}`\n"
        f"📊 Status: {status_icon}\n"
        f"🆔 PID: `{b['pid'] if is_running else 'N/A'}`\n"
        f"━━━━━━━━━━━━━━━━━━━"
    )
    markup = types.InlineKeyboardMarkup(row_width=2)
    if is_running:
        markup.add(types.InlineKeyboardButton("🛑 Stop Bot", callback_data=f"stopbot_{b['id']}"))
    else:
        markup.add(types.InlineKeyboardButton("▶️ Start Bot", callback_data=f"startbot_{b['id']}"))
    markup.add(
        types.InlineKeyboardButton("📜 Live Logs", callback_data=f"logbot_{b['id']}"),
        types.InlineKeyboardButton("🧹 Clear Logs", callback_data=f"clearlog_{b['id']}")
    )
    markup.add(
        types.InlineKeyboardButton("📋 Pip Packages", callback_data=f"piplist_{b['id']}"),
        types.InlineKeyboardButton("🔄 Refresh Panel", callback_data=f"manage_{b['id']}")
    )
    markup.add(types.InlineKeyboardButton("🗑️ Delete Bot", callback_data=f"delbot_{b['id']}"))
    markup.add(types.InlineKeyboardButton("🔙 My Hosted Bots", callback_data="my_bots"))
    send_or_edit(chat_id, msg, markup, msg_id)

def start_bot_action(chat_id, bot_id, msg_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM hosted_bots WHERE id = ?", (bot_id,))
    b = c.fetchone()
    if b and (not b['pid'] or not is_process_alive(b['pid'])):
        try:
            log_file = open(b['logpath'], 'a', encoding='utf-8')
            proc = subprocess.Popen(
                [sys.executable, "-u", b['entry_file'] or b['filepath']],
                stdout=log_file,
                stderr=log_file,
                cwd=os.path.dirname(b['filepath'])
            )
            log_file.close()
            c.execute("UPDATE hosted_bots SET status='running', pid=? WHERE id=?", (proc.pid, bot_id))
            conn.commit()
        except Exception as e:
            bot.send_message(chat_id, f"❌ Start failed: {e}")
    conn.close()
    render_bot_control(chat_id, bot_id, msg_id)

def stop_bot_action(chat_id, bot_id, msg_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT pid FROM hosted_bots WHERE id=?", (bot_id,))
    b = c.fetchone()
    if b and b['pid']:
        try:
            if is_process_alive(b['pid']):
                os.kill(b['pid'], 9)
        except:
            pass
    c.execute("UPDATE hosted_bots SET status='stopped', pid=NULL WHERE id=?", (bot_id,))
    conn.commit()
    conn.close()
    render_bot_control(chat_id, bot_id, msg_id)

def show_logs_action(chat_id, bot_id, msg_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT logpath, filename FROM hosted_bots WHERE id=?", (bot_id,))
    b = c.fetchone()
    conn.close()
    if not b or not os.path.exists(b['logpath']):
        bot.send_message(chat_id, "❌ Log file missing.")
        return
    try:
        with open(b['logpath'], 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()[-35:]
        log_text = "".join(lines) if lines else "No logs."
        msg = f"📜 **Logs for `{b['filename']}`:**\n```\n{log_text[:3500]}\n```"
        markup = types.InlineKeyboardMarkup()
        markup.add(
            types.InlineKeyboardButton("🔄 Refresh", callback_data=f"logbot_{bot_id}"),
            types.InlineKeyboardButton("🧹 Clear", callback_data=f"clearlog_{bot_id}")
        )
        markup.add(types.InlineKeyboardButton("🔙 Manage", callback_data=f"manage_{bot_id}"))
        send_or_edit(chat_id, msg, markup, msg_id)
    except Exception as e:
        bot.send_message(chat_id, f"❌ Error: {e}")

def clear_logs_action(chat_id, bot_id, msg_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT logpath FROM hosted_bots WHERE id=?", (bot_id,))
    b = c.fetchone()
    conn.close()
    if b and os.path.exists(b['logpath']):
        try:
            open(b['logpath'], 'w').close()
        except:
            pass
    show_logs_action(chat_id, bot_id, msg_id)

def show_pip_action(chat_id, bot_id, msg_id):
    try:
        res = subprocess.run([sys.executable, "-m", "pip", "list"], capture_output=True, text=True)
        packages = res.stdout[:3000]
        msg = f"📋 **Installed Packages:**\n```\n{packages}\n```"
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔙 Manage", callback_data=f"manage_{bot_id}"))
        send_or_edit(chat_id, msg, markup, msg_id)
    except Exception as e:
        bot.send_message(chat_id, f"❌ Error: {e}")

def delete_bot_action(chat_id, bot_id, msg_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT filepath, logpath, pid FROM hosted_bots WHERE id=?", (bot_id,))
    b = c.fetchone()
    if b:
        if b['pid'] and is_process_alive(b['pid']):
            try:
                os.kill(b['pid'], 9)
            except:
                pass
        for path in [b['filepath'], b['logpath']]:
            if os.path.exists(path):
                try:
                    os.remove(path)
                except:
                    pass
    c.execute("DELETE FROM hosted_bots WHERE id=?", (bot_id,))
    conn.commit()
    conn.close()
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🔙 My Hosted Bots", callback_data="my_bots"))
    send_or_edit(chat_id, "🗑️ **Bot deleted.**", markup, msg_id)

# ==================== STEP PROCESSORS ====================
def process_claim_code(message):
    if not message.text:
        bot.reply_to(message, "❌ Invalid input.")
        return
    code = message.text.strip()
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT days FROM prime_codes WHERE code=?", (code,))
    row = c.fetchone()
    if row:
        add_prime_days(message.from_user.id, row['days'])
        c.execute("DELETE FROM prime_codes WHERE code=?", (code,))
        conn.commit()
        bot.reply_to(message, f"🎉 Activated {row['days']} days Prime!")
    else:
        bot.reply_to(message, "❌ Invalid code.")
    conn.close()

def process_gift_prime(message):
    if not message.text or not message.text.isdigit():
        bot.reply_to(message, "❌ Invalid Telegram ID.")
        return
    try:
        friend_id = int(message.text.strip())
        add_prime_days(friend_id, 7)
        bot.reply_to(message, f"🎁 Gifted 7 days Prime to `{friend_id}`.")
    except:
        bot.reply_to(message, "❌ Error occurred.")

def process_utr(message, pkg_key):
    if not message.text:
        bot.reply_to(message, "❌ Please send a valid UTR.")
        return
    utr = message.text.strip()
    user_id = message.from_user.id
    pkg = PACKAGES.get(pkg_key)
    if not pkg:
        bot.reply_to(message, "❌ Package not found.")
        return
    # Store pending payment
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT INTO pending_payments (user_id, package, days, amount, utr) VALUES (?, ?, ?, ?, ?)",
              (user_id, pkg['label'], pkg['days'], pkg['price'], utr))
    conn.commit()
    conn.close()
    bot.reply_to(message, f"✅ UTR received! Admin will verify soon.\n📌 UTR: `{utr}`")
    # Notify admin
    try:
        admin_msg = (
            f"🧾 **New Payment UTR**\n"
            f"👤 User: `{user_id}`\n"
            f"📦 Package: {pkg['label']}\n"
            f"💵 Amount: ₹{pkg['price']}\n"
            f"🆔 UTR: `{utr}`\n"
            f"⏳ Go to Admin Panel to approve."
        )
        bot.send_message(ADMIN_ID, admin_msg)
    except:
        pass

# ==================== POLLING ====================
if __name__ == '__main__':
    print("🎬 Made by ANIKET")
    print("⚡ Prime Hosting Server v4.0 Running...")
    print(f"✅ Bot: @{BOT_USERNAME}")
    print(f"✅ Admin: {ADMIN_ID}")
    print(f"✅ UPI: {UPI_ID}")
    bot.infinity_polling(skip_pending=True, timeout=10, long_polling_timeout=5)
