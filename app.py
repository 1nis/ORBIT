"""
ORBIT v4 - Vision & Network Edition
Architecture: State Machine avec Intent Classification + Boucle d'Autonomie + Vision AI

Version: 4.0 - Vision & Network Edition
Fonctionnalites:
- Intent Classification (CHAT/DEV/README/DEBUG_VISUAL)
- Boucle d'Autonomie (The Loop) - Max 5 iterations
- Vision par Ordinateur (Playwright Screenshots + Claude Vision API)
- Acces Internet Controle (DuckDuckGo Search + Web Reader)
- Memoire Self-Healing (known_bugs_fixes)
- Smart Search (optimisation tokens)
- Background Server pour Live Preview
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
import base64
import asyncio
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
    SCREENSHOT_DIR: str = os.getenv("ORBIT_SCREENSHOT_DIR", "screenshots")

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
    playwright_available: bool = False
    duckduckgo_available: bool = False

    @classmethod
    def check_all(cls) -> None:
        cls.git_available = shutil.which("git") is not None
        cls.gh_available = shutil.which("gh") is not None

        # Check Playwright
        try:
            from playwright.sync_api import sync_playwright
            cls.playwright_available = True
        except ImportError:
            cls.playwright_available = False
            logger.warning("Playwright non installe. Installez: pip install playwright && playwright install chromium")

        # Check DuckDuckGo Search
        try:
            from duckduckgo_search import DDGS
            cls.duckduckgo_available = True
        except ImportError:
            cls.duckduckgo_available = False
            logger.warning("duckduckgo-search non installe. Installez: pip install duckduckgo-search")

        logger.info(f"Git: {'OK' if cls.git_available else 'X'} | GitHub CLI: {'OK' if cls.gh_available else 'X'} | Playwright: {'OK' if cls.playwright_available else 'X'} | DuckDuckGo: {'OK' if cls.duckduckgo_available else 'X'}")

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
    "max_iterations": 15,
    "internet_enabled": False  # Toggle Internet - desactive par defaut
}

USAGE_STATS = {"total_input_tokens": 0, "total_output_tokens": 0, "calls": []}

# ═══════════════════════════════════════════════════════════════════════════════
# VISION ENGINE - Screenshots avec Playwright
# ═══════════════════════════════════════════════════════════════════════════════

class VisionEngine:
    """Moteur de vision pour prendre et analyser des screenshots."""

    def __init__(self):
        self.screenshot_dir = os.path.join(WORKSPACE_DIR, Config.SCREENSHOT_DIR)
        os.makedirs(self.screenshot_dir, exist_ok=True)

    def take_screenshot(self, url: str, filename: str = None, full_page: bool = False) -> Dict:
        """Prend un screenshot d'une URL avec Playwright."""
        if not SystemHealth.playwright_available:
            return {"success": False, "error": "Playwright non installe. pip install playwright && playwright install chromium"}

        try:
            from playwright.sync_api import sync_playwright

            if not filename:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"screenshot_{timestamp}.png"

            filepath = os.path.join(self.screenshot_dir, filename)

            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page(viewport={"width": 1280, "height": 720})

                try:
                    page.goto(url, timeout=30000)
                    page.wait_for_load_state("networkidle", timeout=10000)
                except:
                    pass  # Continue even if timeout

                page.screenshot(path=filepath, full_page=full_page)
                browser.close()

            # Encoder en base64 pour l'API Vision
            with open(filepath, "rb") as f:
                image_data = base64.standard_b64encode(f.read()).decode("utf-8")

            return {
                "success": True,
                "filepath": filepath,
                "filename": filename,
                "url": url,
                "base64": image_data,
                "size": os.path.getsize(filepath)
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    def analyze_screenshot(self, image_base64: str, prompt: str = None) -> Dict:
        """Analyse un screenshot avec l'API Vision de Claude."""
        if not client:
            return {"success": False, "error": "Client Anthropic non initialise"}

        analysis_prompt = prompt or """Analyse cette capture d'ecran d'un site web en developpement.
Identifie:
1. Les problemes visuels (alignement, espacement, couleurs)
2. Les bugs d'interface potentiels
3. Les elements manquants ou mal positionnes
4. Suggestions d'amelioration UX/UI

Sois precis et actionnable dans tes observations."""

        try:
            response = client.messages.create(
                model=CONFIG["models"]["reviewer"],
                max_tokens=2000,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/png",
                                    "data": image_base64
                                }
                            },
                            {
                                "type": "text",
                                "text": analysis_prompt
                            }
                        ]
                    }
                ]
            )

            analysis = response.content[0].text if response.content else "Pas d'analyse disponible"

            return {
                "success": True,
                "analysis": analysis,
                "tokens_used": {
                    "input": response.usage.input_tokens,
                    "output": response.usage.output_tokens
                }
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

vision_engine = VisionEngine()

# ═══════════════════════════════════════════════════════════════════════════════
# INTERNET ENGINE - Recherche Web et Lecture de Pages
# ═══════════════════════════════════════════════════════════════════════════════

class InternetEngine:
    """Moteur de recherche et lecture web."""

    @staticmethod
    def is_enabled() -> bool:
        """Verifie si l'acces internet est active."""
        return CONFIG.get("internet_enabled", False)

    @staticmethod
    def web_search(query: str, max_results: int = 5) -> Dict:
        """Recherche sur le web via DuckDuckGo."""
        if not InternetEngine.is_enabled():
            return {"success": False, "error": "Acces Internet desactive. Activez le toggle INTERNET."}

        if not SystemHealth.duckduckgo_available:
            return {"success": False, "error": "duckduckgo-search non installe. pip install duckduckgo-search"}

        try:
            from duckduckgo_search import DDGS

            results = []
            with DDGS() as ddgs:
                for r in ddgs.text(query, max_results=max_results):
                    results.append({
                        "title": r.get("title", ""),
                        "url": r.get("href", ""),
                        "snippet": r.get("body", "")[:200]
                    })

            return {
                "success": True,
                "query": query,
                "results": results,
                "count": len(results)
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    @staticmethod
    def read_webpage(url: str, max_chars: int = 5000) -> Dict:
        """Lit le contenu d'une page web."""
        if not InternetEngine.is_enabled():
            return {"success": False, "error": "Acces Internet desactive. Activez le toggle INTERNET."}

        try:
            import urllib.request
            from html.parser import HTMLParser

            class TextExtractor(HTMLParser):
                def __init__(self):
                    super().__init__()
                    self.text = []
                    self.skip_tags = {'script', 'style', 'head', 'meta', 'link'}
                    self.current_tag = None

                def handle_starttag(self, tag, attrs):
                    self.current_tag = tag

                def handle_endtag(self, tag):
                    self.current_tag = None

                def handle_data(self, data):
                    if self.current_tag not in self.skip_tags:
                        text = data.strip()
                        if text:
                            self.text.append(text)

                def get_text(self):
                    return ' '.join(self.text)

            req = urllib.request.Request(url, headers={'User-Agent': 'ORBIT/4.0'})
            with urllib.request.urlopen(req, timeout=15) as response:
                html = response.read().decode('utf-8', errors='ignore')

            parser = TextExtractor()
            parser.feed(html)
            text = parser.get_text()[:max_chars]

            return {
                "success": True,
                "url": url,
                "content": text,
                "length": len(text)
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

internet_engine = InternetEngine()

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
# INTENT CLASSIFIER - Cerveau Hybride (CHAT/DEV/README/DEBUG_VISUAL)
# ═══════════════════════════════════════════════════════════════════════════════

class IntentClassifier:
    """Classifie l'intention de l'utilisateur: CHAT, DEV, README, ou DEBUG_VISUAL."""

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

    DEBUG_VISUAL_KEYWORDS = [
        "debug visuel", "visual debug", "screenshot", "capture",
        "mal centre", "mal aligne", "pas aligne", "decale",
        "probleme visuel", "visual problem", "visual issue",
        "regarde le site", "check the site", "voir le rendu",
        "bouton mal", "element mal", "css bug", "style bug",
        "probleme d'affichage", "display issue", "rendu incorrect"
    ]

    @classmethod
    def classify(cls, message: str) -> str:
        """Classifie le message en CHAT, DEV, README ou DEBUG_VISUAL."""
        msg_lower = message.lower()

        # Verifier DEBUG_VISUAL en premier (plus specifique)
        for keyword in cls.DEBUG_VISUAL_KEYWORDS:
            if keyword in msg_lower:
                return "DEBUG_VISUAL"

        # Verifier README
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
                system="""Classifie le message en exactement UN mot: CHAT, DEV, README, ou DEBUG_VISUAL.
- CHAT: Questions, conversations, explications, aide generale
- DEV: Creation de code, modification, correction de bugs, nouveaux fichiers
- README: Generation de documentation du projet
- DEBUG_VISUAL: Problemes visuels/CSS, demande de screenshot, debug d'interface
Reponds UNIQUEMENT par: CHAT, DEV, README, ou DEBUG_VISUAL""",
                messages=[{"role": "user", "content": message}]
            )

            result = response.content[0].text.strip().upper()
            if result in ["CHAT", "DEV", "README", "DEBUG_VISUAL"]:
                return result
            return cls.classify(message)
        except:
            return cls.classify(message)

# ═══════════════════════════════════════════════════════════════════════════════
# PERSISTENCE MEMOIRE - Avec Self-Healing (known_bugs_fixes)
# ═══════════════════════════════════════════════════════════════════════════════

class MemoryManager:
    """Gere la persistance des conversations et des solutions aux bugs."""

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
                "version": "4.0",
                "boss": make_serializable(TokenOptimizer.compress_conversation(orchestrator.conversation_boss)),
                "coder": make_serializable(TokenOptimizer.compress_conversation(orchestrator.conversation_coder)),
                "reviewer": make_serializable(TokenOptimizer.compress_conversation(orchestrator.conversation_reviewer)),
                "chat_history": make_serializable(orchestrator.chat_history[-20:]),
                "files": orchestrator.created_files[-10:],
                "project_summary": orchestrator.project_summary,
                "known_bugs_fixes": orchestrator.known_bugs_fixes,  # Self-Healing Memory
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
            orchestrator.known_bugs_fixes = data.get("known_bugs_fixes", [])  # Load Self-Healing Memory

            logger.info(f"Memoire chargee (v{data.get('version', '3.x')}) - {len(orchestrator.known_bugs_fixes)} bugs connus")
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

    def add_bug_fix(self, orchestrator: 'AgentOrchestrator', symptom: str, solution: str) -> bool:
        """Ajoute une solution de bug a la memoire Self-Healing."""
        try:
            bug_fix = {
                "symptom": symptom,
                "solution": solution,
                "timestamp": datetime.now().isoformat(),
                "project": os.path.basename(WORKSPACE_DIR)
            }
            orchestrator.known_bugs_fixes.append(bug_fix)
            # Garder seulement les 50 derniers
            orchestrator.known_bugs_fixes = orchestrator.known_bugs_fixes[-50:]
            self.save(orchestrator)
            logger.info(f"Bug fix ajoute: {symptom[:30]}...")
            return True
        except Exception as e:
            logger.error(f"Erreur ajout bug fix: {e}")
            return False

    def find_similar_bug(self, orchestrator: 'AgentOrchestrator', symptom: str) -> Optional[Dict]:
        """Cherche un bug similaire dans la memoire."""
        symptom_lower = symptom.lower()
        for bug in orchestrator.known_bugs_fixes:
            if any(word in bug.get("symptom", "").lower() for word in symptom_lower.split() if len(word) > 3):
                return bug
        return None

memory_manager = MemoryManager()

# ═══════════════════════════════════════════════════════════════════════════════
# OUTILS AGENTS (enrichis avec vision et internet)
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
    },
    # ═══ NOUVEAUX OUTILS V4: VISION ═══
    {
        "name": "take_screenshot",
        "description": "Prend un screenshot d'une URL (localhost ou web). Utilise Playwright en headless. Retourne le chemin et l'image en base64.",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL a capturer (ex: http://localhost:3000)"},
                "filename": {"type": "string", "description": "Nom du fichier (optionnel)"},
                "full_page": {"type": "boolean", "description": "Capture page entiere (defaut: false)"}
            },
            "required": ["url"]
        }
    },
    {
        "name": "analyze_screenshot",
        "description": "Analyse un screenshot avec l'API Vision de Claude pour detecter les problemes visuels.",
        "input_schema": {
            "type": "object",
            "properties": {
                "image_base64": {"type": "string", "description": "Image en base64"},
                "prompt": {"type": "string", "description": "Instructions specifiques pour l'analyse (optionnel)"}
            },
            "required": ["image_base64"]
        }
    },
    # ═══ NOUVEAUX OUTILS V4: INTERNET ═══
    {
        "name": "web_search",
        "description": "Recherche sur le web via DuckDuckGo. REQUIERT: Toggle Internet active.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Requete de recherche"},
                "max_results": {"type": "integer", "description": "Nombre max de resultats (defaut: 5)"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "read_webpage",
        "description": "Lit le contenu texte d'une page web. REQUIERT: Toggle Internet active.",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL de la page a lire"},
                "max_chars": {"type": "integer", "description": "Nombre max de caracteres (defaut: 5000)"}
            },
            "required": ["url"]
        }
    },
    # ═══ OUTIL MEMOIRE SELF-HEALING ═══
    {
        "name": "save_bug_fix",
        "description": "Sauvegarde une solution de bug dans la memoire Self-Healing pour reference future.",
        "input_schema": {
            "type": "object",
            "properties": {
                "symptom": {"type": "string", "description": "Description du symptome/erreur"},
                "solution": {"type": "string", "description": "Solution appliquee"}
            },
            "required": ["symptom", "solution"]
        }
    }
]

