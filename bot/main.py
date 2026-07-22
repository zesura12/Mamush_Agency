import logging
import asyncio
import os
from aiohttp import web
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

logging.basicConfig(level=logging.INFO)

# --- ውቅር ---
API_TOKEN    = os.environ.get("TELEGRAM_BOT_TOKEN")
ADMIN_ID     = int(os.environ.get("ADMIN_ID", "0"))
WEBHOOK_URL  = os.environ.get("WEBHOOK_URL", "")
WEBHOOK_PATH = "/bot/webhook"
PORT         = int(os.environ.get("PORT", 8000))

if not API_TOKEN:
    raise RuntimeError("❌ TELEGRAM_BOT_TOKEN አልተቀናጀም።")
if not ADMIN_ID:
    raise RuntimeError("❌ ADMIN_ID አልተቀናጀም።")

bot = Bot(token=API_TOKEN)
dp  = Dispatcher(storage=MemoryStorage())


# --- FSM States ---
class OrderState(StatesGroup):
    waiting_for_item_description = State()
    waiting_for_contact          = State()

class FeedbackState(StatesGroup):
    waiting_for_rating  = State()
    waiting_for_comment = State()


# ─── ዋና አገልግሎቶች ───────────────────────────────────────────────────────────────
MAIN_SERVICES = {
    "maintenance": "🛠 የመብራት እና ቧንቧ ጥገና",
    "workers":     "👷‍♂️ ግንባታ፣ ቀለም እና ጂብሰም",
    "cleaning":    "🧹 የቤት እና ቢሮ ፅዳት",
    "moving":      "🚚 እቃዎችን ማዘዋወር",
    "sourcing":    "📦 እቃዎችን በትእዛዝ ማምጣት",
}

