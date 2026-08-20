# Política de runtime Python

## Objetivo

O backend usa uma única série de Python em desenvolvimento, testes, CI e produção. A revisão exata
canónica é `3.13.15`, definida na raiz em `.python-version`. Esta política elimina a divergência
acidental anteriormente existente entre Python 3.12 no CI e Python 3.13.5 no Render.

Esta alteração é apenas de runtime e validação. Não executa migrações, não altera Supabase, não
acede a segredos e não lê nem escreve dados reais.

## Contrato

| Superfície | Regra |
| --- | --- |
| `.python-version` | Fonte canónica da revisão exata: `3.13.15` |
| `backend/pyproject.toml` | Compatibilidade pública limitada a `>=3.13,<3.14` |
| GitHub Actions | Todos os passos `actions/setup-python` usam `python-version-file: .python-version` |
| Render | `PYTHON_VERSION` coincide exatamente com `.python-version` |
| Docker | A imagem base coincide exatamente com `.python-version` |
| Ruff e mypy | Analisam código para Python 3.13 |

O Render continua a usar o runtime Python nativo e o Dockerfile continua a ser uma via de execução
separada. A política alinha as versões; não muda a arquitetura de deployment.

## Verificação

O verificador não depende das bibliotecas da aplicação:

```bash
python backend/scripts/check_python_runtime_policy.py
```

Este modo compara todos os ficheiros e pode ser executado por um intérprete diferente. Para
confirmar também que o intérprete ativo é exatamente o canónico:

```bash
python backend/scripts/check_python_runtime_policy.py --check-interpreter
```

O CI executa o segundo comando imediatamente depois de preparar o Python. Os testes unitários do
contrato são recolhidos pela suite backend e também podem ser executados isoladamente:

```bash
cd backend
python -m unittest discover -s tests -p 'test_python_runtime_policy.py' -v
```

## Atualização futura

Uma atualização não deve ser feita apenas no Render ou apenas no CI.

1. Confirmar a publicação oficial da revisão Python e a disponibilidade no GitHub Actions, no
   Render e na imagem Docker oficial.
2. Atualizar `.python-version`, `render.yaml` e `backend/Dockerfile` na mesma alteração.
3. Se mudar a série, atualizar deliberadamente `requires-python`, Ruff, mypy e a série aceite pelo
   verificador. Uma atualização de `3.13.x` para `3.14.x` é uma mudança de compatibilidade, não uma
   simples atualização de patch.
4. Executar o verificador, os seus testes unitários e toda a suite backend.
5. Exigir CI verde antes do merge.
6. Depois do deployment autorizado, confirmar em modo read-only a saúde da API e a versão efetiva
   do serviço antes de encerrar a ocorrência de paridade.

Não se deve atualizar a issue canónica nem declarar produção alinhada apenas com base num teste
local ou num patch ainda não integrado.
