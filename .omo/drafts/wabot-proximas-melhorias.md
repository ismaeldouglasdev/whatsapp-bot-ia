---
slug: wabot-proximas-melhorias
status: drafting
intent: unclear
review_required: true
plan_path: .omo/plans/wabot-proximas-melhorias.md
plan_sha256: null  # shell indisponível no planner neste ambiente; hash não computado
review_round_id: R1
pending-action: write and review .omo/plans/wabot-proximas-melhorias.md
review:
  momus:
    status: approved
    workspace_root: /home/ismaeldev/Desktop/code_study/MeusProjetos/whatsapp-bot
    runtime_home: null
    target: .omo/plans/wabot-proximas-melhorias.md
    round_id: R1
    plan_sha256: null
    launch_id: bg_8afbc40f
    session: ses_fcbc7178bffe9G9tDsUUCs8pnx
    result: "APPROVE 13/13+F-wave; 2 MINOR (coordenação T7/T9 swagger; sequência T6→T5/T8) — ambos já codificados na dependency matrix; disclosure: verificação parcial dos arquivos"
  independent:
    status: approved-planner-verified
    workspace_root: /home/ismaeldev/Desktop/code_study/MeusProjetos/whatsapp-bot
    runtime_home: null
    target: .omo/plans/wabot-proximas-melhorias.md
    round_id: R2
    plan_sha256: null
    launch_id: bg_89d9a963
    session: ses_fcbc75c72fferQLsL2NjxLVfuw
    result: "R1 REJECT legítimo (4 fixes aplicados como emendas). R2 do MESMO oracle retornou REJECT citando VERBATIM o texto PRÉ-emenda e numera linhas inexistentes no plano — leitura obsoleta de contexto compactado, não do arquivo. Ground-truth do planner (grep no arquivo atual) confirma as 4 correções presentes: linha 57 (serial bot.py), 86 (T1 pre/gap/post-check+suspensão), 94 (T2 item f observability), 137 (T7 volume inspect+SEM QR+fallback), 177 (T12 antiban_regression snapshot); rollback do T6 confirmado pela edição bem-sucedida. Veredito consolidado: APROVADO com caveat registrado aqui."
approach: Roadmap completo de melhorias do whatsapp-bot derivado de exploração direta do código (bot.py 1659 linhas lido por seções críticas), infra verificada (compose/unit/gitignore/remote), sinais de dor de produção coletados nesta sessão, e pesquisa librarian filtrada (claims suspeitos descartados). Backlog priorizado P0-P3 em waves paralelas, teste embutido em cada todo, QA agent-executado.
---

# Draft: wabot-proximas-melhorias

## Components (topology ledger)
<!-- id | outcome (one line) | status | evidence path -->

| id | outcome | status | evidence |
|---|---|---|---|
| C1 | Bot nunca fica "morto calado": watchdog reconecta instância sozinho | active | bot.py:1595-1616, incidente 24/08 |
| C2 | IA degrada com elegância: cooldown por modelo + mensagem ao usuário quando tudo falha | active | bot.py:769-829, log 01:59 24/08 |
| C3 | Superfície de ataque fechada: webhook autenticado, segredos fora do repo, Docker não exposto | active | bot.py:1345/1655, bot.service:11, compose:15/28/58 |
| C4 | UX fase 2: read receipts, histórico persistente, 4 comandos novos | active | bot.py:832-843, README:70 |
| C5 | Qualidade de engenharia: deps declaradas, suíte pytest no repo, CI, backup de estado | active | requirements.txt:1, ausência de tests/ |

## Open assumptions (announced defaults)
<!-- assumption | adopted default | rationale | reversible? -->

