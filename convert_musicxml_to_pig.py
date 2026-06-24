#!/usr/bin/env python3
"""Convert MuseScore-exported MusicXML into PIG-compatible fingering TXT files.

The converter uses music21 as the primary MusicXML compatibility check, then
reads selected raw MusicXML tags that music21 may normalize away, notably
staff numbers and fingering strings such as ``3_1``.

python3 convert_musicxml_to_pig.py --input_dir data/musicxml --output_dir data/pig_txt
"""

from __future__ import annotations

import argparse
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence

from music21 import converter, duration


FINGER_RE = re.compile(r"^[1-5](?:_[1-5])?$")


@dataclass(frozen=True)
class ConverterOptions:
    """Configuration shared across all files in one conversion run."""

    input_dir: Path
    output_dir: Path
    tempo: float | None = None
    fallback_tempo: float = 120.0
    default_on_velocity: int = 64
    default_off_velocity: int = 64
    validate_only: bool = False
    missing_fingering: str = "skip"


@dataclass
class RawMusicXMLNote:
    """A single MusicXML note head after timing and tag extraction."""

    source_index: int
    part_id: str
    part_name: str
    part_index: int
    total_parts: int
    onset_quarters: float
    duration_quarters: float
    pitch_name: str | None
    midi_pitch: int | None
    staff: int | None
    fingering_label: str | None
    is_rest: bool
    is_chord_note: bool
    measure_number: str


@dataclass
class PigNote:
    """One output row in the PIG Dataset fingering text format."""

    note_id: str
    onset_time: float
    offset_time: float
    spelled_pitch: str
    onset_velocity: int
    offset_velocity: int
    channel: int
    finger_number: str
    sort_key: tuple[float, int, int, int]

    def to_line(self) -> str:
        """Serialize the note to exactly eight whitespace-separated fields."""

        return (
            f"{self.note_id} {self.onset_time:.6f} {self.offset_time:.6f} "
            f"{self.spelled_pitch} {self.onset_velocity} {self.offset_velocity} "
            f"{self.channel} {self.finger_number}"
        )


@dataclass
class ValidationReport:
    """Per-file conversion counters and diagnostic details."""

    source_file: Path
    total_notes: int = 0
    converted_notes: int = 0
    skipped_rests: int = 0
    notes_missing_fingering: int = 0
    ambiguous_staff_hand: int = 0
    invalid_finger_labels: int = 0
    chord_notes_without_individual_fingering: int = 0
    substitutions_detected: int = 0
    tempo_used: float | None = None
    tempo_source: str = "unknown"
    details: list[str] = field(default_factory=list)

    def add_detail(self, message: str) -> None:
        """Record one validation detail line."""

        self.details.append(message)

    def to_text(self) -> str:
        """Render a compact human-readable validation report."""

        lines = [
            f"Validation report for: {self.source_file.name}",
            "",
            f"total notes: {self.total_notes}",
            f"converted notes: {self.converted_notes}",
            f"skipped rests: {self.skipped_rests}",
            f"notes missing fingering: {self.notes_missing_fingering}",
            f"notes with ambiguous staff/hand: {self.ambiguous_staff_hand}",
            f"invalid finger labels: {self.invalid_finger_labels}",
            (
                "chord notes without individual fingering: "
                f"{self.chord_notes_without_individual_fingering}"
            ),
            f"substitutions detected: {self.substitutions_detected}",
            f"tempo used: {self.tempo_used:g} ({self.tempo_source})"
            if self.tempo_used is not None
            else f"tempo used: unknown ({self.tempo_source})",
        ]
        if self.details:
            lines.extend(["", "Details:"])
            lines.extend(f"- {detail}" for detail in self.details)
        return "\n".join(lines) + "\n"


class MusicXMLTagHelper:
    """Small namespace-agnostic helpers for MusicXML ElementTree nodes."""

    @staticmethod
    def tag_name(element: ET.Element) -> str:
        """Return the local tag name without an XML namespace."""

        return element.tag.rsplit("}", 1)[-1]

    @classmethod
    def children_named(cls, element: ET.Element, name: str) -> list[ET.Element]:
        """Return direct child elements whose local tag name matches ``name``."""

        return [child for child in list(element) if cls.tag_name(child) == name]

    @classmethod
    def first_child(cls, element: ET.Element, name: str) -> ET.Element | None:
        """Return the first direct child with a matching local tag name."""

        for child in list(element):
            if cls.tag_name(child) == name:
                return child
        return None

    @classmethod
    def child_text(cls, element: ET.Element, name: str) -> str | None:
        """Return stripped text from the first matching direct child."""

        child = cls.first_child(element, name)
        if child is None or child.text is None:
            return None
        text = child.text.strip()
        return text or None

    @classmethod
    def has_child(cls, element: ET.Element, name: str) -> bool:
        """Return whether a direct child with ``name`` exists."""

        return cls.first_child(element, name) is not None

    @classmethod
    def descendants_named(cls, element: ET.Element, name: str) -> list[ET.Element]:
        """Return all descendant elements whose local tag name matches ``name``."""

        return [child for child in element.iter() if cls.tag_name(child) == name]