# ─── ንዑስ አገልግሎቶች ───────────────────────────────────────────────────────────────
SUB_SERVICES = {
    # ── 1. ጥገና ──
    "maintenance_electric": (
        "⚡️ የመብራት ጥገና",
        "⚡️ <b>የመብራት ጥገና</b>\n\n"
        "የቤትዎ ወይም ቢሮዎ የኤሌክትሪክ ብልሽቶችን፣ ቋቋም ያጡ ሶኬቶችን፣ "
        "ሽቦ ዝርጋታ እና ሌሎች ችግሮችን በሰለጠኑ ባለሞያዎች ፈጥነን እናስተካክላለን።"
    ),
    "maintenance_plumbing": (
        "🔧 የቧንቧ እና ፍሳሽ ጥገና",
        "🔧 <b>የቧንቧ እና ፍሳሽ ጥገና</b>\n\n"
        "የቧንቧ ብልሽት፣ ፍሳሽ መብዛት፣ ቁሳቁስ መሰካት እና ሌሎች "
        "ችግሮችን በሰለጠኑ ባለሞያዎች ፈጥነን እናስተካክላለን።"
    ),

    # ── 2. ሰራተኞች ──
    "workers_mason": (
        "🧱 ግንበኛ",
        "🧱 <b>ግንበኛ</b>\n\n"
        "ለማናቸውም የግንባታ ስራዎች — ቤት ማቆም፣ ግድግዳ ማስፋት፣ "
        "ድልድይ — ብቁ ግንበኞችን ቶሎ እናቀርባለን።"
    ),
    "workers_painter": (
        "🎨 ቀለም ቀቢ",
        "🎨 <b>ቀለም ቀቢ</b>\n\n"
        "ለቤት ወይም ቢሮ ቀለም ቅብ ስራ፣ ውሃ-ቀለም፣ ኦይል-ቀለም — "
        "ጥራቱን የጠበቀ ስራ የሚሰሩ ባለሞያዎችን እናቀርባለን።"
    ),
    "workers_gypsum": (
        "🏗 ጂብሰም ባለሞያ",
        "🏗 <b>ጂብሰም ባለሞያ</b>\n\n"
        "ለጂብሰም ጣሪያ፣ ክፍፍል ግድግዳ እና ማስዋቢያ ስራዎች "
        "ሙሉ ልምድ ያላቸውን ባለሞያዎች እናቀርባለን።"
    ),
    "workers_carpenter": (
        "🪚 አናጢ",
        "🪚 <b>አናጢ</b>\n\n"
        "ለበር፣ ለመስኮት፣ ለቁም ሳጥን እና ለሌሎች "
        "የእንጨት ስራዎች ብቁ አናጢዎችን እናቀርባለን።"
    ),

    # ── 3. ፅዳት ──
    "cleaning_home": (
        "🏠 የቤት ፅዳት",
        "🏠 <b>የቤት ፅዳት</b>\n\n"
        "ዘመናዊ የፅዳት መሳሪያዎችን እና ምርቶችን በመጠቀም "
        "የቤትዎን ሙሉ ፅዳት — ወለል፣ መስኮት፣ ኩሽና — "
        "በጥራት እናከናውናለን።"
    ),
    "cleaning_office": (
        "🏢 የቢሮ ፅዳት",
        "🏢 <b>የቢሮ ፅዳት</b>\n\n"
        "ዘመናዊ የፅዳት መሳሪያዎችን እና ምርቶችን በመጠቀም "
        "የቢሮዎን ሙሉ ፅዳት — ወለል፣ ዴስክ፣ መጸዳጃ ቤት — "
        "በጥራት እናከናውናለን።"
    ),

    # ── 4. ማዘዋወር ──
    "moving_home": (
        "🏠 የቤት እቃዎች ማዘዋወር",
        "🏠 <b>የቤት እቃዎች ማዘዋወር</b>\n\n"
        "የቤትዎን ሶፋ፣ አልጋ፣ ቁም ሳጥን እና ሌሎች እቃዎች "
        "ያለምንም ጉዳት በጥንቃቄ ከአንድ ቦታ ወደ ሌላ ቦታ "
        "እናጓጉዛለን።"
    ),
    "moving_office": (
        "🏢 የቢሮ እቃዎች ማዘዋወር",
        "🏢 <b>የቢሮ እቃዎች ማዘዋወር</b>\n\n"
        "የቢሮዎን ኮምፒዩተር፣ ዴስክ፣ ካቢኔ እና ሌሎች እቃዎች "
        "ያለምንም ጉዳት በጥንቃቄ ከአንድ ቦታ ወደ ሌላ ቦታ "
        "እናጓጉዛለን።"
    ),

    # ── 5. ምርቶች (sourcing) ──
    "sourcing_home": (
        "🛋 የቤት ውስጥ እቃዎች",
        "🛋 <b>የቤት ውስጥ እቃዎች</b>\n\n"
        "ሶፋ፣ አልጋ፣ ጠረጴዛ ወይም ሌሎች የቤት እቃዎች — "
        "ምን እቃ እንዲያመጣሉ ይፈልጋሉ?"
    ),
    "sourcing_office": (
        "💼 የቢሮ እቃዎች",
        "💼 <b>የቢሮ እቃዎች</b>\n\n"
        "ዴስክ፣ ወንበር፣ ፋይሊንግ ካቢኔ ወይም ሌሎች የቢሮ እቃዎች — "
        "ምን እቃ እንዲያመጣሉ ይፈልጋሉ?"
    ),
    "sourcing_other": (
        "📦 ሌሎች እቃዎች",
        "📦 <b>ሌሎች እቃዎች</b>\n\n"
        "ማናቸውንም ሌሎች እቃዎች — "
        "ምን እቃ እንዲያመጣሉ ይፈልጋሉ?"
    ),
}

