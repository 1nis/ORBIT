"""
ORBIT v3 - Autonomous Core
Architecture: State Machine avec Intent Classification + Boucle d'Autonomie

Version: 3.0 - Autonomous Development Studio
Fonctionnalites:
- Intent Classification (CHAT/DEV/README)
- Boucle d'Autonomie (The Loop) - Max 5 iterations
- Smart Search (optimisation tokens)
- Background Server pour Live Preview
- Memoire persistante amelioree
"""

import os
import sys
import json
import shutil
import subprocess
import logging
import hashlib
import re
import signal
import threading
from datetime import datetime
from typing import Optional, Dict, List, Any, Generator, Tuple

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
    """Configuration centralisee."""
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    DEFAULT_MODEL: str = os.getenv("ORBIT_MODEL", "claude-sonnet-4-5-20250929")
    OPUS_MODEL: str = os.getenv("ORBIT_OPUS_MODEL", "claude-opus-4-20250514")
    PROJECTS_ROOT: str = os.getenv("PROJECTS_ROOT", DEFAULT_PROJECTS_ROOT)
    MEMORY_FILE: str = os.getenv("ORBIT_MEMORY_FILE", "orbit_memory.json")
    MAX_TOKENS: int = int(os.getenv("ORBIT_MAX_TOKENS", "4096"))
    COMMAND_TIMEOUT: int = int(os.getenv("ORBIT_COMMAND_TIMEOUT", "60"))
    AUTO_CREATE_GITHUB: bool = os.getenv("ORBIT_AUTO_GITHUB", "true").lower() == "true"
    MAX_AUTONOMY_LOOPS: int = int(os.getenv("ORBIT_MAX_LOOPS", "5"))

    @classmethod
    def validate(cls) -> bool:
        if not cls.ANTHROPIC_API_KEY:
            logger.error("ANTHROPIC_API_KEY manquante")
            return False
        return True

if not Config.validate():
    logger.error("Configuration invalide. Verifiez .env")

if not os.path.exists(Config.PROJECTS_ROOT):
    os.makedirs(Config.PROJECTS_ROOT, exist_ok=True)
    logger.info(f"Dossier projets cree: {Config.PROJECTS_ROOT}")

# ═══════════════════════════════════════════════════════════════════════════════
# VERIFICATION DES DEPENDANCES
# ═══════════════════════════════════════════════════════════════════════════════

class SystemHealth:
    """Verifie la disponibilite des outils systeme."""
    git_available: bool = False
    gh_available: bool = False

    @classmethod
    def check_all(cls) -> None:
        cls.git_available = shutil.which("git") is not None
        cls.gh_available = shutil.which("gh") is not None
        logger.info(f"Git: {'OK' if cls.git_available else 'X'} | GitHub CLI: {'OK' if cls.gh_available else 'X'}")

    @classmethod
    def require_git(cls) -> Optional[Dict]:
        if not cls.git_available:
            return {"success": False, "error": "Git non installe"}
        return None

    @classmethod
    def require_gh(cls) -> Optional[Dict]:
        if not cls.gh_available:
            return {"success": False, "error": "GitHub CLI non installe. Installez: winget install GitHub.cli"}
        return None

SystemHealth.check_all()

# ═══════════════════════════════════════════════════════════════════════════════
# SECURITE
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
            return False, f"Commande bloquee: {pattern}"
    return True, ""

# ═══════════════════════════════════════════════════════════════════════════════
# APPLICATION FLASK
# ═══════════════════════════════════════════════════════════════════════════════

app = Flask(__name__)

try:
    client = Anthropic(api_key=Config.ANTHROPIC_API_KEY)
except Exception as e:
    logger.error(f"Erreur Anthropic: {e}")
    client = None

WORKSPACE_DIR = os.getcwd()

CONFIG = {
    "models": {
        "boss": Config.DEFAULT_MODEL,
        "coder": Config.DEFAULT_MODEL,
        "reviewer": Config.DEFAULT_MODEL,
        "classifier": Config.DEFAULT_MODEL
    },
    "autopilot": True,
    "max_iterations": 15
}

USAGE_STATS = {"total_input_tokens": 0, "total_output_tokens": 0, "calls": []}

# ═══════════════════════════════════════════════════════════════════════════════
# GESTIONNAIRE DE SERVEURS EN BACKGROUND (Live Preview)
# ═══════════════════════════════════════════════════════════════════════════════

class BackgroundServerManager:
    """Gere les serveurs en arriere-plan pour le live preview."""

    def __init__(self):
        self.servers: Dict[int, subprocess.Popen] = {}
        self.lock = threading.Lock()

    def start_server(self, command: str, port: int = 3000, cwd: str = None) -> Dict:
        """Lance un serveur en background et retourne le port."""
        with self.lock:
            # Arreter le serveur existant sur ce port
            if port in self.servers:
                self.stop_server(port)

            try:
                # Lancer le processus
                process = subprocess.Popen(
                    ["powershell", "-Command", command],
                    cwd=cwd or WORKSPACE_DIR,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0
                )

                self.servers[port] = process
                logger.info(f"Serveur lance sur port {port}: {command[:50]}...")

                return {
                    "success": True,
                    "port": port,
                    "pid": process.pid,
                    "url": f"http://localhost:{port}"
                }
            except Exception as e:
                return {"success": False, "error": str(e)}

    def stop_server(self, port: int) -> Dict:
        """Arrete un serveur sur un port specifique."""
        with self.lock:
            if port not in self.servers:
                return {"success": False, "error": f"Aucun serveur sur le port {port}"}

            try:
                process = self.servers[port]
                if os.name == 'nt':
                    # Windows: kill process tree
                    subprocess.run(
                        ["taskkill", "/F", "/T", "/PID", str(process.pid)],
                        capture_output=True
                    )
                else:
                    os.killpg(os.getpgid(process.pid), signal.SIGTERM)

                del self.servers[port]
                logger.info(f"Serveur arrete sur port {port}")
                return {"success": True}
            except Exception as e:
                return {"success": False, "error": str(e)}

    def list_servers(self) -> List[Dict]:
        """Liste tous les serveurs actifs."""
        with self.lock:
            return [
                {"port": port, "pid": proc.pid, "running": proc.poll() is None}
                for port, proc in self.servers.items()
            ]

    def stop_all(self):
        """Arrete tous les serveurs."""
        for port in list(self.servers.keys()):
            self.stop_server(port)

