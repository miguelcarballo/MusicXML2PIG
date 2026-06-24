import os
import tempfile
import textwrap
import unittest
from pathlib import Path

from convert_and_visualize import MusicXMLToPigPipeline, PipelineOptions
from test_converter import SIMPLE_MUSICXML


class PipelineTest(unittest.TestCase):
    def test_pipeline_converts_and_writes_html_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            input_dir = Path(tmp) / "musicxml"
            output_dir = Path(tmp) / "out"
            input_dir.mkdir()
            (input_dir / "piece.musicxml").write_text(
                textwrap.dedent(SIMPLE_MUSICXML), encoding="utf-8"
            )

            result = MusicXMLToPigPipeline(
                PipelineOptions(input_dir=input_dir, output_dir=output_dir)
            ).run()

            self.assertEqual(result.converted_notes, 3)
            self.assertEqual(result.visualized_files, 1)
            self.assertTrue((output_dir / "pig_txt" / "piece.txt").exists())
            self.assertTrue((output_dir / "pig_txt" / "piece.validation.txt").exists())
            self.assertTrue((output_dir / "visualizations" / "piece.html").exists())
            self.assertFalse((output_dir / "visualizations" / "piece.mid").exists())


    def test_pipeline_options_default_output_dir_is_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            old_cwd = Path.cwd()
            try:
                os.chdir(tmp)
                input_dir = Path("musicxml")
                input_dir.mkdir()
                (input_dir / "piece.musicxml").write_text(
                    textwrap.dedent(SIMPLE_MUSICXML), encoding="utf-8"
                )

                result = MusicXMLToPigPipeline(
                    PipelineOptions(input_dir=input_dir)
                ).run()

                self.assertEqual(result.visualized_files, 1)
                self.assertTrue(Path("output/pig_txt/piece.txt").exists())
                self.assertTrue(Path("output/visualizations/piece.html").exists())
            finally:
                os.chdir(old_cwd)

    def test_pipeline_writes_midi_when_requested(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            input_dir = Path(tmp) / "musicxml"
            output_dir = Path(tmp) / "out"
            input_dir.mkdir()
            (input_dir / "piece.musicxml").write_text(
                textwrap.dedent(SIMPLE_MUSICXML), encoding="utf-8"
            )

            result = MusicXMLToPigPipeline(
                PipelineOptions(input_dir=input_dir, output_dir=output_dir, make_midi=True)
            ).run()

            self.assertEqual(result.visualized_files, 1)
            self.assertTrue((output_dir / "visualizations" / "piece.html").exists())
            self.assertTrue((output_dir / "visualizations" / "piece.mid").exists())

    def test_pipeline_validate_only_skips_visualization(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            input_dir = Path(tmp) / "musicxml"
            output_dir = Path(tmp) / "out"
            input_dir.mkdir()
            (input_dir / "piece.musicxml").write_text(
                textwrap.dedent(SIMPLE_MUSICXML), encoding="utf-8"
            )

            result = MusicXMLToPigPipeline(
                PipelineOptions(
                    input_dir=input_dir, output_dir=output_dir, validate_only=True
                )
            ).run()

            self.assertEqual(result.visualized_files, 0)
            self.assertFalse((output_dir / "pig_txt" / "piece.txt").exists())
            self.assertTrue((output_dir / "pig_txt" / "piece.validation.txt").exists())
            self.assertFalse((output_dir / "visualizations").exists())


if __name__ == "__main__":
    unittest.main()
