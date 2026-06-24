#!/usr/bin/env python3
"""Convert MusicXML files to PIG TXT and render piano-roll verification HTML.

This is a convenience pipeline around the two focused tools:

    convert_musicxml_to_pig.py  -> MusicXML folder to PIG TXT
    visualize_pig_txt.py       -> PIG TXT to HTML, optional MIDI
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from convert_musicxml_to_pig import (
    ConverterOptions,
    PigFingeringConverter,
    ValidationReport,
    validate_options as validate_converter_options,
)
from visualize_pig_txt import PigVisualizationTool, VisualizationOptions


@dataclass(frozen=True)
class PipelineOptions:
    """Configuration for a complete MusicXML -> PIG -> visualization run."""

    input_dir: Path
    output_dir: Path = Path("output")
    tempo: float | None = None
    fallback_tempo: float = 120.0
    default_on_velocity: int = 64
    default_off_velocity: int = 64
    missing_fingering: str = "skip"
    validate_only: bool = False
    make_midi: bool = False
    make_html: bool = True

    @property
    def pig_txt_dir(self) -> Path:
        """Directory for PIG TXT files and validation reports."""

        return self.output_dir / "pig_txt"

    @property
    def visualization_dir(self) -> Path:
        """Directory for piano-roll HTML and optional MIDI files."""

        return self.output_dir / "visualizations"


@dataclass
class PipelineResult:
    """Summary of a pipeline run."""

    reports: list[ValidationReport]
    visualized_files: int = 0
    visualization_warnings: int = 0
    skipped_visualizations: list[str] = field(default_factory=list)

    @property
    def converted_notes(self) -> int:
        """Total converted PIG notes across all input files."""

        return sum(report.converted_notes for report in self.reports)


class MusicXMLToPigPipeline:
    """Orchestrate conversion and visualization without duplicating core logic."""

    def __init__(self, options: PipelineOptions) -> None:
        self.options = options

    def run(self) -> PipelineResult:
        """Run conversion first, then render visualizations for created TXT files."""

        converter_options = ConverterOptions(
            input_dir=self.options.input_dir,
            output_dir=self.options.pig_txt_dir,
            tempo=self.options.tempo,
            fallback_tempo=self.options.fallback_tempo,
            default_on_velocity=self.options.default_on_velocity,
            default_off_velocity=self.options.default_off_velocity,
            validate_only=self.options.validate_only,
            missing_fingering=self.options.missing_fingering,
        )
        validate_converter_options(converter_options)
        reports = PigFingeringConverter(converter_options).convert_directory()
        result = PipelineResult(reports=reports)

        if self.options.validate_only or not self.options.make_html and not self.options.make_midi:
            return result

        self.options.visualization_dir.mkdir(parents=True, exist_ok=True)
        for report in reports:
            pig_txt = self.options.pig_txt_dir / f"{report.source_file.stem}.txt"
            if not pig_txt.exists():
                result.skipped_visualizations.append(
                    f"{report.source_file.name}: no PIG TXT file was created"
                )
                continue
            if report.converted_notes == 0:
                result.skipped_visualizations.append(
                    f"{report.source_file.name}: no converted notes to visualize"
                )
                continue

            visualization = PigVisualizationTool(
                VisualizationOptions(
                    input_file=pig_txt,
                    output_dir=self.options.visualization_dir,
                    make_midi=self.options.make_midi,
                    make_html=self.options.make_html,
                )
            ).run()
            result.visualized_files += 1
            result.visualization_warnings += len(visualization.warnings)

        return result


def build_arg_parser() -> argparse.ArgumentParser:
    """Create the pipeline CLI parser."""

    parser = argparse.ArgumentParser(
        description="Convert MusicXML files to PIG TXT and render piano-roll verification HTML."
    )
    parser.add_argument("--input_dir", type=Path, required=True)
    parser.add_argument(
        "--output_dir",
        type=Path,
        default=Path("output"),
        help="Root output folder. Defaults to ./output.",
    )
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
    parser.add_argument(
        "--missing_fingering",
        choices=("skip", "zero"),
        default="skip",
        help="Skip notes missing fingering, or output them with finger_number=0.",
    )
    parser.add_argument(
        "--validate_only",
        action="store_true",
        help="Write validation reports only; skip TXT and visualization outputs.",
    )
    parser.add_argument("--midi", action="store_true", help="Also write .mid files.")
    parser.add_argument("--no_html", action="store_true", help="Do not write piano-roll HTML files.")
    return parser


def validate_pipeline_options(options: PipelineOptions) -> None:
    """Validate pipeline-specific option combinations."""

    if not options.validate_only and not options.make_html and not options.make_midi:
        raise ValueError("nothing to do: --no_html was provided without --midi")


def main(argv: Iterable[str] | None = None) -> int:
    """CLI entry point."""

    args = build_arg_parser().parse_args(argv)
    options = PipelineOptions(
        input_dir=args.input_dir,
        output_dir=args.output_dir,
        tempo=args.tempo,
        fallback_tempo=args.fallback_tempo,
        default_on_velocity=args.default_on_velocity,
        default_off_velocity=args.default_off_velocity,
        missing_fingering=args.missing_fingering,
        validate_only=args.validate_only,
        make_midi=args.midi,
        make_html=not args.no_html,
    )

    try:
        validate_pipeline_options(options)
        result = MusicXMLToPigPipeline(options).run()
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(
        f"Processed {len(result.reports)} file(s); converted {result.converted_notes} note(s); "
        f"visualized {result.visualized_files} file(s)."
    )
    print(f"PIG TXT/reports: {options.pig_txt_dir}")
    if not options.validate_only and (options.make_html or options.make_midi):
        print(f"Visualizations: {options.visualization_dir}")
    if result.visualization_warnings:
        print(f"Visualization warnings: {result.visualization_warnings}")
    for skipped in result.skipped_visualizations:
        print(f"Skipped visualization: {skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
