import os
import re
import json
import asyncio
import logging
import pytz  # pip install pytz
import datetime
from datetime import datetime, timedelta, time
from typing import Optional, List, Dict
import urllib.parse

# pip install python-telegram-bot pymongo requests pytz
import telegram
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ConversationHandler, filters, ContextTypes
from pymongo import MongoClient
from bson import ObjectId

# ===================== IST TIMEZONE CONFIGURATION =====================
IST = pytz.timezone('Asia/Kolkata')  # Indian Standard Time (UTC+5:30)
UTC = pytz.UTC

def get_ist_now() -> datetime:
    """Current Indian Time (IST) return karega"""
    return datetime.now(IST)

def get_ist_time_str() -> str:
    """IST time string me return karega"""
    now = get_ist_now()
    return now.strftime("%I:%M:%S %p")

def get_ist_date_str() -> str:
    """IST date string me return karega"""
    now = get_ist_now()
    return now.strftime("%d-%m-%Y")

def get_ist_datetime_obj(date_str: str, time_str: str = "00:00") -> datetime:
    """
    Date aur time ko IST datetime object me convert karega
    date_str: DD-MM-YYYY
    time_str: HH:MM (24 hour format)
    """
    dt_naive = datetime.strptime(f"{date_str} {time_str}", "%d-%m-%Y %H:%M")
    dt_ist = IST.localize(dt_naive)
    return dt_ist

def get_ist_today_start() -> datetime:
    """Aaj ki date 00:00 IST return karega"""
    now = get_ist_now()
    today_start = IST.localize(datetime(now.year, now.month, now.day, 0, 0, 0))
    return today_start

def get_ist_tomorrow() -> str:
    """Kal ki date IST me return karega"""
    now = get_ist_now()
    tomorrow = now + timedelta(days=1)
    return tomorrow.strftime("%d-%m-%Y")

def get_ist_today() -> str:
    """Aaj ki date IST me return karega"""
    return get_ist_now().strftime("%d-%m-%Y")

def convert_to_ist(utc_dt: datetime) -> datetime:
    """UTC datetime ko IST me convert karega"""
    if utc_dt.tzinfo is None:
        utc_dt = pytz.utc.localize(utc_dt)
    return utc_dt.astimezone(IST)

# ===================== CONFIGURATION =====================
BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"  # @BotFather se lo
MONGO_URI = "mongodb://localhost:27017"
DB_NAME = "tatkal_auto_bot_ist"
ADMIN_IDS = [123456789]  # Apna Telegram ID

# UPI Payment Config
UPI_VPA = "yourazorpay@upi"
PAYMENT_MERCHANT = "TatkalBot"

# ===================== MongoDB Collections =====================
client = MongoClient(MONGO_URI)
db = client[DB_NAME]
users_col = db["users"]
bookings_col = db["bookings"]
trains_col = db["trains"]
payment_col = db["payments"]

# ===================== State Constants =====================
(TRAIN_NUMBER, JOURNEY_DATE, CLASS_TYPE, QUOTA_TYPE,
 PASSENGER_DETAILS, MOBILE_NUMBER, UPI_ID,
 CONFIRM_BOOKING) = range(8)

# ===================== 🚀 AUTO TATKAL TIMING ENGINE (IST) =====================

