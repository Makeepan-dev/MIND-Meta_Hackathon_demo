import os
import sys

# Ensure UTF-8 output streams on Windows to prevent UnicodeEncodeError on emoji logs
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Suppress remote GitHub cost-map network fetches in LiteLLM
os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"
import time
from litellm import completion
from dotenv import load_dotenv
from colorama import Fore
from modules.memory_agent import MemoryAgent
import requests
import psutil

# MONITORING CONSTANTS
VRAM_THRESHOLD = 85 # Unload if GPU VRAM > 85%

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(_REPO_ROOT, ".env"), override=False)
load_dotenv(override=False)
os.environ["TIKTOKEN_CACHE_DIR"] = os.path.join(_REPO_ROOT, "cache")

class DynamicModelLoader:
    """Manages VRAM usage by unloading Ollama models."""
    @staticmethod
    def check_gpu_pressure():
        # TODO: Use nvml for real GPU stats. For now, use RAM as proxy or heuristic.
        # If RAM > 90%, assume high pressure
        mem = psutil.virtual_memory().percent
        return mem > VRAM_THRESHOLD

    @staticmethod
    def unload_model(model_name):
        """Forces Ollama to unload a model from VRAM."""
        try:
            # Ollama API: Generate with keep_alive=0 unloads it
            requests.post("http://localhost:11434/api/generate", json={
                "model": model_name,
                "keep_alive": 0
            })
            print(f"{Fore.YELLOW}📉 [BRAIN] Unloaded {model_name} to free VRAM.")
        except:
            pass

from modules.meta_reasoning import MetaLogEntry
import json
import re

