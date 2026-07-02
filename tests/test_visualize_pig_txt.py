import tempfile
import unittest
from pathlib import Path

from visualize_pig_txt import MidiFileWriter, PigTxtParser, PigVisualizationTool, VisualizationOptions


PIG_TEXT = """//Version: PianoFingering_v170101
0 0.000 0.500 C4 64 80 0 1
1 0.250 0.750 F#4 64 80 0 4_1
2 0.500 1.000 C3 64 80 1 -5
"""


class PigVisualizerTest(unittest.TestCase):
    def test_parser_accepts_numeric_ids_and_substitutions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "piece.txt"
            path.write_text(PIG_TEXT, encoding="utf-8")

            result = PigTxtParser().parse(path)

            self.assertEqual(len(result.notes), 3)
            self.assertEqual(result.warnings, [])
            self.assertEqual(result.notes[1].pitch_midi, 66)
            self.assertEqual(result.notes[1].display_finger, "4_1")
            self.assertEqual(result.notes[2].hand, "left")

    def test_tool_writes_html_by_default_without_midi(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            input_file = Path(tmp) / "piece.txt"
            output_dir = Path(tmp) / "out"
            input_file.write_text(PIG_TEXT, encoding="utf-8")

            result = PigVisualizationTool(
                VisualizationOptions(input_file=input_file, output_dir=output_dir)
            ).run()

            self.assertEqual(len(result.notes), 3)
            self.assertFalse((output_dir / "piece.mid").exists())
            self.assertTrue((output_dir / "piece.html").exists())
            html = (output_dir / "piece.html").read_text(encoding="utf-8")
            self.assertIn("PIG Piano Roll", html)
            self.assertIn('id="labels-container"', html)
            self.assertIn("pianoRollContainer.scrollTop", html)


    def test_midi_writer_uses_internal_seconds_mapping(self) -> None:
        writer = MidiFileWriter()

        self.assertEqual(writer.tempo, 60.0)
        self.assertEqual(writer.ticks_per_quarter, 1000)
        self.assertEqual(writer._seconds_to_ticks(1.25), 1250)

    def test_tool_writes_midi_when_requested(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            input_file = Path(tmp) / "piece.txt"
            output_dir = Path(tmp) / "out"
            input_file.write_text(PIG_TEXT, encoding="utf-8")

            PigVisualizationTool(
                VisualizationOptions(
                    input_file=input_file, output_dir=output_dir, make_midi=True
                )
            ).run()

            self.assertTrue((output_dir / "piece.mid").exists())
            self.assertTrue((output_dir / "piece.html").exists())


if __name__ == "__main__":
    unittest.main()
