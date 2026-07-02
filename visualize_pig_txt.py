#!/usr/bin/env python3
"""Visualize PIG fingering TXT files as HTML piano rolls, with optional MIDI.

The input format is the PIG Dataset fingering text format:

    note_id onset_time offset_time spelled_pitch onset_velocity offset_velocity channel finger_number

The tool writes a self-contained HTML piano roll using the local ``piano_roll``
templates. Add ``--midi`` when you also want a standard MIDI file for listening
checks. MIDI export uses the PIG seconds directly, so no user tempo is needed.

python3 visualize_pig_txt.py --input examples/001-1_fingering.txt --output_dir pig_visualizations
"""

from __future__ import annotations

import argparse
import html
import json
import re
import struct
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

from template_renderer import TemplateRenderer


PITCH_RE = re.compile(r"^([A-Ga-g])([#b]*)(-?\d+)$")
FINGER_RE = re.compile(r"^-?[1-5](?:_-?[1-5])?$|^0$")


@dataclass(frozen=True)
class PigNote:
    """One parsed note from a PIG fingering TXT file."""

    note_id: str
    onset: float
    offset: float
    pitch_name: str
    pitch_midi: int
    onset_velocity: int
    offset_velocity: int
    channel: int
    finger_label: str
    source_line: int

    @property
    def hand(self) -> str:
        """Return the hand name used by the piano-roll template."""

        return "right" if self.channel == 0 else "left"

    @property
    def display_finger(self) -> str | None:
        """Return the visual label for the note rectangle."""

        if self.finger_label == "0":
            return None
        return self.finger_label

    @property
    def primary_finger(self) -> int | None:
        """Return the first absolute finger number for coloring."""

        if self.finger_label == "0":
            return None
        first = self.finger_label.split("_", 1)[0]
        return abs(int(first))

    @property
    def is_substitution(self) -> bool:
        """Return whether the finger label uses substitution notation."""

        return "_" in self.finger_label


@dataclass(frozen=True)
class PigParseResult:
    """Parsed notes and non-fatal validation warnings."""

    notes: list[PigNote]
    warnings: list[str]


@dataclass(frozen=True)
class VisualizationOptions:
    """Command-line options for one visualization run."""

    input_file: Path
    output_dir: Path
    title: str | None = None
    make_midi: bool = False
    make_html: bool = True


class PigTxtParser:
    """Parse PIG-compatible fingering TXT files."""

    def parse(self, path: Path) -> PigParseResult:
        """Parse notes from ``path`` while preserving useful warning context."""

        notes: list[PigNote] = []
        warnings: list[str] = []

        for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            line = raw_line.strip()
            if not line or line.startswith("#") or line.startswith("//"):
                continue

            fields = line.split()
            if len(fields) != 8:
                warnings.append(f"line {line_number}: expected 8 fields, found {len(fields)}")
                continue

            try:
                note = self._parse_fields(fields, line_number)
            except ValueError as exc:
                warnings.append(f"line {line_number}: {exc}")
                continue
            notes.append(note)

        notes.sort(key=lambda note: (note.onset, note.channel, note.pitch_midi, note.source_line))
        return PigParseResult(notes=notes, warnings=warnings)

    def _parse_fields(self, fields: Sequence[str], line_number: int) -> PigNote:
        note_id, onset, offset, pitch, on_vel, off_vel, channel, finger = fields
        onset_time = float(onset)
        offset_time = float(offset)
        if offset_time < onset_time:
            raise ValueError("offset_time is before onset_time")

        midi_pitch = self._pitch_to_midi(pitch)
        onset_velocity = self._parse_velocity(on_vel, "onset_velocity")
        offset_velocity = self._parse_velocity(off_vel, "offset_velocity")
        channel_number = int(channel)
        if channel_number not in (0, 1):
            raise ValueError(f"channel must be 0 or 1, found {channel!r}")
        if not FINGER_RE.match(finger):
            raise ValueError(f"invalid finger label {finger!r}")

        return PigNote(
            note_id=note_id,
            onset=onset_time,
            offset=offset_time,
            pitch_name=pitch,
            pitch_midi=midi_pitch,
            onset_velocity=onset_velocity,
            offset_velocity=offset_velocity,
            channel=channel_number,
            finger_label=finger,
            source_line=line_number,
        )

    def _pitch_to_midi(self, pitch: str) -> int:
        match = PITCH_RE.match(pitch)
        if not match:
            raise ValueError(f"invalid spelled pitch {pitch!r}")
        step, accidental_text, octave_text = match.groups()
        base = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
        alter = accidental_text.count("#") - accidental_text.count("b")
        midi = (int(octave_text) + 1) * 12 + base[step.upper()] + alter
        if midi < 0 or midi > 127:
            raise ValueError(f"pitch {pitch!r} maps outside MIDI range")
        return midi

    def _parse_velocity(self, value: str, label: str) -> int:
        velocity = int(value)
        if velocity < 0 or velocity > 127:
            raise ValueError(f"{label} must be between 0 and 127")
        return velocity