# ዋና → ንዑስ ቁልፎች ካርታ
MAIN_TO_SUB = {
    "maintenance": ["maintenance_electric", "maintenance_plumbing"],
    "workers":     ["workers_mason", "workers_painter", "workers_gypsum", "workers_carpenter"],
    "cleaning":    ["cleaning_home", "cleaning_office"],
    "moving":      ["moving_home", "moving_office"],
    "sourcing":    ["sourcing_home", "sourcing_office", "sourcing_other"],
}

STAR_MAP = {"1": "⭐️", "2": "⭐️⭐️", "3": "⭐️⭐️⭐️", "4": "⭐️⭐️⭐️⭐️", "5": "⭐️⭐️⭐️⭐️⭐️"}


# ── ረዳት: ዋና ምናሌ ──────────────────────────────────────────────────────────────
def ዋና_ምናሌ() -> InlineKeyboardMarkup:
    kb = [
        [InlineKeyboardButton(text=label, callback_data=f"serv_{key}")]
        for key, label in MAIN_SERVICES.items()
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

# ── ረዳት: ንዑስ ምናሌ ─────────────────────────────────────────────────────────────
def ንዑስ_ምናሌ(main_key: str) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=SUB_SERVICES[sub][0], callback_data=f"sub_{sub}")]
        for sub in MAIN_TO_SUB[main_key]
    ]
    rows.append([InlineKeyboardButton(text="🔙 ወደ ኋላ ተመለስ", callback_data="back_home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

# ── ረዳት: የደረጃ ምናሌ ────────────────────────────────────────────────────────────
def የደረጃ_ምናሌ() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="1 ⭐️", callback_data="rate_1"),
        InlineKeyboardButton(text="2 ⭐️", callback_data="rate_2"),
        InlineKeyboardButton(text="3 ⭐️", callback_data="rate_3"),
        InlineKeyboardButton(text="4 ⭐️", callback_data="rate_4"),
        InlineKeyboardButton(text="5 ⭐️", callback_data="rate_5"),
    ]])


# ─── /start ────────────────────────────────────────────────────────────────────
@dp.message(Command("start"))
async def ሰላምታ_ላክ(message: types.Message, state: FSMContext):
    await state.clear()
    ጽሁፍ = (
        "👋 ሰላም እንኳን ወደ <b>ማሙሽ Multi-Service Agency</b> በደህና መጡ‼️\n\n"
        "ይህ ድርጅት በከተማችን የሚፈጠረውን የስራ መስተጓጎል፣ የሞያ እና "
        "የባለሞያ ብቁ አለመሆንን እንዲሁም አለመታመንን በማስቀረት "
        "በሙሉ ተጠያቂነት ወደ ስራ የገባ ድርጅት ነው‼️\n\n"
        "እባክዎ ከታች ካሉት አማራጮች የሚፈልጉትን አገልግሎት ይምረጡ፦"
    )
    await message.answer(ጽሁፍ, reply_markup=ዋና_ምናሌ(), parse_mode="HTML")


# ─── /feedback ─────────────────────────────────────────────────────────────────
@dp.message(Command("feedback"))
async def ፍድባክ_ጀምር_ትእዛዝ(message: types.Message, state: FSMContext):
    await state.clear()
    await state.set_state(FeedbackState.waiting_for_rating)
    await message.answer(
        "🌟 <b>አስተያየት ይስጡ</b>\n\n"
        "ለአገልግሎታችን ምን ደረጃ ይሰጣሉ?",
        reply_markup=የደረጃ_ምናሌ(),
        parse_mode="HTML",
    )