class MusicXMLTempoExtractor:
    """Extract a practical conversion tempo from MusicXML."""

    def extract_first_tempo(self, path: Path) -> float | None:
        """Return the first positive tempo found in the MusicXML file."""

        root = ET.parse(path).getroot()
        sound_tempo = self._extract_sound_tempo(root)
        if sound_tempo is not None:
            return sound_tempo
        return self._extract_metronome_tempo(root)

    def _extract_sound_tempo(self, root: ET.Element) -> float | None:
        for sound in MusicXMLTagHelper.descendants_named(root, "sound"):
            tempo = self._positive_float(sound.attrib.get("tempo"))
            if tempo is not None:
                return tempo
        return None

    def _extract_metronome_tempo(self, root: ET.Element) -> float | None:
        for metronome in MusicXMLTagHelper.descendants_named(root, "metronome"):
            beat_unit = MusicXMLTagHelper.child_text(metronome, "beat-unit")
            per_minute = self._positive_float(
                MusicXMLTagHelper.child_text(metronome, "per-minute")
            )
            if beat_unit is None or per_minute is None:
                continue
            dots = len(MusicXMLTagHelper.children_named(metronome, "beat-unit-dot"))
            try:
                quarter_length = float(
                    duration.convertTypeToQuarterLength(beat_unit.lower(), dots=dots)
                )
            except duration.DurationException:
                continue
            return per_minute * quarter_length
        return None

    def _positive_float(self, value: str | None) -> float | None:
        if value is None:
            return None
        try:
            number = float(value)
        except ValueError:
            return None
        return number if number > 0 else None