class MidiFileWriter:
    """Write a minimal MIDI file using PIG seconds as the timing source."""

    def __init__(self, ticks_per_second: int = 1000) -> None:
        self.tempo = 60.0
        self.ticks_per_quarter = ticks_per_second
        self.ticks_per_second = ticks_per_second

    def write(self, notes: Sequence[PigNote], output_file: Path) -> None:
        """Write one format-0 MIDI file."""

        events = self._build_events(notes)
        track_data = bytearray()
        last_tick = 0

        for tick, payload in events:
            delta = max(tick - last_tick, 0)
            track_data.extend(self._var_len(delta))
            track_data.extend(payload)
            last_tick = tick

        track_data.extend(self._var_len(0))
        track_data.extend(b"\xff\x2f\x00")

        header = b"MThd" + struct.pack(">IHHH", 6, 0, 1, self.ticks_per_quarter)
        track = b"MTrk" + struct.pack(">I", len(track_data)) + bytes(track_data)
        output_file.write_bytes(header + track)

    def _build_events(self, notes: Sequence[PigNote]) -> list[tuple[int, bytes]]:
        microseconds_per_quarter = int(round(60_000_000 / self.tempo))
        events: list[tuple[int, int, bytes]] = [
            (0, 0, b"\xff\x51\x03" + microseconds_per_quarter.to_bytes(3, "big")),
            (0, 1, bytes([0xC0, 0])),
            (0, 1, bytes([0xC1, 0])),
        ]

        for note in notes:
            start_tick = self._seconds_to_ticks(note.onset)
            end_tick = max(self._seconds_to_ticks(note.offset), start_tick + 1)
            midi_channel = note.channel
            note_on = bytes([0x90 | midi_channel, note.pitch_midi, note.onset_velocity])
            note_off = bytes([0x80 | midi_channel, note.pitch_midi, note.offset_velocity])
            events.append((start_tick, 2, note_on))
            # Note-off events sort before note-ons at the same tick to avoid stuck overlaps.
            events.append((end_tick, 1, note_off))

        return [(tick, payload) for tick, _order, payload in sorted(events, key=lambda item: (item[0], item[1]))]

    def _seconds_to_ticks(self, seconds: float) -> int:
        return int(round(seconds * self.ticks_per_second))

    def _var_len(self, value: int) -> bytes:
        buffer = value & 0x7F
        value >>= 7
        while value:
            buffer <<= 8
            buffer |= ((value & 0x7F) | 0x80)
            value >>= 7

        output = bytearray()
        while True:
            output.append(buffer & 0xFF)
            if buffer & 0x80:
                buffer >>= 8
            else:
                break
        return bytes(output)