server_manager = BackgroundServerManager()

# ═══════════════════════════════════════════════════════════════════════════════
# OPTIMISATION TOKENS - Context Compression + Smart Search
# ═══════════════════════════════════════════════════════════════════════════════

class TokenOptimizer:
    """Optimise l'utilisation des tokens via compression du contexte."""

    MAX_CONTEXT_MESSAGES = 6

    @staticmethod
    def compress_message(text: str, max_length: int = 500) -> str:
        if len(text) <= max_length:
            return text
        half = max_length // 2
        return text[:half] + "\n[...tronque...]\n" + text[-half:]

    @staticmethod
    def compress_conversation(messages: List[Dict], keep_last: int = 4) -> List[Dict]:
        if len(messages) <= keep_last:
            return messages

        old_messages = messages[:-keep_last]
        recent_messages = messages[-keep_last:]

        summary_parts = []
        for msg in old_messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                summary_parts.append(content[:100])
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        summary_parts.append(block.get("text", "")[:100])

        summary = "[CONTEXTE PRECEDENT RESUME]\n" + "\n".join(summary_parts[:3])

        compressed = [{"role": "user", "content": summary}]
        compressed.extend(recent_messages)
        return compressed

    @staticmethod
    def compress_tool_result(result: Dict) -> Dict:
        compressed = {}
        for key, value in result.items():
            if isinstance(value, str) and len(value) > 300:
                compressed[key] = value[:150] + "..." + value[-100:]
            else:
                compressed[key] = value
        return compressed

    @staticmethod
    def get_compact_file_list(path: str) -> str:
        try:
            items = []
            for item in os.listdir(path)[:20]:
                if not item.startswith('.') and item not in ['__pycache__', 'venv', 'node_modules']:
                    full = os.path.join(path, item)
                    marker = "D" if os.path.isdir(full) else "F"
                    items.append(f"[{marker}]{item}")
            return " | ".join(items)
        except:
            return ""

# ═══════════════════════════════════════════════════════════════════════════════
# SMART SEARCH - Recherche intelligente sans lire les fichiers entiers
# ═══════════════════════════════════════════════════════════════════════════════

