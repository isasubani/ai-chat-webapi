import time
import json
import sqlite3
import logging
import os
import hashlib
import secrets
from fastapi import FastAPI, Request, Form, Cookie, Depends
from fastapi.responses import JSONResponse, StreamingResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
import uvicorn
from gemini_webapi import GeminiClient
from agent_brain import get_os_info, run_shell_command_realtime, read_local_file, write_local_file
import asyncio
import re

# ==========================================
# 1. SETUP LOGGING
# ==========================================
LOG_FILE = "app.log"
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# ==========================================
# 2. SETUP DATABASE & APP
# ==========================================
DB_FILE = "database.db"
app = FastAPI()
os.makedirs("templates", exist_ok=True)
templates = Jinja2Templates(directory="templates")

# Default password dashboard: admin123
DEFAULT_PASSWORD_HASH = hashlib.sha256(b"admin123").hexdigest()

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)''')

    # Default settings jika belum ada
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('SESSION_COOKIE', '')")
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('API_KEY', 'dummy-key')")
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('BASE_URL', 'http://localhost:3001/v1')")
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('AVAILABLE_MODELS', 'gemini-web, gemini-imagen')")
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('DASHBOARD_PASSWORD', ?)", (DEFAULT_PASSWORD_HASH,))

    conn.commit()
    conn.close()

def get_setting(key):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key=?", (key,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else ""

def update_settings(cookie, api_key, base_url, models):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE settings SET value=? WHERE key='SESSION_COOKIE'", (cookie,))
    c.execute("UPDATE settings SET value=? WHERE key='API_KEY'", (api_key,))
    c.execute("UPDATE settings SET value=? WHERE key='BASE_URL'", (base_url,))
    c.execute("UPDATE settings SET value=? WHERE key='AVAILABLE_MODELS'", (models,))
    conn.commit()
    conn.close()

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def update_dashboard_password(new_password: str):
    hashed = hash_password(new_password)
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE settings SET value=? WHERE key='DASHBOARD_PASSWORD'", (hashed,))
    conn.commit()
    conn.close()

def verify_password(password: str) -> bool:
    stored = get_setting("DASHBOARD_PASSWORD") or DEFAULT_PASSWORD_HASH
    return hashlib.sha256(password.encode()).hexdigest() == stored

# ==========================================
# 3. SESSION MANAGEMENT (in-memory)
# ==========================================
valid_sessions: set = set()

def create_session() -> str:
    token = secrets.token_hex(32)
    valid_sessions.add(token)
    return token

def is_valid_session(token: str | None) -> bool:
    if not token:
        return False
    return token in valid_sessions

def invalidate_session(token: str | None):
    if token and token in valid_sessions:
        valid_sessions.discard(token)

def require_auth(request: Request, session_token: str | None = Cookie(default=None)):
    if not is_valid_session(session_token):
        next_url = request.url.path
        return RedirectResponse(url=f"/login?next={next_url}", status_code=302)
    return None

init_db()
logger.info("Aplikasi dimulai. Database siap.")

gemini = None

async def get_gemini_client():
    global gemini
    cookie = get_setting("SESSION_COOKIE")
    if not cookie:
        logger.warning("SESSION_COOKIE belum diatur! Harap isi di dashboard.")
        return None

    if gemini is None:
        gemini = GeminiClient(session_id=cookie, auto_refresh=True)
        try:
            await gemini.init(timeout=30, auto_close=False, auto_refresh=True)
        except Exception as e:
            logger.error(f"Gagal menginisialisasi GeminiClient: {e}")
            gemini = None
            return None
    return gemini

# ==========================================
# 4. ROUTES UNTUK DASHBOARD UI (TETAP UTUH)
# ==========================================
@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, next: str = "/"):
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={"error": "", "next": next}
    )

@app.post("/login")
async def login(
    request: Request,
    password: str = Form(""),
    next: str = Form("/")
):
    if verify_password(password):
        token = create_session()
        response = RedirectResponse(url=next or "/", status_code=303)
        response.set_cookie("session_token", token, httponly=True, samesite="lax")
        logger.info("Login dashboard berhasil.")
        return response
    logger.warning("Percobaan login gagal.")
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={"error": "Password salah. Silakan coba lagi.", "next": next}
    )

@app.get("/logout")
async def logout(session_token: str | None = Cookie(default=None)):
    invalidate_session(session_token)
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie("session_token")
    logger.info("Logout dashboard.")
    return response

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, message: str = "", session_token: str | None = Cookie(default=None)):
    auth = require_auth(request, session_token)
    if auth:
        return auth
    return templates.TemplateResponse(
        request=request,
        name="settings.html",
        context={
            "current_cookie": get_setting("SESSION_COOKIE"),
            "current_api_key": get_setting("API_KEY"),
            "current_base_url": get_setting("BASE_URL"),
            "current_models": get_setting("AVAILABLE_MODELS"),
            "message": message
        }
    )

@app.get("/logs", response_class=HTMLResponse)
async def logs_page(request: Request, session_token: str | None = Cookie(default=None)):
    auth = require_auth(request, session_token)
    if auth:
        return auth
    return templates.TemplateResponse(request=request, name="logs.html", context={})

@app.post("/update-settings")
async def update_settings_route(
    request: Request,
    cookie: str = Form(""), 
    api_key: str = Form(""),
    base_url: str = Form(""),
    models: str = Form(""),
    new_password: str = Form(""),
    confirm_password: str = Form(""),
    session_token: str | None = Cookie(default=None)
):
    auth = require_auth(request, session_token)
    if auth:
        return auth
    global gemini
    update_settings(cookie, api_key, base_url, models)
    gemini = None  # Reset client

    msg = "Pengaturan berhasil diperbarui!"
    if new_password:
        if new_password != confirm_password:
            return RedirectResponse(url="/?message=Password+tidak+cocok!", status_code=303)
        update_dashboard_password(new_password)
        msg = "Pengaturan dan password berhasil diperbarui!"
        logger.info("Password dashboard diperbarui.")

    logger.info("Settings diperbarui via Dashboard.")
    return RedirectResponse(url=f"/?message={msg.replace(' ', '+')}", status_code=303)

@app.get("/api/logs")
async def get_logs(request: Request, session_token: str | None = Cookie(default=None)):
    auth = require_auth(request, session_token)
    if auth:
        return auth
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "r") as f:
            lines = f.readlines()
            return "".join(lines[-100:])
    return "Belum ada log."

# ==========================================
# 5. ROUTES UNTUK API AI (OPENAI-COMPATIBLE + TOOLS & OS AWARENESS)
# ==========================================
@app.get("/v1/models")
async def list_models():
    raw_models = get_setting("AVAILABLE_MODELS")
    model_list = [m.strip() for m in raw_models.split(",") if m.strip()]

    data = []
    for m in model_list:
        data.append({
            "id": m,
            "object": "model",
            "created": int(time.time()),
            "owned_by": "custom"
        })

    return JSONResponse({
        "object": "list",
        "data": data
    })

@app.get("/v1/chat/history/{chat_id}")
async def get_chat_history(chat_id: str):
    client = await get_gemini_client()
    if not client:
        return JSONResponse({"error": "SESSION_COOKIE not configured."}, status_code=500)
    try:
        history = await client.read_chat(chat_id)
        turns_data = [{"role": turn.role, "text": turn.text} for turn in history.turns]
        return JSONResponse({"chat_id": chat_id, "history": turns_data})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)

active_chats: dict = {}

@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    db_api_key = get_setting("API_KEY")
    auth_header = request.headers.get("Authorization", "")

    if db_api_key and auth_header != f"Bearer {db_api_key}":
        logger.warning("Akses ditolak: API Key tidak valid.")
        return JSONResponse({"error": "Unauthorized. Invalid API Key."}, status_code=401)

    client = await get_gemini_client()
    if not client:
        return JSONResponse({"error": "SESSION_COOKIE not configured. Please set it in dashboard."}, status_code=500)

    try:
        body = await request.json()
        messages = body.get("messages", [])
        is_stream = body.get("stream", False)
        requested_model = body.get("model", "gemini-web")
        files = body.get("files", [])

        if not messages:
            return JSONResponse({"error": "No messages provided."}, status_code=400)

        last_prompt = messages[-1].get("content", "")
        if isinstance(last_prompt, list):
            text_prompts = [p.get("text", "") for p in last_prompt if p.get("type") == "text"]
            last_prompt = " ".join(text_prompts)

        os_info = get_os_info()
        system_context = (
            f"[Sistem Informasi Target: OS={os_info['system']}, Release={os_info['release']}, Arch={os_info['machine']}]. "
            "Jika kamu ingin menjalankan perintah terminal di OS user, tuliskan perintah tersebut di dalam blok kode markdown ```bash [perintah] ```. "
            "Berikan penjelasan singkat sebelum menuliskan blok kode tersebut."
        )

        session_key = f"{requested_model}"
        if session_key not in active_chats:
            active_chats[session_key] = client.start_chat()
            await active_chats[session_key].send_message(system_context)

        chat = active_chats[session_key]

        logger.info(f"Menerima prompt super ringan (Model: {requested_model}): {last_prompt[:50]}...")

        # Image Generation handling
        if "imagen" in requested_model.lower() or "buatkan gambar" in last_prompt.lower():
            response = await client.generate_content(last_prompt)
            image_urls = [img.url for img in response.images] if hasattr(response, 'images') else []
            response_text = f"Gambar berhasil dibuat:\n" + "\n".join([f"![]({url})" for url in image_urls]) if image_urls else getattr(response, 'text', str(response))
            return JSONResponse({
                "id": f"chatcmpl-{int(time.time())}",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": requested_model,
                "choices": [{"index": 0, "message": {"role": "assistant", "content": response_text}, "finish_reason": "stop"}]
            })

        # Kirim prompt langsung ke objek chat aktif tanpa mengirim ulang history secara manual
        response = await chat.send_message(last_prompt, files=files if files else None)
        response_text = response.text if hasattr(response, 'text') else str(response)

        match = re.search(r'```(?:bash|sh)\n(.*?)\n```', response_text, re.DOTALL)
        
        if match and is_stream:
            command_to_run = match.group(1).strip()
            logger.info(f"Menjalankan command kilat: {command_to_run}")

            async def real_time_generator_lightning():
                intro_msg = response_text + "\n\n*⚙️ Mengeksekusi secara real-time:* `" + command_to_run + "`\n```text\n"
                chunk_intro = {
                    "id": f"chatcmpl-{int(time.time())}",
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": requested_model,
                    "choices": [{"index": 0, "delta": {"content": intro_msg}, "finish_reason": None}]
                }
                yield f"data: {json.dumps(chunk_intro)}\n\n"

                full_terminal_output = ""
                for line in run_shell_command_realtime(command_to_run):
                    full_terminal_output += line
                    chunk_line = {
                        "id": f"chatcmpl-{int(time.time())}",
                        "object": "chat.completion.chunk",
                        "created": int(time.time()),
                        "model": requested_model,
                        "choices": [{"index": 0, "delta": {"content": line}, "finish_reason": None}]
                    }
                    yield f"data: {json.dumps(chunk_line)}\n\n"

                feedback_prompt = f"Output terminal lengkap dari '{command_to_run}':\n{full_terminal_output}\nBerikan kesimpulan akhir kepada user."
                final_response = await chat.send_message(feedback_prompt)
                final_text = final_response.text if hasattr(final_response, 'text') else str(final_response)

                closing_content = "\n```\n\n" + final_text
                chunk_close = {
                    "id": f"chatcmpl-{int(time.time())}",
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": requested_model,
                    "choices": [{"index": 0, "delta": {"content": closing_content}, "finish_reason": None}]
                }
                yield f"data: {json.dumps(chunk_close)}\n\n"

                stop_chunk = {
                    "id": f"chatcmpl-{int(time.time())}",
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": requested_model,
                    "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]
                }
                yield f"data: {json.dumps(stop_chunk)}\n\n"
                yield "data: [DONE]\n\n"

            return StreamingResponse(real_time_generator_lightning(), media_type="text/event-stream")

        if is_stream:
            async def normal_stream_lightning():
                chunk_data = {
                    "id": f"chatcmpl-{int(time.time())}",
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": requested_model,
                    "choices": [{"index": 0, "delta": {"content": response_text}, "finish_reason": None}]
                }
                yield f"data: {json.dumps(chunk_data)}\n\n"
                
                stop_chunk = {
                    "id": f"chatcmpl-{int(time.time())}",
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": requested_model,
                    "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]
                }
                yield f"data: {json.dumps(stop_chunk)}\n\n"
                yield "data: [DONE]\n\n"

            return StreamingResponse(normal_stream_lightning(), media_type="text/event-stream")

        return JSONResponse({
            "id": f"chatcmpl-{int(time.time())}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": requested_model,
            "choices": [{"index": 0, "message": {"role": "assistant", "content": response_text}, "finish_reason": "stop"}]
        })
    except Exception as e:
        logger.error(f"Error pada chat completions: {str(e)}")
        return JSONResponse({"error": str(e)}, status_code=500)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=3001)