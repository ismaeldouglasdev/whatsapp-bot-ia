# 🔧 Operações — WhatsApp Bot (Evolution API)

Guia operacional para parar, reiniciar e reativar o bot do WhatsApp.
Complementa o README (arquitetura/setup); este arquivo foca em **procedimentos
de operação do dia a dia**.

## 📌 Componentes

| Componente | O que é | Como controlar |
|---|---|---|
| `bot.py` | Lógica do bot (Python, aiohttp) | `systemctl --user whatsapp-bot` |
| `whatsapp-bot.service` | systemd user unit que roda `bot.py` | `systemctl --user` |
| Containers Docker | Evolution API + Postgres + Redis + MinIO | `docker compose` / `docker stop\|start` |

## 🛑 PARAR o bot (desligamento completo)

Para derrubar **tudo** de uma vez (ex.: número caiu, manutenção, pausa):

```bash
# 1. Parar o serviço systemd (mata bot.py + impede auto-restart)
systemctl --user stop whatsapp-bot
systemctl --user disable whatsapp-bot   # opcional: não subir no boot

# 2. Parar os containers da Evolution API
docker stop evolution_api evolution_postgres evolution_redis evolution_minio

# 3. (Opcional) forçar kill se o processo ficar órfão
pkill -f "whatsapp-bot/bot.py"

# Verificar que está tudo parado
docker ps | grep evolution          # nada deve aparecer
systemctl --user status whatsapp-bot # inactive (dead)
```

## ▶️ REATIVAR o bot

```bash
# 1. Subir os containers da Evolution API (na ordem certa)
cd ~/Desktop/code_study/MeusProjetos/whatsapp-bot
docker start evolution_minio evolution_redis evolution_postgres evolution_api
# OU, de forma idêntica: docker compose up -d

# 2. Habilitar + iniciar o serviço systemd
systemctl --user enable whatsapp-bot   # se tinha desabilitado
systemctl --user start whatsapp-bot

# 3. Verificar saúde
systemctl --user status whatsapp-bot    # active (running)
curl localhost:8084/health              # ok
docker ps | grep evolution              # 4 containers up

# 4. Se o número foi desconectado, reparear
curl -H 'apikey: <EVOLUTION_API_KEY>' \
  'http://localhost:8083/instance/connect/bot_ia?number=5511956470308'
# → Digite o pairingCode no WhatsApp: Dispositivos conectados → Conectar c/ número
```

## 🔄 Ciclo rápido (só reiniciar o bot, sem tocar Docker)

```bash
systemctl --user restart whatsapp-bot
```

## 🔑 Chaves e variáveis críticas (.env)

- `EVOLUTION_API_KEY` — apikey da Evolution API (obrigatória)
- `AI_URL` / `AI_MODEL` — roteamento de IA via 9router
- Guardrails anti-ban (WARMUP, caps horários/diários) — ver README

## ⏱️ Logs

```bash
journalctl --user -u whatsapp-bot -f    # logs do bot
docker logs -f evolution_api           # logs da Evolution API
cat ~/Desktop/code_study/MeusProjetos/whatsapp-bot/bot.log
```

## 📦 State (contadores / blacklist / maturidade)

- Arquivo: `~/Desktop/code_study/MeusProjetos/whatsapp-bot/state.json`
- Sobrevive a restart (um reboot não zera os limites anti-ban)
- Backups automáticos: `state.json.bak-*`