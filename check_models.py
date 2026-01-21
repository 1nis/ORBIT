import os
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

try:
    client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    print("🔄 Connexion à Anthropic en cours...")
    
    # On demande à l'API : "Quels modèles je peux utiliser ?"
    models = client.models.list()
    
    print("\n✅ SUCCÈS ! Voici les modèles disponibles pour ta clé :")
    print("------------------------------------------------")
    found_sonnet = False
    
    # On trie pour afficher les plus récents en premier si possible
    sorted_models = sorted(models.data, key=lambda x: x.created_at if hasattr(x, 'created_at') else 0, reverse=True)

    for m in sorted_models:
        print(f"📄 ID: {m.id}")
        if "sonnet" in m.id:
            found_sonnet = True
            
    print("------------------------------------------------")
    
    if found_sonnet:
        print("\n💡 CONSEIL : Copie l'ID qui contient 'sonnet-3-5' ou le plus récent de la liste.")
    else:
        print("\n⚠️ Pas de Sonnet trouvé. Utilise 'claude-3-opus-20240229' ou un ID de la liste ci-dessus.")

except Exception as e:
    print(f"\n❌ ERREUR CRITIQUE : {e}")
    print("Vérifie que ta clé API dans .env est correcte et qu'elle a des crédits.")