"""
Unit and Integration Tests for MIND Meta Llama & Multi-Brain Architecture.
Covers:
1. Successful MindBrain initialization.
2. Correct brain routing.
3. Successful Ollama provider invocation.
4. Correct Meta model identification.
5. Explicit failure when Meta Llama is unavailable.
6. Prevention of silent provider substitution.
7. Desktop chat worker integration.
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Ensure project roots are on path
ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT / "MIND_Code") not in sys.path:
    sys.path.insert(0, str(ROOT / "MIND_Code"))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mind_brain import MindBrain
from MIND_GameDev.ui.backend_bridge import AIWorker


class TestMetaLlamaBrainIntegration(unittest.TestCase):

    def setUp(self):
        # Initialize MindBrain instance
        self.brain = MindBrain()

    def test_01_mind_brain_initialization(self):
        """MindBrain must initialize cleanly with all expected specialized brains."""
        self.assertIsNotNone(self.brain)
        expected_brains = ["THEORIST", "MINISTRAL", "CODER", "VISION", "MANAGER", "ANALYST", "SECURITY", "CREATIVE"]
        for b in expected_brains:
            self.assertIn(b, self.brain.brains, f"Expected brain '{b}' not found in MindBrain")

        # Verify THEORIST targets Meta Llama
        theorist = self.brain.brains["THEORIST"]
        self.assertIn("ollama", theorist["model"])
        self.assertEqual(theorist["api_key"], "local")
        self.assertIn("Meta Llama", theorist["name"])

    def test_02_correct_brain_routing(self):
        """query_specific_brain must query the requested brain directly without keyword reroute."""
        with patch.object(self.brain, "_call_ollama_direct") as mock_ollama:
            mock_ollama.return_value = "Meta Llama reasoning output for quantum theory."
            res = self.brain.query_specific_brain("THEORIST", "Explain quantum theory")
            self.assertEqual(res, "Meta Llama reasoning output for quantum theory.")
            mock_ollama.assert_called_once()
            # Assert target model was passed
            model_arg = mock_ollama.call_args[0][0]
            self.assertIn("llama", model_arg.lower())

    def test_03_ollama_direct_invocation_success(self):
        """_call_ollama_direct makes direct HTTP call to Ollama endpoint and returns text."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"response": "Genuine Meta Llama offline response."}

        with patch("requests.post", return_value=mock_response) as mock_post:
            result = self.brain._call_ollama_direct("llama3.2:1b", "Test prompt", "System instruction")
            self.assertEqual(result, "Genuine Meta Llama offline response.")
            mock_post.assert_called_once()
            call_url = mock_post.call_args[0][0]
            self.assertEqual(call_url, "http://localhost:11434/api/generate")
            payload = mock_post.call_args[1]["json"]
            self.assertEqual(payload["model"], "llama3.2:1b")
            self.assertEqual(payload["prompt"], "Test prompt")

    def test_04_correct_meta_model_identification(self):
        """Brain telemetry must accurately reflect the Meta Llama model."""
        theorist = self.brain.brains["THEORIST"]
        meta_model = theorist["model"].replace("ollama/", "")
        self.assertTrue(meta_model.startswith("llama"), f"Expected Llama model, got '{meta_model}'")
        self.assertIn(meta_model, theorist["name"])

    def test_05_explicit_failure_when_model_missing(self):
        """Missing or uninstalled model must raise explicit RuntimeError, not silently succeed."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = "model 'non_existent_model' not found"

        with patch("requests.post", return_value=mock_response):
            with self.assertRaises(RuntimeError) as ctx:
                self.brain._call_ollama_direct("non_existent_model", "test", "test")
            self.assertIn("not installed", str(ctx.exception))

    def test_06_prevention_of_silent_provider_substitution(self):
        """When user explicitly selects a brain (THEORIST), failures must NOT silently fall back to another model."""
        worker = AIWorker(prompt="Explain theory", brain_type="THEORIST")
        
        # Track signals
        received_responses = []
        received_failures = []
        worker.response_ready.connect(lambda resp, tag: received_responses.append((resp, tag)))
        worker.task_failed.connect(lambda err: received_failures.append(err))

        # Simulate THEORIST failing (e.g. Ollama service stopped)
        with patch("mind_brain.MindBrain.query_specific_brain", side_effect=ConnectionError("Ollama service offline")):
            worker.run()

        # Must have failed explicitly, with NO silent fallback response
        self.assertEqual(len(received_responses), 0, "Silent fallback occurred when specific brain was requested!")
        self.assertEqual(len(received_failures), 1, "task_failed was not emitted on brain failure!")
        self.assertIn("THEORIST", received_failures[0])
        self.assertIn("Ollama service offline", received_failures[0])

    def test_07_desktop_chat_integration_success(self):
        """AIWorker must successfully execute request through MindBrain and emit response_ready."""
        worker = AIWorker(prompt="Hello MIND", brain_type="THEORIST")

        received_responses = []
        received_failures = []
        worker.response_ready.connect(lambda resp, tag: received_responses.append((resp, tag)))
        worker.task_failed.connect(lambda err: received_failures.append(err))

        with patch("mind_brain.MindBrain.query_specific_brain", return_value="Greetings, Sir. Local Meta Llama online."):
            worker.run()

        self.assertEqual(len(received_failures), 0)
        self.assertEqual(len(received_responses), 1)
        resp_text, model_tag = received_responses[0]
        self.assertEqual(resp_text, "Greetings, Sir. Local Meta Llama online.")
        self.assertIn("THEORIST", model_tag)


if __name__ == "__main__":
    unittest.main()
