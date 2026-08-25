# wabot-proximas-melhorias - Work Plan

## TL;DR (For humans)
<!-- Fill this LAST, after the detailed plan below is written, so it summarizes the REAL plan. -->
<!-- Plain English for a non-engineer: NO file paths, NO todo numbers, NO wave/agent/tool names. -->

**What you'll get:** O bot do WhatsApp ganha auto-cura (quando a conexão cair, ele religa o serviço sozinho e te avisa), a IA para de falhar em silêncio (troca de modelo sozinha e avisa o usuário quando estiver fora do ar), portas e segredos que estavam expostos são trancados, e chegam novidades: o bot marca suas mensagens como lidas, lembra das conversas mesmo após reiniciar o PC, e ganha 4 comandos novos (resumir texto, traduzir, lembretes e piadas). De brinde, uma bateria de testes automatizados passa a morar no repositório, com integração contínua no GitHub.

**Why this approach:** As duas maiores dores vieram de incidentes reais das últimas 48h (bot morto por horas após reboot; IA falhando em silêncio de madrugada) — então estabilidade vem antes de feature. Segurança vem logo depois porque um token de acesso está publicado no GitHub e bancos de dados internos estão escutando na rede. Os testes entram junto com cada mudança, não no fim, para nada quebrar o número de WhatsApp vivo.

**What it will NOT do:** Não muda os limites anti-ban calibrados. Não envia nenhuma mensagem proativa nem em massa. Não reorganiza o código em vários arquivos nem instala banco de dados novo.

**Effort:** Large
**Risk:** Medium - toca o bot em produção e a sessão pareada do WhatsApp; mitigado por testes embutidos em cada item, limites anti-ban intocados e nenhum toque na instância pareada.

**Decisions I made for you:** Auto-restart do container ativo por padrão (desligável por variável); mensagem honesta ao usuário quando a IA estiver fora (máx. 1 por 10 min por conversa); exatamente 4 comandos novos; segredo do webhook passado na própria URL configurada na Evolution; Swagger da Evolution continua aberto durante a obra para confirmar rotas e é fechado no final.

Your next move: approve execution via `$start-work`. Full execution detail follows below.

---

> TL;DR (machine): Large/Medium — 13 todos em 4 waves (watchdog, breaker IA, hardening Docker/webhook/secrets/dashboard-token, receipts/histórico/4 comandos, deps/CI/backup) + onda final F1-F4; pytest embutido por todo; zero envio proativo.

## Scope
### Must have
- Watchdog de conexão com auto-restart capado (C1)
- Circuit breaker por modelo + degraded mode com mensagem ao usuário (C2)
- Backoff exponencial no poller de estado (race de boot)
- Dependências declaradas + checks de startup (Pillow/ffmpeg)
- Webhook autenticado por token de URL
- Segredos fora do repositório (EnvironmentFile) + troca do token vazado
- Docker hardening: bind 127.0.0.1, senhas fortes, CORS restrito, manager/docs fechados no fim
- Dashboard/API exigem token sempre
- Marcar-como-lida + reação ✅ em comandos (env-toggle)
- Histórico de conversa persistente + comando .reset
- Comandos novos: .resumo, .traduz, .lembrar, .piada + menu atualizado
- Suíte pytest de contrato no repo + CI GitHub Actions + ruff
- Backup rotativo diário do state.json

### Must NOT have (guardrails, anti-slop, scope boundaries)
- NÃO alterar caps/guardrails anti-ban (`DAILY_SEND_CAP`/`HOURLY_SEND_CAP`/`PER_CHAT_HOURLY_CAP`/`NEW_CONTACT_DAILY_CAP`/`MIN_REPLY_GAP_S` e lógica de `_rate_block_reason` intocados)
- NENHUM envio proativo/broadcast/agendamento em massa (anti-ban + regra de ouro de outreach)
- NÃO refatorar bot.py em pacote multi-arquivo nesta rodada (toda mudança vive no monólito atual)
- NÃO introduzir sqlite/banco novo — persistência continua em state.json
- NÃO implementar buttons/lists/polls do WhatsApp
- NÃO deletar/recriar/logout na instância `bot_ia`; NÃO invalidar sessão pareada
- NÃO commitar segredo algum (nem token novo); unit do systemd segue no repo mas SEM segredos

