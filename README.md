# 🚀 Orbit

**Orbit v4 - Vision & Network Edition** est un assistant de développement IA autonome propulsé par Claude (Anthropic). Il combine une architecture multi-agents, une boucle d'autonomie intelligente, la vision par ordinateur et l'accès contrôlé à Internet pour créer, déboguer et documenter vos projets automatiquement.

## ✨ Fonctionnalités principales

- 🤖 **Architecture Multi-Agents** : Classification d'intentions (CHAT/DEV/README/DEBUG_VISUAL)
- 🔄 **Boucle d'Autonomie** (The Loop) : Exécution itérative jusqu'à 5 cycles
- 👁️ **Vision AI** : Capture d'écran via Playwright + Analyse Claude Vision API
- 🌐 **Accès Internet Contrôlé** : Recherche DuckDuckGo + Lecture de pages web
- 🧠 **Mémoire Self-Healing** : Base de connaissances des bugs résolus
- ⚡ **Smart Search** : Recherche optimisée pour économiser les tokens
- 🖥️ **Live Preview** : Serveur en arrière-plan pour tester vos apps

## 🛠️ Technologies

### Backend
- **Python 3.8+** : Moteur principal
- **Flask** : API REST et interface web
- **Anthropic SDK** : Intégration Claude (Sonnet 4.5 / Opus 4)
- **Playwright** : Automatisation navigateur et screenshots
- **DuckDuckGo Search** : Recherche web sans API key

### Frontend
- **HTML/CSS/JavaScript** : Interface utilisateur
- **Node.js + Express** : Serveur applicatif (exemple SaaS inclus)

### Outils
- **Git** : Versioning automatique
- **GitHub CLI** : Création de repos (optionnel)
- **Multer** : Upload de fichiers (CSV, PDF)

## 📦 Installation

