"""
MIND GameDev — Automated Unit & Integration Tests for AI Image-to-3D Pipeline.
Validates:
1. Image generation success.
2. Image transfer to the coding model.
3. Vision analysis receives the actual image.
4. Python script generation.
5. Invalid script rejection (security AST validator).
6. Blender executable discovery.
7. Blender execution success (genuine local Blender execution).
8. Blender execution failure handling (single-turn error recovery).
9. GLB export verification (glTF 2.0 binary verification).
10. Frontend progress updates (all 8 stages emitted).
11. Final asset delivery.
"""

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

# Ensure repo root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from MIND_GameDev.config import GameDevConfig
from MIND_GameDev.models import ActionType
from MIND_GameDev.tools.instruction_parser import InstructionParser, UserInstruction
from MIND_GameDev.adapters.image_adapter import ImageAssetAdapter
from MIND_GameDev.adapters.coding_adapter import CodingProviderAdapter
from MIND_GameDev.adapters.blender_adapter import BlenderAdapter, BlenderScriptSecurityError
from MIND_GameDev.adapters.threed_adapter import ThreeDAssetAdapter
from MIND_GameDev.orchestrator import GameDevOrchestrator


class TestImageTo3DPipeline(unittest.TestCase):
    """Full test suite for the AI Image-to-3D Reconstruction workflow."""

    @classmethod
    def setUpClass(cls):
        cls.config = GameDevConfig.load()
        cls.blender_adapter = BlenderAdapter(cls.config)
        cls.test_workspace = REPO_ROOT / "Workspace" / "test_unit_pipeline"
        cls.test_workspace.mkdir(parents=True, exist_ok=True)

    @classmethod
    def tearDownClass(cls):
        # Clean up test workspace
        if cls.test_workspace.exists():
            import shutil
            shutil.rmtree(cls.test_workspace, ignore_errors=True)

    def test_01_instruction_parser_3d_routing(self):
        """Tests that natural language dragon and 3D asset prompts route to ActionType.RECONSTRUCT_3D."""
        prompts = [
            ("MIND, create a low-poly frost dragon for my fantasy survival game.", "frost_dragon"),
            ("Create a stylized low-poly frost dragon for my fantasy survival game.", "frost_dragon"),
            ("reconstruct a 3d crystal", "crystal"),
            ("generate a 3d model of a cyber warrior", "warrior"),
        ]
        for prompt, expected_name in prompts:
            ins = InstructionParser.parse(prompt)
            self.assertEqual(ins.action, ActionType.RECONSTRUCT_3D, f"Failed for '{prompt}'")
            self.assertEqual(ins.project_name, expected_name)

    def test_02_image_generation_success(self):
        """Tests concept reference image generation and file integrity."""
        img_adapter = ImageAssetAdapter(self.config)
        meta = img_adapter.generate_concept_image(
            prompt="stylized low-poly frost dragon",
            name="test_dragon_concept",
            output_dir=self.test_workspace,
        )
        self.assertTrue(Path(meta.file_path).exists())
        self.assertGreater(meta.file_size_bytes, 100)
        self.assertTrue(meta.verified)

    def test_03_image_transfer_and_vision_analysis(self):
        """Tests that vision analysis receives the genuine image file on disk."""
        img_adapter = ImageAssetAdapter(self.config)
        coding_adapter = CodingProviderAdapter(self.config)

        # Generate actual reference image
        meta = img_adapter.generate_concept_image(
            prompt="stylized low-poly frost dragon",
            name="test_transfer_img",
            output_dir=self.test_workspace,
        )

        analysis = coding_adapter.analyze_image_for_3d(meta.file_path, "stylized low-poly frost dragon")
        self.assertTrue(analysis.get("success"))
        self.assertIn("analysis_text", analysis)
        self.assertGreater(len(analysis["analysis_text"]), 50)
        self.assertEqual(analysis.get("image_file"), "test_transfer_img.png")

    def test_04_blender_script_generation(self):
        """Tests procedural Blender script synthesis from visual analysis."""
        coding_adapter = CodingProviderAdapter(self.config)
        analysis = {"analysis_text": "Dragon: cylindrical torso, segmented tail, dual horns, wings."}

        script_res = coding_adapter.generate_blender_script(
            visual_analysis=analysis,
            prompt="stylized low-poly frost dragon",
            target_glb_name="dragon_test.glb",
        )
        self.assertTrue(script_res.get("success"))
        code = script_res.get("code", "")
        self.assertIn("import bpy", code)
        if "Dragon_Torso" in code:
            self.assertIn("Dragon_Tail", code)
        else:
            # Real AI-generated Blender script from live cloud provider
            self.assertTrue("bpy.ops" in code or "bpy.data" in code)
            self.assertIn(
                script_res.get("provider"),
                ["Meta AI Model API", "Groq Cloud LPU", "Google Gemini Cloud", "Cerebras Coding Engine"],
            )

    def test_05_invalid_script_rejection(self):
        """Tests AST security sandbox rejecting forbidden modules and shell executions."""
        malicious_scripts = [
            "import os\nos.system('calc.exe')",
            "import subprocess\nsubprocess.run(['dir'])",
            "import socket\ns = socket.socket()",
            "eval('__import__(\"os\").system(\"echo hack\")')",
        ]
        for script in malicious_scripts:
            is_safe, err = self.blender_adapter.validate_script_safety(script)
            self.assertFalse(is_safe, f"Should have rejected: {script}")
            self.assertIn("Security Violation", err)

    def test_06_blender_executable_discovery(self):
        """Tests local Blender executable discovery."""
        self.assertTrue(self.blender_adapter.is_available(), "Blender executable must be discovered")
        version_str = self.blender_adapter.get_blender_version()
        self.assertIn("Blender", version_str)
        self.assertTrue(self.blender_adapter.blender_path.is_file())

    def test_07_genuine_blender_execution_and_glb_export(self):
        """Performs a genuine, non-mocked Blender background execution producing verified GLB."""
        test_script = """
import bpy
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

# Create geometric crystal
bpy.ops.mesh.primitive_cone_add(vertices=6, radius1=1.0, depth=2.0, location=(0, 0, 1.0))
obj = bpy.context.active_object
obj.name = "UnitCrystal"

mat = bpy.data.materials.new(name="UnitMat")
obj.data.materials.append(mat)
"""
        exec_res = self.blender_adapter.execute_script(
            script_code=test_script,
            workspace_dir=self.test_workspace,
            expected_glb_name="unit_crystal.glb",
            timeout_seconds=30.0,
            render_preview=True,
        )
        self.assertTrue(exec_res.get("success"), f"Blender failed: {exec_res.get('error')}")
        glb_p = Path(exec_res.get("glb_path"))
        self.assertTrue(glb_p.exists())
        self.assertGreater(glb_p.stat().st_size, 500)

        # Geometric GLB validation
        val = ThreeDAssetAdapter.validate_3d_file(glb_p)
        self.assertTrue(val.get("is_valid"))
        self.assertEqual(val.get("format"), "glb")

        # Preview verification
        preview_p = Path(exec_res.get("preview_path"))
        self.assertTrue(preview_p.exists())
        self.assertGreater(preview_p.stat().st_size, 1000)

    def test_08_blender_execution_failure_handling(self):
        """Tests that single-turn automatic correction repairs Blender errors."""
        coding_adapter = CodingProviderAdapter(self.config)
        # Old icosphere call that fails in Blender 5.1
        failing_code = "import bpy\nbpy.ops.mesh.primitive_icosphere_add(radius=1.0)"
        corr = coding_adapter.correct_blender_script(
            script_code=failing_code,
            error_msg='AttributeError: Calling operator "bpy.ops.mesh.primitive_icosphere_add" error, could not be found',
            visual_analysis={"analysis_text": "sphere test"},
        )
        self.assertTrue(corr.get("success"))
        self.assertNotIn("primitive_icosphere_add", corr.get("code"))
        self.assertIn("primitive_uv_sphere_add", corr.get("code"))

    def test_09_frontend_progress_and_final_delivery(self):
        """Tests the complete end-to-end orchestrator pipeline emitting all 8 stages."""
        orch = GameDevOrchestrator(self.config, enable_voice=False)
        stages_captured = []

        def track_progress(msg: str, pct: float):
            stages_captured.append((msg, pct))

        res = orch.execute_command(
            "MIND, create a low-poly frost dragon for my fantasy survival game.",
            progress_callback=track_progress,
        )

        self.assertEqual(res.get("status"), "SUCCESS")
        self.assertTrue(res.get("success"))
        self.assertEqual(res.get("asset_name"), "frost_dragon")

        # Confirm all 8 progress stages were emitted
        stage_names = [msg for msg, _ in stages_captured]
        expected_stages = [
            "1. Generating reference image.",
            "2. Analyzing reference image.",
            "3. Creating Blender script.",
            "4. Validating script.",
            "5. Running Blender.",
            "6. Generating 3D model.",
            "7. Exporting GLB.",
            "8. Completed.",
        ]
        for exp in expected_stages:
            self.assertIn(exp, stage_names, f"Missing stage: {exp}")

        # Confirm final asset artifacts exist on disk
        self.assertTrue(Path(res["glb_path"]).exists())
        self.assertTrue(Path(res["preview_path"]).exists())
        self.assertTrue(Path(res["reference_image"]).exists())
        self.assertGreater(res["file_size_bytes"], 100)


if __name__ == "__main__":
    unittest.main()
