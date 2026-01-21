"""
ORBIT - Multi-Agent Development Studio
Architecture: BOSS (Planning) → CODER (Execution) → REVIEWER (Validation)

Version: 2.1 - Production Ready + Token Optimized
Améliorations:
- Configuration centralisée via .env
- Persistance de la mémoire (orbit_memory.json)
- Vérification des dépendances (git, gh) au démarrage
- Sécurisation des commandes (liste noire)
- Auto-création de repo GitHub pour nouveaux projets
- Optimisation des tokens (Context Compression)
"""

import os
import sys
import json
import shutil
import subprocess
import logging
import hashlib
from datetime import datetime
from typing import Optional, Dict, List, Any, Generator

from flask import Flask, render_template, request, jsonify, send_from_directory, Response
from anthropic import Anthropic
from dotenv import load_dotenv

# ═══════════════════════════════════════════════════════════════════════════════
# INITIALISATION ET CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger("ORBIT")

DEFAULT_PROJECTS_ROOT = os.path.join(os.path.expanduser("~"), "Orbit_Projects")

class Config:
    """Configuration centralisée."""
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    DEFAULT_MODEL: str = os.getenv("ORBIT_MODEL", "claude-sonnet-4-5-20250929")
    OPUS_MODEL: str = os.getenv("ORBIT_OPUS_MODEL", "claude-opus-4-20250514")
    PROJECTS_ROOT: str = os.getenv("PROJECTS_ROOT", DEFAULT_PROJECTS_ROOT)
    MEMORY_FILE: str = os.getenv("ORBIT_MEMORY_FILE", "orbit_memory.json")
    MAX_TOKENS: int = int(os.getenv("ORBIT_MAX_TOKENS", "4096"))  # Réduit pour optimisation
    COMMAND_TIMEOUT: int = int(os.getenv("ORBIT_COMMAND_TIMEOUT", "60"))
    # Auto-création GitHub repo
    AUTO_CREATE_GITHUB: bool = os.getenv("ORBIT_AUTO_GITHUB", "true").lower() == "true"
    
    @classmethod
    def validate(cls) -> bool:
        if not cls.ANTHROPIC_API_KEY:
            logger.error("❌ ANTHROPIC_API_KEY manquante")
            return False
        return True

if not Config.validate():
    logger.error("Configuration invalide. Vérifiez .env")

if not os.path.exists(Config.PROJECTS_ROOT):
    os.makedirs(Config.PROJECTS_ROOT, exist_ok=True)
    logger.info(f"📁 Dossier projets créé: {Config.PROJECTS_ROOT}")

# ═══════════════════════════════════════════════════════════════════════════════
# VÉRIFICATION DES DÉPENDANCES (silencieuse - pas d'erreur si non utilisé)
# ═══════════════════════════════════════════════════════════════════════════════

class SystemHealth:
    """Vérifie la disponibilité des outils système."""
    git_available: bool = False
    gh_available: bool = False
    
    @classmethod
    def check_all(cls) -> None:
        cls.git_available = shutil.which("git") is not None
        cls.gh_available = shutil.which("gh") is not None
        logger.info(f"🔧 Git: {'✓' if cls.git_available else '✗'} | GitHub CLI: {'✓' if cls.gh_available else '✗'}")
    
    @classmethod
    def require_git(cls) -> Optional[Dict]:
        if not cls.git_available:
            return {"success": False, "error": "Git non installé"}
        return None
    
    @classmethod
    def require_gh(cls) -> Optional[Dict]:
        if not cls.gh_available:
            return {"success": False, "error": "GitHub CLI non installé. Installez: winget install GitHub.cli"}
        return None

SystemHealth.check_all()

# ═══════════════════════════════════════════════════════════════════════════════
# SCANNER DE CONTEXTE PROJET (Auto-compréhension du code)
# ═══════════════════════════════════════════════════════════════════════════════

