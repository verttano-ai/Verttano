from fastapi import FastAPI, Request, Header, HTTPException, UploadFile, File, Form
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sse_starlette.sse import EventSourceResponse
from pathlib import Path
import asyncio
import json
import time
from typing import Optional

from .config import get_settings

settings = get_settings()
app = FastAPI(title=settings.APP_NAME)

# Caminhos
BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# -------------------------
# Estado simples em memória (substituir depois pelo núcleo real)
# -------------------------
usuarios = {}          # token -> dados
eventos_por_token = {} # token -> lista de eventos
ultimo_n = {}          # token -> último número de evento


def gerar_token() -> str:
    import secrets
    return secrets.token_urlsafe(24)


def exigir_token(x_alfred: Optional[str] = Header(None, alias="x-alfred")):
    if not x_alfred:
        raise HTTPException(status_code=401, detail="Token ausente")
    if x_alfred not in usuarios:
        # Cria sessão de teste automaticamente (temporário)
        usuarios[x_alfred] = {
            "nome": settings.APP_NAME,
            "plano": "gratuito",
            "gasto_hoje": 0.0,
            "modo": "supervisionado",
        }
        eventos_por_token[x_alfred] = []
        ultimo_n[x_alfred] = 0
    return x_alfred


# -------------------------
# Páginas
# -------------------------

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Serve o front-end v7-1 substituindo os placeholders."""
    html_path = STATIC_DIR / "index.html"
    if not html_path.exists():
        raise HTTPException(status_code=404, detail="Front-end não encontrado")

    conteudo = html_path.read_text(encoding="utf-8")

    # Token de sessão simples (em produção usar login real)
    token = request.cookies.get("vt_token") or gerar_token()
    if token not in usuarios:
        usuarios[token] = {
            "nome": settings.APP_NAME,
            "plano": "gratuito",
            "gasto_hoje": 0.0,
            "modo": "supervisionado",
        }
        eventos_por_token[token] = []
        ultimo_n[token] = 0

    conteudo = conteudo.replace("__NOME__", settings.APP_NAME)
    conteudo = conteudo.replace("__TOKEN__", token)

    response = HTMLResponse(content=conteudo)
    response.set_cookie("vt_token", token, httponly=True, samesite="lax", max_age=60*60*24*30)
    return response


@app.get("/login", response_class=HTMLResponse)
async def pagina_login(request: Request):
    return templates.TemplateResponse("login.html", {
        "request": request,
        "nome": settings.APP_NAME,
    })


@app.get("/minha-conta", response_class=HTMLResponse)
async def pagina_minha_conta(request: Request):
    token = request.cookies.get("vt_token")
    usuario = usuarios.get(token, {})
    return templates.TemplateResponse("minha_conta.html", {
        "request": request,
        "nome": settings.APP_NAME,
        "usuario": usuario,
        "token": token or "",
    })


# -------------------------
# API – compatível com o front-end v7-1
# -------------------------

@app.get("/api/estado")
async def api_estado(token: str = Header(None, alias="x-alfred")):
    token = exigir_token(token)
    u = usuarios[token]
    return {
        "cerebro_pronto": bool(settings.GROQ_API_KEY),
        "provedor": "groq" if settings.GROQ_API_KEY else "nenhum",
        "modelo": "llama-3.3-70b-versatile",
        "gasto_hoje": round(u.get("gasto_hoje", 0), 4),
        "limite": settings.LIMITE_GRATUITO_DIARIO_USD,
        "modo": u.get("modo", "supervisionado"),
        "ocupado": False,
        "plano": u.get("plano", "gratuito"),
    }


@app.post("/api/mensagem")
async def api_mensagem(request: Request, token: str = Header(None, alias="x-alfred")):
    token = exigir_token(token)
    body = await request.json()
    texto = (body.get("texto") or "").strip()
    modo = body.get("modo", "supervisionado")

    if not texto:
        raise HTTPException(status_code=400, detail="Texto vazio")

    n = ultimo_n[token] + 1
    ultimo_n[token] = n
    eventos_por_token[token].append({
        "n": n,
        "tipo": "usuario",
        "texto": texto,
        "t": time.strftime("%H:%M:%S"),
    })

    # Resposta simples de teste (substituir pelo cérebro real depois)
    resposta = f"Recebi: “{texto}”. O núcleo de IA ainda está sendo ligado ao front-end."
    n2 = ultimo_n[token] + 1
    ultimo_n[token] = n2
    eventos_por_token[token].append({
        "n": n2,
        "tipo": "resposta",
        "texto": resposta,
        "t": time.strftime("%H:%M:%S"),
    })

    return {"ok": True}


@app.post("/api/transcrever")
async def api_transcrever(
    arquivo: UploadFile = File(...),
    token: str = Header(None, alias="x-alfred"),
):
    token = exigir_token(token)
    # Stub: em produção chama Groq Whisper / modelo de áudio
    return {"texto": "(transcrição de voz ainda não conectada ao Groq)"}


@app.get("/api/eventos")
async def api_eventos(t: str, desde: int = 0):
    if t not in usuarios:
        raise HTTPException(status_code=401, detail="Token inválido")

    async def gerador():
        # Envia eventos antigos primeiro
        for ev in eventos_por_token.get(t, []):
            if ev["n"] > desde:
                yield {"data": json.dumps(ev, ensure_ascii=False)}
        # Depois fica escutando novos
        ultimo = max(desde, ultimo_n.get(t, 0))
        while True:
            await asyncio.sleep(0.4)
            for ev in eventos_por_token.get(t, []):
                if ev["n"] > ultimo:
                    ultimo = ev["n"]
                    yield {"data": json.dumps(ev, ensure_ascii=False)}

    return EventSourceResponse(gerador())


@app.post("/api/parar")
async def api_parar(token: str = Header(None, alias="x-alfred")):
    token = exigir_token(token)
    n = ultimo_n[token] + 1
    ultimo_n[token] = n
    eventos_por_token[token].append({
        "n": n,
        "tipo": "parado",
        "t": time.strftime("%H:%M:%S"),
    })
    return {"ok": True}


@app.post("/api/confirmar")
async def api_confirmar(request: Request, token: str = Header(None, alias="x-alfred")):
    token = exigir_token(token)
    body = await request.json()
    return {"ok": True, "decisao": body.get("decisao")}


@app.get("/api/painel")
async def api_painel(token: str = Header(None, alias="x-alfred")):
    token = exigir_token(token)
    return {
        "automacoes": [],
        "apps": [],
        "conectores": [],
        "mcp": [],
    }


@app.post("/api/automacao/rodar")
async def api_automacao_rodar(request: Request, token: str = Header(None, alias="x-alfred")):
    token = exigir_token(token)
    return {"ok": True}


# -------------------------
# Webhook Mercado Pago (stub)
# -------------------------

@app.post("/api/webhook/mercadopago")
async def webhook_mp(request: Request):
    # Validar assinatura com MP_WEBHOOK_SECRET em produção
    body = await request.json()
    print("Webhook Mercado Pago recebido:", body)
    return {"ok": True}


# -------------------------
# Healthcheck
# -------------------------

@app.get("/health")
async def health():
    return {"status": "ok", "app": settings.APP_NAME}
