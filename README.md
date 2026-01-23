# Orbit

## Description

**Orbit** est un assistant de développement intelligent alimenté par l'API Claude d'Anthropic. Il combine classification d'intentions, boucle d'autonomie, vision par ordinateur (screenshots + analyse), et accès contrôlé à Internet pour automatiser le développement de projets full-stack.

Conçu comme une **State Machine** avec gestion multi-agents (Boss, Coder, Reviewer), Orbit peut générer du code, débugger visuellement, créer de la documentation, et apprendre de ses erreurs via un système de mémoire self-healing.

## Technologies

- **Backend**: Python 3.x (Flask)
- **Frontend**: HTML5, CSS3, JavaScript
- **API**: Anthropic Claude (Sonnet 4.5, Opus 4)
- **Vision**: Playwright (screenshots headless)
- **Recherche**: DuckDuckGo Search
- **Outils**: Git, GitHub CLI, Node.js

## Installation

### Prérequis

- Python 3.8+
- Node.js 16+ (pour projets générés)
- Git
- Clé API Anthropic (Claude)

### Étapes

```bash
# Cloner le dépôt
git clone https://github.com/votre-repo/orbit.git
cd orbit

# Installer les dépendances Python
pip install -r requirements.txt

# Installer Playwright (pour la vision)
playwright install chromium

# Configurer les variables d'environnement
cp .env.example .env
# Éditer .env et ajouter votre ANTHROPIC_API_KEY

# Installer les dépendances Node.js (si nécessaire)
npm install
```

### Configuration `.env`

```env
ANTHROPIC_API_KEY=votre_cle_api_ici
ORBIT_MODEL=claude-sonnet-4-5-20250929
ORBIT_OPUS_MODEL=claude-opus-4-20250514
PROJECTS_ROOT=~/Orbit_Projects
ORBIT_MAX_TOKENS=4096
ORBIT_MAX_LOOPS=5
```

## Usage

### Lancer l'application

```bash
# Démarrer le serveur Flask
python app.py

# Ouvrir le navigateur sur http://localhost:5000
```

### Vérifier les modèles disponibles

```bash
python check_models.py
```

### Commandes principales

- **Chat**: Conversation naturelle avec l'IA
- **Dev**: Génération de code autonome avec The Loop
- **README**: Création automatique de documentation
- **Debug Visual**: Screenshots + analyse d'interface avec Vision AI

### Exemple de projet Node.js

```bash
# Les projets générés incluent leur propre setup
cd ~/Orbit_Projects/mon-projet

# Installer les dépendances
npm install

# Lancer le serveur
npm start
```

## Structure du projet

```
orbit/
├── app.py                  # Serveur Flask principal (State Machine + Agents)
├── requirements.txt        # Dépendances Python
├── package.json            # Dépendances Node.js (si applicable)
├── check_models.py         # Utilitaire vérification API
├── templates/
│   └── index.html          # Interface web
├── static/                 # Assets statiques
├── screenshots/            # Captures d'écran (Vision AI)
├── orbit_memory.json       # Mémoire self-healing
└── README.md               # Ce fichier
```

## Fonctionnalités avancées

### Intent Classification
Détecte automatiquement le type de requête (CHAT/DEV/README/DEBUG_VISUAL) pour choisir la meilleure stratégie.

### The Loop (Boucle d'Autonomie)
Jusqu'à 5 itérations autonomes pour résoudre des tâches complexes sans intervention humaine.

### Vision AI
- Screenshots via Playwright
- Analyse avec Claude Vision API
- Détection de bugs visuels

### Internet Toggle
Recherche web (DuckDuckGo) et lecture de pages activable/désactivable.

### Self-Healing Memory
Sauvegarde les solutions de bugs pour référence future et apprentissage continu.

## Réalisation

**Développé par Anis Kherraf avec l'assistance de Claude Code (Anthropic)**

Ce projet démontre l'intégration avancée d'IA générative dans un workflow de développement moderne, combinant autonomie, vision par ordinateur, et orchestration multi-agents.

## Licence

MIT

---

**Made with ❤️ by ANTIGRAVITY STUDIO**
