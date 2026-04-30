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
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")

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
# Полностью проверено! bible.by использует порядок:
# Деяния → Соборные послания (Иак, 1-2Пет, 1-3Ин, Иуд) → Павел → Откровение
# ВЗ: 1-39 (стандартный), НЗ: Мф=40...Деян=44, затем соборные 45-51,
# Рим=52, 1Кор=53...Евр=65, Откр=66
BOOK_NUM = {
    # Ветхий Завет (стандартная нумерация 1-39)
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
    # Новый Завет — Евангелия и Деяния
    "Матфей": 40, "Марк": 41, "Лука": 42, "Иоанн": 43, "Деяния": 44,
    # Соборные послания (45-51)
    "Иакова": 45,
    "1 Петра": 46, "2 Петра": 47,
    "1 Иоанна": 48, "2 Иоанна": 49, "3 Иоанна": 50,
    "Иуды": 51,
    # Послания Павла (52-65)
    "Римлянам": 52,
    "1 Коринфянам": 53, "2 Коринфянам": 54,
    "Галатам": 55, "Ефесянам": 56, "Филиппийцам": 57, "Колоссянам": 58,
    "1 Фессалоникийцам": 59, "2 Фессалоникийцам": 60,
    "1 Тимофею": 61, "2 Тимофею": 62, "Титу": 63, "Филимону": 64,
    "Евреям": 65,
    # Откровение
    "Откровение": 66,
}

TRANSLATIONS = {
    "syn": "Синодальный",
    "kas": "Кассиана",
    "nrt": "РБО",
    "niv": "NIV (англ.)",
}

GROQ_PROMPT = """
Ты — вдумчивый богослов и библеист с глубоким знанием Священного Писания.
Ты внимательно читаешь текст христианского поста и помогаешь читателю
войти глубже в ту же мысль через Слово Божье.

━━━ ТЕКСТ ПОСТА ━━━
{post_text}

━━━ ТВОЙ ПРОЦЕСС ━━━

ШАГ 1 — ПОЙМИ АВТОРА
Прочитай пост целиком. Определи:
- Главную богословскую мысль которую развивает автор
- Духовный опыт или вопрос стоящий за текстом
- Интонацию: размышление, исповедь, учение, утешение, призыв

ШАГ 2 — ТЕКСТЫ АВТОРА (role="автора")
Найди все тексты Писания которые автор явно цитирует или на которые опирается.
Они идут ПЕРВЫМИ. Если автор не дал точную ссылку — найди сам по содержанию.
Если автор не использует никаких текстов Писания — этот раздел пуст.

ШАГ 3 — ДОПОЛНИТЕЛЬНЫЕ ТЕКСТЫ (role="дополнительно")
Добавь 2-3 отрывка которые углубляют именно мысль автора:
- Один из другой части канона (ВЗ если автор в НЗ, и наоборот)
- Один христологический — как мысль раскрывается через Христа
- Один практический — что делать с этим знанием

СТРОГО ЗАПРЕЩЕНО:
- Подбирать стихи по ключевым словам или тегам — только по смыслу поста
- Брать стихи вырванные из контекста
- Использовать второканонические книги (Товит, Маккавеи, Премудрость и др.)
- Выдумывать или искажать ссылки — только реально существующие стихи
- Давать более 5 отрывков итого

Предпочитай отрывки (3-7 стихов) а не одиночные стихи.

ШАГ 5 — ВОПРОС ДЛЯ РАЗМЫШЛЕНИЯ
Сформулируй вопрос как продолжение мысли автора —
как будто ты его собеседник который прочитал пост и задаёт следующий вопрос.
Конкретный, личный, вытекающий из прочитанного — не общий по теме.

━━━ ОТВЕТ ━━━

Только валидный JSON, без markdown, без пояснений вне JSON:
{{
  "related_posts": [id постов близких по богословской мысли, или [] если нет],
  "bible_refs": [
    {{
      "ref": "Книга глава:стих — ОБЯЗАТЕЛЬНО указывай конкретный стих! Формат: 'Бытие 3:15' или 'Римлянам 8:18-25'. Никогда не пиши просто главу без стиха (не 'Бытие 3'!). Название в именительном падеже: Иоанн, Матфей, Лука, Римлянам, Псалтирь, 1 Коринфянам",
      "theme": "одно предложение — почему этот текст в контексте мысли автора",
      "role": "автора или дополнительно"
    }}
  ],
  "reflection": "Личный вопрос продолжающий мысль автора"
}}
"""