## Verification strategy
> Zero human intervention - all verification is agent-executed.
- Test decision: tests-after embutido em CADA todo (pytest + aiohttp.test_utils; fixtures JSON gravados dos formatos reais do webhook). Framework: pytest>=8, ruff lint.
- Evidence: `.omo/evidence/task-<N>-wabot-proximas-melhorias.<ext>` (fora de ulw-loop usa-se `.omo/evidence/`)
- Smoke de produção agent-executado: `curl localhost:8084/health`, `journalctl --user -u whatsapp-bot.service` greps, `curl -H "Authorization: Bearer $TOKEN" localhost:8084/api/state`, `ss -tlnp` para binds, `docker ps` + connectionState=open. Mensagem real de teste (`.ping`) é disparada pelo USUÁRIO apenas na verificação final F3.

## Execution strategy
### Parallel execution waves
> Target 5-8 todos per wave. REGRA ANTI-CONFLITO (Oracle R1): todos que editam `bot.py` executam SERIALMENTE mesmo dentro da mesma wave (um worker por vez no arquivo); só paralelizam itens de arquivos distintos (compose/.env/unit/workflows/tests).

- **Wave 1 (T1→T2→T4 em série no bot.py; T4 pode sobrepor ao final):** T1 watchdog · T2 circuit breaker · T4 deps/startup checks
- **Wave 2 (após Wave 1; T3,T5,T8 em série no bot.py):** T3 backoff poller · T5 webhook token (arquivo+API) · T6 secrets (unit/env.local — paralelizável com T5) · T8 dashboard token
- **Wave 3 (em série no bot.py):** T9 receipts+reações (+fecha swagger no fim) · T10 histórico+.reset · T11 comandos novos · T7 docker hardening (compose/.env, paralelizável com os demais)
- **Wave 4:** T12 CI+fixtures+ruff+push · T13 backup rotativo

### Dependency matrix
| Todo | Depends on | Blocks | Can parallelize with |
| --- | --- | --- | --- |
| T1 | — | T2, T3 (mesmo arquivo: serial) | T6, T7 |
| T2 | T1 | T3, T8-T11 (serial bot.py) | T6, T7 |
| T4 | — | — | T6, T7 |
| T3 | T1, T2 | T8-T11 (serial) | T6, T7 |
| T5 | T6 | — | T7 |
| T6 | — | T5 | T1-T4 (arquivos distintos) |
| T7 | — | — | qualquer um de arquivo distinto |
| T8 | T6 | T9-T11 (serial) | T5 |
| T9 | T8 | T10, T11 (serial) | T7 |
| T10 | T9 | T11 (serial) | T7 |
| T11 | T10 | T12 | T7 |
| T12 | T1-T11 merged | — | T13 |
| T13 | — | — | T12 |

## Todos
> Implementation + Test = ONE todo. Never separate.
<!-- APPEND TASK BATCHES BELOW THIS LINE WITH edit/apply_patch - never rewrite the headers above. -->

