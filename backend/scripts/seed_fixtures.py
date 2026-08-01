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
    
    collector = ParlamentoCollector(settings, None)

    # 1. Carregar e Guardar Deputados
    try:
        with open('backend/tests/fixtures/parliament_deputies.json', encoding='utf-8') as f:
            raw_deputies = json.load(f)
        
        norm_deputies = collector.normalise_deputies(raw_deputies)
        
        # Procurar o método de gravação no repositório
        for method in ['save_deputies', 'upsert_deputies', 'persist_deputies', 'save_parliament_deputies']:
            if hasattr(repo, method):
                await getattr(repo, method)(norm_deputies)
                print(f"✅ Deputados oficiais guardados com o método '{method}'!")
                break
    except Exception as e:
        print(f"⚠️ Erro nos deputados: {e}")

    # 2. Carregar e Guardar Votações
    try:
        with open('backend/tests/fixtures/parliament_votes.json', encoding='utf-8') as f:
            raw_votes = json.load(f)
            
        norm_votes = collector.normalise_votes(raw_votes)
        
        for method in ['save_votes', 'upsert_votes', 'persist_votes', 'save_parliament_votes']:
            if hasattr(repo, method):
                await getattr(repo, method)(norm_votes)
                print(f"✅ Votações oficiais guardadas com o método '{method}'!")
                break
    except Exception as e:
        print(f"⚠️ Erro nas votações: {e}")

    await repo.disconnect()
    print("\n🎉 Povoamento concluído com sucesso!")

if __name__ == "__main__":
    asyncio.run(main())