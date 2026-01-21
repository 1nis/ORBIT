"""
ORBIT - Multi-Agent Development Studio
Architecture: BOSS (Planning) → CODER (Execution) → REVIEWER (Validation)

Version: 2.0 - Production Ready
Améliorations:
- Configuration centralisée via .env
- Persistance de la mémoire (orbit_memory.json)
- Vérification des dépendances (git, gh) au démarrage
- Sécurisation des commandes (liste noire)
- Logs clairs dans la console
"""

import os
import sys
import json
import shutil
import subprocess
import logging
from datetime import datetime
from typing import Optional, Dict, List, Any, Generator

from flask import Flask, render_template, request, jsonify, send_from_directory, Response
from anthropic import Anthropic
from dotenv import load_dotenv

# ═══════════════════════════════════════════════════════════════════════════════
# INITIALISATION ET CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

# Charger les variables d'environnement
load_dotenv()

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger("ORBIT")

# Chemin par défaut pour les projets (portable via .env ou dossier utilisateur)
DEFAULT_PROJECTS_ROOT = os.path.join(os.path.expanduser("~"), "Orbit_Projects")

# Configuration centralisée depuis .env
class Config:
    """Configuration centralisée - toutes les valeurs viennent du .env ou ont des défauts."""
    
    # API
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    
    # Modèle IA (configurable via .env)
    DEFAULT_MODEL: str = os.getenv("ORBIT_MODEL", "claude-sonnet-4-5-20250929")
    OPUS_MODEL: str = os.getenv("ORBIT_OPUS_MODEL", "claude-opus-4-20250514")
    
    # Chemins (portables)
    PROJECTS_ROOT: str = os.getenv("PROJECTS_ROOT", DEFAULT_PROJECTS_ROOT)
    
    # Fichier de persistance mémoire
    MEMORY_FILE: str = os.getenv("ORBIT_MEMORY_FILE", "orbit_memory.json")
    
    # Paramètres de fonctionnement
    MAX_TOKENS: int = int(os.getenv("ORBIT_MAX_TOKENS", "8192"))
    COMMAND_TIMEOUT: int = int(os.getenv("ORBIT_COMMAND_TIMEOUT", "60"))
    
    @classmethod
    def validate(cls) -> bool:
        """Valide que la configuration minimale est présente."""
        if not cls.ANTHROPIC_API_KEY:
            logger.error("❌ ANTHROPIC_API_KEY manquante dans le fichier .env")
            return False
        return True

# Vérifier la configuration
if not Config.validate():
    logger.error("Configuration invalide. Vérifiez votre fichier .env")
    # On ne quitte pas pour permettre le debug

# Créer le dossier des projets s'il n'existe pas
if not os.path.exists(Config.PROJECTS_ROOT):
    os.makedirs(Config.PROJECTS_ROOT, exist_ok=True)
    logger.info(f"📁 Dossier projets créé: {Config.PROJECTS_ROOT}")

# ═══════════════════════════════════════════════════════════════════════════════
# VÉRIFICATION DES DÉPENDANCES
# ═══════════════════════════════════════════════════════════════════════════════

class SystemHealth:
    """Vérifie la disponibilité des outils système."""
    
    git_available: bool = False
    gh_available: bool = False
    
    @classmethod
    def check_all(cls) -> None:
        """Vérifie toutes les dépendances au démarrage."""
        logger.info("🔍 Vérification des dépendances système...")
        
        # Vérifier Git
        cls.git_available = shutil.which("git") is not None
        if cls.git_available:
            logger.info("  ✓ Git: disponible")
        else:
            logger.warning("  ✗ Git: non installé - fonctions Git désactivées")
        
        # Vérifier GitHub CLI
        cls.gh_available = shutil.which("gh") is not None
        if cls.gh_available:
            logger.info("  ✓ GitHub CLI (gh): disponible")
        else:
            logger.warning("  ✗ GitHub CLI (gh): non installé - création de repos GitHub désactivée")
    
    @classmethod
    def require_git(cls) -> Dict[str, Any]:
        """Retourne une erreur si Git n'est pas disponible."""
        if not cls.git_available:
            return {"success": False, "error": "Git n'est pas installé sur ce système"}
        return None
    
    @classmethod
    def require_gh(cls) -> Dict[str, Any]:
        """Retourne une erreur si gh n'est pas disponible."""
        if not cls.gh_available:
            return {"success": False, "error": "GitHub CLI (gh) n'est pas installé. Installez-le via: winget install GitHub.cli"}
        return None

# Vérifier les dépendances au chargement du module
SystemHealth.check_all()

# ═══════════════════════════════════════════════════════════════════════════════
# SÉCURITÉ - LISTE NOIRE DES COMMANDES
# ═══════════════════════════════════════════════════════════════════════════════

# Patterns de commandes dangereuses à bloquer
DANGEROUS_PATTERNS = [
    # Suppression système
    "rm -rf /", "rm -rf /*", "del /s /q c:\\", "format c:",
    "rd /s /q c:\\", "remove-item -recurse -force c:\\",
    # Manipulation système
    "shutdown", "restart-computer", "stop-computer",
    # Registre Windows
    "reg delete", "remove-itemproperty",
    # Téléchargements malveillants
    "invoke-webrequest", "wget", "curl -o",
    # Exécution de scripts distants
    "iex(", "invoke-expression", "downloadstring",
    # Destruction de données
    "cipher /w:", "sdelete",
]

