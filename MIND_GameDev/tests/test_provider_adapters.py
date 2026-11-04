"""
Unit tests for Provider Adapters:
Validates coding adapter fallbacks, OpenRouter free models, paid-model blocking,
AI Horde submission, polling, retrieval and local fallbacks, 3D glTF/OBJ syntax,
and provider diagnostics reporting without paid token consumption.
"""

import tempfile
import struct
import io
from pathlib import Path
from unittest.mock import patch, MagicMock
from PIL import Image

from MIND_GameDev.config import GameDevConfig
from MIND_GameDev.adapters.coding_adapter import CodingAdapter, CodingProviderAdapter, is_free_model
from MIND_GameDev.adapters.image_adapter import ImageAssetAdapter, ImageProviderAdapter
from MIND_GameDev.adapters.threed_adapter import ThreeDAssetAdapter
from MIND_GameDev.adapters.voice_output import VoiceOutputAdapter
from MIND_GameDev.providers import ProviderDiagnostics


def test_coding_adapter_deterministic_fallback():
    cfg = GameDevConfig.load()
    adapter = CodingAdapter(cfg)
    code = adapter._generate_template_code("player movement jump slide")
    assert "class Player" in code
    assert "jump" in code
    assert "slide" in code


def test_coding_adapter_free_model_verification():
    assert is_free_model("google/gemma-2-9b-it:free") is True
    assert is_free_model("meta-llama/llama-3.3-70b-instruct:free") is True
    assert is_free_model("openrouter/free") is True
    assert is_free_model("openai/gpt-4o") is False
    assert is_free_model("anthropic/claude-3.5-sonnet") is False
    assert is_free_model("") is False


def test_coding_adapter_blocks_paid_model_when_free_only():
    # Attempting to use a paid model with free_only=True must block OpenRouter call
    cfg = GameDevConfig.load()
    adapter = CodingProviderAdapter(cfg, model="openai/gpt-4o")
    adapter.api_key = "sk-test-key-12345"
    adapter.free_only = True

    with patch.object(adapter, "_call_openrouter") as mock_openrouter:
        res = adapter.generate(prompt="write login function")
        # Ensure _call_openrouter was NEVER invoked for the paid model
        mock_openrouter.assert_not_called()
        assert res["success"] is True
        # Must fall back to deterministic or local or configured free cloud fallback
        assert res["provider"] in (
            "Meta AI Model API",
            "offline_deterministic_fallback",
            "ollama_local",
            "test_mode_fallback",
            "Google Gemini Cloud",
            "Groq Cloud LPU",
            "SiliconFlow Cloud",
            "Cerebras Cloud",
        )


def test_coding_adapter_openrouter_free_success_mocked():
    cfg = GameDevConfig.load()
    adapter = CodingProviderAdapter(cfg, model="google/gemma-2-9b-it:free")
    adapter.api_key = "sk-test-free-key"
    adapter.config.test_mode = False

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": "```javascript\nfunction authSuccess() { return true; }\n```"}}]
    }

    with patch("requests.post", return_value=mock_resp):
        res = adapter.generate(prompt="create auth helper")
        assert res["success"] is True
        assert res["provider"] == "openrouter"
        assert res["model"] == "google/gemma-2-9b-it:free"
        assert "authSuccess" in res["code"]


def test_coding_adapter_openrouter_rate_limit_and_timeout():
    cfg = GameDevConfig.load()
    adapter = CodingProviderAdapter(cfg, model="google/gemma-2-9b-it:free")
    adapter.api_key = "sk-test-free-key"
    adapter.config.test_mode = False

    # Simulate 429 rate limit
    mock_resp = MagicMock()
    mock_resp.status_code = 429

    with patch("requests.post", return_value=mock_resp):
        res = adapter.generate(prompt="create player jump")
        # Should fall back cleanly to deterministic
        assert res["success"] is True
        assert res["provider"] == "offline_deterministic_fallback"
        assert "class Player" in res["code"]


