import asyncio
import json
import base64
import os
import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Конфигурация ──────────────────────────────────────────────
BOT_TOKEN    = "8705181884:AAGgfwunSu71wYcipiqdqIxdVQL_3kU_k14"
CHANNEL_ID   = "@Testovuj"
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO  = "maksjermy123/test"
GROQ_API_KEY = "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"

TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"
GITHUB_API   = "https://api.github.com"
GROQ_URL     = "https://api.groq.com/openai/v1/chat/completions"

GITHUB_HEADERS = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json",
}
GROQ_HEADERS = {
    "Authorization": f"Bearer {GROQ_API_KEY}",
    "Content-Type": "application/json",
}

# ── Хэштеги ───────────────────────────────────────────────────
HASHTAG_MAP = {
    "#библия":          "Библия и толкование",
    "#богословие":      "Богословие",
    "#теодицея":        "Теодицея",
    "#книги":           "Книги и авторы",
    "#достоевский":     "Достоевский",
    "#жизнь":           "Христианская жизнь",
    "#молитва":         "Молитва и духовная жизнь",
    "#духовныйдневник": "Духовный дневник",
    "#проповедь":       "Проповедь и семинар",
    "#семинар":         "Проповедь и семинар",
    "#челлендж":        "Челлендж: Лука",
    "#лука":            "Челлендж: Лука",
    "#история":         "История и церковь",
    "#размышления":     "Размышления и цитаты",
    "#цитата":          "Размышления и цитаты",
    "#юмор":            "Юмор",
    "#праздник":        "Праздники",
    "#анонс":           "Анонсы канала",
}
IGNORE_TAGS = {"#отчтениякпреображению"}

# ── Карта книг: русское название → номер на bible.by ─────────
# Формат ссылки: https://bible.by/syn/КНИГА/ГЛАВА/СТИХ/
BOOK_NUM = {
    "Бытие": 1, "Исход": 2, "Левит": 3, "Числа": 4, "Второзаконие": 5,
    "Иисус Навин": 6, "Судьи": 7, "Руфь": 8,
    "1 Царств": 9, "2 Царств": 10, "3 Царств": 11, "4 Царств": 12,
    "1 Паралипоменон": 13, "2 Паралипоменон": 14,
    "Ездра": 15, "Неемия": 16, "Есфирь": 17, "Иов": 18,
    "Псалтирь": 19, "Псалом": 19, "Притчи": 20,
    "Екклесиаст": 21, "Песня Песней": 22,
    "Исаия": 23, "Иеремия": 24, "Плач Иеремии": 25,
    "Иезекииль": 26, "Даниил": 27, "Осия": 28, "Иоиль": 29,
    "Амос": 30, "Авдий": 31, "Иона": 32, "Михей": 33,
    "Наум": 34, "Аввакум": 35, "Софония": 36, "Аггей": 37,
    "Захария": 38, "Малахия": 39,
    "Матфей": 40, "Марк": 41, "Лука": 42, "Иоанн": 43,
    "Деяния": 44, "Римлянам": 45,
    "1 Коринфянам": 46, "2 Коринфянам": 47,
    "Галатам": 48, "Ефесянам": 49, "Филиппийцам": 50,
    "Колоссянам": 51, "1 Фессалоникийцам": 52, "2 Фессалоникийцам": 53,
    "1 Тимофею": 54, "2 Тимофею": 55, "Титу": 56, "Филимону": 57,
    "Евреям": 58, "Иакова": 59,
    "1 Петра": 60, "2 Петра": 61,
    "1 Иоанна": 62, "2 Иоанна": 63, "3 Иоанна": 64,
    "Иуды": 65, "Откровение": 66,
}

TRANSLATIONS = {
    "syn": "Синодальный",
    "kas": "Кассиана",
    "nrt": "РБО",
    "niv": "NIV (англ.)",
}

