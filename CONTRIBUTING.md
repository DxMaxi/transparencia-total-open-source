# Contribuir

Obrigado por ajudar a tornar os dados políticos portugueses mais verificáveis.

## Antes de abrir um pedido

1. Consulte a metodologia em `docs/NEUTRALITY.md`.
2. Consulte a política em `docs/GOVERNANCE.md` e o âmbito das licenças em `LICENSING.md`.
3. Não introduza classificações editoriais, inferências partidárias ou dados sem fonte oficial.
4. Nunca copie credenciais, declarações não públicas ou dados pessoais desnecessários.
5. Abra uma issue a descrever a fonte, o comportamento esperado e um exemplo reproduzível.

## Fluxo de desenvolvimento

1. Crie um fork e uma branch curta.
2. Copie `.env.example` para `.env`.
3. Execute os testes frontend e backend descritos no `README.md`.
4. Inclua testes para novos mapeamentos de dados oficiais.
5. Abra um pull request pequeno, explicando alterações ao modelo de neutralidade.

Nenhum pull request é integrado automaticamente na plataforma oficial. A aprovação exige revisão
humana, fontes verificadas e os testes aplicáveis.

## Regra de ouro das fontes

Cada facto público precisa de URL oficial, data de recolha e hash do documento. Uma mudança
de parser deve preservar o original ou o respetivo identificador de armazenamento imutável.

Ao adicionar um novo portal, atualize a lista de anfitriões permitidos, documente os termos de
reutilização e use um limite de pedidos conservador.

## Licença das contribuições

Ao submeter uma contribuição, declara que possui os direitos e autorizações necessários para o
fazer e aceita que:

- código e outras contribuições de software fiquem sob a
  `PolyForm-Noncommercial-1.0.0`;
- documentação, textos e elementos editoriais originais fiquem sob `CC BY-NC 4.0`;
- dados, documentos e material de terceiros conservem as respetivas condições de origem.

Não submeta conteúdo cuja licença seja incompatível ou cuja titularidade não consiga demonstrar.
A aceitação de uma contribuição não transfere para o projeto direitos que o autor não possua.

## Decisões e segurança

Uma recusa deve indicar a regra metodológica, de segurança, licença ou teste que a fundamenta,
sempre que isso não exponha dados pessoais, credenciais, vulnerabilidades ou conteúdo privado em
revisão. Vulnerabilidades não devem ser publicadas numa issue; siga `SECURITY.md`.