- [ ] 1. Watchdog de conexão com auto-restart capado
  What to do / Must NOT do: Em `bot.py::_poll_instance_state` (linhas 1595-1616): adicionar contador `_conn_bad_streak` incrementado quando `state != "open"` (inclui "unknown"), zerado quando "open". Quando streak >= `WATCHDOG_BAD_POLLS` (env, default 3 ≈ 90s — Evolution própria cicla reconexão a cada ~15s, então 90s contínuos de falha = travado de verdade) e `WATCHDOG_AUTORESTART` (env, default "true"): (i) PRE-CHECK: `subprocess.run(["docker","ps","--filter","name=evolution_api","--format","{{.Status}}"], timeout=10)` deve conter "Up" senão abortar episódio com ERROR; (ii) GAP MÍNIMO entre restarts dentro da janela: `now - _watchdog_restarts[-1] >= WATCHDOG_MIN_GAP_S` (env, default 300) além do cap `WATCHDOG_MAX_RESTARTS`=3/janela 1h (deque `_watchdog_restarts`); (iii) executar `subprocess.run(["docker","restart","evolution_api"], timeout=60, capture_output=True)` via `asyncio.to_thread`; (iv) POST-CHECK: até 3 polls seguintes exigir state "open", senão CRITICAL "auto-heal falhou" e suspender novas tentativas por 30min (`_watchdog_suspended_until`). Após restart, zerar streak e setar `_panel_state["instance"]="recovering"` por 2 ciclos. Logar `WARNING [WATCHDOG] instância %s há %d polls — restart #%d` e disparar `notify-send -a caelestia "🔄 Bot WhatsApp" "Instância caiu — reiniciando container"` via subprocess (best-effort, nunca levanta). NÃO tocar em logout/delete da instância, NÃO alterar intervalo base de 30s, NÃO bloquear o event loop. Se autorestart desligado, apenas logar CRITICAL 1x por episódio.
  Parallelization: Wave 1 | Blocked by: — | Blocks: T3
  References (executor has NO interview context - be exhaustive): bot.py:1595-1616 (poller), bot.py:1573-1589 (`handle_api_state` consome `_panel_state["instance"]`), bot.py:110-131 (RingLog p/ logs no painel), ~/bugs-erros-opencode.md seção 2026-08-24 (incidente raiz: Baileys loop pós-boot resolvido por `docker restart evolution_api`)
  Acceptance criteria (agent-executable): `python3 -m py_compile bot.py` OK; `pytest tests/test_watchdog.py -q` verde cobrindo: streak 3 com autorestart ON chama docker.restart 1x e zera streak; 4ª tentativa dentro de 1h é bloqueada pelo cap; autorestart OFF nunca chama subprocess; state "open" zera contador.
  QA scenarios (name the exact tool + invocation): happy: fixture fake states ["close"]*3 → assert restart chamado; failure: docker restart lançando TimeoutError → poller sobrevive (loop continua), logged ERROR. Evidence `.omo/evidence/task-1-wabot-proximas-melhorias.md`
  Commit: Y | feat(watchdog): auto-restart capado da instância caída

- [ ] 2. Circuit breaker por modelo + degraded mode com mensagem
  What to do / Must NOT do: Em `ask_ai()` (bot.py:769-829) e handler (bot.py:1473-1477): (a) exceções de tentativa carregam status — substituir `RuntimeError(f"IA HTTP {status}...")` (:804) por classe nova `AiUpstreamError(RuntimeError)` com attrs `.status:int|None`, `.model:str`; timeout/socket erros viram status None. (b) dict global `_model_cooldown: dict[str,float]`; classificar no except: HTTP 429→90s; 402,500,502,503→300s; status None (timeout/stream)→120s; outros→30s. Loop pula modelo com `_model_cooldown[m] > now` (log INFO `[IA] %s em cooldown %.0fs`). (c) ordenar tentativas: modelos fora de cooldown primeiro, entre eles ordenar por `_ia_stats[m]["ok"]/max(1,ok+fail)` desc. (d) se TODOS pulados/esgotados → raise `AiUnavailable(str(last_error))`. (e) handler: capturar `AiUnavailable` → se `now - _degraded_last.get(jid,0) > 600` enviar via `_try_send` "⚠️ Minha IA tá fora do ar agora. Tenta de novo em alguns minutinhos 🙏" e atualizar `_degraded_last[jid]=now` (dict global); retornar 200 `{"ok":false,"degraded":true}` (NÃO 502 — evita retry do Evolution). (f) OBSERVABILIDADE DE STARVATION: expor em `handle_api_state` (:1573-1589) dentro do bloco `"ia"`: `"cooldowns": {model: segundos restantes}` e `"degraded_msgs_hoje": contador global` — todo skip por cooldown já loga INFO `[IA] %s em cooldown %.0fs`. NÃO alterar payload/stream/timeouts existentes (:786-800), NÃO alterar caps, NÃO adicionar modelos novos à chain default.
  Parallelization: Wave 1 | Blocked by: — | Blocks: —
  References: bot.py:769-829 (chain), bot.py:802-804 (raise HTTP), bot.py:819-825 (stats fail), bot.py:1473-1477 (except atual), bot.py:1493-1504 (`_try_send`), bot.py:43 (AI_MODELS chain), librarian brief (cooldowns 60-90s/300s — filtrado, claims duvidosos descartados)
  Acceptance criteria: `pytest tests/test_ask_ai_breaker.py -q` verde: (1) modelo A falha 429→cooldown 90s, B responde; (2) próxima chamada pula A direto; (3) todos falhando → AiUnavailable; (4) handler manda mensagem 1x e suprime a 2ª dentro de 10min; (5) 402 gera cooldown 300s. `python3 -m py_compile bot.py` OK.
  QA scenarios: happy + failure conforme acima com aiohttp fake server (`aiohttp.test_utils.TestServer`). Evidence `.omo/evidence/task-2-wabot-proximas-melhorias.md`
  Commit: Y | feat(ai): circuit breaker por modelo + aviso de indisponibilidade