GROQ_PROMPT = """
Ты помощник для христианского канала «От чтения к Преображению».
Проанализируй пост и сформируй ссылочную массу на русском языке.

ТЕКСТ ПОСТА:
{post_text}

ТЕМА (хэштеги): {topics}

ВСЕ ПОСТЫ КАНАЛА:
{all_posts}

Ответь ТОЛЬКО валидным JSON без markdown:
{{
  "related_posts": [3-5 id похожих постов из списка выше],
  "bible_refs": [
    {{"ref": "Книга глава:стих", "theme": "краткая тема"}}
  ],
  "reflection": "один конкретный вопрос для размышления"
}}

Правила:
- related_posts: только существующие id из списка
- bible_refs: 2-4 отрывка, формат ref: "Иов 1:21" или "Римлянам 8:28-30"
- reflection: практический вопрос, не общий
- только JSON, никакого другого текста
"""

github_lock = asyncio.Lock()


# ── GitHub ────────────────────────────────────────────────────
async def github_get(client: httpx.AsyncClient, filename: str):
    url = f"{GITHUB_API}/repos/{GITHUB_REPO}/contents/{filename}"
    r = await client.get(url, headers=GITHUB_HEADERS)
    if r.status_code == 404:
        return None, None
    r.raise_for_status()
    data = r.json()
    content = json.loads(base64.b64decode(data["content"]).decode())
    return content, data["sha"]


async def github_put(client: httpx.AsyncClient, filename: str, content: dict, sha, message: str):
    encoded = base64.b64encode(
        json.dumps(content, ensure_ascii=False, indent=2).encode()
    ).decode()
    body = {"message": message, "content": encoded}
    if sha:
        body["sha"] = sha
    url = f"{GITHUB_API}/repos/{GITHUB_REPO}/contents/{filename}"
    for attempt in range(3):
        r = await client.put(url, headers=GITHUB_HEADERS, json=body)
        if r.status_code in (200, 201):
            return r.json()
        if r.status_code == 409 and attempt < 2:
            _, new_sha = await github_get(client, filename)
            if new_sha:
                body["sha"] = new_sha
            await asyncio.sleep(1)
            continue
        r.raise_for_status()


# ── Парсинг ref: "Книга глава:стих" → (book_num, chapter, verse) ──
def parse_ref(ref: str):
    """Разбираем ref на компоненты. Возвращает (book_num, chapter, verse_start) или None."""
    try:
        parts = ref.strip().split(" ")
        if parts[0].isdigit() and len(parts) >= 3:
            book_ru = parts[0] + " " + parts[1]
            cv = parts[2]
        elif len(parts) >= 2:
            book_ru = parts[0]
            cv = parts[1]
        else:
            return None

        book_num = BOOK_NUM.get(book_ru)
        if not book_num:
            return None

        # cv может быть "1:21" или "8:28-30"
        if ":" in cv:
            chapter, verse_part = cv.split(":", 1)
            verse_start = verse_part.split("-")[0]
            return book_num, int(chapter), int(verse_start)
    except Exception:
        pass
    return None


async def fetch_bible_text(ref: str) -> str:
    """Текст Синодального перевода — парсим bible.by/syn/"""
    parsed = parse_ref(ref)
    if not parsed:
        return ""
    book_num, chapter, verse = parsed
    url = f"https://bible.by/syn/{book_num}/{chapter}/{verse}/"
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            r = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code != 200:
                return ""
            html = r.text
            # Ищем текст стиха между тегами — bible.by хранит его в <p class="verse...">
            import re
            # Ищем span с классом versenum и берём следующий текст
            matches = re.findall(r'<p[^>]*class="[^"]*verse[^"]*"[^>]*>(.*?)</p>', html, re.DOTALL)
            if matches:
                # Убираем HTML теги
                text = re.sub(r'<[^>]+>', '', matches[0]).strip()
                return text[:500]
    except Exception as e:
        print(f"Bible parse error for '{ref}': {e}")
    return ""


def make_translation_links(ref: str) -> dict:
    """Прямая ссылка на стих со всеми переводами на bible.by"""
    parsed = parse_ref(ref)
    if not parsed:
        return {}
    book_num, chapter, verse = parsed
    return {
        "📖 Читать все переводы": f"https://bible.by/verse/{book_num}/{chapter}/{verse}/",
    }