class SmartSearch:
    """Recherche intelligente de code sans charger des fichiers entiers."""

    @staticmethod
    def search_in_files(pattern: str, directory: str = None, extensions: List[str] = None) -> Dict:
        """Recherche un pattern dans les fichiers du projet."""
        search_dir = directory or WORKSPACE_DIR
        results = []
        max_results = 10

        # Extensions par defaut
        if not extensions:
            extensions = ['.py', '.js', '.ts', '.html', '.css', '.jsx', '.tsx', '.vue', '.json']

        try:
            for root, dirs, files in os.walk(search_dir):
                # Ignorer certains dossiers
                dirs[:] = [d for d in dirs if d not in ['.git', '__pycache__', 'venv', 'node_modules', '.venv']]

                for filename in files:
                    if len(results) >= max_results:
                        break

                    # Verifier l'extension
                    if extensions and not any(filename.endswith(ext) for ext in extensions):
                        continue

                    filepath = os.path.join(root, filename)
                    rel_path = os.path.relpath(filepath, search_dir)

                    try:
                        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                            for line_num, line in enumerate(f, 1):
                                if pattern.lower() in line.lower():
                                    results.append({
                                        "file": rel_path,
                                        "line": line_num,
                                        "content": line.strip()[:100]
                                    })
                                    if len(results) >= max_results:
                                        break
                    except:
                        continue

            return {
                "success": True,
                "pattern": pattern,
                "results": results,
                "count": len(results)
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    @staticmethod
    def find_function(name: str, directory: str = None) -> Dict:
        """Trouve une fonction/classe par son nom."""
        # Patterns pour differents langages
        patterns = [
            f"def {name}",          # Python
            f"class {name}",        # Python/JS
            f"function {name}",     # JS
            f"const {name}",        # JS const arrow
            f"let {name}",          # JS let arrow
            f"var {name}",          # JS var
            f"async {name}",        # JS async
            f"export.*{name}",      # JS export
        ]

        for pattern in patterns:
            result = SmartSearch.search_in_files(pattern, directory)
            if result.get("count", 0) > 0:
                return result

        return {"success": True, "results": [], "count": 0, "message": f"'{name}' non trouve"}

    @staticmethod
    def get_file_structure(directory: str = None) -> Dict:
        """Retourne la structure du projet de maniere compacte."""
        search_dir = directory or WORKSPACE_DIR
        structure = {"files": [], "dirs": [], "tech": []}

        try:
            for item in os.listdir(search_dir):
                if item.startswith('.'):
                    continue

                full_path = os.path.join(search_dir, item)
                if os.path.isdir(full_path):
                    if item not in ['__pycache__', 'venv', 'node_modules', '.venv']:
                        structure["dirs"].append(item)
                else:
                    structure["files"].append(item)

            # Detection des technologies
            if 'package.json' in structure["files"]:
                structure["tech"].append("Node.js")
            if any(f.endswith('.py') for f in structure["files"]):
                structure["tech"].append("Python")
            if any(f.endswith('.html') for f in structure["files"]):
                structure["tech"].append("HTML")
            if 'Dockerfile' in structure["files"]:
                structure["tech"].append("Docker")

            return {"success": True, "structure": structure}
        except Exception as e:
            return {"success": False, "error": str(e)}

# ═══════════════════════════════════════════════════════════════════════════════
# INTENT CLASSIFIER - Cerveau Hybride (CHAT/DEV/README)
# ═══════════════════════════════════════════════════════════════════════════════

class IntentClassifier:
    """Classifie l'intention de l'utilisateur: CHAT, DEV, ou README."""

    # Mots-cles pour chaque intention
    CHAT_KEYWORDS = [
        "bonjour", "salut", "hello", "hi", "hey", "merci", "thanks",
        "comment ca va", "how are you", "qui es-tu", "who are you",
        "explique", "explain", "c'est quoi", "what is", "pourquoi",
        "aide", "help", "question", "opinion", "avis", "penses-tu",
        "raconte", "dis-moi", "parle-moi"
    ]

    DEV_KEYWORDS = [
        "cree", "create", "code", "developpe", "build", "fais", "make",
        "ajoute", "add", "modifie", "modify", "change", "update",
        "corrige", "fix", "bug", "erreur", "error", "debug",
        "implemente", "implement", "ecris", "write", "genere", "generate",
        "supprime", "delete", "remove", "refactor", "optimise",
        "landing page", "dashboard", "api", "component", "fonction",
        "jeu", "game", "app", "application", "site", "website"
    ]

    README_KEYWORDS = [
        "readme", "documentation", "doc", "documente", "document",
        "explique le projet", "decris le projet", "describe project"
    ]

    @classmethod
    def classify(cls, message: str) -> str:
        """Classifie le message en CHAT, DEV ou README."""
        msg_lower = message.lower()

        # Verifier README en premier (plus specifique)
        for keyword in cls.README_KEYWORDS:
            if keyword in msg_lower:
                return "README"

        # Compter les mots-cles DEV
        dev_score = sum(1 for kw in cls.DEV_KEYWORDS if kw in msg_lower)

        # Compter les mots-cles CHAT
        chat_score = sum(1 for kw in cls.CHAT_KEYWORDS if kw in msg_lower)

        # Si le message est tres court et conversationnel
        if len(message) < 20 and chat_score > 0:
            return "CHAT"

        # Si beaucoup de mots-cles DEV
        if dev_score >= 2 or (dev_score > chat_score and dev_score > 0):
            return "DEV"

        # Si question ou conversation
        if '?' in message or chat_score > dev_score:
            return "CHAT"

        # Par defaut, si le message parle de creation/modification -> DEV
        if dev_score > 0:
            return "DEV"

        return "CHAT"

    @classmethod
    def classify_with_ai(cls, message: str) -> str:
        """Classification avancee via l'IA (utilise si la methode simple echoue)."""
        if not client:
            return cls.classify(message)

        try:
            response = client.messages.create(
                model=CONFIG["models"]["classifier"],
                max_tokens=50,
                system="""Classifie le message en exactement UN mot: CHAT, DEV, ou README.
- CHAT: Questions, conversations, explications, aide generale
- DEV: Creation de code, modification, correction de bugs, nouveaux fichiers
- README: Generation de documentation du projet
Reponds UNIQUEMENT par: CHAT, DEV, ou README""",
                messages=[{"role": "user", "content": message}]
            )

            result = response.content[0].text.strip().upper()
            if result in ["CHAT", "DEV", "README"]:
                return result
            return cls.classify(message)
        except:
            return cls.classify(message)

# ═══════════════════════════════════════════════════════════════════════════════
# PERSISTENCE MEMOIRE
# ═══════════════════════════════════════════════════════════════════════════════

class MemoryManager:
    """Gere la persistance des conversations."""

    def __init__(self):
        self.memory_file = Config.MEMORY_FILE

    def _get_path(self) -> str:
        return os.path.join(WORKSPACE_DIR, self.memory_file)

    def save(self, orchestrator: 'AgentOrchestrator') -> bool:
        try:
            def make_serializable(obj):
                if isinstance(obj, (str, int, float, bool, type(None))):
                    return obj
                if isinstance(obj, dict):
                    return {k: make_serializable(v) for k, v in obj.items()}
                if isinstance(obj, list):
                    return [make_serializable(x) for x in obj]
                if hasattr(obj, '__dict__'):
                    return make_serializable(obj.__dict__)
                if hasattr(obj, 'to_dict'):
                    return make_serializable(obj.to_dict())
                return str(obj)

            data = {
                "saved_at": datetime.now().isoformat(),
                "workspace": WORKSPACE_DIR,
                "version": "3.0",
                "boss": make_serializable(TokenOptimizer.compress_conversation(orchestrator.conversation_boss)),
                "coder": make_serializable(TokenOptimizer.compress_conversation(orchestrator.conversation_coder)),
                "reviewer": make_serializable(TokenOptimizer.compress_conversation(orchestrator.conversation_reviewer)),
                "chat_history": make_serializable(orchestrator.chat_history[-20:]),
                "files": orchestrator.created_files[-10:],
                "project_summary": orchestrator.project_summary,
                "usage": USAGE_STATS
            }
            with open(self._get_path(), "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2, default=str)
            return True
        except Exception as e:
            logger.error(f"Sauvegarde memoire: {e}")
            return False

    def load(self, orchestrator: 'AgentOrchestrator') -> bool:
        try:
            path = self._get_path()
            if not os.path.exists(path):
                return False
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)

            def is_valid_conversation(conv):
                if not isinstance(conv, list):
                    return False
                for msg in conv:
                    if not isinstance(msg, dict):
                        return False
                    if "role" not in msg or "content" not in msg:
                        return False
                    content = msg.get("content")
                    if isinstance(content, str) and ("TextBlock(" in content or "ToolUseBlock(" in content):
                        return False
                    if isinstance(content, list):
                        for item in content:
                            if isinstance(item, str) and ("TextBlock(" in item or "ToolUseBlock(" in item):
                                return False
                return True

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
            orchestrator.chat_history = data.get("chat_history", [])
            orchestrator.project_summary = data.get("project_summary", "")

            logger.info(f"Memoire chargee (v{data.get('version', '2.x')})")
            return True
        except Exception as e:
            logger.warning(f"Memoire non chargee: {e}")
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
# OUTILS AGENTS (enrichis avec smart_search et start_server)
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
        "description": "Cree/modifie un fichier.",
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
    },
    {
        "name": "smart_search",
        "description": "Recherche intelligente de code sans lire les fichiers entiers. Economise des tokens!",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Texte ou pattern a rechercher"},
                "extensions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Extensions de fichiers (optionnel, ex: ['.py', '.js'])"
                }
            },
            "required": ["pattern"]
        }
    },
    {
        "name": "find_function",
        "description": "Trouve une fonction ou classe par son nom dans le projet.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Nom de la fonction/classe"}
            },
            "required": ["name"]
        }
    },
    {
        "name": "start_server",
        "description": "Lance un serveur en arriere-plan pour le live preview (Node, Python, etc).",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Commande a executer (ex: npm start, python -m http.server)"},
                "port": {"type": "integer", "description": "Port du serveur (defaut: 3000)"}
            },
            "required": ["command"]
        }
    },
    {
        "name": "stop_server",
        "description": "Arrete un serveur en arriere-plan.",
        "input_schema": {
            "type": "object",
            "properties": {
                "port": {"type": "integer", "description": "Port du serveur a arreter"}
            },
            "required": ["port"]
        }
    }
]