class MusicXMLScoreParser:
    """Parse the MusicXML fields needed for symbolic fingering conversion."""

    def parse(self, path: Path) -> list[RawMusicXMLNote]:
        """Parse a MusicXML file into raw note events."""

        tree = ET.parse(path)
        root = tree.getroot()
        part_names = self._read_part_names(root)
        notes: list[RawMusicXMLNote] = []

        source_index = 0
        parts = MusicXMLTagHelper.children_named(root, "part")
        total_parts = len(parts)
        for part_index, part in enumerate(parts):
            part_id = part.attrib.get("id", f"P{part_index + 1}")
            part_name = part_names.get(part_id, part_id)
            source_index = self._parse_part(
                part=part,
                part_id=part_id,
                part_name=part_name,
                part_index=part_index,
                total_parts=total_parts,
                source_index=source_index,
                output=notes,
            )

        return notes

    def _read_part_names(self, root: ET.Element) -> dict[str, str]:
        part_names: dict[str, str] = {}
        part_list = MusicXMLTagHelper.first_child(root, "part-list")
        if part_list is None:
            return part_names

        for score_part in MusicXMLTagHelper.children_named(part_list, "score-part"):
            part_id = score_part.attrib.get("id")
            name = MusicXMLTagHelper.child_text(score_part, "part-name")
            if part_id and name:
                part_names[part_id] = name
        return part_names

    def _parse_part(
        self,
        part: ET.Element,
        part_id: str,
        part_name: str,
        part_index: int,
        total_parts: int,
        source_index: int,
        output: list[RawMusicXMLNote],
    ) -> int:
        divisions = 1.0
        measure_start_quarters = 0.0

        for measure in MusicXMLTagHelper.children_named(part, "measure"):
            cursor_quarters = measure_start_quarters
            max_position_quarters = measure_start_quarters
            last_note_onset_quarters = measure_start_quarters
            measure_number = measure.attrib.get("number", "?")

            for child in list(measure):
                tag = MusicXMLTagHelper.tag_name(child)
                if tag == "attributes":
                    divisions = self._read_divisions(child, divisions)
                elif tag == "backup":
                    cursor_quarters -= self._duration_quarters(child, divisions)
                elif tag == "forward":
                    cursor_quarters += self._duration_quarters(child, divisions)
                    max_position_quarters = max(max_position_quarters, cursor_quarters)
                elif tag == "note":
                    duration_quarters = self._duration_quarters(child, divisions)
                    is_chord_note = MusicXMLTagHelper.has_child(child, "chord")
                    onset_quarters = (
                        last_note_onset_quarters if is_chord_note else cursor_quarters
                    )
                    if not is_chord_note:
                        last_note_onset_quarters = onset_quarters

                    output.append(
                        self._parse_note(
                            note_element=child,
                            source_index=source_index,
                            part_id=part_id,
                            part_name=part_name,
                            part_index=part_index,
                            total_parts=total_parts,
                            onset_quarters=onset_quarters,
                            duration_quarters=duration_quarters,
                            is_chord_note=is_chord_note,
                            measure_number=measure_number,
                        )
                    )
                    source_index += 1

                    if not is_chord_note:
                        cursor_quarters += duration_quarters
                        max_position_quarters = max(
                            max_position_quarters, cursor_quarters
                        )

            measure_start_quarters = max_position_quarters

        return source_index

    def _parse_note(
        self,
        note_element: ET.Element,
        source_index: int,
        part_id: str,
        part_name: str,
        part_index: int,
        total_parts: int,
        onset_quarters: float,
        duration_quarters: float,
        is_chord_note: bool,
        measure_number: str,
    ) -> RawMusicXMLNote:
        is_rest = MusicXMLTagHelper.has_child(note_element, "rest")
        pitch_name: str | None = None
        midi_pitch: int | None = None
        if not is_rest:
            pitch_name, midi_pitch = self._read_pitch(note_element)

        staff_text = MusicXMLTagHelper.child_text(note_element, "staff")
        staff = self._safe_int(staff_text)
        return RawMusicXMLNote(
            source_index=source_index,
            part_id=part_id,
            part_name=part_name,
            part_index=part_index,
            total_parts=total_parts,
            onset_quarters=onset_quarters,
            duration_quarters=duration_quarters,
            pitch_name=pitch_name,
            midi_pitch=midi_pitch,
            staff=staff,
            fingering_label=self._read_fingering(note_element),
            is_rest=is_rest,
            is_chord_note=is_chord_note,
            measure_number=measure_number,
        )

    def _read_divisions(self, attributes: ET.Element, current: float) -> float:
        divisions_text = MusicXMLTagHelper.child_text(attributes, "divisions")
        if divisions_text is None:
            return current
        try:
            divisions = float(divisions_text)
        except ValueError:
            return current
        return divisions if divisions > 0 else current

    def _duration_quarters(self, element: ET.Element, divisions: float) -> float:
        duration_text = MusicXMLTagHelper.child_text(element, "duration")
        if duration_text is None:
            return 0.0
        try:
            return float(duration_text) / divisions
        except ValueError:
            return 0.0

    def _read_pitch(self, note_element: ET.Element) -> tuple[str, int] | tuple[None, None]:
        pitch = MusicXMLTagHelper.first_child(note_element, "pitch")
        if pitch is None:
            return None, None

        step = MusicXMLTagHelper.child_text(pitch, "step")
        octave_text = MusicXMLTagHelper.child_text(pitch, "octave")
        alter_text = MusicXMLTagHelper.child_text(pitch, "alter") or "0"
        if step is None or octave_text is None:
            return None, None

        try:
            octave = int(octave_text)
            alter = int(float(alter_text))
        except ValueError:
            return None, None

        accidental = "#" * alter if alter > 0 else "b" * abs(alter)
        pitch_name = f"{step.upper()}{accidental}{octave}"
        midi_base = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
        midi_pitch = (octave + 1) * 12 + midi_base[step.upper()] + alter
        return pitch_name, midi_pitch

    def _read_fingering(self, note_element: ET.Element) -> str | None:
        fingering_elements = MusicXMLTagHelper.descendants_named(note_element, "fingering")
        labels = [
            self._clean_fingering_text(element.text)
            for element in fingering_elements
            if element.text
        ]
        labels = [label for label in labels if label]
        if not labels:
            return None

        for label in labels:
            if "_" in label:
                return label

        has_substitution = any(
            element.attrib.get("substitution", "").lower() in {"yes", "true", "1"}
            for element in fingering_elements
        )
        if has_substitution and len(labels) >= 2:
            return "_".join(labels[:2])

        return labels[0]

    def _clean_fingering_text(self, value: str) -> str | None:
        cleaned = re.sub(r"\s+", "", value.strip())
        return cleaned or None

    def _safe_int(self, value: str | None) -> int | None:
        if value is None:
            return None
        try:
            return int(value)
        except ValueError:
            return None