def execute_tool(name: str, args: dict, orchestrator: 'AgentOrchestrator' = None) -> dict:
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

        # ═══ OUTILS VISION V4 ═══
        elif name == "take_screenshot":
            url = args["url"]
            filename = args.get("filename")
            full_page = args.get("full_page", False)
            return vision_engine.take_screenshot(url, filename, full_page)

        elif name == "analyze_screenshot":
            image_base64 = args["image_base64"]
            prompt = args.get("prompt")
            return vision_engine.analyze_screenshot(image_base64, prompt)

        # ═══ OUTILS INTERNET V4 ═══
        elif name == "web_search":
            query = args["query"]
            max_results = args.get("max_results", 5)
            return internet_engine.web_search(query, max_results)

        elif name == "read_webpage":
            url = args["url"]
            max_chars = args.get("max_chars", 5000)
            return internet_engine.read_webpage(url, max_chars)

        # ═══ OUTIL MEMOIRE SELF-HEALING ═══
        elif name == "save_bug_fix":
            if orchestrator:
                success = memory_manager.add_bug_fix(
                    orchestrator,
                    args["symptom"],
                    args["solution"]
                )
                return {"success": success, "msg": "Bug fix sauvegarde" if success else "Erreur sauvegarde"}
            return {"success": False, "error": "Orchestrator non disponible"}

        return {"success": False, "error": f"Outil inconnu: {name}"}

    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Timeout"}
    except Exception as e:
        return {"success": False, "error": str(e)[:100]}

