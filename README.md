# Verttano

Assistente por voz com rosto holográfico.

## O que já está nesta versão

- Front-end v7-1 (rosto holográfico + microfone + texto)
- Estrutura FastAPI pronta para o Render
- Páginas `/login` e `/minha-conta`
- Rotas da API compatíveis com o front-end
- Configuração de ambiente (`.env`)
- Arquivo `render.yaml` para deploy

## O que ainda é stub (precisa do núcleo real)

- Cérebro Groq (respostas reais)
- Transcrição de voz (Whisper via Groq)
- Contas e planos completos
- Webhook e assinaturas do Mercado Pago

## Como rodar localmente

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# edite o .env e coloque pelo menos a GROQ_API_KEY
uvicorn app.main:app --reload --port 8000
```

Abra: http://localhost:8000

## Como fazer deploy no Render (gratuito)

1. Suba este projeto para um repositório no **GitHub**
2. No [Render Dashboard](https://dashboard.render.com):
   - **New → Blueprint**
   - Conecte o repositório
   - O Render lê o `render.yaml` automaticamente
3. Preencha as variáveis de ambiente:
   - `GROQ_API_KEY`
   - `MP_ACCESS_TOKEN` (teste)
   - `MP_WEBHOOK_SECRET`
   - `URL_BASE` = a URL que o Render gerar (ex: `https://verttano.onrender.com`)
4. Deploy

Depois do deploy, abra a URL e teste o rosto + microfone (precisa de HTTPS, que o Render já fornece).

## Estrutura

```
verttano/
├── app/
│   ├── main.py          # rotas e app FastAPI
│   └── config.py        # configurações
├── static/
│   └── index.html       # front-end v7-1
├── templates/
│   ├── login.html
│   └── minha_conta.html
├── requirements.txt
├── render.yaml
├── .env.example
└── README.md
```

## Próximos passos

1. Conectar o núcleo real de IA (Groq + cota)
2. Ligar login real + planos
3. Ativar webhook do Mercado Pago
4. Modo mãos-livres