def is_command_safe(command: str) -> tuple[bool, str]:
    """
    Vérifie si une commande est sûre à exécuter.
    Retourne (is_safe, reason_if_blocked).
    """
    cmd_lower = command.lower().strip()
    
    for pattern in DANGEROUS_PATTERNS:
        if pattern.lower() in cmd_lower:
            return False, f"Commande bloquée: contient '{pattern}'"
    
    # Bloquer les chemins système critiques
    critical_paths = ["c:\\windows", "c:\\program files", "system32", "$env:systemroot"]
    for path in critical_paths:
        if path.lower() in cmd_lower and ("remove" in cmd_lower or "del " in cmd_lower or "rd " in cmd_lower):
            return False, f"Commande bloquée: modification de chemin système '{path}'"
    
    return True, ""

# ═══════════════════════════════════════════════════════════════════════════════
# APPLICATION FLASK
# ═══════════════════════════════════════════════════════════════════════════════

app = Flask(__name__)

# Client Anthropic
try:
    client = Anthropic(api_key=Config.ANTHROPIC_API_KEY)
    logger.info("✓ Client Anthropic initialisé")
except Exception as e:
    logger.error(f"❌ Erreur initialisation Anthropic: {e}")
    client = None

# Workspace courant (modifiable dynamiquement)
WORKSPACE_DIR = os.getcwd()

# ═══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION DYNAMIQUE
# ═══════════════════════════════════════════════════════════════════════════════

CONFIG = {
    "models": {
        "boss": Config.DEFAULT_MODEL,
        "coder": Config.DEFAULT_MODEL,
        "reviewer": Config.DEFAULT_MODEL
    },
    "autopilot": True,
    "max_iterations": 15,
    "max_retries": 3
}

USAGE_STATS = {
    "total_input_tokens": 0,
    "total_output_tokens": 0,
    "calls": []
}

# ═══════════════════════════════════════════════════════════════════════════════
# SYSTÈME DE PERSISTANCE (MÉMOIRE)
# ═══════════════════════════════════════════════════════════════════════════════

class MemoryManager:
    """Gère la persistance de l'historique des conversations."""
    
    def __init__(self, memory_file: str = None):
        self.memory_file = memory_file or Config.MEMORY_FILE
        self._ensure_memory_dir()
    
    def _ensure_memory_dir(self) -> None:
        """S'assure que le dossier de mémoire existe."""
        memory_dir = os.path.dirname(self.memory_file)
        if memory_dir and not os.path.exists(memory_dir):
            os.makedirs(memory_dir, exist_ok=True)
    
    def _get_memory_path(self) -> str:
        """Retourne le chemin complet du fichier mémoire pour le projet courant."""
        global WORKSPACE_DIR
        return os.path.join(WORKSPACE_DIR, self.memory_file)
    
    def save(self, orchestrator: 'AgentOrchestrator') -> bool:
        """Sauvegarde l'état de l'orchestrateur."""
        try:
            memory_path = self._get_memory_path()
            data = {
                "saved_at": datetime.now().isoformat(),
                "workspace": WORKSPACE_DIR,
                "conversation_boss": orchestrator.conversation_boss,
                "conversation_coder": orchestrator.conversation_coder,
                "conversation_reviewer": orchestrator.conversation_reviewer,
                "created_files": orchestrator.created_files,
                "usage_stats": USAGE_STATS
            }
            
            with open(memory_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2, default=str)
            
            logger.info(f"💾 Mémoire sauvegardée: {memory_path}")
            return True
        except Exception as e:
            logger.error(f"❌ Erreur sauvegarde mémoire: {e}")
            return False
    
    def load(self, orchestrator: 'AgentOrchestrator') -> bool:
        """Charge l'état depuis le fichier mémoire."""
        try:
            memory_path = self._get_memory_path()
            
            if not os.path.exists(memory_path):
                logger.info("📝 Aucune mémoire précédente trouvée - nouvelle session")
                return False
            
            with open(memory_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            # Restaurer les conversations
            orchestrator.conversation_boss = data.get("conversation_boss", [])
            orchestrator.conversation_coder = data.get("conversation_coder", [])
            orchestrator.conversation_reviewer = data.get("conversation_reviewer", [])
            orchestrator.created_files = data.get("created_files", [])
            
            # Restaurer les stats d'usage
            global USAGE_STATS
            if "usage_stats" in data:
                USAGE_STATS.update(data["usage_stats"])
            
            saved_at = data.get("saved_at", "date inconnue")
            logger.info(f"🧠 Mémoire restaurée depuis: {saved_at}")
            return True
        except Exception as e:
            logger.error(f"❌ Erreur chargement mémoire: {e}")
            return False
    
    def clear(self) -> bool:
        """Efface le fichier mémoire."""
        try:
            memory_path = self._get_memory_path()
            if os.path.exists(memory_path):
                os.remove(memory_path)
                logger.info("🗑️ Mémoire effacée")
            return True
        except Exception as e:
            logger.error(f"❌ Erreur effacement mémoire: {e}")
            return False

# Instance globale du gestionnaire de mémoire
memory_manager = MemoryManager()

# ═══════════════════════════════════════════════════════════════════════════════
# OUTILS (TOOLS) POUR LES AGENTS
# ═══════════════════════════════════════════════════════════════════════════════

TOOLS = [
    {
        "name": "read_file",
        "description": "Lit le contenu d'un fichier. Retourne le contenu ou une erreur.",
        "input_schema": {
            "type": "object",
            "properties": {
                "filename": {"type": "string", "description": "Chemin relatif du fichier"}
            },
            "required": ["filename"]
        }
    },
    {
        "name": "write_file",
        "description": "Cree ou modifie un fichier. Cree les dossiers parents si necessaire.",
        "input_schema": {
            "type": "object",
            "properties": {
                "filename": {"type": "string", "description": "Chemin relatif du fichier"},
                "content": {"type": "string", "description": "Contenu complet du fichier"}
            },
            "required": ["filename", "content"]
        }
    },
    {
        "name": "run_command",
        "description": "Execute une commande PowerShell. Retourne stdout/stderr. Certaines commandes dangereuses sont bloquées.",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Commande PowerShell"}
            },
            "required": ["command"]
        }
    },
    {
        "name": "list_files",
        "description": "Liste les fichiers d'un repertoire.",
        "input_schema": {
            "type": "object",
            "properties": {
                "directory": {"type": "string", "description": "Chemin du dossier (. pour racine)"}
            },
            "required": ["directory"]
        }
    },
    {
        "name": "git_commit",
        "description": "Fait un commit Git avec message descriptif.",
        "input_schema": {
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "Message de commit"}
            },
            "required": ["message"]
        }
    },
    {
        "name": "git_push",
        "description": "Push les commits vers le remote origin.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "git_diff",
        "description": "Affiche les differences des fichiers modifies.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    }
]

