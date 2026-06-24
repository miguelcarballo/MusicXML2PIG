import tempfile
import textwrap
import unittest
from pathlib import Path

from convert_musicxml_to_pig import ConverterOptions, PigFingeringConverter


SIMPLE_MUSICXML = """\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 3.1 Partwise//EN" "http://www.musicxml.org/dtds/partwise.dtd">
<score-partwise version="3.1">
  <part-list>
    <score-part id="P1">
      <part-name>Piano</part-name>
    </score-part>
  </part-list>
  <part id="P1">
    <measure number="1">
      <attributes>
        <divisions>1</divisions>
        <key><fifths>0</fifths></key>
        <time><beats>4</beats><beat-type>4</beat-type></time>
        <staves>2</staves>
        <clef number="1"><sign>G</sign><line>2</line></clef>
        <clef number="2"><sign>F</sign><line>4</line></clef>
      </attributes>
      <note>
        <pitch><step>C</step><octave>4</octave></pitch>
        <duration>1</duration>
        <type>quarter</type>
        <staff>1</staff>
        <notations><technical><fingering>1</fingering></technical></notations>
      </note>
      <note>
        <chord/>
        <pitch><step>E</step><octave>4</octave></pitch>
        <duration>1</duration>
        <type>quarter</type>
        <staff>1</staff>
        <notations><technical><fingering>3</fingering></technical></notations>
      </note>
      <note>
        <pitch><step>C</step><octave>3</octave></pitch>
        <duration>1</duration>
        <type>quarter</type>
        <staff>2</staff>
        <notations><technical><fingering>3_1</fingering></technical></notations>
      </note>
      <note>
        <rest/>
        <duration>1</duration>
        <type>quarter</type>
        <staff>2</staff>
      </note>
    </measure>
  </part>
</score-partwise>
"""


MISSING_FINGER_MUSICXML = SIMPLE_MUSICXML.replace(
    "<notations><technical><fingering>3</fingering></technical></notations>", ""
)


SOUND_TEMPO_MUSICXML = SIMPLE_MUSICXML.replace(
    "      <note>\n",
    '      <direction><sound tempo="60"/></direction>\n      <note>\n',
    1,
)


METRONOME_TEMPO_MUSICXML = SIMPLE_MUSICXML.replace(
    "      <note>\n",
    """      <direction>
        <direction-type>
          <metronome>
            <beat-unit>half</beat-unit>
            <per-minute>30</per-minute>
          </metronome>
        </direction-type>
      </direction>
      <note>
""",
    1,
)


DOTTED_METRONOME_TEMPO_MUSICXML = SIMPLE_MUSICXML.replace(
    "      <note>\n",
    """      <direction>
        <direction-type>
          <metronome>
            <beat-unit>half</beat-unit>
            <beat-unit-dot/>
            <per-minute>20</per-minute>
          </metronome>
        </direction-type>
      </direction>
      <note>
""",
    1,
)


TWO_PART_MUSICXML = """\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 3.1 Partwise//EN" "http://www.musicxml.org/dtds/partwise.dtd">
<score-partwise version="3.1">
  <part-list>
    <score-part id="P1"><part-name>Piano RH</part-name></score-part>
    <score-part id="P2"><part-name>Piano LH</part-name></score-part>
  </part-list>
  <part id="P1">
    <measure number="1">
      <attributes>
        <divisions>1</divisions>
        <key><fifths>0</fifths></key>
        <time><beats>4</beats><beat-type>4</beat-type></time>
        <clef><sign>G</sign><line>2</line></clef>
      </attributes>
      <note>
        <pitch><step>G</step><octave>4</octave></pitch>
        <duration>1</duration>
        <type>quarter</type>
        <notations><technical><fingering>5</fingering></technical></notations>
      </note>
    </measure>
  </part>
  <part id="P2">
    <measure number="1">
      <attributes>
        <divisions>1</divisions>
        <key><fifths>0</fifths></key>
        <time><beats>4</beats><beat-type>4</beat-type></time>
        <clef><sign>F</sign><line>4</line></clef>
      </attributes>
      <note>
        <pitch><step>G</step><octave>2</octave></pitch>
        <duration>1</duration>
        <type>quarter</type>
        <notations><technical><fingering>5</fingering></technical></notations>
      </note>
    </measure>
  </part>
</score-partwise>
"""


