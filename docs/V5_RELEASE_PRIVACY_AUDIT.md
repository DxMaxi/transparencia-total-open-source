# V5.19 — auditoria de privacidade e segredos do candidato

## Nota posterior — 3 de setembro de 2026

A consulta read-only da API do GitHub passou a devolver `private=false` e `visibility=public`.
As issues #58 e #76 consultadas nessa data não registam a resolução ou aceitação do contacto
histórico identificado abaixo. O estado público não permite inferir a data/autor da alteração ou
uma nova aprovação de privacidade. Não foi repetida a auditoria integral nem alterada a história
ou a visibilidade. Este registo acrescenta contexto; não converte o resultado histórico em `PASS`.

Os resultados e limites seguintes referem-se ao checkpoint original de 24-08-2026.

## Âmbito e limites

Esta auditoria foi executada em 24 de agosto de 2026 sobre o commit
`9f46c2f632706eb1694261311ef54955a9a567ce`, antes de qualquer migração V5, alteração de
produção ou mudança de visibilidade do repositório. Abrangeu:

- os quatro JSON versionados em `data/`;
- o working tree e os ficheiros atualmente versionados;
- os 297 commits alcançáveis por todas as referências Git locais;
- padrões adicionais próprios do projeto para identidade `age`, chaves Supabase/OpenAI, JWT,
  chaves privadas e ligações PostgreSQL com credenciais.

O relatório conserva apenas contagens, categorias, caminhos e commits. Não conserva nem publica
valores candidatos, emails completos, tokens, ligações privadas ou conteúdo editorial.

Uma pesquisa automática reduz risco, mas não prova por si só que um repositório nunca contém
informação sensível. Deve ser repetida no commit candidato e complementada pela revisão humana,
pelos controlos do fornecedor e pela confirmação de revogação das credenciais anteriormente
expostas.

## Dados versionados

Foram inspecionados 1 956 808 bytes nos seguintes ficheiros:

- `data/deputados-xvii-auditoria.json`;
- `data/deputados-xvii-atividade-auditoria.json`;
- `data/revisao-deputados-xvii.json`;
- `data/xxv-government-programme.json`.

Resultado:

- zero emails preenchidos;
- zero chaves `NIF`, `NIPC`, `tax_id` ou equivalente;
- zero telefones, moradas ou campos de contacto preenchidos;
- zero marcadores de chave privada, identidade `age`, secret key Supabase ou chave OpenAI;
- sequências de nove algarismos detetadas pela pesquisa textual pertenciam exclusivamente a
  trechos de SHA-256 ou identificadores técnicos, nunca a um valor fiscal autónomo.

Os dois ficheiros parlamentares conservam campos `email` nulos fornecidos pelo contrato da fonte:
1 446 e 286 ocorrências, respetivamente. O teste automático aceita apenas `null` ou string vazia
nesses campos; qualquer valor novo faz falhar o gate.

Fixtures de teste fora de `data/` incluem identificadores deliberadamente demonstrativos para
provar HMAC e recusa de texto em claro. Não são dados de produção nem prova de identidade. Antes de
uma publicação pública do repositório, essas fixtures continuam sujeitas a revisão para garantir
que nenhum valor demonstrativo coincide com uma entidade real.

## Working tree e história Git

Foi usado Gitleaks `8.30.0`, descarregado da release oficial. O SHA-256 do ZIP Windows x64 foi
confirmado contra o manifesto oficial:

`54fe94f644b832dd08e8c3a5915efb3bfa862386d59fb27ca0792cb687a83573`

A versão `8.30.1` não foi usada porque existem relatos públicos de checksum incorreto e de regras
predefinidas que não detetam segredos. O resultado da versão validada foi:

- história Git: 297 commits e aproximadamente 7,64 MB de patches analisados;
- cinco alertas `generic-api-key`;
- quatro alertas eram o mesmo UUID sintético de `auth_user_id` em versões de um teste;
- um alerta era o valor explicitamente marcado para substituição em `.env.example`;
- zero alertas confirmados como credencial real;
- no estado atual versionado, os três alertas equivalentes continuam limitados ao UUID de teste e
  ao placeholder documentado.

Uma segunda pesquisa por padrões específicos encontrou zero identidades privadas `age`, headers de
chave privada, secret keys Supabase, chaves OpenAI e JWT completos na história. Ligações PostgreSQL
com utilizador e password aparecem apenas em `.env.example`, CI e testes com valores locais ou
domínios reservados; nenhuma ligação remota real foi encontrada por esta verificação.

## Bloqueio de privacidade da história

O contacto pessoal já não existe no working tree nem no site público, mas um endereço Gmail
pessoal permanece em diffs históricos de:

- `lib/site.ts`;
- `backend/app/core/config.py`.

O endereço não é repetido neste documento. Este achado não é uma chave revogável, mas torna-se
público se a história Git for publicada sem alteração. Por isso:

- a visibilidade pública do repositório continua bloqueada;
- esta auditoria não autoriza reescrever commits, tags ou branches;
- uma reescrita exige decisão explícita, cópia de segurança das referências, inspeção de metadata
  de autor e coordenação de um force-push;
- aceitar conscientemente a exposição também exige uma decisão explícita do titular.

Eliminar a referência no commit atual não elimina a ocorrência histórica. Nenhuma caixa relativa
à publicação pública pode ser fechada enquanto este ponto não tiver uma decisão e nova verificação.

## Gate automático acrescentado

`tests/v5-release-privacy-contract.test.mjs` passa a analisar todos os JSON de `data/` que estejam
versionados e falha perante:

- email, telefone, morada, NIF ou NIPC preenchidos;
- campos fiscais mesmo que o valor pareça demonstrativo;
- material com forma de identidade `age`, chave privada, secret key Supabase, chave OpenAI, JWT ou
  ligação PostgreSQL com password.

O teste não lê `data/private/` nem transforma um artefacto privado local num ficheiro publicável.
Também não substitui a pesquisa de toda a história com uma ferramenta dedicada.

## Resultado do gate

| Verificação | Estado | Limite |
|---|---|---|
| JSON versionados em `data/` | PASS | repetir no candidato final |
| Credenciais no working tree versionado | PASS com falsos positivos revistos | não prova revogação externa |
| Credenciais na história Git | PASS com falsos positivos revistos | repetir após qualquer reescrita |
| Privacidade do contacto na história | FAIL | email pessoal histórico exige decisão |
| Tornar o repositório público | NÃO AUTORIZADO | depende de resolver o FAIL anterior e de autorização própria |

## Referências

- [Gitleaks — repositório e instruções oficiais](https://github.com/gitleaks/gitleaks);
- [release oficial v8.30.0](https://github.com/gitleaks/gitleaks/releases/tag/v8.30.0);
- [problema de checksum comunicado para v8.30.1](https://github.com/gitleaks/gitleaks/issues/2164);
- [problema de deteção comunicado para v8.30.1](https://github.com/gitleaks/gitleaks/issues/2170).