# ═══════════════════════════════════════════════════════════════════════════════
# MOTEUR D'EXÉCUTION DES OUTILS
# ═══════════════════════════════════════════════════════════════════════════════

def execute_tool(name: str, args: dict) -> dict:
    """Exécute un outil et retourne le résultat structuré."""
    global WORKSPACE_DIR
    
    logger.info(f"🔧 Exécution outil: {name}")
    
    try:
        if name == "read_file":
            path = os.path.join(WORKSPACE_DIR, args["filename"])
            if not os.path.exists(path):
                return {"success": False, "error": f"Fichier non trouvé: {args['filename']}"}
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            return {"success": True, "content": content[:5000], "size": len(content)}

        elif name == "write_file":
            path = os.path.join(WORKSPACE_DIR, args["filename"])
            parent_dir = os.path.dirname(path)
            if parent_dir:
                os.makedirs(parent_dir, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(args["content"])
            logger.info(f"  📝 Fichier créé: {args['filename']}")
            return {"success": True, "message": f"Fichier créé: {args['filename']}", "filename": args["filename"]}

        elif name == "run_command":
            command = args["command"]
            
            # Vérification de sécurité
            is_safe, reason = is_command_safe(command)
            if not is_safe:
                logger.warning(f"  ⚠️ {reason}")
                return {"success": False, "error": reason}
            
            result = subprocess.run(
                ["powershell", "-Command", command],
                capture_output=True, text=True, cwd=WORKSPACE_DIR, 
                timeout=Config.COMMAND_TIMEOUT
            )
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout.strip()[:2000] if result.stdout else "",
                "stderr": result.stderr.strip()[:1000] if result.stderr else "",
                "return_code": result.returncode
            }

        elif name == "list_files":
            path = os.path.join(WORKSPACE_DIR, args.get("directory", "."))
            if not os.path.exists(path):
                return {"success": False, "error": f"Dossier non trouvé: {path}"}
            items = []
            for item in os.listdir(path):
                if not item.startswith('.') and item not in ['__pycache__', 'venv', 'node_modules']:
                    full = os.path.join(path, item)
                    items.append({"name": item, "type": "dir" if os.path.isdir(full) else "file"})
            return {"success": True, "items": items}

        elif name == "git_commit":
            # Vérifier que Git est disponible
            check = SystemHealth.require_git()
            if check:
                return check
            
            subprocess.run(["powershell", "-Command", "git add -A"], cwd=WORKSPACE_DIR, capture_output=True)
            result = subprocess.run(
                ["powershell", "-Command", f'git commit -m "{args["message"]}"'],
                capture_output=True, text=True, cwd=WORKSPACE_DIR
            )
            if result.returncode == 0 or "nothing to commit" in (result.stdout + result.stderr).lower():
                logger.info(f"  ✓ Commit: {args['message']}")
                return {"success": True, "message": f"Commit: {args['message']}"}
            return {"success": False, "error": result.stderr or result.stdout}

        elif name == "git_push":
            check = SystemHealth.require_git()
            if check:
                return check
            
            result = subprocess.run(
                ["powershell", "-Command", "git push"],
                capture_output=True, text=True, cwd=WORKSPACE_DIR
            )
            return {"success": result.returncode == 0, "output": result.stdout or result.stderr}

        elif name == "git_diff":
            check = SystemHealth.require_git()
            if check:
                return check
            
            result = subprocess.run(
                ["powershell", "-Command", "git diff --stat"],
                capture_output=True, text=True, cwd=WORKSPACE_DIR
            )
            return {"success": True, "diff": result.stdout[:3000] if result.stdout else "Aucun changement"}

        return {"success": False, "error": f"Outil inconnu: {name}"}

    except subprocess.TimeoutExpired:
        logger.error(f"  ⏱️ Timeout pour {name}")
        return {"success": False, "error": f"Timeout (>{Config.COMMAND_TIMEOUT}s)"}
    except Exception as e:
        logger.error(f"  ❌ Erreur {name}: {e}")
        return {"success": False, "error": str(e)}