class ConverterTest(unittest.TestCase):
    def test_converts_chords_staffs_and_substitutions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            input_dir = Path(tmp) / "in"
            output_dir = Path(tmp) / "out"
            input_dir.mkdir()
            (input_dir / "piece.musicxml").write_text(
                textwrap.dedent(SIMPLE_MUSICXML), encoding="utf-8"
            )

            options = ConverterOptions(input_dir=input_dir, output_dir=output_dir)
            reports = PigFingeringConverter(options).convert_directory()

            self.assertEqual(len(reports), 1)
            self.assertEqual(reports[0].total_notes, 3)
            self.assertEqual(reports[0].converted_notes, 3)
            self.assertEqual(reports[0].skipped_rests, 1)
            self.assertEqual(reports[0].substitutions_detected, 1)

            output_lines = (output_dir / "piece.txt").read_text(encoding="utf-8").splitlines()
            self.assertEqual(
                output_lines,
                [
                    "N000001 0.000000 0.500000 C4 64 64 0 1",
                    "N000002 0.000000 0.500000 E4 64 64 0 3",
                    "N000003 0.500000 1.000000 C3 64 64 1 -3_-1",
                ],
            )

    def test_validate_only_writes_report_without_txt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            input_dir = Path(tmp) / "in"
            output_dir = Path(tmp) / "out"
            input_dir.mkdir()
            (input_dir / "piece.musicxml").write_text(
                textwrap.dedent(SIMPLE_MUSICXML), encoding="utf-8"
            )

            options = ConverterOptions(
                input_dir=input_dir, output_dir=output_dir, validate_only=True
            )
            PigFingeringConverter(options).convert_directory()

            self.assertFalse((output_dir / "piece.txt").exists())
            self.assertTrue((output_dir / "piece.validation.txt").exists())

    def test_missing_fingering_can_be_written_as_zero(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            input_dir = Path(tmp) / "in"
            output_dir = Path(tmp) / "out"
            input_dir.mkdir()
            (input_dir / "piece.musicxml").write_text(
                textwrap.dedent(MISSING_FINGER_MUSICXML), encoding="utf-8"
            )

            options = ConverterOptions(
                input_dir=input_dir,
                output_dir=output_dir,
                missing_fingering="zero",
            )
            report = PigFingeringConverter(options).convert_directory()[0]

            self.assertEqual(report.notes_missing_fingering, 1)
            self.assertEqual(report.chord_notes_without_individual_fingering, 1)
            output_lines = (output_dir / "piece.txt").read_text(encoding="utf-8").splitlines()
            self.assertIn("N000002 0.000000 0.500000 E4 64 64 0 0", output_lines)

    def test_uses_musicxml_sound_tempo_when_tempo_is_omitted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            input_dir = Path(tmp) / "in"
            output_dir = Path(tmp) / "out"
            input_dir.mkdir()
            (input_dir / "piece.musicxml").write_text(
                textwrap.dedent(SOUND_TEMPO_MUSICXML), encoding="utf-8"
            )

            report = PigFingeringConverter(
                ConverterOptions(input_dir=input_dir, output_dir=output_dir)
            ).convert_directory()[0]

            self.assertEqual(report.tempo_used, 60.0)
            self.assertEqual(report.tempo_source, "MusicXML")
            output_lines = (output_dir / "piece.txt").read_text(encoding="utf-8").splitlines()
            self.assertEqual(output_lines[2], "N000003 1.000000 2.000000 C3 64 64 1 -3_-1")

    def test_uses_musicxml_metronome_tempo_when_sound_tempo_is_absent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            input_dir = Path(tmp) / "in"
            output_dir = Path(tmp) / "out"
            input_dir.mkdir()
            (input_dir / "piece.musicxml").write_text(
                textwrap.dedent(METRONOME_TEMPO_MUSICXML), encoding="utf-8"
            )

            report = PigFingeringConverter(
                ConverterOptions(input_dir=input_dir, output_dir=output_dir)
            ).convert_directory()[0]

            self.assertEqual(report.tempo_used, 60.0)
            self.assertEqual(report.tempo_source, "MusicXML")
            output_lines = (output_dir / "piece.txt").read_text(encoding="utf-8").splitlines()
            self.assertEqual(output_lines[2], "N000003 1.000000 2.000000 C3 64 64 1 -3_-1")

    def test_uses_musicxml_dotted_metronome_tempo(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            input_dir = Path(tmp) / "in"
            output_dir = Path(tmp) / "out"
            input_dir.mkdir()
            (input_dir / "piece.musicxml").write_text(
                textwrap.dedent(DOTTED_METRONOME_TEMPO_MUSICXML), encoding="utf-8"
            )

            report = PigFingeringConverter(
                ConverterOptions(input_dir=input_dir, output_dir=output_dir)
            ).convert_directory()[0]

            self.assertEqual(report.tempo_used, 60.0)
            self.assertEqual(report.tempo_source, "MusicXML")
            output_lines = (output_dir / "piece.txt").read_text(encoding="utf-8").splitlines()
            self.assertEqual(output_lines[2], "N000003 1.000000 2.000000 C3 64 64 1 -3_-1")

    def test_tempo_option_overrides_musicxml_tempo(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            input_dir = Path(tmp) / "in"
            output_dir = Path(tmp) / "out"
            input_dir.mkdir()
            (input_dir / "piece.musicxml").write_text(
                textwrap.dedent(SOUND_TEMPO_MUSICXML), encoding="utf-8"
            )

            report = PigFingeringConverter(
                ConverterOptions(input_dir=input_dir, output_dir=output_dir, tempo=120.0)
            ).convert_directory()[0]

            self.assertEqual(report.tempo_used, 120.0)
            self.assertEqual(report.tempo_source, "--tempo override")
            output_lines = (output_dir / "piece.txt").read_text(encoding="utf-8").splitlines()
            self.assertEqual(output_lines[2], "N000003 0.500000 1.000000 C3 64 64 1 -3_-1")

    def test_infers_hands_from_two_part_exports_without_staff_tags(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            input_dir = Path(tmp) / "in"
            output_dir = Path(tmp) / "out"
            input_dir.mkdir()
            (input_dir / "piece.musicxml").write_text(
                textwrap.dedent(TWO_PART_MUSICXML), encoding="utf-8"
            )

            options = ConverterOptions(input_dir=input_dir, output_dir=output_dir)
            report = PigFingeringConverter(options).convert_directory()[0]

            self.assertEqual(report.ambiguous_staff_hand, 0)
            output_lines = (output_dir / "piece.txt").read_text(encoding="utf-8").splitlines()
            self.assertEqual(
                output_lines,
                [
                    "N000001 0.000000 0.500000 G4 64 64 0 5",
                    "N000002 0.000000 0.500000 G2 64 64 1 -5",
                ],
            )


if __name__ == "__main__":
    unittest.main()
