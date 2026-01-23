# Orbit

## Description

Orbit est un assistant IA autonome pour le développement de projets web. Il intègre une architecture à machine d'états avec classification d'intentions (CHAT/DEV/README/DEBUG_VISUAL), une boucle d'autonomie pour l'auto-correction, la vision par ordinateur via Playwright, et un accès Internet contrôlé. L'application permet de générer du code, déboguer visuellement des interfaces, créer de la documentation et gérer des projets de manière automatisée.

## Technologies

- **Backend**: Python (Flask), Node.js (Express)
- **IA**: Anthropic Claude (Sonnet 4.5, Opus 4)
- **Vision**: Playwright (screenshots), Claude Vision API
- **Web**: HTML, CSS, JavaScript
- **Outils**: Git, GitHub CLI, DuckDuckGo Search
- **Autres**: Multer, CSV-Parser, PDF-Parse, python-dotenv, colorama

## Installation

### Prérequis

- Python 3.8+
- Node.js 16+
- Git
- GitHub CLI (optionnel)

### Backend Python (Orbit Core)

```bash
# Cloner le projet
git clone <url-du-repo>
cd orbit

# Installer les dépendances Python
pip install -r requirements.txt

# Installer Playwright
playwright install chromium

# Configurer les variables d'environnement
cp .env.example .env
# Éditer .env et ajouter votre ANTHROPIC_API_KEY
```

### Backend Node.js (Subscription Manager)

```bash
# Installer les dépendances Node.js
npm install
```

### Configuration

Créer un fichier `.env` à la racine avec :

```env
ANTHROPIC_API_KEY=your_api_key_here
ORBIT_MODEL=claude-sonnet-4-5-20250929
ORBIT_OPUS_MODEL=claude-opus-4-20250514
PROJECTS_ROOT=~/Orbit_Projects
ORBIT_MAX_TOKENS=4096
ORBIT_COMMAND_TIMEOUT=60
ORBIT_AUTO_GITHUB=true
ORBIT_MAX_LOOPS=5
```

## Usage

### Lancer Orbit (Assistant IA)

```bash
python app.py
```

L'interface web sera disponible sur `http://localhost:5000`

### Lancer le Subscription Manager

```bash
# Mode production
npm start

# Mode développement (avec auto-reload)
npm run dev
```

L'API sera disponible sur `http://localhost:3000`

### Vérifier les modèles disponibles

```bash
python check_models.py
```

## Fonctionnalités principales

### Orbit Core

- **Classification d'intentions** : CHAT, DEV, README, DEBUG_VISUAL
- **Boucle d'autonomie** : Auto-correction jusqu'à 5 itérations
- **Vision par ordinateur** : Screenshots automatiques et analyse visuelle
- **Accès Internet** : Recherche web (DuckDuckGo) et lecture de pages
- **Mémoire Self-Healing** : Sauvegarde des solutions de bugs
- **Smart Search** : Recherche optimisée dans le code
- **Serveurs en arrière-plan** : Live preview pour Node.js/Python
- **Gestion Git** : Commits automatiques et intégration GitHub

### Subscription Manager

- Upload et analyse de fichiers bancaires (CSV, PDF)
- Détection automatique des abonnements
- API REST pour la gestion des données

## Structure du projet

```
orbit/
├── app.py                      # Application Flask principale (Orbit Core)
├── requirements.txt            # Dépendances Python
├── package.json                # Configuration Node.js
├── .env                        # Variables d'environnement (à créer)
├── check_models.py             # Utilitaire de vérification des modèles Claude
├── index.html                  # Interface web (Snake Game - exemple)
├── screenshots/                # Dossier des captures d'écran
├── orbit_memory.json           # Mémoire persistante de l'IA
├── backend/
│   └── server.js               # Serveur Node.js (Subscription Manager)
└── templates/                  # Templates Flask (si utilisés)
```

## API Tools disponibles

- `read_file` : Lecture de fichiers
- `write_file` : Création/modification de fichiers
- `run_command` : Exécution PowerShell (timeout 60s)
- `list_files` : Liste des fichiers d'un dossier
- `git_commit` : Commit Git automatique
- `smart_search` : Recherche intelligente dans le code
- `find_function` : Localisation de fonctions/classes
- `start_server` / `stop_server` : Gestion de serveurs en arrière-plan
- `take_screenshot` : Capture d'écran avec Playwright
- `analyze_screenshot` : Analyse visuelle avec Claude Vision
- `web_search` : Recherche DuckDuckGo
- `read_webpage` : Lecture de contenu web
- `save_bug_fix` : Sauvegarde de solutions dans la mémoire

## Configuration avancée

### Limites de sécurité

Les commandes dangereuses sont automatiquement bloquées :
- `rm -rf /`, `format c:`, `shutdown`, etc.
- Injection de code via `iex()`, `invoke-expression`

### Modèles IA

Par défaut, Orbit utilise :
- **Sonnet 4.5** pour la classification et le développement
- **Opus 4** pour les tâches complexes (optionnel)

Modifiez `ORBIT_MODEL` et `ORBIT_OPUS_MODEL` dans `.env` pour changer.

### Toggle Internet

L'accès Internet est désactivé par défaut. Pour l'activer, modifiez `internet_enabled` dans le fichier de configuration de l'application web.

## Licence

MIT

## Support

Pour toute question ou problème, consultez les logs de l'application ou vérifiez la configuration de votre clé API Anthropic.
