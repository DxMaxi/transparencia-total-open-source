import asyncio
import json
from app.core.config import get_settings
from app.repositories.postgres import PostgresRepository
from app.services.parlamento import ParlamentoCollector

async def main():
    settings = get_settings()
    repo = PostgresRepository(settings)
    
    print("🔌 A ligar à base de dados no Supabase...")
    await repo.connect()
    print("✅ Ligação estabelecida com sucesso!")
    
    collector = ParlamentoCollector(settings, None, repo)
    
    # 1. Carregar Deputados
    try:
        with open('backend/tests/fixtures/parliament_deputies.json', encoding='utf-8') as f:
            deputies_data = json.load(f)
        
        if hasattr(collector, 'persist_deputies'):
            await collector.persist_deputies(deputies_data)
        elif hasattr(collector, 'save_deputies'):
            await collector.save_deputies(deputies_data)
        else:
            await collector.persist_deputies(deputies_data)
            
        print("✅ Deputados oficiais carregados na base de dados!")
    except Exception as e:
        print(f"⚠️ Erro ao carregar deputados: {e}")

    # 2. Carregar Votações
    try:
        with open('backend/tests/fixtures/parliament_votes.json', encoding='utf-8') as f:
            votes_data = json.load(f)
            
        if hasattr(collector, 'persist_votes'):
            await collector.persist_votes(votes_data)
        elif hasattr(collector, 'save_votes'):
            await collector.save_votes(votes_data)
        else:
            await collector.persist_votes(votes_data)
            
        print("✅ Votações oficiais carregadas na base de dados!")
    except Exception as e:
        print(f"⚠️ Erro ao carregar votações: {e}")

    await repo.disconnect()
    print("\n🎉 Processo concluído! Podes verificar a plataforma.")

if __name__ == "__main__":
    asyncio.run(main())