# ─── ዋና አገልግሎት ሲነካ → ንዑስ ዝርዝር ──────────────────────────────────────────────
@dp.callback_query(F.data.startswith("serv_"))
async def ዋና_ምናሌ_ንካ(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    key   = callback.data[len("serv_"):]
    label = MAIN_SERVICES.get(key, "አገልግሎት")
    await callback.message.edit_text(
        f"<b>{label}</b>\n\nእባክዎ ዝርዝር አገልግሎት ይምረጡ፦",
        reply_markup=ንዑስ_ምናሌ(key),
        parse_mode="HTML",
    )


# ─── ንዑስ አገልግሎት ሲነካ → ዝርዝር + ትእዛዝ ቁልፍ ────────────────────────────────────
@dp.callback_query(F.data.startswith("sub_"))
async def ንዑስ_ምናሌ_ንካ(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    sub_key = callback.data[len("sub_"):]
    label, description = SUB_SERVICES.get(sub_key, ("—", "—"))
    main_key = sub_key.rsplit("_", 1)[0]
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ ትእዛዝ አስተላልፍ", callback_data=f"order_{sub_key}")],
        [InlineKeyboardButton(text="🔙 ወደ ኋላ ተመለስ",  callback_data=f"serv_{main_key}")],
    ])
    await callback.message.edit_text(description, reply_markup=kb, parse_mode="HTML")


# ─── ትእዛዝ: ሁሉም አገልግሎቶች ፍላጎት ይፃፉ ────────────────────────────────────────────
@dp.callback_query(F.data.startswith("order_"))
async def ትእዛዝ_ጀምር(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    sub_key = callback.data[len("order_"):]
    await state.update_data(selected_service=sub_key)
    await state.set_state(OrderState.waiting_for_item_description)

    if sub_key.startswith("sourcing_"):
        prompt = (
            "📝 <b>ምን እቃ እንዲያመጣሉ ይፈልጋሉ?</b>\n\n"
            "የሚፈልጉትን እቃ ዝርዝር (ስም፣ ቁጥር፣ ቀለም ወዘተ) ይፃፉ ⬇️"
        )
    else:
        label = SUB_SERVICES.get(sub_key, ("አገልግሎት",))[0]
        prompt = (
            f"📝 <b>ስለ {label} ፍላጎትዎ ይፃፉ</b>\n\n"
            "ዝርዝሩን (ቦታ፣ ስፋት፣ ልዩ ፍላጎት ወዘተ) ሲፅፉ ምላሽ ፈጣን ይሆናል ⬇️"
        )
    await callback.message.answer(prompt, parse_mode="HTML")


# ─── ፍላጎት ሲደርስ → ስልክ ጠይቅ ──────────────────────────────────────────────────
@dp.message(OrderState.waiting_for_item_description)
async def የእቃ_ዝርዝር_ተቀበል(message: types.Message, state: FSMContext):
    item_text = message.text or "—"
    await state.update_data(item_description=item_text)
    await state.set_state(OrderState.waiting_for_contact)

    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 ስልክ ቁጥሬን ላክ", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
    await message.answer(
        "✅ ምርጫዎ ተመዝግቧል!\n\n"
        "አሁን ደግሞ <b>'ስልክ ቁጥሬን ላክ'</b> ይጫኑ — ቶሎ እንደውልዎታለን።",
        reply_markup=kb,
        parse_mode="HTML",
    )


# ─── ስልክ ሲደርስ → Admin ላክ ────────────────────────────────────────────────────
@dp.message(OrderState.waiting_for_contact, F.contact)
async def ስልክ_ቁጥር_ተቀበል(message: types.Message, state: FSMContext):
    data      = await state.get_data()
    sub_key   = data.get("selected_service", "")
    label     = SUB_SERVICES.get(sub_key, ("❓ ያልታወቀ አገልግሎት",))[0]
    item_desc = data.get("item_description")

    user_id   = message.from_user.id
    phone     = message.contact.phone_number
    user_name = message.from_user.full_name
    username  = f"@{message.from_user.username}" if message.from_user.username else "—"

    await state.clear()

    # ምስጋና
    await message.answer(
        "✅ እናመሰግናለን‼️ ትእዛዝዎ ለ<b>ማሙሽ ኤጀንሲ</b> ደርሷል።\nበቅርቡ እንደውላለን። 🙏",
        reply_markup=types.ReplyKeyboardRemove(),
        parse_mode="HTML",
    )

    # ሌላ ትእዛዝ? + አስተያየት ቁልፍ
    kb_yn = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ አዎ", callback_data="another_yes"),
            InlineKeyboardButton(text="❌ አይ", callback_data="another_no"),
        ],
        [InlineKeyboardButton(text="🌟 አስተያየት ስጥ", callback_data="give_feedback")],
    ])
    await message.answer("🔄 ሌላ ትእዛዝ አለዎት?", reply_markup=kb_yn)

    # Admin ማሳወቂያ
    admin_msg = (
        f"🚨 <b>አዲስ ትእዛዝ!</b>\n\n"
        f"🛎 <b>አገልግሎት:</b> {label}\n"
    )
    if item_desc:
        admin_msg += f"📦 <b>ዝርዝር ፍላጎት:</b>\n{item_desc}\n"
    admin_msg += (
        f"👤 <b>ስም:</b> {user_name}\n"
        f"🔗 <b>Username:</b> {username}\n"
        f"📞 <b>ስልክ:</b> {phone}\n"
        f"{'─' * 20}"
    )
    admin_kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="📬 ስራ ሲያልቅ ደንበኛ አሳውቅ",
            callback_data=f"notify_{user_id}",
        )
    ]])
    await bot.send_message(ADMIN_ID, admin_msg, parse_mode="HTML", reply_markup=admin_kb)


