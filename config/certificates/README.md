# CA pública da base Supabase

`supabase-prod-ca-2021.crt` é um certificado público de autoridade, sem chave privada.
Foi obtido em 10-09-2026 do URL HTTPS usado pelo dashboard oficial:

https://supabase-downloads.s3-ap-southeast-1.amazonaws.com/prod/ssl/prod-ca-2021.crt

A origem está definida no código Supabase:
https://github.com/supabase/supabase/blob/1966209483edcbb11361deeb606fef5f90620df4/apps/studio/hooks/custom-content/custom-content.json

- SHA-256 do certificado DER: `807025ad50d4ed219d2c9c7d299c004f824eb00cf7f65afef607d07b72e6cafa`.
- Válido até 26-04-2031; CI verifica validade, identidade e atributo CA.
- Ensaio TLS 1.3 sem credenciais no pooler oficial confirmou cadeia e hostname.
- O verificador usa `verify-full`; Prisma usa `require`, esta CA e `sslaccept=strict`.
- Não instalar esta CA globalmente nem desativar validação de certificados.

Referências: https://supabase.com/docs/guides/platform/ssl-enforcement e
https://docs.prisma.io/docs/orm/v6/overview/databases/postgresql.