# ═══════════════════════════════════════════════════════════════════════════════
# PROMPTS SYSTEME
# ═══════════════════════════════════════════════════════════════════════════════

BOSS_PROMPT = """Tu es le BOSS d'ORBIT v4 (Vision & Network Edition). Tu analyses et planifies.

FORMAT:
[ANALYSE] Ce que l'utilisateur veut (1-2 lignes)
[PLAN] Etapes numerotees (max 5)
[INSTRUCTION_CODER] Instructions detaillees pour le CODER

REGLES:
- UTILISE smart_search AVANT de lire des fichiers entiers
- Consulte la MEMOIRE DES BUGS CONNUS avant chaque tache
- Si internet est active, tu peux utiliser web_search pour chercher des docs
- Sois concis et efficace
- Delegue au CODER pour l'execution
- Pas de signature/credit dans le code"""

CODER_PROMPT = """Tu es le CODER d'ORBIT v4 sur Windows PowerShell.

OUTILS: write_file, read_file, run_command, list_files, smart_search, find_function, start_server, take_screenshot, web_search (si Internet active)

REGLES:
- Separe HTML/CSS/JS en fichiers distincts
- PowerShell: utilise 'dir' pas 'ls', 'type' pas 'cat'
- Dark mode par defaut pour les UI
- Pas de signature/credit
- Si erreur -> analyse et corrige immediatement
- Pour les apps React/Node, utilise start_server pour le preview
- Quand tu corriges un bug difficile, utilise save_bug_fix pour sauvegarder la solution

FORMAT: [ACTION] description [EXECUTION] ce que tu fais [RESULTAT] resultat"""

REVIEWER_PROMPT = """Tu es le REVIEWER d'ORBIT v4. Tu verifies le code.

FORMAT:
[REVIEW] Fichiers verifies
[CHECKLIST] Points (OK ou X pour chaque)
[VERDICT] APPROUVE ou CORRECTIONS avec details

Si CORRECTIONS, sois specifique sur ce qu'il faut corriger.

NOUVEAUTE V4: Tu peux utiliser take_screenshot pour voir le rendu visuel et analyze_screenshot pour detecter les problemes d'interface."""

CHAT_PROMPT = """Tu es ORBIT v4, un assistant de developpement intelligent avec Vision et Acces Internet.
Tu reponds de maniere conversationnelle et utile.
Tu as acces au contexte du projet actuel.
Sois concis mais informatif. N'utilise pas les outils sauf si necessaire.
Si l'utilisateur parle d'un probleme visuel, propose d'utiliser le mode DEBUG_VISUAL."""

README_PROMPT = """Tu es un expert en documentation. Genere un README.md complet:

# Nom du Projet
## Description
## Installation
## Usage
## Structure
## Technologies

Base-toi sur l'analyse des fichiers du projet."""

DEBUG_VISUAL_PROMPT = """Tu es le DEBUGGER VISUEL d'ORBIT v4. Tu analyses les problemes d'interface.

WORKFLOW:
1. Prends un screenshot avec take_screenshot
2. Analyse le screenshot avec analyze_screenshot
3. Identifie les problemes visuels
4. Correle avec le code source
5. Propose et applique les corrections
6. Prends un nouveau screenshot de verification

OUTILS: take_screenshot, analyze_screenshot, read_file, write_file, smart_search

FORMAT:
[CAPTURE] Screenshot de l'URL
[ANALYSE_VISUELLE] Problemes detectes
[CORRELATION_CODE] Fichiers concernes
[FIX] Corrections appliquees
[VERIFICATION] Nouveau screenshot"""

# ═══════════════════════════════════════════════════════════════════════════════
# ORCHESTRATEUR AUTONOME (The Loop) - V4 avec Vision
# ═══════════════════════════════════════════════════════════════════════════════