# ─── state ውስጥ ሌላ message ──────────────────────────────────────────────────
@dp.message(OrderState.waiting_for_contact)
async def ስልክ_ቁጥር_ጠበቅ(message: types.Message):
    await message.answer(
        "📱 ስልክ ቁጥርዎን ለመላክ ከታች ያለውን <b>'ስልክ ቁጥሬን ላክ'</b> ቁልፍ ይጫኑ።",
        parse_mode="HTML",
    )


# ─── Admin: ደንበኛ አሳውቅ ────────────────────────────────────────────────────────
@dp.callback_query(F.data.startswith("notify_"))
async def admin_ደንበኛ_አሳውቅ(callback: types.CallbackQuery):
    await callback.answer("✅ ደንበኛ ተነገረ!")
    customer_id = int(callback.data[len("notify_"):])

    # ደንበኛ: ✅ / ❌ ምርጫ ይስጠው
    confirm_kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ አዎ ተሰርቷል",   callback_data=f"done_yes_{customer_id}"),
        InlineKeyboardButton(text="❌ አልተሰራም",     callback_data=f"done_no_{customer_id}"),
    ]])
    try:
        await bot.send_message(
            customer_id,
            "📬 <b>ማሙሽ ኤጀንሲ:</b>\n\nስራዎ ተጠናቅቋል ተብሎ ተነግሮናል።\n\n"
            "ስራው ለእርስዎ ተሰርቷልን?",
            reply_markup=confirm_kb,
            parse_mode="HTML",
        )
        # Admin ደንበኛ እንደተነገረ ያሳውቅ
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer("✅ ደንበኛ ተነግሯቸዋል — ምላሻቸውን ጠብቅ።")
    except Exception as e:
        await callback.message.answer(f"⚠️ ደንበኛ ማሳወቅ አልተቻለም: {e}")


# ─── ደንበኛ: ✅ ስራ ተሰርቷል ────────────────────────────────────────────────────────
@dp.callback_query(F.data.startswith("done_yes_"))
async def ደንበኛ_ተሰርቷል(callback: types.CallbackQuery):
    await callback.answer()
    customer_id = callback.data[len("done_yes_"):]
    await callback.message.edit_text(
        "✅ <b>እናመሰግናለን!</b> ደስ ብሎናል ስራዎ ተጠናቋል። 🙏\n\n"
        "ሌሎች አገልግሎቶች ለማዘዝ /start ይጫኑ።",
        parse_mode="HTML",
    )
    # Admin ማሳወቂያ
    await bot.send_message(
        ADMIN_ID,
        f"✅ <b>ደንበኛ አረጋግጧል:</b> ስራው ተሰርቷል ✔️\n(User ID: {customer_id})",
        parse_mode="HTML",
    )