class MindBrain:
    def __init__(self):
        self.loader = DynamicModelLoader()
        # Initialize Memory
        self.memory = MemoryAgent()
        self.locked_role = None # Locked Persona State
        
        # Load Long-Term Context (Last 10 messages from DB)
        self.history = self.memory.get_recent_context(limit=10)
        self.max_history = 10

        print(f"{Fore.GREEN}🧠 [BRAIN] Restored {len(self.history)} memories.")
        
        # --- THE BRAINS OF MIND (Migrated to Official Meta AI Model API + Local Ollama Fallbacks) ---
        from multi_brain.providers.meta_provider import (
            MetaModelClient,
            get_meta_api_base,
            get_meta_api_key,
        )
        meta_api_key = get_meta_api_key()
        meta_api_base = get_meta_api_base()
        meta_llama_model = os.getenv("OLLAMA_META_MODEL", "llama3.2:1b")
        self.brains = {
            "THEORIST": {
                "name": f"THEORIST (Meta Llama {meta_llama_model} Local)",
                "model": f"ollama/{meta_llama_model}",
                "provider": "ollama",
                "api_key": "local",
                "desc": "Meta Llama Local Reasoning, Offline Private Intelligence"
            },
            "MINISTRAL": {
                "name": "MINISTRAL (Ollama Local)",
                "model": "ollama/ministral",
                "provider": "ollama",
                "api_key": "local",
                "desc": "Efficient, Fast Local Offline Reasoning"
            },
            "CODER": {
                "name": "CODER (Meta muse-spark-1.3)",
                "model": "muse-spark-1.3",
                "provider": "meta",
                "api_key": meta_api_key,
                "api_base": meta_api_base,
                "desc": "Meta Flagship 1M-Context Coding, Debugging, and Tool Use"
            },
            "VISION": {
                "name": "VISION (Meta muse-spark-1.3 Multimodal)",
                "model": "muse-spark-1.3",
                "provider": "meta",
                "api_key": meta_api_key,
                "api_base": meta_api_base,
                "desc": "Meta Multimodal Visual Grounding and UI Interaction"
            },
            "MANAGER": {
                "name": "MANAGER (Meta muse-spark-1.1)",
                "model": "muse-spark-1.1",
                "provider": "meta",
                "api_key": meta_api_key,
                "api_base": meta_api_base,
                "desc": "Meta Fast Routing, Intent Classification, and Orchestration"
            },
            "ANALYST": {
                "name": "ANALYST (Meta muse-spark-1.2)",
                "model": "muse-spark-1.2",
                "provider": "meta",
                "api_key": meta_api_key,
                "api_base": meta_api_base,
                "desc": "Meta Quantitative Data Analysis, Math, and Investigation"
            },
            "SECURITY": {
                "name": "SECURITY (Meta muse-spark-1.2)",
                "model": "muse-spark-1.2",
                "provider": "meta",
                "api_key": meta_api_key,
                "api_base": meta_api_base,
                "desc": "Meta Defensive Security, Safety, and Vulnerability Auditing"
            },
            "CREATIVE": {
                "name": "CREATIVE (Meta muse-wonder-1.0)",
                "model": "muse-wonder-1.0",
                "provider": "meta",
                "api_key": meta_api_key,
                "api_base": meta_api_base,
                "desc": "Meta Frontier Creativity, Visual Direction, and Writing"
            },
            "GLM": {
                "name": "GLM (Meta muse-wonder-1.0 Synthesis)",
                "model": "muse-wonder-1.0",
                "provider": "meta",
                "api_key": meta_api_key,
                "api_base": meta_api_base,
                "desc": "Meta Frontier Dialectical Synthesis and Conflict Resolution"
            },
            "DEEPSEEK": {
                "name": "DEEPSEEK (Meta muse-wonder-1.0 Reasoning)",
                "model": "muse-wonder-1.0",
                "provider": "meta",
                "api_key": meta_api_key,
                "api_base": meta_api_base,
                "desc": "Meta Frontier Multi-Step Reasoning, Proofs, and Logic"
            },
            "CEREBRAS": {
                "name": "SPEED (Meta muse-spark-1.1)",
                "model": "muse-spark-1.1",
                "provider": "meta",
                "api_key": meta_api_key,
                "api_base": meta_api_base,
                "desc": "Meta Low-Latency Fast Inference"
            },
            "OSS_LLM": {
                "name": "OSS_LLM (Meta muse-spark-1.2)",
                "model": "muse-spark-1.2",
                "provider": "meta",
                "api_key": meta_api_key,
                "api_base": meta_api_base,
                "desc": "Meta General Knowledge and Analytical Synthesis"
            }
        }
        
        self.log_brain_status() # List brains on init

    def log_brain_status(self):
        print(f"\n{Fore.CYAN}--- ACTIVE NEURAL CENTERS (BRAINS) ---")
        print(f"{Fore.CYAN}{'ID':<12} | {'MODEL':<30} | {'ROLE'}")
        print(f"{Fore.CYAN}{'-'*70}")
        for key, info in self.brains.items():
            print(f"{Fore.CYAN}{key:<12} | {info['name'][:30]:<30} | {info['desc']}")
        print(f"{Fore.CYAN}{'-'*70}\n")

    def add_to_history(self, role, content):
        # 1. Save to DB (Persistent)
        self.memory.save_message(role, content)
        
        # 2. Update RAM (Short-Term)
        self.history.append({"role": role, "content": content})
        if len(self.history) > self.max_history:
            self.history.pop(0)

    def _determine_brain(self, text):
        """Routes the input to the correct brain."""
        text = text.lower()
        
        # 0. Direct Triggers - Specific Models First
        if "ministral" in text or "mistral" in text:
            return "MINISTRAL"
            
        if "glm" in text or "mind 4.7" in text or "advanced" in text or "conflict" in text or "mediate" in text or "dispute" in text:
            return "GLM"
        
        if "deepseek" in text or "r1" in text or "reason" in text or "solve" in text or "problem" in text or "logic" in text or "puzzle" in text or "why" in text or "how" in text:
            return "DEEPSEEK"
            
        if "fast" in text or "speed" in text or "cerebras" in text or "quick" in text:
            return "CEREBRAS"
            
        if "oss" in text or "open source" in text or "120b" in text:
            return "OSS_LLM"

        # 0.5. Ministral Triggers (Phrases)
        if any(w in text for w in ["quick check", "fast logic"]):
            return "MINISTRAL"

        # 1. THEORIST (Study / Theory)
        if any(w in text for w in ["theory", "study", "explain concept", "what is the meaning of", "academic", "thesis"]):
            return "THEORIST"
            
        # 2. CODER (Dev) - High Priority
        if any(w in text for w in ["code", "python", "script", "debug", "function", "class", "error", "exception", "java", "kotlin"]):
            return "CODER"
            
        # 3. SECURITY (Hacking / OSINT)
        if any(w in text for w in ["hack", "hunt", "osint", "exploit", "vulnerab", "ip address", "trace", "security"]):
            return "SECURITY"
            
        # 4. ANALYST (Data / Math)
        if any(w in text for w in ["analyze", "data", "plot", "graph", "chart", "calculate", "math", "average", "stats"]):
            return "ANALYST"
            
        # 5. CREATIVE (Writing)
        if any(w in text for w in ["write a story", "poem", "joke", "creative", "brainstorm"]):
            return "CREATIVE"
            
        # Default -> MANAGER for speed
        return "MANAGER"

    def _call_ollama_direct(self, model: str, prompt: str, system_prompt: str, temperature: float = 0.7) -> str:
        """Invokes local Ollama API directly with zero-overhead and strict error reporting."""
        url = "http://localhost:11434/api/generate"
        clean_model = model.replace("ollama/", "")
        payload = {
            "model": clean_model,
            "system": system_prompt,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": temperature}
        }
        try:
            r = requests.post(url, json=payload, timeout=35.0)
            if r.status_code == 200:
                reply = r.json().get("response", "").strip()
                if not reply:
                    return "Command processed with empty response from local model."
                self.add_to_history("assistant", reply)
                return reply
            elif r.status_code == 404:
                raise RuntimeError(f"Ollama model '{clean_model}' is not installed at http://localhost:11434. Please run 'ollama pull {clean_model}'.")
            else:
                raise RuntimeError(f"Ollama error (HTTP {r.status_code}): {r.text[:150]}")
        except requests.exceptions.ConnectionError:
            raise ConnectionError("Ollama service is offline or unreachable at http://localhost:11434. Please start Ollama.")
        except requests.exceptions.Timeout:
            raise TimeoutError(f"Ollama request for model '{clean_model}' timed out after 35s.")

    def query_specific_brain(self, brain_key: str, user_input: str, system_role: str = None, temperature: float = 0.7) -> str:
        """
        Queries a specific brain persona directly without auto-routing.
        Enforces authentic provider attribution and prevents silent provider substitution.
        """
        if brain_key not in self.brains:
            raise ValueError(f"Brain '{brain_key}' not found in registered brains: {list(self.brains.keys())}")

        target_brain = self.brains[brain_key]
        model_name = target_brain["model"]
        api_key = target_brain.get("api_key")

        # Save prompt to user history
        self.add_to_history("user", user_input)

        # Build prompt messages
        default_system = target_brain.get("desc", "You are MIND.")
        sys_prompt = system_role or f"You are MIND's {brain_key} brain ({target_brain.get('name')}). {default_system} Always address the user as 'Sir'."

        # 1. Direct Local Ollama Execution
        if "ollama" in model_name or api_key == "local":
            return self._call_ollama_direct(model_name, user_input, sys_prompt, temperature)

        # 2. Cloud Execution via Meta Model API (or LiteLLM fallback)
        if not api_key or api_key.startswith("your_"):
            raise ValueError(f"API key for brain '{brain_key}' ({model_name}) is not configured.")

        messages = [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_input}
        ]
        if target_brain.get("provider") == "meta":
            from multi_brain.providers.meta_provider import MetaModelClient
            client = MetaModelClient.get_instance()
            res = client.chat_completion(
                messages=messages,
                model=model_name,
                agent_id=brain_key,
                temperature=temperature,
                allow_model_fallback=False,
            )
            reply = (res.get("content") or "").strip()
            self.add_to_history("assistant", reply)
            return reply

        base_url = target_brain.get("api_base")
        resp = completion(
            model=model_name,
            messages=messages,
            api_key=api_key if api_key != "local" else None,
            temperature=temperature,
            api_base=base_url
        )
        reply = resp.choices[0].message.content.strip()
        self.add_to_history("assistant", reply)
        return reply

    def think(self, user_input, system_role="You are MIND, a loyal and efficient AI. Always address the user as 'Sir'.", temperature=0.7):
        """Wrapped to return just the text for backward compatibility."""
        meta_log = self.think_with_meta(user_input, system_role, temperature)
        return meta_log.final_response

    def think_multi_brain(self, user_input):
        """Routes through the Modular Multi-Brain Architecture."""
        try:
            from multi_brain.adapter import MultiBrainAdapter
            return MultiBrainAdapter.get_instance().process(user_input)
        except Exception as e:
            return f"Multi-Brain processing error: {e}"

    def orchestrate(self, user_input):
        """Full multi-brain orchestration returning structured results and evidence."""
        from multi_brain.adapter import MultiBrainAdapter
        return MultiBrainAdapter.get_instance().process_detailed(user_input)

    def think_and_act(self, user_input, max_steps=5):
        """
        An agentic loop that plans, executes, and iterates.
        """
        print(f"{Fore.YELLOW}🚀 [AGENTIC LOOP] Initializing for: {user_input}")
        
        # 1. Generate Plan
        plan_prompt = (
            f"User Request: {user_input}\n\n"
            "Task: Break this down into a multi-step execution plan.\n"
            "Output format: JSON list of steps. Example: [\"Step 1: ...\", \"Step 2: ...\"]\n"
            "Be extremely specific."
        )
        
        # Use DeepSeek for planning
        # We need to manually set routing if we want to force specific brain, 
        # but think_with_meta handles routing.
        meta = self.think_with_meta(plan_prompt)
        plan_text = meta.final_response
        
        # Simple extraction
        steps = []
        try:
            match = re.search(r'\[.*\]', plan_text, re.DOTALL)
            if match:
                steps = json.loads(match.group(0))
            else:
                steps = [s.strip() for s in plan_text.split("\n") if len(s) > 5]
        except:
            steps = [plan_text]

        print(f"{Fore.GREEN}📋 [PLAN] {len(steps)} steps identified.")
        
        # 2. Iterate
        results = []
        for i, step in enumerate(steps[:max_steps]):
            print(f"{Fore.CYAN}⚙️ [STEP {i+1}] {step}")
            # Observe/Execute cycle
            step_meta = self.think_with_meta(f"Current Status: {results}\nNext Step: {step}\nAction: Execute this step and report result.")
            results.append(step_meta.final_response)
            
            if "TASK COMPLETE" in step_meta.final_response:
                break
        
        final_summary = self.think(f"Summarize the outcome of these actions: {results}")
        return final_summary

    def think_with_meta(self, user_input, system_role="You are MIND.", temperature=0.7, image_b64=None):
        """
        Executes the thinking process and returns a MetaLogEntry with traceable confidence.
        """
        # 1. Update Memory
        if not image_b64:
            self.add_to_history("user", user_input)
        
        # 2. Determine Persona / Routing
        from modules.personas import get_role_from_input, MIND_ROLES
        
        # Initialize Log
        log_entry = MetaLogEntry(task="General Query", persona="Unknown", input_text=user_input)

        # A. Check for Locking/Overrides
        brain_key = "MANAGER" # Default
        if not image_b64:
            if "stay in" in user_input.lower() and "mode" in user_input.lower():
                scored_roles = get_role_from_input(user_input)
                if scored_roles and scored_roles[0][1] > 0.4:
                    self.locked_role = scored_roles[0][0]
                    log_entry.final_response = f"🔒 Persona Locked: {self.locked_role}."
                    return log_entry

            if "reset role" in user_input.lower():
                self.locked_role = None
                log_entry.final_response = "🔓 Persona Unlocked."
                return log_entry

        # B. Resolve Active Role
        active_role = None
        if self.locked_role:
            active_role = self.locked_role
        else:
            scored_roles = get_role_from_input(user_input)
            if scored_roles and scored_roles[0][1] >= 0.7:
                active_role = scored_roles[0][0]

        # C. Apply Persona & Routing
        if image_b64:
            brain_key = "VISION"
        elif active_role:
            data = MIND_ROLES[active_role]
            system_role = f"{data['prompt']}\n\nTONE: {data.get('tone','Professional')}"
            brain_key = data['brain']
            log_entry.persona = active_role
        else:
            brain_key = self._determine_brain(user_input)
            log_entry.persona = brain_key

        selected_brain = self.brains[brain_key]
        print(Fore.CYAN + f"🧠 [ROUTING] {brain_key} | {selected_brain['name']}")
        
        # D. Execute with Meta-Prompting
        # We ask the model to output a specific format if it's a capable model
        # For simplicity in this v1 implementation, we append a request for confidence if it's a 'smart' model
        
        is_smart = brain_key in ["MANAGER", "ANALYST", "THEORIST", "SECURITY", "GLM", "DEEPSEEK", "VISION"]
        
        original_system_role = system_role
        
        # --- Memory Retrieval (RAG) for Reasoning ---
        # If we are in deep thought mode, check if we've solved similar things before.
        if brain_key in ["DEEPSEEK", "THEORIST", "SECURITY"] and not image_b64:
             memories = self.memory.search_memory(user_input, limit=2)
             if memories:
                 print(f"{Fore.MAGENTA}🧠 [MEMORY] Recalled {len(memories)} past items.")
                 memory_context = "\n\n[RELEVANT PAST MEMORIES]\n" + "\n".join(memories) + "\n[END MEMORIES]"
                 system_role += memory_context

        if is_smart and "json" not in user_input.lower(): # Don't break user JSON requests
            system_role += "\n\nIMPORTANT: At the end of your response, strictly output your confidence level (0.0 to 1.0) on a new line like: 'CONFIDENCE: 0.95'"

        # --- Message Construction ---
        if image_b64:
            messages = [
                {"role": "system", "content": system_role},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_input},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}}
                    ]
                }
            ]
        else:
            messages = [{"role": "system", "content": system_role}] + self.history

        try:
            # Check Keys
            if selected_brain['api_key'] != "local" and not selected_brain['api_key']:
                 print(f"{Fore.YELLOW}⚠️ [BRAIN] Key missing for {brain_key}. Falling back to MANAGER.")
                 selected_brain = self.brains["MANAGER"] # Fallback
            
            # 2nd Fallback: If MANAGER key is also missing, use THEORIST (Local)
            if selected_brain['api_key'] != "local" and not selected_brain['api_key']:
                 print(f"{Fore.YELLOW}⚠️ [BRAIN] MANAGER key also missing. Falling back to THEORIST (Local).")
                 selected_brain = self.brains["THEORIST"]

            # Call API
            if "ollama" in selected_brain["model"] or selected_brain.get("api_key") == "local":
                reply = self._call_ollama_direct(selected_brain["model"], user_input, system_role, temperature)
                log_entry.add_step(f"{brain_key} Response", 0.95, sources=[selected_brain['model']])
                log_entry.compute_overall_confidence()
                log_entry.final_response = reply
                self.add_to_history("assistant", reply)
                return log_entry

            base_url = selected_brain.get("api_base")
            
            try:
                if selected_brain.get("provider") == "meta":
                    from multi_brain.providers.meta_provider import MetaModelClient
                    client = MetaModelClient.get_instance()
                    meta_res = client.chat_completion(
                        messages=messages,
                        model=selected_brain["model"],
                        agent_id=brain_key,
                        temperature=temperature,
                    )
                    reply = meta_res.get("content") or ""
                else:
                    response = completion(
                        model=selected_brain["model"],
                        messages=messages,
                        api_key=selected_brain["api_key"] if selected_brain["api_key"] != "local" else None,
                        temperature=temperature,
                        api_base=base_url
                    )
                    reply = response.choices[0].message.content
            except Exception as lite_error:
                print(Fore.RED + f"⚠️ [BRAIN] Inference Error: {lite_error}")
                # Fallback response for connection errors
                log_entry.add_step(f"Error: {lite_error}", 0.0)
                log_entry.final_response = "I encountered a neural network connection error, Sir. Please check my internet access."
                return log_entry
            
            # E. Parse Meta-Data (Confidence)
            confidence_match = re.search(r"CONFIDENCE:\s*([0-9]*\.?[0-9]+)", reply)
            extracted_conf = 0.85 # Default
            
            final_text = reply
            if confidence_match:
                extracted_conf = float(confidence_match.group(1))
                # Remove the meta-line from the spoken output to keep it clean
                final_text = reply.replace(confidence_match.group(0), "").strip()
            
            # Log the step
            log_entry.add_step(f"{brain_key} Response", extracted_conf, sources=[selected_brain['model']])
            log_entry.compute_overall_confidence()
            log_entry.final_response = final_text
            
            self.add_to_history("assistant", final_text)
            
            # Print Meta-Log Status
            print(Fore.MAGENTA + f"📊 [META] Confidence: {log_entry.overall_confidence:.2f}")
            
            return log_entry

        except Exception as e:
            print(Fore.RED + f"⚠️ Brain Error: {e}")
            log_entry.add_step(f"Error: {e}", 0.0)
            log_entry.final_response = "I encountered a neural error, Sir."
            return log_entry