import os
import re
import json
import asyncio
import logging
import datetime
from datetime import datetime, timedelta
from typing import Optional, List, Dict
import urllib.parse

# pip install python-telegram-bot pymongo requests schedule
import telegram
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ConversationHandler, filters, ContextTypes
from pymongo import MongoClient
from bson import ObjectId

# ===================== CONFIGURATION =====================
BOT_TOKEN = "8975874713:AAEoAyYW1Dyoqyoli-B0auTcOuOEoC9Mm4c"  # @BotFather se lo
MONGO_URI = "mongodb+srv://taiyabalim8:ZixPlaysBot2026@cluster0.kmqdqwj.mongodb.net/?appName=Cluster0&compressors=zlib"
DB_NAME = "tatkal_auto_bot"
ADMIN_IDS = [123456789]  # Apna Telegram ID

# UPI Payment Config (Real payment gateway ke liye)
UPI_VPA = "blitzzxtaiyab@okaxis"  # Aapka UPI ID jisme payment aayegi
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

# ===================== Auto Tatkal Timing Engine =====================

def get_tatkal_timing_auto() -> dict:
    """
    🚀 AUTO TATKAL TIMING CALCULATOR
    Current time ke hisaab se automatically calculate karega
    ki Tatkal kab khulega
    """
    now = datetime.now()
    today = now.date()
    tomorrow = today + timedelta(days=1)
    
    # Tatkal Rules:
    # - AC Classes (1A, 2A, 3A, CC): Booking 10:00 AM (1 day before)
    # - Non-AC Classes (SL, 2S): Booking 11:00 AM (1 day before)
    # - Sunday: No tatkal for some trains
    # - Festival season: Dynamic timings
    
    ac_open_time = datetime.combine(tomorrow, datetime.strptime("10:00", "%H:%M").time())
    non_ac_open_time = datetime.combine(tomorrow, datetime.strptime("11:00", "%H:%M").time())
    
    # Check if today is Sunday (Tatkal nahi hota kuch trains me)
    is_sunday = today.weekday() == 6
    
    # Calculate time remaining
    ac_remaining = ac_open_time - now if ac_open_time > now else timedelta(0)
    non_ac_remaining = non_ac_open_time - now if non_ac_open_time > now else timedelta(0)
    
    # Tatkal window: 10:00 AM to 11:00 AM (AC), 11:00 AM to 12:00 PM (Non-AC)
    ac_window_close = datetime.combine(today, datetime.strptime("11:00", "%H:%M").time())
    non_ac_window_close = datetime.combine(today, datetime.strptime("12:00", "%H:%M").time())
    
    ac_window = now <= ac_window_close and now >= datetime.combine(today, datetime.strptime("10:00", "%H:%M").time())
    non_ac_window = now <= non_ac_window_close and now >= datetime.combine(today, datetime.strptime("11:00", "%H:%M").time())
    
    # Booking available hai ya nahi
    ac_available = now >= ac_open_time and ac_window
    non_ac_available = now >= non_ac_open_time and non_ac_window
    
    return {
        "today": today.strftime("%d-%m-%Y"),
        "tomorrow": tomorrow.strftime("%d-%m-%Y"),
        "is_sunday": is_sunday,
        "ac": {
            "opens_at": ac_open_time.strftime("%I:%M %p"),
            "opens_date": tomorrow.strftime("%d-%m-%Y"),
            "time_remaining": str(ac_remaining).split(".")[0] if ac_remaining.total_seconds() > 0 else "OPEN NOW",
            "available": ac_available,
            "window_close": ac_window_close.strftime("%I:%M %p")
        },
        "non_ac": {
            "opens_at": non_ac_open_time.strftime("%I:%M %p"),
            "opens_date": tomorrow.strftime("%d-%m-%Y"),
            "time_remaining": str(non_ac_remaining).split(".")[0] if non_ac_remaining.total_seconds() > 0 else "OPEN NOW", 
            "available": non_ac_available,
            "window_close": non_ac_window_close.strftime("%I:%M %p")
        },
        "current_time": now.strftime("%I:%M:%S %p"),
        "booking_date": tomorrow.strftime("%d-%m-%Y")
    }

