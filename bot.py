"""
ROYAL X NUMBER — Multi-Panel Bot (ScarFace + MinoSMS + STEX + Zenex + JS SMS)
With Per-Range Panel Priority + Panel Usage Tracking + Clickable Range Buttons
+ New Organized Admin Panel
Webhook Ready for Render — FINAL VERSION (MinoSMS Fixed)
"""

import asyncio
import io
import re
import json
import html
import os
import time
import threading
import httpx
import random
import string
from datetime import datetime, timedelta
from flask import Flask, request
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters, CallbackQueryHandler

# ============================================================
# SERVICES + USER MANAGEMENT
# ============================================================
SERVICES_FILE = "services.json"
PANEL_LOG_FILE = "panel_usage_log.json"

def _svc_load():
    if not os.path.exists(SERVICES_FILE):
        with open(SERVICES_FILE, "w") as f:
            json.dump({}, f)
        return {}
    try:
        with open(SERVICES_FILE, "r") as f:
            return json.load(f)
    except:
        return {}

def _svc_save(data):
    with open(SERVICES_FILE, "w") as f:
        json.dump(data, f, indent=2)

def get_all_services():
    return _svc_load()

def get_ranges(service):
    return _svc_load().get(service, {}).get("ranges", {})

def add_service(name, icon="🚀"):
    data = _svc_load()
    if name in data:
        return False
    data[name] = {"icon": icon, "ranges": {}}
    _svc_save(data)
    return True

def delete_service(name):
    data = _svc_load()
    if name in data:
        del data[name]
        _svc_save(data)
        return True
    return False

def rename_service(old, new):
    data = _svc_load()
    if old not in data or new in data:
        return False
    data[new] = data.pop(old)
    _svc_save(data)
    return True

def add_range(service, rid, country, rate, panel_priority=None):
    data = _svc_load()
    if service not in data or rid in data[service]["ranges"]:
        return False
    data[service]["ranges"][rid] = {
        "country": country,
        "rate": rate,
        "panel_priority": panel_priority or [],
        "panel_stats": {}
    }
    _svc_save(data)
    return True

def delete_range(service, rid):
    data = _svc_load()
    if service in data and rid in data[service]["ranges"]:
        del data[service]["ranges"][rid]
        _svc_save(data)
        return True
    return False

def update_range_rate(service, rid, rate):
    data = _svc_load()
    if service in data and rid in data[service]["ranges"]:
        data[service]["ranges"][rid]["rate"] = rate
        _svc_save(data)
        return True
    return False

def update_range_country(service, rid, country):
    data = _svc_load()
    if service in data and rid in data[service]["ranges"]:
        data[service]["ranges"][rid]["country"] = country
        _svc_save(data)
        return True
    return False

def update_range_priority(service, rid, panel_priority):
    data = _svc_load()
    if service in data and rid in data[service]["ranges"]:
        data[service]["ranges"][rid]["panel_priority"] = panel_priority
        _svc_save(data)
        return True
    return False

def record_range_panel_use(service, rid, panel_name):
    data = _svc_load()
    if service in data and rid in data[service]["ranges"]:
        rs = data[service]["ranges"][rid]
        if "panel_stats" not in rs:
            rs["panel_stats"] = {}
        rs["panel_stats"][panel_name] = rs["panel_stats"].get(panel_name, 0) + 1
        _svc_save(data)

def bulk_add_ranges(service, lines):
    data = _svc_load()
    if service not in data:
        data[service] = {"icon": "🚀", "ranges": {}}
    count = 0
    for line in lines:
        parts = [p.strip() for p in line.split("|")]
        if len(parts) >= 3:
            try:
                rid = parts[0]
                country = parts[1]
                rate = float(parts[2])
                priority = []
                if len(parts) >= 4 and parts[3]:
                    priority = [p.strip().lower() for p in parts[3].split(",")]
                data[service]["ranges"][rid] = {
                    "country": country,
                    "rate": rate,
                    "panel_priority": priority,
                    "panel_stats": {}
                }
                count += 1
            except:
                continue
    _svc_save(data)
    return count

def export_services_txt():
    data = _svc_load()
    out = []
    for sname, sdata in data.items():
        for rid, rdata in sdata.get("ranges", {}).items():
            prio = ",".join(rdata.get("panel_priority", []))
            out.append(f"{sname}|{rid}|{rdata.get('country','')}|{rdata.get('rate',0.3)}|{prio}")
    return "\n".join(out)

# ---------------- PANEL USAGE LOG ----------------
def _log_load():
    if not os.path.exists(PANEL_LOG_FILE):
        with open(PANEL_LOG_FILE, "w") as f:
            json.dump([], f)
        return []
    try:
        with open(PANEL_LOG_FILE, "r") as f:
            return json.load(f)
    except:
        return []

def _log_save(data):
    with open(PANEL_LOG_FILE, "w") as f:
        json.dump(data, f, indent=2)

def log_panel_usage(uid, service, range_id, panel_name, panel_id, number):
    logs = _log_load()
    logs.append({
        "time": datetime.now().isoformat(),
        "uid": str(uid),
        "service": service,
        "range": range_id,
        "panel_name": panel_name,
        "panel_id": panel_id,
        "number": number
    })
    if len(logs) > 5000:
        logs = logs[-5000:]
    _log_save(logs)

def get_panel_usage_summary(days=7):
    logs = _log_load()
    cutoff = datetime.now() - timedelta(days=days)
    summary = {}
    for entry in logs:
        try:
            t = datetime.fromisoformat(entry["time"])
            if t < cutoff:
                continue
        except:
            continue
        key = (entry["service"], entry["range"])
        if key not in summary:
            summary[key] = {}
        pname = entry.get("panel_name", "Unknown")
        summary[key][pname] = summary[key].get(pname, 0) + 1
    return summary

# ---------------- USER MANAGER ----------------
_USERS_FILE = "users.json"
_BANNED_FILE = "banned_users.json"

def _um_load_users():
    if not os.path.exists(_USERS_FILE):
        with open(_USERS_FILE, "w") as f:
            json.dump({}, f)
        return {}
    try:
        with open(_USERS_FILE, "r") as f:
            return json.load(f)
    except:
        return {}

def _um_save_users(data):
    with open(_USERS_FILE, "w") as f:
        json.dump(data, f, indent=2)

def _um_load_banned():
    if not os.path.exists(_BANNED_FILE):
        with open(_BANNED_FILE, "w") as f:
            json.dump([], f)
        return []
    try:
        with open(_BANNED_FILE, "r") as f:
            return json.load(f)
    except:
        return []

def _um_save_banned(data):
    with open(_BANNED_FILE, "w") as f:
        json.dump(data, f, indent=2)

def um_add_balance(uid, amount):
    uid = str(uid)
    data = _um_load_users()
    if uid not in data:
        data[uid] = {"balance": 0, "otp_count": 0, "name": ""}
    data[uid]["balance"] = data[uid].get("balance", 0) + amount
    _um_save_users(data)
    return data[uid]["balance"]

def um_get_balance(uid):
    return _um_load_users().get(str(uid), {}).get("balance", 0)

def um_set_name(uid, name):
    uid = str(uid)
    data = _um_load_users()
    if uid not in data:
        data[uid] = {"balance": 0, "otp_count": 0, "name": ""}
    data[uid]["name"] = name
    _um_save_users(data)

def um_increment_otp(uid, name=""):
    uid = str(uid)
    data = _um_load_users()
    if uid not in data:
        data[uid] = {"balance": 0, "otp_count": 0, "name": ""}
    if name:
        data[uid]["name"] = name
    data[uid]["otp_count"] = data[uid].get("otp_count", 0) + 1
    _um_save_users(data)
    return data[uid]["otp_count"]

def um_get_user_data(uid):
    return _um_load_users().get(str(uid), {})

def um_get_all_users():
    return list(_um_load_users().keys())

def um_get_total_balance():
    return sum(u.get("balance", 0) for u in _um_load_users().values())

def um_get_today_otp_users(limit=10):
    data = _um_load_users()
    rows = [(u, ud.get("otp_count", 0), ud.get("name", "User")) for u, ud in data.items()]
    rows = [r for r in rows if r[1] > 0]
    rows.sort(key=lambda x: x[1], reverse=True)
    return rows[:limit]

def um_get_top_otp_users(limit=10):
    return um_get_today_otp_users(limit)

def um_search_users(query):
    return [(u, d) for u, d in _um_load_users().items() if query in u][:10]

def um_is_banned(uid):
    return str(uid) in _um_load_banned()

def um_ban(uid):
    banned = _um_load_banned()
    if str(uid) not in banned:
        banned.append(str(uid))
        _um_save_banned(banned)
    return True

def um_unban(uid):
    banned = _um_load_banned()
    if str(uid) in banned:
        banned.remove(str(uid))
        _um_save_banned(banned)
    return True

def um_load_banned():
    return _um_load_banned()

def um_export_users_csv():
    data = _um_load_users()
    lines = ["uid,balance,otp_count,name"]
    for u, d in data.items():
        lines.append(f"{u},{d.get('balance',0)},{d.get('otp_count',0)},{d.get('name','')}")
    return "\n".join(lines)

def aui_services_list_kb():
    btns = [[InlineKeyboardButton(f"📦 {n}", callback_data=f"svc_view_{n}", style="primary")] for n in get_all_services()]
    btns.append([InlineKeyboardButton("➕ ADD", callback_data="svc_add", style="success"),
                 InlineKeyboardButton("📥 BULK", callback_data="svc_bulk", style="success")])
    btns.append([InlineKeyboardButton("📤 EXPORT", callback_data="svc_export", style="primary")])
    btns.append([InlineKeyboardButton("🔙 BACK", callback_data="adm_back_admin", style="danger")])
    return InlineKeyboardMarkup(btns)

def aui_service_text(srv):
    data = get_all_services().get(srv, {})
    ranges = data.get("ranges", {})
    txt = f"📦 <b>{srv.upper()}</b>\n━━━━━━━━━━━━━━━\n\n"
    txt += f"🔢 Total Ranges: <b>{len(ranges)}</b>\n\n"
    if len(ranges) > 0:
        txt += "<i>👇 ট্যাপ করুন যেকোনো Range-এ — Edit / Delete করতে</i>"
    else:
        txt += "<i>⚠️ কোনো Range নেই — ADD RANGE ক্লিক করুন</i>"
    return txt

def aui_service_detail_kb(srv):
    ranges = get_ranges(srv)
    btns = []
    range_items = list(ranges.items())
    for i in range(0, len(range_items), 2):
        row = []
        for rid, rdata in range_items[i:i+2]:
            label = f"📍 {rid}"
            row.append(InlineKeyboardButton(label, callback_data=f"rng_view_{srv}_{rid}", style="primary"))
        btns.append(row)
    btns.append([InlineKeyboardButton("➕ ADD RANGE", callback_data=f"rng_add_{srv}", style="success")])
    btns.append([InlineKeyboardButton("✏️ RENAME", callback_data=f"svc_rename_{srv}", style="primary"),
                 InlineKeyboardButton("🗑 DELETE ALL", callback_data=f"svc_del_{srv}", style="danger")])
    btns.append([InlineKeyboardButton("🔙 BACK", callback_data="svc_list", style="danger")])
    return InlineKeyboardMarkup(btns)

def aui_range_detail_kb(srv, rid):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💰 RATE", callback_data=f"rng_rate_{srv}_{rid}", style="primary"),
         InlineKeyboardButton("🌍 COUNTRY", callback_data=f"rng_country_{srv}_{rid}", style="primary")],
        [InlineKeyboardButton("⚙️ PANEL PRIORITY", callback_data=f"rng_prio_{srv}_{rid}", style="primary")],
        [InlineKeyboardButton("📊 STATS", callback_data=f"rng_stats_{srv}_{rid}", style="success")],
        [InlineKeyboardButton("🗑 DELETE THIS RANGE", callback_data=f"rng_del_{srv}_{rid}", style="danger")],
        [InlineKeyboardButton("🔙 BACK", callback_data=f"svc_view_{srv}", style="danger")]])

def aui_user_management_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 STATS", callback_data="usr_stats", style="primary"),
         InlineKeyboardButton("🏆 TOP", callback_data="usr_top", style="primary")],
        [InlineKeyboardButton("💰 BALANCE", callback_data="usr_balance", style="primary"),
         InlineKeyboardButton("🔍 SEARCH", callback_data="usr_search", style="primary")],
        [InlineKeyboardButton("📋 LIST", callback_data="usr_list", style="primary"),
         InlineKeyboardButton("📊 CSV", callback_data="usr_csv", style="primary")],
        [InlineKeyboardButton("🚫 BAN LIST", callback_data="usr_banlist", style="danger")],
        [InlineKeyboardButton("🔙 BACK", callback_data="adm_back_admin", style="danger")]])

def aui_user_profile_text(uid):
    ud = um_get_user_data(uid)
    return (f"👤 <b>USER: {uid}</b>\n━━━━━━━━━━━━━━━\n\n"
            f"🏷️ Name: <b>{html.escape(ud.get('name','User'))}</b>\n"
            f"💰 Balance: <b>{ud.get('balance',0):.2f} BDT</b>\n"
            f"📩 OTPs: <b>{ud.get('otp_count',0)}</b>\n"
            f"🚫 Banned: <b>{'YES' if um_is_banned(uid) else 'NO'}</b>")

def aui_user_actions_kb(uid):
    banned = um_is_banned(uid)
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ ADD BAL", callback_data=f"usr_addbal_{uid}", style="success"),
         InlineKeyboardButton("➖ REMOVE", callback_data=f"usr_rembal_{uid}", style="danger")],
        [InlineKeyboardButton("🔓 UNBAN" if banned else "🚫 BAN",
                              callback_data=f"usr_unban_{uid}" if banned else f"usr_ban_{uid}",
                              style="success" if banned else "danger")],
        [InlineKeyboardButton("🔙 BACK", callback_data="usr_mgmt", style="danger")]])

def aui_stats_text():
    return (f"📊 <b>STATISTICS</b>\n━━━━━━━━━━━━━━━\n\n"
            f"👥 Users: <b>{len(um_get_all_users())}</b>\n"
            f"💰 Total Balance: <b>{um_get_total_balance():.2f} BDT</b>")

# ============================================================
# CONFIG
# ============================================================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8809085299:AAH3Rhzas42tVL5SEK2_c2Ap8khza7F4I0g")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "").rstrip("/")
PORT = int(os.environ.get("PORT", 10000))

ADMINS = [8234545453]

OTP_GROUP_ID = -1004408491237
WITHDRAW_GROUP_ID = -1004415866624
BREAKUP_GROUP_ID = -1003925317148
OTP_CHANNEL_URL = "https://t.me/RoyalOTPXCenter"
SUPPORT_LINK = "https://t.me/Niva_CoinZoneBD"

OTP_RATE = 0.03
REFERRAL_PRICE = 5
MIN_WITHDRAW = 10
MAX_WITHDRAW = 10000
CHECK_INTERVAL = 3.0
FORCE_JOIN_ENABLED = True

USER_DATA_FILE = "users.json"
PAID_SMS_FILE = "paid_sms.json"
STATS_FILE = "user_stats.json"
REFERRAL_DATA_FILE = "referral_data.json"
BANNED_USERS_FILE = "banned_users.json"
WITHDRAW_DATA_FILE = "withdraw_requests.json"
DATA_RANGE_FILE = "datarange.json"
FORCE_JOIN_FILE = "force_join.json"
PANELS_FILE = "panels.json"

WELCOME_MESSAGE = """⚡ 𝗥𝗢𝗬𝗔𝗟 𝗫 𝗡𝗨𝗠𝗕𝗘𝗥 ⚡ 
━━━━━━━━━━━━━━━━━━━━━━
🟢 𝗣𝗿𝗲𝗺𝗶𝘂𝗺 & ⚡ 𝗙𝗮𝘀𝘁 𝗦𝗲𝗿𝘃𝗶𝗰𝗲 🟢"""

