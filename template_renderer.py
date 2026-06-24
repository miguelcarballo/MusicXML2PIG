"""Render self-contained piano-roll HTML for PIG TXT verification."""

from __future__ import annotations

from pathlib import Path

import jinja2


class TemplateRenderer:
    """Load the local piano-roll template files and render the symbolic verifier."""

    def __init__(self) -> None:
        self._template_dir = Path(__file__).parent / "piano_roll"
        self._env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(str(self._template_dir)),
            autoescape=False,
            keep_trailing_newline=True,
        )

    def _read(self, filename: str) -> str:
        """Read one template file as UTF-8 text."""

        return (self._template_dir / filename).read_text(encoding="utf-8")

    @staticmethod
    def _build_legend_html(fingering_colors: dict[int, str]) -> str:
        """Build the static finger color legend."""

        names = {1: "Thumb", 2: "Index", 3: "Middle", 4: "Ring", 5: "Pinky"}
        items = []
        for finger, color in fingering_colors.items():
            items.append(
                '<div class="legend-item">'
                f'<div class="legend-color" style="background:{color};"></div>'
                f"<span>{finger} - {names[finger]}</span>"
                "</div>"
            )
        items.append(
            '<div class="legend-item">'
            '<div class="legend-color" style="background:#808080;"></div>'
            "<span>Missing fingering</span>"
            "</div>"
        )
        return "".join(items)

    def render_piano_roll(
        self,
        *,
        title: str,
        notes_json: str,
        fingering_colors: dict[int, str],
        colors_json: str,
        stats_json: str,
        metadata_html: str,
        min_pitch: int,
        max_pitch: int,
        max_time: float,
    ) -> str:
        """Render the PIG piano-roll verifier as a complete HTML document."""

        context = {
            "title": title,
            "notes_json": notes_json,
            "colors_json": colors_json,
            "stats_json": stats_json,
            "metadata_html": metadata_html,
            "legend_html": self._build_legend_html(fingering_colors),
            "min_pitch": min_pitch,
            "max_pitch": max_pitch,
            "max_time": max_time,
            "shared_css": self._read("styles.css"),
            "utility_js": self._read("utility.js"),
            "keyboard_js": self._read("keyboard.js"),
            "piano_roll_js": self._read("piano_roll.js"),
        }
        return self._env.get_template("template.html.j2").render(**context)