def get_tatkal_timing_auto_ist() -> dict:
    """
    🕐 IST TIME KE ACCORDING TATKAL TIMING CALCULATOR
    Indian Standard Time (IST) use karta hai
    
    Tatkal Rules (Indian Time):
    - Tatkal booking: 1 day before journey date
    - AC Classes (1A, 2A, 3A, CC, EC): Booking opens at 10:00 AM IST
    - Non-AC Classes (SL, 2S, GN): Booking opens at 11:00 AM IST
    - Premium Tatkal: 10:00 AM IST (same as AC)
    - Sunday: Limited tatkal (some trains excluded)
    - Festival season: Timing may vary
    """
    now_ist = get_ist_now()
    today_ist = get_ist_today()
    tomorrow_ist = get_ist_tomorrow()
    
    # Today's date at 00:00 IST
    today_start = get_ist_today_start()
    
    # Tomorrow date components
    tomorrow_dt = now_ist + timedelta(days=1)
    tomorrow_date_str = tomorrow_dt.strftime("%d-%m-%Y")
    
    # ⏰ Tatkal Opening Times (IST)
    ac_open_time_ist = IST.localize(datetime(
        tomorrow_dt.year, tomorrow_dt.month, tomorrow_dt.day, 10, 0, 0  # 10:00 AM IST
    ))
    
    non_ac_open_time_ist = IST.localize(datetime(
        tomorrow_dt.year, tomorrow_dt.month, tomorrow_dt.day, 11, 0, 0  # 11:00 AM IST
    ))
    
    premium_tatkal_time_ist = IST.localize(datetime(
        tomorrow_dt.year, tomorrow_dt.month, tomorrow_dt.day, 10, 0, 0  # 10:00 AM IST
    ))
    
    # ⏰ Tatkal Window Close Times (IST)
    ac_window_close_ist = IST.localize(datetime(
        tomorrow_dt.year, tomorrow_dt.month, tomorrow_dt.day, 11, 0, 0  # 11:00 AM IST
    ))
    
    non_ac_window_close_ist = IST.localize(datetime(
        tomorrow_dt.year, tomorrow_dt.month, tomorrow_dt.day, 12, 0, 0  # 12:00 PM IST
    ))
    
    # Current time comparison ke liye
    current_time_ist = now_ist
    
    # ⏳ Time remaining/elapsed calculate karo
    # AC Tatkal
    if current_time_ist < ac_open_time_ist:
        ac_time_remaining = ac_open_time_ist - current_time_ist
        ac_remaining_str = str(ac_time_remaining).split(".")[0]
        ac_status = "UPCOMING"
    elif current_time_ist <= ac_window_close_ist:
        ac_time_remaining = ac_window_close_ist - current_time_ist
        ac_remaining_str = str(ac_time_remaining).split(".")[0]
        ac_status = "OPEN"
    else:
        ac_time_remaining = ac_open_time_ist + timedelta(days=1) - current_time_ist
        ac_remaining_str = str(ac_time_remaining).split(".")[0]
        ac_status = "CLOSED"
    
    # Non-AC Tatkal
    if current_time_ist < non_ac_open_time_ist:
        non_ac_time_remaining = non_ac_open_time_ist - current_time_ist
        non_ac_remaining_str = str(non_ac_time_remaining).split(".")[0]
        non_ac_status = "UPCOMING"
    elif current_time_ist <= non_ac_window_close_ist:
        non_ac_time_remaining = non_ac_window_close_ist - current_time_ist
        non_ac_remaining_str = str(non_ac_time_remaining).split(".")[0]
        non_ac_status = "OPEN"
    else:
        non_ac_time_remaining = non_ac_open_time_ist + timedelta(days=1) - current_time_ist
        non_ac_remaining_str = str(non_ac_time_remaining).split(".")[0]
        non_ac_status = "CLOSED"
    
    # Sunday check
    is_sunday = now_ist.weekday() == 6
    
    # Booking available hai ki nahi
    ac_available = (ac_status == "OPEN")
    non_ac_available = (non_ac_status == "OPEN")
    
    return {
        "ist_time": {
            "current": current_time_ist.strftime("%I:%M:%S %p"),
            "current_24h": current_time_ist.strftime("%H:%M:%S"),
            "timezone": "IST (UTC+5:30)",
            "date": today_ist,
            "weekday": now_ist.strftime("%A"),
            "weekday_num": now_ist.weekday()
        },
        "today": today_ist,
        "tomorrow": tomorrow_ist,
        "booking_date": tomorrow_date_str,
        "is_sunday": is_sunday,
        "ac_tatkal": {
            "opens_at": ac_open_time_ist.strftime("%I:%M %p"),
            "opens_at_24h": "10:00",
            "opens_date": tomorrow_date_str,
            "window_close": ac_window_close_ist.strftime("%I:%M %p"),
            "time_remaining": ac_remaining_str,
            "status": ac_status,
            "available": ac_available,
            "is_open": ac_status == "OPEN",
            "is_closed": ac_status == "CLOSED",
            "is_upcoming": ac_status == "UPCOMING"
        },
        "non_ac_tatkal": {
            "opens_at": non_ac_open_time_ist.strftime("%I:%M %p"),
            "opens_at_24h": "11:00",
            "opens_date": tomorrow_date_str,
            "window_close": non_ac_window_close_ist.strftime("%I:%M %p"),
            "time_remaining": non_ac_remaining_str,
            "status": non_ac_status,
            "available": non_ac_available,
            "is_open": non_ac_status == "OPEN",
            "is_closed": non_ac_status == "CLOSED",
            "is_upcoming": non_ac_status == "UPCOMING"
        },
        "premium_tatkal": {
            "opens_at": premium_tatkal_time_ist.strftime("%I:%M %p"),
            "opens_date": tomorrow_date_str,
            "status": ac_status  # Same as AC Tatkal
        }
    }