# ═══════════════════════════════════════════════════════════════════════════════
# PROMPTS SYSTÈME DES AGENTS
# ═══════════════════════════════════════════════════════════════════════════════

BOSS_PROMPT = """Tu es le BOSS de l'equipe de developpement.

## TON ROLE
- Analyser les demandes utilisateur
- Creer un plan d'action clair et structure
- Deleguer les taches au CODER
- Valider le travail du REVIEWER
- Prendre les decisions finales

## TES RESPONSABILITES
1. Quand tu recois une demande, cree un PLAN avec les etapes numerotees
2. Envoie les instructions claires au CODER via [INSTRUCTION_CODER]
3. Attends le rapport du REVIEWER avant de valider
4. Fais les commits Git quand le travail est valide

## FORMAT DE REPONSE
[ANALYSE]
Description de ce que l'utilisateur veut

[PLAN]
1. Etape 1
2. Etape 2
...

[INSTRUCTION_CODER]
Instructions detaillees pour le CODER

## REGLES
- Sois concis mais precis
- Ne fais PAS le code toi-meme, delegue au CODER
- Utilise git_commit uniquement apres validation du REVIEWER
- Si une erreur persiste apres 3 tentatives, arrete et explique
- NE JAMAIS inclure de nom d'auteur, signature ou credit dans le code"""

CODER_PROMPT = """Tu es le CODER de l'equipe de developpement sur Windows.

## TON ROLE
- Ecrire du code propre, modulaire et maintenable
- Separer les responsabilites (HTML structure, CSS style, JS logic)

## TES OUTILS
- write_file, read_file, run_command, list_files

## REGLES STRICTES
1. SEPARATION DES FICHIERS : Ne fais JAMAIS de CSS/JS inline geant.
   - Cree `index.html` pour la structure
   - Cree `style.css` pour le design
   - Cree `script.js` pour la logique
2. PowerShell : Utilise 'dir' au lieu de 'ls', 'type' au lieu de 'cat'
3. Erreurs: Si une commande echoue, analyse l'erreur et corrige SANS demander
4. Design : Utilise des classes modernes, du dark mode par defaut.
5. Imports : N'oublie pas de lier les fichiers dans le HTML (<link>, <script src...>)
6. ANONYMAT : NE JAMAIS inclure de nom d'auteur, signature, credit ou commentaire d'attribution

## FORMAT DE REPONSE
[ACTION] Explication...
[EXECUTION] (Outils...)
[RESULTAT] Resume..."""

REVIEWER_PROMPT = """Tu es le REVIEWER de l'equipe de developpement.

## TON ROLE
- Verifier le travail du CODER
- Generer une checklist de validation
- Identifier les bugs ou problemes
- Suggerer des corrections si necessaire

## TES RESPONSABILITES
1. Lire les fichiers crees/modifies avec read_file
2. Verifier que le code respecte les bonnes pratiques
3. Tester les commandes si necessaire
4. Creer un rapport de review

## FORMAT DE REPONSE
[REVIEW]
Fichiers verifies: liste

[CHECKLIST]
- [ ] ou [x] Point de verification 1
- [ ] ou [x] Point de verification 2
...

[VERDICT]
APPROUVE ou CORRECTIONS_REQUISES

[CORRECTIONS] (si necessaire)
Liste des corrections a apporter"""

# ═══════════════════════════════════════════════════════════════════════════════
# ORCHESTRATEUR MULTI-AGENTS
# ═══════════════════════════════════════════════════════════════════════════════

