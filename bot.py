import os
import asyncio
import aiohttp
import urllib.parse
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, BufferedInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from collections import defaultdict
from aiohttp import web

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENROUTER_KEY = os.getenv("OPENROUTER_KEY")

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Хранилища
history = defaultdict(list)
characters = {} # Здесь будут храниться созданные персонажи

SYSTEM_PROMPT = (
    "Ты — рассказчик и ИИ-Система для взрослых (18+). Все персонажи строго старше 18 лет. "
    "Главный фокус твоих ответов — ДЕТАЛЬНАЯ ТРАНСФОРМАЦИЯ ТЕЛА. "
    "Описывай, как меняется кожа, плоть, органы, как выделяются жидкости, как трансформируются конечности. "
    "Используй максимально грязные, пошлые слова. Никакого кровного родства. "
    "Если пользователь дает тебе описание персонажа, строго следуй ему и описывай, как его тело меняется по воле пользователя."
)

# Машина состояний для создания персонажа
class CharacterCreation(StatesGroup):
    waiting_for_name = State()
    waiting_for_body = State()
    waiting_for_changes = State()

async def llm_reply(user_id, text):
    history[user_id].append({"role": "user", "content": text})
    if len(history[user_id]) > 20:
        history[user_id] = history[user_id][-20:]
    
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history[user_id]
    
    api_url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "arliai/qwq-32b-arliai-rpr-v1:free", 
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

# --- Создание персонажа ---
@dp.message(F.text == "/create")
async def start_creation(message: Message, state: FSMContext):
    await state.set_state(CharacterCreation.waiting_for_name)
    await message.answer("🧬 Добро пожаловать в Мастерскую Тела.\nШаг 1: Напиши имя твоего персонажа и кем она была до изменений (например: 'Анна, строгая секретарша').")

@dp.message(CharacterCreation.waiting_for_name)
async def process_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    await state.set_state(CharacterCreation.waiting_for_body)
    await message.answer("Шаг 2: Опиши её желаемый класс и базовые формы (например: 'Суккуб, огромная грудь, красная кожа, рога, хвост').")

@dp.message(CharacterCreation.waiting_for_body)
async def process_body(message: Message, state: FSMContext):
    await state.update_data(body=message.text)
    await state.set_state(CharacterCreation.waiting_for_changes)
    await message.answer("Шаг 3: Опиши самые грязные детали её трансформации (например: 'Из сосков течет светящееся молоко, киска превращается в плотоядный цветок, выделяет липкую слизь').")

@dp.message(CharacterCreation.waiting_for_changes)
async def process_changes(message: Message, state: FSMContext):
    data = await state.get_data()
    name = data['name']
    body = data['body']
    changes = message.text
    
    char_id = f"{name.split(',')[0]}" # Берем имя для тега
    
    characters[char_id] = {
        "full_name": name,
        "body": body,
        "changes": changes
    }
    
    await state.clear()
    await message.answer(
        f"✅ Персонаж **{name}** успешно создан!\n\n"
        f"Чтобы начать игру, напиши: 'Начинаем игру с {name.split(',')[0]}'.\n"
        f"Я загружу её параметры и начну трансформацию.",
        parse_mode="Markdown"
    )

@dp.message(F.text.startswith("Начинаем игру с "))
async def start_game(message: Message):
    char_name = message.text.replace("Начинаем игру с ", "").strip()
    
    if char_name in characters:
        char = characters[char_name]
        prompt = (
            f"Начинаем игру. Персонаж: {char['full_name']}. "
            f"Её тело: {char['body']}. "
            f"Детали трансформации: {char['changes']}. "
            f"Опиши первую сцену, как она появляется передо мной, и как её тело начинает меняться согласно заданным параметрам. Используй грязные слова."
        )
        await message.answer("✍️ Запускаю симуляцию...")
        try:
            reply = await llm_reply(message.from_user.id, prompt)
            await message.answer(reply)
        except Exception as e:
            await message.answer(f"Ошибка: {e}")
    else:
        await message.answer("❌ Персонаж не найден. Создай его через /create.")

# --- Обычный диалог и картинки ---
@dp.message(F.text)
async def handle(message: Message):
    text = message.text.strip()
    if not text or text.startswith("/"):
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
    
    # Если это не команда и не картинка — отправляем в ИИ
    await message.answer("✍️ Думаю…")
    try:
        await message.answer(await llm_reply(message.from_user.id, text))
    except Exception as e:
        await message.answer(f"Ошибка: {e}")

# --- Веб-сервер ---
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