class AgentOrchestrator:
    """Orchestrateur avec boucle d'autonomie (max 5 iterations) et Vision."""

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
        self.known_bugs_fixes: List[Dict] = []  # Memoire Self-Healing
        self.last_screenshot: Optional[Dict] = None  # Dernier screenshot pris

    def reset(self) -> None:
        self.conversation_boss = []
        self.conversation_coder = []
        self.conversation_reviewer = []
        self.created_files = []
        self.chat_history = []
        self.project_summary = ""
        self.loop_count = 0
        self.last_error = ""
        # Ne pas reset known_bugs_fixes pour garder la memoire
        self.last_screenshot = None

    def track_usage(self, response, agent: str) -> None:
        if hasattr(response, 'usage'):
            USAGE_STATS["total_input_tokens"] += response.usage.input_tokens
            USAGE_STATS["total_output_tokens"] += response.usage.output_tokens
            USAGE_STATS["calls"].append({
                "agent": agent,
                "in": response.usage.input_tokens,
                "out": response.usage.output_tokens
            })

    def call_agent(self, agent: str, messages: list, system_prompt: str, include_image: Dict = None):
        """Appelle un agent, avec support optionnel d'image pour Vision."""
        if not client:
            raise RuntimeError("Client Anthropic non initialise")

        compressed_messages = TokenOptimizer.compress_conversation(messages)
        model = CONFIG["models"].get(agent, CONFIG["models"]["coder"])

        # Si une image est fournie, l'ajouter au dernier message
        if include_image and compressed_messages:
            last_msg = compressed_messages[-1]
            if last_msg["role"] == "user":
                content = last_msg.get("content", "")
                if isinstance(content, str):
                    last_msg["content"] = [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": include_image["base64"]
                            }
                        },
                        {"type": "text", "text": content}
                    ]

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
                result = execute_tool(block.name, block.input, self)
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

                # Stocker le dernier screenshot
                if block.name == "take_screenshot" and result.get("success"):
                    self.last_screenshot = result

                # Tracker les erreurs
                if not result.get("success"):
                    self.last_error = result.get("error", "Erreur inconnue")

        if assistant_content:
            conversation.append({"role": "assistant", "content": assistant_content})
        return results

    # ═══════════════════════════════════════════════════════════════════════════════
    # SMART CONTEXT INJECTION - V5 Core Feature
    # ═══════════════════════════════════════════════════════════════════════════════

    def _gather_smart_context(self, user_message: str, intent: str, force_files: list = None) -> dict:
        """
        Pre-charge intelligemment les fichiers pertinents AVANT d'appeler l'IA.

        Args:
            user_message: La demande utilisateur
            intent: Le mode (DEV, README, DEBUG_VISUAL)
            force_files: Liste de fichiers a forcer (optionnel)

        Returns:
            dict avec 'context_string', 'files_loaded', 'structure'
        """
        MAX_FILES = 5
        MAX_CHARS_PER_FILE = 10000

        logger.info(f"[SMART_CONTEXT] Gathering context for intent={intent}")

        # ─────────────────────────────────────────────────────────────
        # ETAPE 1: Scan rapide de la structure
        # ─────────────────────────────────────────────────────────────
        structure = SmartSearch.get_file_structure()
        all_files = structure.get("structure", {}).get("files", [])
        tech_stack = structure.get("structure", {}).get("tech", [])
        project_name = os.path.basename(WORKSPACE_DIR)

        # ─────────────────────────────────────────────────────────────
        # ETAPE 2: Selection des fichiers pertinents
        # ─────────────────────────────────────────────────────────────
        relevant_files = []

        if force_files:
            # Mode force: utiliser les fichiers specifies
            for f in force_files:
                # Gerer les chemins relatifs et absolus
                if os.path.isabs(f):
                    filepath = f
                    filename = os.path.basename(f)
                else:
                    filepath = os.path.join(WORKSPACE_DIR, f)
                    filename = f

                if os.path.exists(filepath) and filename not in relevant_files:
                    relevant_files.append(filename)

            # Completer avec des fichiers auto-detectes si < MAX_FILES
            if len(relevant_files) < MAX_FILES and all_files:
                for f in all_files:
                    if f not in relevant_files and len(relevant_files) < MAX_FILES:
                        relevant_files.append(f)
        else:
            # Mode intelligent: appel API pour selection
            try:
                # Filtrer les fichiers non-pertinents
                code_extensions = {'.py', '.js', '.ts', '.jsx', '.tsx', '.html', '.css',
                                   '.scss', '.json', '.yaml', '.yml', '.md', '.vue', '.svelte'}
                filtered_files = [f for f in all_files
                                  if any(f.endswith(ext) for ext in code_extensions)][:50]

                if not filtered_files:
                    filtered_files = all_files[:30]

                files_list = "\n".join(f"- {f}" for f in filtered_files)

                # Prompt adapte selon l'intent
                intent_hints = {
                    "DEV": "modification de code, creation de fonctionnalites, correction de bugs",
                    "README": "documentation, description du projet, installation, usage",
                    "DEBUG_VISUAL": "problemes CSS, layout, styles, interface utilisateur"
                }
                hint = intent_hints.get(intent, "developpement general")

                response = client.messages.create(
                    model=CONFIG["models"]["classifier"],
                    max_tokens=200,
                    system=f"""Tu es un expert en analyse de code.
Pour une tache de type "{hint}", identifie les 3 a 5 fichiers les plus critiques a lire.

REGLES:
- Reponds UNIQUEMENT par un tableau JSON: ["fichier1.py", "fichier2.js"]
- Pas d'explication, pas de texte supplementaire
- Maximum 5 fichiers
- Priorise les fichiers principaux (app.py, index.js, main.py, etc.)""",
                    messages=[{
                        "role": "user",
                        "content": f"Demande: {user_message}\n\nFichiers disponibles:\n{files_list}"
                    }]
                )

                # Parser la reponse JSON
                response_text = response.content[0].text.strip()

                # Nettoyer (enlever markdown si present)
                if "```" in response_text:
                    parts = response_text.split("```")
                    for part in parts:
                        if part.strip().startswith("["):
                            response_text = part.strip()
                            break
                        elif part.strip().startswith("json"):
                            response_text = part.strip()[4:].strip()
                            break

                # Trouver le JSON dans la reponse
                start = response_text.find("[")
                end = response_text.rfind("]") + 1
                if start != -1 and end > start:
                    response_text = response_text[start:end]

                selected_files = json.loads(response_text)

                # Valider que les fichiers existent
                for f in selected_files:
                    if f in all_files and f not in relevant_files:
                        relevant_files.append(f)
                        if len(relevant_files) >= MAX_FILES:
                            break

                logger.info(f"[SMART_CONTEXT] IA a selectionne: {relevant_files}")

            except Exception as e:
                logger.warning(f"[SMART_CONTEXT] Erreur selection IA: {e}")
                # Fallback intelligent base sur l'intent
                fallback_map = {
                    "DEV": ['app.py', 'main.py', 'index.js', 'server.js', 'package.json'],
                    "README": ['package.json', 'requirements.txt', 'app.py', 'main.py', 'setup.py'],
                    "DEBUG_VISUAL": ['index.html', 'style.css', 'styles.css', 'app.css', 'index.js']
                }
                fallback = fallback_map.get(intent, ['app.py', 'main.py', 'index.js'])
                relevant_files = [f for f in fallback if f in all_files][:MAX_FILES]

        # ─────────────────────────────────────────────────────────────
        # ETAPE 3: Lecture Python des fichiers
        # ─────────────────────────────────────────────────────────────
        context_parts = []
        files_actually_loaded = []
        total_chars = 0

        for filename in relevant_files:
            filepath = os.path.join(WORKSPACE_DIR, filename)
            try:
                with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()

                # Tronquer si necessaire
                if len(content) > MAX_CHARS_PER_FILE:
                    content = content[:MAX_CHARS_PER_FILE] + f"\n... [TRONQUE - {len(content)} chars total]"

                context_parts.append(f"""
╔══════════════════════════════════════════════════════════════════╗
║ FICHIER: {filename}
╚══════════════════════════════════════════════════════════════════╝
{content}
""")
                files_actually_loaded.append(filename)
                total_chars += len(content)

            except Exception as e:
                logger.warning(f"[SMART_CONTEXT] Erreur lecture {filename}: {e}")

        # ─────────────────────────────────────────────────────────────
        # ETAPE 4: Formater le contexte final
        # ─────────────────────────────────────────────────────────────
        if context_parts:
            header = f"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                    SMART CONTEXT - PRE-CHARGE (ORBIT V5)                     ║