class AgentOrchestrator:
    """Orchestre les agents BOSS, CODER et REVIEWER."""
    
    def __init__(self):
        self.conversation_boss: List[Dict] = []
        self.conversation_coder: List[Dict] = []
        self.conversation_reviewer: List[Dict] = []
        self.created_files: List[str] = []
        self.current_agent: str = "boss"
        
    def reset(self) -> None:
        """Réinitialise toutes les conversations."""
        self.conversation_boss = []
        self.conversation_coder = []
        self.conversation_reviewer = []
        self.created_files = []
        self.current_agent = "boss"
        logger.info("🔄 Orchestrateur réinitialisé")
    
    def track_usage(self, response, agent: str) -> None:
        """Enregistre l'utilisation de l'API."""
        if hasattr(response, 'usage'):
            USAGE_STATS["total_input_tokens"] += response.usage.input_tokens
            USAGE_STATS["total_output_tokens"] += response.usage.output_tokens
            USAGE_STATS["calls"].append({
                "agent": agent,
                "input": response.usage.input_tokens,
                "output": response.usage.output_tokens,
                "time": datetime.now().isoformat()
            })
    
    def call_agent(self, agent: str, messages: list, system_prompt: str):
        """Appelle un agent spécifique."""
        if not client:
            raise RuntimeError("Client Anthropic non initialisé. Vérifiez votre clé API.")
        
        model = CONFIG["models"].get(agent, CONFIG["models"]["coder"])
        
        response = client.messages.create(
            model=model,
            max_tokens=Config.MAX_TOKENS,
            system=system_prompt,
            messages=messages,
            tools=TOOLS
        )
        
        self.track_usage(response, agent)
        return response
    
    def process_tool_calls(self, response, conversation: list) -> List[Dict]:
        """Traite les appels d'outils et retourne les résultats."""
        results = []
        assistant_content = []
        
        for block in response.content:
            if block.type == "text":
                assistant_content.append({"type": "text", "text": block.text})
            elif block.type == "tool_use":
                assistant_content.append({
                    "type": "tool_use",
                    "id": block.id,
                    "name": block.name,
                    "input": block.input
                })
                
                result = execute_tool(block.name, block.input)
                results.append({
                    "tool": block.name,
                    "input": block.input,
                    "result": result,
                    "id": block.id
                })
                
                if block.name == "write_file" and result.get("success"):
                    filename = block.input.get("filename", "")
                    if filename not in self.created_files:
                        self.created_files.append(filename)
        
        if assistant_content:
            conversation.append({"role": "assistant", "content": assistant_content})
        
        return results
    
    def run_agent_loop(self, agent: str, initial_message: str, system_prompt: str, 
                       conversation: list, max_turns: int = 5) -> Generator:
        """Exécute un agent jusqu'à complétion ou max_turns."""
        if not conversation or conversation[-1]["role"] != "user":
            conversation.append({"role": "user", "content": initial_message})
        
        for turn in range(max_turns):
            response = self.call_agent(agent, conversation, system_prompt)
            tool_results = self.process_tool_calls(response, conversation)
            
            for block in response.content:
                if block.type == "text":
                    yield {"type": "agent_text", "agent": agent, "content": block.text}
            
            for tr in tool_results:
                yield {"type": "tool_result", "agent": agent, "tool": tr["tool"], 
                       "success": tr["result"].get("success", False), "result": tr["result"]}
            
            if tool_results:
                tool_results_content = []
                for tr in tool_results:
                    tool_results_content.append({
                        "type": "tool_result",
                        "tool_use_id": tr["id"],
                        "content": json.dumps(tr["result"], ensure_ascii=False)
                    })
                conversation.append({"role": "user", "content": tool_results_content})
            else:
                break
        
        yield {"type": "agent_complete", "agent": agent}

    def orchestrate(self, user_message: str) -> Generator:
        """Flux principal: BOSS -> CODER -> REVIEWER -> GIT."""
        logger.info(f"🚀 Nouvelle demande: {user_message[:50]}...")
        
        yield {"type": "phase", "phase": "BOSS", "status": "Planning"}
        
        self.conversation_boss.append({"role": "user", "content": user_message})
        
        response = self.call_agent("boss", self.conversation_boss, BOSS_PROMPT)
        
        boss_text = ""
        for block in response.content:
            if block.type == "text":
                boss_text = block.text
                yield {"type": "agent_text", "agent": "boss", "content": block.text}
        
        self.conversation_boss.append({"role": "assistant", "content": response.content})
        
        coder_instructions = boss_text
        if "[INSTRUCTION_CODER]" in boss_text:
            coder_instructions = boss_text.split("[INSTRUCTION_CODER]")[-1].strip()
        
        yield {"type": "phase", "phase": "CODER", "status": "Coding"}
        
        self.conversation_coder = [{"role": "user", "content": f"Instructions du BOSS:\n{coder_instructions}"}]
        
        for event in self.run_agent_loop("coder", coder_instructions, CODER_PROMPT, self.conversation_coder, max_turns=8):
            yield event
        
        yield {"type": "phase", "phase": "REVIEWER", "status": "Reviewing"}
        
        files_to_review = ", ".join(self.created_files) if self.created_files else "les fichiers modifiés"
        review_request = f"Vérifie le travail du CODER sur: {files_to_review}"
        
        self.conversation_reviewer = [{"role": "user", "content": review_request}]
        
        reviewer_verdict = "APPROUVE"
        for event in self.run_agent_loop("reviewer", review_request, REVIEWER_PROMPT, self.conversation_reviewer, max_turns=3):
            yield event
            if event.get("type") == "agent_text" and "CORRECTIONS_REQUISES" in event.get("content", ""):
                reviewer_verdict = "CORRECTIONS_REQUISES"
        
        if reviewer_verdict == "APPROUVE" or CONFIG["autopilot"]:
            if SystemHealth.git_available:
                yield {"type": "phase", "phase": "GIT", "status": "Committing"}
                
                commit_msg = f"feat: {user_message[:50]}"
                result = execute_tool("git_commit", {"message": commit_msg})
                
                yield {"type": "tool_result", "agent": "boss", "tool": "git_commit", 
                       "success": result.get("success", False), "result": result}
            else:
                logger.warning("⚠️ Git non disponible, commit ignoré")
        
        # Sauvegarder la mémoire après chaque échange
        memory_manager.save(self)
        
        html_files = [f for f in self.created_files if f.endswith(('.html', '.htm'))]
        yield {
            "type": "complete",
            "files": self.created_files,
            "preview": html_files[0] if html_files else None
        }

