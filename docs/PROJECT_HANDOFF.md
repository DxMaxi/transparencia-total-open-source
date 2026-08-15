# PROJECT HANDOFF — Transparência Total / Fator Cívico

Atualizado em: **2026-08-15**

Este documento existe para permitir continuidade segura entre sessões de trabalho, colaboradores e chats sem depender de memória externa ao repositório.

> **Regra principal:** antes de alterar código, ler `docs/V5_RELEASE_CHECKLIST.md`, a issue #58 e a issue #76. Depois confirmar o estado real de `main`, porque este handoff é um checkpoint e pode existir trabalho posterior.

## 1. Objetivo do projeto

O Transparência Total / Fator Cívico é uma plataforma cívica para apresentar informação política e institucional verificável com fonte oficial, cobertura explícita, histórico e regras de publicação prudentes.

A V5 deve terminar como uma plataforma simultaneamente:

- tecnicamente robusta;
- auditável e verificável;
- segura e juridicamente prudente;
- acessível e responsiva;
- simples de utilizar por um cidadão comum;
- incapaz de transformar indisponibilidade técnica em afirmações factuais falsas.

## 2. Arquitetura atual

### Frontend

- Next.js 16 / React 19 / TypeScript
- Vercel em produção
- PWA com service worker explícito
- Playwright para testes E2E públicos
- Prisma no ecossistema da aplicação

### Backend

- FastAPI
- PostgreSQL / asyncpg
- Render em produção
- Supabase previsto/usado para autenticação editorial V5
- separação entre recolha, staging, revisão, aprovação e publicação

### URLs públicas

- Site: `https://www.transparenciatotal.pt`
- API: `https://transparencia-total-api.onrender.com`

Nunca adicionar neste documento segredos, chaves, `.env`, dumps, tokens, passwords ou dados pessoais não destinados a publicação.

## 3. Versões de runtime relevantes

- `package.json` exige **Node 24.x**.
- CI usa Node 24.
- O ambiente local oficial deve respeitar Node 24 para evitar resultados não reprodutíveis.
- O backend declara Python `>=3.12`.
- No checkpoint de 2026-08-15, CI usa Python 3.12 e Render declara Python 3.13.5; esta divergência está registada na issue #76.

## 4. Estado da V5

Issue canónica: **#58 — [V5] Plano de conclusão da versão 5**.

Frentes ainda pertencentes à V5:

- #52 — Supabase e autenticação em staging
- #53 — circuito editorial e Parlamento em staging
- #56 — perfis, Promessómetro e cobertura histórica
- #57 — Investigador Cívico e IA responsável
- #55 — pesquisa, comparação, desempenho e alertas PWA
- #54 — migração, segurança, recuperação e release de produção
- #76 — bugs, riscos e dívida técnica encontrados na auditoria profunda de 2026-08-15

A melhoria de UX iniciada em agosto de 2026 faz parte da estabilização/conclusão da **V5**. Não deve ser tratada como início de uma V6 nem como autorização para reescrever o projeto.

## 5. Baseline técnico conhecido

Checkpoint validado antes da auditoria profunda:

- commit `11bc16f` — `test: add public E2E audit coverage`
- commit `11bf420` — `fix: avoid false zero counts when public API is unavailable`
- suite `npm.cmd run test:frontend`: **64 testes, 64 pass, 0 fail** no checkpoint `11bf420`
- deployment Vercel desse commit confirmado com sucesso
- `npm audit --omit=dev` tinha devolvido **0 vulnerabilidades** na auditoria anterior
- pesquisa de segredos não encontrou credenciais reais conhecidas; repetir antes do release final

Este baseline não substitui a verificação do `HEAD` atual.

## 6. Correção importante já aplicada

Foi corrigido um erro de semântica pública: quando a API ficava temporariamente indisponível, a homepage apresentava falsamente `0 registos aprovados` e fontes como `Sem recolha`.

Com a correção `11bf420`:

- indisponibilidade temporária deixa de ser apresentada como zero;
- os contadores usam `—` quando não existe informação válida;
- as fontes aparecem como `Indisponível`;
- existe teste de regressão no contrato público da UI.

**Invariante:** nunca voltar a representar uma falha de API como ausência factual de dados.

## 7. Auditoria aprofundada de 2026-08-15