- [ ] 3. Backoff exponencial no poller (race de boot)
  What to do / Must NOT do: Mesma função do T1 (`_poll_instance_state`): manter `_poll_backoff` iniciado em 2s; a cada fetch com exceção/HTTP!=200 dobrar até cap 30s; ao obter state válido voltar a `POLL_INTERVAL_S` (env, default 30, extraído como constante). Logar DEBUG a cada backoff step. NÃO alterar lógica do watchdog do T1.
  Parallelization: Wave 2 | Blocked by: T1 | Blocks: —
  References: bot.py:1595-1616; log real 24/08 10:29:54 `[PANEL] erro ao fetch estado ... ::1 8083` (Evolution ainda não subira)
  Acceptance criteria: `pytest tests/test_watchdog.py::test_boot_backoff -q` verde (fetches falhos consecutivos → sleeps 2,4,8...cap 30; sucesso → volta 30). py_compile OK.
  QA scenarios: happy (recuperação) + failure (falha permanente, cap 30s mantido). Evidence `.omo/evidence/task-3-wabot-proximas-melhorias.md`
  Commit: Y | fix(panel): backoff exponencial no poller de estado

- [ ] 4. Dependências declaradas + checks de startup
  What to do / Must NOT do: `requirements.txt`: linhas `aiohttp>=3.9,<4` e `Pillow>=10,<12`. Em `main()` (bot.py:1634-1655), ANTES de `_load_state()`: se `STICKER_ENABLED` e `shutil.which(FFMPEG) is None` → `log.error("ffmpeg não encontrado (FFMPEG_PATH=%r) — figurinhas de vídeo desativadas")` e seguir com sticker de imagem apenas (setar flag global `_video_sticker_ok=False` consultada em `make_video_sticker_raw` bot.py:941 para levantar erro tratado no webhook :1439-1442); import de PIL já no topo — envolver em try/except ImportError com mensagem fatal clara e `sys.exit(1)` ("pip install -r requirements.txt"). Adicionar `import shutil`. NÃO instalar nada globalmente nesta task além de `pip install -r requirements.txt --user` local para validação; NÃO mudar pipeline de stickers.
  Parallelization: Wave 1 | Blocked by: — | Blocks: —
  References: bot.py:32 (`from PIL import Image`), bot.py:88 (FFMPEG), requirements.txt:1, README tabela deps
  Acceptance criteria: `pip install -r requirements.txt --user --dry-run` resolve; `pytest tests/test_startup_checks.py -q` verde (which=None → flag False; ImportError simulado → SystemExit); bot real reinicia OK (`systemctl --user restart whatsapp-bot` + health 200).
  QA scenarios: happy (ffmpeg presente) + failure (PATH sem ffmpeg → vídeo falha com msg tratada, imagem funciona). Evidence `.omo/evidence/task-4-wabot-proximas-melhorias.md`
  Commit: Y | fix(deps): declara Pillow, pin aiohttp, checks de startup

- [ ] 5. Webhook autenticado por token de URL
  What to do / Must NOT do: Env `WEBHOOK_TOKEN` (gerar 32 hex). Em `handle_webhook` (bot.py:1345): ANTES do parse de json, validar `request.query.get("token") == WEBHOOK_TOKEN` OU header `X-Webhook-Token`; mismatch/ausente → `log.warning("[WEBHOOK] 403 de %s", request.remote)` + 403. Se WEBHOOK_TOKEN vazio → log CRITICAL no boot e 403 em tudo (fail-closed). Reconfigurar webhook da instância: `POST http://localhost:8083/webhook/set/bot_ia -H apikey:$EVOLUTION_API_KEY` body `{"webhook":{"enabled":true,"url":"http://172.17.0.1:8084/webhook?token=<NOVO>","events":["MESSAGES_UPSERT"]}}` (mesma URL do README:42 + query). Persistir WEBHOOK_TOKEN em `~/.config/wabot/env.local` (ver T6). Atualizar README seção Setup. NÃO mudar eventos, NÃO expor token em logs.
  Parallelization: Wave 2 | Blocked by: — | Blocks: —
  References: bot.py:1345-1349, bot.py:1644 (rota), bot.py:37-39 (EVOLUTION_*), README:39-42, docker-compose.yml:32-47 (rede bridge → host é 172.17.0.1)
  Acceptance criteria: `pytest tests/test_webhook_auth.py -q` verde (sem token→403; token errado→403; header correto→processa; query correta→processa); E2E local: `curl -s -o /dev/null -w "%{http_code}" "http://localhost:8084/webhook"` == 403 e com `?token=` == 400/200 (payload inválido ≠ 403); webhook-set retorna 200 e mensagem real do usuário ainda processada (checar log).
  QA scenarios: happy (token query/header) + failure (ausente/errado/vazio-global). Evidence `.omo/evidence/task-5-wabot-proximas-melhorias.md`
  Commit: Y | feat(security): webhook autenticado por token

