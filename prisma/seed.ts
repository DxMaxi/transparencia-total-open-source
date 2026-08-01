import "dotenv/config";
import { PrismaPg } from "@prisma/adapter-pg";
import { PrismaClient } from "../generated/prisma/client";

const connectionString = process.env.DATABASE_URL;
if (!connectionString) throw new Error("DATABASE_URL não configurada");

const prisma = new PrismaClient({ adapter: new PrismaPg({ connectionString }) });

async function main() {
  await prisma.sourceDocument.upsert({
    where: {
      url_contentSha256: {
        url: "https://www.parlamento.pt/Cidadania/Paginas/DadosAbertos.aspx",
        contentSha256: "catalogue-placeholder-not-a-document-hash",
      },
    },
    create: {
      publisher: "PARLIAMENT",
      kind: "OPEN_DATASET",
      title: "Catálogo de Dados Abertos da Assembleia da República",
      url: "https://www.parlamento.pt/Cidadania/Paginas/DadosAbertos.aspx",
      retrievedAt: new Date(),
      contentSha256: "catalogue-placeholder-not-a-document-hash",
      parserVersion: "seed-v1",
    },
    update: { retrievedAt: new Date() },
  });
}

main()
  .finally(async () => prisma.$disconnect())
  .catch((error) => {
    console.error(error);
    process.exitCode = 1;
  });