Documento detalhado: `docs/AUDIT_2026-08-15.md`

Issue de acompanhamento: **#76**.

Regra de gate:

> A V5 não deve ser fechada enquanto existir qualquer P1 confirmado aberto.

Os achados de maior prioridade incluem:

- dependências Python divergentes entre `pyproject.toml` e `requirements.txt`;
- risco de um perfil político temporariamente indisponível ser tratado como 404 real;
- public smoke não provar necessariamente o deployment do commit que o disparou;
- startup da API depender diretamente da disponibilidade do PostgreSQL;
- Playwright existir mas ainda não correr no CI;
- falta de observabilidade suficiente nas falhas frontend→API;
- necessidade de rever timeout/retry/stale data sem mascarar erros reais.

Consultar #76 para estado atualizado de cada item.

## 8. Comandos de validação relevantes

Em Windows PowerShell usar `npm.cmd` quando necessário.

### Frontend / contratos

```powershell
npm.cmd run test:frontend
```

### Qualidade frontend completa

```powershell
npm.cmd run quality
```

### Build Next usado no CI relevante

```powershell
npm.cmd run build:next
```

### Smoke público

```powershell
npm.cmd run smoke:public
```

### Backend

No ambiente Python correto:

```text
ruff check backend
ruff format --check backend
mypy --config-file backend/pyproject.toml backend/app
pytest backend
```

Antes do release final devem também correr os E2E Playwright no browser real depois de a integração CI respetiva estar concluída.

## 9. Regras de dados e publicação que não podem ser quebradas

- Não substituir dados oficiais indisponíveis por exemplos fictícios.
- Não inventar relações entre pessoas, empresas, contratos ou entidades.
- Não transformar coincidência de nomes em identidade.
- Não criar acusações, scores reputacionais ou conclusões políticas automáticas.
- Preservar URL/fonte oficial, proveniência e cobertura quando disponíveis.
- Distinguir sempre recolha, normalização, evidência, revisão, aprovação e publicação.
- Aprovação editorial não deve publicar automaticamente.
- Falha de endpoint não equivale a `0`, `não existe`, `sem recolha` ou 404.
- Manter direito de resposta, histórico e limitações públicas.
- Staging nunca prova uma condição de produção.
- Não colocar segredos, dados privados ou dumps em commits, issues ou logs públicos.

## 10. UX V5

Problema identificado: a plataforma é tecnicamente rigorosa mas ainda apresenta demasiada complexidade interna ao cidadão.

Direção aprovada para a revisão UX:

- rever página a página, começando pela homepage;
- mostrar primeiro a tarefa que o cidadão quer realizar;
- usar progressive disclosure para metodologia, cobertura e limitações;
- manter toda a rastreabilidade, mas não obrigar o visitante a compreendê-la antes de pesquisar;
- simplificar linguagem pública sem simplificar as regras internas;
- testar sempre desktop, mobile, teclado e estados de indisponibilidade.

Antes de alterar uma página, identificar:

1. objetivo principal do utilizador;
2. fonte de confusão atual;
3. hierarquia de informação proposta;
4. impacto em acessibilidade e estados de erro;
5. testes de regressão necessários.

## 11. Processo de trabalho recomendado

Para cada correção:

1. confirmar `HEAD` e working tree;
2. reproduzir ou provar o problema;
3. corrigir o mínimo necessário;
4. adicionar teste que falharia antes da correção;
5. correr testes direcionados;
6. correr a suite/gate relevante;
7. rever `git diff` e `git status`;
8. commit com mensagem específica;
9. push;
10. confirmar CI/deployment/smoke aplicável;
11. atualizar a issue correspondente com evidência, sem segredos.

Evitar grandes alterações simultâneas. Os P1 da #76 devem ser tratados um de cada vez.

## 12. O que um novo chat deve ler primeiro

Ordem recomendada:

1. `docs/PROJECT_HANDOFF.md`
2. `docs/V5_RELEASE_CHECKLIST.md`
3. issue #58
4. issue #76
5. a issue específica da tarefa (#52–#57)
6. `docs/AUDIT_2026-08-15.md` quando o trabalho tocar em resiliência, CI, segurança ou release

Depois deve inspecionar o código atual e não assumir que um documento de handoff substitui o estado real do repositório.