class ProjectContextScanner:
    """Scanne un projet et génère un résumé de contexte automatique."""
    
    # Fichiers clés à lire pour comprendre le projet
    KEY_FILES = ['README.md', 'readme.md', 'package.json', 'requirements.txt', 
                 'index.html', 'app.py', 'main.py', 'server.js', 'index.js']
    
    # Extensions de code à analyser
    CODE_EXTENSIONS = {'.py', '.js', '.ts', '.html', '.css', '.jsx', '.tsx', '.vue'}
    
    @classmethod
    def scan_project(cls, project_path: str) -> str:
        """Scanne le projet et retourne un résumé de contexte."""
        if not os.path.exists(project_path):
            return ""
        
        context_parts = []
        
        # 1. Nom du projet
        project_name = os.path.basename(project_path)
        context_parts.append(f"📂 PROJET: {project_name}")
        
        # 2. Liste des fichiers (compacte)
        files = cls._get_file_tree(project_path)
        if files:
            context_parts.append(f"📁 FICHIERS: {files}")
        
        # 3. Technologies détectées
        tech = cls._detect_technologies(project_path)
        if tech:
            context_parts.append(f"🔧 TECH: {', '.join(tech)}")
        
        # 4. Lecture du README (s'il existe)
        readme = cls._read_readme(project_path)
        if readme:
            context_parts.append(f"📖 README:\n{readme}")
        
        # 5. Structure principale du code
        structure = cls._analyze_main_files(project_path)
        if structure:
            context_parts.append(f"💻 CODE:\n{structure}")
        
        return "\n\n".join(context_parts)
    
    @classmethod
    def _get_file_tree(cls, path: str, max_files: int = 25) -> str:
        """Liste compacte des fichiers."""
        try:
            items = []
            for root, dirs, files in os.walk(path):
                # Ignorer certains dossiers
                dirs[:] = [d for d in dirs if d not in ['.git', '__pycache__', 'venv', 'node_modules', '.venv']]
                rel_root = os.path.relpath(root, path)
                for f in files:
                    if not f.startswith('.'):
                        if rel_root == '.':
                            items.append(f)
                        else:
                            items.append(f"{rel_root}/{f}")
                        if len(items) >= max_files:
                            break
                if len(items) >= max_files:
                    break
            return " | ".join(items[:max_files])
        except:
            return ""
    
    @classmethod
    def _detect_technologies(cls, path: str) -> List[str]:
        """Détecte les technologies utilisées."""
        tech = []
        files = os.listdir(path)
        
        if 'package.json' in files:
            tech.append('Node.js')
        if 'requirements.txt' in files or any(f.endswith('.py') for f in files):
            tech.append('Python')
        if any(f.endswith('.html') for f in files):
            tech.append('HTML')
        if any(f.endswith('.ts') in files for f in files):
            tech.append('TypeScript')
        if 'Dockerfile' in files:
            tech.append('Docker')
        if '.git' in os.listdir(path):
            tech.append('Git')
        
        return tech[:5]  # Max 5
    
    @classmethod
    def _read_readme(cls, path: str) -> str:
        """Lit le README et retourne un résumé."""
        for readme_name in ['README.md', 'readme.md', 'README.txt']:
            readme_path = os.path.join(path, readme_name)
            if os.path.exists(readme_path):
                try:
                    with open(readme_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    # Garder les 500 premiers caractères
                    return content[:500] + ('...' if len(content) > 500 else '')
                except:
                    pass
        return ""
    
    @classmethod
    def _analyze_main_files(cls, path: str) -> str:
        """Analyse les fichiers principaux du projet."""
        summaries = []
        
        for filename in cls.KEY_FILES:
            filepath = os.path.join(path, filename)
            if os.path.exists(filepath):
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        content = f.read()
                    # Extraire les premières lignes (imports, structure)
                    lines = content.split('\n')[:15]
                    summary = '\n'.join(lines)
                    if len(summary) > 300:
                        summary = summary[:300] + '...'
                    summaries.append(f"[{filename}]\n{summary}")
                except:
                    pass
        
        return "\n\n".join(summaries[:3])  # Max 3 fichiers

# ═══════════════════════════════════════════════════════════════════════════════
# SÉCURITÉ
# ═══════════════════════════════════════════════════════════════════════════════

DANGEROUS_PATTERNS = [
    "rm -rf /", "rm -rf /*", "del /s /q c:\\", "format c:",
    "rd /s /q c:\\", "remove-item -recurse -force c:\\",
    "shutdown", "restart-computer", "stop-computer",
    "reg delete", "remove-itemproperty",
    "iex(", "invoke-expression", "downloadstring",
]

def is_command_safe(command: str) -> tuple[bool, str]:
    cmd_lower = command.lower().strip()
    for pattern in DANGEROUS_PATTERNS:
        if pattern.lower() in cmd_lower:
            return False, f"Commande bloquée: {pattern}"
    return True, ""

# ═══════════════════════════════════════════════════════════════════════════════
# APPLICATION FLASK
# ═══════════════════════════════════════════════════════════════════════════════

app = Flask(__name__)

try:
    client = Anthropic(api_key=Config.ANTHROPIC_API_KEY)
except Exception as e:
    logger.error(f"❌ Erreur Anthropic: {e}")
    client = None

WORKSPACE_DIR = os.getcwd()

CONFIG = {
    "models": {
        "boss": Config.DEFAULT_MODEL,
        "coder": Config.DEFAULT_MODEL,
        "reviewer": Config.DEFAULT_MODEL
    },
    "autopilot": True,
    "max_iterations": 15
}

USAGE_STATS = {"total_input_tokens": 0, "total_output_tokens": 0, "calls": []}

# ═══════════════════════════════════════════════════════════════════════════════
# OPTIMISATION TOKENS - Context Compression (comme mgrep)
# ═══════════════════════════════════════════════════════════════════════════════

class TokenOptimizer:
    """Optimise l'utilisation des tokens via compression du contexte."""
    
    # Limite de tokens par conversation avant compression
    MAX_CONTEXT_MESSAGES = 6
    
    @staticmethod
    def compress_message(text: str, max_length: int = 500) -> str:
        """Compresse un message en gardant l'essentiel."""
        if len(text) <= max_length:
            return text
        # Garder le début et la fin
        half = max_length // 2
        return text[:half] + "\n[...contenu tronqué...]\n" + text[-half:]
    
    @staticmethod
    def compress_conversation(messages: List[Dict], keep_last: int = 4) -> List[Dict]:
        """Compresse l'historique en gardant les N derniers messages complets."""
        if len(messages) <= keep_last:
            return messages
        
        # Résumer les anciens messages
        old_messages = messages[:-keep_last]
        recent_messages = messages[-keep_last:]
        
        # Créer un résumé des anciens échanges
        summary_parts = []
        for msg in old_messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                summary_parts.append(content[:100])
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        summary_parts.append(block.get("text", "")[:100])
        
        summary = "[CONTEXTE PRÉCÉDENT RÉSUMÉ]\n" + "\n".join(summary_parts[:3])
        
        compressed = [{"role": "user", "content": summary}]
        compressed.extend(recent_messages)
        return compressed
    
    @staticmethod
    def compress_tool_result(result: Dict) -> Dict:
        """Compresse les résultats d'outils pour économiser des tokens."""
        compressed = {}
        for key, value in result.items():
            if isinstance(value, str) and len(value) > 300:
                compressed[key] = value[:150] + "..." + value[-100:]
            else:
                compressed[key] = value
        return compressed
    
    @staticmethod
    def get_compact_file_list(path: str) -> str:
        """Retourne une liste compacte des fichiers (moins de tokens)."""
        try:
            items = []
            for item in os.listdir(path)[:20]:  # Max 20 items
                if not item.startswith('.') and item not in ['__pycache__', 'venv', 'node_modules']:
                    full = os.path.join(path, item)
                    marker = "📁" if os.path.isdir(full) else "📄"
                    items.append(f"{marker}{item}")
            return " | ".join(items)
        except:
            return ""

# ═══════════════════════════════════════════════════════════════════════════════
# PERSISTENCE MÉMOIRE
# ═══════════════════════════════════════════════════════════════════════════════

class MemoryManager:
    """Gère la persistance des conversations."""
    
    def __init__(self):
        self.memory_file = Config.MEMORY_FILE
    
    def _get_path(self) -> str:
        return os.path.join(WORKSPACE_DIR, self.memory_file)
    
    def save(self, orchestrator: 'AgentOrchestrator') -> bool:
        try:
            # Compresser avant sauvegarde
            data = {
                "saved_at": datetime.now().isoformat(),
                "workspace": WORKSPACE_DIR,
                "boss": TokenOptimizer.compress_conversation(orchestrator.conversation_boss),
                "coder": TokenOptimizer.compress_conversation(orchestrator.conversation_coder),
                "reviewer": TokenOptimizer.compress_conversation(orchestrator.conversation_reviewer),
                "files": orchestrator.created_files[-10:],  # Garder les 10 derniers
                "usage": USAGE_STATS
            }
            with open(self._get_path(), "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2, default=str)
            return True
        except Exception as e:
            logger.error(f"❌ Sauvegarde mémoire: {e}")
            return False
    
    def load(self, orchestrator: 'AgentOrchestrator') -> bool:
        try:
            path = self._get_path()
            if not os.path.exists(path):
                return False
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            # Valider et nettoyer les conversations avant de les charger
            def is_valid_conversation(conv):
                """Vérifie si une conversation est valide pour l'API."""
                if not isinstance(conv, list):
                    return False
                for msg in conv:
                    if not isinstance(msg, dict):
                        return False
                    if "role" not in msg or "content" not in msg:
                        return False
                    content = msg.get("content")
                    # Rejeter si le contenu est une string qui ressemble à du Python repr
                    if isinstance(content, str) and ("TextBlock(" in content or "ToolUseBlock(" in content):
                        return False
                    # Rejeter si le contenu est une liste avec des strings au lieu de dicts
                    if isinstance(content, list):
                        for item in content:
                            if isinstance(item, str) and ("TextBlock(" in item or "ToolUseBlock(" in item):
                                return False
                return True
            
            # Ne charger que les conversations valides
            boss = data.get("boss", [])
            coder = data.get("coder", [])
            reviewer = data.get("reviewer", [])
            
            if is_valid_conversation(boss):
                orchestrator.conversation_boss = boss
            if is_valid_conversation(coder):
                orchestrator.conversation_coder = coder
            if is_valid_conversation(reviewer):
                orchestrator.conversation_reviewer = reviewer
            
            orchestrator.created_files = data.get("files", [])
            logger.info(f"🧠 Mémoire chargée")
            return True
        except Exception as e:
            logger.warning(f"⚠️ Mémoire non chargée: {e}")
            return False
    
    def clear(self) -> bool:
        try:
            path = self._get_path()
            if os.path.exists(path):
                os.remove(path)
            return True
        except:
            return False

memory_manager = MemoryManager()

# ═══════════════════════════════════════════════════════════════════════════════
# OUTILS AGENTS (optimisés)
# ═══════════════════════════════════════════════════════════════════════════════

TOOLS = [
    {
        "name": "read_file",
        "description": "Lit un fichier. Retourne contenu (max 3000 chars).",
        "input_schema": {
            "type": "object",
            "properties": {"filename": {"type": "string", "description": "Chemin"}},
            "required": ["filename"]
        }
    },
    {
        "name": "write_file",
        "description": "Crée/modifie un fichier.",
        "input_schema": {
            "type": "object",
            "properties": {
                "filename": {"type": "string"},
                "content": {"type": "string"}
            },
            "required": ["filename", "content"]
        }
    },
    {
        "name": "run_command",
        "description": "Execute PowerShell. Timeout 60s.",
        "input_schema": {
            "type": "object",
            "properties": {"command": {"type": "string"}},
            "required": ["command"]
        }
    },
    {
        "name": "list_files",
        "description": "Liste fichiers d'un dossier.",
        "input_schema": {
            "type": "object",
            "properties": {"directory": {"type": "string", "description": ". pour racine"}},
            "required": ["directory"]
        }
    },
    {
        "name": "git_commit",
        "description": "Commit Git.",
        "input_schema": {
            "type": "object",
            "properties": {"message": {"type": "string"}},
            "required": ["message"]
        }
    }
]

def execute_tool(name: str, args: dict) -> dict:
    """Exécute un outil avec résultats compressés."""
    global WORKSPACE_DIR
    
    try:
        if name == "read_file":
            path = os.path.join(WORKSPACE_DIR, args["filename"])
            if not os.path.exists(path):
                return {"success": False, "error": f"Fichier non trouvé: {args['filename']}"}
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            # Compression du contenu
            return {"success": True, "content": content[:3000], "size": len(content)}

        elif name == "write_file":
            path = os.path.join(WORKSPACE_DIR, args["filename"])
            parent = os.path.dirname(path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(args["content"])
            return {"success": True, "msg": f"✓ {args['filename']}"}

        elif name == "run_command":
            is_safe, reason = is_command_safe(args["command"])
            if not is_safe:
                return {"success": False, "error": reason}
            
            result = subprocess.run(
                ["powershell", "-Command", args["command"]],
                capture_output=True, text=True, cwd=WORKSPACE_DIR,
                timeout=Config.COMMAND_TIMEOUT
            )
            # Compression de la sortie
            stdout = result.stdout.strip()[:500] if result.stdout else ""
            stderr = result.stderr.strip()[:200] if result.stderr else ""
            return {"success": result.returncode == 0, "out": stdout, "err": stderr}

        elif name == "list_files":
            path = os.path.join(WORKSPACE_DIR, args.get("directory", "."))
            if not os.path.exists(path):
                return {"success": False, "error": "Dossier non trouvé"}
            # Format compact
            items = TokenOptimizer.get_compact_file_list(path)
            return {"success": True, "files": items}

        elif name == "git_commit":
            if not SystemHealth.git_available:
                return {"success": False, "error": "Git non disponible"}
            subprocess.run(["powershell", "-Command", "git add -A"], cwd=WORKSPACE_DIR, capture_output=True)
            result = subprocess.run(
                ["powershell", "-Command", f'git commit -m "{args["message"]}"'],
                capture_output=True, text=True, cwd=WORKSPACE_DIR
            )
            if result.returncode == 0 or "nothing to commit" in (result.stdout + result.stderr).lower():
                return {"success": True, "msg": "Commit OK"}
            return {"success": False, "error": result.stderr[:100]}

        return {"success": False, "error": f"Outil inconnu: {name}"}

    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Timeout"}
    except Exception as e:
        return {"success": False, "error": str(e)[:100]}

# ═══════════════════════════════════════════════════════════════════════════════
# PROMPTS SYSTÈME (optimisés - moins de tokens)
# ═══════════════════════════════════════════════════════════════════════════════

BOSS_PROMPT = """Tu es le BOSS. Analyse les demandes et crée un plan.

FORMAT:
[ANALYSE] Ce que l'utilisateur veut
[PLAN] Étapes numérotées
[INSTRUCTION_CODER] Instructions pour le CODER

RÈGLES: Sois concis. Délègue au CODER. Pas de signature/crédit."""

CODER_PROMPT = """Tu es le CODER sur Windows.

OUTILS: write_file, read_file, run_command, list_files

RÈGLES:
- Sépare HTML/CSS/JS en fichiers distincts
- PowerShell: 'dir' pas 'ls'
- Dark mode par défaut
- Pas de signature/crédit

FORMAT: [ACTION] [EXECUTION] [RESULTAT]"""

REVIEWER_PROMPT = """Tu es le REVIEWER. Vérifie le code.

FORMAT:
[REVIEW] Fichiers vérifiés
[CHECKLIST] Points ✓ ou ✗
[VERDICT] APPROUVE ou CORRECTIONS_REQUISES"""

# ═══════════════════════════════════════════════════════════════════════════════
# ORCHESTRATEUR (optimisé)
# ═══════════════════════════════════════════════════════════════════════════════

class AgentOrchestrator:
    def __init__(self):
        self.conversation_boss: List[Dict] = []
        self.conversation_coder: List[Dict] = []
        self.conversation_reviewer: List[Dict] = []
        self.created_files: List[str] = []
        self.current_agent: str = "boss"
        
    def reset(self) -> None:
        self.conversation_boss = []
        self.conversation_coder = []
        self.conversation_reviewer = []
        self.created_files = []
    
    def track_usage(self, response, agent: str) -> None:
        if hasattr(response, 'usage'):
            USAGE_STATS["total_input_tokens"] += response.usage.input_tokens
            USAGE_STATS["total_output_tokens"] += response.usage.output_tokens
            USAGE_STATS["calls"].append({
                "agent": agent,
                "in": response.usage.input_tokens,
                "out": response.usage.output_tokens
            })
    
    def call_agent(self, agent: str, messages: list, system_prompt: str):
        if not client:
            raise RuntimeError("Client Anthropic non initialisé")
        
        # Compression du contexte avant appel
        compressed_messages = TokenOptimizer.compress_conversation(messages)
        
        model = CONFIG["models"].get(agent, CONFIG["models"]["coder"])
        
        # Retry automatique pour erreurs réseau (3 tentatives)
        import time
        max_retries = 3
        last_error = None
        
        for attempt in range(max_retries):
            try:
                response = client.messages.create(
                    model=model,
                    max_tokens=Config.MAX_TOKENS,
                    system=system_prompt,
                    messages=compressed_messages,
                    tools=TOOLS
                )
                self.track_usage(response, agent)
                return response
            except Exception as e:
                last_error = e
                error_msg = str(e).lower()
                # Retry seulement pour erreurs réseau/temporaires
                if any(x in error_msg for x in ["network", "timeout", "connection", "overloaded", "529", "500", "502", "503"]):
                    wait_time = (attempt + 1) * 2  # 2s, 4s, 6s
                    logger.warning(f"⚠️ Erreur réseau {agent} (tentative {attempt+1}/{max_retries}), retry dans {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    # Erreur non-réseau, ne pas retry
                    raise e
        
        # Toutes les tentatives échouées
        raise RuntimeError(f"Échec après {max_retries} tentatives: {last_error}")
    
    def process_tool_calls(self, response, conversation: list) -> List[Dict]:
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
                # Compression du résultat
                compressed_result = TokenOptimizer.compress_tool_result(result)
                results.append({
                    "tool": block.name,
                    "result": compressed_result,
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
                    # JSON compact
                    tool_results_content.append({
                        "type": "tool_result",
                        "tool_use_id": tr["id"],
                        "content": json.dumps(tr["result"], ensure_ascii=False, separators=(',', ':'))
                    })
                conversation.append({"role": "user", "content": tool_results_content})
            else:
                break
        
        yield {"type": "agent_complete", "agent": agent}

    def orchestrate(self, user_message: str) -> Generator:
        logger.info(f"🚀 Demande: {user_message[:40]}...")
        
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
        
        self.conversation_coder = [{"role": "user", "content": f"BOSS:\n{coder_instructions}"}]
        
        for event in self.run_agent_loop("coder", coder_instructions, CODER_PROMPT, self.conversation_coder, max_turns=6):
            yield event
        
        yield {"type": "phase", "phase": "REVIEWER", "status": "Reviewing"}
        
        files_str = ", ".join(self.created_files[-5:]) if self.created_files else "fichiers"
        self.conversation_reviewer = [{"role": "user", "content": f"Vérifie: {files_str}"}]
        
        for event in self.run_agent_loop("reviewer", "", REVIEWER_PROMPT, self.conversation_reviewer, max_turns=2):
            yield event
        
        if SystemHealth.git_available and CONFIG["autopilot"]:
            yield {"type": "phase", "phase": "GIT", "status": "Commit"}
            result = execute_tool("git_commit", {"message": f"feat: {user_message[:40]}"})
            yield {"type": "tool_result", "agent": "boss", "tool": "git_commit", 
                   "success": result.get("success", False), "result": result}
        
        memory_manager.save(self)
        
        html_files = [f for f in self.created_files if f.endswith('.html')]
        yield {"type": "complete", "files": self.created_files, "preview": html_files[0] if html_files else None}

orchestrator = AgentOrchestrator()
memory_manager.load(orchestrator)

# ═══════════════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

def generate_commit_message() -> Optional[str]:
    if not SystemHealth.git_available:
        return None
    result = subprocess.run(
        ["powershell", "-Command", "git status --porcelain"],
        capture_output=True, text=True, cwd=WORKSPACE_DIR
    )
    if result.returncode != 0 or not result.stdout.strip():
        return None
    lines = result.stdout.strip().split('\n')
    if len(lines) == 0:
        return None
    return f"chore: update {len(lines)} files"

def generate_readme_content() -> str:
    project_name = os.path.basename(WORKSPACE_DIR)
    files = [f for f in os.listdir(WORKSPACE_DIR) 
             if not f.startswith('.') and f not in ['__pycache__', 'venv', 'node_modules']]
    return f"# {project_name}\n\n## Files\n" + "\n".join([f"- {f}" for f in sorted(files)[:10]])

def create_github_repo(name: str, private: bool = True) -> Dict:
    """Crée un repo GitHub et retourne le résultat."""
    if not SystemHealth.gh_available:
        return {"success": False, "error": "GitHub CLI non installé"}
    if not SystemHealth.git_available:
        return {"success": False, "error": "Git non installé"}
    
    visibility = "--private" if private else "--public"
    
    # Vérifier si remote existe
    check = subprocess.run(
        ["powershell", "-Command", "git remote get-url origin"],
        capture_output=True, text=True, cwd=WORKSPACE_DIR
    )
    if check.returncode == 0 and check.stdout.strip():
        return {"success": False, "error": f"Remote existe: {check.stdout.strip()[:50]}"}
    
    # Init git
    subprocess.run(["powershell", "-Command", "git init"], cwd=WORKSPACE_DIR, capture_output=True)
    
    # Créer repo
    result = subprocess.run(
        ["powershell", "-Command", f'gh repo create {name} {visibility} --source=. --remote=origin'],
        capture_output=True, text=True, cwd=WORKSPACE_DIR
    )
    
    if result.returncode != 0:
        return {"success": False, "error": result.stderr.strip()[:100] or result.stdout.strip()[:100]}
    
    # Initial commit + push
    subprocess.run(["powershell", "-Command", "git add -A"], cwd=WORKSPACE_DIR, capture_output=True)
    subprocess.run(["powershell", "-Command", 'git commit -m "Initial commit"'], cwd=WORKSPACE_DIR, capture_output=True)
    subprocess.run(["powershell", "-Command", "git push -u origin main"], cwd=WORKSPACE_DIR, capture_output=True)
    subprocess.run(["powershell", "-Command", "git push -u origin master"], cwd=WORKSPACE_DIR, capture_output=True)
    
    return {"success": True, "message": f"Repo créé: {name}", "url": result.stdout.strip()}

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
            model = Config.OPUS_MODEL if data['model'] == 'opus' else Config.DEFAULT_MODEL
            CONFIG['models']['boss'] = model
        return jsonify({"success": True, "config": CONFIG})
    return jsonify(CONFIG)

@app.route('/usage')
def usage():
    return jsonify(USAGE_STATS)

@app.route('/files')
def list_workspace_files():
    files = []
    for item in os.listdir(WORKSPACE_DIR):
        if not item.startswith('.') and item not in ['__pycache__', 'templates', 'venv']:
            path = os.path.join(WORKSPACE_DIR, item)
            if os.path.isfile(path):
                files.append({"name": item, "size": os.path.getsize(path)})
    return jsonify(files)

@app.route('/health')
def health():
    return jsonify({
        "status": "ok",
        "git": SystemHealth.git_available,
        "gh": SystemHealth.gh_available,
        "workspace": WORKSPACE_DIR,
        "model": Config.DEFAULT_MODEL
    })

# ═══════════════════════════════════════════════════════════════════════════════
# ROUTES GIT
# ═══════════════════════════════════════════════════════════════════════════════

@app.route('/git/status')
def git_status_route():
    if not SystemHealth.git_available:
        return jsonify({"success": False, "status": "Git non installé"})
    result = subprocess.run(
        ["powershell", "-Command", "git status --short"],
        capture_output=True, text=True, cwd=WORKSPACE_DIR
    )
    return jsonify({
        "success": result.returncode == 0,
        "status": result.stdout.strip() if result.stdout else "Clean"
    })

@app.route('/git/diff')
def git_diff_route():
    if not SystemHealth.git_available:
        return jsonify({"success": False, "diff": "Git non installé"})
    result = subprocess.run(
        ["powershell", "-Command", "git diff --stat"],
        capture_output=True, text=True, cwd=WORKSPACE_DIR
    )
    return jsonify({"success": True, "diff": result.stdout.strip()[:500] or "Aucun changement"})

@app.route('/git/commit', methods=['POST'])
def git_commit_route():
    if not SystemHealth.git_available:
        return jsonify({"success": False, "error": "Git non installé"})
    
    data = request.json or {}
    message = data.get('message', '').strip() or generate_commit_message()
    if not message:
        return jsonify({"success": False, "error": "Rien à commiter"})
    
    subprocess.run(["powershell", "-Command", "git add -A"], cwd=WORKSPACE_DIR, capture_output=True)
    result = subprocess.run(
        ["powershell", "-Command", f'git commit -m "{message}"'],
        capture_output=True, text=True, cwd=WORKSPACE_DIR
    )
    
    if result.returncode == 0 or "nothing to commit" in (result.stdout + result.stderr).lower():
        return jsonify({"success": True, "message": message})
    return jsonify({"success": False, "error": result.stderr[:100]})

@app.route('/git/push', methods=['POST'])
def git_push_route():
    if not SystemHealth.git_available:
        return jsonify({"success": False, "error": "Git non installé"})
    result = subprocess.run(
        ["powershell", "-Command", "git push"],
        capture_output=True, text=True, cwd=WORKSPACE_DIR
    )
    return jsonify({"success": result.returncode == 0, "output": result.stdout.strip() or result.stderr.strip()})

@app.route('/git/pull', methods=['POST'])
def git_pull_route():
    if not SystemHealth.git_available:
        return jsonify({"success": False, "error": "Git non installé"})
    result = subprocess.run(
        ["powershell", "-Command", "git pull"],
        capture_output=True, text=True, cwd=WORKSPACE_DIR
    )
    return jsonify({"success": result.returncode == 0, "output": result.stdout.strip() or result.stderr.strip()})

@app.route('/git/log')
def git_log_route():
    if not SystemHealth.git_available:
        return jsonify({"success": False, "log": "Git non installé"})
    result = subprocess.run(
        ["powershell", "-Command", "git log --oneline -5"],
        capture_output=True, text=True, cwd=WORKSPACE_DIR
    )
    return jsonify({"success": result.returncode == 0, "log": result.stdout.strip() or "Aucun commit"})

@app.route('/readme/generate', methods=['POST'])
def readme_generate():
    content = generate_readme_content()
    path = os.path.join(WORKSPACE_DIR, "README.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return jsonify({"success": True, "message": "README.md généré"})

# ═══════════════════════════════════════════════════════════════════════════════
# ROUTES GITHUB
# ═══════════════════════════════════════════════════════════════════════════════

@app.route('/github/create', methods=['POST'])
def github_create():
    if not SystemHealth.gh_available:
        return jsonify({"success": False, "error": "GitHub CLI non installé. Installez: winget install GitHub.cli"})
    
    data = request.json or {}
    repo_name = data.get('name', os.path.basename(WORKSPACE_DIR))
    private = data.get('private', True)
    
    result = create_github_repo(repo_name, private)
    return jsonify(result)

@app.route('/github/status')
def github_status():
    if not SystemHealth.gh_available:
        return jsonify({"authenticated": False, "output": "GitHub CLI non installé"})
    
    result = subprocess.run(
        ["powershell", "-Command", "gh auth status"],
        capture_output=True, text=True, cwd=WORKSPACE_DIR
    )
    return jsonify({"authenticated": result.returncode == 0, "output": result.stdout.strip() or result.stderr.strip()})

# ═══════════════════════════════════════════════════════════════════════════════
# GESTION DES PROJETS
# ═══════════════════════════════════════════════════════════════════════════════

@app.route('/projects')
def list_projects():
    """Liste projets disponibles."""
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
    """Crée un nouveau projet avec dossier + optionnellement repo GitHub."""
    global WORKSPACE_DIR
    data = request.json or {}
    name = data.get('name', '').strip()
    auto_github = data.get('auto_github', Config.AUTO_CREATE_GITHUB)
    private = data.get('private', True)
    
    if not name:
        return jsonify({"success": False, "error": "Nom de projet requis"})
    
    # Sanitize
    name = "".join(c for c in name if c.isalnum() or c in (' ', '-', '_')).strip()
    name = name.replace(' ', '_')
    
    if not name:
        return jsonify({"success": False, "error": "Nom invalide"})
    
    project_path = os.path.join(Config.PROJECTS_ROOT, name)
    
    if os.path.exists(project_path):
        return jsonify({"success": False, "error": f"'{name}' existe déjà"})
    
    try:
        # 1. Créer le dossier
        os.makedirs(project_path)
        logger.info(f"📁 Dossier créé: {project_path}")
        
        # 2. Changer le workspace
        WORKSPACE_DIR = project_path
        
        # 3. Init Git si disponible
        git_ok = False
        if SystemHealth.git_available:
            subprocess.run(["powershell", "-Command", "git init"], cwd=project_path, capture_output=True)
            git_ok = True
            logger.info(f"  ✓ Git initialisé")
        
        # 4. Créer README basique
        readme_path = os.path.join(project_path, "README.md")
        with open(readme_path, "w", encoding="utf-8") as f:
            f.write(f"# {name}\n\nProjet créé avec ORBIT.\n")
        
        # 5. Auto-création repo GitHub si demandé et gh disponible
        github_result = None
        if auto_github and SystemHealth.gh_available and git_ok:
            github_result = create_github_repo(name, private)
            if github_result.get("success"):
                logger.info(f"  ✓ Repo GitHub créé: {name}")
            else:
                logger.warning(f"  ⚠ GitHub: {github_result.get('error', 'erreur')}")
        
        # 6. Reset orchestrator
        orchestrator.reset()
        
        response = {
            "success": True,
            "message": f"Projet '{name}' créé",
            "path": project_path,
            "git_initialized": git_ok
        }
        
        if github_result:
            response["github"] = github_result
        
        return jsonify(response)
        
    except Exception as e:
        logger.error(f"❌ Création projet: {e}")
        return jsonify({"success": False, "error": str(e)})

@app.route('/projects/select', methods=['POST'])
def select_project():
    """Sélectionne un projet existant et charge son contexte automatiquement."""
    global WORKSPACE_DIR
    data = request.json or {}
    name = data.get('name', '')
    
    project_path = os.path.join(Config.PROJECTS_ROOT, name)
    
    if not os.path.exists(project_path):
        return jsonify({"success": False, "error": f"'{name}' introuvable"})
    
    WORKSPACE_DIR = project_path
    orchestrator.reset()
    
    # Charger la mémoire existante si disponible
    memory_loaded = memory_manager.load(orchestrator)
    
    # Scanner le projet et injecter le contexte si pas de mémoire
    if not memory_loaded or len(orchestrator.conversation_boss) == 0:
        context = ProjectContextScanner.scan_project(project_path)
        if context:
            # Injecter le contexte comme premier message système
            context_message = f"[CONTEXTE PROJET AUTO-DÉTECTÉ]\n{context}"
            orchestrator.conversation_boss = [{"role": "user", "content": context_message}]
            logger.info(f"🔍 Contexte projet scanné et chargé")
    
    logger.info(f"📂 Projet sélectionné: {name}")
    return jsonify({"success": True, "message": f"'{name}' sélectionné", "path": project_path, "context_loaded": True})

@app.route('/projects/current')
def current_project():
    return jsonify({"name": os.path.basename(WORKSPACE_DIR), "path": WORKSPACE_DIR})

# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    print("\n" + "=" * 50)
    print("  🛸 ORBIT v2.1 - Token Optimized")
    print("  -> http://127.0.0.1:5000")
    print("-" * 50)
    print(f"  📁 Projets: {Config.PROJECTS_ROOT}")
    print(f"  🤖 Modèle: {Config.DEFAULT_MODEL}")
    print(f"  🔧 Git: {'✓' if SystemHealth.git_available else '✗'}")
    print(f"  🐙 GitHub: {'✓' if SystemHealth.gh_available else '✗ (optionnel)'}")
    print(f"  ⚡ Max tokens: {Config.MAX_TOKENS}")
    print("=" * 50 + "\n")
    
    app.run(debug=True, port=5000, threaded=True)