class PianoRollHtmlRenderer:
    """Render parsed PIG notes with the existing symbolic piano-roll style."""

    BASE_COLORS = {
        1: "#FF6B6B",
        2: "#4ECDC4",
        3: "#45B7D1",
        4: "#96CEB4",
        5: "#FFEAA7",
    }

    def __init__(self) -> None:
        self.template_renderer = TemplateRenderer()

    def render(self, notes: Sequence[PigNote], input_file: Path, title: str | None = None) -> str:
        """Return a complete self-contained HTML piano-roll document."""

        if not notes:
            raise ValueError("cannot render piano roll with zero valid notes")

        notes_payload = [self._note_payload(note) for note in notes]
        colors = self._colors_for(notes)
        min_pitch = max(min(note.pitch_midi for note in notes) - 2, 0)
        max_pitch = min(max(note.pitch_midi for note in notes) + 2, 127)
        max_time = max(note.offset for note in notes)
        page_title = title or f"PIG Piano Roll: {input_file.name}"

        return self.template_renderer.render_piano_roll(
            title=page_title,
            notes_json=json.dumps(notes_payload),
            fingering_colors=self.BASE_COLORS,
            colors_json=json.dumps(colors),
            stats_json=json.dumps(self._stats(notes, max_time)),
            metadata_html=self._metadata_html(input_file, notes),
            min_pitch=min_pitch,
            max_pitch=max_pitch,
            max_time=max_time,
        )

    def _note_payload(self, note: PigNote) -> dict:
        return {
            "id": note.note_id,
            "onset": note.onset,
            "offset": note.offset,
            "pitch_midi": note.pitch_midi,
            "pitch_name": note.pitch_name,
            "hand": note.hand,
            "finger": note.display_finger,
            "finger_label": note.finger_label,
            "velocity_on": note.onset_velocity,
            "velocity_off": note.offset_velocity,
        }

    def _colors_for(self, notes: Sequence[PigNote]) -> dict[str, str]:
        colors = {str(finger): color for finger, color in self.BASE_COLORS.items()}
        colors["0"] = "#808080"
        for note in notes:
            display = note.display_finger
            primary = note.primary_finger
            if display and primary:
                colors[display] = self.BASE_COLORS.get(primary, "#999999")
        return colors

    def _stats(self, notes: Sequence[PigNote], max_time: float) -> dict[str, str]:
        right = sum(1 for note in notes if note.channel == 0)
        left = sum(1 for note in notes if note.channel == 1)
        substitutions = sum(1 for note in notes if note.is_substitution)
        return {
            "Notes": str(len(notes)),
            "Duration": f"{max_time:.2f}s",
            "Pitch Range": self._pitch_range_label(notes),
            "Right": str(right),
            "Left": str(left),
            "Substitutions": str(substitutions),
        }

    def _pitch_range_label(self, notes: Sequence[PigNote]) -> str:
        low = min(notes, key=lambda note: note.pitch_midi)
        high = max(notes, key=lambda note: note.pitch_midi)
        return f"{low.pitch_name} - {high.pitch_name}"

    def _metadata_html(self, input_file: Path, notes: Sequence[PigNote]) -> str:
        first_onset = min(note.onset for note in notes)
        last_offset = max(note.offset for note in notes)
        items = [
            ("Source", input_file.name),
            ("Valid Notes", str(len(notes))),
            ("First Onset", f"{first_onset:.3f}s"),
            ("Last Offset", f"{last_offset:.3f}s"),
        ]
        html_items = []
        for index, (label, value) in enumerate(items):
            if index:
                html_items.append('<span class="run-sep">|</span>')
            html_items.append(
                '<span class="run-item">'
                f'<span class="run-label">{html.escape(label)}</span>'
                f'<span class="run-value">{html.escape(value)}</span>'
                '</span>'
            )
        return '<div class="run-info">' + "".join(html_items) + "</div>"


class PigVisualizationTool:
    """High-level orchestration for TXT parsing, MIDI writing, and HTML rendering."""

    def __init__(self, options: VisualizationOptions) -> None:
        self.options = options
        self.parser = PigTxtParser()
        self.html_renderer = PianoRollHtmlRenderer()

    def run(self) -> PigParseResult:
        """Generate requested artifacts and return the parse result."""

        self.options.output_dir.mkdir(parents=True, exist_ok=True)
        result = self.parser.parse(self.options.input_file)
        if not result.notes:
            raise ValueError("no valid notes found in input file")

        stem = self.options.input_file.stem
        if self.options.make_midi:
            MidiFileWriter().write(result.notes, self.options.output_dir / f"{stem}.mid")
        if self.options.make_html:
            html_doc = self.html_renderer.render(result.notes, self.options.input_file, self.options.title)
            (self.options.output_dir / f"{stem}.html").write_text(html_doc, encoding="utf-8")
        if result.warnings:
            (self.options.output_dir / f"{stem}.warnings.txt").write_text(
                "\n".join(result.warnings) + "\n", encoding="utf-8"
            )
        return result


def build_arg_parser() -> argparse.ArgumentParser:
    """Create the CLI parser."""

    parser = argparse.ArgumentParser(
        description="Render a PIG fingering TXT file as a piano-roll HTML verifier."
    )
    parser.add_argument("--input", required=True, type=Path, help="PIG fingering TXT file")
    parser.add_argument("--output_dir", type=Path, default=Path("pig_visualizations"))
    parser.add_argument("--title", default=None, help="Optional HTML page title")
    parser.add_argument("--midi", action="store_true", help="Also write a .mid file")
    parser.add_argument("--no_html", action="store_true", help="Do not write an .html piano roll")
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    """CLI entry point."""

    args = build_arg_parser().parse_args(argv)
    options = VisualizationOptions(
        input_file=args.input,
        output_dir=args.output_dir,
        title=args.title,
        make_midi=args.midi,
        make_html=not args.no_html,
    )

    try:
        if not options.input_file.exists():
            raise ValueError(f"input file does not exist: {options.input_file}")
        if not options.make_midi and not options.make_html:
            raise ValueError("nothing to do: --no_html was provided without --midi")
        result = PigVisualizationTool(options).run()
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(
        f"Parsed {len(result.notes)} note(s); wrote artifacts to {options.output_dir}. "
        f"Warnings: {len(result.warnings)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