╠══════════════════════════════════════════════════════════════════════════════╣
║ Projet: {project_name:<63} ║
║ Fichiers charges: {len(files_actually_loaded)} ({total_chars:,} caracteres)                                  ║
║ Technologies: {', '.join(tech_stack[:5]) if tech_stack else 'Non detectees':<53} ║
╚══════════════════════════════════════════════════════════════════════════════╝

IMPORTANT: Ces fichiers sont PRE-CHARGES. Tu n'as PAS besoin d'utiliser read_file pour eux.
"""
            context_string = header + "\n".join(context_parts)
        else:
            context_string = ""

        return {
            "context_string": context_string,
            "files_loaded": files_actually_loaded,
            "structure": structure,
            "project_name": project_name,
            "tech_stack": tech_stack,
            "total_chars": total_chars
        }

    def run_agent_loop(self, agent: str, initial_message: str, system_prompt: str,
                       conversation: list, max_turns: int = 5, include_image: Dict = None) -> Generator:
        if not conversation or conversation[-1]["role"] != "user":
            conversation.append({"role": "user", "content": initial_message})

        for turn in range(max_turns):
            response = self.call_agent(agent, conversation, system_prompt, include_image if turn == 0 else None)
            tool_results = self.process_tool_calls(response, conversation)

            for block in response.content:
                if block.type == "text":
                    yield {"type": "agent_text", "agent": agent, "content": block.text}

            for tr in tool_results:
                yield {"type": "tool_result", "agent": agent, "tool": tr["tool"],
                       "success": tr["result"].get("success", False), "result": tr["result"]}

                # Si un screenshot a ete pris, l'envoyer au frontend
                if tr["tool"] == "take_screenshot" and tr["result"].get("success"):
                    yield {"type": "screenshot", "filename": tr["result"].get("filename"),
                           "base64": tr["result"].get("base64", "")[:100] + "..."}  # Tronque pour le log

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
    # MODE README - V5 avec Smart Context Injection
    # ───────────────────────────────────────────────────────────────────────

    def handle_readme(self, user_message: str) -> Generator:
        """Genere un README.md avec Smart Context - Idealement en 1 tour."""
        logger.info(f"[README] Generation documentation V5...")

        yield {"type": "phase", "phase": "README", "status": "Smart Context Loading"}

        # Fichiers racines critiques pour un README
        readme_force_files = [
            'package.json', 'requirements.txt', 'pyproject.toml', 'setup.py',
            'Cargo.toml', 'go.mod', 'pom.xml', 'build.gradle',
            'app.py', 'main.py', 'index.js', 'server.js', 'index.ts',
            'index.html', 'docker-compose.yml', 'Dockerfile', 'Makefile',
            '.env.example', 'config.json', 'settings.py'
        ]

        # Utiliser Smart Context avec fichiers forces
        smart_ctx = self._gather_smart_context(user_message, intent="README", force_files=readme_force_files)

        yield {"type": "smart_context_loaded",
               "files": smart_ctx["files_loaded"],
               "chars": smart_ctx["total_chars"]}

        yield {"type": "phase", "phase": "README", "status": "Generation (1 tour attendu)"}

        # PROMPT ULTRA-DIRECTIF pour action en 1 tour
        prompt = f"""════════════════════════════════════════════════════════════════════════════════
                         MISSION: CREER README.md
════════════════════════════════════════════════════════════════════════════════

PROJET: {smart_ctx["project_name"]}
TECHNOLOGIES: {', '.join(smart_ctx["tech_stack"]) if smart_ctx["tech_stack"] else 'A determiner depuis le code'}

{smart_ctx["context_string"]}

══════════════════════════════════════════════════════════════════════════════
                         INSTRUCTIONS CRITIQUES
══════════════════════════════════════════════════════════════════════════════

1. Tu as DEJA TOUT LE CONTEXTE ci-dessus. N'utilise PAS read_file.

2. UTILISE IMMEDIATEMENT l'outil write_file avec:
   - filename: "README.md"
   - content: Le README complet en Markdown

