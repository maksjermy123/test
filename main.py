import asyncio
import json
import base64
import os
import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from datetime import datetime

app = FastAPI()

# ── Конфигурация ──────────────────────────────────────────────
BOT_TOKEN      = "8705181884:AAGgfwunSu71wYcipiqdqIxdVQL_3kU_k14"
CHANNEL_ID     = "@Testovuj"
GITHUB_TOKEN   = os.environ.get("GITHUB_TOKEN", "")  # задаётся в Render
GITHUB_REPO    = "maksjermy123/test"
GEMINI_API_KEY = "AIzaSyBqCiHuH1iS0lkhFdJQRmj45975rRXDKZI"

TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"
GITHUB_API   = "https://api.github.com"
GEMINI_API   = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    f"gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
)
GITHUB_HEADERS = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json",
}

# ── Хэштеги → категории ───────────────────────────────────────
HASHTAG_MAP = {
    "#библия":          "📖 Библия и толкование",
    "#богословие":      "✝️ Богословие",
    "#теодицея":        "😔 Теодицея",
    "#книги":           "📚 Книги и авторы",
    "#достоевский":     "📚 Достоевский",
    "#жизнь":           "🌱 Христианская жизнь",
    "#молитва":         "🙏 Молитва и духовная жизнь",
    "#духовныйдневник": "📔 Духовный дневник",
    "#проповедь":       "🎤 Проповедь и семинар",
    "#семинар":         "🎤 Проповедь и семинар",
    "#челлендж":        "📅 Челлендж: Лука",
    "#лука":            "📅 Челлендж: Лука",
    "#история":         "🏛️ История и церковь",
    "#размышления":     "💬 Размышления и цитаты",
    "#цитата":          "💬 Размышления и цитаты",
    "#юмор":            "😄 Юмор",
    "#праздник":        "🎄 Праздники",
    "#анонс":           "📻 Анонсы канала",
}
IGNORE_TAGS = {"#отчтениякпреображению"}

GEMINI_PROMPT = """
Ты помощник для христианского канала «От чтения к Преображению».
Проанализируй пост канала и сформируй ссылочную массу на русском языке.

ТЕКСТ ПОСТА:
{post_text}

ТЕМА ПОСТА (хэштеги): {topics}

ВСЕ ПОСТЫ КАНАЛА (JSON):
{all_posts}

Сформируй JSON без лишнего текста:
{{
  "related_posts": [список из 3-5 id постов из канала наиболее близких по теме],
  "bible_refs": [
    {{"ref": "Книга глава:стихи", "url": "https://bible.by/verse/...", "theme": "краткая тема"}}
  ],
  "quotes": [
    {{"author": "Имя автора", "book": "Название книги", "text": "цитата до 200 символов"}}
  ],
  "reflection": "один глубокий вопрос для личного размышления по теме поста"
}}

Правила:
- related_posts: только реально существующие id из предоставленного JSON
- bible_refs: 2-4 отрывка, URL формат bible.by: https://bible.by/verse/КНИГА/ГЛАВА/СТИХ/
- quotes: цитаты богословов (Льюис, Фергюсон, Достоевский, Сперджен, Барт) если уместны
- reflection: конкретный практический вопрос, не общий
- Весь текст на русском языке
- Только валидный JSON, без markdown блоков
"""

# ── Блокировка от race condition ──────────────────────────────
github_lock = asyncio.Lock()


# ── GitHub helpers ────────────────────────────────────────────
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
            fresh, new_sha = await github_get(client, filename)
            if new_sha:
                body["sha"] = new_sha
            await asyncio.sleep(1)
            continue
        r.raise_for_status()


# ── Gemini анализ ─────────────────────────────────────────────
async def analyze_with_gemini(post_text: str, topics: list, all_posts: dict):
    prompt = GEMINI_PROMPT.format(
        post_text=post_text,
        topics=", ".join(topics),
        all_posts=json.dumps(all_posts, ensure_ascii=False)[:8000],
    )
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(GEMINI_API, json=payload)
        r.raise_for_status()
        text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
        text = text.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
        return json.loads(text)


# ── Обработка поста ───────────────────────────────────────────
async def process_post(post: dict):
    post_id = post.get("message_id") or post.get("id")
    text = post.get("text", "") or post.get("caption", "")
    if not text or not post_id:
        return

    words = text.lower().split()
    topics = [
        HASHTAG_MAP[w]
        for w in words
        if w in HASHTAG_MAP and w not in IGNORE_TAGS
    ]
    if not topics:
        print(f"Post {post_id}: no known hashtags, skipping.")
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
                result = await analyze_with_gemini(text, topics, posts_data)
            except Exception as e:
                print(f"Gemini error for post {post_id}: {e}")
                return

            result["post_id"] = post_id
            result["topics"] = topics

            links_data, links_sha = await github_get(client, "links.json")
            if links_data is None:
                links_data = {}
            links_data[str(post_id)] = result
            await github_put(client, "links.json", links_data, links_sha, f"Links for post {post_id}")
            print(f"✅ Post {post_id} processed successfully.")


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