class PigFingeringConverter:
    """Convert parsed MusicXML notes into PIG fingering rows and reports."""

    def __init__(self, options: ConverterOptions) -> None:
        self.options = options
        self.parser = MusicXMLScoreParser()
        self.tempo_extractor = MusicXMLTempoExtractor()

    def convert_directory(self) -> list[ValidationReport]:
        """Convert every supported MusicXML file in the input directory."""

        self.options.output_dir.mkdir(parents=True, exist_ok=True)
        input_files = sorted(
            path
            for path in self.options.input_dir.iterdir()
            if path.is_file() and path.suffix.lower() in {".musicxml", ".xml"}
        )
        reports: list[ValidationReport] = []
        for input_file in input_files:
            reports.append(self.convert_file(input_file))
        return reports

    def convert_file(self, input_file: Path) -> ValidationReport:
        """Convert one MusicXML file and write its TXT/report artifacts."""

        report = ValidationReport(source_file=input_file)
        try:
            converter.parse(str(input_file))
        except Exception as exc:  # pragma: no cover - exact music21 errors vary.
            report.add_detail(f"music21 parse error: {exc}")
            self._write_report(input_file, report)
            return report

        tempo = self._resolve_tempo(input_file, report)
        seconds_per_quarter = 60.0 / tempo

        raw_notes = self.parser.parse(input_file)
        pig_notes = self._convert_notes(raw_notes, report, seconds_per_quarter)
        pig_notes.sort(key=lambda item: item.sort_key)

        for index, pig_note in enumerate(pig_notes, start=1):
            pig_note.note_id = f"N{index:06d}"

        report.converted_notes = len(pig_notes)
        if not self.options.validate_only:
            output_file = self.options.output_dir / f"{input_file.stem}.txt"
            output_file.write_text(
                "".join(f"{pig_note.to_line()}\n" for pig_note in pig_notes),
                encoding="utf-8",
            )

        self._write_report(input_file, report)
        return report

    def _resolve_tempo(self, input_file: Path, report: ValidationReport) -> float:
        if self.options.tempo is not None:
            report.tempo_used = self.options.tempo
            report.tempo_source = "--tempo override"
            return self.options.tempo

        extracted_tempo = self.tempo_extractor.extract_first_tempo(input_file)
        if extracted_tempo is not None:
            report.tempo_used = extracted_tempo
            report.tempo_source = "MusicXML"
            return extracted_tempo

        report.tempo_used = self.options.fallback_tempo
        report.tempo_source = "fallback"
        report.add_detail(f"no MusicXML tempo found; used fallback tempo {self.options.fallback_tempo:g}")
        return self.options.fallback_tempo

    def _convert_notes(
        self,
        raw_notes: Sequence[RawMusicXMLNote],
        report: ValidationReport,
        seconds_per_quarter: float,
    ) -> list[PigNote]:
        pig_notes: list[PigNote] = []

        for raw_note in raw_notes:
            if raw_note.is_rest:
                report.skipped_rests += 1
                continue

            report.total_notes += 1
            channel = self._channel_for(raw_note, report)
            if channel is None:
                continue

            finger = self._normalize_fingering(raw_note, channel, report)
            if finger is None:
                continue

            if raw_note.pitch_name is None or raw_note.midi_pitch is None:
                report.add_detail(self._note_detail(raw_note, "missing pitch data"))
                continue

            onset = raw_note.onset_quarters * seconds_per_quarter
            offset = (raw_note.onset_quarters + raw_note.duration_quarters) * seconds_per_quarter
            pig_notes.append(
                PigNote(
                    note_id="",
                    onset_time=onset,
                    offset_time=offset,
                    spelled_pitch=raw_note.pitch_name,
                    onset_velocity=self.options.default_on_velocity,
                    offset_velocity=self.options.default_off_velocity,
                    channel=channel,
                    finger_number=finger,
                    sort_key=(onset, channel, raw_note.midi_pitch, raw_note.source_index),
                )
            )

        return pig_notes

    def _channel_for(
        self, raw_note: RawMusicXMLNote, report: ValidationReport
    ) -> int | None:
        staff = raw_note.staff
        if staff == 1:
            return 0
        if staff == 2:
            return 1
        if staff is not None:
            report.ambiguous_staff_hand += 1
            report.add_detail(self._note_detail(raw_note, f"unsupported staff {staff}"))
            return None

        inferred_staff = self._infer_staff_from_part(raw_note)
        if inferred_staff == 1:
            return 0
        if inferred_staff == 2:
            return 1

        report.ambiguous_staff_hand += 1
        report.add_detail(self._note_detail(raw_note, "missing staff/hand"))
        return None

    def _infer_staff_from_part(self, raw_note: RawMusicXMLNote) -> int | None:
        name = raw_note.part_name.lower()
        right_markers = ("right", "r.h", "rh", "treble", "primo")
        left_markers = ("left", "l.h", "lh", "bass", "secondo")
        if any(marker in name for marker in right_markers):
            return 1
        if any(marker in name for marker in left_markers):
            return 2
        if raw_note.total_parts == 2:
            return 1 if raw_note.part_index == 0 else 2
        return None

    def _normalize_fingering(
        self, raw_note: RawMusicXMLNote, channel: int, report: ValidationReport
    ) -> str | None:
        label = raw_note.fingering_label
        if label is None:
            report.notes_missing_fingering += 1
            if raw_note.is_chord_note:
                report.chord_notes_without_individual_fingering += 1
            report.add_detail(self._note_detail(raw_note, "missing fingering"))
            return "0" if self.options.missing_fingering == "zero" else None

        if not FINGER_RE.match(label):
            report.invalid_finger_labels += 1
            report.add_detail(self._note_detail(raw_note, f"invalid fingering {label!r}"))
            return None

        if "_" in label:
            report.substitutions_detected += 1

        if channel == 0:
            return label
        return "_".join(f"-{finger}" for finger in label.split("_"))

    def _write_report(self, input_file: Path, report: ValidationReport) -> None:
        report_file = self.options.output_dir / f"{input_file.stem}.validation.txt"
        report_file.write_text(report.to_text(), encoding="utf-8")

    def _note_detail(self, raw_note: RawMusicXMLNote, message: str) -> str:
        pitch = raw_note.pitch_name or "unknown pitch"
        staff = raw_note.staff if raw_note.staff is not None else "missing"
        return (
            f"{message}: part={raw_note.part_name!r}, measure={raw_note.measure_number}, "
            f"offset_quarters={raw_note.onset_quarters:g}, pitch={pitch}, staff={staff}"
        )