3. STRUCTURE OBLIGATOIRE du README:
   # {smart_ctx["project_name"]}

   ## Description
   [Ce que fait l'application - 2-3 phrases]

   ## Technologies
   [Liste des technos detectees]

   ## Installation
   ```bash
   [Commandes exactes d'installation]
   ```

   ## Usage
   ```bash
   [Comment lancer l'app]
   ```

   ## Structure du projet
   [Arborescence principale]

   ## Licence
   [MIT ou autre si detecte]

4. NE REPONDS PAS avec du texte. EXECUTE write_file MAINTENANT.

DEMANDE SUPPLEMENTAIRE DE L'UTILISATEUR: {user_message if user_message else "Aucune"}
"""

        self.conversation_coder = [{"role": "user", "content": prompt}]

        # Prompt systeme renforce pour forcer l'action
        readme_system_prompt = """Tu es un generateur de documentation ULTRA-EFFICACE.

REGLE ABSOLUE: Tu recois un contexte pre-charge. Tu dois IMMEDIATEMENT appeler write_file.
- PAS de read_file (le code est deja fourni)
- PAS de list_files (la structure est fournie)
- PAS de bavardage ("Je vais...", "Voici...")
- JUSTE l'appel a write_file avec le README complet

Un bon README = 1 seul appel a write_file. C'est tout."""

        files_generated = False
        readme_written = False

        # max_turns=10 par securite, mais devrait finir en 1
        for event in self.run_agent_loop("coder", prompt, readme_system_prompt,
                                         self.conversation_coder, max_turns=10):
            yield event

            if event.get("type") == "tool_result" and event.get("tool") == "write_file":
                if event.get("success"):
                    files_generated = True
                    # Verifier si c'est bien le README
                    result = event.get("result", {})
                    if "README" in str(result).upper() or "readme" in str(result).lower():
                        readme_written = True
                        # On peut sortir tot si le README est ecrit
                        break

        memory_manager.save(self)

        if files_generated or readme_written:
            if "README.md" not in self.created_files:
                self.created_files.append("README.md")
            yield {"type": "agent_text", "agent": "readme",
                   "content": f"\n README.md genere avec succes (Smart Context V5)"}
            yield {"type": "complete", "files": ["README.md"], "preview": None}
        else:
            yield {"type": "agent_text", "agent": "readme",
                   "content": "\n Echec: L'agent n'a pas utilise write_file. Verifiez les logs."}
            yield {"type": "complete", "files": [], "preview": None}

    # ───────────────────────────────────────────────────────────────────────
    # MODE DEBUG_VISUAL - V5 avec Smart Context pre-charge
    # ───────────────────────────────────────────────────────────────────────

    def handle_debug_visual(self, user_message: str, screenshot_base64: str = None, target_url: str = None) -> Generator:
        """Mode DEBUG_VISUAL V5: Smart Context + Screenshot -> Analyse -> Fix."""
        logger.info(f"[DEBUG_VISUAL] {user_message[:40]}...")

        yield {"type": "phase", "phase": "DEBUG_VISUAL", "status": "Initialisation V5"}

        # ─────────────────────────────────────────────────────────────
        # ETAPE 1: Pre-charger le contexte CSS/HTML AVANT le screenshot
        # ─────────────────────────────────────────────────────────────
        yield {"type": "phase", "phase": "DEBUG_VISUAL", "status": "Pre-chargement CSS/HTML"}

        # Fichiers visuels prioritaires
        visual_force_files = [
            'index.html', 'app.html', 'main.html',
            'style.css', 'styles.css', 'app.css', 'main.css', 'global.css',
            'index.css', 'theme.css', 'variables.css',
            'tailwind.config.js', 'postcss.config.js',
            'App.vue', 'App.jsx', 'App.tsx', 'App.svelte',
            'layout.tsx', 'layout.jsx', 'page.tsx', 'page.jsx'
        ]

        smart_ctx = self._gather_smart_context(user_message, intent="DEBUG_VISUAL", force_files=visual_force_files)

        if smart_ctx["files_loaded"]:
            yield {"type": "smart_context_loaded",
                   "files": smart_ctx["files_loaded"],
                   "chars": smart_ctx["total_chars"]}

        # ─────────────────────────────────────────────────────────────
        # ETAPE 2: Determiner l'URL cible
        # ─────────────────────────────────────────────────────────────
        if not target_url:
            servers = server_manager.list_servers()
            if servers:
                running = [s for s in servers if s.get("running")]
                if running:
                    target_url = f"http://localhost:{running[0]['port']}"
            if not target_url:
                target_url = "http://localhost:3000"

        # Consulter la memoire des bugs visuels
        bug_context = ""
        if self.known_bugs_fixes:
            similar = memory_manager.find_similar_bug(self, user_message)
            if similar:
                bug_context = f"""
════════════════════════════════════════════════════════════════════
 BUG SIMILAIRE DEJA RESOLU
════════════════════════════════════════════════════════════════════
Symptome: {similar['symptom'][:80]}...
Solution: {similar['solution'][:80]}...
"""
                yield {"type": "memory_hint", "bug": similar}

        # ─────────────────────────────────────────────────────────────
        # ETAPE 3: Construire le message avec contexte pre-charge
        # ─────────────────────────────────────────────────────────────
        yield {"type": "phase", "phase": "DEBUG_VISUAL", "status": "Analyse & Correction"}

        if screenshot_base64:
            # Screenshot manuel fourni
            debug_message = f"""════════════════════════════════════════════════════════════════════════════════
                    DEBUG VISUEL - SCREENSHOT MANUEL
════════════════════════════════════════════════════════════════════════════════

PROBLEME SIGNALE:
{user_message}
{bug_context}

{smart_ctx["context_string"]}

══════════════════════════════════════════════════════════════════════════════
                         INSTRUCTIONS
══════════════════════════════════════════════════════════════════════════════

1. Le screenshot est joint a ce message - ANALYSE-LE
2. Le code CSS/HTML est PRE-CHARGE ci-dessus - tu n'as PAS besoin de read_file
3. CORRELE le probleme visuel avec le code source
4. Utilise write_file pour appliquer la correction
5. Prends un nouveau screenshot pour verifier (si possible)

AGIS MAINTENANT - Le contexte est complet."""

            # Analyser le screenshot fourni
            analysis = vision_engine.analyze_screenshot(screenshot_base64, user_message)
            if analysis.get("success"):
                yield {"type": "agent_text", "agent": "debug_visual",
                       "content": f"[ANALYSE INITIALE]\n{analysis['analysis'][:500]}..."}
                debug_message += f"\n\n[PRE-ANALYSE DU SCREENSHOT]\n{analysis['analysis']}"

        else:
            # Pas de screenshot - l'agent devra en prendre un
            debug_message = f"""════════════════════════════════════════════════════════════════════════════════
                    DEBUG VISUEL - CAPTURE REQUISE
════════════════════════════════════════════════════════════════════════════════

PROBLEME SIGNALE:
{user_message}

URL CIBLE: {target_url}
{bug_context}

{smart_ctx["context_string"]}

══════════════════════════════════════════════════════════════════════════════
                         INSTRUCTIONS SEQUENTIELLES
══════════════════════════════════════════════════════════════════════════════

1. PRENDS un screenshot de {target_url} avec take_screenshot
2. ANALYSE le screenshot pour identifier le probleme visuel
3. Le code est PRE-CHARGE ci-dessus - CORRELE avec le screenshot
4. Utilise write_file pour appliquer la correction CSS/HTML
5. PRENDS un nouveau screenshot pour VERIFIER la correction

Le contexte code est deja charge - concentre-toi sur l'analyse visuelle."""

        self.conversation_coder = [{"role": "user", "content": debug_message}]

        # Lancer la boucle avec le screenshot si fourni
        for event in self.run_agent_loop("coder", debug_message, DEBUG_VISUAL_PROMPT,
                                         self.conversation_coder, max_turns=8,
                                         include_image={"base64": screenshot_base64} if screenshot_base64 else None):
            yield event

        # ─────────────────────────────────────────────────────────────
        # ETAPE 4: Verification finale
        # ─────────────────────────────────────────────────────────────
        yield {"type": "phase", "phase": "DEBUG_VISUAL", "status": "Verification finale"}

        if self.last_screenshot:
            verification_result = vision_engine.analyze_screenshot(
                self.last_screenshot.get("base64", ""),
                f"Verifie si le probleme '{user_message[:50]}' a ete resolu. Compare avant/apres."
            )
            if verification_result.get("success"):
                yield {"type": "agent_text", "agent": "debug_visual",
                       "content": f"\n[VERIFICATION]\n{verification_result['analysis']}"}

        # Sauvegarder le fix si succes
        if not self.last_error and self.created_files:
            memory_manager.add_bug_fix(self, f"[VISUAL] {user_message[:80]}",
                                       f"Fix via DEBUG_VISUAL V5 - Fichiers: {', '.join(self.created_files[-3:])}")

        memory_manager.save(self)

        html_files = [f for f in self.created_files if f.endswith('.html')]
        css_files = [f for f in self.created_files if f.endswith('.css')]
        preview_file = html_files[0] if html_files else None

        yield {"type": "complete",
               "files": self.created_files,
               "preview": preview_file,
               "screenshot": self.last_screenshot.get("filename") if self.last_screenshot else None,
               "css_modified": css_files}

    # ───────────────────────────────────────────────────────────────────────
    # MODE DEV - Boucle d'autonomie V5 avec Smart Context
    # ───────────────────────────────────────────────────────────────────────

    def orchestrate_dev(self, user_message: str) -> Generator:
        """Boucle d'autonomie V5: SMART_CONTEXT -> PLAN -> ACTION -> VERIFY (max 5 iterations)."""
        logger.info(f"[DEV] {user_message[:40]}...")

        self.loop_count = 0
        self.last_error = ""
        max_loops = Config.MAX_AUTONOMY_LOOPS

        # ═══════════════════════════════════════════════════════════════════════
        # PHASE 0: SMART CONTEXT INJECTION (V5)
        # ═══════════════════════════════════════════════════════════════════════
        yield {"type": "phase", "phase": "SMART_CONTEXT", "status": "Pre-chargement intelligent"}

        smart_ctx = self._gather_smart_context(user_message, intent="DEV")
        smart_context = smart_ctx["context_string"]

        if smart_ctx["files_loaded"]:
            logger.info(f"[SMART_CONTEXT] {len(smart_ctx['files_loaded'])} fichiers pre-charges ({smart_ctx['total_chars']:,} chars)")
            yield {"type": "smart_context_loaded",
                   "files": smart_ctx["files_loaded"],
                   "chars": smart_ctx["total_chars"]}

        # Consulter la memoire des bugs
        bug_context = ""
        if self.known_bugs_fixes:
            similar = memory_manager.find_similar_bug(self, user_message)
            if similar:
                bug_context = f"\n\n[MEMOIRE BUG] Probleme similaire deja resolu:\nSymptome: {similar['symptom']}\nSolution: {similar['solution']}"
                yield {"type": "memory_hint", "bug": similar}

        while self.loop_count < max_loops:
            self.loop_count += 1
            logger.info(f"=== BOUCLE AUTONOMIE {self.loop_count}/{max_loops} ===")

            yield {"type": "loop_start", "iteration": self.loop_count, "max": max_loops}

            # ─────────────────────────────────────────────────────────────
            # PHASE 1: PLAN (BOSS) - Avec Smart Context au Tour 1
            # ─────────────────────────────────────────────────────────────
            yield {"type": "phase", "phase": "BOSS", "status": f"Planning (Loop {self.loop_count})"}

            if self.loop_count == 1:
                # Premier tour: injecter le contexte complet
                boss_message = f"""DEMANDE UTILISATEUR:
{user_message}
{bug_context}

{smart_context}

INSTRUCTIONS POUR LE BOSS:
1. Le contexte ci-dessus contient deja le code des fichiers pertinents
2. Analyse-le pour creer un plan PRECIS
3. Le CODER recevra aussi ce contexte, il pourra agir des le Tour 1
4. Sois specifique: indique les fichiers a modifier et les changements exacts"""
            elif self.last_error:
                boss_message = f"""CORRECTION REQUISE (iteration {self.loop_count}):
Erreur precedente: {self.last_error}
Demande originale: {user_message}

Analyse l'erreur et propose une solution alternative."""
            else:
                boss_message = f"Continue la tache: {user_message}"

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
            # PHASE 2: ACTION (CODER) - Avec contexte transmis au Tour 1
            # ─────────────────────────────────────────────────────────────
            yield {"type": "phase", "phase": "CODER", "status": f"Coding (Loop {self.loop_count})"}

            if self.loop_count == 1 and smart_context:
                # Transmettre le contexte au coder pour action immediate
                coder_message = f"""INSTRUCTIONS DU BOSS:
{coder_instructions}

{smart_context}

ACTION IMMEDIATE REQUISE:
- Les fichiers sont deja charges ci-dessus
- N'utilise PAS read_file pour ces fichiers
- Utilise DIRECTEMENT write_file pour appliquer les modifications
- Agis maintenant, pas de questions"""
            else:
                coder_message = f"BOSS:\n{coder_instructions}"

            self.conversation_coder = [{"role": "user", "content": coder_message}]
            self.last_error = ""

            coder_had_error = False
            for event in self.run_agent_loop("coder", coder_message, CODER_PROMPT, self.conversation_coder, max_turns=6):
                yield event
                if event.get("type") == "tool_result" and not event.get("success", True):
                    coder_had_error = True

            # ─────────────────────────────────────────────────────────────
            # PHASE 3: VERIFY (REVIEWER)
            # ─────────────────────────────────────────────────────────────
            yield {"type": "phase", "phase": "REVIEWER", "status": f"Reviewing (Loop {self.loop_count})"}

            files_str = ", ".join(self.created_files[-5:]) if self.created_files else "aucun fichier"
            review_message = f"Verifie les fichiers crees/modifies: {files_str}"

            if self.last_error:
                review_message += f"\nErreur detectee: {self.last_error}"

            self.conversation_reviewer = [{"role": "user", "content": review_message}]

            reviewer_text = ""
            for event in self.run_agent_loop("reviewer", review_message, REVIEWER_PROMPT, self.conversation_reviewer, max_turns=2):
                yield event
                if event.get("type") == "agent_text":
                    reviewer_text += event.get("content", "")

            # ─────────────────────────────────────────────────────────────
            # PHASE 4: DECISION
            # ─────────────────────────────────────────────────────────────
            verdict_approved = "APPROUVE" in reviewer_text.upper() or "APPROVED" in reviewer_text.upper()
            has_critical_error = coder_had_error or (self.last_error and "error" in self.last_error.lower())

            if verdict_approved and not has_critical_error:
                # SUCCES
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
                if self.loop_count < max_loops:
                    yield {"type": "loop_end", "iteration": self.loop_count, "status": "RETRY",
                           "reason": self.last_error or "Review non approuve"}
                    if "CORRECTION" in reviewer_text.upper():
                        correction_part = reviewer_text.split("CORRECTION")[-1][:200]
                        self.last_error = f"Review: {correction_part}"
                else:
                    yield {"type": "loop_end", "iteration": self.loop_count, "status": "MAX_REACHED"}

        memory_manager.save(self)

        html_files = [f for f in self.created_files if f.endswith('.html')]
        preview_file = html_files[0] if html_files else None

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

    def orchestrate(self, user_message: str, screenshot_base64: str = None) -> Generator:
        """Point d'entree principal avec classification d'intention."""

        # ETAPE 1: Classifier l'intention
        intent = IntentClassifier.classify(user_message)

        # Si un screenshot est fourni, forcer DEBUG_VISUAL
        if screenshot_base64:
            intent = "DEBUG_VISUAL"

        logger.info(f"[INTENT] {intent} -> {user_message[:30]}...")

        yield {"type": "intent", "intent": intent}

        # ETAPE 2: Router vers le bon handler
        if intent == "CHAT":
            yield from self.handle_chat(user_message)
        elif intent == "README":
            yield from self.handle_readme(user_message)
        elif intent == "DEBUG_VISUAL":
            yield from self.handle_debug_visual(user_message, screenshot_base64)
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

@app.route('/screenshot/<path:filename>')
def serve_screenshot(filename):
    """Sert les screenshots depuis le dossier screenshots."""
    screenshot_dir = os.path.join(WORKSPACE_DIR, Config.SCREENSHOT_DIR)
    return send_from_directory(screenshot_dir, filename)

@app.route('/chat', methods=['POST'])
def chat():
    user_message = request.json.get('message', '')
    screenshot_base64 = request.json.get('screenshot')  # Screenshot manuel optionnel

    if not user_message and not screenshot_base64:
        return jsonify({"error": "Message ou screenshot requis"}), 400

    def generate():
        for event in orchestrator.orchestrate(user_message, screenshot_base64):
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
        if 'internet_enabled' in data:
            CONFIG['internet_enabled'] = data['internet_enabled']
            logger.info(f"Internet toggle: {'ON' if data['internet_enabled'] else 'OFF'}")
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
        "version": "4.0",
        "features": ["vision", "internet", "self_healing"],
        "git": SystemHealth.git_available,
        "gh": SystemHealth.gh_available,
        "playwright": SystemHealth.playwright_available,
        "duckduckgo": SystemHealth.duckduckgo_available,
        "workspace": WORKSPACE_DIR,
        "model": Config.DEFAULT_MODEL,
        "internet_enabled": CONFIG.get("internet_enabled", False),
        "servers": server_manager.list_servers(),
        "known_bugs_count": len(orchestrator.known_bugs_fixes)
    })

