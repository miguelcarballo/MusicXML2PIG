import io
import os
import tempfile
import textwrap
import unittest
from pathlib import Path

from app import create_app
from test_converter import SIMPLE_MUSICXML
from test_visualize_pig_txt import PIG_TEXT


class FlaskAppTest(unittest.TestCase):
    def make_client(self, storage_root: Path):
        app = create_app(storage_root=storage_root)
        app.config.update(TESTING=True)
        return app.test_client()

    def test_home_page_loads(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            client = self.make_client(Path(tmp) / "runs")

            response = client.get("/")

            self.assertEqual(response.status_code, 200)
            self.assertIn(b"MusicXML to PIG", response.data)
            self.assertIn(b"PIG TXT visualizer", response.data)
            self.assertIn(b"Advanced defaults", response.data)
            self.assertIn(b"Used only if no readable MusicXML tempo is found", response.data)
            self.assertIn(b"Default onset velocity", response.data)
            self.assertIn(b"PIG TXT stores one note per line", response.data)
            self.assertIn(b"note_id onset_time offset_time", response.data)
            self.assertIn(b"velocity columns are required", response.data)
            self.assertIn(b"PIG Dataset website", response.data)


    def test_old_web_jobs_are_cleaned_on_startup(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage_root = Path(tmp) / "runs"
            old_job = storage_root / ("a" * 32)
            old_job.mkdir(parents=True)
            (old_job / "result.json").write_text("{}", encoding="utf-8")
            old_timestamp = 946684800
            os.utime(old_job / "result.json", (old_timestamp, old_timestamp))
            os.utime(old_job, (old_timestamp, old_timestamp))

            self.make_client(storage_root)

            self.assertFalse(old_job.exists())

    def test_musicxml_upload_creates_pig_and_embedded_html(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage_root = Path(tmp) / "runs"
            client = self.make_client(storage_root)
            data = {
                "musicxml_file": (
                    io.BytesIO(textwrap.dedent(SIMPLE_MUSICXML).encode("utf-8")),
                    "piece.musicxml",
                ),
                "fallback_tempo": "120",
                "default_on_velocity": "64",
                "default_off_velocity": "64",
                "missing_fingering": "skip",
            }

            response = client.post(
                "/convert-musicxml",
                data=data,
                content_type="multipart/form-data",
                follow_redirects=True,
            )

            self.assertEqual(response.status_code, 200)
            self.assertIn(b"piece.txt", response.data)
            self.assertIn(b"piece.validation.txt", response.data)
            self.assertIn(b"piece.html", response.data)
            self.assertEqual(len(list(storage_root.glob("*/output/pig_txt/piece.txt"))), 1)
            self.assertEqual(len(list(storage_root.glob("*/output/visualizations/piece.html"))), 1)

    def test_pig_upload_creates_visualizer_html(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage_root = Path(tmp) / "runs"
            client = self.make_client(storage_root)
            data = {
                "pig_file": (io.BytesIO(PIG_TEXT.encode("utf-8")), "piece.txt"),
            }

            response = client.post(
                "/visualize-pig",
                data=data,
                content_type="multipart/form-data",
                follow_redirects=True,
            )

            self.assertEqual(response.status_code, 200)
            self.assertIn(b"Uploaded PIG TXT", response.data)
            self.assertIn(b"piece.html", response.data)
            self.assertEqual(len(list(storage_root.glob("*/output/visualizations/piece.html"))), 1)


if __name__ == "__main__":
    unittest.main()
