"""
ANTIGRAVITY STUDIO v3 - Multi-Agent Orchestrator
Architecture: BOSS (Planning) → CODER (Execution) → REVIEWER (Validation)
"""

import os
import json
import subprocess
import time
from datetime import datetime
from flask import Flask, render_template, request, jsonify, send_from_directory, Response
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

WORKSPACE_DIR = os.getcwd()

# ═══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

CONFIG = {
    "models": {
        "boss": "claude-sonnet-4-5-20250929",      # Orchestrator - can upgrade to opus
        "coder": "claude-sonnet-4-5-20250929",     # Fast coder
        "reviewer": "claude-sonnet-4-5-20250929"   # Reviewer
    },
    "autopilot": True,   # Auto-confirm without user input
    "max_iterations": 15,
    "max_retries": 3
}

# Usage tracking
USAGE_STATS = {
    "total_input_tokens": 0,
    "total_output_tokens": 0,
    "calls": []
}

# ═══════════════════════════════════════════════════════════════════════════════
# TOOLS DEFINITION
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
        "description": "Crée ou modifie un fichier. Crée les dossiers parents si nécessaire.",
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
        "description": "Exécute une commande PowerShell. Retourne stdout/stderr.",
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
        "description": "Liste les fichiers d'un répertoire.",
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
        "description": "Affiche les différences des fichiers modifiés.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    }
]

# ═══════════════════════════════════════════════════════════════════════════════
# TOOL EXECUTION ENGINE
# ═══════════════════════════════════════════════════════════════════════════════