# ─── ደንበኛ: ❌ ስራ አልተሰራም ──────────────────────────────────────────────────────
@dp.callback_query(F.data.startswith("done_no_"))
async def ደንበኛ_አልተሰራም(callback: types.CallbackQuery):
    await callback.answer()
    customer_id = callback.data[len("done_no_"):]
    await callback.message.edit_text(
        "❌ <b>ይቅርታ!</b> ስራዎ ባሚፈለጉት ደረጃ አልተሰራም ብለው ተናግረዋል።\n\n"
        "ኤጀንሲዎ ብቅ ብሎ ያስተካክልልዎታል — ወደፊት ይደዉሉልዎታል። 🙏",
        parse_mode="HTML",
    )
    # Admin ማሳወቂያ
    await bot.send_message(
        ADMIN_ID,
        f"❌ <b>ደንበኛ አምኗቸዋል:</b> ስራው አልተሰራም ✖️\n(User ID: {customer_id})\n\n"
        "⚠️ ደንበኛው ቅሬታ አለው — ወዲያው ደውልልህ!",
        parse_mode="HTML",
    )


# ─── ሌላ ትእዛዝ: አዎ ────────────────────────────────────────────────────────────
@dp.callback_query(F.data == "another_yes")
async def ሌላ_ትእዛዝ_አዎ(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    await callback.message.edit_text(
        "እባክዎ ሌላ የሚፈልጉትን አገልግሎት ይምረጡ፦",
        reply_markup=ዋና_ምናሌ(),
    )


# ─── ሌላ ትእዛዝ: አይ ────────────────────────────────────────────────────────────
@dp.callback_query(F.data == "another_no")
async def ሌላ_ትእዛዝ_አይ(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌟 አስተያየት ስጥ", callback_data="give_feedback")],
        [InlineKeyboardButton(text="🛒 ለማዘዝ", callback_data="back_home")],
    ])
    await callback.message.edit_text(
        "🙏 ለዛሬ ትእዛዝ እናመሰግናለን!\nቀጣይ ማዘዝ ሲፈልጉ እንደገና እንጠብቆታለን።",
        reply_markup=kb,
    )


# ─── አስተያየት ቁልፍ ─────────────────────────────────────────────────────────────
@dp.callback_query(F.data == "give_feedback")
async def ፍድባክ_ጀምር(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    await state.set_state(FeedbackState.waiting_for_rating)
    await callback.message.answer(
        "🌟 <b>አስተያየት ይስጡ</b>\n\n"
        "ለአገልግሎታችን ምን ደረጃ ይሰጣሉ?",
        reply_markup=የደረጃ_ምናሌ(),
        parse_mode="HTML",
    )


# ─── ደረጃ ሲደርስ → ሃሳብ ጠይቅ ──────────────────────────────────────────────────
@dp.callback_query(FeedbackState.waiting_for_rating, F.data.startswith("rate_"))
async def ደረጃ_ተቀበል(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    rating = callback.data[len("rate_"):]
    stars  = STAR_MAP.get(rating, rating)
    await state.update_data(rating=rating, stars=stars)
    await state.set_state(FeedbackState.waiting_for_comment)

    kb_skip = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="⏭️ ዝለሉ", callback_data="skip_comment"),
    ]])
    await callback.message.edit_text(
        f"<b>{stars}</b> ደረጃ ሰጥተዋል!\n\n"
        "💬 ሃሳብዎን ወይም ምክረ-ሃሳብዎን ይፃፉ "
        "(ወይም <b>ዝለሉ</b> ይጫኑ):",
        reply_markup=kb_skip,
        parse_mode="HTML",
    )