- [ ] 6. Segredos fora do repositório + troca do token vazado
  What to do / Must NOT do: Criar `~/.config/wabot/env.local` (chmod 600) com `DASHBOARD_TOKEN=<novo 32 hex>` e `WEBHOOK_TOKEN=<novo>`. Editar `bot.service` (no repo): remover linha `Environment=DASHBOARD_TOKEN=...` (:11) e adicionar `EnvironmentFile=%h/.config/wabot/env.local`; manter demais Environment (caps/AI_MODELS/ACTIVE_HOURS). `cp bot.service ~/.config/systemd/user/ && systemctl --user daemon-reload && systemctl --user restart whatsapp-bot`. Tratar token antigo (45ec84...) como comprometido: ele deixa de existir em config ativa; NÃO reescrever histórico do git (escopo). Validar: `/api/state` sem auth → 401; com `Authorization: Bearer <novo>` → 200. Commit do service SEM segredo. NÃO commit env.local, NÃO mudar WorkingDirectory/ExecStart, NÃO alterar caps no unit.
  Parallelization: Wave 2 | Blocked by: — | Blocks: T5 (consome WEBHOOK_TOKEN do env.local), T8
  References: bot.service:11 (linha a remover), bot.service:13-18 (manter), .gitignore:1-5 (env.local já coberto por padrão `.env`? NÃO — adicionar linha `env.local` explícita em .gitignore), ~/.config/systemd/user/ (destino do unit)
  Acceptance criteria: `grep -c DASHBOARD_TOKEN bot.service` == 0; `systemctl --user show whatsapp-bot -p EnvironmentFiles` aponta o env.local; curl asserts 401/200; `.gitignore` contém `env.local`; `git diff` do commit não contém nenhum valor de token.
  QA scenarios: happy (service sobe com EnvironmentFile) + failure (env.local ausente → bot sobe com DASHBOARD_TOKEN/WEBHOOK_TOKEN vazios e fail-closed de T5/T8 protege; ROLLBACK documentado: restaurar unit anterior do git + daemon-reload se E2E de mensagem real falhar). Evidence `.omo/evidence/task-6-wabot-proximas-melhorias.md`
  Commit: Y | fix(security): remove segredos do unit, usa EnvironmentFile

- [ ] 7. Docker hardening: bind local, senhas fortes, CORS
  What to do / Must NOT do: `docker-compose.yml`: ports de postgres/redis/minio → `"127.0.0.1:5433:5433"`, `"127.0.0.1:6380:6380"`, `"127.0.0.1:9000:9000"`, `"127.0.0.1:9001:9001"`; senhas via interpolação `${POSTGRES_PASSWORD:?set}`/`${MINIO_ROOT_PASSWORD:?set}` lidas do `.env` (gerar 24+ chars cada, atualizar `DATABASE_CONNECTION_URI` no .env para a senha nova — atenção: URI usa host `postgres:5433` interno, só a senha muda). `.env`: `CORS_ORIGIN=http://localhost:8083`, `SERVER_DISABLE_MANAGER=true`. NÃO fechar `SERVER_DISABLE_DOCS` aqui (T9 faz no fim, após confirmar rotas). `docker compose up -d` (recria containers; volume de instâncias preserva sessão — NÃO rodar `down -v`). Validar: evolution_api up, connectionState=open (restart do T1 pode agir se necessário), bot health 200, `ss -tlnp | grep -E "5433|6380|9000"` mostra apenas 127.0.0.1.
  Parallelization: Wave 3 | Blocked by: — | Blocks: —
  References: docker-compose.yml:15,16,28,43,53,58,60 (ports/senhas), .env:20 (DATABASE_CONNECTION_URI), .env:14,45,46 (CORS/MANAGER/DOCS), ~/bugs-erros-opencode.md 2026-08-24 (se cair em reconnect-loop: `docker restart evolution_api`, NÃO logout/QR)
  Acceptance criteria: `ss -tlnp` binds locais; `docker compose ps` 4 serviços Up; connectionState open ≤3min; SESSÃO PRESERVADA: `docker volume inspect evolution_instances` com ID idêntico antes/depois do recreate e connectionState=open SEM QR (se cair em reconnect-loop: `docker restart evolution_api`, NUNCA logout/QR); mensagem real processada (log do bot recebe webhook — pedir .ping ao usuário na F3 se necessário); `git diff` não contém senhas (ficam só no .env ignorado).
  QA scenarios: happy (stack sobe com env novas) + failure (senha faltante → compose falha com erro claro `:?set`). Evidence `.omo/evidence/task-7-wabot-proximas-melhorias.md`
  Commit: Y | fix(security): bind local dos serviços internos + credenciais fortes

