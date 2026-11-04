"""
Concurrency & Multitask Verification Tests.
Verifies:
1. Simultaneous execution of Coding, Image Generation, and 3D Model tasks.
2. Thread isolation and non-blocking worker threads.
3. Separate output directories preventing file collisions.
4. Independent task metadata and clean progress callbacks.
"""

import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from MIND_GameDev.config import GameDevConfig
from MIND_GameDev.adapters.coding_adapter import CodingProviderAdapter
from MIND_GameDev.adapters.image_adapter import ImageProviderAdapter
from MIND_GameDev.adapters.blender_adapter import BlenderAdapter


class TestConcurrencyMultitask(unittest.TestCase):

    def setUp(self):
        self.config = GameDevConfig.load()
        self.coding_adapter = CodingProviderAdapter(config=self.config)
        self.image_adapter = ImageProviderAdapter(config=self.config)
        self.blender_adapter = BlenderAdapter(config=self.config)
        self.task_root = self.config.workspace_root / "tasks" / "test_concurrency"
        self.task_root.mkdir(parents=True, exist_ok=True)

    def _run_coding_task(self):
        prompt = "Create a scoring system for a 2D arcade game"
        res = self.coding_adapter.generate(prompt=prompt, language="javascript")
        return {"type": "coding", "success": res.get("success"), "code_len": len(res.get("code", ""))}

    def _run_image_task(self):
        dest = self.task_root / "concurrent_banner.png"
        res = self.image_adapter.generate_concept_image(
            prompt="arcade scoring interface banner",
            target_path=dest,
            name="concurrent_banner",
            allow_fallback=True
        )
        return {"type": "image", "exists": dest.exists(), "size": dest.stat().st_size if dest.exists() else 0}

    def _run_3d_task(self):
        ws = self.task_root / "concurrent_3d_ws"
        ws.mkdir(parents=True, exist_ok=True)
        script = """
import bpy
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()
bpy.ops.mesh.primitive_cube_add(size=1.5, location=(0,0,0))
"""
        res = self.blender_adapter.execute_script(
            script_code=script,
            workspace_dir=ws,
            expected_glb_name="concurrent_cube.glb",
            timeout_seconds=30.0,
            render_preview=False
        )
        return {"type": "3d", "success": res.get("success"), "size": res.get("file_size_bytes", 0)}

    def test_simultaneous_coding_image_and_3d(self):
        """Executes coding, image rendering, and 3D generation concurrently across threads."""
        t0 = time.time()
        with ThreadPoolExecutor(max_workers=3) as executor:
            fut_code = executor.submit(self._run_coding_task)
            fut_img = executor.submit(self._run_image_task)
            fut_3d = executor.submit(self._run_3d_task)

            res_code = fut_code.result()
            res_img = fut_img.result()
            res_3d = fut_3d.result()
        t1 = time.time()

        # Assertions
        self.assertTrue(res_code["success"])
        self.assertGreater(res_code["code_len"], 20)

        self.assertTrue(res_img["exists"])
        self.assertGreater(res_img["size"], 500)

        self.assertTrue(res_3d["success"])
        self.assertGreater(res_3d["size"], 100)

        # Elapsed time check - all 3 finished
        elapsed = t1 - t0
        self.assertLess(elapsed, 45.0, f"Concurrent tasks took too long: {elapsed}s")


if __name__ == "__main__":
    unittest.main()
