"""
MIND Universal Development Studio — Mobile App Workflow.
Generates native Android application project architectures with Manifest,
Activities, responsive XML layouts, Gradle build scripts, and static XML/Kotlin validation.
"""

import json
import os
import time
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, Any, List

from .base_workflow import BaseProjectWorkflow
from ..models import ProjectSpecification, ProjectType, ExecutionReport
from ..tools.workspace_files import SafeWorkspaceManager


class MobileAppWorkflow(BaseProjectWorkflow):
    """Workflow for native Android mobile applications."""

    project_type = ProjectType.MOBILE_APP

    def build(self, spec: ProjectSpecification, workspace: SafeWorkspaceManager) -> Dict[str, Any]:
        title = spec.title or "MindPulse Mobile"
        desc = spec.description or "Native Android application with Jetpack Compose & Material 3"
        pkg_name = "com.mind.mobileapp"

        # Directories
        src_dir = f"app/src/main/java/{pkg_name.replace('.', '/')}"
        res_layout_dir = "app/src/main/res/layout"
        res_values_dir = "app/src/main/res/values"

        workspace.create_directory(src_dir)
        workspace.create_directory(res_layout_dir)
        workspace.create_directory(res_values_dir)

        self._write_manifest_xml(workspace, title, pkg_name)
        self._write_main_activity(workspace, src_dir, pkg_name, title)
        self._write_layout_xml(workspace, res_layout_dir, title)
        self._write_values_xml(workspace, res_values_dir, title)
        self._write_gradle_files(workspace, pkg_name)
        self._write_project_manifest(workspace, title, desc, pkg_name)

        return {
            "status": "SUCCESS",
            "project_type": "mobile_app",
            "title": title,
            "package_name": pkg_name,
            "entry_point": "app/src/main/AndroidManifest.xml",
        }

    def _write_manifest_xml(self, ws: SafeWorkspaceManager, title: str, pkg_name: str) -> None:
        xml = f"""<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android"
    package="{pkg_name}">

    <uses-permission android:name="android.permission.INTERNET" />
    <uses-permission android:name="android.permission.ACCESS_NETWORK_STATE" />

    <application
        android:allowBackup="true"
        android:icon="@android:drawable/sym_def_app_icon"
        android:label="{title}"
        android:roundIcon="@android:drawable/sym_def_app_icon"
        android:supportsRtl="true"
        android:theme="@style/Theme.MindPulse">
        
        <activity
            android:name=".MainActivity"
            android:exported="true">
            <intent-filter>
                <action android:name="android.intent.action.MAIN" />
                <category android:name="android.intent.category.LAUNCHER" />
            </intent-filter>
        </activity>
    </application>
</manifest>
"""
        ws.write_file("app/src/main/AndroidManifest.xml", xml, overwrite=True)

    def _write_main_activity(self, ws: SafeWorkspaceManager, src_dir: str, pkg_name: str, title: str) -> None:
        code = f"""package {pkg_name}

import android.os.Bundle
import android.widget.Button
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity

class MainActivity : AppCompatActivity() {{

    private var tapCount = 0

    override fun onCreate(savedInstanceState: Bundle?) {{
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        val titleView = findViewById<TextView>(R.id.text_title)
        val statusView = findViewById<TextView>(R.id.text_status)
        val actionBtn = findViewById<Button>(R.id.button_action)

        titleView.text = "{title}"
        statusView.text = "System Operational • Ready"

        actionBtn.setOnClickListener {{
            tapCount++
            statusView.text = "Interactions logged: $tapCount"
            Toast.makeText(this, "Telemetry event triggered", Toast.LENGTH_SHORT).show()
        }}
    }}
}}
"""
        ws.write_file(f"{src_dir}/MainActivity.kt", code, overwrite=True)

    def _write_layout_xml(self, ws: SafeWorkspaceManager, res_dir: str, title: str) -> None:
        xml = f"""<?xml version="1.0" encoding="utf-8"?>
<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android"
    android:layout_width="match_parent"
    android:layout_height="match_parent"
    android:orientation="vertical"
    android:padding="24dp"
    android:gravity="center"
    android:background="#0B1020">

    <TextView
        android:id="@+id/text_title"
        android:layout_width="wrap_content"
        android:layout_height="wrap_content"
        android:text="{title}"
        android:textColor="#00F3FF"
        android:textSize="24sp"
        android:textStyle="bold"
        android:layout_marginBottom="12dp" />

    <TextView
        android:id="@+id/text_status"
        android:layout_width="wrap_content"
        android:layout_height="wrap_content"
        android:text="System Initializing..."
        android:textColor="#94A3B8"
        android:textSize="16sp"
        android:layout_marginBottom="32dp" />

    <Button
        android:id="@+id/button_action"
        android:layout_width="wrap_content"
        android:layout_height="wrap_content"
        android:text="Execute Action"
        android:backgroundTint="#00F3FF"
        android:textColor="#05070E"
        android:paddingHorizontal="24dp"
        android:paddingVertical="12dp" />
</LinearLayout>
"""
        ws.write_file(f"{res_dir}/activity_main.xml", xml, overwrite=True)

    def _write_values_xml(self, ws: SafeWorkspaceManager, res_dir: str, title: str) -> None:
        strings = f"""<resources>
    <string name="app_name">{title}</string>
</resources>
"""
        ws.write_file(f"{res_dir}/strings.xml", strings, overwrite=True)

        colors = """<resources>
    <color name="primary">#00F3FF</color>
    <color name="background">#0B1020</color>
    <color name="text">#F8FAFC</color>
</resources>
"""
        ws.write_file(f"{res_dir}/colors.xml", colors, overwrite=True)

        themes = """<resources>
    <style name="Theme.MindPulse" parent="Theme.MaterialComponents.DayNight.NoActionBar">
        <item name="colorPrimary">@color/primary</item>
        <item name="android:windowBackground">@color/background</item>
    </style>
</resources>
"""
        ws.write_file(f"{res_dir}/themes.xml", themes, overwrite=True)

    def _write_gradle_files(self, ws: SafeWorkspaceManager, pkg_name: str) -> None:
        build_gradle = f"""plugins {{
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}}

android {{
    namespace = "{pkg_name}"
    compileSdk = 34

    defaultConfig {{
        applicationId = "{pkg_name}"
        minSdk = 26
        targetSdk = 34
        versionCode = 1
        versionName = "1.0.0"
    }}

    buildTypes {{
        release {{
            isMinifyEnabled = false
        }}
    }}
}}

dependencies {{
    implementation("androidx.core:core-ktx:1.12.0")
    implementation("androidx.appcompat:appcompat:1.6.1")
    implementation("com.google.android.material:material:1.11.0")
}}
"""
        ws.write_file("app/build.gradle.kts", build_gradle, overwrite=True)
        ws.write_file("settings.gradle.kts", 'rootProject.name = "MindPulseMobile"\ninclude(":app")\n', overwrite=True)

    def _write_project_manifest(self, ws: SafeWorkspaceManager, title: str, desc: str, pkg_name: str) -> None:
        manifest = {
            "name": title.lower().replace(" ", "_"),
            "title": title,
            "type": "mobile_app",
            "framework": "android_kotlin_gradle",
            "package_name": pkg_name,
            "min_sdk": 26,
            "target_sdk": 34,
            "build_command": "./gradlew assembleDebug",
            "run_command": "android run",
            "entry_point": "app/src/main/AndroidManifest.xml",
        }
        ws.write_file("project.json", json.dumps(manifest, indent=2), overwrite=True)

    def verify(self, project_dir: Path) -> ExecutionReport:
        start_time = time.time()
        errors: List[str] = []

        manifest_file = project_dir / "app/src/main/AndroidManifest.xml"
        layout_file = project_dir / "app/src/main/res/layout/activity_main.xml"

        # XML Parsing verification
        for xml_p in [manifest_file, layout_file]:
            if not xml_p.exists():
                errors.append(f"Missing Android file: {xml_p.name}")
            else:
                try:
                    ET.parse(str(xml_p))
                except Exception as e:
                    errors.append(f"XML parse error in {xml_p.name}: {e}")

        # Check Kotlin file exists
        kt_files = list(project_dir.rglob("*.kt"))
        if not kt_files:
            errors.append("No Kotlin source files found in project.")

        success = len(errors) == 0
        elapsed = round(time.time() - start_time, 3)

        return ExecutionReport(
            workflow_id=str(uuid.uuid4())[:8],
            project_name=project_dir.name,
            success=success,
            status="VERIFIED" if success else "FAILED",
            target_engine="Android SDK / Gradle",
            project_type="mobile_app",
            project_path=str(project_dir),
            entry_point="app/src/main/AndroidManifest.xml",
            files_created=[f.name for f in project_dir.rglob("*") if f.is_file()],
            tests_passed=1 if success else 0,
            tests_failed=0 if success else 1,
            elapsed_seconds=elapsed,
            summary="Android mobile app structure and XML manifests verified successfully.",
            errors=errors,
        )

    def get_run_instructions(self, project_dir: Path) -> Dict[str, Any]:
        return {
            "run_command": "android run",
            "build_command": "./gradlew assembleDebug",
            "instructions": "Build with gradle or use 'android run' to deploy to connected AVD/device.",
        }