def get_tatkal_status_message(class_type: str = None) -> str:
    """Tatkal status ke hisaab se message generate karega"""
    timing = get_tatkal_timing_auto()
    
    if timing["is_sunday"]:
        return (
            "⚠️ *Today is SUNDAY*\n\n"
            "IRCTC Sunday ko kuch trains ke liye Tatkal booking nahi karti.\n"
            "Kal (Monday) se try karein."
        )
    
    msg = (
        f"⏰ *AUTO TATKAL TIMING*\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"📅 *Today:* {timing['today']}\n"
        f"📅 *Booking For:* {timing['tomorrow']}\n"
        f"🕐 *Current Time:* {timing['current_time']}\n\n"
    )
    
    # AC Tatkal
    ac = timing["ac"]
    ac_status = "✅ *OPEN NOW*" if ac["available"] else "❌ *Closed*" 
    msg += (
        f"🟦 *AC Tatkal* (1A, 2A, 3A, CC)\n"
        f"   Opens: {ac['opens_at']} on {ac['opens_date']}\n"
        f"   Window: 10:00 AM - 11:00 AM\n"
        f"   Status: {ac_status}\n"
        f"   Time Left: `{ac['time_remaining']}`\n\n"
    )
    
    # Non-AC Tatkal
    non_ac = timing["non_ac"]
    non_ac_status = "✅ *OPEN NOW*" if non_ac["available"] else "❌ *Closed*"
    msg += (
        f"🟩 *Non-AC Tatkal* (SL, 2S)\n"
        f"   Opens: {non_ac['opens_at']} on {non_ac['opens_date']}\n"
        f"   Window: 11:00 AM - 12:00 PM\n"
        f"   Status: {non_ac_status}\n"
        f"   Time Left: `{non_ac['time_remaining']}`\n\n"
    )
    
    if ac["available"] or non_ac["available"]:
        msg += "⚡ *Tatkal window is OPEN!* Jaldi booking karein!"
    else:
        msg += "💡 *Tip:* Exactly time pe ready rahein! Tatkal jaldi book hota hai!"
    
    return msg

# ===================== Auto Schedule Check =====================

def should_attempt_booking(class_type: str) -> bool:
    """Check karega ki abhi booking attempt karna chahiye ya nahi"""
    timing = get_tatkal_timing_auto()
    
    if timing["is_sunday"]:
        return False
    
    if class_type in ["1A", "2A", "3A", "CC"]:
        return timing["ac"]["available"]
    else:
        return timing["non_ac"]["available"]

def get_next_booking_time(class_type: str) -> str:
    """Agli baar booking kab try karega, wo batayega"""
    timing = get_tatkal_timing_auto()
    
    if class_type in ["1A", "2A", "3A", "CC"]:
        if timing["ac"]["time_remaining"] == "OPEN NOW":
            return "NOW"
        return timing["ac"]["opens_at"] + " " + timing["ac"]["opens_date"]
    else:
        if timing["non_ac"]["time_remaining"] == "OPEN NOW":
            return "NOW"
        return timing["non_ac"]["opens_at"] + " " + timing["non_ac"]["opens_date"]

# ===================== UPI Payment Link Generator =====================

def generate_upi_payment_link(amount: int, payee_vpa: str, 
                              payee_name: str = "TatkalBot",
                              transaction_note: str = "Tatkal Ticket Booking",
                              transaction_ref: str = None) -> str:
    """
    UPI deep link generate karega jo directly UPI app khol dega
    """
    if transaction_ref is None:
        transaction_ref = f"TKT{datetime.now().strftime('%y%m%d%H%M%S')}"
    
    # UPI URI format
    params = {
        "pa": payee_vpa,           # Payee VPA
        "pn": payee_name,          # Payee Name
        "am": str(amount),         # Amount
        "tn": transaction_note,    # Transaction Note
        "tr": transaction_ref,     # Transaction Reference
        "cu": "INR"                # Currency
    }
    
    query_string = urllib.parse.urlencode(params)
    upi_link = f"upi://pay?{query_string}"
    
    return upi_link, transaction_ref