def execute_tool(name: str, args: dict) -> dict:
    """Execute un outil avec resultats compresses."""
    global WORKSPACE_DIR

    try:
        if name == "read_file":
            path = os.path.join(WORKSPACE_DIR, args["filename"])
            if not os.path.exists(path):
                return {"success": False, "error": f"Fichier non trouve: {args['filename']}"}
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            return {"success": True, "content": content[:3000], "size": len(content)}

        elif name == "write_file":
            path = os.path.join(WORKSPACE_DIR, args["filename"])
            parent = os.path.dirname(path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(args["content"])
            return {"success": True, "msg": f"OK {args['filename']}"}

        elif name == "run_command":
            is_safe, reason = is_command_safe(args["command"])
            if not is_safe:
                return {"success": False, "error": reason}

            result = subprocess.run(
                ["powershell", "-Command", args["command"]],
                capture_output=True, text=True, cwd=WORKSPACE_DIR,
                timeout=Config.COMMAND_TIMEOUT
            )
            stdout = result.stdout.strip()[:500] if result.stdout else ""
            stderr = result.stderr.strip()[:200] if result.stderr else ""
            return {"success": result.returncode == 0, "out": stdout, "err": stderr}

        elif name == "list_files":
            path = os.path.join(WORKSPACE_DIR, args.get("directory", "."))
            if not os.path.exists(path):
                return {"success": False, "error": "Dossier non trouve"}
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

        elif name == "smart_search":
            extensions = args.get("extensions")
            return SmartSearch.search_in_files(args["pattern"], WORKSPACE_DIR, extensions)

        elif name == "find_function":
            return SmartSearch.find_function(args["name"], WORKSPACE_DIR)

        elif name == "start_server":
            port = args.get("port", 3000)
            return server_manager.start_server(args["command"], port, WORKSPACE_DIR)

        elif name == "stop_server":
            return server_manager.stop_server(args["port"])

        return {"success": False, "error": f"Outil inconnu: {name}"}

    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Timeout"}
    except Exception as e:
        return {"success": False, "error": str(e)[:100]}

# ═══════════════════════════════════════════════════════════════════════════════
# PROMPTS SYSTEME
# ═══════════════════════════════════════════════════════════════════════════════

BOSS_PROMPT = """Tu es le BOSS d'ORBIT v3. Tu analyses et planifies.

FORMAT:
[ANALYSE] Ce que l'utilisateur veut (1-2 lignes)
[PLAN] Etapes numerotees (max 5)
[INSTRUCTION_CODER] Instructions detaillees pour le CODER

REGLES:
- UTILISE smart_search AVANT de lire des fichiers entiers
- Sois concis et efficace
- Delegue au CODER pour l'execution
- Pas de signature/credit dans le code"""

CODER_PROMPT = """Tu es le CODER d'ORBIT v3 sur Windows PowerShell.

OUTILS: write_file, read_file, run_command, list_files, smart_search, find_function, start_server

REGLES:
- Separe HTML/CSS/JS en fichiers distincts
- PowerShell: utilise 'dir' pas 'ls', 'type' pas 'cat'
- Dark mode par defaut pour les UI
- Pas de signature/credit
- Si erreur -> analyse et corrige immediatement
- Pour les apps React/Node, utilise start_server pour le preview

FORMAT: [ACTION] description [EXECUTION] ce que tu fais [RESULTAT] resultat"""

REVIEWER_PROMPT = """Tu es le REVIEWER d'ORBIT v3. Tu verifies le code.

FORMAT:
[REVIEW] Fichiers verifies
[CHECKLIST] Points (OK ou X pour chaque)
[VERDICT] APPROUVE ou CORRECTIONS avec details

Si CORRECTIONS, sois specifique sur ce qu'il faut corriger."""

CHAT_PROMPT = """Tu es ORBIT, un assistant de developpement intelligent.
Tu reponds de maniere conversationnelle et utile.
Tu as acces au contexte du projet actuel.
Sois concis mais informatif. N'utilise pas les outils sauf si necessaire."""

README_PROMPT = """Tu es un expert en documentation. Genere un README.md complet:

# Nom du Projet
## Description
## Installation
## Usage
## Structure
## Technologies

Base-toi sur l'analyse des fichiers du projet."""

# ═══════════════════════════════════════════════════════════════════════════════
# ORCHESTRATEUR AUTONOME (The Loop)
# ═══════════════════════════════════════════════════════════════════════════════

class AgentOrchestrator:
    """Orchestrateur avec boucle d'autonomie (max 5 iterations)."""

    def __init__(self):
        self.conversation_boss: List[Dict] = []
        self.conversation_coder: List[Dict] = []
        self.conversation_reviewer: List[Dict] = []
        self.created_files: List[str] = []
        self.current_agent: str = "boss"
        self.chat_history: List[Dict] = []
        self.project_summary: str = ""
        self.loop_count: int = 0
        self.last_error: str = ""

    def reset(self) -> None:
        self.conversation_boss = []
        self.conversation_coder = []
        self.conversation_reviewer = []
        self.created_files = []
        self.chat_history = []
        self.project_summary = ""
        self.loop_count = 0
        self.last_error = ""

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
            raise RuntimeError("Client Anthropic non initialise")

        compressed_messages = TokenOptimizer.compress_conversation(messages)
        model = CONFIG["models"].get(agent, CONFIG["models"]["coder"])

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
                if any(x in error_msg for x in ["network", "timeout", "connection", "overloaded", "529", "500", "502", "503"]):
                    wait_time = (attempt + 1) * 2
                    logger.warning(f"Erreur reseau {agent} (tentative {attempt+1}/{max_retries}), retry dans {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    raise e

        raise RuntimeError(f"Echec apres {max_retries} tentatives: {last_error}")

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

                # Tracker les erreurs
                if not result.get("success"):
                    self.last_error = result.get("error", "Erreur inconnue")

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
                    tool_results_content.append({
                        "type": "tool_result",
                        "tool_use_id": tr["id"],
                        "content": json.dumps(tr["result"], ensure_ascii=False, separators=(',', ':'))
                    })
                conversation.append({"role": "user", "content": tool_results_content})
            else:
                break

        yield {"type": "agent_complete", "agent": agent}

    # ───────────────────────────────────────────────────────────────────────
    # MODE CHAT - Conversation simple sans pipeline DEV
    # ───────────────────────────────────────────────────────────────────────

    def handle_chat(self, user_message: str) -> Generator:
        """Gere une conversation simple (mode CHAT)."""
        logger.info(f"[CHAT] {user_message[:40]}...")

        yield {"type": "phase", "phase": "CHAT", "status": "Conversation"}

        # Construire le contexte
        context = f"Projet actuel: {os.path.basename(WORKSPACE_DIR)}\n"

        # Ajouter le resume du projet si disponible
        if self.project_summary:
            context += f"Resume: {self.project_summary}\n"
        else:
            # Scanner rapidement le projet
            structure = SmartSearch.get_file_structure()
            if structure.get("success"):
                files = structure["structure"].get("files", [])[:10]
                tech = structure["structure"].get("tech", [])
                context += f"Fichiers: {', '.join(files)}\n"
                context += f"Technologies: {', '.join(tech)}\n"

        # Historique recent
        recent_history = self.chat_history[-6:] if self.chat_history else []

        messages = recent_history + [{"role": "user", "content": f"{context}\n\nQuestion: {user_message}"}]

        try:
            response = self.call_agent("boss", messages, CHAT_PROMPT)

            response_text = ""
            for block in response.content:
                if block.type == "text":
                    response_text += block.text
                    yield {"type": "agent_text", "agent": "chat", "content": block.text}

            # Sauvegarder dans l'historique
            self.chat_history.append({"role": "user", "content": user_message})
            self.chat_history.append({"role": "assistant", "content": response_text})

            # Garder seulement les 20 derniers messages
            self.chat_history = self.chat_history[-20:]

        except Exception as e:
            yield {"type": "agent_text", "agent": "chat", "content": f"Erreur: {str(e)}"}

        memory_manager.save(self)
        yield {"type": "complete", "files": [], "preview": None}

    # ───────────────────────────────────────────────────────────────────────
    # MODE README - Generation de documentation
    # ───────────────────────────────────────────────────────────────────────

    def handle_readme(self, user_message: str) -> Generator:
        """Genere un README.md intelligent."""
        logger.info(f"[README] Generation documentation...")

        yield {"type": "phase", "phase": "README", "status": "Analyse"}

        # Scanner le projet
        structure = SmartSearch.get_file_structure()
        project_name = os.path.basename(WORKSPACE_DIR)

        # Lire les fichiers cles pour comprendre le projet
        key_files_content = ""
        key_files = ['package.json', 'requirements.txt', 'app.py', 'index.html', 'main.py', 'server.js']

        for filename in key_files:
            filepath = os.path.join(WORKSPACE_DIR, filename)
            if os.path.exists(filepath):
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        content = f.read()[:500]
                    key_files_content += f"\n--- {filename} ---\n{content}\n"
                except:
                    pass

        prompt = f"""Genere un README.md professionnel pour ce projet:

Projet: {project_name}
Structure: {json.dumps(structure.get('structure', {}), indent=2)}
Contenu des fichiers principaux:
{key_files_content}

{user_message}"""

        messages = [{"role": "user", "content": prompt}]

        yield {"type": "phase", "phase": "README", "status": "Redaction"}

        try:
            response = self.call_agent("boss", messages, README_PROMPT)

            readme_content = ""
            for block in response.content:
                if block.type == "text":
                    readme_content += block.text
                    yield {"type": "agent_text", "agent": "readme", "content": block.text}

            # Sauvegarder le README
            readme_path = os.path.join(WORKSPACE_DIR, "README.md")
            with open(readme_path, "w", encoding="utf-8") as f:
                f.write(readme_content)

            self.created_files.append("README.md")
            yield {"type": "tool_result", "agent": "readme", "tool": "write_file",
                   "success": True, "result": {"msg": "README.md genere"}}

        except Exception as e:
            yield {"type": "agent_text", "agent": "readme", "content": f"Erreur: {str(e)}"}

        memory_manager.save(self)
        yield {"type": "complete", "files": ["README.md"], "preview": None}

    # ───────────────────────────────────────────────────────────────────────
    # MODE DEV - Boucle d'autonomie complete
    # ───────────────────────────────────────────────────────────────────────

    def orchestrate_dev(self, user_message: str) -> Generator:
        """Boucle d'autonomie: PLAN -> ACTION -> VERIFY -> DECISION (max 5 iterations)."""
        logger.info(f"[DEV] {user_message[:40]}...")

        self.loop_count = 0
        self.last_error = ""
        max_loops = Config.MAX_AUTONOMY_LOOPS

        while self.loop_count < max_loops:
            self.loop_count += 1
            logger.info(f"=== BOUCLE AUTONOMIE {self.loop_count}/{max_loops} ===")

            yield {"type": "loop_start", "iteration": self.loop_count, "max": max_loops}

            # ─────────────────────────────────────────────────────────────
            # PHASE 1: PLAN (BOSS)
            # ─────────────────────────────────────────────────────────────
            yield {"type": "phase", "phase": "BOSS", "status": f"Planning (Loop {self.loop_count})"}

            # Si c'est une correction, ajouter le contexte de l'erreur
            boss_message = user_message
            if self.loop_count > 1 and self.last_error:
                boss_message = f"""CORRECTION REQUISE (iteration {self.loop_count}):
Erreur precedente: {self.last_error}
Demande originale: {user_message}

Analyse l'erreur et propose une solution alternative."""

            self.conversation_boss.append({"role": "user", "content": boss_message})

            boss_text = ""
            for event in self.run_agent_loop("boss", boss_message, BOSS_PROMPT, self.conversation_boss, max_turns=3):
                yield event
                if event.get("type") == "agent_text":
                    boss_text += event.get("content", "")

            # Extraire les instructions pour le coder
            coder_instructions = boss_text
            if "[INSTRUCTION_CODER]" in boss_text:
                coder_instructions = boss_text.split("[INSTRUCTION_CODER]")[-1].strip()

            # ─────────────────────────────────────────────────────────────
            # PHASE 2: ACTION (CODER)
            # ─────────────────────────────────────────────────────────────
            yield {"type": "phase", "phase": "CODER", "status": f"Coding (Loop {self.loop_count})"}

            self.conversation_coder = [{"role": "user", "content": f"BOSS:\n{coder_instructions}"}]
            self.last_error = ""  # Reset error

            coder_had_error = False
            for event in self.run_agent_loop("coder", coder_instructions, CODER_PROMPT, self.conversation_coder, max_turns=6):
                yield event
                if event.get("type") == "tool_result" and not event.get("success", True):
                    coder_had_error = True

            # ─────────────────────────────────────────────────────────────
            # PHASE 3: VERIFY (REVIEWER)
            # ─────────────────────────────────────────────────────────────
            yield {"type": "phase", "phase": "REVIEWER", "status": f"Reviewing (Loop {self.loop_count})"}

            files_str = ", ".join(self.created_files[-5:]) if self.created_files else "aucun fichier"
            review_message = f"Verifie les fichiers crees: {files_str}"

            if self.last_error:
                review_message += f"\nErreur detectee: {self.last_error}"

            self.conversation_reviewer = [{"role": "user", "content": review_message}]

            reviewer_text = ""
            for event in self.run_agent_loop("reviewer", "", REVIEWER_PROMPT, self.conversation_reviewer, max_turns=2):
                yield event
                if event.get("type") == "agent_text":
                    reviewer_text += event.get("content", "")

            # ─────────────────────────────────────────────────────────────
            # PHASE 4: DECISION
            # ─────────────────────────────────────────────────────────────
            verdict_approved = "APPROUVE" in reviewer_text.upper() or "APPROVED" in reviewer_text.upper()
            has_critical_error = coder_had_error or (self.last_error and "error" in self.last_error.lower())

            if verdict_approved and not has_critical_error:
                # SUCCES: Commit et fin
                if SystemHealth.git_available and CONFIG["autopilot"]:
                    yield {"type": "phase", "phase": "GIT", "status": "Commit"}
                    commit_msg = f"feat: {user_message[:40]}"
                    if self.loop_count > 1:
                        commit_msg = f"fix: {user_message[:35]} (v{self.loop_count})"
                    result = execute_tool("git_commit", {"message": commit_msg})
                    yield {"type": "tool_result", "agent": "git", "tool": "git_commit",
                           "success": result.get("success", False), "result": result}

                yield {"type": "loop_end", "iteration": self.loop_count, "status": "SUCCESS"}
                break

            else:
                # ECHEC: Continuer la boucle si possible
                if self.loop_count < max_loops:
                    yield {"type": "loop_end", "iteration": self.loop_count, "status": "RETRY",
                           "reason": self.last_error or "Review non approuve"}

                    # Extraire la correction du reviewer si disponible
                    if "CORRECTION" in reviewer_text.upper():
                        correction_part = reviewer_text.split("CORRECTION")[-1][:200]
                        self.last_error = f"Review: {correction_part}"
                else:
                    yield {"type": "loop_end", "iteration": self.loop_count, "status": "MAX_REACHED"}

        # Sauvegarder la memoire
        memory_manager.save(self)

        # Determiner le fichier de preview
        html_files = [f for f in self.created_files if f.endswith('.html')]
        preview_file = html_files[0] if html_files else None

        # Verifier si un serveur tourne
        servers = server_manager.list_servers()
        server_info = None
        if servers:
            running = [s for s in servers if s.get("running")]
            if running:
                server_info = {"port": running[0]["port"], "url": f"http://localhost:{running[0]['port']}"}

        yield {"type": "complete",
               "files": self.created_files,
               "preview": preview_file,
               "server": server_info,
               "loops": self.loop_count}

    # ───────────────────────────────────────────────────────────────────────
    # POINT D'ENTREE PRINCIPAL
    # ───────────────────────────────────────────────────────────────────────

    def orchestrate(self, user_message: str) -> Generator:
        """Point d'entree principal avec classification d'intention."""

        # ETAPE 1: Classifier l'intention
        intent = IntentClassifier.classify(user_message)
        logger.info(f"[INTENT] {intent} -> {user_message[:30]}...")

        yield {"type": "intent", "intent": intent}

        # ETAPE 2: Router vers le bon handler
        if intent == "CHAT":
            yield from self.handle_chat(user_message)
        elif intent == "README":
            yield from self.handle_readme(user_message)
        else:  # DEV
            yield from self.orchestrate_dev(user_message)


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
    """Cree un repo GitHub et retourne le resultat."""
    if not SystemHealth.gh_available:
        return {"success": False, "error": "GitHub CLI non installe"}
    if not SystemHealth.git_available:
        return {"success": False, "error": "Git non installe"}

    visibility = "--private" if private else "--public"

    check = subprocess.run(
        ["powershell", "-Command", "git remote get-url origin"],
        capture_output=True, text=True, cwd=WORKSPACE_DIR
    )
    if check.returncode == 0 and check.stdout.strip():
        return {"success": False, "error": f"Remote existe: {check.stdout.strip()[:50]}"}

    subprocess.run(["powershell", "-Command", "git init"], cwd=WORKSPACE_DIR, capture_output=True)

    result = subprocess.run(
        ["powershell", "-Command", f'gh repo create {name} {visibility} --source=. --remote=origin'],
        capture_output=True, text=True, cwd=WORKSPACE_DIR
    )

    if result.returncode != 0:
        return {"success": False, "error": result.stderr.strip()[:100] or result.stdout.strip()[:100]}

    subprocess.run(["powershell", "-Command", "git add -A"], cwd=WORKSPACE_DIR, capture_output=True)
    subprocess.run(["powershell", "-Command", 'git commit -m "Initial commit"'], cwd=WORKSPACE_DIR, capture_output=True)
    subprocess.run(["powershell", "-Command", "git push -u origin main"], cwd=WORKSPACE_DIR, capture_output=True)
    subprocess.run(["powershell", "-Command", "git push -u origin master"], cwd=WORKSPACE_DIR, capture_output=True)

    return {"success": True, "message": f"Repo cree: {name}", "url": result.stdout.strip()}

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
    server_manager.stop_all()
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
            CONFIG['models']['coder'] = model
            CONFIG['models']['reviewer'] = model
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
        "version": "3.0",
        "git": SystemHealth.git_available,
        "gh": SystemHealth.gh_available,
        "workspace": WORKSPACE_DIR,
        "model": Config.DEFAULT_MODEL,
        "servers": server_manager.list_servers()
    })