### Prérequis
- Python 3.8 ou supérieur
- Node.js 16+ et npm
- Git installé
- Clé API Anthropic ([Obtenir une clé](https://console.anthropic.com/))

### Étapes

1. **Cloner le projet**
```bash
git clone <votre-repo>
cd Orbit
```

2. **Installer les dépendances Python**
```bash
pip install -r requirements.txt
playwright install chromium
```

3. **Installer les dépendances Node.js** (pour l'exemple SaaS)
```bash
npm install
```

4. **Configuration**

Créez un fichier `.env` à la racine :
```env
ANTHROPIC_API_KEY=votre_cle_api_anthropic
ORBIT_MODEL=claude-sonnet-4-5-20250929
ORBIT_OPUS_MODEL=claude-opus-4-20250514
PROJECTS_ROOT=C:\Users\VotreNom\Orbit_Projects
ORBIT_MAX_TOKENS=4096
ORBIT_MAX_LOOPS=5
ORBIT_AUTO_GITHUB=true
ORBIT_COMMAND_TIMEOUT=60
```

5. **Vérifier les modèles disponibles** (optionnel)
```bash
python check_models.py
```

## 🚀 Usage

### Démarrer Orbit

**Mode Web (Interface graphique)** :
```bash
python app.py
```
Puis ouvrez http://localhost:5000 dans votre navigateur.

**Mode Terminal** :
```bash
python orbit_terminal.py
```

### Démarrer l'exemple SaaS (Subscription Manager)

**Backend Node.js** :
```bash
npm start
```
Ou en mode développement :
```bash
npm run dev
```

L'application sera disponible sur http://localhost:3000

### Exemples de commandes

**Créer un projet** :
```
Crée-moi un jeu Snake en HTML/CSS/JS avec scores
```

**Déboguer visuellement** :
```
Prends un screenshot de http://localhost:3000 et analyse les bugs visuels
```

**Générer une documentation** :
```
Génère un README.md complet pour ce projet
```

**Recherche web** (si Toggle Internet activé) :
```
Recherche les meilleures pratiques pour sécuriser une API REST Node.js
```

## 📁 Structure du projet

```
Orbit/
├── app.py                    # 🧠 Moteur principal Orbit v4
├── orbit_terminal.py         # 💻 Mode terminal (optionnel)
├── check_models.py           # 🔍 Vérificateur de modèles Anthropic
├── requirements.txt          # 📦 Dépendances Python
├── package.json              # 📦 Dépendances Node.js
├── .env                      # 🔐 Configuration (à créer)
│
├── templates/                # 🌐 Interface web Flask
│   └── index.html
│
├── static/                   # 🎨 Assets statiques
│   ├── css/
│   ├── js/
│   └── screenshots/          # 📸 Captures d'écran générées
│
├── backend/                  # 🖥️ Exemple SaaS - Backend Node.js
│   └── server.js
│
├── frontend/                 # 🎨 Exemple SaaS - Frontend
│   ├── index.html
│   ├── style.css
│   └── app.js
│
└── Orbit_Projects/           # 📂 Projets générés par Orbit
    └── [vos-projets]/
```

## 🎯 Modes de fonctionnement

### 1. **Mode CHAT**
Conversation libre avec l'IA sans exécution de code.

### 2. **Mode DEV**
Création de projets, exécution de commandes, gestion de fichiers.

### 3. **Mode README**
Génération automatique de documentation (comme ce fichier !).

### 4. **Mode DEBUG_VISUAL**
Capture d'écran + Analyse visuelle pour détecter les bugs UI/UX.

## 🔧 Configuration avancée

### Toggle Internet
Par défaut, l'accès Internet est **désactivé**. Pour l'activer :
- Interface web : Cochez "Activer Internet"
- Code : `CONFIG["internet_enabled"] = True`

### Modèles IA
Modifiez dans `.env` :
- **ORBIT_MODEL** : Modèle par défaut (Sonnet 4.5 recommandé)
- **ORBIT_OPUS_MODEL** : Modèle premium pour tâches complexes

### Limites d'autonomie
```env
ORBIT_MAX_LOOPS=5          # Nombre max d'itérations The Loop
ORBIT_MAX_TOKENS=4096      # Tokens max par requête
ORBIT_COMMAND_TIMEOUT=60   # Timeout commandes (secondes)
```

## 📊 Exemple : Subscription Manager SaaS

Le projet inclut une application SaaS complète de gestion d'abonnements bancaires :

**Fonctionnalités** :
- Upload et analyse de relevés bancaires (CSV, PDF)
- Détection automatique d'abonnements récurrents
- Tableau de bord analytique
- API REST pour intégrations

**Stack technique** :
- Backend : Node.js + Express
- Frontend : Vanilla JS + Chart.js
- Parsing : Multer + csv-parser + pdf-parse

## 🐛 Dépannage

### "ANTHROPIC_API_KEY manquante"
→ Créez un fichier `.env` avec votre clé API.

### "Playwright non installé"
```bash
pip install playwright
playwright install chromium
```

### "GitHub CLI non installé"
```bash
winget install GitHub.cli  # Windows
brew install gh            # macOS
```

### Erreur "Modèle non disponible"
Vérifiez les modèles autorisés :
```bash
python check_models.py
```

## 📜 Licence

**MIT License**

Copyright (c) 2025 Orbit Project

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

## 🤝 Contribution

Les contributions sont les bienvenues ! Pour contribuer :

1. Forkez le projet
2. Créez une branche (`git checkout -b feature/AmazingFeature`)
3. Committez vos changements (`git commit -m 'Add AmazingFeature'`)
4. Pushez vers la branche (`git push origin feature/AmazingFeature`)
5. Ouvrez une Pull Request

## 📞 Support

- **Issues** : [GitHub Issues](https://github.com/votre-username/orbit/issues)
- **Documentation** : Ce README + commentaires dans le code
- **API Anthropic** : [Documentation officielle](https://docs.anthropic.com)

## 🌟 Crédits

Développé avec ❤️ par **ANTIGRAVITY STUDIO**  
Propulsé par **Claude (Anthropic)**

---

**Version actuelle** : 4.0 - Vision & Network Edition  
**Dernière mise à jour** : 2025