def get_tatkal_status_message_ist() -> str:
    """
    IST time ke hisaab se Tatkal status message generate karega
    """
    timing = get_tatkal_timing_auto_ist()
    now = get_ist_now()
    
    # Header with live time
    msg = (
        f"⏰ *LIVE TATKAL STATUS (IST)* ⏰\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🕐 *Indian Time:* `{timing['ist_time']['current']}`\n"
        f"📅 *Date:* {timing['today']} ({timing['ist_time']['weekday']})\n"
        f"🌏 *Timezone:* {timing['ist_time']['timezone']}\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
    )
    
    if timing["is_sunday"]:
        msg += (
            f"⚠️ *Today is SUNDAY* ⚠️\n\n"
            f"IRCTC Sunday ko kuch trains ke liye Tatkal booking nahi karta.\n"
            f"*Kal (Monday)* se try karein.\n"
            f"Agli booking: {timing['tomorrow']} ko 10:00 AM IST\n\n"
        )
        return msg
    
    # AC Tatkal Status
    ac = timing["ac_tatkal"]
    ac_icon = "🟢" if ac["available"] else ("🔴" if ac["is_closed"] else "🟡")
    ac_status_text = "✅ *OPEN NOW*" if ac["available"] else ("❌ *CLOSED*" if ac["is_closed"] else "⏳ *UPCOMING*")
    
    msg += (
        f"{ac_icon} *AC TATKAL* (1A, 2A, 3A, CC, EC)\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"   📅 Booking for: {ac['opens_date']}\n"
        f"   🕐 Opens at: `{ac['opens_at']}` IST\n"
        f"   🕐 Window: 10:00 AM - 11:00 AM IST\n"
        f"   📊 Status: {ac_status_text}\n"
    )
    
    if ac["is_upcoming"]:
        msg += f"   ⏳ Time left to open: `{ac['time_remaining']}`\n"
    elif ac["is_open"]:
        msg += f"   ⏳ Window closes in: `{ac['time_remaining']}`\n"
        msg += f"   ⚡ *BOOK NOW!* Jaldi karein!\n"
    elif ac["is_closed"]:
        msg += f"   🔄 Next opening: Kal {ac['opens_at']} IST\n"
    
    msg += "\n"
    
    # Non-AC Tatkal Status
    non_ac = timing["non_ac_tatkal"]
    non_ac_icon = "🟢" if non_ac["available"] else ("🔴" if non_ac["is_closed"] else "🟡")
    non_ac_status_text = "✅ *OPEN NOW*" if non_ac["available"] else ("❌ *CLOSED*" if non_ac["is_closed"] else "⏳ *UPCOMING*")
    
    msg += (
        f"{non_ac_icon} *NON-AC TATKAL* (SL, 2S)\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"   📅 Booking for: {non_ac['opens_date']}\n"
        f"   🕐 Opens at: `{non_ac['opens_at']}` IST\n"
        f"   🕐 Window: 11:00 AM - 12:00 PM IST\n"
        f"   📊 Status: {non_ac_status_text}\n"
    )
    
    if non_ac["is_upcoming"]:
        msg += f"   ⏳ Time left to open: `{non_ac['time_remaining']}`\n"
    elif non_ac["is_open"]:
        msg += f"   ⏳ Window closes in: `{non_ac['time_remaining']}`\n"
        msg += f"   ⚡ *BOOK NOW!*\n"
    elif non_ac["is_closed"]:
        msg += f"   🔄 Next opening: Kal {non_ac['opens_at']} IST\n"
    
    msg += "\n"
    
    # Premium Tatkal
    premium = timing["premium_tatkal"]
    msg += (
        f"💎 *PREMIUM TATKAL*\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"   Opens at: `{premium['opens_at']}` IST\n"
        f"   Same timing as AC Tatkal\n"
        f"   Higher charges but better chance!\n\n"
    )
    
    # Summary
    msg += f"━━━━━━━━━━━━━━━━━━━━━\n"
    if ac["available"] or non_ac["available"]:
        msg += f"\n🔥 *TATKAL WINDOW OPEN HAI!*\nJaldi booking karein! 🚂💨"
    else:
        msg += f"\n💡 *Next Tatkal:* {timing['tomorrow']}\n"
        msg += f"   • AC: 10:00 AM IST\n"
        msg += f"   • Non-AC: 11:00 AM IST\n"
        msg += f"   • Exactly time pe ready rahein!"
    
    return msg

def get_next_tatkal_time_ist() -> str:
    """
    Agla Tatkal opening time IST me return karega
    """
    timing = get_tatkal_timing_auto_ist()
    now = get_ist_now()
    
    if timing["ac_tatkal"]["available"] or timing["non_ac_tatkal"]["available"]:
        return "NOW"
    
    # Next AC opening
    next_ac = timing["ac_tatkal"]["opens_at"]
    next_date = timing["ac_tatkal"]["opens_date"]
    
    return f"{next_ac} IST on {next_date}"

def should_attempt_booking_ist(class_type: str) -> bool:
    """
    IST time ke hisaab se check karega ki booking attempt karna chahiye ya nahi
    """
    timing = get_tatkal_timing_auto_ist()
    
    if timing["is_sunday"]:
        return False
    
    if class_type in ["1A", "2A", "3A", "CC", "EC"]:
        return timing["ac_tatkal"]["available"]
    else:
        return timing["non_ac_tatkal"]["available"]

def get_day_name_ist(date_str: str) -> str:
    """
    Kisi bhi date ka day name IST me return karega
    """
    dt = datetime.strptime(date_str, "%d-%m-%Y")
    dt_ist = IST.localize(dt)
    return dt_ist.strftime("%A")

# ===================== UI Components =====================