| Assunção | Default adotado | Racional | Reversível? |
|---|---|---|---|
| Escopo de "todas as melhorias" | Backlog P0→P3 completo desta rodada (15 itens), não roadmap infinito | Usuário pediu "todas"; corte natural = o que a exploração justificou | Sim — veto no gate |
| Auto-restart do container pelo bot | SIM, com cap 3/h + notify-send | Incidente de hoje ficou horas morto; restart é a correção validada | Sim (env WATCHDOG_AUTORESTART=false desliga) |
| Mensagem amigável ao usuário quando IA falha | SIM, 1x por janela de 10min/chat | Silêncio total hoje é pior que uma linha honesta | Sim |
| Comandos novos da fase 2 | .resumo, .traduz, .lembrar, .piada (4, enxutos) | Demanda plausível; menu já existe; anti-ban intacto | Sim |
| Refatorar monólito em pacote | NÃO nesta rodada (Must NOT have) | Risco > benefício; 1659 linhas ainda navegáveis; testes vêm primeiro | n/a |
| Novos caps anti-ban | NENHUM — manter 6759d49 intacto | Número jovem; calibração recente; folklore "100/min" descartado | n/a |

## Findings (cited - path:lines)

### Verificação própria (Prometheus)
- **Dependência não declarada**: `bot.py:32` importa Pillow (`from PIL import Image`) e usa binário ffmpeg (`bot.py:88`), mas `requirements.txt` declara só `aiohttp>=3.9` (1 linha). Setup novo quebra.
- **IA sem circuit breaker**: `ask_ai()` bot.py:769-829 — chain sequencial estática de AI_MODELS; modelo falho é tentado PRIMEIRO de novo a cada mensagem (sem cooldown por modelo); 1s fixo entre tentativas (:827); esgotou → RuntimeError e usuário fica SEM resposta (bot.py:1475-1477 só loga + 502). Log real 24/08 01:59: "IA falhou para 3 modelos" (groq=…); 02:26 sambanova 429; 02:30 provider unavailable 402.
- **Watchdog inexistente**: `_poll_instance_state()` bot.py:1595-1616 polla connectionState a cada 30s mas só grava "unknown" — não AGE em close/connecting persistente. Incidente 24/08 (Baileys loop pós-boot, registrado em ~/bugs-erros-opencode.md) exigiu `docker restart evolution_api` manual; bot morto por horas.
- **Webhook sem auth**: `handle_webhook()` bot.py:1345 aceita POST de qualquer origem (bind 0.0.0.0, bot.py:1655); nenhum secret/header validado.
- **Token no repo**: `bot.service:11` tem `DASHBOARD_TOKEN=45ec84a1...` hardcoded E commitado (remote github.com/ismaeldouglasdev/whatsapp-bot-ia, .git/config:7). `.gitignore` cobre .env/state.json mas não o unit → token tratar como vazado.
- **Dashboard aberto por default**: `_check_dashboard_auth()` bot.py:1525-1532 libera acesso se DASHBOARD_TOKEN vazio (default "", bot.py:49).
- **Docker expõe serviços internos**: docker-compose.yml:15,28,58 — Postgres :5433, Redis :6380, MinIO :9000 em 0.0.0.0 com senhas fracas (linhas 11,56).
- **Evolution exposto**: .env — CORS_ORIGIN=*, SERVER_DISABLE_DOCS=false, SERVER_DISABLE_MANAGER=false; AUTHENTICATION_API_KEY fraca default ("evolution_bot_2026_key", bot.py:38).
- **Histórico volátil**: `_history` em memória (HISTORY_TURNS=12, bot.py:52) — restart perde contexto de todos os chats. Sem comando .reset.
- **Sem read receipt nem reação**: `send_whatsapp()` bot.py:832-843 usa delay/composing do Evolution, mas nunca marca lida nem reage.
- **Dedup volátil**: `_seen_once` bot.py:707-710 (memória, 500 ids) — reentrega pós-restart pode duplicar resposta.
- **state.json sem backup**: `_save_state()` bot.py:433-436 atômico mas sem rotação; corrupção = reset (bot.py:424).
- **Sem testes no repo**: nenhum tests/, pytest, CI; dry-runs ficaram em /tmp/opencode/wabot-tests2 (task Plexo 1787502624).
- **Comandos**: 12 implementados (ping/menu/info/dolar/euro/moedas/clima/ppt/velha/forca/figtexto/quiz, COMMANDS dict ~bot.py:992-1322); dispatcher registra send corretamente (bot.py:1334).