# ── Groq анализ ───────────────────────────────────────────────
async def analyze_post(post_text: str, topics: list, all_posts: dict):
    prompt = GROQ_PROMPT.format(
        post_text=post_text,
        topics=", ".join(topics),
        all_posts=json.dumps(all_posts, ensure_ascii=False)[:8000],
    )
    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
    }
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(GROQ_URL, headers=GROQ_HEADERS, json=payload)
        r.raise_for_status()
        text = r.json()["choices"][0]["message"]["content"]
        text = text.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
        return json.loads(text)


# ── Обработка поста ───────────────────────────────────────────
async def process_post(post: dict):
    post_id = post.get("message_id") or post.get("id")
    text = post.get("text", "") or post.get("caption", "")
    if not text or not post_id:
        return

    words = text.lower().split()
    topics = [HASHTAG_MAP[w] for w in words if w in HASHTAG_MAP and w not in IGNORE_TAGS]
    if not topics:
        print(f"Post {post_id}: no hashtags, skipping.")
        return

    async with github_lock:
        async with httpx.AsyncClient(timeout=20) as client:
            posts_data, posts_sha = await github_get(client, "posts.json")
            if posts_data is None:
                posts_data = {"posts": [], "topics": [], "total": 0, "updated": ""}

            existing_ids = {p["id"] for p in posts_data["posts"]}
            if post_id not in existing_ids:
                posts_data["posts"].append({
                    "id": post_id,
                    "text": text[:500],
                    "topics": topics,
                    "date": datetime.utcnow().isoformat(),
                })
                posts_data["total"] = len(posts_data["posts"])
                posts_data["updated"] = datetime.utcnow().isoformat()
                await github_put(client, "posts.json", posts_data, posts_sha, f"Add post {post_id}")

            try:
                result = await analyze_post(text, topics, posts_data)
            except Exception as e:
                print(f"Groq error for post {post_id}: {e}")
                return

            result["post_id"] = post_id
            result["topics"] = topics
            result["quotes"] = []

            # Подтягиваем текст и ссылки на переводы для каждого стиха
            for bible_ref in result.get("bible_refs", []):
                ref_str = bible_ref.get("ref", "")
                bible_ref["text_syn"] = await fetch_bible_text(ref_str)
                bible_ref["translations"] = make_translation_links(ref_str)

            links_data, links_sha = await github_get(client, "links.json")
            if links_data is None:
                links_data = {}
            links_data[str(post_id)] = result
            await github_put(client, "links.json", links_data, links_sha, f"Links for post {post_id}")
            print(f"Post {post_id} processed OK.")


# ── Эндпоинты ─────────────────────────────────────────────────
@app.get("/")
async def root():
    return {"status": "ok", "service": "deeplink-test"}


@app.head("/")
async def root_head():
    return JSONResponse(content={})


@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    post = data.get("channel_post") or data.get("message")
    if post:
        asyncio.create_task(process_post(post))
    return {"ok": True}


@app.get("/links/{post_id}")
async def get_links(post_id: int):
    async with httpx.AsyncClient(timeout=10) as client:
        links_data, _ = await github_get(client, "links.json")
    if not links_data or str(post_id) not in links_data:
        return JSONResponse(status_code=404, content={"error": "not found"})
    return links_data[str(post_id)]


@app.post("/analyze/{post_id}")
async def manual_analyze(post_id: int):
    async with httpx.AsyncClient(timeout=10) as client:
        posts_data, _ = await github_get(client, "posts.json")
    if not posts_data:
        return JSONResponse(status_code=404, content={"error": "posts.json not found"})
    post = next((p for p in posts_data["posts"] if p["id"] == post_id), None)
    if not post:
        return JSONResponse(status_code=404, content={"error": f"post {post_id} not found"})
    asyncio.create_task(process_post({"message_id": post_id, "text": post["text"]}))
    return {"ok": True, "message": f"Analysis started for post {post_id}"}


@app.get("/set_webhook")
async def set_webhook(request: Request):
    base_url = str(request.base_url).rstrip("/")
    url = f"{TELEGRAM_API}/setWebhook"
    payload = {
        "url": f"{base_url}/webhook",
        "allowed_updates": ["message", "channel_post"],
    }
    async with httpx.AsyncClient() as client:
        r = await client.post(url, json=payload)
    return r.json()
