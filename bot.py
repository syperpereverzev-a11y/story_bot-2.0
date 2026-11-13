import os
import asyncio
import aiohttp
import urllib.parse
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, BufferedInputFile
from collections import defaultdict
from aiohttp import web

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENROUTER_KEY = os.getenv("OPENROUTER_KEY")

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()
history = defaultdict(list)

SYSTEM_PROMPT = "Ты — рассказчик и собеседник для взрослых (18+). Все персонажи строго старше 18 лет. Веди ролевые диалоги, описывай сцены подробно."

async def llm_reply(user_id, text):
    history[user_id].append({"role": "user", "content": text})
    if len(history[user_id]) > 20:
        history[user_id] = history[user_id][-20:]
    
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history[user_id]
    
    # Исправленная ссылка (без дублей)
    api_url = "https://openrouter.ai/api/v1/chat/completions"
    
    headers = {
        "Authorization": f"Bearer {OPENROUTER_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "meta-llama/llama-3.1-8b-instruct:free", 
        "messages": messages,
        "temperature": 0.9
    }
    
    async with aiohttp.ClientSession() as s:
        async with s.post(api_url, headers=headers, json=payload) as r:
            if r.status != 200:
                raise Exception(f"OpenRouter {r.status}: {await r.text()}")
            data = await r.json()
            reply = data["choices"][0]["message"]["content"]
            history[user_id].append({"role": "assistant", "content": reply})
            return reply

async def generate_image(prompt):
    encoded = urllib.parse.quote(prompt)
    img_url = f"https://image.pollinations.ai/prompt/{encoded}?width=1024&height=1024&nologo=true"
    async with aiohttp.ClientSession() as s:
        async with s.get(img_url, timeout=180) as r:
            if r.status != 200:
                raise Exception(f"Image {r.status}")
            return await r.read()

@dp.message(F.text)
async def handle(message: Message):
    text = message.text.strip()
    if not text:
        return
    if text.lower().startswith("/img"):
        prompt = text[4:].strip()
        if not prompt:
            await message.answer("Пример: /img девушка 25 лет, готический стиль")
            return
        await message.answer("🎨 Генерирую…")
        try:
            img = await generate_image(prompt)
            await message.answer_photo(BufferedInputFile(img, "image.png"), caption=prompt[:200])
        except Exception as e:
            await message.answer(f"Ошибка: {e}")
        return
    await message.answer("✍️ Думаю…")
    try:
        await message.answer(await llm_reply(message.from_user.id, text))
    except Exception as e:
        await message.answer(f"Ошибка: {e}")

async def health_check(request):
    return web.Response(text="Bot is alive!")

async def start_web_server():
    app = web.Application()
    app.router.add_get('/', health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()

async def main():
    print("Bot started")
    await start_web_server()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())