# ═══════════════════════════════════════════════════════════════════════════════
# ROUTES VISION V4
# ═══════════════════════════════════════════════════════════════════════════════

@app.route('/vision/screenshot', methods=['POST'])
def take_screenshot_route():
    """Prend un screenshot d'une URL."""
    data = request.json or {}
    url = data.get('url', 'http://localhost:3000')
    full_page = data.get('full_page', False)

    result = vision_engine.take_screenshot(url, full_page=full_page)

    if result.get("success"):
        # Ne pas renvoyer le base64 complet dans la reponse API
        return jsonify({
            "success": True,
            "filename": result.get("filename"),
            "url": result.get("url"),
            "size": result.get("size")
        })
    return jsonify(result)

@app.route('/vision/analyze', methods=['POST'])
def analyze_screenshot_route():
    """Analyse un screenshot avec Vision API."""
    data = request.json or {}
    image_base64 = data.get('image_base64')
    prompt = data.get('prompt')

    if not image_base64:
        return jsonify({"success": False, "error": "image_base64 requis"})

    result = vision_engine.analyze_screenshot(image_base64, prompt)
    return jsonify(result)

# ═══════════════════════════════════════════════════════════════════════════════
# ROUTES INTERNET V4
# ═══════════════════════════════════════════════════════════════════════════════