def execute_tool(name: str, args: dict) -> dict:
    """Execute a tool and return structured result."""
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
            return {"success": True, "message": f"Fichier cree: {args['filename']}", "filename": args["filename"]}

        elif name == "run_command":
            result = subprocess.run(
                ["powershell", "-Command", args["command"]],
                capture_output=True, text=True, cwd=WORKSPACE_DIR, timeout=60
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
                return {"success": False, "error": f"Dossier non trouve: {path}"}
            items = []
            for item in os.listdir(path):
                if not item.startswith('.') and item not in ['__pycache__', 'venv', 'node_modules']:
                    full = os.path.join(path, item)
                    items.append({"name": item, "type": "dir" if os.path.isdir(full) else "file"})
            return {"success": True, "items": items}

        elif name == "git_commit":
            subprocess.run(["powershell", "-Command", "git add -A"], cwd=WORKSPACE_DIR, capture_output=True)
            result = subprocess.run(
                ["powershell", "-Command", f'git commit -m "{args["message"]}"'],
                capture_output=True, text=True, cwd=WORKSPACE_DIR
            )
            if result.returncode == 0 or "nothing to commit" in (result.stdout + result.stderr).lower():
                return {"success": True, "message": f"Commit: {args['message']}"}
            return {"success": False, "error": result.stderr or result.stdout}

        elif name == "git_push":
            result = subprocess.run(
                ["powershell", "-Command", "git push"],
                capture_output=True, text=True, cwd=WORKSPACE_DIR
            )
            return {"success": result.returncode == 0, "output": result.stdout or result.stderr}

        elif name == "git_diff":
            result = subprocess.run(
                ["powershell", "-Command", "git diff --stat"],
                capture_output=True, text=True, cwd=WORKSPACE_DIR
            )
            return {"success": True, "diff": result.stdout[:3000] if result.stdout else "Aucun changement"}

        return {"success": False, "error": f"Outil inconnu: {name}"}

    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Timeout (>60s)"}
    except Exception as e:
        return {"success": False, "error": str(e)}

# ═══════════════════════════════════════════════════════════════════════════════
# AGENT SYSTEM PROMPTS
# ═══════════════════════════════════════════════════════════════════════════════

BOSS_PROMPT = """Tu es le BOSS de l'equipe ANTIGRAVITY STUDIO.

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
- Si une erreur persiste apres 3 tentatives, arrete et explique"""

CODER_PROMPT = """Tu es le CODER de l'equipe ANTIGRAVITY STUDIO sur Windows.

## TON ROLE
- Ecrire du code propre et fonctionnel
- Executer les commandes systeme
- Creer/modifier les fichiers selon les instructions du BOSS

## TES OUTILS
- write_file: Creer/modifier des fichiers
- read_file: Lire des fichiers existants
- run_command: Executer des commandes PowerShell
- list_files: Lister le contenu d'un dossier

## REGLES STRICTES
1. HTML/CSS/JS: Mets TOUT dans un seul fichier HTML (CSS et JS inline)
2. PowerShell: Utilise 'dir' au lieu de 'ls', 'type' au lieu de 'cat'
3. Erreurs: Si une commande echoue, analyse l'erreur et corrige SANS demander
4. Fichiers: Cree les fichiers complets, pas de placeholders
5. Design: Creer des interfaces MODERNES et BELLES (dark mode, animations)

## FORMAT DE REPONSE
[ACTION]
Ce que tu vas faire

[EXECUTION]
(utilise les outils)

[RESULTAT]
Resume de ce qui a ete fait"""

REVIEWER_PROMPT = """Tu es le REVIEWER de l'equipe ANTIGRAVITY STUDIO.

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
# MULTI-AGENT ORCHESTRATOR
# ═══════════════════════════════════════════════════════════════════════════════

class AgentOrchestrator:
    def __init__(self):
        self.conversation_boss = []
        self.conversation_coder = []
        self.conversation_reviewer = []
        self.created_files = []
        self.current_agent = "boss"
        
    def reset(self):
        self.conversation_boss = []
        self.conversation_coder = []
        self.conversation_reviewer = []
        self.created_files = []
        self.current_agent = "boss"
    
    def track_usage(self, response, agent: str):
        """Track API usage."""
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
        """Call a specific agent."""
        model = CONFIG["models"].get(agent, CONFIG["models"]["coder"])
        
        response = client.messages.create(
            model=model,
            max_tokens=8192,
            system=system_prompt,
            messages=messages,
            tools=TOOLS
        )
        
        self.track_usage(response, agent)
        return response
    
    def process_tool_calls(self, response, conversation: list):
        """Process tool calls and return results."""
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
                
                # Track created files
                if block.name == "write_file" and result.get("success"):
                    filename = block.input.get("filename", "")
                    if filename not in self.created_files:
                        self.created_files.append(filename)
        
        if assistant_content:
            conversation.append({"role": "assistant", "content": assistant_content})
        
        return results
    
    def run_agent_loop(self, agent: str, initial_message: str, system_prompt: str, conversation: list, max_turns: int = 5):
        """Run an agent until it completes or reaches max turns."""
        if not conversation or conversation[-1]["role"] != "user":
            conversation.append({"role": "user", "content": initial_message})
        
        for turn in range(max_turns):
            response = self.call_agent(agent, conversation, system_prompt)
            tool_results = self.process_tool_calls(response, conversation)
            
            # Yield agent output
            for block in response.content:
                if block.type == "text":
                    yield {"type": "agent_text", "agent": agent, "content": block.text}
            
            # Yield tool results
            for tr in tool_results:
                yield {"type": "tool_result", "agent": agent, "tool": tr["tool"], 
                       "success": tr["result"].get("success", False), "result": tr["result"]}
            
            # If tool calls were made, send results back
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
                # No tool calls = agent is done
                break
        
        yield {"type": "agent_complete", "agent": agent}

    def orchestrate(self, user_message: str):
        """Main orchestration flow: BOSS -> CODER -> REVIEWER -> BOSS (commit)"""
        
        # ═══════════════════════════════════════════════════════
        # PHASE 1: BOSS - Planning
        # ═══════════════════════════════════════════════════════
        yield {"type": "phase", "phase": "BOSS", "status": "Planning"}
        
        self.conversation_boss.append({"role": "user", "content": user_message})
        
        response = self.call_agent("boss", self.conversation_boss, BOSS_PROMPT)
        
        boss_text = ""
        for block in response.content:
            if block.type == "text":
                boss_text = block.text
                yield {"type": "agent_text", "agent": "boss", "content": block.text}
        
        self.conversation_boss.append({"role": "assistant", "content": response.content})
        
        # Extract CODER instructions
        coder_instructions = boss_text
        if "[INSTRUCTION_CODER]" in boss_text:
            coder_instructions = boss_text.split("[INSTRUCTION_CODER]")[-1].strip()
        
        # ═══════════════════════════════════════════════════════
        # PHASE 2: CODER - Execution
        # ═══════════════════════════════════════════════════════
        yield {"type": "phase", "phase": "CODER", "status": "Coding"}
        
        self.conversation_coder = [{"role": "user", "content": f"Instructions du BOSS:\n{coder_instructions}"}]
        
        for event in self.run_agent_loop("coder", coder_instructions, CODER_PROMPT, self.conversation_coder, max_turns=8):
            yield event
        
        # ═══════════════════════════════════════════════════════
        # PHASE 3: REVIEWER - Validation
        # ═══════════════════════════════════════════════════════
        yield {"type": "phase", "phase": "REVIEWER", "status": "Reviewing"}
        
        files_to_review = ", ".join(self.created_files) if self.created_files else "les fichiers modifies"
        review_request = f"Verifie le travail du CODER sur: {files_to_review}"
        
        self.conversation_reviewer = [{"role": "user", "content": review_request}]
        
        reviewer_verdict = "APPROUVE"
        for event in self.run_agent_loop("reviewer", review_request, REVIEWER_PROMPT, self.conversation_reviewer, max_turns=3):
            yield event
            if event.get("type") == "agent_text" and "CORRECTIONS_REQUISES" in event.get("content", ""):
                reviewer_verdict = "CORRECTIONS_REQUISES"
        
        # ═══════════════════════════════════════════════════════
        # PHASE 4: BOSS - Commit (if approved)
        # ═══════════════════════════════════════════════════════
        if reviewer_verdict == "APPROUVE" or CONFIG["autopilot"]:
            yield {"type": "phase", "phase": "GIT", "status": "Committing"}
            
            commit_msg = f"feat: {user_message[:50]}"
            result = execute_tool("git_commit", {"message": commit_msg})
            
            yield {"type": "tool_result", "agent": "boss", "tool": "git_commit", 
                   "success": result.get("success", False), "result": result}
        
        # ═══════════════════════════════════════════════════════
        # COMPLETE
        # ═══════════════════════════════════════════════════════
        html_files = [f for f in self.created_files if f.endswith(('.html', '.htm'))]
        yield {
            "type": "complete",
            "files": self.created_files,
            "preview": html_files[0] if html_files else None
        }

# Global orchestrator instance
orchestrator = AgentOrchestrator()

# ═══════════════════════════════════════════════════════════════════════════════
# FLASK ROUTES
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
    return jsonify({"success": True})

@app.route('/config', methods=['GET', 'POST'])
def config():
    if request.method == 'POST':
        data = request.json
        if 'autopilot' in data:
            CONFIG['autopilot'] = data['autopilot']
        if 'model' in data and data['model'] in ['opus', 'sonnet']:
            model_name = "claude-opus-4-20250514" if data['model'] == 'opus' else "claude-sonnet-4-5-20250929"
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

# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    print("\n" + "=" * 60)
    print("  ANTIGRAVITY STUDIO v3 - Multi-Agent System")
    print("  -> http://127.0.0.1:5000")
    print("  Agents: BOSS | CODER | REVIEWER")
    print("=" * 60 + "\n")
    app.run(debug=True, port=5000, threaded=True)