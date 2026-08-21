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
templates = Jinja2Templates(directory="templates")

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)''')
    
    # Default settings jika belum ada
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('SESSION_COOKIE', '')")
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('API_KEY', 'dummy-key')")
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('BASE_URL', 'http://localhost:3001/v1')")
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('AVAILABLE_MODELS', 'gemini-web')")
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('DASHBOARD_PASSWORD', '')")
    
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
    stored = get_setting("DASHBOARD_PASSWORD")
    if not stored:
        return True  # Belum ada password = bebas akses
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
    # Jika belum ada password, semua akses diizinkan
    if not get_setting("DASHBOARD_PASSWORD"):
        return True
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

def get_gemini_client():
    global gemini
    cookie = get_setting("SESSION_COOKIE")
    if not cookie:
        logger.warning("SESSION_COOKIE belum diatur! Harap isi di dashboard.")
        return None
    
    if gemini is None:
        gemini = GeminiClient(session_id=cookie)
    return gemini

# ==========================================
# 4. ROUTES UNTUK DASHBOARD UI
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
# 4. ROUTES UNTUK API AI (OPENCODE)
# ==========================================
@app.get("/v1/models")
async def list_models():
    # Ambil daftar model dinamis dari database (dipisah dengan koma)
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

@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    db_api_key = get_setting("API_KEY")
    auth_header = request.headers.get("Authorization", "")
    
    if db_api_key and auth_header != f"Bearer {db_api_key}":
        logger.warning("Akses ditolak: API Key tidak valid.")
        return JSONResponse({"error": "Unauthorized. Invalid API Key."}, status_code=401)

    client = get_gemini_client()
    if not client:
        return JSONResponse({"error": "SESSION_COOKIE not configured. Please set it in dashboard."}, status_code=500)

    try:
        body = await request.json()
        messages = body.get("messages", [])
        is_stream = body.get("stream", False)
        requested_model = body.get("model", "gemini-web")
        
        prompt = messages[-1]["content"] if messages else ""
        logger.info(f"Menerima prompt (Model: {requested_model}): {prompt[:50]}...")
        
        if is_stream:
            async def event_generator():
                full_text = ""
                async for chunk in client.generate_content_stream(prompt):
                    current_text = chunk.text if hasattr(chunk, 'text') else str(chunk)
                    
                    if current_text.startswith(full_text) and len(full_text) > 0:
                        delta_text = current_text[len(full_text):]
                        full_text = current_text
                    else:
                        delta_text = current_text
                        full_text += current_text

                    if delta_text:
                        data_chunk = {
                            "id": f"chatcmpl-{int(time.time())}",
                            "object": "chat.completion.chunk",
                            "created": int(time.time()),
                            "model": requested_model,
                            "choices": [{"index": 0, "delta": {"content": delta_text}, "finish_reason": None}]
                        }
                        yield f"data: {json.dumps(data_chunk)}\n\n"
                
                stop_chunk = {
                    "id": f"chatcmpl-{int(time.time())}",
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": requested_model,
                    "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]
                }
                yield f"data: {json.dumps(stop_chunk)}\n\n"
                yield "data: [DONE]\n\n"
                logger.info("Selesai generate response (Streaming).")
                
            return StreamingResponse(event_generator(), media_type="text/event-stream")
            
        response = await client.generate_content(prompt)
        response_text = response.text if hasattr(response, 'text') else str(response)
        
        logger.info("Selesai generate response (Non-Stream).")
        return JSONResponse({
            "id": f"chatcmpl-{int(time.time())}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": requested_model,
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": response_text},
                "finish_reason": "stop"
            }]
        })
    except Exception as e:
        logger.error(f"Error: {str(e)}")
        return JSONResponse({"error": str(e)}, status_code=500)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=3001)