# Instance globale de l'orchestrateur
orchestrator = AgentOrchestrator()

# Charger la mémoire au démarrage
memory_manager.load(orchestrator)

# ═══════════════════════════════════════════════════════════════════════════════
# FONCTIONS HELPER GIT
# ═══════════════════════════════════════════════════════════════════════════════

def get_git_status() -> str:
    """Récupère le statut Git."""
    if not SystemHealth.git_available:
        return ""
    result = subprocess.run(
        ["powershell", "-Command", "git status --porcelain"],
        capture_output=True, text=True, cwd=WORKSPACE_DIR
    )
    return result.stdout.strip() if result.returncode == 0 else ""

def generate_commit_message() -> Optional[str]:
    """Génère un message de commit automatique."""
    status = get_git_status()
    if not status:
        return None
    
    lines = status.split('\n')
    added = [l[3:] for l in lines if l.startswith('A ') or l.startswith('?? ')]
    modified = [l[3:] for l in lines if l.startswith('M ') or l.startswith(' M')]
    deleted = [l[3:] for l in lines if l.startswith('D ')]
    
    parts = []
    if added:
        parts.append(f"add {', '.join(added[:3])}" + (" ..." if len(added) > 3 else ""))
    if modified:
        parts.append(f"update {', '.join(modified[:3])}" + (" ..." if len(modified) > 3 else ""))
    if deleted:
        parts.append(f"remove {', '.join(deleted[:3])}" + (" ..." if len(deleted) > 3 else ""))
    
    if not parts:
        return "chore: minor changes"
    
    return "; ".join(parts)[:72]

def generate_readme_content() -> str:
    """Génère le contenu du README."""
    files = []
    for item in os.listdir(WORKSPACE_DIR):
        if not item.startswith('.') and item not in ['__pycache__', 'venv', 'node_modules', 'templates']:
            files.append(item)
    
    has_html = any(f.endswith('.html') for f in files)
    has_py = any(f.endswith('.py') for f in files)
    
    project_name = os.path.basename(WORKSPACE_DIR)
    
    readme = f"""# {project_name}

## Description

Project generated with ORBIT Development Studio.

## Files

"""
    for f in sorted(files):
        readme += f"- `{f}`\n"
    
    readme += "\n## Getting Started\n\n"
    
    if has_html:
        readme += "Open `index.html` in your browser to view the project.\n\n"
    if has_py:
        readme += "```bash\npython app.py\n```\n\n"
    
    readme += "## License\n\nMIT\n"
    
    return readme

# ═══════════════════════════════════════════════════════════════════════════════
# ROUTES FLASK
# ═══════════════════════════════════════════════════════════════════════════════

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/view/<path:filename>')
def serve_file(filename):
    return send_from_directory(WORKSPACE_DIR, filename)

@app.route('/chat', methods=['POST'])
def chat():
    user_message = request.json.get('message', '')
    if not user_message:
        return jsonify({"error": "Message vide"}), 400
    
    def generate():
        for event in orchestrator.orchestrate(user_message):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
    
    return Response(generate(), mimetype='text/event-stream')

@app.route('/reset', methods=['POST'])
def reset():
    orchestrator.reset()
    memory_manager.clear()
    return jsonify({"success": True})

@app.route('/config', methods=['GET', 'POST'])
def config_route():
    if request.method == 'POST':
        data = request.json
        if 'autopilot' in data:
            CONFIG['autopilot'] = data['autopilot']
        if 'model' in data and data['model'] in ['opus', 'sonnet']:
            model_name = Config.OPUS_MODEL if data['model'] == 'opus' else Config.DEFAULT_MODEL
            CONFIG['models']['boss'] = model_name
        return jsonify({"success": True, "config": CONFIG})
    return jsonify(CONFIG)

@app.route('/usage')
def usage():
    return jsonify(USAGE_STATS)

@app.route('/files')
def list_workspace_files():
    files = []
    for item in os.listdir(WORKSPACE_DIR):
        if not item.startswith('.') and item not in ['__pycache__', 'templates', 'venv', 'node_modules']:
            path = os.path.join(WORKSPACE_DIR, item)
            if os.path.isfile(path):
                files.append({"name": item, "size": os.path.getsize(path)})
    return jsonify(files)

@app.route('/health')
def health():
    """Endpoint de santé du système."""
    return jsonify({
        "status": "ok",
        "git_available": SystemHealth.git_available,
        "gh_available": SystemHealth.gh_available,
        "workspace": WORKSPACE_DIR,
        "projects_root": Config.PROJECTS_ROOT,
        "model": Config.DEFAULT_MODEL
    })

# ═══════════════════════════════════════════════════════════════════════════════
# ROUTES API GIT
# ═══════════════════════════════════════════════════════════════════════════════