# ─── ሃሳብ ሲደርስ → Admin ላክ ──────────────────────────────────────────────────
@dp.message(FeedbackState.waiting_for_comment)
async def ሃሳብ_ተቀበልና_ላክ(message: types.Message, state: FSMContext):
    data    = await state.get_data()
    stars   = data.get("stars", "—")
    comment = message.text or "—"
    await _ፍድባክ_ወደ_admin(message.from_user, state, stars, comment)
    await message.answer(
        "✅ <b>አስተያየትዎ ተላከ!</b> ስለ ትብብርዎ እናመሰግናለን 🙏\n\n"
        "ሌሎች አገልግሎቶች ለማዘዝ ቁልፉን ይጫኑ 👇",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🛒 ወደ ምናሌ ተመለስ", callback_data="back_home")
        ]]),
        parse_mode="HTML",
    )


# ─── ዝለሉ (ሃሳብ ሳይፃፉ) ──────────────────────────────────────────────────────────
@dp.callback_query(FeedbackState.waiting_for_comment, F.data == "skip_comment")
async def ሃሳብ_ዝለሉ(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    data  = await state.get_data()
    stars = data.get("stars", "—")
    await _ፍድባክ_ወደ_admin(callback.from_user, state, stars, comment=None)
    await callback.message.edit_text(
        "✅ <b>አስተያየትዎ ተላከ!</b> ስለ ትብብርዎ እናመሰግናለን 🙏\n\n"
        "ሌሎች አገልግሎቶች ለማዘዝ ቁልፉን ይጫኑ 👇",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🛒 ወደ ምናሌ ተመለስ", callback_data="back_home")
        ]]),
        parse_mode="HTML",
    )


# ─── ረዳት: ፍድባክ Admin ላክ ────────────────────────────────────────────────────
async def _ፍድባክ_ወደ_admin(user, state: FSMContext, stars: str, comment):
    await state.clear()
    user_name = user.full_name
    username  = f"@{user.username}" if user.username else "—"
    msg = (
        f"💬 <b>አዲስ አስተያየት!</b>\n\n"
        f"⭐️ <b>ደረጃ:</b> {stars}\n"
        f"👤 <b>ስም:</b> {user_name}\n"
        f"🔗 <b>Username:</b> {username}\n"
    )
    if comment:
        msg += f"💬 <b>ሃሳብ:</b>\n{comment}\n"
    msg += f"{'─' * 20}"
    await bot.send_message(ADMIN_ID, msg, parse_mode="HTML")