COUNTRY_FLAGS = {
    "bangladesh": "🇧🇩", "india": "🇮🇳", "pakistan": "🇵🇰",
    "uk": "🇬🇧", "united kingdom": "🇬🇧", "usa": "🇺🇸", "united states": "🇺🇸",
    "russia": "🇷🇺", "egypt": "🇪🇬", "south africa": "🇿🇦",
    "nigeria": "🇳🇬", "kenya": "🇰🇪", "ghana": "🇬🇭", "morocco": "🇲🇦",
    "cameroon": "🇨🇲", "ivory coast": "🇨🇮", "madagascar": "🇲🇬",
    "romania": "🇷🇴", "france": "🇫🇷", "germany": "🇩🇪",
    "italy": "🇮🇹", "spain": "🇪🇸", "netherlands": "🇳🇱",
    "belgium": "🇧🇪", "switzerland": "🇨🇭", "austria": "🇦🇹",
    "sweden": "🇸🇪", "norway": "🇳🇴", "denmark": "🇩🇰",
    "finland": "🇫🇮", "portugal": "🇵🇹", "ireland": "🇮🇪",
    "poland": "🇵🇱", "ukraine": "🇺🇦", "turkey": "🇹🇷",
    "saudi": "🇸🇦", "uae": "🇦🇪", "qatar": "🇶🇦",
    "kuwait": "🇰🇼", "oman": "🇴🇲", "bahrain": "🇧🇭",
    "jordan": "🇯🇴", "lebanon": "🇱🇧", "iraq": "🇮🇶",
    "china": "🇨🇳", "japan": "🇯🇵", "south korea": "🇰🇷",
    "vietnam": "🇻🇳", "thailand": "🇹🇭", "indonesia": "🇮🇩",
    "malaysia": "🇲🇾", "singapore": "🇸🇬", "philippines": "🇵🇭",
    "myanmar": "🇲🇲", "sri lanka": "🇱🇰", "nepal": "🇳🇵",
    "brazil": "🇧🇷", "mexico": "🇲🇽", "argentina": "🇦🇷",
    "australia": "🇦🇺", "new zealand": "🇳🇿",
    "guinea": "🇬🇳", "togo": "🇹🇬", "benin": "🇧🇯",
    "senegal": "🇸🇳", "mali": "🇲🇱", "burkina faso": "🇧🇫",
    "niger": "🇳🇪", "chad": "🇹🇩", "sudan": "🇸🇩",
    "ethiopia": "🇪🇹", "somalia": "🇸🇴", "uganda": "🇺🇬",
    "tanzania": "🇹🇿", "zambia": "🇿🇲", "zimbabwe": "🇿🇼",
    "mozambique": "🇲🇿", "angola": "🇦🇴", "congo": "🇨🇬",
    "gabon": "🇬🇦", "liberia": "🇱🇷", "sierra leone": "🇸🇱",
    "tunisia": "🇹🇳", "algeria": "🇩🇿", "libya": "🇱🇾",
}

def add_flag_to_country(country_name):
    if not country_name:
        return "🌍 Unknown"
    c = country_name.strip()
    if c and ord(c[0]) > 0x1F000:
        return c
    key = c.lower()
    flag = COUNTRY_FLAGS.get(key)
    if flag:
        return f"{flag} {c}"
    for k, v in COUNTRY_FLAGS.items():
        if k in key or key in k:
            return f"{v} {c}"
    return f"🌍 {c}"

# ============================================================
# HELPERS
# ============================================================
def get_bd_time():
    return datetime.utcnow() + timedelta(hours=6)

def normalize_number(number):
    if not number:
        return ""
    return re.sub(r'\D', '', str(number))

def mask_number(number):
    s = str(number)
    if len(s) <= 6:
        return s
    return s[:4] + "****" + s[-2:]

def format_balance(b):
    try:
        return f"{float(b):.2f}"
    except:
        return "0.00"

def is_admin(uid):
    return uid in ADMINS

def make_bold_unicode(text):
    out = []
    for c in text:
        cp = ord(c)
        if 65 <= cp <= 90:
            out.append(chr(cp - 65 + 0x1D5D4))
        elif 97 <= cp <= 122:
            out.append(chr(cp - 97 + 0x1D5EE))
        elif 48 <= cp <= 57:
            out.append(chr(cp - 48 + 0x1D7EC))
        else:
            out.append(c)
    return "".join(out)

def normalize_stylized_text(text):
    if not text:
        return ""
    out = []
    for c in text:
        cp = ord(c)
        if 0x1D5D4 <= cp <= 0x1D5ED:
            out.append(chr(cp - 0x1D5D4 + 65))
        elif 0x1D5EE <= cp <= 0x1D607:
            out.append(chr(cp - 0x1D5EE + 97))
        elif 0x1D7EC <= cp <= 0x1D7F5:
            out.append(chr(cp - 0x1D7EC + 48))
        else:
            out.append(c)
    return "".join(out)

def extract_link_and_otp(sms):
    if not sms:
        return None, None
    otp = None
    m = re.search(r'\b(\d{3})\s+(\d{3})\b', sms)
    if m:
        otp = m.group(1) + m.group(2)
    if not otp:
        m = re.search(r'\b(\d{4,8})\b', sms)
        if m:
            otp = m.group(1)
    if not otp:
        m = re.search(r'\d{4,8}', sms)
        if m:
            otp = m.group(0)
    lm = re.search(r'https?://[^\s]+', sms)
    link = lm.group(0) if lm else None
    return otp, link

def numbers_match(n1, n2):
    a = re.sub(r'\D', '', str(n1))
    b = re.sub(r'\D', '', str(n2))
    if not a or not b:
        return False
    return a in b or b in a

def is_valid_bd_number(n):
    c = re.sub(r'\D', '', str(n))
    if len(c) == 11 and c.startswith("01"):
        return True
    if len(c) == 13 and c.startswith("8801"):
        return True
    return False

def get_country_info(number):
    num = re.sub(r'\D', '', str(number))
    cmap = {
        "880": ("🇧🇩", "Bangladesh"), "91": ("🇮🇳", "India"),
        "92": ("🇵🇰", "Pakistan"), "44": ("🇬🇧", "UK"),
        "1": ("🇺🇸", "USA"), "7": ("🇷🇺", "Russia"),
        "20": ("🇪🇬", "Egypt"), "27": ("🇿🇦", "South Africa"),
        "234": ("🇳🇬", "Nigeria"), "254": ("🇰🇪", "Kenya"),
        "233": ("🇬🇭", "Ghana"), "212": ("🇲🇦", "Morocco"),
        "237": ("🇨🇲", "Cameroon"), "225": ("🇨🇮", "Ivory Coast"),
        "261": ("🇲🇬", "Madagascar"), "40": ("🇷🇴", "Romania"),
        "33": ("🇫🇷", "France"), "49": ("🇩🇪", "Germany"),
        "39": ("🇮🇹", "Italy"), "34": ("🇪🇸", "Spain"),
        "31": ("🇳🇱", "Netherlands"), "32": ("🇧🇪", "Belgium"),
        "41": ("🇨🇭", "Switzerland"), "43": ("🇦🇹", "Austria"),
        "46": ("🇸🇪", "Sweden"), "47": ("🇳🇴", "Norway"),
        "45": ("🇩🇰", "Denmark"), "358": ("🇫🇮", "Finland"),
        "351": ("🇵🇹", "Portugal"), "353": ("🇮🇪", "Ireland"),
        "48": ("🇵🇱", "Poland"), "380": ("🇺🇦", "Ukraine"),
        "90": ("🇹🇷", "Turkey"), "966": ("🇸🇦", "Saudi"),
        "971": ("🇦🇪", "UAE"), "974": ("🇶🇦", "Qatar"),
        "965": ("🇰🇼", "Kuwait"), "968": ("🇴🇲", "Oman"),
        "973": ("🇧🇭", "Bahrain"), "962": ("🇯🇴", "Jordan"),
        "961": ("🇱🇧", "Lebanon"), "964": ("🇮🇶", "Iraq"),
        "86": ("🇨🇳", "China"), "81": ("🇯🇵", "Japan"),
        "82": ("🇰🇷", "South Korea"), "84": ("🇻🇳", "Vietnam"),
        "66": ("🇹🇭", "Thailand"), "62": ("🇮🇩", "Indonesia"),
        "60": ("🇲🇾", "Malaysia"), "65": ("🇸🇬", "Singapore"),
        "63": ("🇵🇭", "Philippines"), "95": ("🇲🇲", "Myanmar"),
        "94": ("🇱🇰", "Sri Lanka"), "977": ("🇳🇵", "Nepal"),
        "55": ("🇧🇷", "Brazil"), "52": ("🇲🇽", "Mexico"),
        "54": ("🇦🇷", "Argentina"), "61": ("🇦🇺", "Australia"),
        "64": ("🇳🇿", "New Zealand"),
        "224": ("🇬🇳", "Guinea"), "228": ("🇹🇬", "Togo"),
    }
    for prefix in sorted(cmap.keys(), key=len, reverse=True):
        if num.startswith(prefix):
            return cmap[prefix]
    return ("🌍", "Unknown")

def detect_service(sms):
    if not sms:
        return "SMS SERVICE"
    s = sms.lower()
    kws = {
        "facebook": "FACEBOOK", "fb": "FACEBOOK", "instagram": "INSTAGRAM",
        "insta": "INSTAGRAM", "tiktok": "TIKTOK", "twitter": "TWITTER",
        "snapchat": "SNAPCHAT", "whatsapp": "WHATSAPP", "telegram": "TELEGRAM",
        "discord": "DISCORD", "messenger": "MESSENGER", "linkedin": "LINKEDIN",
        "google": "GOOGLE", "gmail": "GOOGLE", "amazon": "AMAZON",
        "microsoft": "MICROSOFT", "outlook": "MICROSOFT", "yahoo": "YAHOO",
        "paypal": "PAYPAL", "binance": "BINANCE", "coinbase": "COINBASE",
        "spotify": "SPOTIFY", "netflix": "NETFLIX", "uber": "UBER",
        "apple": "APPLE", "icloud": "APPLE", "bkash": "BKASH",
        "nagad": "NAGAD", "line": "LINE", "wechat": "WECHAT",
        "viber": "VIBER", "signal": "SIGNAL", "free fire": "FREEFIRE",
    }
    for kw, name in sorted(kws.items(), key=lambda x: len(x[0]), reverse=True):
        if kw in s:
            return name
    return "SMS SERVICE"

# ============================================================
# FILE DB HELPERS
# ============================================================
def load_data(fn):
    if not os.path.exists(fn):
        with open(fn, "w") as f:
            json.dump({}, f)
        return {}
    try:
        with open(fn, "r") as f:
            return json.load(f)
    except:
        return {}

def save_data(data, fn):
    with open(fn, "w") as f:
        json.dump(data, f, indent=4)

def get_otp_group_id():
    return OTP_GROUP_ID

def get_withdraw_group_id():
    return WITHDRAW_GROUP_ID

def get_breakup_group_id():
    return BREAKUP_GROUP_ID