# ═══════════════════════════════════════════════════════════════════════════════
# ROUTES SERVEURS BACKGROUND
# ═══════════════════════════════════════════════════════════════════════════════

@app.route('/servers')
def list_servers():
    return jsonify({"servers": server_manager.list_servers()})

@app.route('/servers/start', methods=['POST'])
def start_server_route():
    data = request.json or {}
    command = data.get('command', 'python -m http.server 3000')
    port = data.get('port', 3000)
    return jsonify(server_manager.start_server(command, port, WORKSPACE_DIR))

@app.route('/servers/stop', methods=['POST'])
def stop_server_route():
    data = request.json or {}
    port = data.get('port')
    if not port:
        return jsonify({"success": False, "error": "Port requis"})
    return jsonify(server_manager.stop_server(port))

# ═══════════════════════════════════════════════════════════════════════════════
# ROUTES GIT
# ═══════════════════════════════════════════════════════════════════════════════

@app.route('/git/status')
def git_status_route():
    if not SystemHealth.git_available:
        return jsonify({"success": False, "status": "Git non installe"})
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
        return jsonify({"success": False, "diff": "Git non installe"})
    result = subprocess.run(
        ["powershell", "-Command", "git diff --stat"],
        capture_output=True, text=True, cwd=WORKSPACE_DIR
    )
    return jsonify({"success": True, "diff": result.stdout.strip()[:500] or "Aucun changement"})