- [ ] 8. Dashboard exige token sempre
  What to do / Must NOT do: `_check_dashboard_auth` (bot.py:1525-1532): se `not DASHBOARD_TOKEN` → return False (fail-closed). `main()`: se vazio, `log.error("DASHBOARD_TOKEN vazio — painel e /api/state ficarão inacessíveis")`. `handle_root` (:1541-1545) segue repassando token. NÃO adicionar rate-limit nem session; NÃO mudar HTML do dashboard.
  Parallelization: Wave 2 | Blocked by: — | Blocks: —
  References: bot.py:49 (default ""), bot.py:1525-1532, bot.py:1535-1538, bot.py:1548-1550
  Acceptance criteria: `pytest tests/test_dashboard_auth.py -q` verde (vazio→False; header certo→True; query certa→True); E2E pós-T6: `/dashboard` sem token → 401, com `?token=` → 200.
  QA scenarios: happy/failure conforme acima. Evidence `.omo/evidence/task-8-wabot-proximas-melhorias.md`
  Commit: Y | fix(security): painel fail-closed sem token

- [ ] 9. Marcar-como-lida + reação ✅ em comandos (+ fecha swagger no fim)
  What to do / Must NOT do: (1) Confirmar rotas exatas no v2.3.7: baixar `GET http://localhost:8083/docs` (swagger JSON; se 404, usar `/json` ou doc.evolution-api.com) e registrar os paths de read-receipt e sendReaction como comentário no topo da seção. (2) `READ_RECEIPTS` (env, default true) e `REACTIONS` (env, default true). (3) No `handle_webhook` logo após dedup/blacklist (:1406) e antes dos guardrails: se READ_RECEIPTS e key.id/remoteJid válidos → POST read-receipt (fire-and-forget, try/except log DEBUG). (4) Em `dispatch_command` após `_register_send` (:1334): se REACTIONS → POST reaction "✅" na msg (key.id), fire-and-forget. (5) APÓS validação E2E das duas rotas: editar `.env` `SERVER_DISABLE_DOCS=true` e `docker compose up -d evolution_api` (coordenar com T7 já aplicado). NÃO bloquear pipeline se receipt/reaction falhar; NÃO reagir em mensagens de IA livre (só comandos).
  Parallelization: Wave 3 | Blocked by: — | Blocks: passo docs-dependente de T7
  References: bot.py:1351-1372 (payload key/data disponível), bot.py:1322-1339 (dispatcher), bot.py:37-39 (creds), README arquitetura; swagger :8083/docs como fonte de verdade das rotas
  Acceptance criteria: `pytest tests/test_receipts_reactions.py -q` verde (mock aiohttp: payload correto p/ receipt e reaction; falhas engolidas com DEBUG; flags false desligam); E2E: mensagem real → log sem blue-check pendente (verificação visual do usuário na F3); reação ✅ aparece no comando .ping.
  QA scenarios: happy (receipt+reaction enviados) + failure (rota 404 → só log, fluxo segue). Evidence `.omo/evidence/task-9-wabot-proximas-melhorias.md`
  Commit: Y | feat(ux): marcar lida + reação de confirmação em comandos

