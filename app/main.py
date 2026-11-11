from fastapi import FastAPI, Request, Header, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sse_starlette.sse import EventSourceResponse
from pathlib import Path
from typing import Optional
import asyncio
import json
import time
import secrets

from .config import get_settings

settings = get_settings()
app = FastAPI(title=settings.APP_NAME)

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# -------------------------
# Estado em memória (temporário)
# -------------------------
usuarios = {}
eventos_por_token = {}
ultimo_n = {}
historico = {}  # token -> lista de mensagens para o contexto da IA


def gerar_token() -> str:
    return secrets.token_urlsafe(24)


def exigir_token(x_alfred: Optional[str] = Header(None, alias="x-alfred")):
    if not x_alfred:
        raise HTTPException(status_code=401, detail="Token ausente")
    if x_alfred not in usuarios:
        usuarios[x_alfred] = {
            "nome": settings.APP_NAME,
            "plano": "gratuito",
            "gasto_hoje": 0.0,
            "modo": "supervisionado",
        }
        eventos_por_token[x_alfred] = []
        ultimo_n[x_alfred] = 0
        historico[x_alfred] = []
    return x_alfred


def adicionar_evento(token: str, tipo: str, **dados):
    n = ultimo_n.get(token, 0) + 1
    ultimo_n[token] = n
    evento = {"n": n, "tipo": tipo, "t": time.strftime("%H:%M:%S"), **dados}
    eventos_por_token.setdefault(token, []).append(evento)
    return evento


# -------------------------
# Função da IA (Groq)
# -------------------------
async def chamar_ia(token: str, texto: str) -> str:
    if not settings.GROQ_API_KEY:
        return "Ainda não tenho a chave da IA configurada. Peça ao administrador para adicionar a GROQ_API_KEY."

    try:
        from groq import Groq
        client = Groq(api_key=settings.GROQ_API_KEY)

        # Monta o histórico curto
        mensagens = [
            {
                "role": "system",
                "content": (
                    f"Você é o {settings.APP_NAME}, um assistente virtual brasileiro "
                    "inteligente, direto, educado e com personalidade. "
                    "Responda sempre em português do Brasil, de forma clara e natural. "
                    "Seja útil e objetivo."
                ),
            }
        ]

        # Adiciona últimas mensagens do histórico (máximo 8)
        for m in historico.get(token, [])[-8:]:
            mensagens.append(m)

        mensagens.append({"role": "user", "content": texto})

        completion = client.chat.completions.create(
            model=settings.GROQ_MODEL,
            messages=mensagens,
            temperature=0.7,
            max_tokens=2000,
        )

        resposta = (completion.choices[0].message.content or "").strip()

        # Atualiza histórico
        historico.setdefault(token, []).append({"role": "user", "content": texto})
        historico[token].append({"role": "assistant", "content": resposta})

        return resposta

    except Exception as e:
        return f"Erro ao falar com a IA: {str(e)}"


# -------------------------
# Páginas
# -------------------------
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    html_path = STATIC_DIR / "index.html"
    if not html_path.exists():
        raise HTTPException(status_code=404, detail="Front-end não encontrado")

    conteudo = html_path.read_text(encoding="utf-8")
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
        historico[token] = []

    conteudo = conteudo.replace("__NOME__", settings.APP_NAME)
    conteudo = conteudo.replace("__TOKEN__", token)

    response = HTMLResponse(content=conteudo)
    response.set_cookie(
        "vt_token", token, httponly=True, samesite="lax", max_age=60 * 60 * 24 * 30
    )
    return response


@app.get("/login", response_class=HTMLResponse)
async def pagina_login(request: Request):
    return templates.TemplateResponse(
        "login.html", {"request": request, "nome": settings.APP_NAME}
    )


@app.get("/minha-conta", response_class=HTMLResponse)
async def pagina_minha_conta(request: Request):
    token = request.cookies.get("vt_token")
    usuario = usuarios.get(token, {})
    return templates.TemplateResponse(
        "minha_conta.html",
        {
            "request": request,
            "nome": settings.APP_NAME,
            "usuario": usuario,
            "token": token or "",
        },
    )


# -------------------------
# API
# -------------------------
@app.get("/api/estado")
async def api_estado(token: str = Header(None, alias="x-alfred")):
    token = exigir_token(token)
    u = usuarios[token]
    return {
        "cerebro_pronto": bool(settings.GROQ_API_KEY),
        "provedor": "groq" if settings.GROQ_API_KEY else "nenhum",
        "modelo": settings.GROQ_MODEL,
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

    if not texto:
        raise HTTPException(status_code=400, detail="Texto vazio")

    # Evento do usuário
    adicionar_evento(token, "usuario", texto=texto)

    # Chama a IA
    resposta = await chamar_ia(token, texto)

    # Evento da resposta
    adicionar_evento(token, "resposta", texto=resposta)

    return {"ok": True}


@app.post("/api/transcrever")
async def api_transcrever(
    arquivo: UploadFile = File(...),
    token: str = Header(None, alias="x-alfred"),
):
    token = exigir_token(token)
    # Por enquanto ainda é stub (próximo passo)
    return {"texto": "(transcrição de voz ainda não conectada)"}


@app.get("/api/eventos")
async def api_eventos(t: str, desde: int = 0):
    if t not in usuarios:
        raise HTTPException(status_code=401, detail="Token inválido")

    async def gerador():
        for ev in eventos_por_token.get(t, []):
            if ev["n"] > desde:
                yield {"data": json.dumps(ev, ensure_ascii=False)}

        ultimo = max(desde, ultimo_n.get(t, 0))
        while True:
            await asyncio.sleep(0.35)
            for ev in eventos_por_token.get(t, []):
                if ev["n"] > ultimo:
                    ultimo = ev["n"]
                    yield {"data": json.dumps(ev, ensure_ascii=False)}

    return EventSourceResponse(gerador())


@app.post("/api/parar")
async def api_parar(token: str = Header(None, alias="x-alfred")):
    token = exigir_token(token)
    adicionar_evento(token, "parado")
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


@app.post("/api/webhook/mercadopago")
async def webhook_mp(request: Request):
    body = await request.json()
    print("Webhook Mercado Pago:", body)
    return {"ok": True}


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "ia": bool(settings.GROQ_API_KEY),
    }