def test_image_adapter_local_fallback():
    with tempfile.TemporaryDirectory() as tmpdir:
        cfg = GameDevConfig.load()
        adapter = ImageAssetAdapter(cfg)
        output_dir = Path(tmpdir)

        meta = adapter._generate_local_concept_art(
            prompt="Cyberpunk runner hero",
            target_path=output_dir / "hero.png",
            name="hero",
        )
        assert meta.verified is True
        assert Path(meta.file_path).exists()
        assert Path(meta.file_path).stat().st_size > 500
        assert meta.metadata["generation_type"] == "procedural_local"
        assert meta.metadata["provider"] == "local_pillow_engine"


def test_image_adapter_ai_horde_mocked_success():
    with tempfile.TemporaryDirectory() as tmpdir:
        cfg = GameDevConfig.load()
        cfg.test_mode = False
        adapter = ImageProviderAdapter(cfg)
        out_file = Path(tmpdir) / "ai_concept.png"

        # Create valid test PNG bytes in memory
        img = Image.new("RGB", (256, 256), color=(20, 40, 80))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        png_bytes = buf.getvalue()

        # Mock submit -> check -> status -> image download
        submit_mock = MagicMock(status_code=202)
        submit_mock.json.return_value = {"id": "horde-task-789"}

        check_mock = MagicMock(status_code=200)
        check_mock.json.return_value = {"done": True, "faulted": False}

        status_mock = MagicMock(status_code=200)
        status_mock.json.return_value = {
            "generations": [{"img": "https://fake.horde/img.png", "worker_name": "worker_01"}]
        }

        download_mock = MagicMock(status_code=200, content=png_bytes)

        with patch("requests.post", return_value=submit_mock), \
             patch("requests.get", side_effect=[check_mock, status_mock, download_mock]):
            meta = adapter.generate_concept_image(
                prompt="Futuristic city highway",
                target_path=out_file,
                name="ai_city",
            )
            assert meta.verified is True
            assert meta.metadata["generation_type"] == "ai_generated"
            assert meta.metadata["provider"] == "ai_horde"
            assert out_file.exists()


def test_threed_adapter_gltf_and_obj_generation():
    with tempfile.TemporaryDirectory() as tmpdir:
        cfg = GameDevConfig.load()
        adapter = ThreeDAssetAdapter(cfg)
        output_dir = Path(tmpdir)

        # Generate character
        char_meta = adapter.generate_asset(
            name="test_runner",
            asset_type="character",
            output_dir=output_dir,
            file_format="glb",
        )
        assert char_meta.verified is True
        glb_p = Path(char_meta.file_path)
        assert glb_p.exists()

        # Check binary glTF header: Magic(0x46546C67), Version(2)
        with open(glb_p, "rb") as f:
            magic = f.read(4)
            version = struct.unpack("<I", f.read(4))[0]
            assert magic == b"glTF"
            assert version == 2

        # Check secondary Wavefront OBJ
        obj_p = Path(char_meta.metadata["secondary_obj_path"])
        assert obj_p.exists()
        obj_content = obj_p.read_text(encoding="utf-8")
        assert "v " in obj_content
        assert "f " in obj_content

        # Generate coin
        coin_meta = adapter.generate_asset(
            name="test_coin",
            asset_type="coin",
            output_dir=output_dir,
            file_format="glb",
        )
        assert coin_meta.verified is True
        assert Path(coin_meta.file_path).exists()


def test_voice_output_sanitization():
    adapter = VoiceOutputAdapter(enabled=False)
    # Should not raise exception
    adapter.speak("Hello 'world' with $var and \n newlines", block=False)
    adapter.stop()
    assert not adapter.is_speaking.is_set()


def test_provider_diagnostics_structure():
    diag = ProviderDiagnostics()
    report = diag.run_diagnostics()
    assert "providers" in report
    assert "openrouter" in report["providers"]
    assert "ollama" in report["providers"]
    assert "ai_horde" in report["providers"]
    assert "procedural_3d" in report["providers"]
    assert report["cost_protection"]["free_only_mode"] is True
    # Ensure no raw secret tokens are present in report
    rep_str = str(report)
    assert "sk-or-v1-" not in rep_str