- [ ] 10. Histórico persistente + comando .reset
  What to do / Must NOT do: `_state["history"]: dict[str, list]` (jid → lista de {"role","content","ts"}); helpers `_history_load/_history_append(jid,msgs)`; em ask_ai montar messages a partir do store persistido respeitando HISTORY_TURNS (bot.py:52) e podando entradas com ts > 7 dias no `_load_state` (:419-430); `_history_append` chamado nos pontos atuais (:1480-1481) e salva state de forma throttled (marcar dirty + flush no próximo `_save_state` já existente — NÃO salvar a cada append). Comando `.reset` registrado em COMMANDS: limpa history do jid, responde "🧹 Contexto desta conversa limpo!". Migrar leitura atual `_history[chat_jid]` (:781) para o store. NÃO guardar mídia/base64 no histórico; NÃO mudar HISTORY_TURNS default.
  Parallelization: Wave 3 | Blocked by: — | Blocks: —
  References: bot.py:52 (HISTORY_TURNS), bot.py:419-436 (load/save state), bot.py:779-782 (montagem messages), bot.py:1480-1481 (appends), bot.py:992-1024 (registro COMMANDS/MENU_TEXT), README:70
  Acceptance criteria: `pytest tests/test_history_persist.py -q` verde (roundtrip save/load; poda 7d; .reset limpa só do jid; cap HISTORY_TURNS); restart real: contexto sobrevive (enviar msg, restart, referenciar assunto → IA lembra).
  QA scenarios: happy (persistência + recall pós-restart) + failure (state.json corrompido → história começa vazia sem crash). Evidence `.omo/evidence/task-10-wabot-proximas-melhorias.md`
  Commit: Y | feat(memory): histórico persistente + .reset

- [ ] 11. Comandos novos: .resumo .traduz .lembrar .piada
  What to do / Must NOT do: Novos handlers no padrão existente (`async def _cmd_x(request, jid, args)` registrados em COMMANDS + MENU_TEXT atualizado bot.py:1010): `.resumo` — exige reply em mensagem citada com texto >400 chars (`extract_quoted*` padrão bot.py:586; se ausente/curto → instruções de uso); chama ask_ai(use_history=False) com prompt "resuma em até 3 bullets curtos". `.traduz <texto>` — ask_ai(use_history=False) prompt: detectar idioma; se pt-BR → traduzir para EN, senão → PT-BR; máx 1000 chars de args. `.lembrar HH:MM texto` — parse estrito `^([01]?\d|2[0-3]):[0-5]\d .+$`; guarda em `_state["reminders"][] {jid,ts,text}`; task asyncio dormindo até ts e envia via _try_send; re-agendar pendentes no boot (load_state); cap 5 lembretes ativos/chat; `.lembrar` sem args lista ativos. `.piada` — ask_ai(use_history=False) prompt piada curta PT-BR, temperatura alta via payload próprio (aceito duplicar payload local, NÃO alterar ask_ai assinatura além do já definido). Todos passam pelos caps existentes via dispatcher (_register_send :1334). NÃO implementar recorrência/daily digest; NÃO usar APIs externas pagas.
  Parallelization: Wave 3 | Blocked by: — | Blocks: —
  References: bot.py:992-1340 (padrão de comandos: _CMD_RE, COMMANDS, _cmd_quiz como referência de ask_ai em comando :1281), bot.py:1010-1024 (MENU_TEXT), bot.py:586-602 (quoted extraction), bot.py:1493 (_try_send)
  Acceptance criteria: `pytest tests/test_commands_new.py -q` verde (parse HH:MM válido/inválido; cap 5; resumo exige quote longa — caminho negativo; menu contém os 4 novos); E2E real: `.piada` responde; `.lembrar` dispara no minuto (testar com +2min); `.traduz hello` → tradução.
  QA scenarios: happy + failure (args ruins → mensagem de uso, sem crash). Evidence `.omo/evidence/task-11-wabot-proximas-melhorias.md`
  Commit: Y | feat(commands): resumo, traduz, lembrar, piada