@app.route('/internet/search', methods=['POST'])
def web_search_route():
    """Recherche web via DuckDuckGo."""
    data = request.json or {}
    query = data.get('query')
    max_results = data.get('max_results', 5)

    if not query:
        return jsonify({"success": False, "error": "query requis"})

    result = internet_engine.web_search(query, max_results)
    return jsonify(result)

@app.route('/internet/read', methods=['POST'])
def read_webpage_route():
    """Lit une page web."""
    data = request.json or {}
    url = data.get('url')
    max_chars = data.get('max_chars', 5000)

    if not url:
        return jsonify({"success": False, "error": "url requis"})

    result = internet_engine.read_webpage(url, max_chars)
    return jsonify(result)

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
            f.write(f"# {name}\n\nProjet cree avec ORBIT v4.\n")

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
# ROUTES MEMOIRE SELF-HEALING
# ═══════════════════════════════════════════════════════════════════════════════

@app.route('/memory/bugs')
def list_known_bugs():
    """Liste les bugs connus et leurs solutions."""
    return jsonify({
        "success": True,
        "bugs": orchestrator.known_bugs_fixes,
        "count": len(orchestrator.known_bugs_fixes)
    })

@app.route('/memory/bugs/add', methods=['POST'])
def add_bug_fix():
    """Ajoute manuellement un bug fix a la memoire."""
    data = request.json or {}
    symptom = data.get('symptom', '').strip()
    solution = data.get('solution', '').strip()

    if not symptom or not solution:
        return jsonify({"success": False, "error": "symptom et solution requis"})

    success = memory_manager.add_bug_fix(orchestrator, symptom, solution)
    return jsonify({"success": success})

@app.route('/memory/bugs/search', methods=['POST'])
def search_bug():
    """Cherche un bug similaire dans la memoire."""
    data = request.json or {}
    symptom = data.get('symptom', '').strip()

    if not symptom:
        return jsonify({"success": False, "error": "symptom requis"})

    result = memory_manager.find_similar_bug(orchestrator, symptom)
    return jsonify({
        "success": True,
        "found": result is not None,
        "bug": result
    })

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
    print("\n" + "=" * 60)
    print("  ORBIT v4.0 - Vision & Network Edition")
    print("  -> http://127.0.0.1:5000")
    print("-" * 60)
    print(f"  Projets: {Config.PROJECTS_ROOT}")
    print(f"  Modele: {Config.DEFAULT_MODEL}")
    print(f"  Git: {'OK' if SystemHealth.git_available else 'X'}")
    print(f"  GitHub: {'OK' if SystemHealth.gh_available else 'X (optionnel)'}")
    print(f"  Playwright (Vision): {'OK' if SystemHealth.playwright_available else 'X (pip install playwright)'}")
    print(f"  DuckDuckGo (Internet): {'OK' if SystemHealth.duckduckgo_available else 'X (pip install duckduckgo-search)'}")
    print(f"  Max tokens: {Config.MAX_TOKENS}")
    print(f"  Boucles autonomie: {Config.MAX_AUTONOMY_LOOPS}")
    print(f"  Bugs connus: {len(orchestrator.known_bugs_fixes)}")
    print("=" * 60)
    print("  Modes: [CHAT] [DEV] [README] [DEBUG_VISUAL]")
    print("=" * 60 + "\n")

    app.run(debug=True, port=5000, threaded=True)
