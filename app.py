#!/usr/bin/env python3
"""Flask UI for MusicXML -> PIG conversion and PIG piano-roll visualization."""

from __future__ import annotations

import json
import os
import shutil
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from flask import (
    Flask,
    abort,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

from convert_and_visualize import MusicXMLToPigPipeline, PipelineOptions
from visualize_pig_txt import PigVisualizationTool, VisualizationOptions


ALLOWED_MUSICXML_EXTENSIONS = {".musicxml", ".xml"}
ALLOWED_PIG_EXTENSIONS = {".txt"}
DEFAULT_MAX_CONTENT_LENGTH = 20 * 1024 * 1024
DEFAULT_JOB_RETENTION_HOURS = 24.0


@dataclass(frozen=True)
class WebArtifact:
    """One downloadable or embeddable file produced by a web job."""

    label: str
    relative_path: str
    kind: str


@dataclass(frozen=True)
class WebJobResult:
    """Metadata written after a successful web job."""

    job_id: str
    title: str
    mode: str
    summary: str
    preview_path: str | None
    artifacts: list[WebArtifact]
    warnings: list[str]

    def to_json(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "title": self.title,
            "mode": self.mode,
            "summary": self.summary,
            "preview_path": self.preview_path,
            "artifacts": [artifact.__dict__ for artifact in self.artifacts],
            "warnings": self.warnings,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "WebJobResult":
        return cls(
            job_id=data["job_id"],
            title=data["title"],
            mode=data["mode"],
            summary=data["summary"],
            preview_path=data.get("preview_path"),
            artifacts=[WebArtifact(**artifact) for artifact in data.get("artifacts", [])],
            warnings=list(data.get("warnings", [])),
        )


class WebJobService:
    """Create isolated upload/output folders and run the existing tools."""

    def __init__(self, storage_root: Path, job_retention_hours: float) -> None:
        self.storage_root = storage_root
        self.job_retention_seconds = max(0.0, job_retention_hours * 60 * 60)
        self.storage_root.mkdir(parents=True, exist_ok=True)
        self.cleanup_old_jobs()

    def cleanup_old_jobs(self) -> None:
        """Remove old generated jobs so public deployments do not accumulate files."""

        if self.job_retention_seconds <= 0:
            return
        cutoff = time.time() - self.job_retention_seconds
        for child in self.storage_root.iterdir():
            if not child.is_dir():
                continue
            try:
                if child.stat().st_mtime < cutoff:
                    shutil.rmtree(child)
            except OSError:
                # A cleanup failure should not block a user's conversion job.
                continue

    def convert_musicxml(self, upload: FileStorage, form: dict[str, str]) -> WebJobResult:
        """Run the full MusicXML -> PIG -> HTML pipeline for one uploaded file."""

        job_id, job_dir = self._create_job_dir()
        input_dir = job_dir / "input_musicxml"
        output_dir = job_dir / "output"
        input_dir.mkdir(parents=True, exist_ok=True)
        source_file = self._save_upload(upload, input_dir, ALLOWED_MUSICXML_EXTENSIONS)

        options = PipelineOptions(
            input_dir=input_dir,
            output_dir=output_dir,
            tempo=self._optional_float(form.get("tempo")),
            fallback_tempo=self._float_or_default(form.get("fallback_tempo"), 120.0),
            default_on_velocity=self._int_or_default(form.get("default_on_velocity"), 64),
            default_off_velocity=self._int_or_default(form.get("default_off_velocity"), 64),
            missing_fingering=form.get("missing_fingering", "skip"),
            make_midi=form.get("midi") == "on",
        )
        result = MusicXMLToPigPipeline(options).run()
        artifacts = self._pipeline_artifacts(job_dir, source_file.stem, options.make_midi)
        preview = self._first_existing(
            job_dir,
            [f"output/visualizations/{source_file.stem}.html"],
        )
        summary = (
            f"Converted {result.converted_notes} note(s) from {source_file.name}; "
            f"visualized {result.visualized_files} file(s)."
        )
        warnings = list(result.skipped_visualizations)
        if result.visualization_warnings:
            warnings.append(f"Visualization warnings: {result.visualization_warnings}")

        return self._write_result(
            job_dir,
            WebJobResult(
                job_id=job_id,
                title=f"MusicXML conversion: {source_file.name}",
                mode="musicxml",
                summary=summary,
                preview_path=preview,
                artifacts=artifacts,
                warnings=warnings,
            ),
        )

    def visualize_pig(self, upload: FileStorage, form: dict[str, str]) -> WebJobResult:
        """Render a piano-roll verifier for one uploaded PIG TXT file."""

        job_id, job_dir = self._create_job_dir()
        input_dir = job_dir / "input_pig"
        output_dir = job_dir / "output" / "visualizations"
        input_dir.mkdir(parents=True, exist_ok=True)
        source_file = self._save_upload(upload, input_dir, ALLOWED_PIG_EXTENSIONS)

        options = VisualizationOptions(
            input_file=source_file,
            output_dir=output_dir,
            make_midi=form.get("midi") == "on",
            make_html=True,
        )
        result = PigVisualizationTool(options).run()
        artifacts = self._pig_visualizer_artifacts(job_dir, source_file, options.make_midi)
        preview = self._first_existing(job_dir, [f"output/visualizations/{source_file.stem}.html"])
        summary = f"Visualized {len(result.notes)} note(s) from {source_file.name}."

        return self._write_result(
            job_dir,
            WebJobResult(
                job_id=job_id,
                title=f"PIG visualizer: {source_file.name}",
                mode="pig_txt",
                summary=summary,
                preview_path=preview,
                artifacts=artifacts,
                warnings=result.warnings,
            ),
        )

    def load_result(self, job_id: str) -> WebJobResult | None:
        metadata_path = self._job_dir(job_id) / "result.json"
        if not metadata_path.exists():
            return None
        return WebJobResult.from_json(json.loads(metadata_path.read_text(encoding="utf-8")))

    def job_dir(self, job_id: str) -> Path:
        return self._job_dir(job_id)

    def _create_job_dir(self) -> tuple[str, Path]:
        self.cleanup_old_jobs()
        job_id = uuid.uuid4().hex
        job_dir = self._job_dir(job_id)
        job_dir.mkdir(parents=True, exist_ok=False)
        return job_id, job_dir

    def _job_dir(self, job_id: str) -> Path:
        # Keep job IDs opaque and path-safe before using them in filesystem paths.
        if not job_id or any(char not in "0123456789abcdef" for char in job_id):
            abort(404)
        return self.storage_root / job_id

    def _save_upload(
        self, upload: FileStorage, destination: Path, allowed_extensions: set[str]
    ) -> Path:
        if not upload or not upload.filename:
            raise ValueError("Please choose a file to upload.")
        filename = secure_filename(upload.filename)
        suffix = Path(filename).suffix.lower()
        if suffix not in allowed_extensions:
            allowed = ", ".join(sorted(allowed_extensions))
            raise ValueError(f"Unsupported file type {suffix!r}. Expected: {allowed}.")
        target = destination / filename
        upload.save(target)
        return target

    def _pipeline_artifacts(self, job_dir: Path, stem: str, include_midi: bool) -> list[WebArtifact]:
        candidates = [
            WebArtifact("PIG TXT", f"output/pig_txt/{stem}.txt", "txt"),
            WebArtifact("Validation report", f"output/pig_txt/{stem}.validation.txt", "txt"),
            WebArtifact("Piano-roll HTML", f"output/visualizations/{stem}.html", "html"),
        ]
        if include_midi:
            candidates.append(WebArtifact("MIDI", f"output/visualizations/{stem}.mid", "midi"))
        return [artifact for artifact in candidates if (job_dir / artifact.relative_path).exists()]

    def _pig_visualizer_artifacts(
        self, job_dir: Path, source_file: Path, include_midi: bool
    ) -> list[WebArtifact]:
        candidates = [
            WebArtifact("Uploaded PIG TXT", f"input_pig/{source_file.name}", "txt"),
            WebArtifact("Piano-roll HTML", f"output/visualizations/{source_file.stem}.html", "html"),
        ]
        if include_midi:
            candidates.append(WebArtifact("MIDI", f"output/visualizations/{source_file.stem}.mid", "midi"))
        warnings = WebArtifact("Warnings", f"output/visualizations/{source_file.stem}.warnings.txt", "txt")
        candidates.append(warnings)
        return [artifact for artifact in candidates if (job_dir / artifact.relative_path).exists()]

    def _first_existing(self, job_dir: Path, relative_paths: list[str]) -> str | None:
        for relative_path in relative_paths:
            if (job_dir / relative_path).exists():
                return relative_path
        return None

    def _write_result(self, job_dir: Path, result: WebJobResult) -> WebJobResult:
        (job_dir / "result.json").write_text(
            json.dumps(result.to_json(), indent=2), encoding="utf-8"
        )
        return result

    def _optional_float(self, value: str | None) -> float | None:
        if value is None or not value.strip():
            return None
        return float(value)

    def _float_or_default(self, value: str | None, default: float) -> float:
        parsed = self._optional_float(value)
        return default if parsed is None else parsed

    def _int_or_default(self, value: str | None, default: int) -> int:
        if value is None or not value.strip():
            return default
        return int(value)


def _env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None or not value.strip():
        return default
    return int(value)


def _env_float(name: str, default: float) -> float:
    value = os.environ.get(name)
    if value is None or not value.strip():
        return default
    return float(value)


def create_app(storage_root: Path | None = None) -> Flask:
    """Create the Flask app, optionally using a test-specific storage root."""

    app = Flask(__name__, template_folder="web/templates", static_folder="web/static")
    app.config["MAX_CONTENT_LENGTH"] = _env_int("MAX_UPLOAD_MB", 20) * 1024 * 1024
    app.config["WEB_STORAGE_ROOT"] = storage_root or Path(os.environ.get("WEB_STORAGE_ROOT", "web_runs"))
    app.config["WEB_JOB_RETENTION_HOURS"] = _env_float(
        "WEB_JOB_RETENTION_HOURS", DEFAULT_JOB_RETENTION_HOURS
    )
    service = WebJobService(
        Path(app.config["WEB_STORAGE_ROOT"]),
        job_retention_hours=app.config["WEB_JOB_RETENTION_HOURS"],
    )

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.post("/convert-musicxml")
    def convert_musicxml():
        try:
            result = service.convert_musicxml(request.files.get("musicxml_file"), request.form)
        except Exception as exc:
            return render_template("index.html", error=str(exc)), 400
        return redirect(url_for("job_result", job_id=result.job_id))

    @app.post("/visualize-pig")
    def visualize_pig():
        try:
            result = service.visualize_pig(request.files.get("pig_file"), request.form)
        except Exception as exc:
            return render_template("index.html", error=str(exc)), 400
        return redirect(url_for("job_result", job_id=result.job_id))

    @app.get("/jobs/<job_id>")
    def job_result(job_id: str):
        result = service.load_result(job_id)
        if result is None:
            abort(404)
        return render_template("result.html", result=result)

    @app.get("/jobs/<job_id>/files/<path:relative_path>")
    def job_file(job_id: str, relative_path: str):
        download = request.args.get("download") == "1"
        return send_from_directory(
            service.job_dir(job_id), relative_path, as_attachment=download
        )

    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=True, use_reloader=False)
