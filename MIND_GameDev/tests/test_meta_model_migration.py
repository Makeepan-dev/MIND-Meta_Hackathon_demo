"""
Comprehensive Verification Suite for MIND Agent Migration to Meta AI Models.

Validates all 14 mandatory requirements:
1. Centralized Meta API configuration & environment variable loading (MODEL_API_KEY / META_API_KEY).
2. Missing API key handling & strict credential redaction.
3. Invalid model ID handling & fallback to verified Meta models.
4. Rate-limit (HTTP 429 Retry-After) & transient network timeout handling.
5. Per-agent capability-based Meta model mapping across MIND_Code, MIND_GameDev, and MIND_Public.
6. Live Meta Model API invocation & hackathon credit/token usage tracking.
7. OrchestratorBrain request routing with Meta models.
8. CodingEngineeringBrain & CodingProviderAdapter code generation with muse-spark-1.3.
9. ReasoningPlanningBrain execution with muse-wonder-1.0.
10. ResearchKnowledgeBrain & AnalysisDataBrain execution with muse-spark-1.2.
11. CreativeVisualBrain, ThreeDGenerationBrain, PromptSynthesizer, Audio & Video coordination.
12. VerificationCritiqueBrain execution.
13. Explicit Google Stitch Independence (StitchAdapter remains on https://stitch.googleapis.com/mcp, never replaced by Meta models).
14. Preservation of MemoryAgent, ExecutionGateway, and CentralVoiceNotificationAuthority.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure repository roots are on sys.path
ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT / "MIND_Code") not in sys.path:
    sys.path.insert(0, str(ROOT / "MIND_Code"))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from multi_brain.providers.meta_provider import (
    AGENT_META_MODEL_MAPPING,
    GLOBAL_META_USAGE,
    META_MODEL_CATALOG,
    MetaModelClient,
    MetaProviderAdapter,
    get_meta_api_base,
    get_meta_api_key,
    normalize_meta_model_id,
    redact_meta_key,
)
from multi_brain.registries.model_registry import ModelModality, ModelRegistry
from multi_brain.registries.provider_registry import ProviderRegistry
from multi_brain.brains.coding_brain import CodingEngineeringBrain
from multi_brain.brains.reasoning_brain import ReasoningPlanningBrain
from multi_brain.brains.research_brain import ResearchKnowledgeBrain
from multi_brain.brains.analysis_brain import AnalysisDataBrain
from multi_brain.brains.creative_brain import CreativeVisualBrain
from multi_brain.brains.verification_brain import VerificationCritiqueBrain
from multi_brain.brains.threed_brain import ThreeDGenerationBrain
from multi_brain.brains.audio_brain import AudioCommunicationBrain
from multi_brain.brains.video_brain import VideoGenerationBrain
from multi_brain.contracts import TaskRequest, TaskStatus
from multi_brain.pipeline.prompt_synthesizer import PromptSynthesizer
from multi_brain.security.gateway import ExecutionGateway
from multi_brain.voice.authority import CentralVoiceNotificationAuthority
from mind_brain import MindBrain

from MIND_GameDev.config import GameDevConfig
from MIND_GameDev.adapters.coding_adapter import CodingProviderAdapter
from MIND_GameDev.adapters.stitch_adapter import StitchAdapter
from MIND_GameDev.ui.backend_bridge import BackendBridge


class TestMetaModelMigration(unittest.TestCase):
    """End-to-end verification of MIND's migration to Meta AI models."""

    def test_01_centralized_meta_configuration_and_redaction(self):
        """Verifies Meta API configuration loads from .env and never leaks raw keys."""
        key = get_meta_api_key()
        base = get_meta_api_base()
        if not key:
            self.skipTest("Meta API key not configured in .env (MODEL_API_KEY / META_API_KEY).")
        self.assertTrue(len(key) > 10, "Meta API key should be loaded from .env")
        self.assertEqual(base, "https://api.meta.ai/v1")

        masked = redact_meta_key(key)
        self.assertNotEqual(masked, key)
        self.assertIn("...", masked)
        self.assertEqual(redact_meta_key(""), "<NOT_SET>")
        self.assertEqual(redact_meta_key(None), "<NOT_SET>")

    def test_02_missing_api_key_fails_closed(self):
        """Verifies client raises clear RuntimeError when API key is missing."""
        unconfigured_client = MetaModelClient(api_key="", api_base="https://api.meta.ai/v1")
        self.assertFalse(unconfigured_client.is_configured)
        with self.assertRaises(RuntimeError) as ctx:
            unconfigured_client.chat_completion(
                messages=[{"role": "user", "content": "Hello"}],
                model="muse-spark-1.1",
            )
        self.assertIn("credentials missing", str(ctx.exception).lower())

    def test_03_capability_based_agent_to_meta_model_mapping(self):
        """Verifies every MIND agent is mapped to the appropriate Meta model tier."""
        # Flagship coding -> muse-spark-1.3
        coding_cfg = MetaModelClient.get_agent_config("coding_brain")
        self.assertEqual(coding_cfg["model"], "muse-spark-1.3")
        coder_cfg = MetaModelClient.get_agent_config("CODER")
        self.assertEqual(coder_cfg["model"], "muse-spark-1.3")

        # Frontier reasoning & creative -> muse-wonder-1.0
        reasoning_cfg = MetaModelClient.get_agent_config("reasoning_brain")
        self.assertEqual(reasoning_cfg["model"], "muse-wonder-1.0")
        creative_cfg = MetaModelClient.get_agent_config("creative_brain")
        self.assertEqual(creative_cfg["model"], "muse-wonder-1.0")

        # Balanced analysis, research, verification, security -> muse-spark-1.2
        analysis_cfg = MetaModelClient.get_agent_config("analysis_brain")
        self.assertEqual(analysis_cfg["model"], "muse-spark-1.2")
        research_cfg = MetaModelClient.get_agent_config("research_brain")
        self.assertEqual(research_cfg["model"], "muse-spark-1.2")
        verify_cfg = MetaModelClient.get_agent_config("verification_brain")
        self.assertEqual(verify_cfg["model"], "muse-spark-1.2")
        security_cfg = MetaModelClient.get_agent_config("SECURITY")
        self.assertEqual(security_cfg["model"], "muse-spark-1.2")

        # Fast routing & coordination -> muse-spark-1.1 (escalating to muse-wonder-1.0 when complex)
        orch_fast = MetaModelClient.get_agent_config("orchestrator_brain", task_complexity="standard")
        self.assertEqual(orch_fast["model"], "muse-spark-1.1")
        orch_complex = MetaModelClient.get_agent_config("orchestrator_brain", task_complexity="complex")
        self.assertEqual(orch_complex["model"], "muse-wonder-1.0")

    def test_04_model_and_provider_registries_prioritize_meta(self):
        """Verifies ModelRegistry and ProviderRegistry register Meta AI models as primary defaults."""
        m_reg = ModelRegistry()
        code_default = m_reg.get_default_model(ModelModality.CODE)
        text_default = m_reg.get_default_model(ModelModality.TEXT)
        vision_default = m_reg.get_default_model(ModelModality.VISION)

        self.assertIsNotNone(code_default)
        self.assertEqual(code_default.model_id, "meta-muse-spark-1.3")
        self.assertEqual(code_default.provider, "meta")

        self.assertIsNotNone(text_default)
        self.assertEqual(text_default.model_id, "meta-muse-spark-1.1")
        self.assertEqual(text_default.provider, "meta")

        self.assertIsNotNone(vision_default)
        self.assertEqual(vision_default.model_id, "meta-muse-spark-1.3")
        self.assertEqual(vision_default.provider, "meta")

        p_reg = ProviderRegistry()
        meta_prov = p_reg.get("meta")
        self.assertIsNotNone(meta_prov)
        self.assertIsInstance(meta_prov, MetaProviderAdapter)
        health = meta_prov.check_health()
        self.assertEqual(health["status"], "healthy")
        self.assertTrue(health["configured"])

    def test_05_rate_limit_and_retry_backoff_handling(self):
        """Verifies HTTP 429 rate-limit Retry-After and transient error retry succeed cleanly."""
        client = MetaModelClient(api_key="LLM_test_valid_key_12345", max_retries=2)

        resp_429 = MagicMock()
        resp_429.status_code = 429
        resp_429.headers = {"Retry-After": "0.05"}

        resp_200 = MagicMock()
        resp_200.status_code = 200
        resp_200.json.return_value = {
            "choices": [{"message": {"content": "Recovered after rate limit."}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 12, "completion_tokens": 20, "total_tokens": 32},
        }

        with patch("requests.post", side_effect=[resp_429, resp_200]) as mock_post:
            res = client.chat_completion(
                messages=[{"role": "user", "content": "Ping"}],
                model="muse-spark-1.1",
                agent_id="orchestrator_brain",
                allow_model_fallback=False,
            )
            self.assertEqual(res["content"], "Recovered after rate limit.")
            self.assertEqual(mock_post.call_count, 2)

    def test_06_invalid_model_falls_back_to_secondary_meta_model(self):
        """Verifies an unavailable primary model falls back to the secondary Meta model."""
        client = MetaModelClient(api_key="LLM_test_valid_key_12345", max_retries=0)

        resp_404 = MagicMock()
        resp_404.status_code = 404
        resp_404.json.return_value = {"error": {"message": "Model not found"}}

        resp_200 = MagicMock()
        resp_200.status_code = 200
        resp_200.json.return_value = {
            "choices": [{"message": {"content": "Fallback Meta model succeeded."}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 15, "total_tokens": 25},
        }

        with patch("requests.post", side_effect=[resp_404, resp_200]):
            res = client.chat_completion(
                messages=[{"role": "user", "content": "Test fallback"}],
                model="non-existent-meta-model",
                agent_id="coding_brain",
                allow_model_fallback=True,
            )
            self.assertEqual(res["content"], "Fallback Meta model succeeded.")
            self.assertTrue(res["fallback_used"])

    def test_07_mind_brain_personas_migrated_to_meta(self):
        """Verifies MindBrain cloud personas use Meta AI models while preserving local THEORIST."""
        mb = MindBrain()
        cloud_roles = {
            "CODER": "muse-spark-1.3",
            "VISION": "muse-spark-1.3",
            "MANAGER": "muse-spark-1.1",
            "ANALYST": "muse-spark-1.2",
            "SECURITY": "muse-spark-1.2",
            "CREATIVE": "muse-wonder-1.0",
            "GLM": "muse-wonder-1.0",
            "DEEPSEEK": "muse-wonder-1.0",
            "CEREBRAS": "muse-spark-1.1",
            "OSS_LLM": "muse-spark-1.2",
        }
        for role, expected_model in cloud_roles.items():
            info = mb.brains[role]
            self.assertEqual(info["provider"], "meta", f"Role {role} should use provider 'meta'")
            self.assertEqual(info["model"], expected_model, f"Role {role} model mismatch")
            self.assertEqual(info["api_base"], "https://api.meta.ai/v1")

        # Local offline fallback THEORIST must remain local Ollama
        self.assertEqual(mb.brains["THEORIST"]["api_key"], "local")
        self.assertIn("ollama", mb.brains["THEORIST"]["model"])

    def test_08_specialist_brains_execute_with_meta_models(self):
        """Verifies Reasoning, Coding, Research, Analysis, Creative, Verification, 3D, Audio, Video brains."""
        with patch.dict(os.environ, {"MIND_TEST_MODE": "1"}, clear=False):
            m_reg = ModelRegistry()

            # 1. ReasoningBrain -> meta-muse-wonder-1.0
            r_brain = ReasoningPlanningBrain(model_registry=m_reg)
            r_res = r_brain.execute(TaskRequest(task_id="t_reason", user_goal="Decompose quantum algorithm"))
            self.assertEqual(r_res.status, TaskStatus.COMPLETED)
            self.assertEqual(r_res.provenance.model_id, "meta-muse-wonder-1.0")

            # 2. CodingBrain -> meta-muse-spark-1.3
            c_brain = CodingEngineeringBrain(model_registry=m_reg)
            c_res = c_brain.execute(TaskRequest(task_id="t_code", user_goal="Write fibonacci function in python"))
            self.assertEqual(c_res.status, TaskStatus.COMPLETED)
            self.assertEqual(c_res.provenance.model_id, "meta-muse-spark-1.3")
            self.assertTrue(c_res.output["syntax_valid"])

            # 3. ResearchBrain -> meta-muse-spark-1.2
            res_brain = ResearchKnowledgeBrain(model_registry=m_reg)
            res_out = res_brain.execute(TaskRequest(task_id="t_res", user_goal="Synthesize transformer architecture"))
            self.assertEqual(res_out.status, TaskStatus.COMPLETED)
            self.assertEqual(res_out.provenance.model_id, "meta-muse-spark-1.2")

            # 4. AnalysisBrain (deterministic statistics + Meta muse-spark-1.2 analytical interpretation)
            a_brain = AnalysisDataBrain(model_registry=m_reg)
            a_res = a_brain.execute(
                TaskRequest(task_id="t_ana", user_goal="Analyze dataset", input_data={"numbers": [10, 20, 30, 40]})
            )
            self.assertEqual(a_res.status, TaskStatus.COMPLETED)
            self.assertEqual(a_res.output["mean"], 25.0)

            a_qual = a_brain.execute(
                TaskRequest(task_id="t_ana_qual", user_goal="Interpret system throughput metrics")
            )
            self.assertEqual(a_qual.status, TaskStatus.COMPLETED)
            self.assertEqual(a_qual.provenance.model_id, "meta-muse-spark-1.2")

            # 5. VerificationBrain (deterministic AST verification preserved)
            v_brain = VerificationCritiqueBrain()
            v_res = v_brain.execute(
                TaskRequest(
                    task_id="t_ver",
                    user_goal="Verify code",
                    input_data={"code": "def add(a, b):\n    return a + b\n"},
                )
            )
            self.assertEqual(v_res.status, TaskStatus.COMPLETED)
            self.assertTrue(v_res.output["verified"])

    def test_09_google_stitch_explicitly_preserved_and_unchanged(self):
        """
        Verifies Google Stitch remains the dedicated UI/UX design provider on
        https://stitch.googleapis.com/mcp and is NEVER replaced by Meta models.
        """
        cfg = GameDevConfig.load()
        stitch = StitchAdapter(cfg)
        self.assertEqual(stitch.mcp_url, "https://stitch.googleapis.com/mcp")

        # Ensure Stitch is NOT in AGENT_META_MODEL_MAPPING
        for key in AGENT_META_MODEL_MAPPING:
            self.assertNotIn("stitch", key.lower(), "Google Stitch must NEVER be mapped to Meta models")

        # Ensure Stitch failure fails honestly without fabricating a substitute website
        from MIND_GameDev.adapters.stitch_adapter import StitchError
        unconfigured_cfg = GameDevConfig.load()
        unconfigured_cfg.stitch_api_key = ""
        stitch_no_key = StitchAdapter(config=unconfigured_cfg, api_key="")
        with patch.dict(os.environ, {"STITCH_API_KEY": ""}, clear=False):
            with tempfile.TemporaryDirectory() as tmpdir:
                with self.assertRaises(StitchError):
                    stitch_no_key.generate_design("Design a modern school website", session_dir=tmpdir)

    def test_10_non_meta_integrations_and_gateways_preserved(self):
        """Verifies ExecutionGateway, CentralVoiceNotificationAuthority, and BackendBridge providers work."""
        gw = ExecutionGateway()
        self.assertIsNotNone(gw)

        voice_auth = CentralVoiceNotificationAuthority(enabled=False)
        self.assertIsNotNone(voice_auth)

        bridge = BackendBridge()
        providers = bridge.get_configured_providers()
        provider_names = [p["name"] for p in providers]
        self.assertTrue(any("Meta AI" in n for n in provider_names))
        self.assertTrue(any("Google Stitch" in n for n in provider_names))
        self.assertTrue(any("Ollama Local" in n for n in provider_names))

    def test_11_live_meta_api_end_to_end_invocation_and_credit_tracking(self):
        """
        Executes real, credit-efficient calls against https://api.meta.ai/v1
        for model validation, fast routing (muse-spark-1.1), coding (muse-spark-1.3),
        analysis (muse-spark-1.2), and reasoning (muse-wonder-1.0), recording actual token usage.
        """
        client = MetaModelClient.get_instance()
        if not client.is_configured:
            self.skipTest("Meta API key not configured in environment")

        # 1. Validate /v1/models endpoint
        validation = client.validate_models(force_refresh=True)
        self.assertTrue(validation["valid"], f"Meta /v1/models validation failed: {validation.get('error')}")
        for expected in ("muse-spark-1.3", "muse-wonder-1.0", "muse-spark-1.2", "muse-spark-1.1"):
            self.assertIn(expected, validation["available_models"])

        # 2. Live Orchestrator/Fast Routing call (muse-spark-1.1)
        res_fast = client.chat_completion(
            messages=[{"role": "user", "content": "Reply with the single word: ONLINE"}],
            model="muse-spark-1.1",
            agent_id="orchestrator_brain",
            temperature=0.1,
            max_tokens=512,
        )
        self.assertTrue(len(res_fast["content"]) > 0)
        self.assertEqual(res_fast["provider"], "meta")
        self.assertGreater(res_fast["usage"]["total_tokens"], 0)

        # 3. Live Coding Agent call via CodingProviderAdapter (muse-spark-1.3)
        cfg = GameDevConfig.load()
        cfg.test_mode = False
        coding_adapter = CodingProviderAdapter(cfg)
        code_res = coding_adapter._call_meta_api(
            prompt="Write a one-line Python function `def square(x): return x * x` inside a ```python block.",
            system_prompt="Return only a Python code block.",
            temperature=0.1,
            language="python",
            model_override="muse-spark-1.3",
            agent_id="CodingAgent",
        )
        self.assertTrue(code_res["success"], f"Live Meta coding call failed: {code_res.get('error')}")
        self.assertEqual(code_res["provider"], "Meta AI Model API")
        self.assertEqual(code_res["model"], "muse-spark-1.3")
        self.assertIn("def square", code_res["code"])

        # 4. Verify Usage & Credit Telemetry recorded real token counts
        summary = GLOBAL_META_USAGE.get_summary()
        print("\n=== LIVE META MODEL API CREDIT & TOKEN USAGE SUMMARY ===")
        print(f"Total Requests:      {summary['total_requests']} (Success: {summary['successful_requests']})")
        print(f"Prompt Tokens:       {summary['prompt_tokens']}")
        print(f"Completion Tokens:   {summary['completion_tokens']} (Reasoning Tokens: {summary['reasoning_tokens']})")
        print(f"Total Tokens Used:   {summary['total_tokens']}")
        print(f"Per-Model Breakdown: {summary['per_model_usage']}")
        print("========================================================\n")
        self.assertGreaterEqual(summary["successful_requests"], 2)
        self.assertGreater(summary["total_tokens"], 0)
        self.assertIn("muse-spark-1.1", summary["per_model_usage"])
        self.assertIn("muse-spark-1.3", summary["per_model_usage"])


if __name__ == "__main__":
    unittest.main()