RELATED_PROMPT = """
Ты — богослов и редактор христианского канала.
Твоя задача — найти посты канала которые богословски связаны с данным постом.

АНАЛИЗИРУЕМЫЙ ПОСТ:
{post_text}

ПОСТЫ КАНАЛА:
{all_posts}

Прочитай анализируемый пост и определи его главную богословскую мысль.
Затем внимательно прочитай каждый пост из списка и найди те которые:
- Развивают ту же богословскую тему
- Используют похожие тексты Писания
- Продолжают или дополняют мысль автора
- Рассматривают смежную духовную проблему

НЕ выбирай посты просто потому что в них есть похожие слова или теги.
Выбирай по богословской близости мысли.
Если нет действительно близких постов — верни пустой список.

Ответь ТОЛЬКО валидным JSON без markdown:
{{"related_posts": [0-3 наиболее близких поста]}}
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
BOOK_ALIASES = {
    # Полные альтернативные названия
    "Евангелие от Матфея": "Матфей", "Евангелие от Марка": "Марк",
    "Евангелие от Луки": "Лука", "Евангелие от Иоанна": "Иоанн",
    "Деяния апостолов": "Деяния", "Деяния Апостолов": "Деяния",
    "Послание к Римлянам": "Римлянам", "Послание Иакова": "Иакова",
    "1-е Коринфянам": "1 Коринфянам", "2-е Коринфянам": "2 Коринфянам",
    "1-е Петра": "1 Петра", "2-е Петра": "2 Петра",
    "1-е Иоанна": "1 Иоанна", "2-е Иоанна": "2 Иоанна",
    "1-е Тимофею": "1 Тимофею", "2-е Тимофею": "2 Тимофею",
    "1-е Фессалоникийцам": "1 Фессалоникийцам",
    "2-е Фессалоникийцам": "2 Фессалоникийцам",
    "Откровение Иоанна": "Откровение", "Апокалипсис": "Откровение",
    # Сокращения ВЗ
    "Быт": "Бытие", "Исх": "Исход", "Лев": "Левит",
    "Чис": "Числа", "Втор": "Второзаконие",
    "Нав": "Иисус Навин", "Суд": "Судьи",
    "1Цар": "1 Царств", "2Цар": "2 Царств",
    "3Цар": "3 Царств", "4Цар": "4 Царств",
    "1Пар": "1 Паралипоменон", "2Пар": "2 Паралипоменон",
    "Езд": "Ездра", "Неем": "Неемия", "Есф": "Есфирь",
    "Иов": "Иов",
    "Пс": "Псалтирь", "Пс.": "Псалтирь", "Псалом": "Псалтирь",
    # Родительный падеж (ИИ часто пишет "Евангелие от Иоанна", "Послание Иакова" и т.д.)
    "Иоанна": "Иоанн",
    "Матфея": "Матфей",
    "Марка": "Марк",
    "Луки": "Лука",
    "Иакова": "Иакова",  # уже есть как книга
    "Петра": "1 Петра",  # осторожно — неоднозначно
    "Иуды": "Иуды",
    "Притч": "Притчи",
    "Деян": "Деяния",
    "Евр": "Евреям",
    "Флп": "Филиппийцам",
    "Кол": "Колоссянам",
    "Гал": "Галатам",
    "Еф": "Ефесянам",
    "Прит": "Притчи", "Еккл": "Екклесиаст", "Песн": "Песня Песней",
    "Ис": "Исаия", "Иер": "Иеремия", "Плач": "Плач Иеремии",
    "Иез": "Иезекииль", "Дан": "Даниил",
    "Ос": "Осия", "Иоил": "Иоиль", "Ам": "Амос",
    "Авд": "Авдий", "Иона": "Иона", "Мих": "Михей",
    "Наум": "Наум", "Авв": "Аввакум", "Соф": "Софония",
    "Агг": "Аггей", "Зах": "Захария", "Мал": "Малахия",
    # Сокращения НЗ
    "Мф": "Матфей", "Мк": "Марк", "Лк": "Лука",
    "Ин": "Иоанн", "Ин.": "Иоанн",
    "Деян": "Деяния",
    "Рим": "Римлянам",
    "1Кор": "1 Коринфянам", "2Кор": "2 Коринфянам",
    "Гал": "Галатам", "Еф": "Ефесянам", "Флп": "Филиппийцам",
    "Кол": "Колоссянам",
    "1Фес": "1 Фессалоникийцам", "2Фес": "2 Фессалоникийцам",
    "1Тим": "1 Тимофею", "2Тим": "2 Тимофею",
    "Тит": "Титу", "Флм": "Филимону",
    "Евр": "Евреям", "Иак": "Иакова",
    "1Пет": "1 Петра", "2Пет": "2 Петра",
    "1Ин": "1 Иоанна", "2Ин": "2 Иоанна", "3Ин": "3 Иоанна",
    "Иуд": "Иуды", "Откр": "Откровение",
    "Послание к Ефесянам": "Ефесянам",
    "Послание к Галатам": "Галатам",
    "Послание к Евреям": "Евреям",
    "Послание к Колоссянам": "Колоссянам",
    "Послание к Филиппийцам": "Филиппийцам",
    "Послание к Римлянам": "Римлянам",
    "1-е послание к Коринфянам": "1 Коринфянам",
    "2-е послание к Коринфянам": "2 Коринфянам",
    "1-е послание к Фессалоникийцам": "1 Фессалоникийцам",
    "2-е послание к Фессалоникийцам": "2 Фессалоникийцам",
    "1-е послание к Тимофею": "1 Тимофею",
    "2-е послание к Тимофею": "2 Тимофею",
    "1-е послание Петра": "1 Петра", "2-е послание Петра": "2 Петра",
    "1-е послание Иоанна": "1 Иоанна",
}


def normalize_book(name: str) -> str:
    """Нормализуем название книги через алиасы"""
    return BOOK_ALIASES.get(name, name)


def parse_ref(ref: str):
    """Разбираем ref на компоненты. Возвращает (book_num, chapter, verse_start) или None."""
    import re
    try:
        ref = ref.strip()
        # Убираем всё после " — " (ИИ иногда добавляет описание через тире)
        ref = re.split(r' [—–-]{1,2} ', ref)[0].strip()

        # Ищем паттерн "глава:стих" в конце строки
        m = re.search(r'(\d+:\d+(?:-\d+)?)$', ref)
        if m:
            cv = m.group(1)
            book_ru = normalize_book(ref[:m.start()].strip())
            book_num = BOOK_NUM.get(book_ru)
            if not book_num:
                return None
            chapter, verse_part = cv.split(":", 1)
            verse_start = verse_part.split("-")[0]
            return book_num, int(chapter), int(verse_start)

        # Если только глава без стиха (например "Бытие 3") — берём стих 1
        m2 = re.search(r'(\d+)$', ref)
        if m2:
            chapter = m2.group(1)
            book_ru = normalize_book(ref[:m2.start()].strip())
            book_num = BOOK_NUM.get(book_ru)
            if book_num:
                return book_num, int(chapter), 1
    except Exception:
        pass
    return None


# Кэш библейской базы (загружается один раз)
_bible_cache = None

async def get_bible_db(client: httpx.AsyncClient):
    """Загружаем ru_synodal.json напрямую через raw GitHub URL (файл >1MB)"""
    global _bible_cache
    if _bible_cache is not None:
        return _bible_cache
    try:
        url = f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/ru_synodal.json"
        r = await client.get(url, timeout=30)
        if r.status_code == 200:
            _bible_cache = r.json()
            print(f"Bible DB loaded: {len(_bible_cache)} books")
            return _bible_cache
    except Exception as e:
        print(f"Bible DB load error: {e}")
    return None


# Порядок книг в ru_synodal.json совпадает со стандартным:
# 0=Бытие, 38=Малахия, 39=Матфей, 65=Откровение
BOOK_JSON_INDEX = {
    # Ветхий Завет (0-38)
    "Бытие": 0, "Исход": 1, "Левит": 2, "Числа": 3, "Второзаконие": 4,
    "Иисус Навин": 5, "Судьи": 6, "Руфь": 7,
    "1 Царств": 8, "2 Царств": 9, "3 Царств": 10, "4 Царств": 11,
    "1 Паралипоменон": 12, "2 Паралипоменон": 13,
    "Ездра": 14, "Неемия": 15, "Есфирь": 16, "Иов": 17,
    "Псалтирь": 18, "Псалом": 18, "Притчи": 19,
    "Екклесиаст": 20, "Песня Песней": 21,
    "Исаия": 22, "Иеремия": 23, "Плач Иеремии": 24,
    "Иезекииль": 25, "Даниил": 26, "Осия": 27, "Иоиль": 28,
    "Амос": 29, "Авдий": 30, "Иона": 31, "Михей": 32,
    "Наум": 33, "Аввакум": 34, "Софония": 35, "Аггей": 36,
    "Захария": 37, "Малахия": 38,
    # Новый Завет — стандартный порядок (39-65)
    "Матфей": 39, "Марк": 40, "Лука": 41, "Иоанн": 42, "Деяния": 43,
    "Римлянам": 44,
    "1 Коринфянам": 45, "2 Коринфянам": 46,
    "Галатам": 47, "Ефесянам": 48, "Филиппийцам": 49, "Колоссянам": 50,
    "1 Фессалоникийцам": 51, "2 Фессалоникийцам": 52,
    "1 Тимофею": 53, "2 Тимофею": 54, "Титу": 55, "Филимону": 56,
    "Евреям": 57, "Иакова": 58,
    "1 Петра": 59, "2 Петра": 60,
    "1 Иоанна": 61, "2 Иоанна": 62, "3 Иоанна": 63,
    "Иуды": 64, "Откровение": 65,
}


async def fetch_bible_text(ref: str) -> str:
    """Текст Синодального перевода из ru_synodal.json на GitHub"""
    try:
        import re as _re
        # Убираем описание после тире: "Бытие 3 — Книга Бытия" -> "Бытие 3"
        ref = _re.split(r' [—–-]{1,2} ', ref.strip())[0].strip()

        m = _re.search(r'(\d+:\d+(?:-\d+)?)$', ref)
        if not m:
            # Только глава без стиха — берём первые 5 стихов
            m2 = _re.search(r'(\d+)$', ref)
            if not m2:
                return ""
            chapter = int(m2.group(1)) - 1
            book_ru = normalize_book(ref[:m2.start()].strip())
            book_idx = BOOK_JSON_INDEX.get(book_ru)
            if book_idx is None:
                return ""
            async with httpx.AsyncClient(timeout=15) as client:
                bible = await get_bible_db(client)
            if not bible or chapter >= len(bible[book_idx]["chapters"]):
                return ""
            verses = bible[book_idx]["chapters"][chapter][:5]
            return " ".join(f"{i+1} {v}" for i, v in enumerate(verses))

        cv = m.group(1)
        book_ru = normalize_book(ref[:m.start()].strip())
        book_idx = BOOK_JSON_INDEX.get(book_ru)
        if book_idx is None:
            return ""

        if ":" not in cv:
            return ""
        chapter_str, verse_str = cv.split(":", 1)
        chapter = int(chapter_str) - 1  # 0-based
        # Диапазон стихов: "1-4" → берём стихи 1,2,3,4
        if "-" in verse_str:
            v_start, v_end = verse_str.split("-", 1)
            verse_start = int(v_start) - 1  # 0-based
            verse_end = int(v_end)          # включительно
        else:
            verse_start = int(verse_str) - 1
            verse_end = verse_start + 1

        async with httpx.AsyncClient(timeout=15) as client:
            bible = await get_bible_db(client)
        if not bible:
            return ""

        book_data = bible[book_idx]
        chapters = book_data.get("chapters", [])
        if chapter >= len(chapters):
            return ""
        verses = chapters[chapter]
        selected = verses[verse_start:verse_end]
        if not selected:
            return ""
        # Нумеруем стихи
        first_verse_num = verse_start + 1
        result = " ".join(
            f"{first_verse_num + i} {v}" for i, v in enumerate(selected)
        )
        return result
    except Exception as e:
        print(f"Bible fetch error for '{ref}': {e}")
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


# ── Поиск связанных постов ───────────────────────────────────
async def find_related_posts(post_text: str, all_posts: dict) -> list:
    """Отдельный запрос к ИИ только для поиска связанных постов"""
    if not all_posts.get("posts"):
        return []
    # Передаём полный текст каждого поста
    posts_summary = []
    for p in all_posts["posts"]:
        posts_summary.append({
            "id": p["id"],
            "text": p["text"],  # уже до 2000 символов
            "topics": p.get("topics", [])
        })
    prompt = RELATED_PROMPT.format(
        post_text=post_text,
        all_posts=json.dumps(posts_summary, ensure_ascii=False)[:15000]
    )
    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,  # очень низкая — нужна точность, не креативность
    }
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(GROQ_URL, headers=GROQ_HEADERS, json=payload)
            r.raise_for_status()
            text = r.json()["choices"][0]["message"]["content"]
            text = text.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
            data = json.loads(text)
            return data.get("related_posts", [])
    except Exception as e:
        print(f"Related posts error: {e}")
        return []


# ── Groq анализ ───────────────────────────────────────────────
async def analyze_post(post_text: str, topics: list):
    prompt = GROQ_PROMPT.format(
        post_text=post_text,
        topics=", ".join(topics),
    )
    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
    }
    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.post(GROQ_URL, headers=GROQ_HEADERS, json=payload)
        r.raise_for_status()
        text = r.json()["choices"][0]["message"]["content"]
        text = text.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
        return json.loads(text)


# ── Кнопка "Глубже" под постом ───────────────────────────────
# Имя бота для формирования ссылки на Mini App
BOT_USERNAME = "my_channel_index_bot"

async def send_deeper_button(post_id: int):
    """Отправляем inline-кнопку под пост в канале.
    
    web_app кнопки запрещены в каналах — используем url кнопку.
    Формат ссылки: t.me/BOT?startapp=POST_ID открывает Mini App.
    """
    # Правильный формат для Mini App: t.me/BOT/APPNAME?startapp=POST_ID
    miniapp_url = f"https://t.me/{BOT_USERNAME}/deeper?startapp={post_id}"

    keyboard = {
        "inline_keyboard": [[
            {
                "text": "📚 Глубже",
                "url": miniapp_url
            }
        ]]
    }

    async with httpx.AsyncClient(timeout=10) as client:
        # Пробуем добавить кнопку к существующему посту
        r = await client.post(
            f"{TELEGRAM_API}/editMessageReplyMarkup",
            json={
                "chat_id": CHANNEL_ID,
                "message_id": post_id,
                "reply_markup": keyboard
            }
        )
        result = r.json()
        print(f"editMessageReplyMarkup: {result}")

        if result.get("ok"):
            print(f"✅ Кнопка '📚 Глубже' добавлена к посту {post_id}")
            return

        # Если edit не сработал — отправляем отдельное сообщение-кнопку
        print(f"⚠️ edit failed: {result.get('description')} — пробуем sendMessage")
        r2 = await client.post(
            f"{TELEGRAM_API}/sendMessage",
            json={
                "chat_id": CHANNEL_ID,
                "text": "📚 Библейский контекст и связи этого поста",
                "reply_to_message_id": post_id,
                "reply_markup": keyboard
            }
        )
        result2 = r2.json()
        if result2.get("ok"):
            print(f"✅ Кнопка отправлена отдельным сообщением")
        else:
            print(f"❌ Ошибка: {result2.get('description')}")


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

    # Для юмора — специальный ответ без ИИ
    if "😄 Юмор" in topics or "Юмор" in topics:
        humor_result = {
            "post_id": post_id,
            "topics": topics,
            "related_posts": [],
            "bible_refs": [],
            "quotes": [],
            "reflection": "",
            "humor": True,
            "humor_text": "«Серьёзность человека, обладающего чувством юмора, намного серьёзнее серьёзности серьёзного человека»",
            "humor_author": "А. П. Чехов"
        }
        async with github_lock:
            async with httpx.AsyncClient(timeout=20) as client:
                links_data, links_sha = await github_get(client, "links.json")
                if links_data is None:
                    links_data = {}
                links_data[str(post_id)] = humor_result
                await github_put(client, "links.json", links_data, links_sha, f"Humor post {post_id}")
        await send_deeper_button(post_id)
        print(f"😄 Humor post {post_id} saved.")
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
                    "text": text[:3000],  # для хранения в posts.json
                    "topics": topics,
                    "date": datetime.utcnow().isoformat(),
                })
                posts_data["total"] = len(posts_data["posts"])
                posts_data["updated"] = datetime.utcnow().isoformat()
                await github_put(client, "posts.json", posts_data, posts_sha, f"Add post {post_id}")

            # Параллельно запускаем анализ и поиск связанных постов
            try:
                result, related = await asyncio.gather(
                    analyze_post(text, topics),
                    find_related_posts(text, posts_data)
                )
            except Exception as e:
                print(f"Groq error for post {post_id}: {e}")
                return

            result["post_id"] = post_id
            result["topics"] = topics
            result["quotes"] = []
            result["related_posts"] = related[:2]  # показываем только 2 самых близких

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

            # Отправляем кнопку "Глубже" под пост в канале
            await send_deeper_button(post_id)


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

    # Обрабатываем сообщения канала
    post = data.get("channel_post")
    if post:
        asyncio.create_task(process_post(post))
        return {"ok": True}

    # Обрабатываем личные сообщения пользователей
    message = data.get("message")
    if message:
        asyncio.create_task(handle_user_message(message))

    return {"ok": True}


async def handle_user_message(message: dict):
    """Обрабатываем сообщения пользователей боту"""
    chat_id = message.get("chat", {}).get("id")
    text = message.get("text", "")

    if not chat_id:
        return

    # Извлекаем post_id из start_param: /start 312
    post_id = None
    if text.startswith("/start"):
        parts = text.split()
        if len(parts) > 1:
            try:
                post_id = int(parts[1])
            except ValueError:
                pass

    miniapp_url = f"https://maksjermy123.github.io/test/"
    if post_id:
        miniapp_url += f"?post_id={post_id}"

    # Отправляем кнопку web_app — она открывает Mini App без перехода
    payload = {
        "chat_id": chat_id,
        "text": "📚 Нажми чтобы открыть материалы поста:",
        "reply_markup": {
            "inline_keyboard": [[
                {
                    "text": "📚 Глубже",
                    "web_app": {"url": miniapp_url}
                }
            ]]
        }
    }

    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(f"{TELEGRAM_API}/sendMessage", json=payload)
        result = r.json()
        if result.get("ok"):
            print(f"✅ Отправлена web_app кнопка пользователю {chat_id} для поста {post_id}")
        else:
            print(f"⚠️ Ошибка: {result.get('description')}")


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
        "allowed_updates": ["message", "channel_post", "callback_query"],
    }
    async with httpx.AsyncClient() as client:
        r = await client.post(url, json=payload)
    return r.json()