- [ ] 12. Suíte consolidada + CI GitHub Actions + ruff
  What to do / Must NOT do: Criar `tests/conftest.py` (fixture app/TestServer aiohttp + state isolado em tmp_path via env STATE_FILE) e `tests/fixtures/*.json` com payloads messages.upsert representativos (texto, imagem c/ base64 1px, vídeo flag, grupo menção, grupo sem menção, opt-out "sair", msg duplicada, fromMe) — espelhando os shapes consumidos em bot.py:1351-1385. Rodar suíte inteira `pytest tests/ -q` verde. `.github/workflows/ci.yml`: on push/PR; ubuntu-latest; setup-python 3.12; `pip install -r requirements.txt pytest ruff`; `ruff check bot.py tests --select E9,F63,F7,F82` (erros fatais apenas — NÃO estilo agressivo) e `pytest -q`. Push para origin/master. NÃO habilitar jobs pesados (docker) no CI; NÃO subir segredos (CI não precisa de tokens).
  Parallelization: Wave 4 | Blocked by: T1-T11 merged | Blocks: —
  References: todos os tests/tests_*.py criados em T1-T11; bot.py:1351-1385 (shapes), .git/config:7 (origin), requirements.txt pós-T4
  Acceptance criteria: `pytest tests/ -q` ≥ 30 passed, 0 failed; INCLUINDO `tests/test_antiban_regression.py`: congela os defaults dos caps (DAILY/HOURLY/PER_CHAT/NEW_CONTACT/MIN_GAP extraídos de bot.py:66-70) num teste snapshot — qualquer mudança futura neles QUEBRA o teste deliberadamente (regression guard exigido pelo gate); `ruff check` limpo; workflow YAML válido (`python3 -c "import yaml,sys;yaml.safe_load(open('.github/workflows/ci.yml'))"`); `git push` OK e CI verde no GitHub (verificar com `gh run list --limit 1` se gh auth disponível, senão link do run no evidence).
  QA scenarios: happy (suite local + CI) + failure (teste propositalmente quebrado em branch scratch → CI vermelho — validar e reverter). Evidence `.omo/evidence/task-12-wabot-proximas-melhorias.md`
  Commit: Y | test(ci): suíte consolidada + GitHub Actions

- [ ] 13. Backup rotativo diário do state.json
  What to do / Must NOT do: Em `_save_state` (bot.py:433-436): uma vez por dia (quando `_state["date"]` muda no `_load_state` :426-428, copiar state.json → `state.json.bak-N` N=1..7 rotativo antes do primeiro save do dia; manter só 7. Caminho junto ao STATE_FILE. NÃO comprimir; NÃO fazer backup a cada save.
  Parallelization: Wave 4 | Blocked by: — | Blocks: —
  References: bot.py:419-436, STATE_FILE bot.py:53
  Acceptance criteria: `pytest tests/test_state_backup.py -q` verde (simular 8 trocas de dia → exatamente 7 baks, mais antigo removido; corrupção do principal → load cai no bak mais recente ANTES de começar limpo — ajustar `_load_state` para tentar baks em ordem desc antes do reset :424).
  QA scenarios: happy (rotação) + failure (principal corrompido → recupera do bak). Evidence `.omo/evidence/task-13-wabot-proximas-melhorias.md`
  Commit: Y | feat(state): backup rotativo com recovery

## Final verification wave
> Runs in parallel after ALL todos. ALL must APPROVE. Surface results and wait for the user's explicit okay before declaring complete.
- [ ] F1. Plan compliance audit
- [ ] F2. Code quality review
- [ ] F3. Real manual QA
- [ ] F4. Scope fidelity

## Commit strategy

Um commit convencional por todo (`feat|fix|test(scope): resumo`), branch `master`, push ao final do T12 (e re-push se T13/F-wave gerarem commits). Nenhum commit contém segredos; `.env` e `env.local` permanecem ignorados. Tag opcional `v0.2-improvements` após F-wave aprovada.

## Success criteria

1. Instância caída se auto-recupera em ≤ ~4 min sem intervenção (watchdog log + notify) — demonstrado por teste e/ou incidente real
2. Chain IA esgotada produz EXATAMENTE uma mensagem honesta ao usuário por 10min/chat, e cooldowns impedem martelar modelo morto (stats no painel mostram skips)
3. `curl` sem token: /webhook 403, /api/state 401, /dashboard 401; com token: 200
4. `ss -tlnp`: 5433/6380/9000/9001 apenas em 127.0.0.1; swagger :8083/docs desativado no fim
5. Nenhum segredo em `git grep` no HEAD; unit sem Environment=DASHBOARD_TOKEN
6. Contexto de conversa sobrevive a restart; `.reset` limpo; 4 comandos novos funcionando E2E
7. `pytest tests/ -q` ≥ 30 passed; CI verde; ruff fatal-clean; 7 baks de state.json rotacionando
8. Caps anti-ban e comportamento anti-ban bit-a-bit iguais aos de antes (diff não toca `_rate_block_reason`/caps defaults)
