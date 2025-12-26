import asyncio
import time
import logging
from datetime import datetime
from curl_cffi.requests import AsyncSession
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

# ================= CONFIGURATION =================
BOT_TOKEN = "8540102385:AAEIgeQjvqTD-m1JMaJrYT5pVQCQr2BtLq4"
ADMIN_CHAT_ID = "7616065999"  # बटन रिस्पॉन्स के लिए भी इस्तेमाल होगा
CATEGORY_API = "https://www.sheinindia.in/api/category/sverse-5939-37961"
SIZE_API_PREFIX = "https://www.sheinindia.in/api/cart/sizeVariants/"

CHECK_INTERVAL = 3 
logging.basicConfig(level=logging.INFO)

# Global State
SEEN_PRODUCTS = set()
LAST_RESULT_COUNT = 0

# --- SHARED FUNCTIONS ---

async def fetch_product_details(session, pid):
    url = f"{SIZE_API_PREFIX}{pid}"
    try:
        resp = await session.get(url, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            name = data.get("name", "New Product")
            price = data.get("price", {}).get("displayformattedValue", "Price Hidden")
            img = data.get("images", [{}])[0].get("url")
            p_url = f"https://www.sheinindia.in{data.get('url', '')}"
            
            available_sizes = []
            options = data.get("baseOptions", [{}])[0].get("options", [])
            for opt in options:
                stock_lv = opt.get("stock", {}).get("stockLevel", 0)
                if stock_lv > 0:
                    for q in opt.get("variantOptionQualifiers", []):
                        if q['qualifier'] == "size":
                            available_sizes.append(f"{q['value']} ({stock_lv} left)")
            
            return {"id": pid, "name": name, "price": price, "img": img, "sizes": available_sizes, "link": p_url}
    except Exception: return None

async def send_alert(bot, product, is_manual=False):
    size_text = "\n".join([f"✅ {s}" for s in product['sizes']]) if product['sizes'] else "❌ Out of Stock"
    tag = "🔘 MANUAL CHECK" if is_manual else "🚨 NEW ARRIVAL"
    
    msg = (
        f"<b>{tag}</b>\n\n"
        f"📦 <b>Name:</b> {product['name']}\n"
        f"💰 <b>Price:</b> {product['price']}\n\n"
        f"<b>Sizes:</b>\n{size_text}\n\n"
        f"🆔 <code>{product['id']}</code>\n"
        f"🔗 <a href='{product['link']}'>Click to View</a>"
    )
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="🛒 BUY NOW", url=product['link']))
    
    if product['img']:
        await bot.send_photo(ADMIN_CHAT_ID, photo=product['img'], caption=msg, parse_mode="HTML", reply_markup=builder.as_markup())
    else:
        await bot.send_message(ADMIN_CHAT_ID, msg, parse_mode="HTML", reply_markup=builder.as_markup())

async def run_check(bot, session, is_manual=False):
    """यह फंक्शन ऑटो और मैन्युअल दोनों के लिए स्टॉक चेक करता है"""
    global LAST_RESULT_COUNT
    params = {"fields": "SITE", "pageSize": "45", "format": "json", "_": str(int(time.time()*1000))}
    resp = await session.get(CATEGORY_API, params=params)
    
    if resp.status_code == 200:
        data = resp.json()
        current_count = int(data['pagination']['totalResults'])
        products = data.get("products", [])
        
        # अगर स्टॉक में बदलाव है या मैन्युअल चेक है
        new_items = [p for p in products if p['code'] not in SEEN_PRODUCTS]
        
        if new_items:
            tasks = [fetch_product_details(session, p['code']) for p in new_items]
            detailed_products = await asyncio.gather(*tasks)
            for dp in detailed_products:
                if dp:
                    await send_alert(bot, dp, is_manual=False)
                    SEEN_PRODUCTS.add(dp['id'])
        
        LAST_RESULT_COUNT = current_count
        return current_count
    return None

# --- BOT HANDLERS ---

dp = Dispatcher()

@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="🔄 Check Stock Now", callback_data="manual_check"))
    await message.reply(
        "<b>Sheinverse High-Speed Monitor Bot</b>\n\n"
        "⚡ Status: <code>Running</code>\n"
        "🕒 Interval: <code>3 Seconds</code>\n\n"
        "आप नीचे दिए गए बटन से मैन्युअल चेक भी कर सकते हैं।",
        parse_mode="HTML",
        reply_markup=builder.as_markup()
    )

@dp.callback_query(F.data == "manual_check")
async def manual_check_handler(callback: types.Callback_Query, bot: Bot):
    await callback.answer("🔍 Checking Stock...")
    async with AsyncSession(impersonate="chrome110") as session:
        count = await run_check(bot, session, is_manual=True)
        now = datetime.now().strftime("%H:%M:%S")
        if count is not None:
            await callback.message.edit_text(
                f"✅ <b>Manual Check Complete</b>\n\n"
                f"📦 Total Products: <code>{count}</code>\n"
                f"🕒 Last Check: <code>{now}</code>\n\n"
                "अगर कोई नया प्रोडक्ट मिला होगा, तो ऊपर मैसेज आ गया होगा।",
                parse_mode="HTML",
                reply_markup=callback.message.reply_markup
            )

async def monitor_loop(bot: Bot):
    async with AsyncSession(impersonate="chrome110") as session:
        while True:
            await run_check(bot, session)
            await asyncio.sleep(CHECK_INTERVAL)

async def main():
    bot = Bot(token=BOT_TOKEN)
    # बैकग्राउंड लूप शुरू करें
    asyncio.create_task(monitor_loop(bot))
    # टेलीग्राम कमांड्स सुनना शुरू करें
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot stopped.")