@app.route('/git/commit', methods=['POST'])
def git_commit_route():
    if not SystemHealth.git_available:
        return jsonify({"success": False, "error": "Git non installe"})

    data = request.json or {}
    message = data.get('message', '').strip() or generate_commit_message()
    if not message:
        return jsonify({"success": False, "error": "Rien a commiter"})

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
        return jsonify({"success": False, "error": "Git non installe"})
    result = subprocess.run(
        ["powershell", "-Command", "git push"],
        capture_output=True, text=True, cwd=WORKSPACE_DIR
    )
    return jsonify({"success": result.returncode == 0, "output": result.stdout.strip() or result.stderr.strip()})

@app.route('/git/pull', methods=['POST'])
def git_pull_route():
    if not SystemHealth.git_available:
        return jsonify({"success": False, "error": "Git non installe"})
    result = subprocess.run(
        ["powershell", "-Command", "git pull"],
        capture_output=True, text=True, cwd=WORKSPACE_DIR
    )
    return jsonify({"success": result.returncode == 0, "output": result.stdout.strip() or result.stderr.strip()})

@app.route('/git/log')
def git_log_route():
    if not SystemHealth.git_available:
        return jsonify({"success": False, "log": "Git non installe"})
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
    return jsonify({"success": True, "message": "README.md genere"})

