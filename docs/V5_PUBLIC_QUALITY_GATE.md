# V5.17 — gate público de segurança e acessibilidade

## Objetivo

Esta etapa torna verificável o endurecimento das páginas públicas e privadas sem alterar dados,
publicar conteúdo ou executar migrações. As garantias são testadas no artefacto Next.js de produção
e no domínio público depois de cada deployment.

## CSP adequada a cada âmbito

As rotas editoriais `/admin/*` e `/auth/*` já são dinâmicas, privadas e `no-store`. Cada pedido
recebe agora um `nonce` criptograficamente aleatório. O mesmo valor segue no pedido interno do
Next.js e no cabeçalho da resposta, permitindo apenas os scripts e estilos emitidos para aquele
pedido. Em produção, a política privada inclui `strict-dynamic` e não inclui `unsafe-inline`.

As páginas públicas mantêm temporariamente a política estática compatível com a geração estática,
ISR e cache CDN. Um `nonce` global obrigaria essas páginas a renderização dinâmica por pedido; a
alternativa SRI do Next.js continua experimental e depende de Webpack, enquanto este projeto usa
Turbopack. A limitação pública fica, por isso, explícita e não é apresentada como resolvida.

Origens adicionais de API e Supabase só entram em `connect-src` quando são HTTPS ou HTTP local de
desenvolvimento. Um valor inválido não alarga a política.

## Verificação em navegador real

O E2E confirma no artefacto de produção que:

- a página de entrada editorial carrega sem erros;
- o cabeçalho privado contém um `nonce` por pedido e `strict-dynamic`;
- a política privada não contém `unsafe-inline`;
- a resposta editorial é `private` e `no-store`;
- as rotas públicas principais continuam acessíveis.

## Dependências de construção

A auditoria local identificou `deepmerge-ts` anterior a 8.0.0 na cadeia do Prisma. A versão era
abrangida por CVE-2026-40345, que permite esgotamento de pilha perante grafos recursivos
construídos. Enquanto o Prisma não atualizar a dependência transitiva, o projeto fixa a versão
corrigida 8.0.1 através de `overrides`. A validação e geração Prisma, o build Next.js e o gate em
navegador são repetidos com esse override; `npm audit --omit=dev` não reporta vulnerabilidades.

## Acessibilidade

As rotas públicas principais são analisadas no Chromium com axe-core para os critérios automáticos
WCAG 2.0, 2.1 e 2.2 de níveis A e AA. A primeira execução detetou e corrigiu o contraste do cartão
do Promessómetro na página inicial.

Uma análise automática não substitui testes humanos com teclado, leitor de ecrã, ampliação e
utilizadores. O resultado significa apenas “nenhuma violação automaticamente detetável nas páginas
testadas”, nunca conformidade total certificada.

## Limites preservados

Este gate não altera a separação entre recolha, revisão e publicação. Não muda fontes, factos,
estados editoriais, histórico, direito de resposta, correspondências ou identificadores pessoais.
Não constitui auditoria jurídica nem prova de cobertura histórica completa.
