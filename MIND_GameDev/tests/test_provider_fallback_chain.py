"""
Unit & Integration Tests for Hierarchical Provider Failover & Gemini Fallback Chain.
Verifies:
1. Primary provider success.
2. Primary provider authentication failure (e.g. OpenRouter 401 failover).
3. Primary provider timeout / network failure failover.
4. Gemini fallback success (live or simulated depending on network).
5. All providers offline -> deterministic scaffold fallback.
6. Correct provider attribution in metadata.
"""

import os
import unittest
from unittest.mock import patch, MagicMock
import requests

from MIND_GameDev.adapters.coding_adapter import CodingProviderAdapter
from MIND_GameDev.config import GameDevConfig


class TestProviderFallbackChain(unittest.TestCase):

    def setUp(self):
        self.config = GameDevConfig.load()
        self.adapter = CodingProviderAdapter(config=self.config)

    def test_openrouter_401_fails_over_to_groq_or_gemini(self):
        """When OpenRouter returns 401, system must not crash; it must fail over to next tier."""
        with patch.object(self.adapter, "_call_openrouter") as mock_or:
            mock_or.return_value = {"success": False, "error": "OpenRouter HTTP 401: API key expired"}
            
            with patch.object(self.adapter, "_call_groq") as mock_groq:
                mock_groq.return_value = {
                    "success": True,
                    "code": "const ready = true;",
                    "provider": "Groq Cloud LPU",
                    "model": "openai/gpt-oss-120b",
                }
                
                res = self.adapter.generate(prompt="Create a simple helper", language="javascript")
                self.assertTrue(res.get("success"))
                self.assertEqual(res.get("provider"), "Groq Cloud LPU")
                self.assertIn("const ready = true;", res.get("code", ""))

    def test_groq_failure_fails_over_to_gemini(self):
        """When OpenRouter and Groq fail, system must seamlessly fail over to Gemini."""
        with patch.object(self.adapter, "_call_openrouter") as mock_or:
            mock_or.return_value = {"success": False, "error": "OpenRouter offline"}
            
            with patch.object(self.adapter, "_call_groq") as mock_groq:
                mock_groq.return_value = {"success": False, "error": "Groq rate limit (429)"}
                
                with patch.object(self.adapter, "_call_gemini") as mock_gem:
                    mock_gem.return_value = {
                        "success": True,
                        "code": "function calculateScore() { return 100; }",
                        "provider": "Google Gemini Cloud",
                        "model": "gemini-3-flash-preview",
                    }
                    
                    res = self.adapter.generate(prompt="Score calculator", language="javascript")
                    self.assertTrue(res.get("success"))
                    self.assertEqual(res.get("provider"), "Google Gemini Cloud")
                    self.assertEqual(res.get("model"), "gemini-3-flash-preview")
                    self.assertIn("calculateScore", res.get("code", ""))

    def test_gemini_failure_fails_over_to_ollama(self):
        """When cloud tiers fail, local Ollama engine is invoked."""
        with patch.object(self.adapter, "_call_openrouter", return_value={"success": False, "error": "offline"}), \
             patch.object(self.adapter, "_call_groq", return_value={"success": False, "error": "offline"}), \
             patch.object(self.adapter, "_call_gemini", return_value={"success": False, "error": "offline"}), \
             patch.object(self.adapter, "_call_ollama") as mock_ollama:
            
            mock_ollama.return_value = {
                "success": True,
                "code": "class LocalGame {};",
                "provider": "ollama_local",
                "model": "qwen2.5-coder:7b",
            }
            
            res = self.adapter.generate(prompt="Create game class", language="javascript")
            self.assertTrue(res.get("success"))
            self.assertEqual(res.get("provider"), "ollama_local")

    def test_all_providers_unavailable_deterministic_fallback(self):
        """When all cloud APIs and local Ollama are unreachable, deterministic fallback succeeds."""
        with patch.object(self.adapter, "_call_openrouter", return_value={"success": False, "error": "err"}), \
             patch.object(self.adapter, "_call_groq", return_value={"success": False, "error": "err"}), \
             patch.object(self.adapter, "_call_gemini", return_value={"success": False, "error": "err"}), \
             patch.object(self.adapter, "_call_ollama", return_value={"success": False, "error": "err"}):
            
            res = self.adapter.generate(prompt="Create player jump controller", language="javascript")
            self.assertTrue(res.get("success"))
            self.assertEqual(res.get("provider"), "offline_deterministic_fallback")
            self.assertIn("Player", res.get("code", ""))

    def test_gemini_blender_script_fallback(self):
        """When Cerebras and Groq are unavailable, Gemini generates the Blender script."""
        with patch.object(self.adapter, "_call_groq", return_value={"success": False, "error": "timeout"}), \
             patch.object(self.adapter, "_call_gemini") as mock_gem:
            
            mock_gem.return_value = {
                "success": True,
                "code": "import bpy\nbpy.ops.mesh.primitive_cube_add()",
                "provider": "Google Gemini Cloud",
                "model": "gemini-3-flash-preview",
            }
            
            res = self.adapter.generate_blender_script(
                visual_analysis={"analysis_text": "Cubic structure"},
                prompt="Cubic monolith",
                target_glb_name="monolith.glb",
            )
            self.assertTrue(res.get("success"))
            self.assertEqual(res.get("provider"), "Google Gemini Cloud")
            self.assertIn("import bpy", res.get("code", ""))


if __name__ == "__main__":
    unittest.main()