# ═══════════════════════════════════════════════════════════════════════════════
# ROUTES GITHUB
# ═══════════════════════════════════════════════════════════════════════════════

@app.route('/github/create', methods=['POST'])
def github_create():
    if not SystemHealth.gh_available:
        return jsonify({"success": False, "error": "GitHub CLI non installe. Installez: winget install GitHub.cli"})

    data = request.json or {}
    repo_name = data.get('name', os.path.basename(WORKSPACE_DIR))
    private = data.get('private', True)

    result = create_github_repo(repo_name, private)
    return jsonify(result)

@app.route('/github/status')
def github_status():
    if not SystemHealth.gh_available:
        return jsonify({"authenticated": False, "output": "GitHub CLI non installe"})

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
    global WORKSPACE_DIR
    data = request.json or {}
    name = data.get('name', '').strip()
    auto_github = data.get('auto_github', Config.AUTO_CREATE_GITHUB)
    private = data.get('private', True)

    if not name:
        return jsonify({"success": False, "error": "Nom de projet requis"})

    name = "".join(c for c in name if c.isalnum() or c in (' ', '-', '_')).strip()
    name = name.replace(' ', '_')

    if not name:
        return jsonify({"success": False, "error": "Nom invalide"})

    project_path = os.path.join(Config.PROJECTS_ROOT, name)

    if os.path.exists(project_path):
        return jsonify({"success": False, "error": f"'{name}' existe deja"})

    try:
        os.makedirs(project_path)
        logger.info(f"Dossier cree: {project_path}")

        WORKSPACE_DIR = project_path

        git_ok = False
        if SystemHealth.git_available:
            subprocess.run(["powershell", "-Command", "git init"], cwd=project_path, capture_output=True)
            git_ok = True
            logger.info(f"  Git initialise")

        readme_path = os.path.join(project_path, "README.md")
        with open(readme_path, "w", encoding="utf-8") as f:
            f.write(f"# {name}\n\nProjet cree avec ORBIT v3.\n")

        github_result = None
        if auto_github and SystemHealth.gh_available and git_ok:
            github_result = create_github_repo(name, private)
            if github_result.get("success"):
                logger.info(f"  Repo GitHub cree: {name}")
            else:
                logger.warning(f"  GitHub: {github_result.get('error', 'erreur')}")

        orchestrator.reset()

        response = {
            "success": True,
            "message": f"Projet '{name}' cree",
            "path": project_path,
            "git_initialized": git_ok
        }

        if github_result:
            response["github"] = github_result

        return jsonify(response)

    except Exception as e:
        logger.error(f"Creation projet: {e}")
        return jsonify({"success": False, "error": str(e)})

