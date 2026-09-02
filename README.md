# 🤖 WhatsApp Bot com IA

Bot de WhatsApp que responde mensagens automaticamente usando LLM local gratuito
(9router), construído sobre a [Evolution API v2](https://doc.evolution-api.com).

## Arquitetura

```
WhatsApp ⇄ Evolution API (Docker: :8083)
              │ webhook MESSAGES_UPSERT
              ▼
         bot.py (:8084, systemd user service)
              │ OpenAI-compatible
              ▼
         9router (:20131) → LLM gratuito
```

| Componente | Tecnologia |
|---|---|
| Gateway WhatsApp | Evolution API 2.3.7 (Baileys) + Postgres 15 + Redis 7 (Docker Compose) |
| Bot | Python 3.14 + aiohttp (única dependência) |
| IA | 9router local — modelo default `ollama/gpt-oss:120b` |

## Setup

```bash
# 1. Subir a Evolution API
docker compose up -d

# 2. Configurar .env (ver seção abaixo) e criar instância + conectar número
curl -X POST http://localhost:8083/instance/create \
  -H 'apikey: <API_KEY>' -H 'Content-Type: application/json' \
  -d '{"instanceName":"bot_ia","integration":"WHATSAPP-BAILEYS"}'

# Pareamento por código (mais confiável que QR):
curl -H 'apikey: <API_KEY>' 'http://localhost:8083/instance/connect/bot_ia?number=5511956470308'
# → digite o pairingCode no app: Dispositivos conectados → Conectar c/ número

# 3. Apontar o webhook para o bot
curl -X POST http://localhost:8083/webhook/set/bot_ia \
  -H 'apikey: <API_KEY>' -H 'Content-Type: application/json' \
  -d '{"webhook":{"enabled":true,"url":"http://172.17.0.1:8084/webhook","events":["MESSAGES_UPSERT"]}}'

# 4. Instalar e ativar o serviço do bot
pip install -r requirements.txt
cp bot.service ~/.config/systemd/user/
systemctl --user daemon-reload && systemctl --user enable --now whatsapp-bot
```

## Variáveis de ambiente (bot.py)

| Var | Default | Descrição |
|---|---|---|
| `EVOLUTION_URL` | `http://localhost:8083` | Endereço da Evolution API |
| `EVOLUTION_API_KEY` | `CHANGE_ME` | apikey da Evolution (obrigatória — setar via env.local) |
| `EVOLUTION_INSTANCE` | `bot_ia` | Nome da instância |
| `AI_URL` | `http://localhost:20131/v1/chat/completions` | Endpoint OpenAI-compatível |
| `AI_MODEL` | `9router/ollama/gpt-oss:120b` | Modelo de resposta |
| `SYSTEM_PROMPT` | assistente PT-BR conciso | Persona do bot |
| `RESPOND_IN_GROUPS` | `false` | Responder em grupos (com menção) |
| `REPLY_DELAY_MS` | `1200` | Delay "digitando..." antes de responder |

## Comportamento

- ✅ Responde mensagens de texto em chats privados
- 👥 Grupos: responde **somente quando o bot é mencionado** (`@bot` no texto ou
  na legenda de mídia); sem menção, ignora silenciosamente (`RESPOND_IN_GROUPS=false`
  desliga grupos por completo)
- 🛡️ Anti-loop: ignora mensagens próprias (`fromMe`) + dedup por id de mensagem
- 🧠 Histórico de conversa por chat (últimas 12 trocas, em memória)
- 😅 Mensagens sem texto/mídia suportada são ignoradas silenciosamente
- 🎨 Imagem/vídeo → figurinha (ver seção acima); figurinha citada + menção → reenvia com seu pack

## 🎨 Figurinhas (imagens, vídeos e figurinhas citadas)

Mande uma **imagem** ou **vídeo curto** para o bot e ele responde com uma
figurinha pronta — em grupos, **só quando você mencionar o bot** (@menção,
inclusive na legenda). Responder uma figurinha citando o bot também funciona.

| Recurso | Detalhe |
|---|---|
| Formato | WebP 512×512 |
| Enquadramento | **Crop 1:1** centralizado (`STICKER_MODE=crop`) ou letterbox (`full`) |
| Metadados do pack | EXIF injetado na posição que o WhatsApp lê (chunk após VP8X) — nome do pack aparece ao tocar na figurinha |
| Vídeos | ffmpeg → WebP animado 15fps, máx `STICKER_MAX_VIDEO_S` (8s) |
| Pack padrão | `STICKER_PACK_NAME=ismaeldev-bot`, autor `ismaeldev` |

Pipeline: base64 do webhook → Pillow (crop/scale) ou ffmpeg (vídeo) →
remux EXIF → `POST /message/sendSticker`.

## 🛡️ Guardrails anti-ban

Número de WhatsApp que se comporta como bot recebe ban. O bot tem múltiplas
camadas de proteção — todas ativas por padrão:

| Proteção | Default (warm-up) | Descrição |
|---|---|---|
| `WARMUP` | `true` | Regime conservador para número novo/jovem |
| `DAILY_SEND_CAP` | 25 (`false`: 150) | Máximo de mensagens enviadas por dia |
| `HOURLY_SEND_CAP` | 6 (`false`: 25) | Máximo global por hora |
| `PER_CHAT_HOURLY_CAP` | 4 (`false`: 8) | Máximo por chat/hora |
| `NEW_CONTACT_DAILY_CAP` | 3 (`false`: 5) | Contato novo tem teto próprio até "amadurecer" |
| `MIN_REPLY_GAP_S` | 20s | Intervalo mínimo entre respostas no mesmo chat |
| `ACTIVE_HOURS` | `8-23` | Fora desse horário não responde (bot às 3h = automação) |
| `MAX_REPLY_CHARS` | 900 | Respostas curtas (textão = spam) |
| `ALLOW_LINKS` | `false` | **Remove links** das respostas da IA (maior gatilho de ban) |
| Delay humanizado | ~1.2-5.7s | "Digitando..." proporcional ao tamanho + jitter ±20% |
| Opt-out LGPD | — | Contato manda `parar/sair/stop` → blacklist persistente; `voltar` reativa |

Contadores diários, blacklist e maturidade de contatos ficam em `state.json`
(sobrevivem a restart — um reboot não zera os limites).

**Recomendação:** mantenha `WARMUP=true` pelas primeiras semanas. Para
"graduar" o número, troque para `WARMUP=false` no service do systemd
(`Environment=WARMUP=false`) e reinicie.

## Comandos úteis

```bash
systemctl --user status whatsapp-bot     # estado do serviço
journalctl --user -u whatsapp-bot -f     # logs ao vivo
docker compose ps                        # containers
curl localhost:8084/health               # healthcheck do bot
```

## Licença

MIT