# ─── ወደ ቤት ──────────────────────────────────────────────────────────────────
@dp.callback_query(F.data == "back_home")
async def ወደ_ቤት(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    ጽሁፍ = (
        "👋 ሰላም እንኳን ወደ <b>ማሙሽ Multi-Service Agency</b> በደህና መጡ‼️\n\n"
        "እባክዎ የሚፈልጉትን አገልግሎት ይምረጡ፦"
    )
    await callback.message.edit_text(ጽሁፍ, reply_markup=ዋና_ምናሌ(), parse_mode="HTML")


# ─── Fallback: ያልተጠበቀ message ────────────────────────────────────────────────
@dp.message()
async def ያልታወቀ_message(message: types.Message, state: FSMContext):
    current = await state.get_state()
    if current:
        return
    await message.answer(
        "👋 ትእዛዝ ለመስጠት /start ይጫኑ።",
        reply_markup=ዋና_ምናሌ(),
    )


# ─── Health check ─────────────────────────────────────────────────────────────
async def health(request):
    return web.Response(text="✅ ቦቱ እየሰራ ነው።")


# ─── Keep-alive: ቦቱ እንዳይተኛ (polling + webhook ሁለቱም ይሰራሉ) ──────────────────
async def keep_alive_loop():
    await asyncio.sleep(30)
    # Polling mode ውስጥ localhost ይጠቀማሉ፣ webhook ሲሆን ደሞ WEBHOOK_URL
    if WEBHOOK_URL:
        ping_url = f"{WEBHOOK_URL}/bot/health"
    else:
        ping_url = f"http://localhost:{PORT}/bot/health"

    import aiohttp as _aiohttp
    logging.info("Keep-alive ጀምሯል → %s", ping_url)
    while True:
        try:
            async with _aiohttp.ClientSession() as session:
                async with session.get(ping_url, timeout=_aiohttp.ClientTimeout(total=10)) as resp:
                    logging.info("Keep-alive ✅ status=%s", resp.status)
        except Exception as e:
            logging.warning("Keep-alive ping ሳይሳካ ቀረ: %s", e)
        await asyncio.sleep(60)


# ─── Startup / shutdown ───────────────────────────────────────────────────────
async def on_startup():
    try:
        await bot.set_my_commands([
            types.BotCommand(command="start",    description="ማሙሽ ኤጀንሲ ጀምር / አገልግሎቶቹን ይመልከቱ"),
            types.BotCommand(command="feedback", description="አስተያየት ይስጡ ⭐️"),
        ])
        await bot.set_my_description(
            "🏠 ማሙሽ Multi-Service Agency\n\n"
            "✅ የመብራት እና ቧንቧ ጥገና\n"
            "✅ ግንበኛ፣ ቀለም ቀቢ፣ ጂብሰም እና አናጢ\n"
            "✅ የቤት እና ቢሮ ፅዳት\n"
            "✅ እቃዎችን ማዘዋወር\n"
            "✅ እቃዎችን በትእዛዝ ማምጣት\n\n"
            "24/7 | ፈጣን ምላሽ | አስተማማኝ ባለሞያዎች\n\n"
            "ለማዘዝ /start ይጫኑ 👇"
        )
        await bot.set_my_short_description(
            "🏠 ማሙሽ ኤጀንሲ — ጥገና፣ ፅዳት፣ ማዘዋወር እና ሌሎች አገልግሎቶች | /start ይጫኑ"
        )
        logging.info("Bot profile ተቀናጅቷል ✅")
    except Exception as e:
        logging.warning("Bot profile setup ሳይሳካ ቀረ: %s", e)

    if WEBHOOK_URL:
        try:
            await bot.set_webhook(
                f"{WEBHOOK_URL}{WEBHOOK_PATH}",
                drop_pending_updates=True,
                allowed_updates=["message", "callback_query"],
            )
            logging.info("Webhook ተቀናጅቷል → %s%s", WEBHOOK_URL, WEBHOOK_PATH)
        except Exception as e:
            logging.error("Webhook setup አልተሳካም: %s", e)


async def on_shutdown():
    if WEBHOOK_URL:
        await bot.delete_webhook()
    await bot.session.close()


async def on_startup_keepalive():
    asyncio.create_task(keep_alive_loop())


dp.startup.register(on_startup)
dp.startup.register(on_startup_keepalive)
dp.shutdown.register(on_shutdown)


# ─── Main ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    logging.info("✅ ማሙሽ ቦት እየጀመረ ነው... (port=%s)", PORT)

    if WEBHOOK_URL:
        app = web.Application()
        app.router.add_get("/bot/health", health)
        SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=WEBHOOK_PATH)
        setup_application(app, dp, bot=bot)
        web.run_app(app, host="0.0.0.0", port=PORT)
    else:
        async def run_polling():
            app = web.Application()
            app.router.add_get("/bot/health", health)

            async def start_app(application):
                runner = web.AppRunner(application)
                await runner.setup()
                site = web.TCPSite(runner, "0.0.0.0", PORT)
                await site.start()

            await start_app(app)
            await dp.start_polling(bot, drop_pending_updates=True,
                                   allowed_updates=["message", "callback_query"])

        asyncio.run(run_polling())