# ============================================================
# PANEL MANAGER — ScarFace + MinoSMS + STEX + Zenex + JS SMS
# ============================================================
def pm_load():
    if not os.path.exists(PANELS_FILE):
        defaults = {
            "scarface_1": {
                "id": "scarface_1", "name": "ScarFace",
                "panel_type": "scarface",
                "base_url": "https://nexaotpservice.com/api/v1",
                "api_key": "sk_jyb1cUo",
                "header_name": "X-API-Key",
                "get_number_path": "/numbers/allocate", "get_number_method": "POST",
                "sms_path": "/numbers/batch-otps", "sms_method": "POST",
                "status": "ON", "priority": 1,
                "stats": {"numbers_fetched": 0, "otps_received": 0, "failures": 0},
                "circuit_open_until": 0
            },
            "minosms_1": {
                "id": "minosms_1", "name": "MinoSMS",
                "panel_type": "minosms",
                "base_url": "https://minosms.com",
                "api_key": "mino_live_fe99ec41ecd1c0891cf1a20518aa607d",
                "header_name": "mauthapi",
                "get_number_path": "/getnumber.php", "get_number_method": "POST",
                "sms_path": "/check.php", "sms_method": "GET",
                "status": "ON", "priority": 2,
                "stats": {"numbers_fetched": 0, "otps_received": 0, "failures": 0},
                "circuit_open_until": 0
            },
            "stex_1": {
                "id": "stex_1", "name": "STEX SMS",
                "panel_type": "stex",
                "base_url": "https://api.2oo9.cloud/MXS47FLFX0U/tness",
                "api_key": "MM68AEJHDZH",
                "header_name": "mauthapi",
                "get_number_path": "/@public/api/getnum", "get_number_method": "POST",
                "sms_path": "/@public/api/success-otp", "sms_method": "GET",
                "status": "ON", "priority": 3,
                "stats": {"numbers_fetched": 0, "otps_received": 0, "failures": 0},
                "circuit_open_until": 0
            },
            "zenex_1": {
                "id": "zenex_1", "name": "Zenex Network",
                "panel_type": "zenex",
                "base_url": "https://api.zenexnetwork.com",
                "api_key": "ZNX_ZKPQW3UUQGSK5L3TQS5ZPQVE",
                "header_name": "mapikey",
                "get_number_path": "/v1/getnum", "get_number_method": "POST",
                "sms_path": "/v1/numsuccess/info", "sms_method": "GET",
                "status": "ON", "priority": 4,
                "stats": {"numbers_fetched": 0, "otps_received": 0, "failures": 0},
                "circuit_open_until": 0
            },
            "jssms_1": {
                "id": "jssms_1", "name": "JS SMS Panel",
                "panel_type": "jssms",
                "base_url": "https://jssmspanel.com",
                "api_key": "92d1nnjmu0TnCn4OXOxbJfC62tx1-JSAPI-XYZ987",
                "header_name": "Authorization",
                "header_prefix": "Bearer ",
                "get_number_path": "/api/external/get-number", "get_number_method": "POST",
                "sms_path": "/api/external/check-otp", "sms_method": "GET",
                "needs_service": True,
                "status": "ON", "priority": 5,
                "stats": {"numbers_fetched": 0, "otps_received": 0, "failures": 0},
                "circuit_open_until": 0
            }
        }
        pm_save(defaults)
        return defaults
    try:
        with open(PANELS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def pm_save(p):
    with open(PANELS_FILE, "w", encoding="utf-8") as f:
        json.dump(p, f, indent=2, ensure_ascii=False)

def pm_active():
    panels = pm_load()
    now = time.time()
    out = []
    for p in panels.values():
        if p.get("status") != "ON":
            continue
        if now < p.get("circuit_open_until", 0):
            continue
        out.append(p)
    out.sort(key=lambda x: x.get("priority", 999))
    return out

def pm_resolve_priority(priority_list):
    if not priority_list:
        return pm_active()
    panels = pm_load()
    resolved = []
    seen = set()
    for p in priority_list:
        p_clean = p.strip().lower()
        if p_clean in panels and p_clean not in seen:
            panel = panels[p_clean]
            if panel.get("status") == "ON":
                resolved.append(panel)
                seen.add(p_clean)
    for p in priority_list:
        p_clean = p.strip().lower()
        for pid, panel in panels.items():
            if pid in seen:
                continue
            if panel.get("status") != "ON":
                continue
            pname = panel.get("name", "").lower()
            if p_clean in pname or p_clean in pid:
                resolved.append(panel)
                seen.add(pid)
                break
    if not resolved:
        return pm_active()
    return resolved

def pm_toggle(pid):
    panels = pm_load()
    if pid not in panels:
        return None
    cur = panels[pid].get("status", "ON")
    panels[pid]["status"] = "OFF" if cur == "ON" else "ON"
    if panels[pid]["status"] == "ON":
        panels[pid]["circuit_open_until"] = 0
        panels[pid]["stats"]["failures"] = 0
    pm_save(panels)
    return panels[pid]["status"]

def pm_update_field(pid, field, value):
    panels = pm_load()
    if pid in panels:
        panels[pid][field] = value
        pm_save(panels)
        return True
    return False

def pm_delete(pid):
    panels = pm_load()
    if pid in panels:
        del panels[pid]
        pm_save(panels)
        return True
    return False

def pm_add(name, base_url, api_key, header, get_path="/getnum",
           get_method="POST", sms_path="/success-otp", sms_method="GET"):
    panels = pm_load()
    base_id = re.sub(r'[^a-z0-9]', '_', name.lower())[:20]
    pid = f"{base_id}_1"
    i = 1
    while pid in panels:
        i += 1
        pid = f"{base_id}_{i}"
    max_pri = max([p.get("priority", 0) for p in panels.values()], default=0)
    panels[pid] = {
        "id": pid, "name": name,
        "panel_type": "generic",
        "base_url": base_url.rstrip("/"),
        "api_key": api_key, "header_name": header,
        "get_number_path": get_path, "get_number_method": get_method.upper(),
        "sms_path": sms_path, "sms_method": sms_method.upper(),
        "status": "ON", "priority": max_pri + 1,
        "stats": {"numbers_fetched": 0, "otps_received": 0, "failures": 0},
        "circuit_open_until": 0
    }
    pm_save(panels)
    return pid

def pm_update_stats(pid, key, inc=1):
    panels = pm_load()
    if pid not in panels:
        return
    s = panels[pid].setdefault("stats", {})
    s[key] = s.get(key, 0) + inc
    pm_save(panels)

def pm_record_failure(pid):
    panels = pm_load()
    if pid not in panels:
        return
    s = panels[pid].setdefault("stats", {})
    s["failures"] = s.get("failures", 0) + 1
    if s["failures"] >= 5:
        panels[pid]["circuit_open_until"] = time.time() + 300
        s["failures"] = 0
    pm_save(panels)

def pm_record_success(pid):
    panels = pm_load()
    if pid not in panels:
        return
    panels[pid].setdefault("stats", {})["failures"] = 0
    pm_save(panels)

_pm_client = httpx.AsyncClient(
    timeout=httpx.Timeout(connect=5.0, read=12.0, write=10.0, pool=15.0),
    limits=httpx.Limits(max_connections=200, max_keepalive_connections=100)
)
PANEL_TIMEOUT = 10

# ==================== NUMBER PARSERS ====================
def _num_scarface(r):
    if not isinstance(r, dict):
        return ""
    num = r.get("msisdn") or r.get("number") or ""
    if num:
        return num
    d = r.get("data", {})
    if isinstance(d, dict):
        return d.get("msisdn") or d.get("number") or d.get("full_number") or ""
    return ""

def _num_minosms(r):
    if not isinstance(r, dict):
        return ""
    d = r.get("data", {})
    if isinstance(d, dict):
        num = d.get("full_number") or d.get("number") or d.get("no_plus_number") or d.get("national_number") or ""
        if num:
            return num
    return r.get("full_number") or r.get("number") or r.get("msisdn") or ""

def _num_stex(r):
    d = r.get("data", {})
    return d.get("full_number") or d.get("no_plus_number") or d.get("national_number") or ""

def _num_zenex(r):
    d = r.get("data", {})
    return d.get("full_number") or d.get("number") or ""

def _num_jssms(r):
    d = r.get("data", {})
    return d.get("number") or ""

def _num_parser(p):
    t = (p.get("panel_type") or p.get("name", "")).lower()
    if t in ("scarface", "scarface sms"):
        return _num_scarface
    if t in ("minosms", "mino"):
        return _num_minosms
    if t in ("stex", "stex sms"):
        return _num_stex
    if t in ("zenex", "zenex network"):
        return _num_zenex
    if t in ("jssms", "js sms panel"):
        return _num_jssms

    def g(d):
        dd = d.get("data", d)
        return dd.get("full_number") or dd.get("number") or dd.get("national_number") or ""
    return g

# ==================== SMS PARSERS ====================
def _sms_scarface(r, panel=None):
    out = []
    if not isinstance(r, dict):
        return out
    data = r.get("data", {})
    if isinstance(data, dict):
        for num_id, otp_list in data.items():
            if isinstance(otp_list, list):
                for item in otp_list:
                    if not isinstance(item, dict):
                        continue
                    out.append({
                        "number": "",
                        "message": item.get("rawMessage", "") or item.get("message", ""),
                        "otp": item.get("code", "") or item.get("otp", ""),
                        "nid": item.get("id", "") or f"{num_id}_{item.get('code','')}",
                        "_number_id": num_id,
                    })
    if not out:
        nums = r.get("numbers", [])
        if isinstance(nums, list):
            for n in nums:
                if not isinstance(n, dict):
                    continue
                num_id = n.get("numberId", "") or n.get("id", "")
                msisdn = n.get("msisdn", "")
                otps = n.get("otps", [])
                if not isinstance(otps, list):
                    continue
                for item in otps:
                    if not isinstance(item, dict):
                        continue
                    out.append({
                        "number": msisdn,
                        "message": item.get("rawMessage", "") or item.get("message", ""),
                        "otp": item.get("code", "") or item.get("otp", ""),
                        "nid": item.get("id", ""),
                        "_number_id": num_id,
                    })
    return out

def _sms_minosms(r, panel=None):
    """
    MinoSMS check.php response handler.
    Supports:
      - Single OTP direct: {"status":"success", "otp":"123456", "message":"..."}
      - Single OTP inside data: {"status":"success", "data":{"otp":"123456", ...}}
      - List of OTPs: {"otps":[...]} or {"data":{"otps":[...]}}
    """
    out = []
    if not isinstance(r, dict):
        return out

    # --- Case 1: Direct single OTP at root ---
    if r.get("status") == "success" and (r.get("otp") or r.get("code") or r.get("otp_code")):
        out.append({
            "number": r.get("number", "") or r.get("msisdn", ""),
            "message": r.get("message", "") or r.get("full_message", "") or r.get("text", ""),
            "otp": r.get("otp", "") or r.get("code", "") or r.get("otp_code", ""),
            "nid": str(r.get("id", "")) or str(r.get("message_id", "")) or str(r.get("otp_id", ""))
        })
        return out

    # --- Case 2: OTP inside data dict (single) ---
    d = r.get("data")
    if isinstance(d, dict):
        if d.get("otp") or d.get("code") or d.get("otp_code"):
            out.append({
                "number": d.get("number", "") or d.get("msisdn", ""),
                "message": d.get("message", "") or d.get("full_message", "") or d.get("text", ""),
                "otp": d.get("otp", "") or d.get("code", "") or d.get("otp_code", ""),
                "nid": str(d.get("id", "")) or str(d.get("message_id", "")) or str(d.get("otp_id", ""))
            })
            return out

    # --- Case 3: List of OTPs somewhere ---
    otps = []
    if isinstance(r.get("otps"), list):
        otps = r["otps"]
    elif isinstance(r.get("sms"), list):
        otps = r["sms"]
    elif isinstance(r.get("messages"), list):
        otps = r["messages"]
    elif isinstance(d, dict):
        if isinstance(d.get("otps"), list):
            otps = d["otps"]
        elif isinstance(d.get("sms"), list):
            otps = d["sms"]
        elif isinstance(d.get("messages"), list):
            otps = d["messages"]
    elif isinstance(d, list):
        otps = d

    for item in otps:
        if not isinstance(item, dict):
            continue
        out.append({
            "number": item.get("number", "") or item.get("msisdn", ""),
            "message": item.get("message", "") or item.get("full_message", "") or item.get("text", "") or item.get("body", ""),
            "otp": item.get("otp_code", "") or item.get("otp", "") or item.get("code", ""),
            "nid": str(item.get("id", "")) or str(item.get("message_id", "")) or f"{item.get('number','')}_{item.get('otp_code','')}"
        })
    return out

def _sms_stex(r, panel=None):
    if r.get("meta", {}).get("code") == 200:
        otps = r.get("data", {}).get("otps", [])
        out = []
        for item in otps:
            out.append({
                "number": item.get("number", ""),
                "message": item.get("message", ""),
                "otp": "",
                "nid": str(item.get("otp_id", ""))
            })
        return out
    return []

def _sms_zenex(r, panel=None):
    if r.get("meta", {}).get("status") == "success":
        return r.get("data", {}).get("otps", [])
    return []

def _sms_jssms(r, panel=None):
    if r.get("meta", {}).get("code") == 200 or r.get("meta", {}).get("status") == "ok":
        otps = r.get("data", {}).get("otps", [])
        out = []
        for item in otps:
            out.append({
                "number": item.get("number", ""),
                "message": item.get("full_message", "") or item.get("message", ""),
                "otp": item.get("otp", ""),
                "service": item.get("service", ""),
                "nid": f"{item.get('number','')}_{item.get('otp','')}"
            })
        return out
    return []

def _sms_parser(p):
    t = (p.get("panel_type") or p.get("name", "")).lower()
    if t in ("scarface", "scarface sms"):
        return _sms_scarface
    if t in ("minosms", "mino"):
        return _sms_minosms
    if t in ("stex", "stex sms"):
        return _sms_stex
    if t in ("zenex", "zenex network"):
        return _sms_zenex
    if t in ("jssms", "js sms panel"):
        return _sms_jssms

    def g(r):
        if r.get("meta", {}).get("status") == "success":
            return r.get("data", {}).get("otps", [])
        if r.get("meta", {}).get("code") == 200:
            return r.get("data", {}).get("otps", [])
        return []
    return g

def _build_headers(panel):
    h = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json, text/plain, */*",
    }
    hname = panel.get("header_name", "")
    prefix = panel.get("header_prefix", "")
    if hname:
        h[hname] = f"{prefix}{panel.get('api_key','')}"
    return h

async def pm_fetch_number(panel, range_str, service=""):
    pid = panel.get("id", "unknown")
    try:
        url = panel["base_url"] + panel["get_number_path"]
        headers = _build_headers(panel)
        method = panel.get("get_number_method", "POST").upper()
        ptype = (panel.get("panel_type") or "").lower()

        if ptype in ("scarface", "scarface sms"):
            r_clean = re.sub(r'[xX]+$', '', range_str).strip()
            body = {"prefix": r_clean}
        elif ptype in ("minosms", "mino"):
            r_clean = re.sub(r'[xX]+$', '', range_str).strip()
            body = {"rid": r_clean}
        elif ptype in ("stex", "stex sms"):
            r_clean = re.sub(r'[xX]+$', '', range_str).strip()
            body = {"rid": r_clean}
        elif ptype in ("zenex", "zenex network"):
            body = {"range": range_str, "is_national": False, "remove_plus": False}
        elif ptype in ("jssms", "js sms panel"):
            r_clean = re.sub(r'[xX]+$', '', range_str).strip()
            svc = (service or "telegram").lower()
            body = {"service": svc, "range": r_clean}
        else:
            body = {"range": range_str}

        if method == "POST":
            r = await asyncio.wait_for(_pm_client.post(url, json=body, headers=headers), timeout=PANEL_TIMEOUT)
        else:
            r = await asyncio.wait_for(_pm_client.get(url, params=body, headers=headers), timeout=PANEL_TIMEOUT)

        if r.status_code not in (200, 201):
            print(f"❌ [{pid}] HTTP {r.status_code}: {r.text[:200]}")
            pm_record_failure(pid)
            return None
        try:
            resp = r.json()
        except Exception as e:
            print(f"❌ [{pid}] JSON parse: {e}")
            pm_record_failure(pid)
            return None

        ok = (resp.get("success") is True
              or resp.get("status") in ("success", "ok", "held", "active")
              or resp.get("meta", {}).get("status") in ("success", "ok")
              or resp.get("meta", {}).get("code") == 200
              or resp.get("id")
              or resp.get("msisdn"))
        if not ok:
            print(f"⚠️ [{pid}] Not OK: {str(resp)[:150]}")
            return None

        num = _num_parser(panel)(resp)
        if not num:
            print(f"⚠️ [{pid}] No number: {str(resp)[:150]}")
            return None
        clean = re.sub(r'\D', '', str(num))
        if not clean or len(clean) < 6:
            return None

        number_id = ""
        if ptype in ("scarface", "scarface sms"):
            number_id = resp.get("id", "") or resp.get("numberId", "") or resp.get("number_id", "")
            if not number_id:
                d = resp.get("data", {})
                if isinstance(d, dict):
                    number_id = d.get("id", "") or d.get("numberId", "")

        pm_record_success(pid)
        return {
            "number": clean,
            "panel_id": pid,
            "panel_name": panel.get("name", "Unknown"),
            "number_id": number_id,
        }
    except asyncio.TimeoutError:
        print(f"⏱ [{pid}] Timeout")
        pm_record_failure(pid)
        return None
    except Exception as e:
        print(f"❌ [{pid}]: {e}")
        pm_record_failure(pid)
        return None

async def pm_fetch_any(range_str, service="", priority_list=None):
    if priority_list:
        panels = pm_resolve_priority(priority_list)
    else:
        panels = pm_active()
    if not panels:
        return None
    tasks = [pm_fetch_number(p, range_str, service) for p in panels]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    ok = []
    for i, res in enumerate(results):
        if isinstance(res, dict) and res.get("number"):
            ok.append((i, res))
    if not ok:
        return None
    ok.sort(key=lambda x: x[0])
    winner = ok[0][1]
    pm_update_stats(winner["panel_id"], "numbers_fetched")
    return winner

async def pm_fetch_sms(panel):
    pid = panel.get("id", "unknown")
    ptype = (panel.get("panel_type") or "").lower()
    try:
        # --- ScarFace: POST with empty body, returns batch OTPs ---
        if ptype in ("scarface", "scarface sms"):
            url = panel["base_url"] + panel["sms_path"]
            headers = _build_headers(panel)
            body = {"ids": []}
            r = await asyncio.wait_for(
                _pm_client.post(url, json=body, headers=headers, timeout=PANEL_TIMEOUT),
                timeout=PANEL_TIMEOUT
            )
            if r.status_code != 200:
                print(f"❌ SMS [ScarFace] HTTP {r.status_code}: {r.text[:200]}")
                return []
            try:
                resp = r.json()
            except:
                return []
            return _sms_scarface(resp, panel) or []

        # --- MinoSMS: per-number GET with api_key + number ---
        elif ptype in ("minosms", "mino"):
            url = panel["base_url"] + panel["sms_path"]
            minosms_numbers = []
            for num, info in active_numbers.items():
                if info.get("panel_id") == pid:
                    minosms_numbers.append(num)
            if not minosms_numbers:
                return []
            all_results = []
            for num in minosms_numbers:
                try:
                    params = {
                        "api_key": panel.get("api_key", ""),
                        "number": f"+{num}",
                    }
                    r = await asyncio.wait_for(
                        _pm_client.get(url, params=params, timeout=PANEL_TIMEOUT),
                        timeout=PANEL_TIMEOUT
                    )
                    if r.status_code != 200:
                        continue
                    try:
                        resp = r.json()
                    except:
                        continue
                    results = _sms_minosms(resp, panel) or []
                    for item in results:
                        if not item.get("number"):
                            item["number"] = num
                    all_results.extend(results)
                except Exception as e:
                    print(f"❌ SMS [MinoSMS] {num}: {e}")
                    continue
            return all_results

        # --- Others: standard GET/POST ---
        url = panel["base_url"] + panel["sms_path"]
        headers = _build_headers(panel)
        method = panel.get("sms_method", "GET").upper()
        if method == "POST":
            r = await asyncio.wait_for(_pm_client.post(url, json={}, headers=headers), timeout=PANEL_TIMEOUT)
        else:
            r = await asyncio.wait_for(_pm_client.get(url, headers=headers), timeout=PANEL_TIMEOUT)
        if r.status_code != 200:
            return []
        try:
            resp = r.json()
        except:
            return []
        return _sms_parser(panel)(resp) or []
    except Exception as e:
        print(f"❌ SMS [{pid}]: {e}")
        return []

async def pm_test(panel):
    try:
        ptype = (panel.get("panel_type") or "").lower()

        # --- ScarFace: wallet/balance endpoint ---
        if ptype in ("scarface", "scarface sms"):
            url = panel["base_url"] + "/wallet/balance"
            headers = _build_headers(panel)
            r = await asyncio.wait_for(_pm_client.get(url, headers=headers), timeout=10)
            if r.status_code == 200:
                try:
                    d = r.json()
                    bal = d.get("balance", 0)
                    rate = d.get("otpRate", 0)
                    return True, f"✅ Connected!\n💰 Balance: {bal} BDT\n📊 Rate: {rate}"
                except:
                    return True, "✅ Connected!"
            elif r.status_code in (401, 403):
                return False, f"❌ Auth fail ({r.status_code})"
            else:
                return False, f"❌ HTTP {r.status_code}: {r.text[:100]}"

        # --- MinoSMS: check.php with dummy number (404 = OK) ---
        elif ptype in ("minosms", "mino"):
            url = panel["base_url"] + panel["sms_path"]
            params = {
                "api_key": panel.get("api_key", ""),
                "number": "+8801700000000",
            }
            try:
                r = await asyncio.wait_for(
                    _pm_client.get(url, params=params, timeout=10),
                    timeout=10
                )
                if r.status_code == 200:
                    return True, "✅ Connected!"
                elif r.status_code in (400, 404):
                    try:
                        resp = r.json()
                        msg = resp.get("message", "") or resp.get("status", "")
                        return True, f"✅ Connected! (API alive)\n   {msg[:60]}"
                    except:
                        return True, "✅ Connected! (API alive)"
                elif r.status_code in (401, 403):
                    return False, f"❌ Auth fail ({r.status_code}) — Check API key"
                else:
                    return False, f"❌ HTTP {r.status_code}: {r.text[:100]}"
            except asyncio.TimeoutError:
                return False, "❌ Timeout"
            except Exception as e:
                return False, f"❌ {str(e)[:100]}"

        # --- Others ---
        url = panel["base_url"] + panel["sms_path"]
        headers = _build_headers(panel)
        r = await asyncio.wait_for(_pm_client.get(url, headers=headers), timeout=10)
        if r.status_code == 200:
            try:
                d = r.json()
                if isinstance(d, dict) and (d.get("success") or d.get("meta")):
                    return True, "✅ Connected!"
                return True, "⚠️ HTTP 200"
            except:
                return False, "❌ Invalid JSON"
        elif r.status_code in (401, 403):
            return False, f"❌ Auth fail ({r.status_code})"
        else:
            return False, f"❌ HTTP {r.status_code}"
    except asyncio.TimeoutError:
        return False, "❌ Timeout"
    except Exception as e:
        return False, f"❌ {str(e)[:60]}"

# ============================================================
# FORCE JOIN
# ============================================================
def load_fj():
    if not os.path.exists(FORCE_JOIN_FILE):
        with open(FORCE_JOIN_FILE, "w") as f:
            json.dump([], f)
        return []
    try:
        with open(FORCE_JOIN_FILE, "r") as f:
            return json.load(f)
    except:
        return []

def save_fj(l):
    with open(FORCE_JOIN_FILE, "w") as f:
        json.dump(l, f, indent=4)

async def check_joined(bot, uid, ch):
    try:
        m = await bot.get_chat_member(chat_id=ch, user_id=uid)
        return m.status in ["creator", "administrator", "member", "restricted"]
    except:
        return False

async def get_unjoined(bot, uid):
    chs = load_fj()
    if not chs:
        return []
    out = []
    for ch in chs:
        cid = ch.get("id")
        if not cid:
            continue
        if not await check_joined(bot, uid, cid):
            out.append(ch)
    return out

def fj_keyboard(unjoined):
    btns = []
    for ch in unjoined:
        cid = ch.get("id")
        name = ch.get("name", "Channel")
        if isinstance(cid, str) and cid.startswith("@"):
            url = f"https://t.me/{cid[1:]}"
        elif isinstance(cid, str) and cid.startswith("-"):
            url = f"https://t.me/c/{str(cid)[4:]}/1"
        else:
            url = f"https://t.me/{cid}"
        btns.append([InlineKeyboardButton(f"📢 {name}", url=url, style="primary")])
    btns.append([InlineKeyboardButton("✅ I HAVE JOINED", callback_data="fj_check", style="success")])
    return InlineKeyboardMarkup(btns)

async def fj_gate(update, context):
    if not FORCE_JOIN_ENABLED:
        return True
    uid = update.effective_user.id
    if is_admin(uid):
        return True
    unj = await get_unjoined(context.bot, uid)
    if not unj:
        return True
    text = "🚫 <b>JOIN REQUIRED</b>\n━━━━━━━━━━━━━━━\n\n<blockquote>আপনি সব চ্যানেলে join করেননি!</blockquote>"
    kb = fj_keyboard(unj)
    if update.callback_query:
        try:
            await update.callback_query.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
        except:
            pass
    elif update.message:
        await update.message.reply_text(text, parse_mode="HTML", reply_markup=kb)
    return False

# ============================================================
# RUNTIME STATE
# ============================================================
active_numbers = {}
last_range = {}
request_queue = asyncio.Queue()

# ============================================================
# KEYBOARDS
# ============================================================
def main_keyboard(uid):
    kb = [
        [KeyboardButton(f"📞 {make_bold_unicode('GET NUMBER')}", style="primary")],
        [KeyboardButton(f"💸 {make_bold_unicode('WITHDRAW')}", style="success"),
         KeyboardButton(f"👤 {make_bold_unicode('PROFILE')}", style="primary")],
        [KeyboardButton(f"👥 {make_bold_unicode('REFER AND EARN')}", style="primary"),
         KeyboardButton(f"🏆 {make_bold_unicode('LEADERBOARD')}", style="primary")],
        [KeyboardButton(f"💬 {make_bold_unicode('SUPPORT')}", style="primary")]
    ]
    if is_admin(uid):
        kb.append([KeyboardButton(f"⚙️ {make_bold_unicode('ADMIN PANEL')} ⚙️", style="danger")])
    return ReplyKeyboardMarkup(kb, resize_keyboard=True)

def cancel_keyboard():
    return ReplyKeyboardMarkup([[KeyboardButton(f"❌ {make_bold_unicode('CANCEL')}", style="danger")]], resize_keyboard=True)

def withdraw_method_keyboard():
    return ReplyKeyboardMarkup([
        [KeyboardButton(f"📱 {make_bold_unicode('BKASH')}", style="primary"),
         KeyboardButton(f"💵 {make_bold_unicode('NAGAD')}", style="primary")],
        [KeyboardButton(f"🚀 {make_bold_unicode('ROCKET')}", style="primary"),
         KeyboardButton(f"🏦 {make_bold_unicode('BINANCE')}", style="primary")],
        [KeyboardButton(f"❌ {make_bold_unicode('CANCEL')}", style="danger")]
    ], resize_keyboard=True)

def admin_main_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(make_bold_unicode("⚙️ SYSTEM SETTINGS"), callback_data="sys_settings", style="primary")],
        [InlineKeyboardButton(make_bold_unicode("📦 SERVICE MANAGEMENT"), callback_data="svc_list", style="success")],
        [InlineKeyboardButton(make_bold_unicode("👥 USER MANAGEMENT"), callback_data="usr_mgmt", style="primary")],
        [InlineKeyboardButton(make_bold_unicode("📊 PANEL USAGE LOG"), callback_data="pm_usage_log", style="primary")],
        [InlineKeyboardButton(make_bold_unicode("⚙️ SYSTEM CONFIG"), callback_data="adm_sys", style="primary")],
        [InlineKeyboardButton(make_bold_unicode("🔗 FORCE JOIN"), callback_data="fj_menu", style="success")],
        [InlineKeyboardButton(make_bold_unicode("🔙 BACK"), callback_data="adm_back_main", style="danger")]
    ])

def sys_settings_kb():
    panels = pm_load()
    btns = []
    panel_btns = []
    for pid, p in panels.items():
        st = p.get("status", "ON")
        icon = "🟢" if st == "ON" else "🔴"
        name = p.get("name", pid)
        panel_btns.append(InlineKeyboardButton(f"{icon} {name}", callback_data=f"pm_view_{pid}", style="primary"))
    for i in range(0, len(panel_btns), 2):
        btns.append(panel_btns[i:i+2])
    btns.append([InlineKeyboardButton(make_bold_unicode("➕ ADD NEW PANEL"), callback_data="pm_add", style="success")])
    btns.append([InlineKeyboardButton(make_bold_unicode("📋 PANEL MANAGEMENT"), callback_data="pm_list", style="primary")])
    btns.append([InlineKeyboardButton(make_bold_unicode("📢 GROUP CONFIGURATION"), callback_data="grp_config", style="primary")])
    btns.append([InlineKeyboardButton(make_bold_unicode("🔗 FORCE JOIN SYSTEM"), callback_data="fj_menu", style="success")])
    btns.append([InlineKeyboardButton(make_bold_unicode("🧪 TEST ALL PANELS"), callback_data="sys_test_all", style="success")])
    btns.append([InlineKeyboardButton(make_bold_unicode("🔙 BACK"), callback_data="adm_back_admin", style="danger")])
    return InlineKeyboardMarkup(btns)

def pm_main_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(make_bold_unicode("📋 LIST PANELS"), callback_data="pm_list", style="primary")],
        [InlineKeyboardButton(make_bold_unicode("➕ ADD PANEL"), callback_data="pm_add", style="success")],
        [InlineKeyboardButton(make_bold_unicode("📊 USAGE LOG"), callback_data="pm_usage_log", style="success")],
        [InlineKeyboardButton(make_bold_unicode("🔙 BACK"), callback_data="sys_settings", style="danger")]
    ])

def adm_sys_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(make_bold_unicode("⛔ BAN"), callback_data="adm_ban", style="danger"),
         InlineKeyboardButton(make_bold_unicode("🔓 UNBAN"), callback_data="adm_unban", style="success")],
        [InlineKeyboardButton(make_bold_unicode("📜 BANNED LIST"), callback_data="adm_banlist", style="primary")],
        [InlineKeyboardButton(make_bold_unicode("📢 BROADCAST"), callback_data="adm_broadcast", style="primary")],
        [InlineKeyboardButton(make_bold_unicode("🔙 BACK"), callback_data="adm_back_admin", style="danger")]
    ])

def fj_admin_kb():
    chs = load_fj()
    btns = []
    for i, ch in enumerate(chs):
        btns.append([
            InlineKeyboardButton(f"📢 {ch.get('name','Ch')}", callback_data=f"fj_noop_{i}", style="primary"),
            InlineKeyboardButton("❌", callback_data=f"fj_del_{i}", style="danger")
        ])
    btns.append([InlineKeyboardButton(make_bold_unicode("➕ ADD"), callback_data="fj_add", style="success")])
    btns.append([InlineKeyboardButton(make_bold_unicode("🔙 BACK"), callback_data="sys_settings", style="danger")])
    return InlineKeyboardMarkup(btns)

# ============================================================
# COMMAND HANDLERS
# ============================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await fj_gate(update, context):
        return
    uid = update.effective_user.id
    user = update.effective_user
    full_name = user.full_name or user.first_name or "User"

    existing = load_data(USER_DATA_FILE)
    is_new = str(uid) not in existing
    if is_new:
        um_add_balance(uid, 0)

    try:
        um_set_name(uid, full_name)
    except:
        pass

    args = context.args
    if args:
        param = args[0]
        if param.isdigit() and is_new:
            try:
                ref = int(param)
                if ref != uid and str(ref) in existing:
                    refs_data = load_data(REFERRAL_DATA_FILE)
                    r = str(ref)
                    if r not in refs_data:
                        refs_data[r] = {"referral_count": 0, "referred_users": []}
                    refs_data[r]["referral_count"] = refs_data[r].get("referral_count", 0) + 1
                    if "referred_users" not in refs_data[r]:
                        refs_data[r]["referred_users"] = []
                    refs_data[r]["referred_users"].append({
                        "uid": str(uid),
                        "joined_at": get_bd_time().isoformat()
                    })
                    save_data(refs_data, REFERRAL_DATA_FILE)
                    um_add_balance(ref, REFERRAL_PRICE)
                    try:
                        users = load_data(USER_DATA_FILE)
                        if r in users:
                            users[r]["referral_count"] = refs_data[r]["referral_count"]
                            save_data(users, USER_DATA_FILE)
                    except:
                        pass
                    try:
                        new_bal = um_get_balance(ref)
                        await context.bot.send_message(ref,
                            f"🎉 <b>NEW REFERRAL!</b>\n\n"
                            f"<blockquote>🆔 New User: <code>{uid}</code>\n"
                            f"💰 +{int(REFERRAL_PRICE)} BDT\n"
                            f"💵 New Balance: <code>{format_balance(new_bal)} BDT</code></blockquote>",
                            parse_mode="HTML")
                    except:
                        pass
            except:
                pass
    context.user_data.clear()
    await update.message.reply_text(WELCOME_MESSAGE, parse_mode="Markdown")
    await update.message.reply_text("🔹 PLEASE USE THE BUTTONS BELOW:", reply_markup=main_keyboard(uid))

async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if um_is_banned(uid):
        await update.message.reply_text("🚫 YOU ARE BANNED", reply_markup=main_keyboard(uid))
        return
    if not await fj_gate(update, context):
        return
    bal = um_get_balance(uid)
    await update.message.reply_text(f"💰 BALANCE: `{format_balance(bal)} BDT`", parse_mode="Markdown", reply_markup=main_keyboard(uid))

async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if um_is_banned(uid):
        await update.message.reply_text("🚫 BANNED", reply_markup=main_keyboard(uid))
        return
    if not await fj_gate(update, context):
        return
    ud = um_get_user_data(uid) or {}
    st = get_user_stats_legacy(uid)
    user = update.effective_user
    txt = (
        f"👤 **YOUR PROFILE**\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🏷️ NAME: `{user.full_name}`\n"
        f"🆔 USERNAME: @{user.username or 'No username'}\n"
        f"🗝️ ID: `{uid}`\n\n"
        f"💵 BALANCE: {format_balance(ud.get('balance', 0))} BDT\n\n"
        f"✨ TODAY: 📱 {st['today_numbers']} | 🔑 {st['today_otps']}\n"
        f"🔥 7 DAYS: 📱 {st['last7d_numbers']} | 🔑 {st['last7d_otps']}\n"
        f"🌐 ALL TIME: 📱 {st['total_numbers']} | 🔑 {st['total_otps']}"
    )
    await update.message.reply_text(txt, parse_mode="Markdown", reply_markup=main_keyboard(uid))

async def refer_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if um_is_banned(uid):
        await update.message.reply_text("🚫 BANNED", reply_markup=main_keyboard(uid))
        return
    if not await fj_gate(update, context):
        return
    bot_info = await context.bot.get_me()
    link = f"https://t.me/{bot_info.username}?start={uid}"
    refs_data = load_data(REFERRAL_DATA_FILE)
    cnt = refs_data.get(str(uid), {}).get("referral_count", 0)
    earned = cnt * REFERRAL_PRICE
    msg = (
        f"🎁 <b>REFER AND EARN</b> 🎁\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<blockquote>🚀 প্রতি referral এ <b>{int(REFERRAL_PRICE)} টাকা</b>!</blockquote>\n\n"
        f"<b>🔗 YOUR LINK:</b>\n<blockquote><code>{link}</code></blockquote>\n\n"
        f"<b>📊 STATS:</b>\n"
        f"<blockquote>👥 Refers: <code>{cnt}</code>\n"
        f"💰 Earned: <code>{format_balance(earned)} BDT</code></blockquote>"
    )
    await update.message.reply_text(msg, parse_mode="HTML", disable_web_page_preview=True,
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("💸 WITHDRAW", callback_data="withdraw_start", style="success")
        ]]))

async def leaderboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if um_is_banned(uid):
        await update.message.reply_text("🚫 BANNED", reply_markup=main_keyboard(uid))
        return
    if not await fj_gate(update, context):
        return
    rows = um_get_today_otp_users(10)
    if not rows:
        msg = "<b>🏆 TOP 10 OTP LEADERBOARD 🏆</b>\n━━━━━━━━━━━━━━━━━━━━\n\n❌ আজ কেউ OTP পায়নি।"
    else:
        msg = "<b>🏆 TOP 10 OTP (TODAY) 🏆</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
        for i, (u, c, n) in enumerate(rows, 1):
            m = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}️⃣"
            name = html.escape(n) if n and n != "User" else f"User {u[-4:]}"
            msg += f"{m} <b>{name}</b>\n   🔑 <code>{c}</code> OTPs\n\n"
    await update.message.reply_text(msg, parse_mode="HTML", reply_markup=main_keyboard(uid))

# ============================================================
# LEGACY USER STATS
# ============================================================
def load_stats_legacy():
    if not os.path.exists(STATS_FILE):
        with open(STATS_FILE, "w") as f:
            json.dump({}, f)
        return {}
    try:
        with open(STATS_FILE, "r") as f:
            return json.load(f)
    except:
        return {}

def save_stats_legacy(s):
    with open(STATS_FILE, "w") as f:
        json.dump(s, f, indent=4)

def add_number_taken(uid, count=1):
    uid = str(uid)
    s = load_stats_legacy()
    if uid not in s:
        s[uid] = {"numbers_taken": [], "otps_received": []}
    s[uid].setdefault("numbers_taken", [])
    now = get_bd_time().isoformat()
    for _ in range(count):
        s[uid]["numbers_taken"].append(now)
    save_stats_legacy(s)

def add_otp_received(uid):
    uid = str(uid)
    s = load_stats_legacy()
    if uid not in s:
        s[uid] = {"numbers_taken": [], "otps_received": []}
    s[uid].setdefault("otps_received", [])
    s[uid]["otps_received"].append(get_bd_time().isoformat())
    save_stats_legacy(s)

def get_user_stats_legacy(uid):
    uid = str(uid)
    s = load_stats_legacy().get(uid, {"numbers_taken": [], "otps_received": []})
    now = get_bd_time()
    today = datetime(now.year, now.month, now.day)
    last7 = now - timedelta(days=7)
    nlist = s.get("numbers_taken", [])
    olist = s.get("otps_received", [])
    t_n = t_o = s_n = s_o = 0
    for t in nlist:
        try:
            dt = datetime.fromisoformat(t)
            if dt >= today:
                t_n += 1
            if dt >= last7:
                s_n += 1
        except:
            continue
    for t in olist:
        try:
            dt = datetime.fromisoformat(t)
            if dt >= today:
                t_o += 1
            if dt >= last7:
                s_o += 1
        except:
            continue
    return {
        "total_numbers": len(nlist), "total_otps": len(olist),
        "today_numbers": t_n, "today_otps": t_o,
        "last7d_numbers": s_n, "last7d_otps": s_o
    }

# ============================================================
# WITHDRAW STORAGE
# ============================================================
def load_withdrawals():
    if not os.path.exists(WITHDRAW_DATA_FILE):
        with open(WITHDRAW_DATA_FILE, "w") as f:
            json.dump({}, f)
        return {}
    try:
        with open(WITHDRAW_DATA_FILE, "r") as f:
            return json.load(f)
    except:
        return {}

def save_withdrawals(d):
    with open(WITHDRAW_DATA_FILE, "w") as f:
        json.dump(d, f, indent=4)

def gen_payment_id():
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=20))

# ============================================================
# SHOW SERVICES
# ============================================================
async def show_services(update, context):
    uid = update.effective_user.id
    if um_is_banned(uid):
        await update.message.reply_text("🚫 BANNED", reply_markup=main_keyboard(uid))
        return
    if not await fj_gate(update, context):
        return

    services = get_all_services()
    if not services:
        await update.message.reply_text(
            "⚠️ <b>কোনো Service নেই!</b>\n\nAdmin Panel থেকে Service add করুন।",
            parse_mode="HTML", reply_markup=main_keyboard(uid))
        return

    btns = []
    for srv_name, srv_data in services.items():
        icon = srv_data.get("icon", "🚀")
        range_count = len(srv_data.get("ranges", {}))
        if range_count == 0:
            continue
        btns.append([InlineKeyboardButton(
            f"{icon} {srv_name}",
            callback_data=f"user_svc_{srv_name}",
            style="primary")])
    if not btns:
        await update.message.reply_text("⚠️ <b>কোনো Service এ Range নেই!</b>", parse_mode="HTML", reply_markup=main_keyboard(uid))
        return
    btns.append([InlineKeyboardButton("❌ CLOSE", callback_data="back_to_main_menu", style="danger")])

    await update.message.reply_text(
        "📞 <b>SELECT SERVICE</b>\n━━━━━━━━━━━━━━━\n\n"
        "<blockquote>👇 নিচ থেকে আপনার পছন্দের Service সিলেক্ট করুন</blockquote>",
        parse_mode="HTML", reply_markup=InlineKeyboardMarkup(btns))

# ============================================================
# ALLOCATE NUMBER
# ============================================================
async def allocate_number_from_button(update, context, service, country, rid_list, rate, priority_list=None):
    q = update.callback_query
    uid = q.from_user.id
    status = await context.bot.send_message(
        chat_id=uid,
        text=f"⚡ <b>ALLOCATING NUMBER...</b>\n\n<blockquote>📦 {service}\n🌍 {country}</blockquote>",
        parse_mode="HTML")
    try:
        result = None
        used_range = None
        for rid in rid_list:
            rng_prio = priority_list
            if rng_prio is None:
                srv_ranges = get_ranges(service)
                rng_info = srv_ranges.get(rid, {})
                rng_prio = rng_info.get("panel_priority", [])
            r = await pm_fetch_any(rid, service, rng_prio)
            if r and r.get("number"):
                result = r
                used_range = rid
                break
        if not result:
            await status.edit_text(
                f"❌ <b>Number পাওয়া যায়নি!</b>\n\n"
                f"<blockquote>📦 {service}\n🌍 {country}\n\n"
                f"এইমুহূর্তে number নেই বা সব panel busy।</blockquote>",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔄 TRY AGAIN", callback_data=f"user_cnt_{service}|||{country}", style="primary"),
                    InlineKeyboardButton("⬅️ MENU", callback_data="back_to_main_menu", style="danger")]]))
            return

        clean = result["number"]
        panel_name = result.get("panel_name", "Unknown")
        panel_id = result.get("panel_id", "unknown")
        number_id = result.get("number_id", "")

        record_range_panel_use(service, used_range, panel_name)
        log_panel_usage(uid, service, used_range, panel_name, panel_id, clean)

        add_number_taken(uid, 1)
        last_range[uid] = used_range
        active_numbers[clean] = {
            "uid": uid, "range": used_range, "service": service,
            "country": country, "rate": rate,
            "panel_name": panel_name, "panel_id": panel_id,
            "number_id": number_id,
            "timestamp": datetime.now()
        }

        flag, cname = get_country_info(clean)
        txt = (
            f"✅ <b>YOUR NUMBER</b> ✅\n\n"
            f"<blockquote>📦 SERVICE: <code>{service}</code></blockquote>\n"
            f"<blockquote>🌍 COUNTRY: <code>{flag} {html.escape(cname)}</code></blockquote>\n"
            f"<blockquote>📞 NUMBER: <code>+{clean}</code></blockquote>\n"
            f"<blockquote>💰 RATE: <b>{rate} BDT</b></blockquote>\n\n"
            f"<b>📩 STATUS: ⏳ WAITING FOR SMS...</b>"
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 CHANGE NUMBER", callback_data=f"change_num_{service}|||{country}|||{used_range}|||{rate}", style="primary")],
            [InlineKeyboardButton("❌ CANCEL NUMBER", callback_data=f"cancel_num_{clean}", style="danger")],
            [InlineKeyboardButton("🌍 OTHER SERVICES", callback_data="back_services", style="success")],
            [InlineKeyboardButton("📢 OTP GROUP", url=OTP_CHANNEL_URL, style="primary")],
            [InlineKeyboardButton("⬅️ MENU", callback_data="back_to_main_menu", style="danger")]
        ])
        await status.edit_text(txt, parse_mode="HTML", reply_markup=kb)
    except Exception as e:
        print(f"Allocate error: {e}")
        await status.edit_text(f"❌ Error: {str(e)[:100]}")

# ============================================================
# WORKER
# ============================================================
async def worker():
    while True:
        task = await request_queue.get()
        try:
            if task['type'] == 'auto':
                rng = task['range']
                uid = task['update'].effective_user.id
                last_range[uid] = rng
        except Exception as e:
            print(f"Worker error: {e}")
        finally:
            request_queue.task_done()

# ============================================================
# MONITOR LOOP
# ============================================================
async def monitor_loop(app):
    while True:
        try:
            active = pm_active()
            if not active:
                await asyncio.sleep(5)
                continue
            tasks = [pm_fetch_sms(p) for p in active]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            all_otps = []
            for i, res in enumerate(results):
                if isinstance(res, list):
                    p = active[i]
                    for item in res:
                        item["_pid"] = p.get("id", "")
                        item["_pname"] = p.get("name", "Unknown")
                        all_otps.append(item)
            if all_otps:
                paid = load_data(PAID_SMS_FILE)
                paid_set = set(paid.keys())
                proc = set()
                for otp in all_otps:
                    num = normalize_number(otp.get("number", ""))
                    sms = otp.get("message") or otp.get("otp") or ""
                    oid = str(otp.get("nid", ""))
                    pid = otp.get("_pid", "")
                    pname = otp.get("_pname", "Unknown")
                    ext_otp, ext_link = extract_link_and_otp(sms)
                    if not ext_otp:
                        ext_otp = otp.get("otp")
                    code = ext_otp or "N/A"
                    key = oid if oid else f"{num}_{sms}"

                    matched = None
                    scf_num_id = otp.get("_number_id", "")
                    if scf_num_id:
                        for an, ad in active_numbers.items():
                            if ad.get("number_id") == scf_num_id:
                                matched = an
                                break
                    if not matched:
                        for an in active_numbers.keys():
                            if numbers_match(num, an):
                                matched = an
                                break
                    if not matched:
                        continue
                    if matched and key not in paid_set and key not in proc:
                        d = active_numbers[matched]
                        paid_set.add(key)
                        proc.add(key)
                        paid[key] = {"uid": d["uid"], "otp": code}

                        reward_rate = d.get("rate", OTP_RATE)
                        um_add_balance(d["uid"], reward_rate)
                        try:
                            _chat = await app.bot.get_chat(d["uid"])
                            _uname = _chat.full_name or _chat.first_name or "User"
                        except:
                            _uname = "User"
                        um_increment_otp(d["uid"], _uname)
                        add_otp_received(d["uid"])
                        if pid:
                            pm_update_stats(pid, "otps_received")

                        rinfo = d.get("range", "") or matched
                        flag, cname = get_country_info(matched)
                        svc = d.get("service") or detect_service(sms)
                        full = f"+{matched.replace('+','')}"
                        masked = f"+{mask_number(matched.replace('+',''))}"
                        safe_sms = html.escape(str(sms))
                        safe_otp = html.escape(str(code))
                        lsec = ""
                        if ext_link:
                            lsec = f"<blockquote>🔗 <a href='{ext_link}'>{ext_link}</a></blockquote>\n"

                        umsg = (
                            f"✅ <b>OTP RECEIVED!</b> ✅\n\n"
                            f"<blockquote>📦 SERVICE: <code>{svc}</code></blockquote>\n"
                            f"<blockquote>🌍 COUNTRY: <code>{flag} {cname}</code></blockquote>\n"
                            f"<blockquote>📞 NUMBER: <code>{full}</code></blockquote>\n"
                            f"<blockquote>🔑 OTP: <code>{safe_otp}</code></blockquote>\n"
                            f"{lsec}\n"
                            f"<blockquote>📩 SMS:\n<code>{safe_sms}</code></blockquote>\n\n"
                            f"<b>💵 +{reward_rate:.2f} BDT ADDED</b>"
                        )
                        ukb = InlineKeyboardMarkup([
                            [InlineKeyboardButton(f"📋 COPY OTP ({code})", callback_data=f"copy_otp_{code}", style="success")],
                            [InlineKeyboardButton("🔄 SAME SERVICE", callback_data=f"user_svc_{svc}", style="primary")],
                            [InlineKeyboardButton("🌍 NEW NUMBER", callback_data="back_to_main_menu", style="success")],
                            [InlineKeyboardButton("📢 OTP GROUP", url=OTP_CHANNEL_URL, style="primary")]
                        ])
                        gmsg = (
                            f"✅ <b>OTP SUCCESS</b>\n\n"
                            f"<blockquote>📦 SERVICE: <code>{svc}</code></blockquote>\n"
                            f"<blockquote>📶 RANGE: <code>{rinfo}</code></blockquote>\n"
                            f"<blockquote>🌍 COUNTRY: <code>{flag} {cname}</code></blockquote>\n"
                            f"<blockquote>📞 NUMBER: <code>{masked}</code></blockquote>\n"
                            f"<blockquote>🔑 OTP: <code>{safe_otp}</code></blockquote>\n"
                            f"{lsec}\n"
                            f"<blockquote>📩 SMS:\n<code>{safe_sms}</code></blockquote>"
                        )
                        gkb = InlineKeyboardMarkup([[
                            InlineKeyboardButton("‼️ PANEL", url="https://t.me/royal_number_1bot", style="primary"),
                            InlineKeyboardButton("📢 CHANNEL", url="https://t.me/RoyalNumberXUpdates", style="primary")
                        ]])
                        try:
                            await app.bot.send_message(d["uid"], umsg, parse_mode="HTML", reply_markup=ukb)
                        except Exception as e:
                            print(f"User send fail: {e}")
                        try:
                            await app.bot.send_message(get_otp_group_id(), gmsg, parse_mode="HTML", reply_markup=gkb)
                        except Exception as e:
                            print(f"OTP grp fail: {e}")
                        try:
                            await app.bot.send_message(get_breakup_group_id(), gmsg, parse_mode="HTML", reply_markup=gkb)
                        except Exception as e:
                            print(f"Brk grp fail: {e}")
                        save_data(paid, PAID_SMS_FILE)

                now_dt = datetime.now()
                for nk in list(active_numbers.keys()):
                    e = active_numbers[nk]
                    if 'timestamp' not in e:
                        e['timestamp'] = now_dt
                    elif (now_dt - e['timestamp']).total_seconds() > 3600:
                        del active_numbers[nk]
        except Exception as e:
            print(f"Monitor error: {e}")
        await asyncio.sleep(CHECK_INTERVAL)

# ============================================================
# MESSAGE HANDLER
# ============================================================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    uid = update.effective_user.id
    if not is_admin(uid):
        if not await fj_gate(update, context):
            return
    raw = update.message.text.strip() if update.message.text else ""
    text = normalize_stylized_text(raw).strip()

    admin_state = context.user_data.get("admin_state")
    if admin_state and is_admin(uid):

        if admin_state == "add_panel_name":
            context.user_data["new_panel"] = {"name": text}
            context.user_data["admin_state"] = "add_panel_url"
            await update.message.reply_text("2️⃣ Send <b>Base URL</b>:", parse_mode="HTML", reply_markup=cancel_keyboard())
            return
        elif admin_state == "add_panel_url":
            context.user_data["new_panel"]["base_url"] = text
            context.user_data["admin_state"] = "add_panel_key"
            await update.message.reply_text("3️⃣ Send <b>API Key</b>:", reply_markup=cancel_keyboard())
            return
        elif admin_state == "add_panel_key":
            context.user_data["new_panel"]["api_key"] = text
            context.user_data["admin_state"] = "add_panel_header"
            await update.message.reply_text("4️⃣ Send <b>Header Name</b>:", reply_markup=cancel_keyboard())
            return
        elif admin_state == "add_panel_header":
            context.user_data["new_panel"]["header_name"] = text
            context.user_data["admin_state"] = "add_panel_getpath"
            await update.message.reply_text("5️⃣ Send <b>Get Number Path</b>:", parse_mode="HTML", reply_markup=cancel_keyboard())
            return
        elif admin_state == "add_panel_getpath":
            context.user_data["new_panel"]["get_path"] = text
            context.user_data["admin_state"] = "add_panel_smspath"
            await update.message.reply_text("6️⃣ Send <b>SMS Check Path</b>:", parse_mode="HTML", reply_markup=cancel_keyboard())
            return
        elif admin_state == "add_panel_smspath":
            context.user_data["new_panel"]["sms_path"] = text
            np = context.user_data["new_panel"]
            pid = pm_add(np["name"], np["base_url"], np["api_key"], np["header_name"],
                         np.get("get_path", "/getnum"), "POST",
                         np.get("sms_path", "/success-otp"), "GET")
            context.user_data["admin_state"] = None
            context.user_data["new_panel"] = None
            await update.message.reply_text(
                f"✅ <b>Panel Added!</b>\n\n🆔 <code>{pid}</code>\n📛 {np['name']}",
                parse_mode="HTML", reply_markup=main_keyboard(uid))
            return
        elif admin_state == "edit_panel_value":
            pid = context.user_data.get("edit_pid")
            field = context.user_data.get("edit_field")
            pm_update_field(pid, field, text)
            context.user_data["admin_state"] = None
            await update.message.reply_text(f"✅ Updated <code>{field}</code>", parse_mode="HTML", reply_markup=main_keyboard(uid))
            return

        elif admin_state == "svc_add_name":
            name = text.strip().upper()
            if add_service(name, "🚀"):
                context.user_data["admin_state"] = None
                await update.message.reply_text(
                    f"✅ Service <code>{name}</code> added!",
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("📋 VIEW", callback_data=f"svc_view_{name}", style="primary"),
                        InlineKeyboardButton("🔙 LIST", callback_data="svc_list", style="danger")]]))
            else:
                await update.message.reply_text("⚠️ Service exists!")
                context.user_data["admin_state"] = None
            return

        elif admin_state == "svc_rename_new":
            old = context.user_data.get("svc_old_name")
            new = text.strip().upper()
            if rename_service(old, new):
                context.user_data["admin_state"] = None
                await update.message.reply_text(
                    f"✅ Renamed to <code>{new}</code>",
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("📋 VIEW", callback_data=f"svc_view_{new}", style="primary"),
                        InlineKeyboardButton("🔙 LIST", callback_data="svc_list", style="danger")]]))
            else:
                await update.message.reply_text("❌ Rename failed")
                context.user_data["admin_state"] = None
            return

        elif admin_state == "rng_add_id":
            srv = context.user_data["rng_srv"]
            context.user_data["rng_new_id"] = text.strip().upper()
            context.user_data["admin_state"] = "rng_add_country"
            await update.message.reply_text("2️⃣ Send country (e.g. <code>🇧🇩 Bangladesh</code>):", parse_mode="HTML", reply_markup=cancel_keyboard())
            return

        elif admin_state == "rng_add_country":
            context.user_data["rng_new_country"] = text
            context.user_data["admin_state"] = "rng_add_rate"
            await update.message.reply_text("3️⃣ Send OTP rate (e.g. <code>0.3</code>):", parse_mode="HTML", reply_markup=cancel_keyboard())
            return

        elif admin_state == "rng_add_rate":
            try:
                rate = float(text.strip())
            except:
                await update.message.reply_text("❌ Invalid rate")
                return
            context.user_data["rng_new_rate"] = rate
            context.user_data["admin_state"] = "rng_add_priority"
            panels = pm_load()
            panel_list = "\n".join([f"• <code>{pid}</code> → {p['name']}" for pid, p in panels.items()])
            await update.message.reply_text(
                f"4️⃣ <b>PANEL PRIORITY</b>\n\n"
                f"কোন প্যানেল আগে try করবে সেটা কমা দিয়ে লিখুন।\n\n"
                f"<b>Available panels:</b>\n{panel_list}\n\n"
                f"<b>Examples:</b>\n"
                f"• <code>scarface_1, minosms_1, stex_1</code>\n"
                f"• <code>zenex_1, jssms_1</code>\n"
                f"• খালি পাঠান → সব প্যানেল auto use করবে",
                parse_mode="HTML", reply_markup=cancel_keyboard())
            return

        elif admin_state == "rng_add_priority":
            srv = context.user_data["rng_srv"]
            rid = context.user_data["rng_new_id"]
            country = context.user_data["rng_new_country"]
            rate = context.user_data["rng_new_rate"]
            priority = []
            if text.strip():
                priority = [p.strip().lower() for p in text.split(",") if p.strip()]
            if add_range(srv, rid, country, rate, priority):
                context.user_data["admin_state"] = None
                prio_display = " → ".join(priority) if priority else "AUTO (all panels)"
                await update.message.reply_text(
                    f"✅ Range <code>{rid}</code> added to <b>{srv}</b>\n"
                    f"⚙️ Priority: <code>{prio_display}</code>",
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("📋 VIEW", callback_data=f"svc_view_{srv}", style="primary")]]))
            else:
                await update.message.reply_text("⚠️ Range already exists")
                context.user_data["admin_state"] = None
            return

        elif admin_state == "rng_set_rate":
            try:
                rate = float(text.strip())
            except:
                await update.message.reply_text("❌ Invalid rate")
                return
            srv = context.user_data["rng_srv"]
            rid = context.user_data["rng_id"]
            update_range_rate(srv, rid, rate)
            context.user_data["admin_state"] = None
            await update.message.reply_text(
                f"✅ Rate updated for <code>{rid}</code>: <b>{rate} BDT</b>",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("📋 VIEW", callback_data=f"rng_view_{srv}_{rid}", style="primary")]]))
            return

        elif admin_state == "rng_set_country":
            srv = context.user_data["rng_srv"]
            rid = context.user_data["rng_id"]
            update_range_country(srv, rid, text.strip())
            context.user_data["admin_state"] = None
            await update.message.reply_text(
                f"✅ Country updated for <code>{rid}</code>",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("📋 VIEW", callback_data=f"rng_view_{srv}_{rid}", style="primary")]]))
            return

        elif admin_state == "rng_set_priority":
            srv = context.user_data["rng_srv"]
            rid = context.user_data["rng_id"]
            priority = []
            if text.strip():
                priority = [p.strip().lower() for p in text.split(",") if p.strip()]
            update_range_priority(srv, rid, priority)
            context.user_data["admin_state"] = None
            prio_display = " → ".join(priority) if priority else "AUTO (all panels)"
            await update.message.reply_text(
                f"✅ Priority updated for <code>{rid}</code>\n⚙️ <code>{prio_display}</code>",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("📋 VIEW", callback_data=f"rng_view_{srv}_{rid}", style="primary")]]))
            return

        elif admin_state == "svc_bulk_srv":
            context.user_data["svc_bulk_name"] = text.strip().upper()
            context.user_data["admin_state"] = "svc_bulk_content"
            await update.message.reply_text(
                "2️⃣ Send range lines (one per line):\n"
                "<code>880X01|🇧🇩 Bangladesh|0.3|scarface_1,minosms_1\n"
                "91X05|🇮🇳 India|0.3|zenex_1\n"
                "44X05|🇬🇧 UK|0.5|jssms_1</code>",
                parse_mode="HTML", reply_markup=cancel_keyboard())
            return

        elif admin_state == "svc_bulk_content":
            srv = context.user_data["svc_bulk_name"]
            lines = text.split("\n")
            added = bulk_add_ranges(srv, lines)
            context.user_data["admin_state"] = None
            await update.message.reply_text(
                f"✅ Added <b>{added}</b> ranges to <code>{srv}</code>",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("📋 VIEW", callback_data=f"svc_view_{srv}", style="primary")]]))
            return

        elif admin_state == "usr_search":
            results = um_search_users(text.strip())
            context.user_data["admin_state"] = None
            if not results:
                await update.message.reply_text("❌ No users found",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("🔙 BACK", callback_data="usr_mgmt", style="danger")]]))
                return
            btns = []
            for uid_, udata in results[:10]:
                bal = udata.get("balance", 0)
                uname = udata.get("name", "User")[:20]
                btns.append([InlineKeyboardButton(
                    f"🆔 {uname} — {bal:.2f}৳",
                    callback_data=f"usr_view_{uid_}",
                    style="primary")])
            btns.append([InlineKeyboardButton("🔙 BACK", callback_data="usr_mgmt", style="danger")])
            await update.message.reply_text(
                f"🔍 <b>Found {len(results)} users</b>",
                parse_mode="HTML", reply_markup=InlineKeyboardMarkup(btns))
            return

        elif admin_state == "usr_addbal_amt":
            try:
                amt = float(text.strip())
            except:
                await update.message.reply_text("❌ Invalid amount")
                return
            tu = context.user_data["usr_target"]
            new_bal = um_add_balance(tu, amt)
            context.user_data["admin_state"] = None
            await update.message.reply_text(
                f"✅ Added <b>{amt} BDT</b> to <code>{tu}</code>\n"
                f"💰 New: <b>{new_bal} BDT</b>",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("👤 VIEW", callback_data=f"usr_view_{tu}", style="primary")]]))
            return

        elif admin_state == "usr_rembal_amt":
            try:
                amt = float(text.strip())
            except:
                await update.message.reply_text("❌ Invalid amount")
                return
            tu = context.user_data["usr_target"]
            new_bal = um_add_balance(tu, -amt)
            context.user_data["admin_state"] = None
            await update.message.reply_text(
                f"✅ Removed <b>{amt} BDT</b> from <code>{tu}</code>\n"
                f"💰 New: <b>{new_bal} BDT</b>",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("👤 VIEW", callback_data=f"usr_view_{tu}", style="primary")]]))
            return

        elif admin_state == "fj_add_channel":
            try:
                parts = text.split("|")
                if len(parts) < 2:
                    await update.message.reply_text("❌ Format: <code>@username | Display Name</code>", parse_mode="HTML")
                    return
                rid = parts[0].strip()
                dn = parts[1].strip()
                if rid.startswith("@"):
                    cid = rid
                elif rid.startswith("-"):
                    try:
                        cid = int(rid)
                    except:
                        await update.message.reply_text("❌ Invalid ID")
                        return
                else:
                    try:
                        cid = int(rid)
                    except:
                        await update.message.reply_text("❌ Invalid ID")
                        return
                try:
                    chat = await context.bot.get_chat(cid)
                    atype = "channel" if chat.type == "channel" else "group"
                except Exception as e:
                    await update.message.reply_text(f"❌ Bot access নেই: {str(e)[:100]}")
                    return
                chs = load_fj()
                if any(str(c.get("id")) == str(cid) for c in chs):
                    await update.message.reply_text("⚠️ আগে থেকেই আছে!")
                    return
                chs.append({"id": cid, "name": dn, "type": atype})
                save_fj(chs)
                context.user_data["admin_state"] = None
                await update.message.reply_text(f"✅ Added: {dn}", reply_markup=main_keyboard(uid))
            except Exception as e:
                await update.message.reply_text(f"❌ {str(e)[:100]}")
            return

        elif admin_state == "broadcast":
            context.user_data["admin_state"] = None
            users = um_get_all_users()
            if not users:
                await update.message.reply_text("❌ No users!")
                return
            status = await update.message.reply_text(f"🚀 Broadcasting to {len(users)}...")
            ok, fail = 0, 0
            for u in users:
                try:
                    await context.bot.send_message(int(u), f"📢 <b>ADMIN NOTICE:</b>\n\n{update.message.text}", parse_mode="HTML")
                    ok += 1
                except:
                    fail += 1
                await asyncio.sleep(0.05)
            await status.edit_text(f"✅ Done!\n✅ Success: {ok}\n❌ Failed: {fail}")
            return

        elif admin_state == "ban_user":
            context.user_data["admin_state"] = None
            if not text.isdigit():
                await update.message.reply_text("❌ Invalid ID")
                return
            um_ban(int(text))
            await update.message.reply_text(f"✅ Banned: {text}")
            return
        elif admin_state == "unban_user":
            context.user_data["admin_state"] = None
            if not text.isdigit():
                await update.message.reply_text("❌ Invalid ID")
                return
            um_unban(int(text))
            await update.message.reply_text(f"✅ Unbanned: {text}")
            return

    if um_is_banned(uid):
        await update.message.reply_text("🚫 BANNED", reply_markup=main_keyboard(uid))
        return

    if context.user_data.get("w_mode") == "select":
        if text == "❌ CANCEL":
            context.user_data["w_mode"] = None
            await update.message.reply_text("❌ Cancelled", reply_markup=main_keyboard(uid))
            return
        mmap = {"📱 BKASH": "BKASH", "💵 NAGAD": "NAGAD", "🚀 ROCKET": "ROCKET", "🏦 BINANCE": "BINANCE"}
        if text in mmap:
            b = um_get_balance(uid)
            context.user_data["w_method"] = mmap[text]
            context.user_data["w_mode"] = "amount"
            await update.message.reply_text(
                f"<blockquote>💸 Send amount\n💵 Balance: {format_balance(b)} BDT\n📉 Min: {MIN_WITHDRAW}</blockquote>",
                parse_mode="HTML", reply_markup=cancel_keyboard())
        else:
            await update.message.reply_text("⚠️ Select a valid method!", reply_markup=withdraw_method_keyboard())
        return
    if context.user_data.get("w_mode") == "amount":
        if text == "❌ CANCEL":
            context.user_data["w_mode"] = None
            await update.message.reply_text("❌ Cancelled", reply_markup=main_keyboard(uid))
            return
        try:
            amt = float(text)
        except:
            await update.message.reply_text("⚠️ Invalid amount", reply_markup=cancel_keyboard())
            return
        b = um_get_balance(uid)
        if amt < MIN_WITHDRAW or amt > MAX_WITHDRAW:
            await update.message.reply_text(f"📉 Min {MIN_WITHDRAW} / Max {MAX_WITHDRAW}", reply_markup=cancel_keyboard())
            return
        if amt > b:
            await update.message.reply_text("🚫 Insufficient balance", reply_markup=cancel_keyboard())
            return
        context.user_data["w_amount"] = amt
        context.user_data["w_mode"] = "number"
        await update.message.reply_text("📞 Send your payment number (017XXXXXXXX):", reply_markup=cancel_keyboard())
        return
    if context.user_data.get("w_mode") == "number":
        if text == "❌ CANCEL":
            context.user_data["w_mode"] = None
            await update.message.reply_text("❌ Cancelled", reply_markup=main_keyboard(uid))
            return
        if not is_valid_bd_number(text):
            await update.message.reply_text("⚠️ Invalid number!", reply_markup=cancel_keyboard())
            return
        method = context.user_data.get("w_method")
        amt = context.user_data.get("w_amount")
        pid = gen_payment_id()
        context.user_data["w_temp"] = {"method": method, "amount": amt, "number": text, "pid": pid}
        await update.message.reply_text(
            f"✨ <b>Confirm Withdraw</b>\n\n<blockquote>📝 {method}\n📞 {text}\n💰 {format_balance(amt)} BDT</blockquote>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ CANCEL", callback_data="w_cancel", style="danger"),
                InlineKeyboardButton("✅ CONFIRM", callback_data="w_confirm", style="success")]]))
        return

    if "WITHDRAW" in text:
        b = um_get_balance(uid)
        if b < MIN_WITHDRAW:
            await update.message.reply_text(f"<blockquote>💵 {format_balance(b)} BDT\n📉 Min: {MIN_WITHDRAW}</blockquote>", parse_mode="HTML", reply_markup=main_keyboard(uid))
            return
        context.user_data["w_mode"] = "select"
        await update.message.reply_text(
            f"💸 <b>WITHDRAW</b>\n\n<blockquote>💰 Balance: {format_balance(b)} BDT\n📉 Min: {MIN_WITHDRAW}</blockquote>\n\n👇 Select method:",
            parse_mode="HTML", reply_markup=withdraw_method_keyboard())
        return
    if "PROFILE" in text:
        await profile_command(update, context)
        return
    if "REFER AND EARN" in text:
        await refer_command(update, context)
        return
    if "GET NUMBER" in text:
        await show_services(update, context)
        return
    if "LEADERBOARD" in text:
        await leaderboard_command(update, context)
        return
    if "SUPPORT" in text:
        await update.message.reply_text(
            "💬 SUPPORT",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("💬 SUPPORT", url=SUPPORT_LINK, style="primary"),
                InlineKeyboardButton("👨‍💻 DEV", url="https://t.me/samirchowdury2", style="danger")]]))
        return
    if "ADMIN PANEL" in text and is_admin(uid):
        await update.message.reply_text(
            "👑 <b>ADMIN PANEL</b> 👑\n━━━━━━━━━━━━━━━",
            parse_mode="HTML", reply_markup=admin_main_kb())
        return

    await update.message.reply_text("🔹 Use buttons below:", reply_markup=main_keyboard(uid))

# ============================================================
# CALLBACK HANDLER
# ============================================================
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    uid = q.from_user.id
    data = q.data
    await q.answer()

    if data == "fj_check":
        unj = await get_unjoined(context.bot, uid)
        if not unj:
            try:
                await q.message.edit_text("✅ Thanks! Use /start")
            except:
                pass
            await context.bot.send_message(uid, "🔹 Menu:", reply_markup=main_keyboard(uid))
        else:
            await q.answer("⚠️ Join all channels!", show_alert=True)
        return

    if data.startswith("copy_otp_"):
        otp = data.replace("copy_otp_", "")
        await q.answer(f"📋 Copied: {otp}", show_alert=True)
        try:
            await context.bot.send_message(uid, f"<code>{otp}</code>", parse_mode="HTML")
        except:
            pass
        return

    if data == "back_to_main_menu":
        try:
            await q.message.delete()
        except:
            pass
        await context.bot.send_message(uid, "🔹 Menu:", reply_markup=main_keyboard(uid))
        return

    if data.startswith("user_svc_"):
        srv = data.replace("user_svc_", "")
        ranges = get_ranges(srv)
        if not ranges:
            await q.answer("No ranges", show_alert=True)
            return

        try:
            hide_msg = await context.bot.send_message(
                chat_id=uid,
                text=".",
                reply_markup=ReplyKeyboardRemove()
            )
            await asyncio.sleep(0.5)
            await hide_msg.delete()
        except Exception as e:
            print(f"Hide keyboard error: {e}")

        countries = {}
        for rid, rdata in ranges.items():
            c = (rdata.get("country") or "🌍 Unknown").strip()
            if c not in countries:
                countries[c] = []
            countries[c].append(rid)
        country_list = sorted(countries.keys())
        btns = []
        for i in range(0, len(country_list), 2):
            row = []
            for c in country_list[i:i+2]:
                count = len(countries[c])
                flagged = add_flag_to_country(c)
                label = f"{flagged}" if count == 1 else f"{flagged} ({count})"
                row.append(InlineKeyboardButton(
                    label,
                    callback_data=f"user_cnt_{srv}|||{c}",
                    style="primary"))
            btns.append(row)
        btns.append([InlineKeyboardButton("🔙 BACK", callback_data="back_services", style="danger")])
        await q.message.edit_text(
            f"🌍 <b>SELECT COUNTRY</b>\n\n"
            f"<blockquote>📦 Service: <b>{srv}</b>\n"
            f"📊 Total Countries: <b>{len(countries)}</b></blockquote>",
            parse_mode="HTML", reply_markup=InlineKeyboardMarkup(btns))
        return

    if data.startswith("user_cnt_"):
        rest = data.replace("user_cnt_", "")
        parts = rest.split("|||", 1)
        srv = parts[0]
        country = parts[1] if len(parts) > 1 else ""
        ranges = get_ranges(srv)
        rid_list = [rid for rid, rd in ranges.items() if (rd.get("country") or "🌍 Unknown").strip() == country]
        if not rid_list:
            await q.answer("No ranges", show_alert=True)
            return
        rate = ranges[rid_list[0]].get("rate", 0.3)
        await allocate_number_from_button(update, context, srv, country, rid_list, rate)
        return

    if data.startswith("change_num_"):
        rest = data.replace("change_num_", "")
        parts = rest.split("|||")
        if len(parts) < 4:
            await q.answer("Invalid request", show_alert=True)
            return
        srv = parts[0]
        country = parts[1]
        old_used_range = parts[2]
        try:
            rate = float(parts[3])
        except:
            rate = 0.3
        for an, ad in list(active_numbers.items()):
            if ad.get("uid") == uid and ad.get("service") == srv and ad.get("range") == old_used_range:
                del active_numbers[an]
                break
        status = await context.bot.send_message(
            chat_id=uid,
            text=f"🔄 <b>CHANGING NUMBER...</b>\n\n<blockquote>📦 {srv}\n🌍 {country}\n📶 Range: {old_used_range}</blockquote>",
            parse_mode="HTML")
        try:
            srv_ranges = get_ranges(srv)
            rng_prio = srv_ranges.get(old_used_range, {}).get("panel_priority", [])
            r = await pm_fetch_any(old_used_range, srv, rng_prio)
            if not r or not r.get("number"):
                await status.edit_text(
                    f"❌ <b>নতুন number পাওয়া যায়নি!</b>\n\n"
                    f"<blockquote>আগের range এখন busy।</blockquote>",
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("🔄 TRY AGAIN", callback_data=f"change_num_{srv}|||{country}|||{old_used_range}|||{rate}", style="primary"),
                        InlineKeyboardButton("⬅️ MENU", callback_data="back_to_main_menu", style="danger")]]))
                return
            clean = r["number"]
            panel_name = r.get("panel_name", "Unknown")
            panel_id = r.get("panel_id", "unknown")
            number_id = r.get("number_id", "")
            record_range_panel_use(srv, old_used_range, panel_name)
            log_panel_usage(uid, srv, old_used_range, panel_name, panel_id, clean)
            add_number_taken(uid, 1)
            active_numbers[clean] = {
                "uid": uid, "range": old_used_range, "service": srv,
                "country": country, "rate": rate,
                "panel_name": panel_name, "panel_id": panel_id,
                "number_id": number_id,
                "timestamp": datetime.now()
            }
            flag, cname = get_country_info(clean)
            txt = (
                f"✅ <b>YOUR NEW NUMBER</b> ✅\n\n"
                f"<blockquote>📦 SERVICE: <code>{srv}</code></blockquote>\n"
                f"<blockquote>🌍 COUNTRY: <code>{flag} {html.escape(cname)}</code></blockquote>\n"
                f"<blockquote>📞 NUMBER: <code>+{clean}</code></blockquote>\n"
                f"<blockquote>💰 RATE: <b>{rate} BDT</b></blockquote>\n\n"
                f"<b>📩 STATUS: ⏳ WAITING FOR SMS...</b>"
            )
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 CHANGE NUMBER", callback_data=f"change_num_{srv}|||{country}|||{old_used_range}|||{rate}", style="primary")],
                [InlineKeyboardButton("❌ CANCEL NUMBER", callback_data=f"cancel_num_{clean}", style="danger")],
                [InlineKeyboardButton("🌍 OTHER SERVICES", callback_data="back_services", style="success")],
                [InlineKeyboardButton("⬅️ MENU", callback_data="back_to_main_menu", style="danger")]
            ])
            await status.edit_text(txt, parse_mode="HTML", reply_markup=kb)
        except Exception as e:
            print(f"Change number error: {e}")
            await status.edit_text(f"❌ Error: {str(e)[:100]}")
        return

    if data.startswith("cancel_num_"):
        num = data.replace("cancel_num_", "")
        if num in active_numbers and active_numbers[num].get("uid") == uid:
            del active_numbers[num]
            await q.message.edit_text(
                f"❌ <b>Number Cancelled</b>\n\n"
                f"<blockquote>📞 <code>+{num}</code>\n\n"
                f"এই number-এ আর SMS চেক হবে না।</blockquote>",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🌍 OTHER SERVICES", callback_data="back_services", style="success"),
                    InlineKeyboardButton("⬅️ MENU", callback_data="back_to_main_menu", style="danger")]]))
        else:
            await q.answer("Number already cancelled", show_alert=True)
        return

    if data == "back_services":
        services = get_all_services()
        btns = []
        for srv_name, srv_data in services.items():
            icon = srv_data.get("icon", "🚀")
            if not srv_data.get("ranges", {}):
                continue
            btns.append([InlineKeyboardButton(
                f"{icon} {srv_name}",
                callback_data=f"user_svc_{srv_name}",
                style="primary")])
        btns.append([InlineKeyboardButton("❌ CLOSE", callback_data="back_to_main_menu", style="danger")])
        try:
            await q.message.edit_text(
                "📞 <b>SELECT SERVICE</b>",
                parse_mode="HTML", reply_markup=InlineKeyboardMarkup(btns))
        except:
            pass
        return

    if data == "withdraw_start":
        b = um_get_balance(uid)
        if b < MIN_WITHDRAW:
            await q.answer(f"Min {MIN_WITHDRAW}", show_alert=True)
            return
        context.user_data["w_mode"] = "select"
        await context.bot.send_message(uid, "💳 Select method:", reply_markup=withdraw_method_keyboard())
        return

    if data == "w_confirm":
        temp = context.user_data.get("w_temp")
        if not temp:
            await q.answer("Session expired", show_alert=True)
            return
        um_add_balance(uid, -temp["amount"])
        wr = load_withdrawals()
        wr[temp["pid"]] = {"user_id": uid, "method": temp["method"], "amount": temp["amount"],
                           "number": temp["number"], "payment_id": temp["pid"], "status": "pending",
                           "timestamp": datetime.now().isoformat()}
        save_withdrawals(wr)
        await q.message.edit_text(
            f"✅ <b>WITHDRAW SUBMITTED</b>\n\n<blockquote>📝 {temp['method']}\n📞 {temp['number']}\n💰 {format_balance(temp['amount'])} BDT\n🆔 {temp['pid']}</blockquote>",
            parse_mode="HTML")
        admin_msg = (
            f"✅ <b>NEW WITHDRAWAL</b>\n\n"
            f"<blockquote>🆔 User: <code>{uid}</code>\n"
            f"📝 {temp['method']}\n📞 {temp['number']}\n"
            f"💰 {format_balance(temp['amount'])} BDT\n"
            f"🆔 {temp['pid']}</blockquote>")
        akb = InlineKeyboardMarkup([[
            InlineKeyboardButton("❌ REJECT", callback_data=f"wrej_{temp['pid']}", style="danger"),
            InlineKeyboardButton("✅ APPROVE", callback_data=f"wapp_{temp['pid']}", style="success")]])
        try:
            await context.bot.send_message(get_withdraw_group_id(), admin_msg, parse_mode="HTML", reply_markup=akb)
        except:
            pass
        for a in ADMINS:
            try:
                await context.bot.send_message(a, admin_msg, parse_mode="HTML", reply_markup=akb)
            except:
                pass
        context.user_data["w_temp"] = None
        context.user_data["w_mode"] = None
        await context.bot.send_message(uid, "🎉 Done!", reply_markup=main_keyboard(uid))
        return

    if data == "w_cancel":
        context.user_data["w_temp"] = None
        context.user_data["w_mode"] = None
        await q.message.edit_text("❌ Cancelled")
        return

    if data.startswith("wapp_") or data.startswith("wrej_"):
        if not is_admin(uid):
            await q.answer("Admin only!", show_alert=True)
            return
        act = "approve" if data.startswith("wapp_") else "reject"
        pid = data.replace("wapp_", "").replace("wrej_", "")
        wr = load_withdrawals()
        if pid not in wr:
            await q.answer("Not found", show_alert=True)
            return
        rd = wr[pid]
        wr[pid]["status"] = "approved" if act == "approve" else "rejected"
        save_withdrawals(wr)
        if act == "approve":
            try:
                await context.bot.send_message(rd["user_id"], f"✅ Withdraw approved! {format_balance(rd['amount'])} BDT sent.")
            except:
                pass
        else:
            um_add_balance(rd["user_id"], rd["amount"])
            try:
                await context.bot.send_message(rd["user_id"], "❌ Withdraw rejected. Balance refunded.")
            except:
                pass
        await q.message.edit_text(f"{'✅ APPROVED' if act=='approve' else '❌ REJECTED'} | {rd['amount']} BDT")
        return

    if data == "adm_back_admin":
        await q.message.edit_text("👑 <b>ADMIN PANEL</b>", parse_mode="HTML", reply_markup=admin_main_kb())
        return
    if data == "adm_back_main":
        try:
            await q.message.delete()
        except:
            pass
        await context.bot.send_message(uid, "🔹 Menu:", reply_markup=main_keyboard(uid))
        return
    if data == "adm_sys":
        await q.message.edit_text("⚙️ <b>SYSTEM CONFIG</b>", parse_mode="HTML", reply_markup=adm_sys_kb())
        return
    if data == "adm_broadcast":
        context.user_data["admin_state"] = "broadcast"
        await q.message.edit_text("📢 Send broadcast message:", reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("❌ CANCEL", callback_data="adm_sys", style="danger")]]))
        return
    if data == "adm_ban":
        context.user_data["admin_state"] = "ban_user"
        await q.message.edit_text("⛔ Send user ID to ban:", reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("❌", callback_data="adm_sys", style="danger")]]))
        return
    if data == "adm_unban":
        context.user_data["admin_state"] = "unban_user"
        await q.message.edit_text("🔓 Send user ID to unban:", reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("❌", callback_data="adm_sys", style="danger")]]))
        return
    if data == "adm_banlist":
        bl = um_load_banned()
        txt = "📜 <b>BANNED</b>\n\n" + ("\n".join(f"{i}. <code>{b}</code>" for i, b in enumerate(bl, 1)) if bl else "None")
        await q.message.edit_text(txt, parse_mode="HTML", reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙", callback_data="adm_sys", style="danger")]]))
        return

    if data == "sys_settings":
        if not is_admin(uid):
            await q.answer("Admin only", show_alert=True)
            return
        await q.message.edit_text(
            "⚙️ <b>SYSTEM SETTINGS</b>\n━━━━━━━━━━━━━━━\n\n"
            "<i>👇 Panel, Group, ও অন্যান্য system control</i>",
            parse_mode="HTML", reply_markup=sys_settings_kb())
        return

    if data == "grp_config":
        if not is_admin(uid):
            await q.answer("Admin only", show_alert=True)
            return
        await q.message.edit_text(
            "📢 <b>GROUP CONFIGURATION</b>\n━━━━━━━━━━━━━━━\n\n"
            f"📞 OTP Group: <code>{get_otp_group_id()}</code>\n"
            f"💸 Withdraw Group: <code>{get_withdraw_group_id()}</code>\n"
            f"📊 Breakup Group: <code>{get_breakup_group_id()}</code>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 BACK", callback_data="sys_settings", style="danger")]]))
        return

    if data == "sys_test_all":
        if not is_admin(uid):
            await q.answer("Admin only", show_alert=True)
            return
        await q.answer("Testing all panels...")
        panels = pm_load()
        if not panels:
            await context.bot.send_message(uid, "❌ No panels found!")
            return
        result_lines = ["🧪 <b>TEST ALL PANELS</b>\n━━━━━━━━━━━━━━━\n"]
        for pid, p in panels.items():
            name = p.get("name", pid)
            try:
                ok, msg = await pm_test(p)
                result_lines.append(f"<b>{name}</b>\n   {msg}\n")
            except Exception as e:
                result_lines.append(f"<b>{name}</b>\n   ❌ Error: {str(e)[:50]}\n")
        await context.bot.send_message(uid, "\n".join(result_lines), parse_mode="HTML")
        return

    if data == "svc_list":
        if not is_admin(uid):
            await q.answer("Admin only", show_alert=True)
            return
        await q.message.edit_text(
            "📦 <b>SERVICE MANAGEMENT</b>\n━━━━━━━━━━━━━━━",
            parse_mode="HTML", reply_markup=aui_services_list_kb())
        return

    if data == "svc_add":
        if not is_admin(uid):
            await q.answer("Admin only", show_alert=True)
            return
        context.user_data["admin_state"] = "svc_add_name"
        await q.message.edit_text(
            "➕ <b>ADD SERVICE</b>\n\n1️⃣ Send service name (e.g. <code>WHATSAPP</code>):",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ CANCEL", callback_data="svc_list", style="danger")]]))
        return

    if data.startswith("svc_view_"):
        if not is_admin(uid):
            await q.answer("Admin only", show_alert=True)
            return
        srv = data.replace("svc_view_", "")
        txt = aui_service_text(srv)
        kb = aui_service_detail_kb(srv)
        await q.message.edit_text(txt, parse_mode="HTML", reply_markup=kb)
        return

    if data.startswith("rng_add_"):
        if not is_admin(uid):
            await q.answer("Admin only", show_alert=True)
            return
        srv = data.replace("rng_add_", "")
        context.user_data["admin_state"] = "rng_add_id"
        context.user_data["rng_srv"] = srv
        await q.message.edit_text(
            f"➕ <b>ADD RANGE to {srv}</b>\n\n1️⃣ Send range ID (e.g. <code>880X01</code>):",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ CANCEL", callback_data=f"svc_view_{srv}", style="danger")]]))
        return

    if data.startswith("svc_del_"):
        if not is_admin(uid):
            await q.answer("Admin only", show_alert=True)
            return
        srv = data.replace("svc_del_", "")
        delete_service(srv)
        await q.answer(f"Deleted {srv}", show_alert=True)
        await q.message.edit_text(
            "📦 <b>SERVICE MANAGEMENT</b>",
            parse_mode="HTML", reply_markup=aui_services_list_kb())
        return

    if data.startswith("svc_rename_"):
        if not is_admin(uid):
            await q.answer("Admin only", show_alert=True)
            return
        srv = data.replace("svc_rename_", "")
        context.user_data["admin_state"] = "svc_rename_new"
        context.user_data["svc_old_name"] = srv
        await q.message.edit_text(
            f"✏️ Send new name for <b>{srv}</b>:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ CANCEL", callback_data=f"svc_view_{srv}", style="danger")]]))
        return

    if data.startswith("rng_view_"):
        if not is_admin(uid):
            await q.answer("Admin only", show_alert=True)
            return
        parts = data.replace("rng_view_", "").split("_", 1)
        if len(parts) < 2:
            return
        srv, rid = parts[0], parts[1]
        info = get_ranges(srv).get(rid)
        if not info:
            await q.answer("Not found", show_alert=True)
            return
        priority = info.get("panel_priority", [])
        prio_display = " → ".join(priority) if priority else "AUTO (all panels)"
        panel_stats = info.get("panel_stats", {})
        stats_txt = ""
        if panel_stats:
            stats_lines = [f"  • {pn}: {cnt}" for pn, cnt in panel_stats.items()]
            stats_txt = "\n\n📊 <b>PANEL STATS:</b>\n" + "\n".join(stats_lines)
        txt = (
            f"📍 <b>RANGE: {rid}</b>\n━━━━━━━━━━━━━━━\n\n"
            f"📦 Service: <code>{srv}</code>\n"
            f"🌍 Country: {info.get('country', '?')}\n"
            f"💰 Rate: <b>{info.get('rate', 0.3)} BDT</b>\n"
            f"⚙️ Priority: <code>{prio_display}</code>"
            f"{stats_txt}")
        await q.message.edit_text(txt, parse_mode="HTML",
            reply_markup=aui_range_detail_kb(srv, rid))
        return

    if data.startswith("rng_stats_"):
        if not is_admin(uid):
            await q.answer("Admin only", show_alert=True)
            return
        parts = data.replace("rng_stats_", "").split("_", 1)
        srv, rid = parts[0], parts[1]
        info = get_ranges(srv).get(rid, {})
        panel_stats = info.get("panel_stats", {})
        if not panel_stats:
            txt = f"📊 <b>NO DATA YET</b>\n\nরেঞ্জ <code>{rid}</code> থেকে এখনো কোনো number আসেনি।"
        else:
            total = sum(panel_stats.values())
            txt = f"📊 <b>PANEL STATS</b>\n\n📦 Service: <code>{srv}</code>\n📶 Range: <code>{rid}</code>\n🔢 Total Numbers: <b>{total}</b>\n\n"
            for pn, cnt in sorted(panel_stats.items(), key=lambda x: -x[1]):
                pct = (cnt / total) * 100
                bar = "█" * int(pct / 10) + "░" * (10 - int(pct / 10))
                txt += f"⚙️ <b>{pn}</b>\n   {bar} {cnt} ({pct:.1f}%)\n\n"
        await q.message.edit_text(txt, parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 BACK", callback_data=f"rng_view_{srv}_{rid}", style="danger")]]))
        return

    if data.startswith("rng_rate_"):
        if not is_admin(uid):
            await q.answer("Admin only", show_alert=True)
            return
        parts = data.replace("rng_rate_", "").split("_", 1)
        srv, rid = parts[0], parts[1]
        context.user_data["admin_state"] = "rng_set_rate"
        context.user_data["rng_srv"] = srv
        context.user_data["rng_id"] = rid
        await q.message.edit_text(
            f"💰 Send new OTP rate for <code>{rid}</code> (e.g. <code>0.3</code>):",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ CANCEL", callback_data=f"rng_view_{srv}_{rid}", style="danger")]]))
        return

    if data.startswith("rng_country_"):
        if not is_admin(uid):
            await q.answer("Admin only", show_alert=True)
            return
        parts = data.replace("rng_country_", "").split("_", 1)
        srv, rid = parts[0], parts[1]
        context.user_data["admin_state"] = "rng_set_country"
        context.user_data["rng_srv"] = srv
        context.user_data["rng_id"] = rid
        await q.message.edit_text(
            f"🌍 Send new country for <code>{rid}</code>:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ CANCEL", callback_data=f"rng_view_{srv}_{rid}", style="danger")]]))
        return

    if data.startswith("rng_prio_"):
        if not is_admin(uid):
            await q.answer("Admin only", show_alert=True)
            return
        parts = data.replace("rng_prio_", "").split("_", 1)
        srv, rid = parts[0], parts[1]
        context.user_data["admin_state"] = "rng_set_priority"
        context.user_data["rng_srv"] = srv
        context.user_data["rng_id"] = rid
        panels = pm_load()
        panel_list = "\n".join([f"• <code>{pid}</code> → {p['name']}" for pid, p in panels.items()])
        await q.message.edit_text(
            f"⚙️ <b>SET PANEL PRIORITY for {rid}</b>\n\n"
            f"<b>Available panels:</b>\n{panel_list}\n\n"
            f"<b>Examples:</b>\n"
            f"• <code>scarface_1, minosms_1, stex_1, zenex_1, jssms_1</code>\n"
            f"• <code>zenex_1</code>\n"
            f"• খালি পাঠান = AUTO",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ CANCEL", callback_data=f"rng_view_{srv}_{rid}", style="danger")]]))
        return

    if data.startswith("rng_del_"):
        if not is_admin(uid):
            await q.answer("Admin only", show_alert=True)
            return
        parts = data.replace("rng_del_", "").split("_", 1)
        srv, rid = parts[0], parts[1]
        delete_range(srv, rid)
        await q.answer(f"Deleted {rid}", show_alert=True)
        await q.message.edit_text(aui_service_text(srv), parse_mode="HTML",
            reply_markup=aui_service_detail_kb(srv))
        return

    if data == "svc_export":
        if not is_admin(uid):
            await q.answer("Admin only", show_alert=True)
            return
        content = export_services_txt()
        f = io.BytesIO(content.encode())
        f.name = "services_backup.txt"
        await context.bot.send_document(uid, f, caption="📤 Services Backup")
        return

    if data == "svc_bulk":
        if not is_admin(uid):
            await q.answer("Admin only", show_alert=True)
            return
        context.user_data["admin_state"] = "svc_bulk_srv"
        await q.message.edit_text(
            "📥 <b>BULK IMPORT</b>\n\n1️⃣ Send service name (e.g. <code>WHATSAPP</code>):",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ CANCEL", callback_data="svc_list", style="danger")]]))
        return

    if data == "usr_mgmt":
        if not is_admin(uid):
            await q.answer("Admin only", show_alert=True)
            return
        await q.message.edit_text(
            "👥 <b>USER MANAGEMENT</b>\n━━━━━━━━━━━━━━━",
            parse_mode="HTML", reply_markup=aui_user_management_kb())
        return

    if data == "usr_stats":
        await q.message.edit_text(aui_stats_text(), parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 BACK", callback_data="usr_mgmt", style="danger")]]))
        return

    if data == "usr_top":
        rows = um_get_top_otp_users(10)
        if not rows:
            await q.message.edit_text("❌ No data", reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙", callback_data="usr_mgmt", style="danger")]]))
            return
        txt = "🏆 <b>TOP 10 OTP USERS</b>\n━━━━━━━━━━━━━━━\n\n"
        for i, (u, c, n) in enumerate(rows, 1):
            m = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}️⃣"
            name = html.escape(n) if n and n != "User" else f"User {u[-4:]}"
            txt += f"{m} <b>{name}</b>\n   🆔 <code>{u}</code> │ 📩 {c}\n\n"
        await q.message.edit_text(txt, parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 BACK", callback_data="usr_mgmt", style="danger")]]))
        return

    if data == "usr_balance":
        total = um_get_total_balance()
        await q.message.edit_text(
            f"💰 <b>TOTAL BALANCE</b>\n\n<blockquote>Total: <b>{total:.2f} BDT</b></blockquote>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 BACK", callback_data="usr_mgmt", style="danger")]]))
        return

    if data == "usr_list":
        users = um_get_all_users()
        if not users:
            await q.message.edit_text("❌ No users!", reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙", callback_data="usr_mgmt", style="danger")]]))
            return
        content = "\n".join(users)
        f = io.BytesIO(content.encode())
        f.name = f"users_{len(users)}.txt"
        await context.bot.send_document(uid, f, caption=f"👥 {len(users)} users")
        await q.answer("Downloaded", show_alert=True)
        return

    if data == "usr_search":
        context.user_data["admin_state"] = "usr_search"
        await q.message.edit_text(
            "🔍 Send user ID (or part of it):",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ CANCEL", callback_data="usr_mgmt", style="danger")]]))
        return

    if data == "usr_csv":
        content = um_export_users_csv()
        f = io.BytesIO(content.encode())
        f.name = "users_data.txt"
        await context.bot.send_document(uid, f, caption="📊 Full User Data")
        return

    if data == "usr_banlist":
        banned = um_load_banned()
        if not banned:
            txt = "📜 <b>BANNED USERS</b>\n\n<i>No users banned</i>"
        else:
            txt = f"📜 <b>BANNED USERS ({len(banned)})</b>\n\n"
            txt += "\n".join(f"• <code>{b}</code>" for b in banned[:50])
        await q.message.edit_text(txt, parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 BACK", callback_data="usr_mgmt", style="danger")]]))
        return

    if data.startswith("usr_addbal_"):
        tu = data.replace("usr_addbal_", "")
        context.user_data["admin_state"] = "usr_addbal_amt"
        context.user_data["usr_target"] = tu
        await q.message.edit_text(
            f"➕ Send amount to ADD to <code>{tu}</code>:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌", callback_data=f"usr_view_{tu}", style="danger")]]))
        return

    if data.startswith("usr_rembal_"):
        tu = data.replace("usr_rembal_", "")
        context.user_data["admin_state"] = "usr_rembal_amt"
        context.user_data["usr_target"] = tu
        await q.message.edit_text(
            f"➖ Send amount to REMOVE from <code>{tu}</code>:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌", callback_data=f"usr_view_{tu}", style="danger")]]))
        return

    if data.startswith("usr_ban_"):
        tu = data.replace("usr_ban_", "")
        um_ban(tu)
        await q.answer(f"Banned {tu}", show_alert=True)
        await q.message.edit_text(aui_user_profile_text(tu), parse_mode="HTML",
            reply_markup=aui_user_actions_kb(tu))
        return

    if data.startswith("usr_unban_"):
        tu = data.replace("usr_unban_", "")
        um_unban(tu)
        await q.answer(f"Unbanned {tu}", show_alert=True)
        await q.message.edit_text(aui_user_profile_text(tu), parse_mode="HTML",
            reply_markup=aui_user_actions_kb(tu))
        return

    if data.startswith("usr_view_"):
        tu = data.replace("usr_view_", "")
        await q.message.edit_text(aui_user_profile_text(tu), parse_mode="HTML",
            reply_markup=aui_user_actions_kb(tu))
        return

    if data == "pm_usage_log":
        if not is_admin(uid):
            await q.answer("Admin only", show_alert=True)
            return
        summary = get_panel_usage_summary(days=7)
        if not summary:
            txt = "📊 <b>PANEL USAGE LOG</b>\n\n<i>গত ৭ দিনে কোনো data নেই।</i>"
        else:
            txt = "📊 <b>PANEL USAGE — Last 7 Days</b>\n━━━━━━━━━━━━━━━\n\n"
            for (srv, rid), panels in summary.items():
                total = sum(panels.values())
                txt += f"📦 <b>{srv}</b> → <code>{rid}</code>\n"
                for pn, cnt in sorted(panels.items(), key=lambda x: -x[1]):
                    txt += f"   ⚙️ {pn}: <b>{cnt}</b>\n"
                txt += f"   ── Total: <b>{total}</b>\n\n"
        await q.message.edit_text(txt, parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("📥 DOWNLOAD FULL LOG", callback_data="pm_download_log", style="success")],
                [InlineKeyboardButton("🔙 BACK", callback_data="adm_back_admin", style="danger")]]))
        return

    if data == "pm_download_log":
        if not is_admin(uid):
            await q.answer("Admin only", show_alert=True)
            return
        logs = _log_load()
        if not logs:
            await q.answer("No logs yet", show_alert=True)
            return
        content = "TIME | UID | SERVICE | RANGE | PANEL | NUMBER\n"
        content += "=" * 70 + "\n"
        for entry in logs[-1000:]:
            content += f"{entry['time'][:19]} | {entry['uid']} | {entry['service']} | {entry['range']} | {entry['panel_name']} | {entry['number']}\n"
        f = io.BytesIO(content.encode())
        f.name = f"panel_usage_log_{len(logs)}.txt"
        await context.bot.send_document(uid, f, caption=f"📥 Panel Usage Log ({len(logs)} entries)")
        await q.answer("Downloaded", show_alert=True)
        return

    if data == "pm_menu":
        await q.message.edit_text("🔌 <b>PANEL MANAGEMENT</b>", parse_mode="HTML", reply_markup=pm_main_kb())
        return
    if data == "pm_list":
        panels = pm_load()
        if not panels:
            await q.message.edit_text("❌ No panels!", reply_markup=pm_main_kb())
            return
        txt = "🔌 <b>ALL PANELS</b>\n━━━━━━━━━━━━━━━\n\n"
        btns = []
        for pid, p in panels.items():
            st = p.get("status", "ON")
            icon = "🟢" if st == "ON" else "🔴"
            s = p.get("stats", {})
            txt += f"{icon} <b>{p['name']}</b>\n"
            txt += f"   🆔 <code>{pid}</code>\n"
            txt += f"   📞 Numbers: {s.get('numbers_fetched', 0)}\n"
            txt += f"   📩 OTPs: {s.get('otps_received', 0)}\n\n"
            btns.append([
                InlineKeyboardButton(f"{icon} {p['name']}", callback_data=f"pm_view_{pid}", style="primary"),
                InlineKeyboardButton("🔄", callback_data=f"pm_toggle_{pid}", style="success" if st == "OFF" else "danger")])
        btns.append([InlineKeyboardButton("🔙 BACK", callback_data="sys_settings", style="danger")])
        await q.message.edit_text(txt, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(btns))
        return
    if data.startswith("pm_view_"):
        pid = data.replace("pm_view_", "")
        panels = pm_load()
        if pid not in panels:
            await q.answer("Not found", show_alert=True)
            return
        p = panels[pid]
        s = p.get("stats", {})
        st = p.get("status", "ON")
        circ = ""
        if time.time() < p.get("circuit_open_until", 0):
            circ = "\n⚡ Circuit: OPEN (auto-disabled)"
        txt = (
            f"⚙️ <b>{p['name']}</b>\n━━━━━━━━━━━━━━━\n\n"
            f"🆔 ID: <code>{p['id']}</code>\n"
            f"🔗 URL: <code>{p['base_url']}</code>\n"
            f"🔑 Key: <code>{p['api_key'][:10]}...</code>\n"
            f"📡 Header: <code>{p['header_name']}</code>\n"
            f"🔢 Priority: <code>{p.get('priority')}</code>\n"
            f"📊 Status: {'🟢 ON' if st == 'ON' else '🔴 OFF'}{circ}\n\n"
            f"📈 Numbers: {s.get('numbers_fetched', 0)}\n"
            f"📩 OTPs: {s.get('otps_received', 0)}\n"
            f"❌ Failures: {s.get('failures', 0)}")
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"{'🔴 TURN OFF' if st=='ON' else '🟢 TURN ON'}", callback_data=f"pm_toggle_{pid}", style="danger" if st == "ON" else "success")],
            [InlineKeyboardButton("🔑 Edit API Key", callback_data=f"pm_edit_key_{pid}", style="primary"),
             InlineKeyboardButton("🔗 Edit URL", callback_data=f"pm_edit_url_{pid}", style="primary")],
            [InlineKeyboardButton("📡 Edit Header", callback_data=f"pm_edit_header_{pid}", style="primary")],
            [InlineKeyboardButton("🧪 TEST", callback_data=f"pm_test_{pid}", style="success"),
             InlineKeyboardButton("🗑 DELETE", callback_data=f"pm_del_{pid}", style="danger")],
            [InlineKeyboardButton("🔙 BACK", callback_data="sys_settings", style="danger")]])
        await q.message.edit_text(txt, parse_mode="HTML", reply_markup=kb)
        return
    if data.startswith("pm_toggle_"):
        pid = data.replace("pm_toggle_", "")
        new = pm_toggle(pid)
        if new:
            await q.answer(f"Now {new}", show_alert=True)
        await q.message.edit_text(
            "⚙️ <b>SYSTEM SETTINGS</b>\n━━━━━━━━━━━━━━━\n\n"
            "<i>👇 Panel, Group, ও অন্যান্য system control</i>",
            parse_mode="HTML", reply_markup=sys_settings_kb())
        return
    if data.startswith("pm_del_"):
        pid = data.replace("pm_del_", "")
        pm_delete(pid)
        await q.answer("Deleted", show_alert=True)
        await q.message.edit_text(
            "⚙️ <b>SYSTEM SETTINGS</b>\n━━━━━━━━━━━━━━━\n\n"
            "<i>👇 Panel, Group, ও অন্যান্য system control</i>",
            parse_mode="HTML", reply_markup=sys_settings_kb())
        return
    if data.startswith("pm_test_"):
        pid = data.replace("pm_test_", "")
        panels = pm_load()
        if pid not in panels:
            await q.answer("Not found", show_alert=True)
            return
        await q.answer("Testing...")
        ok, msg = await pm_test(panels[pid])
        await context.bot.send_message(uid, f"🧪 <b>Test: {panels[pid]['name']}</b>\n\n{msg}", parse_mode="HTML")
        return
    if data.startswith("pm_edit_key_"):
        pid = data.replace("pm_edit_key_", "")
        context.user_data["admin_state"] = "edit_panel_value"
        context.user_data["edit_pid"] = pid
        context.user_data["edit_field"] = "api_key"
        await q.message.edit_text("🔑 Send new API Key:", reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("❌", callback_data=f"pm_view_{pid}", style="danger")]]))
        return
    if data.startswith("pm_edit_url_"):
        pid = data.replace("pm_edit_url_", "")
        context.user_data["admin_state"] = "edit_panel_value"
        context.user_data["edit_pid"] = pid
        context.user_data["edit_field"] = "base_url"
        await q.message.edit_text("🔗 Send new Base URL:", reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("❌", callback_data=f"pm_view_{pid}", style="danger")]]))
        return
    if data.startswith("pm_edit_header_"):
        pid = data.replace("pm_edit_header_", "")
        context.user_data["admin_state"] = "edit_panel_value"
        context.user_data["edit_pid"] = pid
        context.user_data["edit_field"] = "header_name"
        await q.message.edit_text("📡 Send new Header Name (ASCII only):", reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("❌", callback_data=f"pm_view_{pid}", style="danger")]]))
        return
    if data == "pm_add":
        context.user_data["admin_state"] = "add_panel_name"
        await q.message.edit_text("➕ <b>ADD NEW PANEL</b>\n\n1️⃣ Send Panel Name:", parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ CANCEL", callback_data="sys_settings", style="danger")]]))
        return

    if data == "fj_menu":
        chs = load_fj()
        await q.message.edit_text(
            f"🔗 <b>FORCE JOIN</b>\n\n📢 Channels: {len(chs)}",
            parse_mode="HTML", reply_markup=fj_admin_kb())
        return
    if data == "fj_add":
        context.user_data["admin_state"] = "fj_add_channel"
        await q.message.edit_text(
            "➕ <b>ADD CHANNEL</b>\n\nFormat: <code>@username | Display Name</code>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ CANCEL", callback_data="fj_menu", style="danger")]]))
        return
    if data.startswith("fj_del_"):
        idx = int(data.replace("fj_del_", ""))
        chs = load_fj()
        if 0 <= idx < len(chs):
            del chs[idx]
            save_fj(chs)
        await q.message.edit_text("✅ Deleted", reply_markup=fj_admin_kb())
        return
    if data.startswith("fj_noop_"):
        await q.answer("Channel", show_alert=False)
        return

# ============================================================
# POST INIT / WEBHOOK / MAIN
# ============================================================
async def post_init(app):
    for _ in range(10):
        asyncio.create_task(worker())
    asyncio.create_task(monitor_loop(app))
    print("✅ Post-init: workers & monitor started")

flask_app = Flask(__name__)
ptb_app = None
MAIN_LOOP = None

@flask_app.route("/", methods=["GET"])
@flask_app.route("/health", methods=["GET"])
def health_check():
    return "ROYAL X BOT is ALIVE ✅", 200

@flask_app.route("/webhook", methods=["POST"])
def telegram_webhook():
    global ptb_app, MAIN_LOOP
    if ptb_app is None or MAIN_LOOP is None:
        return "App not ready", 503
    try:
        update_data = request.get_json(force=True)
        update = Update.de_json(update_data, ptb_app.bot)
        asyncio.run_coroutine_threadsafe(
            ptb_app.update_queue.put(update),
            MAIN_LOOP
        )
        return "OK", 200
    except Exception as e:
        print(f"Webhook error: {e}")
        return "Error", 500

def run_flask():
    flask_app.run(host="0.0.0.0", port=PORT, threaded=True, use_reloader=False)

def main():
    global ptb_app, MAIN_LOOP
    ptb_app = ApplicationBuilder().token(BOT_TOKEN).concurrent_updates(True).post_init(post_init).build()
    ptb_app.add_handler(CommandHandler("start", start))
    ptb_app.add_handler(CommandHandler("balance", balance_command))
    ptb_app.add_handler(CommandHandler("profile", profile_command))
    ptb_app.add_handler(CommandHandler("refer", refer_command))
    ptb_app.add_handler(CommandHandler("leaderboard", leaderboard_command))
    ptb_app.add_handler(CommandHandler("get1number", lambda u, c: show_services(u, c)))
    ptb_app.add_handler(CallbackQueryHandler(callback_handler))
    ptb_app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))

    print("🚀 ROYAL X BOT STARTING...")
    print(f"🌐 WEBHOOK_URL: {WEBHOOK_URL if WEBHOOK_URL else 'NOT SET (polling)'}")
    print(f"🔌 PORT: {PORT}")

    if WEBHOOK_URL:
        MAIN_LOOP = asyncio.new_event_loop()
        asyncio.set_event_loop(MAIN_LOOP)
        flask_thread = threading.Thread(target=run_flask, daemon=True)
        flask_thread.start()
        print("✅ Flask server started in background thread")

        async def run_ptb():
            await ptb_app.initialize()
            await ptb_app.bot.set_webhook(
                url=f"{WEBHOOK_URL}/webhook",
                allowed_updates=Update.ALL_TYPES,
                drop_pending_updates=True
            )
            print(f"✅ Webhook set: {WEBHOOK_URL}/webhook")
            await ptb_app.start()
            print("✅ PTB Application started")
            stop_event = asyncio.Event()
            await stop_event.wait()

        try:
            MAIN_LOOP.run_until_complete(run_ptb())
        except (KeyboardInterrupt, SystemExit):
            print("🛑 Shutting down...")
    else:
        print("📡 POLLING MODE (local dev)")
        ptb_app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == "__main__":
    main()