async def send_upi_payment_notification(update: Update, context: ContextTypes.DEFAULT_TYPE,
                                        upi_id: str, amount: int, booking_data: dict):
    """
    UPI payment link bhejega. User jab pay karega, to UPI app notification aayega.
    """
    # Payment link generate karo
    upi_link, txn_ref = generate_upi_payment_link(
        amount=amount,
        payee_vpa=UPI_VPA,
        payee_name=PAYMENT_MERCHANT,
        transaction_note=f"Tatkal {booking_data['train_number']} {booking_data['journey_date']}",
        transaction_ref=txn_ref
    )
    
    # Payment record save karo
    payment_col.insert_one({
        "user_id": update.effective_chat.id,
        "transaction_ref": txn_ref,
        "amount": amount,
        "upi_id": upi_id,
        "status": "pending",
        "booking_data_id": str(booking_data.get("_id", "")),
        "created_at": datetime.now()
    })
    
    # UPI Pay button ke saath message
    keyboard = [
        [InlineKeyboardButton("💳 Pay via UPI", url=upi_link)],
        [InlineKeyboardButton("✅ Payment Done", callback_data=f"payment_done_{txn_ref}")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    msg = (
        f"💳 *UPI Payment Required*\n\n"
        f"💰 *Amount:* ₹{amount}\n"
        f"💳 *Pay To:* `{UPI_VPA}`\n"
        f"🆔 *Ref:* `{txn_ref}`\n\n"
        f"👇 *UPI Pay button dabaye* - aapka UPI app automatically open ho jayega\n\n"
        f"⚠️ *Payment karne ke baad* '✅ Payment Done' button dabaye!\n\n"
        f"🔄 *Ya phir manually UPI app me pay karein:*\n"
        f"   UPI ID: `{UPI_VPA}`\n"
        f"   Amount: ₹{amount}\n"
        f"   Ref: `{txn_ref}`"
    )
    
    return await update.message.reply_text(
        msg,
        parse_mode="Markdown",
        reply_markup=reply_markup
    )

async def payment_done_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Jab user 'Payment Done' button dabayega"""
    query = update.callback_query
    await query.answer()
    
    # Txn ref extract karo
    txn_ref = query.data.replace("payment_done_", "")
    
    # Payment record update karo
    payment_col.update_one(
        {"transaction_ref": txn_ref},
        {"$set": {
            "status": "paid_by_user",
            "paid_at": datetime.now()
        }}
    )
    
    await query.edit_message_text(
        text=(
            "✅ *Payment Confirmed!*\n\n"
            "🔄 Aapka payment record save ho gaya hai.\n"
            "IRCTC booking process start ho raha hai...\n\n"
            "⏳ *Please wait...*"
        ),
        parse_mode="Markdown"
    )
    
    # Yahan actual IRCTC API call hogi
    await asyncio.sleep(2)
    
    await query.message.reply_text(
        "🎉 *Booking Confirmed!*\n\n"
        "Aapki Tatkal ticket book ho gayi!\n"
        "Details check karne ke liye /bookings use karein.",
        parse_mode="Markdown",
        reply_markup=get_main_keyboard()
    )

# ===================== UI Components =====================

def get_main_keyboard():
    keyboard = [
        [KeyboardButton("🚂 Auto Book Tatkal"), KeyboardButton("📋 My Bookings")],
        [KeyboardButton("⏰ Tatkal Status"), KeyboardButton("🔔 Set Auto Book")],
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
    """IRCTC se train info fetch karega"""
    # Simulated data - actual IRCTC API se replace karein
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
    }
    cls = class_type.upper()
    if cls in charges:
        base = charges[cls]["base"]
        gst = charges[cls]["gst"]
        total = base + gst
        return {"base_charge": base, "gst": gst, "total_charge": total, "description": charges[cls]["description"]}
    return {"base_charge": 0, "gst": 0, "total_charge": 0, "description": "Unknown"}

def calculate_total_amount(class_type: str, passenger_count: int) -> dict:
    """Total amount calculate karega with all charges"""
    charges = calculate_tatkal_charges(class_type)
    
    base_fare_per = 50  # IRCTC base fare
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

# ===================== Command Handlers =====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat_id = update.effective_chat.id
    
    # User ko DB me save karo
    users_col.update_one(
        {"user_id": chat_id},
        {"$set": {
            "username": user.username,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "last_active": datetime.now()
        }},
        upsert=True
    )
    
    # Auto tatkal status check karo
    timing = get_tatkal_timing_auto()
    
    welcome_msg = (
        f"🚂 *TATKAL AUTO BOOKING BOT* 🚂\n\n"
        f"Namaste {user.first_name}! 🙏\n\n"
        f"⚡ *Sab Automatic!* Aap bas train number daalo, baaki sab bot karega!\n\n"
        f"📅 *Today:* {timing['today']}\n"
        f"🕐 *Current Time:* {timing['current_time']}\n"
        f"📅 *Booking For:* {timing['tomorrow']}\n\n"
    )
    
    if timing["ac"]["available"] or timing["non_ac"]["available"]:
        welcome_msg += "🔥 *TATKAL WINDOW OPEN HAI!* Jaldi karein!\n\n"
    else:
        if not timing["is_sunday"]:
            welcome_msg += f"⏰ *AC Tatkal:* {timing['ac']['opens_at']}, *Non-AC:* {timing['non_ac']['opens_at']}\n\n"
    
    welcome_msg += (
        f"✅ *Features:*\n"
        f"   🔄 Auto timing calculation\n"
        f"   💳 UPI auto payment link\n"
        f"   📋 Booking history\n"
        f"   🔔 Auto-book reminder\n\n"
        f"👇 *Start karein:*"
    )
    
    await update.message.reply_text(
        welcome_msg,
        parse_mode="Markdown",
        reply_markup=get_main_keyboard()
    )

async def tatkal_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Real-time Tatkal status dikhaye"""
    status_msg = get_tatkal_status_message()
    await update.message.reply_text(status_msg, parse_mode="Markdown", reply_markup=get_main_keyboard())

async def my_bookings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """User ki saari bookings dikhaye"""
    chat_id = update.effective_chat.id
    bookings = list(bookings_col.find({"user_id": chat_id}).sort("created_at", -1).limit(15))
    
    if not bookings:
        await update.message.reply_text(
            "❌ *No Bookings Found*\n\nAapne koi booking nahi kari hai abhi tak.",
            parse_mode="Markdown",
            reply_markup=get_main_keyboard()
        )
        return
    
    msg = f"📋 *Your Bookings ({len(bookings)})*\n\n"
    for idx, b in enumerate(bookings, 1):
        status_icon = "✅" if b.get("status") == "Confirmed" else "⏳"
        pay_icon = "💰" if b.get("payment_status") == "Paid" else "💳"
        
        msg += (
            f"{idx}. {status_icon} *{b.get('train_number')}* - {b.get('train_name', 'N/A')[:30]}...\n"
            f"   📅 {b.get('journey_date')} | 🛏️ {b.get('class_type')}\n"
            f"   👥 {len(b.get('passengers', []))} passengers\n"
            f"   {pay_icon} ₹{b.get('total_amount', 0)} | {b.get('status', 'N/A')}\n"
            f"   🆔 `{str(b['_id'])[:10]}`\n\n"
        )
    
    await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=get_main_keyboard())

async def set_auto_book(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Auto-book feature set karein"""
    await update.message.reply_text(
        "🔔 *Auto Book Feature*\n\n"
        "Ye feature aapko *Tatkal khulte hi* notify karega!\n\n"
        "Abhi ke liye manual booking karein.\n\n"
        "Auto-book Pro version me available hai.",
        parse_mode="Markdown",
        reply_markup=get_main_keyboard()
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "📖 *Tatkal Auto Bot Guide*\n\n"
        "🚂 *Auto Book Tatkal*\n"
        "• 'Auto Book Tatkal' button dabaye\n"
        "• Sirf train number daalein (5 digit)\n"
        "• Bot automatically: date, class, quota puchhega\n"
        "• Passengers add karein\n"
        "• UPI payment link aayega - pay karein\n"
        "• 'Payment Done' button dabaye\n\n"
        "⏰ *Auto Timings*\n"
        "• AC Tatkal: 10:00 AM (1 din pehle)\n"
        "• Non-AC Tatkal: 11:00 AM (1 din pehle)\n"
        "• Bot automatically timing calculate karega\n\n"
        "💳 *UPI Payment*\n"
        "• Bot UPI link generate karega\n"
        "• Button dabate hi UPI app open ho jayega\n"
        "• Pay karne ke baad 'Payment Done' dabaye\n\n"
        "❓ *Koi problem?*\n"
        "/start se dubara try karein"
    )
    await update.message.reply_text(help_text, parse_mode="Markdown", reply_markup=get_main_keyboard())

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "❌ *Cancelled*\n\nBooking process cancel kar diya gaya.",
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
    """Step 1: Start booking"""
    context.user_data.clear()
    context.user_data["passengers"] = []
    
    # Auto timing check
    timing = get_tatkal_timing_auto()
    
    msg = (
        f"🚂 *AUTO TATKAL BOOKING*\n\n"
        f"📅 *Booking For:* {timing['booking_date']}\n\n"
        f"*Step 1: Train Number*\n\n"
        f"Apni train ka *5 digit number* dalein.\n\n"
        f"उदाहरण: `12301`, `12431`, `12001`"
    )
    
    await update.message.reply_text(
        msg,
        parse_mode="Markdown",
        reply_markup=get_cancel_keyboard()
    )
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
        f"📅 *Step 2: Journey Date*\n\n"
        f"Date dalein (DD-MM-YYYY):\n"
        f"Default: `{get_tatkal_timing_auto()['booking_date']}`",
        parse_mode="Markdown",
        reply_markup=get_cancel_keyboard()
    )
    return JOURNEY_DATE

async def receive_journey_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    
    if text == "❌ Cancel Booking":
        return await cancel(update, context)
    
    try:
        # Default date: tomorrow
        default_date = get_tatkal_timing_auto()["booking_date"]
        
        if text.lower() == "default" or text == "":
            text = default_date
        
        journey_date = datetime.strptime(text, "%d-%m-%Y")
        today = datetime.now()
        
        if journey_date < today.replace(hour=0, minute=0, second=0, microsecond=0):
            await update.message.reply_text(
                "❌ *Past date!* Aaj ya kal ki date dalein.",
                parse_mode="Markdown"
            )
            return JOURNEY_DATE
        
        max_date = today + timedelta(days=120)
        if journey_date > max_date:
            await update.message.reply_text(
                "❌ *Max 120 days ahead!*",
                parse_mode="Markdown"
            )
            return JOURNEY_DATE
        
        user_data = context.user_data
        user_data["journey_date"] = text
        
        await update.message.reply_text(
            f"✅ Date: *{text}*\n\n"
            f"🛏️ *Step 3: Select Class*\n\n"
            f"Kripya class chune:",
            parse_mode="Markdown",
            reply_markup=get_class_keyboard()
        )
        return CLASS_TYPE
        
    except ValueError:
        await update.message.reply_text(
            "❌ *Invalid format!* `DD-MM-YYYY` use karein\n"
            "Example: `25-12-2024`\n"
            "Default ke liye `default` likhein",
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
        "1A": "AC 1 Tier (1A)", "CC": "Chair Car (CC)", "2S": "Second Sitting (2S)"
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
            f"Format me details bhejein:\n\n"
            f"`Name, Age, Gender`\n\n"
            f"Example:\n"
            f"`Rahul Kumar, 28, Male`\n\n"
            f"*Ek baar mein ek passenger*\n"
            f"Multiple passengers ke liye baad mein puchhunga."
        ),
        parse_mode="Markdown"
    )
    return PASSENGER_DETAILS

async def receive_passenger_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    
    if text == "❌ Cancel Booking":
        return await cancel(update, context)
    
    try:
        # Parse: "Name, Age, Gender"
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
        
        # Normalize gender
        gender_map = {"M": "Male", "F": "Female", "O": "Other"}
        if gender in gender_map:
            gender = gender_map[gender]
        
        passenger = {"name": name, "age": age, "gender": gender}
        
        user_data = context.user_data
        user_data["passengers"].append(passenger)
        
        # Ask for more passengers
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
        f"Example: `user@paytm`, `name@ybl`, `user@upi`\n\n"
        f"*Is UPI ID se payment hogi*",
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
    
    # Show full summary
    passengers = user_data["passengers"]
    total = len(passengers)
    class_type = user_data["class_type"]
    charges = calculate_tatkal_charges(class_type)
    total_amount_detailed = calculate_total_amount(class_type, total)
    
    msg = (
        f"📄 *BOOKING SUMMARY - Final Check*\n\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🚂 *{user_data['train_number']}* - {user_data['train_name']}\n"
        f"🚉 {user_data['source']} → {user_data['dest']}\n"
        f"📅 *Date:* {user_data['journey_date']}\n"
        f"🛏️ *Class:* {class_type} | 📋 *Quota:* {user_data['quota']}\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"👥 *Passengers ({total}):*\n"
    )
    
    for i, p in enumerate(passengers, 1):
        msg += f"   {i}. {p['name']} ({p['age']} yrs, {p['gender']})\n"
    
    msg += (
        f"\n📱 *Mobile:* {user_data['mobile']}\n"
        f"💳 *UPI:* {user_data['upi_id']}\n\n"
        f"💰 *Payment Details:*\n"
        f"   Base Fare: ₹{total_amount_detailed['base_fare']}\n"
        f"   Tatkal Charges: ₹{total_amount_detailed['tatkal_charge']}\n"
        f"   GST: ₹{total_amount_detailed['gst']}\n"
        f"   ─────────────────────\n"
        f"   *Total: ₹{total_amount_detailed['grand_total']}*\n\n"
        f"✅ *Confirm booking?*"
    )
    
    await update.message.reply_text(
        msg,
        parse_mode="Markdown",
        reply_markup=get_confirm_keyboard()
    )
    return CONFIRM_BOOKING

async def confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "cancel":
        return await callback_cancel(update, context)
    
    user_data = context.user_data
    chat_id = update.effective_chat.id
    
    # Booking record create karo
    passengers = user_data["passengers"]
    total_passengers = len(passengers)
    total_amount = calculate_total_amount(user_data["class_type"], total_passengers)["grand_total"]
    
    booking_data = {
        "user_id": chat_id,
        "train_number": user_data["train_number"],
        "train_name": user_data.get("train_name", ""),
        "source": user_data.get("source", ""),
        "dest": user_data.get("dest", ""),
        "journey_date": user_data["journey_date"],
        "class_type": user_data["class_type"],
        "quota": user_data["quota"],
        "passengers": user_data["passengers"],
        "mobile": user_data["mobile"],
        "upi_id": user_data["upi_id"],
        "total_amount": total_amount,
        "status": "Payment Pending",
        "payment_status": "Pending",
        "created_at": datetime.now(),
        "updated_at": datetime.now()
    }
    
    result = bookings_col.insert_one(booking_data)
    booking_data["_id"] = result.inserted_id
    
    # UPI payment notification bhejo
    await query.edit_message_text(
        text="⏳ *Generating payment link...*",
        parse_mode="Markdown"
    )
    
    # UPI Payment link ke saath message
    upi_link, txn_ref = generate_upi_payment_link(
        amount=total_amount,
        payee_vpa=UPI_VPA,
        payee_name=PAYMENT_MERCHANT,
        transaction_note=f"Tatkal {user_data['train_number']} {user_data['journey_date']}",
        transaction_ref=f"TKT{datetime.now().strftime('%y%m%d%H%M%S')}"
    )
    
    # Payment record
    payment_col.insert_one({
        "user_id": chat_id,
        "booking_id": str(booking_data["_id"]),
        "transaction_ref": txn_ref,
        "amount": total_amount,
        "upi_id": user_data["upi_id"],
        "payee_vpa": UPI_VPA,
        "status": "pending",
        "created_at": datetime.now()
    })
    
    keyboard = [
        [InlineKeyboardButton("💳 Pay ₹" + str(total_amount) + " via UPI", url=upi_link)],
        [InlineKeyboardButton("✅ Payment Done", callback_data=f"pd_{txn_ref}")],
        [InlineKeyboardButton("❌ Cancel Booking", callback_data="cancel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        text=(
            f"💳 *PAYMENT REQUIRED*\n\n"
            f"💰 *Amount:* ₹{total_amount}\n"
            f"💳 *Pay To:* `{UPI_VPA}`\n"
            f"🆔 *Ref:* `{txn_ref}`\n\n"
            f"👇 *'Pay via UPI' button dabaye*\n"
            f"→ Aapka UPI app automatically open ho jayega\n\n"
            f"✅ *Pay karne ke baad* 'Payment Done' dabaye\n\n"
            f"🔄 *Manual payment:*\n"
            f"   UPI: `{UPI_VPA}`\n"
            f"   Amount: ₹{total_amount}\n"
            f"   Ref: `{txn_ref}`"
        ),
        parse_mode="Markdown",
        reply_markup=reply_markup
    )
    
    return CONFIRM_BOOKING

async def payment_done_callback_final(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Payment done callback"""
    query = update.callback_query
    await query.answer()
    
    txn_ref = query.data.replace("pd_", "")
    
    # Update payment status
    payment_col.update_one(
        {"transaction_ref": txn_ref},
        {"$set": {"status": "paid", "paid_at": datetime.now()}}
    )
    
    # Update booking status
    payment = payment_col.find_one({"transaction_ref": txn_ref})
    if payment:
        bookings_col.update_one(
            {"_id": ObjectId(payment["booking_id"])},
            {"$set": {"status": "Confirmed", "payment_status": "Paid", "updated_at": datetime.now()}}
        )
    
    await query.edit_message_text(
        text="✅ *PAYMENT RECEIVED!*\n\n🔄 Booking confirmation in progress...",
        parse_mode="Markdown"
    )
    
    await asyncio.sleep(1.5)
    
    await query.edit_message_text(
        text=(
            "🎉✅ *TICKET BOOKED SUCCESSFULLY!*\n\n"
            f"🆔 *Booking ID:* `{txn_ref}`\n\n"
            f"🚂 *Train booked!*\n"
            f"💰 *Paid:* ✅\n"
            f"📊 *Status:* CONFIRMED\n\n"
            f"📋 /bookings se details check karein"
        ),
        parse_mode="Markdown"
    )
    
    await query.message.reply_text(
        "👇 *Aur kya help chahiye?*",
        reply_markup=get_main_keyboard()
    )
    
    context.user_data.clear()
    return ConversationHandler.END

# ===================== Message Router =====================

async def message_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    
    routes = {
        "🚂 Auto Book Tatkal": book_tatkal,
        "📋 My Bookings": my_bookings,
        "⏰ Tatkal Status": tatkal_status,
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
    
    # Conversation Handler
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
        name="auto_booking",
        per_user=True,
        per_chat=True
    )
    
    # Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("bookings", my_bookings))
    app.add_handler(CommandHandler("status", tatkal_status))
    app.add_handler(conv_handler)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_router))
    app.add_error_handler(error_handler)
    
    print("🚂 Tatkal Auto Bot Running...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()