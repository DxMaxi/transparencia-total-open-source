# Contribuir

Obrigado por ajudar a tornar os dados políticos portugueses mais verificáveis.

## Antes de abrir um pedido

1. Consulte a metodologia em `docs/NEUTRALITY.md`.
2. Não introduza classificações editoriais, inferências partidárias ou dados sem fonte oficial.
3. Nunca copie credenciais, declarações não públicas ou dados pessoais desnecessários.
4. Abra uma issue a descrever a fonte, o comportamento esperado e um exemplo reproduzível.

## Fluxo de desenvolvimento

1. Crie um fork e uma branch curta.
2. Copie `.env.example` para `.env`.
3. Execute os testes frontend e backend descritos no `README.md`.
4. Inclua testes para novos mapeamentos de dados oficiais.
5. Abra um pull request pequeno, explicando alterações ao modelo de neutralidade.

## Regra de ouro das fontes

Cada facto público precisa de URL oficial, data de recolha e hash do documento. Uma mudança
de parser deve preservar o original ou o respetivo identificador de armazenamento imutável.

Ao adicionar um novo portal, atualize a lista de anfitriões permitidos, documente os termos de
reutilização e use um limite de pedidos conservador.