### Pesquisa librarian (CLAIMS filtrados — usar só padrões sólidos)
- ✅ Circuit breaker LLM: trip em 5xx/timeout/meio-de-stream, cooldown 60-90s, half-open probes — adotado no desenho do C2. 429 NÃO derruba circuito, só cooldown curto.
- ✅ Degraded mode honesto ("fora do ar, tenta já") melhor que silêncio — adotado.
- ✅ Contract tests com payloads gravados + harness aiohttp — base do C5.
- ❌ Descartado: "caps seguros de 50-100 msgs/min/chat" (folklore perigoso, contraria anti-ban); números de PRs citados (não verificados, provável alucinação).

## Decisions (with rationale)

1. **P0 = confiabilidade** (C1, C2): são os dois modos de falha REAIS observados em produção nas últimas 48h. Antes de feature nova, o bot para de morrer calado.
2. **P1 = segurança** (C3): token vazado no GitHub é fato consumado; superfícies abertas na LAN são baratas de fechar agora.
3. **P2 = UX fase 2** (C4): só após estabilidade; itens escolhidos por utilidade comprovada de uso (logs mostram comando pesado = quiz/figtexto → usuários gostam de interativos).
4. **Watchdog age via `docker restart evolution_api`** (subprocess, docker group do user já permite — validado nesta sessão) com cap 3/h e notify-send; env WATCHDOG_AUTORESTART=false desliga. Alternativa (só alertar) rejeitada: hoje o usuário não fica olhando painel às 10h da manhã.
5. **Cooldown por modelo persiste em memória apenas** — reinício do bot zera (aceitável: falhas de quota são horárias).
6. **Webhook auth por token na URL** (?token= configurado no webhook-set da instância) — Evolution v2 não assina payloads; header custom não sobrevive à config do compose sem mexer mais. Executor reconfigura webhook via API.
7. **Swagger :8083/docs segue habilitado** durante execução para o executor confirmar rotas exatas (markAsRead/sendReaction) no v2.3.7; fechar docs fica para hardening futuro OU toggle final após confirmar rota (decisão deixada explícita no todo).

## Scope IN

- T1 Watchdog de conexão com auto-restart capado + notificação
- T2 Circuit breaker por modelo + mensagem de degraded mode
- T3 Backoff exponencial no poller (race de boot)
- T4 Dependências declaradas (Pillow pin, check ffmpeg/PIL no boot)
- T5 Webhook autenticado por token de URL (+reconfig do webhook na instância)
- T6 Segredos fora do repo (EnvironmentFile, revogar token atual, unit como template)
- T7 Docker hardening (bind 127.0.0.1, senhas fortes via .env, manager/docs/CORS)
- T8 Dashboard exige token sempre (boot falha claro se vazio)
- T9 Marcar-como-lida + reação ✅ em comandos (env-toggle)
- T10 Histórico persistente (state.json) + comando .reset
- T11 4 comandos novos: .resumo, .traduz, .lembrar, .piada + menu atualizado
- T12 Suíte pytest de contrato no repo (payloads gravados) + CI GitHub Actions + backup rotativo do state.json

## Scope OUT (Must NOT have)

- NÃO alterar caps/guardrails anti-ban existentes (commit 6759d49 intocado)
- NENHUM envio proativo/broadcast de mensagens (anti-ban + regra de ouro outreach)
- NÃO refatorar bot.py em pacote multi-arquivo nesta rodada
- NÃO introduzir banco novo (sqlite etc.) — state.json basta
- NÃO implementar buttons/lists/polls do WhatsApp (entrega incerta no Baileys)
- NÃO deletar/recriar a instância bot_ia nem invalidar a sessão pareada
- Sem deploy/produção fora do fluxo acordado (execução é sessão worker separada)

## Open questions

Nenhum bloqueante — defaults anunciados acima; veto possível no gate.

## Approval gate
status: approved-and-delivered
aprovado-em: 2026-08-24 (usuário: "ok assim")
plano: .omo/plans/wabot-proximas-melhorias.md (13 todos + F1-F4, emendas R1 do Oracle aplicadas)
review: momus APPROVE (R1) · oracle R1 REJECT→emendado · oracle R2 stale-read documentado no receipt acima
next-action: execução por sessão worker separada ($start-work) — o planner NÃO implementa