def get_main_keyboard():
    keyboard = [
        [KeyboardButton("🚂 Auto Book Tatkal"), KeyboardButton("📋 My Bookings")],
        [KeyboardButton("⏰ Live Tatkal Status (IST)"), KeyboardButton("🔔 Set Auto Book")],
        [KeyboardButton("ℹ️ Help / Info")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_cancel_keyboard():
    keyboard = [[KeyboardButton("❌ Cancel Booking")]]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_class_keyboard():
    keyboard = [
        [InlineKeyboardButton("🛏️ Sleeper (SL) - Non AC", callback_data="class_SL")],
        [InlineKeyboardButton("💺 AC 3 Tier (3A)", callback_data="class_3A")],
        [InlineKeyboardButton("💺 AC 2 Tier (2A)", callback_data="class_2A")],
        [InlineKeyboardButton("💺 AC 1 Tier (1A)", callback_data="class_1A")],
        [InlineKeyboardButton("🪑 Chair Car (CC)", callback_data="class_CC")],
        [InlineKeyboardButton("💎 Premium Tatkal (PT)", callback_data="class_PT")],
        [InlineKeyboardButton("🪑 Second Sitting (2S) - Non AC", callback_data="class_2S")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_quota_keyboard():
    keyboard = [
        [InlineKeyboardButton("🔴 Tatkal (TQ) ⚡FASTEST", callback_data="quota_TQ")],
        [InlineKeyboardButton("🔵 Premium Tatkal (PT) ⚡⚡", callback_data="quota_PT")],
        [InlineKeyboardButton("🟢 General (GN)", callback_data="quota_GN")],
        [InlineKeyboardButton("🟡 Ladies (LD)", callback_data="quota_LD")],
        [InlineKeyboardButton("🟠 Lower Berth (SS)", callback_data="quota_SS")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_confirm_keyboard():
    keyboard = [
        [InlineKeyboardButton("✅ Confirm & Pay Now", callback_data="confirm_yes")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
    ]
    return InlineKeyboardMarkup(keyboard)

# ===================== Helper Functions =====================

def validate_upi(upi_id: str) -> bool:
    pattern = r'^[a-zA-Z0-9.\-_]{2,49}@[a-zA-Z]{2,}$'
    return bool(re.match(pattern, upi_id))

def validate_mobile(mobile: str) -> bool:
    pattern = r'^[6-9]\d{9}$'
    return bool(re.match(pattern, mobile))

def validate_train_number(train_no: str) -> bool:
    return bool(re.match(r'^\d{5}$', train_no))

async def fetch_train_info(train_number: str) -> dict:
    trains_db = {
        "12301": {"name": "Howrah - New Delhi Rajdhani Express", "source": "Howrah (HWH)", "dest": "New Delhi (NDLS)"},
        "12302": {"name": "New Delhi - Howrah Rajdhani Express", "source": "New Delhi (NDLS)", "dest": "Howrah (HWH)"},
        "12001": {"name": "Bhopal - New Delhi Shatabdi", "source": "Bhopal (BPL)", "dest": "New Delhi (NDLS)"},
        "12431": {"name": "Trivandrum - Nizamuddin Rajdhani", "source": "Trivandrum (TVC)", "dest": "Hazrat Nizamuddin (NZM)"},
        "12621": {"name": "New Delhi - Chennai Tamil Nadu Express", "source": "New Delhi (NDLS)", "dest": "Chennai (MAS)"},
        "12951": {"name": "Mumbai - New Delhi Rajdhani Express", "source": "Mumbai (MMCT)", "dest": "New Delhi (NDLS)"},
    }
    if train_number in trains_db:
        return trains_db[train_number]
    return {"name": "Unknown Train", "source": "Unknown", "dest": "Unknown"}

def calculate_tatkal_charges(class_type: str) -> dict:
    charges = {
        "SL": {"base": 150, "gst": 18, "description": "Sleeper"},
        "3A": {"base": 300, "gst": 18, "description": "AC 3 Tier"},
        "2A": {"base": 400, "gst": 18, "description": "AC 2 Tier"},
        "1A": {"base": 500, "gst": 18, "description": "AC 1 Tier"},
        "CC": {"base": 250, "gst": 18, "description": "Chair Car"},
        "2S": {"base": 100, "gst": 18, "description": "Second Sitting"},
        "PT": {"base": 400, "gst": 18, "description": "Premium Tatkal"},
    }
    cls = class_type.upper()
    if cls in charges:
        base = charges[cls]["base"]
        gst = charges[cls]["gst"]
        total = base + gst
        return {"base_charge": base, "gst": gst, "total_charge": total, "description": charges[cls]["description"]}
    return {"base_charge": 0, "gst": 0, "total_charge": 0, "description": "Unknown"}

def calculate_total_amount(class_type: str, passenger_count: int) -> dict:
    charges = calculate_tatkal_charges(class_type)
    base_fare_per = 50
    tatkal_charge = charges["base_charge"]
    gst = charges["gst"]
    
    total_base = base_fare_per * passenger_count
    total_tatkal = tatkal_charge * passenger_count
    total_gst = gst * passenger_count
    grand_total = total_base + total_tatkal + total_gst
    
    return {
        "base_fare": total_base,
        "tatkal_charge": total_tatkal,
        "gst": total_gst,
        "grand_total": grand_total,
        "per_passenger": {
            "base": base_fare_per,
            "tatkal": tatkal_charge,
            "gst": gst
        }
    }

def generate_upi_payment_link(amount: int, payee_vpa: str, 
                              payee_name: str = "TatkalBot",
                              transaction_note: str = "Tatkal Ticket Booking",
                              transaction_ref: str = None) -> str:
    if transaction_ref is None:
        transaction_ref = f"TKT{datetime.now().strftime('%y%m%d%H%M%S')}"
    
    params = {
        "pa": payee_vpa,
        "pn": payee_name,
        "am": str(amount),
        "tn": transaction_note,
        "tr": transaction_ref,
        "cu": "INR"
    }
    
    query_string = urllib.parse.urlencode(params)
    upi_link = f"upi://pay?{query_string}"
    
    return upi_link, transaction_ref

# ===================== Command Handlers =====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat_id = update.effective_chat.id
    
    users_col.update_one(
        {"user_id": chat_id},
        {"$set": {
            "username": user.username,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "last_active": get_ist_now()
        }},
        upsert=True
    )
    
    timing = get_tatkal_timing_auto_ist()
    
    welcome_msg = (
        f"🚂 *TATKAL AUTO BOOKING BOT* 🚂\n\n"
        f"Namaste {user.first_name}! 🙏\n\n"
        f"🕐 *Current Indian Time:* `{timing['ist_time']['current']}` IST\n"
        f"📅 *Date:* {timing['today']} ({timing['ist_time']['weekday']})\n"
        f"📅 *Booking For:* {timing['tomorrow']}\n\n"
    )
    
    if timing["ac_tatkal"]["available"] or timing["non_ac_tatkal"]["available"]:
        welcome_msg += "🔥 *TATKAL WINDOW OPEN HAI!* Jaldi karein!\n\n"
    else:
        if not timing["is_sunday"]:
            welcome_msg += (
                f"⏰ *Next Tatkal Opening:*\n"
                f"   🟦 AC: `{timing['ac_tatkal']['opens_at']}` IST\n"
                f"   🟩 Non-AC: `{timing['non_ac_tatkal']['opens_at']}` IST\n\n"
            )
    
    welcome_msg += (
        f"✅ *Features:*\n"
        f"   🕐 Indian Time (IST) based\n"
        f"   🔄 Auto timing calculation\n"
        f"   💳 UPI auto payment link\n"
        f"   📋 Booking history\n\n"
        f"👇 *Start karein:*"
    )
    
    await update.message.reply_text(
        welcome_msg,
        parse_mode="Markdown",
        reply_markup=get_main_keyboard()
    )

async def tatkal_status_ist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Live IST-based Tatkal status"""
    status_msg = get_tatkal_status_message_ist()
    await update.message.reply_text(status_msg, parse_mode="Markdown", reply_markup=get_main_keyboard())

async def my_bookings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    bookings = list(bookings_col.find({"user_id": chat_id}).sort("created_at", -1).limit(15))
    
    if not bookings:
        await update.message.reply_text(
            "❌ *No Bookings Found*",
            parse_mode="Markdown",
            reply_markup=get_main_keyboard()
        )
        return
    
    msg = f"📋 *Your Bookings ({len(bookings)})*\n\n"
    for idx, b in enumerate(bookings, 1):
        # Convert stored UTC time to IST for display
        created_ist = ""
        if "created_at" in b:
            created_ist = convert_to_ist(b["created_at"]).strftime("%d-%m-%Y %I:%M %p")
        
        status_icon = "✅" if b.get("status") == "Confirmed" else "⏳"
        pay_icon = "💰" if b.get("payment_status") == "Paid" else "💳"
        
        msg += (
            f"{idx}. {status_icon} *{b.get('train_number')}*\n"
            f"   📅 {b.get('journey_date')} | 🛏️ {b.get('class_type')}\n"
            f"   👥 {len(b.get('passengers', []))} passengers\n"
            f"   {pay_icon} ₹{b.get('total_amount', 0)}\n"
            f"   🕐 Booked at: {created_ist}\n"
            f"   🆔 `{str(b['_id'])[:10]}`\n\n"
        )
    
    await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=get_main_keyboard())

async def set_auto_book(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔔 *Auto Book Feature*\n\n"
        f"🕐 *Current IST:* {get_ist_time_str()}\n\n"
        "• Aapko Tatkal khulte hi notify karega\n"
        "• Auto-book Pro version mein available\n"
        "• Abhi manual booking use karein",
        parse_mode="Markdown",
        reply_markup=get_main_keyboard()
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    now_ist = get_ist_now()
    timing = get_tatkal_timing_auto_ist()
    
    help_text = (
        f"📖 *Tatkal Auto Bot Guide*\n\n"
        f"🕐 *Current IST:* `{now_ist.strftime('%I:%M:%S %p')}`\n"
        f"📅 *Date:* {now_ist.strftime('%d-%m-%Y')}\n\n"
        f"🚂 *Auto Book Tatkal*\n"
        f"1️⃣ 'Auto Book Tatkal' button dabaye\n"
        f"2️⃣ Train number dalein (5 digit)\n"
        f"3️⃣ Baaki sab bot automatically handle karega\n"
        f"4️⃣ UPI se payment karein\n"
        f"5️⃣ 'Payment Done' button dabaye\n\n"
        f"⏰ *Tatkal Timings (IST)*\n"
        f"🟦 AC: `{timing['ac_tatkal']['opens_at']}` IST (Window: 10-11 AM)\n"
        f"🟩 Non-AC: `{timing['non_ac_tatkal']['opens_at']}` IST (Window: 11-12 PM)\n\n"
        f"💳 *UPI Payment*\n"
        f"• Bot UPI link generate karega\n"
        f"• Button dabate hi UPI app open hoga\n\n"
        f"❓ /start se dubara try karein"
    )
    await update.message.reply_text(help_text, parse_mode="Markdown", reply_markup=get_main_keyboard())

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "❌ *Cancelled*",
        parse_mode="Markdown",
        reply_markup=get_main_keyboard()
    )
    return ConversationHandler.END

async def callback_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data.clear()
    await query.edit_message_text("❌ *Cancelled*", parse_mode="Markdown")
    await query.message.reply_text("Koi aur help?", reply_markup=get_main_keyboard())
    return ConversationHandler.END

# ===================== Booking Flow =====================

async def book_tatkal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    context.user_data["passengers"] = []
    
    timing = get_tatkal_timing_auto_ist()
    
    msg = (
        f"🚂 *AUTO TATKAL BOOKING*\n\n"
        f"🕐 *IST:* `{timing['ist_time']['current']}`\n"
        f"📅 *Booking For:* {timing['booking_date']}\n\n"
        f"*Step 1: Train Number*\n\n"
        f"Apni train ka *5 digit number* dalein.\n\n"
        f"उदाहरण: `12301`, `12431`, `12001`"
    )
    
    await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=get_cancel_keyboard())
    return TRAIN_NUMBER

async def receive_train_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    
    if text == "❌ Cancel Booking":
        return await cancel(update, context)
    
    if not validate_train_number(text):
        await update.message.reply_text(
            "❌ *Invalid!* 5 digit number dalein. Jaise: `12301`",
            parse_mode="Markdown"
        )
        return TRAIN_NUMBER
    
    user_data = context.user_data
    user_data["train_number"] = text
    
    train_info = await fetch_train_info(text)
    user_data["train_name"] = train_info["name"]
    user_data["source"] = train_info["source"]
    user_data["dest"] = train_info["dest"]
    
    await update.message.reply_text(
        f"✅ *Train Found!*\n\n"
        f"🚂 `{text}` - {train_info['name']}\n"
        f"🚉 {train_info['source']} → {train_info['dest']}\n\n"
        f"📅 *Step 2: Journey Date (IST)*\n\n"
        f"Date dalein (DD-MM-YYYY):\n"
        f"Default: `{get_tatkal_timing_auto_ist()['booking_date']}`\n"
        f"(Kal ki date - Tatkal 1 din pehle book hota hai)",
        parse_mode="Markdown",
        reply_markup=get_cancel_keyboard()
    )
    return JOURNEY_DATE

async def receive_journey_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    
    if text == "❌ Cancel Booking":
        return await cancel(update, context)
    
    try:
        default_date = get_tatkal_timing_auto_ist()["booking_date"]
        
        if text.lower() in ["default", ""]:
            text = default_date
        
        # Parse in IST context
        journey_date = datetime.strptime(text, "%d-%m-%Y")
        now_ist = get_ist_now()
        today_start = get_ist_today_start()
        
        # Journey date in IST
        journey_start = IST.localize(datetime(
            journey_date.year, journey_date.month, journey_date.day, 0, 0, 0
        ))
        
        if journey_start < today_start:
            await update.message.reply_text(
                "❌ *Past date!* Aaj ya kal ki date dalein (IST).",
                parse_mode="Markdown"
            )
            return JOURNEY_DATE
        
        max_date = today_start + timedelta(days=120)
        if journey_start > max_date:
            await update.message.reply_text(
                "❌ *Max 120 days ahead only!*",
                parse_mode="Markdown"
            )
            return JOURNEY_DATE
        
        user_data = context.user_data
        user_data["journey_date"] = text
        user_data["journey_day"] = journey_start.strftime("%A")
        
        await update.message.reply_text(
            f"✅ Date: *{text}* ({journey_start.strftime('%A')})\n\n"
            f"🛏️ *Step 3: Select Class*\n\n"
            f"Kripya class chune:",
            parse_mode="Markdown",
            reply_markup=get_class_keyboard()
        )
        return CLASS_TYPE
        
    except ValueError:
        await update.message.reply_text(
            "❌ *Invalid format!* `DD-MM-YYYY` use karein\n"
            "Example: `25-12-2024`",
            parse_mode="Markdown"
        )
        return JOURNEY_DATE

async def class_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "cancel":
        return await callback_cancel(update, context)
    
    class_type = query.data.replace("class_", "")
    class_names = {
        "SL": "Sleeper (SL)", "3A": "AC 3 Tier (3A)", "2A": "AC 2 Tier (2A)",
        "1A": "AC 1 Tier (1A)", "CC": "Chair Car (CC)", "2S": "Second Sitting (2S)",
        "PT": "Premium Tatkal (PT)"
    }
    
    user_data = context.user_data
    user_data["class_type"] = class_type
    
    charges = calculate_tatkal_charges(class_type)
    
    await query.edit_message_text(
        text=(
            f"✅ *{class_names.get(class_type, class_type)}* Selected\n\n"
            f"💰 *Charges per person:*\n"
            f"   Base: ₹50 + Tatkal: ₹{charges['base_charge']} + GST: ₹{charges['gst']}\n"
            f"   *Total per person: ₹{charges['total_charge'] + 50}*\n\n"
            f"📋 *Step 4: Select Quota*\n\n"
            f"Tatkal ke liye 'Tatkal (TQ)' select karein:"
        ),
        parse_mode="Markdown",
        reply_markup=get_quota_keyboard()
    )
    return QUOTA_TYPE

async def quota_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "cancel":
        return await callback_cancel(update, context)
    
    quota_type = query.data.replace("quota_", "")
    quota_names = {
        "TQ": "Tatkal (TQ)", "PT": "Premium Tatkal (PT)",
        "GN": "General (GN)", "LD": "Ladies (LD)", "SS": "Lower Berth (SS)"
    }
    
    user_data = context.user_data
    user_data["quota"] = quota_type
    
    await query.edit_message_text(
        text=(
            f"✅ Quota: *{quota_names.get(quota_type, quota_type)}*\n\n"
            f"👤 *Step 5: Passenger Details*\n\n"
            f"Format: `Name, Age, Gender`\n\n"
            f"Example:\n"
            f"`Rahul Kumar, 28, Male`\n\n"
            f"*Ek baar mein ek passenger*"
        ),
        parse_mode="Markdown"
    )
    return PASSENGER_DETAILS

async def receive_passenger_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    
    if text == "❌ Cancel Booking":
        return await cancel(update, context)
    
    try:
        parts = [p.strip() for p in text.split(",")]
        
        if len(parts) != 3:
            raise ValueError("3 fields needed")
        
        name = parts[0]
        age = int(parts[1])
        gender = parts[2].capitalize()
        
        if len(name) < 2:
            raise ValueError("Name too short")
        if age < 1 or age > 120:
            raise ValueError("Invalid age")
        if gender not in ["Male", "Female", "M", "F", "Other", "O"]:
            raise ValueError("Invalid gender")
        
        gender_map = {"M": "Male", "F": "Female", "O": "Other"}
        if gender in gender_map:
            gender = gender_map[gender]
        
        passenger = {"name": name, "age": age, "gender": gender}
        
        user_data = context.user_data
        user_data["passengers"].append(passenger)
        
        keyboard = [
            [InlineKeyboardButton("➕ Add More", callback_data="add_more")],
            [InlineKeyboardButton("✅ Next - Mobile Number", callback_data="next_mobile")],
            [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"✅ *Passenger #{len(user_data['passengers'])} Added!*\n\n"
            f"👤 Name: {name}\n"
            f"🕐 Age: {age}\n"
            f"👤 Gender: {gender}\n\n"
            f"*Add more ya proceed karein?*",
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
        return PASSENGER_DETAILS
        
    except (ValueError, IndexError):
        await update.message.reply_text(
            "❌ *Invalid format!*\n\n"
            "Sahi format: `Name, Age, Gender`\n"
            "Example: `Rahul Kumar, 28, Male`",
            parse_mode="Markdown"
        )
        return PASSENGER_DETAILS

async def passenger_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "cancel":
        return await callback_cancel(update, context)
    
    if query.data == "add_more":
        await query.edit_message_text(
            text="➕ *Add Another Passenger*\n\n"
                 "Format: `Name, Age, Gender`\n"
                 "Example: `Priya Sharma, 25, Female`",
            parse_mode="Markdown"
        )
        return PASSENGER_DETAILS
    
    if query.data == "next_mobile":
        await query.edit_message_text(
            text="📱 *Step 6: Mobile Number*\n\n"
                 "Apna 10-digit mobile number dalein:",
            parse_mode="Markdown"
        )
        return MOBILE_NUMBER

async def receive_mobile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    
    if text == "❌ Cancel Booking":
        return await cancel(update, context)
    
    if not validate_mobile(text):
        await update.message.reply_text(
            "❌ *Invalid!* Sahi 10-digit mobile number dalein:",
            parse_mode="Markdown"
        )
        return MOBILE_NUMBER
    
    user_data = context.user_data
    user_data["mobile"] = text
    
    await update.message.reply_text(
        f"✅ Mobile: *{text}*\n\n"
        f"💳 *Step 7: UPI ID*\n\n"
        f"Apna UPI ID dalein:\n\n"
        f"Example: `user@paytm`, `name@ybl`, `user@upi`",
        parse_mode="Markdown",
        reply_markup=get_cancel_keyboard()
    )
    return UPI_ID

async def receive_upi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    
    if text == "❌ Cancel Booking":
        return await cancel(update, context)
    
    if not validate_upi(text):
        await update.message.reply_text(
            "❌ *Invalid UPI ID!*\n\n"
            "Sahi format: `username@provider`\n"
            "Example: `user@paytm`, `name@ybl`",
            parse_mode="Markdown"
        )
        return UPI_ID
    
    user_data = context.user_data
    user_data["upi_id"] = text
    
    passengers = user_data["passengers"]
    total = len(passengers)
    class_type = user_data["class_type"]
    total_amount_detailed = calculate_total_amount(class_type, total)
    
    now_ist = get_ist_now()
    
    msg = (
        f"📄 *BOOKING SUMMARY*\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🕐 *IST:* {now_ist.strftime('%I:%M %p')}\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"🚂 *{user_data['train_number']}* - {user_data['train_name']}\n"
        f"🚉 {user_data['source']} → {user_data['dest']}\n"
        f"📅 *Date:* {user_data['journey_date']} ({user_data.get('journey_day', '')})\n"
        f"🛏️ *Class:* {class_type} | 📋 *Quota:* {user_data['quota']}\n\n"
        f"👥 *Passengers ({total}):*\n"
    )
    
    for i, p in enumerate(passengers, 1):
        msg += f"   {i}. {p['name']} ({p['age']} yrs, {p['gender']})\n"
    
    msg += (
        f"\n📱 *Mobile:* {user_data['mobile']}\n"
        f"💳 *UPI:* {user_data['upi_id']}\n\n"
        f"💰 *Payment:*\n"
        f"   Base Fare: ₹{total_amount_detailed['base_fare']}\n"
        f"   Tatkal Charges: ₹{total_amount_detailed['tatkal_charge']}\n"
        f"   GST: ₹{total_amount_detailed['gst']}\n"
        f"   ─────────────────────\n"
        f"   *Total: ₹{total_amount_detailed['grand_total']}*\n\n"
        f"✅ *Confirm booking?*"
    )
    
    await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=get_confirm_keyboard())
    return CONFIRM_BOOKING

async def confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "cancel":
        return await callback_cancel(update, context)
    
    user_data = context.user_data
    chat_id = update.effective_chat.id
    
    passengers = user_data["passengers"]
    total_passengers = len(passengers)
    total_amount = calculate_total_amount(user_data["class_type"], total_passengers)["grand_total"]
    
    now_ist = get_ist_now()
    
    booking_data = {
        "user_id": chat_id,
        "train_number": user_data["train_number"],
        "train_name": user_data.get("train_name", ""),
        "source": user_data.get("source", ""),
        "dest": user_data.get("dest", ""),
        "journey_date": user_data["journey_date"],
        "journey_day": user_data.get("journey_day", ""),
        "class_type": user_data["class_type"],
        "quota": user_data["quota"],
        "passengers": user_data["passengers"],
        "mobile": user_data["mobile"],
        "upi_id": user_data["upi_id"],
        "total_amount": total_amount,
        "status": "Payment Pending",
        "payment_status": "Pending",
        "created_at_ist": now_ist,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }
    
    result = bookings_col.insert_one(booking_data)
    booking_data["_id"] = result.inserted_id
    
    await query.edit_message_text(text="⏳ *Generating payment link...*", parse_mode="Markdown")
    
    # UPI Payment link
    txn_ref = f"TKT{now_ist.strftime('%y%m%d%H%M%S')}"
    upi_link, _ = generate_upi_payment_link(
        amount=total_amount,
        payee_vpa=UPI_VPA,
        payee_name=PAYMENT_MERCHANT,
        transaction_note=f"Tatkal {user_data['train_number']} {user_data['journey_date']}",
        transaction_ref=txn_ref
    )
    
    payment_col.insert_one({
        "user_id": chat_id,
        "booking_id": str(booking_data["_id"]),
        "transaction_ref": txn_ref,
        "amount": total_amount,
        "upi_id": user_data["upi_id"],
        "payee_vpa": UPI_VPA,
        "status": "pending",
        "created_at_ist": now_ist,
        "created_at": datetime.utcnow()
    })
    
    keyboard = [
        [InlineKeyboardButton(f"💳 Pay ₹{total_amount} via UPI", url=upi_link)],
        [InlineKeyboardButton("✅ Payment Done", callback_data=f"pd_{txn_ref}")],
        [InlineKeyboardButton("❌ Cancel Booking", callback_data="cancel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        text=(
            f"💳 *PAYMENT REQUIRED*\n\n"
            f"🕐 *IST:* {now_ist.strftime('%I:%M %p')}\n\n"
            f"💰 *Amount:* ₹{total_amount}\n"
            f"💳 *Pay To:* `{UPI_VPA}`\n"
            f"🆔 *Ref:* `{txn_ref}`\n\n"
            f"👇 *'Pay via UPI' button dabaye*\n"
            f"→ UPI app automatically open ho jayega\n\n"
            f"✅ *Pay karne ke baad* '✅ Payment Done' dabaye"
        ),
        parse_mode="Markdown",
        reply_markup=reply_markup
    )
    
    return CONFIRM_BOOKING

async def payment_done_callback_final(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    txn_ref = query.data.replace("pd_", "")
    now_ist = get_ist_now()
    
    payment_col.update_one(
        {"transaction_ref": txn_ref},
        {"$set": {"status": "paid", "paid_at_ist": now_ist, "paid_at": datetime.utcnow()}}
    )
    
    payment = payment_col.find_one({"transaction_ref": txn_ref})
    if payment:
        bookings_col.update_one(
            {"_id": ObjectId(payment["booking_id"])},
            {"$set": {
                "status": "Confirmed",
                "payment_status": "Paid",
                "confirmed_at_ist": now_ist,
                "updated_at": datetime.utcnow()
            }}
        )
    
    await query.edit_message_text(
        text="✅ *PAYMENT RECEIVED!*\n\n🔄 Booking confirmation in progress...\n🕐 IST: " + now_ist.strftime("%I:%M %p"),
        parse_mode="Markdown"
    )
    
    await asyncio.sleep(1.5)
    
    await query.edit_message_text(
        text=(
            f"🎉✅ *TICKET BOOKED SUCCESSFULLY!*\n\n"
            f"🆔 *Booking ID:* `{txn_ref}`\n"
            f"🕐 *Confirmed at:* {now_ist.strftime('%I:%M %p')} IST\n\n"
            f"🚂 *Train booked!*\n"
            f"💰 *Paid:* ✅\n"
            f"📊 *Status:* CONFIRMED\n\n"
            f"📋 /bookings se details check karein"
        ),
        parse_mode="Markdown"
    )
    
    await query.message.reply_text("👇 *Aur kya help chahiye?*", reply_markup=get_main_keyboard())
    context.user_data.clear()
    return ConversationHandler.END

# ===================== Message Router =====================

async def message_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    
    routes = {
        "🚂 Auto Book Tatkal": book_tatkal,
        "📋 My Bookings": my_bookings,
        "⏰ Live Tatkal Status (IST)": tatkal_status_ist,
        "🔔 Set Auto Book": set_auto_book,
        "ℹ️ Help / Info": help_command,
        "❌ Cancel Booking": cancel
    }
    
    if text in routes:
        return await routes[text](update, context)
    
    await update.message.reply_text(
        "❌ *Samajh nahi aaya!*\n\nNeeche diye buttons use karein:",
        parse_mode="Markdown",
        reply_markup=get_main_keyboard()
    )

# ===================== Error Handler =====================

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.error(f"Error: {context.error}")
    try:
        if update and update.effective_chat:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="❌ *Technical Error!* /start se try karein.",
                parse_mode="Markdown",
                reply_markup=get_main_keyboard()
            )
    except:
        pass

# ===================== Main =====================

def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    app = Application.builder().token(BOT_TOKEN).build()
    
    conv_handler = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex('^🚂 Auto Book Tatkal$'), book_tatkal),
            CommandHandler('book', book_tatkal),
        ],
        states={
            TRAIN_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_train_number)],
            JOURNEY_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_journey_date)],
            CLASS_TYPE: [CallbackQueryHandler(class_callback)],
            QUOTA_TYPE: [CallbackQueryHandler(quota_callback)],
            PASSENGER_DETAILS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_passenger_details),
                CallbackQueryHandler(passenger_callback)
            ],
            MOBILE_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_mobile)],
            UPI_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_upi)],
            CONFIRM_BOOKING: [
                CallbackQueryHandler(confirm_callback, pattern='^confirm_yes$'),
                CallbackQueryHandler(payment_done_callback_final, pattern='^pd_'),
                CallbackQueryHandler(callback_cancel, pattern='^cancel$')
            ],
        },
        fallbacks=[
            CommandHandler('cancel', cancel),
            MessageHandler(filters.Regex('^❌ Cancel Booking$'), cancel),
            CallbackQueryHandler(callback_cancel, pattern='^cancel$'),
        ],
        name="auto_booking_ist",
        per_user=True,
        per_chat=True
    )
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("bookings", my_bookings))
    app.add_handler(CommandHandler("status", tatkal_status_ist))
    app.add_handler(conv_handler)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_router))
    app.add_error_handler(error_handler)
    
    print(f"🚂 Tatkal Auto Bot Running with IST Timezone!")
    print(f"🕐 Current IST: {get_ist_time_str()}")
    print(f"📅 Date: {get_ist_date_str()}")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()