@app.route('/git/status')
def git_status_route():
    check = SystemHealth.require_git()
    if check:
        return jsonify(check)
    
    result = subprocess.run(
        ["powershell", "-Command", "git status --short"],
        capture_output=True, text=True, cwd=WORKSPACE_DIR
    )
    return jsonify({
        "success": result.returncode == 0,
        "status": result.stdout.strip() if result.stdout else "Clean",
        "error": result.stderr.strip() if result.stderr else None
    })

@app.route('/git/diff')
def git_diff_route():
    check = SystemHealth.require_git()
    if check:
        return jsonify(check)
    
    result = subprocess.run(
        ["powershell", "-Command", "git diff --stat"],
        capture_output=True, text=True, cwd=WORKSPACE_DIR
    )
    return jsonify({
        "success": True,
        "diff": result.stdout.strip() if result.stdout else "Aucun changement"
    })

@app.route('/git/commit', methods=['POST'])
def git_commit_route():
    check = SystemHealth.require_git()
    if check:
        return jsonify(check)
    
    data = request.json or {}
    message = data.get('message', '').strip()
    
    if not message:
        message = generate_commit_message()
        if not message:
            return jsonify({"success": False, "error": "Rien à commiter"})
    
    subprocess.run(["powershell", "-Command", "git add -A"], cwd=WORKSPACE_DIR, capture_output=True)
    
    result = subprocess.run(
        ["powershell", "-Command", f'git commit -m "{message}"'],
        capture_output=True, text=True, cwd=WORKSPACE_DIR
    )
    
    if result.returncode == 0:
        logger.info(f"✓ Commit: {message}")
        return jsonify({"success": True, "message": message})
    elif "nothing to commit" in (result.stdout + result.stderr).lower():
        return jsonify({"success": True, "message": "Rien à commiter"})
    else:
        return jsonify({"success": False, "error": result.stderr or result.stdout})

@app.route('/git/push', methods=['POST'])
def git_push_route():
    check = SystemHealth.require_git()
    if check:
        return jsonify(check)
    
    result = subprocess.run(
        ["powershell", "-Command", "git push"],
        capture_output=True, text=True, cwd=WORKSPACE_DIR
    )
    return jsonify({
        "success": result.returncode == 0,
        "output": result.stdout.strip() or result.stderr.strip()
    })

@app.route('/git/pull', methods=['POST'])
def git_pull_route():
    check = SystemHealth.require_git()
    if check:
        return jsonify(check)
    
    result = subprocess.run(
        ["powershell", "-Command", "git pull"],
        capture_output=True, text=True, cwd=WORKSPACE_DIR
    )
    return jsonify({
        "success": result.returncode == 0,
        "output": result.stdout.strip() or result.stderr.strip()
    })

@app.route('/git/log')
def git_log_route():
    check = SystemHealth.require_git()
    if check:
        return jsonify(check)
    
    result = subprocess.run(
        ["powershell", "-Command", "git log --oneline -10"],
        capture_output=True, text=True, cwd=WORKSPACE_DIR
    )
    return jsonify({
        "success": result.returncode == 0,
        "log": result.stdout.strip() if result.stdout else "Aucun commit"
    })

# ═══════════════════════════════════════════════════════════════════════════════
# GÉNÉRATION README
# ═══════════════════════════════════════════════════════════════════════════════

@app.route('/readme/generate', methods=['POST'])
def readme_generate():
    content = generate_readme_content()
    path = os.path.join(WORKSPACE_DIR, "README.md")
    
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    
    logger.info("📄 README.md généré")
    return jsonify({
        "success": True,
        "message": "README.md généré",
        "content": content
    })

# ═══════════════════════════════════════════════════════════════════════════════
# CRÉATION DE REPO GITHUB
# ═══════════════════════════════════════════════════════════════════════════════

@app.route('/github/create', methods=['POST'])
def github_create():
    # Vérifier que gh est disponible
    check = SystemHealth.require_gh()
    if check:
        return jsonify(check)
    
    check_git = SystemHealth.require_git()
    if check_git:
        return jsonify(check_git)
    
    data = request.json or {}
    repo_name = data.get('name', os.path.basename(WORKSPACE_DIR))
    private = data.get('private', True)
    push_now = data.get('push', True)
    
    visibility = "--private" if private else "--public"
    
    # Vérifier si un remote existe déjà
    check_remote = subprocess.run(
        ["powershell", "-Command", "git remote get-url origin"],
        capture_output=True, text=True, cwd=WORKSPACE_DIR
    )
    
    if check_remote.returncode == 0 and check_remote.stdout.strip():
        return jsonify({
            "success": False,
            "error": f"Remote origin existe déjà: {check_remote.stdout.strip()}"
        })
    
    # Initialiser git si nécessaire
    subprocess.run(
        ["powershell", "-Command", "git init"],
        capture_output=True, cwd=WORKSPACE_DIR
    )
    
    # Créer le repo via gh CLI
    result = subprocess.run(
        ["powershell", "-Command", f'gh repo create {repo_name} {visibility} --source=. --remote=origin'],
        capture_output=True, text=True, cwd=WORKSPACE_DIR
    )
    
    if result.returncode != 0:
        return jsonify({
            "success": False,
            "error": result.stderr.strip() or result.stdout.strip()
        })
    
    repo_url = result.stdout.strip()
    logger.info(f"🐙 Repo GitHub créé: {repo_name}")
    
    if push_now:
        subprocess.run(["powershell", "-Command", "git add -A"], cwd=WORKSPACE_DIR, capture_output=True)
        subprocess.run(
            ["powershell", "-Command", 'git commit -m "Initial commit" --allow-empty'],
            cwd=WORKSPACE_DIR, capture_output=True
        )
        
        push_result = subprocess.run(
            ["powershell", "-Command", "git push -u origin main"],
            capture_output=True, text=True, cwd=WORKSPACE_DIR
        )
        
        if push_result.returncode != 0:
            subprocess.run(
                ["powershell", "-Command", "git push -u origin master"],
                capture_output=True, cwd=WORKSPACE_DIR
            )
    
    return jsonify({
        "success": True,
        "message": f"Repo créé: {repo_name}",
        "url": repo_url
    })