@app.route('/projects/select', methods=['POST'])
def select_project():
    global WORKSPACE_DIR
    data = request.json or {}
    name = data.get('name', '')

    project_path = os.path.join(Config.PROJECTS_ROOT, name)

    if not os.path.exists(project_path):
        return jsonify({"success": False, "error": f"'{name}' introuvable"})

    WORKSPACE_DIR = project_path
    orchestrator.reset()

    memory_loaded = memory_manager.load(orchestrator)

    if not memory_loaded or len(orchestrator.conversation_boss) == 0:
        structure = SmartSearch.get_file_structure(project_path)
        if structure.get("success"):
            s = structure["structure"]
            context_message = f"[CONTEXTE PROJET]\nFichiers: {', '.join(s.get('files', []))}\nDossiers: {', '.join(s.get('dirs', []))}\nTech: {', '.join(s.get('tech', []))}"
            orchestrator.conversation_boss = [{"role": "user", "content": context_message}]
            logger.info(f"Contexte projet scanne")

    logger.info(f"Projet selectionne: {name}")
    return jsonify({"success": True, "message": f"'{name}' selectionne", "path": project_path, "context_loaded": True})

@app.route('/projects/current')
def current_project():
    return jsonify({"name": os.path.basename(WORKSPACE_DIR), "path": WORKSPACE_DIR})

# ═══════════════════════════════════════════════════════════════════════════════
# CLEANUP
# ═══════════════════════════════════════════════════════════════════════════════

import atexit

@atexit.register
def cleanup():
    """Nettoie les ressources a la fermeture."""
    server_manager.stop_all()
    logger.info("ORBIT ferme. Serveurs arretes.")

# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    print("\n" + "=" * 55)
    print("  ORBIT v3.0 - Autonomous Core")
    print("  -> http://127.0.0.1:5000")
    print("-" * 55)
    print(f"  Projets: {Config.PROJECTS_ROOT}")
    print(f"  Modele: {Config.DEFAULT_MODEL}")
    print(f"  Git: {'OK' if SystemHealth.git_available else 'X'}")
    print(f"  GitHub: {'OK' if SystemHealth.gh_available else 'X (optionnel)'}")
    print(f"  Max tokens: {Config.MAX_TOKENS}")
    print(f"  Boucles autonomie: {Config.MAX_AUTONOMY_LOOPS}")
    print("=" * 55)
    print("  [CHAT] Conversation | [DEV] Code | [README] Doc")
    print("=" * 55 + "\n")

    app.run(debug=True, port=5000, threaded=True)