def build_arg_parser() -> argparse.ArgumentParser:
    """Create the command-line argument parser."""

    parser = argparse.ArgumentParser(
        description=(
            "Convert MuseScore-exported MusicXML files into PIG-compatible "
            "piano fingering TXT files."
        )
    )
    parser.add_argument("--input_dir", type=Path, required=True)
    parser.add_argument("--output_dir", type=Path, required=True)
    parser.add_argument(
        "--tempo",
        type=float,
        default=None,
        help="Override MusicXML tempo in quarter notes per minute. Defaults to auto-detect.",
    )
    parser.add_argument(
        "--fallback_tempo",
        type=float,
        default=120.0,
        help="Tempo to use when MusicXML has no readable tempo and --tempo is omitted.",
    )
    parser.add_argument("--default_on_velocity", type=int, default=64)
    parser.add_argument("--default_off_velocity", type=int, default=64)
    parser.add_argument("--validate_only", action="store_true")
    parser.add_argument(
        "--missing_fingering",
        choices=("skip", "zero"),
        default="skip",
        help="Skip notes missing fingering, or output them with finger_number=0.",
    )
    return parser


def validate_options(options: ConverterOptions) -> None:
    """Validate CLI options before conversion begins."""

    if not options.input_dir.exists() or not options.input_dir.is_dir():
        raise ValueError(f"input_dir does not exist or is not a directory: {options.input_dir}")
    if options.tempo is not None and options.tempo <= 0:
        raise ValueError("--tempo must be greater than 0")
    if options.fallback_tempo <= 0:
        raise ValueError("--fallback_tempo must be greater than 0")
    for value_name, value in (
        ("--default_on_velocity", options.default_on_velocity),
        ("--default_off_velocity", options.default_off_velocity),
    ):
        if value < 0 or value > 127:
            raise ValueError(f"{value_name} must be between 0 and 127")


def main(argv: Iterable[str] | None = None) -> int:
    """CLI entry point."""

    args = build_arg_parser().parse_args(argv)
    options = ConverterOptions(
        input_dir=args.input_dir,
        output_dir=args.output_dir,
        tempo=args.tempo,
        fallback_tempo=args.fallback_tempo,
        default_on_velocity=args.default_on_velocity,
        default_off_velocity=args.default_off_velocity,
        validate_only=args.validate_only,
        missing_fingering=args.missing_fingering,
    )

    try:
        validate_options(options)
        reports = PigFingeringConverter(options).convert_directory()
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    converted_files = len(reports)
    converted_notes = sum(report.converted_notes for report in reports)
    print(
        f"Processed {converted_files} file(s); converted {converted_notes} note(s). "
        f"Reports written to {options.output_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
