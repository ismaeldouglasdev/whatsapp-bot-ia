# Sessão 2026-08-24 — Bot WhatsApp: reconexão + plano de melhorias

**Data:** 24 de agosto de 2026
**Modo:** ulw-plan (Prometheus) a partir do pedido "planeje todas as próximas melhorias"

## Objetivos da Sessão
1. Retomar o bot do WhatsApp (handoff obrigatório)
2. Reconectar instância bot_ia (estava em loop close/connecting pós-boot)
3. Planejar TODAS as próximas melhorias (ulw-plan, intent UNCLEAR, review_required)

## Alterações Realizadas
- **Reconexão operacional**: `docker restart evolution_api` → state=open estável sem QR (sessão válida; Baileys travado em memória). Registrado em `~/bugs-erros-opencode.md` (seção 2026-08-24 com prevenção)
- **Exploração**: bot.py lido por seções críticas (107 símbolos mapeados); infra verificada (compose/unit/.gitignore/remote github ismaeldouglasdev/whatsapp-bot-ia)
- **Achados-chave**: Pillow/ffmpeg não declarados; IA sem circuit breaker (silêncio ao usuário na falha); watchdog inexistente; webhook sem auth; DASHBOARD_TOKEN commitado no GitHub; Docker expondo PG/Redis/MinIO em 0.0.0.0; histórico volátil
- **Plano escrito**: `.omo/plans/wabot-proximas-melhorias.md` — 13 todos (T1-T13) + F1-F4, 4 waves, matriz de dependências
- **Review alta precisão**: momus APPROVE (2 MINOR) · Oracle R1 REJECT → 4 fixes aplicados como emendas (T1 pre/gap/post-check, T2 observabilidade starvation, T6 rollback/T7 sessão preservada, serialização bot.py + antiban regression guard T12) · Oracle R2 leu versão stale (caveat documentado no draft); ground-truth grep confirmou fixes nas linhas 57/86/94/137/177
- **Plexo**: task `1787583284-23a3c9` criada (high, whatsapp-bot) + contexto completo

## Pendências / Follow-ups
- **Execução** é sessão worker SEPARADA (`$start-work`) — planner não implementa
- F3 (manual QA real) precisa do usuário mandando `.ping` no zap no fim da execução

## 📊 Resumo da Sessão
```
📄 Plano gerado:        .omo/plans/wabot-proximas-melhorias.md (~200 linhas, 13 todos)
📄 Draft:               findings 14 · defaults 6 · receipts R1/R2
🔍 Símbolos mapeados:   107 (bot.py) + 3 subagentes (1 ok, 2 timeout)
🛡️ Fixes de review:     4/4 aplicados e verificados
⏰ Duração:             ~11h20 → ~12h05 (sessão opencode; epoch 1787578548)
🤖 Modelo:              ollama/gpt-oss:120b (+combo-round-robin nos subagentes)
```