@app.route('/github/status')
def github_status():
    check = SystemHealth.require_gh()
    if check:
        return jsonify({"authenticated": False, "output": check["error"]})
    
    result = subprocess.run(
        ["powershell", "-Command", "gh auth status"],
        capture_output=True, text=True, cwd=WORKSPACE_DIR
    )
    return jsonify({
        "authenticated": result.returncode == 0,
        "output": result.stdout.strip() or result.stderr.strip()
    })

# ═══════════════════════════════════════════════════════════════════════════════
# GESTION DES PROJETS
# ═══════════════════════════════════════════════════════════════════════════════

@app.route('/projects')
def list_projects():
    """Liste tous les projets dans PROJECTS_ROOT."""
    projects = []
    if os.path.exists(Config.PROJECTS_ROOT):
        for item in os.listdir(Config.PROJECTS_ROOT):
            path = os.path.join(Config.PROJECTS_ROOT, item)
            if os.path.isdir(path) and not item.startswith('.'):
                has_git = os.path.exists(os.path.join(path, '.git'))
                projects.append({
                    "name": item,
                    "path": path,
                    "has_git": has_git,
                    "is_current": path == WORKSPACE_DIR
                })
    return jsonify({"projects": projects, "current": os.path.basename(WORKSPACE_DIR)})

@app.route('/projects/create', methods=['POST'])
def create_project():
    """Crée un nouveau dossier projet."""
    global WORKSPACE_DIR
    data = request.json or {}
    name = data.get('name', '').strip()
    
    if not name:
        return jsonify({"success": False, "error": "Nom de projet requis"})
    
    # Sanitizer le nom
    name = "".join(c for c in name if c.isalnum() or c in (' ', '-', '_')).strip()
    name = name.replace(' ', '_')
    
    if not name:
        return jsonify({"success": False, "error": "Nom de projet invalide"})
    
    project_path = os.path.join(Config.PROJECTS_ROOT, name)
    
    if os.path.exists(project_path):
        return jsonify({"success": False, "error": f"Le projet '{name}' existe déjà"})
    
    try:
        os.makedirs(project_path)
        if SystemHealth.git_available:
            subprocess.run(["powershell", "-Command", "git init"], cwd=project_path, capture_output=True)
        WORKSPACE_DIR = project_path
        orchestrator.reset()
        logger.info(f"📁 Nouveau projet créé: {name}")
        return jsonify({"success": True, "message": f"Projet '{name}' créé", "path": project_path})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/projects/select', methods=['POST'])
def select_project():
    """Sélectionne un projet existant."""
    global WORKSPACE_DIR
    data = request.json or {}
    name = data.get('name', '')
    
    project_path = os.path.join(Config.PROJECTS_ROOT, name)
    
    if not os.path.exists(project_path):
        return jsonify({"success": False, "error": f"Projet '{name}' introuvable"})
    
    WORKSPACE_DIR = project_path
    orchestrator.reset()
    # Charger la mémoire du projet sélectionné
    memory_manager.load(orchestrator)
    logger.info(f"📂 Projet sélectionné: {name}")
    return jsonify({"success": True, "message": f"Projet '{name}' sélectionné", "path": project_path})

@app.route('/projects/current')
def current_project():
    """Retourne les infos du projet courant."""
    return jsonify({
        "name": os.path.basename(WORKSPACE_DIR),
        "path": WORKSPACE_DIR
    })

# ═══════════════════════════════════════════════════════════════════════════════
# POINT D'ENTRÉE
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    print("\n" + "=" * 60)
    print("  🛸 ORBIT - Development Studio v2.0")
    print("  -> http://127.0.0.1:5000")
    print("  Agents: BOSS | CODER | REVIEWER")
    print("-" * 60)
    print(f"  📁 Projets: {Config.PROJECTS_ROOT}")
    print(f"  🤖 Modèle: {Config.DEFAULT_MODEL}")
    print(f"  🔧 Git: {'✓' if SystemHealth.git_available else '✗'}")
    print(f"  🐙 GitHub CLI: {'✓' if SystemHealth.gh_available else '✗'}")
    print("=" * 60 + "\n")
    
    app.run(debug=True, port=5000, threaded=True)