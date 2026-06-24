# MuseScore MusicXML to PIG Fingering TXT

This tool converts MuseScore-exported MusicXML files into symbolic piano
fingering TXT files compatible with the PIG Dataset fingering text format.
"Symbolic" means the converter works with score-level note events, pitch
spellings, timings, staff/hand assignment, and fingering labels rather than
audio or expressive MIDI performance data.

PIG Dataset reference: https://beam.kisarazu.ac.jp/~saito/research/PianoFingeringDataset/

Each output note line has exactly eight whitespace-separated fields:

```text
(note_id) (onset_time) (offset_time) (spelled_pitch) (onset_velocity) (offset_velocity) (channel) (finger_number)
```

Column meanings:

```text
note_id          Stable unique note id within the file, for example N000001
onset_time       Note start time in seconds
offset_time      Note end time in seconds
spelled_pitch    Scientific pitch spelling, for example C4, F#3, or Bbb2
onset_velocity   Required PIG velocity field; defaults to 64 when unavailable
offset_velocity  Required PIG release velocity field; defaults to 64 when unavailable
channel          0 for right hand, 1 for left hand
finger_number    1..5 for right hand, -1..-5 for left hand, substitutions allowed
```

The velocity columns are included because this PIG TXT format requires them.
MuseScore MusicXML exports usually do not include real per-note performance
velocities, so the converter writes neutral MIDI-like defaults unless you choose
different values.

The converter is for symbolic fingering data, not MIDI generation. Timing is
derived from MusicXML quarter lengths. By default, the converter reads the
first tempo it can find in the MusicXML file and falls back to 120 BPM only
when no readable tempo is present.

## Install

Use Python 3. Required Python packages are listed in `requirements.txt`.

```bash
python3 -m pip install -r requirements.txt
```

## Enter Fingerings In MuseScore

1. Open the score in MuseScore.
2. Select a note.
3. Add a fingering from the palette, or use MuseScore's fingering text entry.
4. Use labels `1`, `2`, `3`, `4`, or `5`.
5. For finger substitutions, enter underscore notation such as `3_1`.

Right-hand notes should be on staff 1. Left-hand notes should be on staff 2.
The converter writes right-hand fingers as positive values and left-hand
fingers as negative values, so staff 2 `3_1` becomes `-3_-1`.

For chords, add fingering to each note head that needs a line in the output.
Chord notes without individual fingering are called out in the validation
report.

## Export MusicXML From MuseScore

1. Open the finished MuseScore file.
2. Choose `File > Export`.
3. Select `MusicXML` or `Uncompressed MusicXML`.
4. Save the exported `.musicxml` or `.xml` file into your input folder.


## Run The Web App Locally

The Flask web app gives you two browser workflows:

```text
MusicXML upload -> PIG TXT + validation report + embedded piano-roll HTML
PIG TXT upload  -> embedded piano-roll HTML
```

Start it with:

```bash
python3 app.py
```

Then open this local development URL on the same computer:

```text
http://127.0.0.1:5000
```

`127.0.0.1` means "this computer". It is useful for local testing, but it is not the public website URL. For public access, deploy the app with Render or another Python web host.

The MusicXML form accepts `.musicxml` and `.xml` files. The PIG visualizer form accepts `.txt` files. Both forms can optionally create MIDI files. Web outputs are stored under `web_runs/`, with one isolated folder per upload. Old web jobs are cleaned automatically; by default, generated files are kept for 24 hours.

Useful web environment variables:

```text
MAX_UPLOAD_MB=20              # maximum upload size in MB
WEB_JOB_RETENTION_HOURS=24    # how long generated web jobs are kept
WEB_STORAGE_ROOT=web_runs     # folder for temporary web uploads/results
```

## Deploy On Render

This repository includes `render.yaml` for a Render web service. The production start command is:

```bash
gunicorn app:app
```

Recommended GitHub + Render workflow:

1. Create a GitHub repository, for example `MusicXML2PIG`.
2. Push this project to that repository.
3. In Render, choose `New > Web Service` and connect the GitHub repo.
4. Use the included `render.yaml`, or set these manually:

```text
Build Command: pip install -r requirements.txt
Start Command: gunicorn app:app
```

On Render free instances, the app can spin down after inactivity and generated local files can disappear when the service restarts or spins down. Users should download results immediately. For long-term saved jobs, use persistent storage outside the app filesystem.

Before publishing for the scientific community, choose a license and add citation metadata such as `CITATION.cff`.

## One-Step Convert And Visualize

For the normal workflow, run the full pipeline. It converts every MusicXML file to PIG TXT and creates an HTML piano-roll verifier for each result.

```bash
python3 convert_and_visualize.py \
  --input_dir data/musicxml
```

This writes to `./output` by default:

```text
output/pig_txt/example.txt
output/pig_txt/example.validation.txt
output/visualizations/example.html
```

Use `--output_dir data/output` if you want a different root output folder.

Add `--midi` when you also want a MIDI listening file:

```bash
python3 convert_and_visualize.py \
  --input_dir data/musicxml \
  --midi
```

## Run Only The Converter

Use the converter directly when you only need PIG TXT files and validation reports.

```bash
python3 convert_musicxml_to_pig.py \
  --input_dir data/musicxml \
  --output_dir data/pig_txt
```

Useful options for the converter and pipeline:

```text
--tempo 120              # optional override; otherwise auto-detected from MusicXML
--fallback_tempo 120     # used only when MusicXML has no readable tempo
--default_on_velocity 64 # default PIG value when performance velocity is unavailable
--default_off_velocity 64 # default PIG value when release velocity is unavailable
--validate_only
--missing_fingering skip
--missing_fingering zero
--midi                  # pipeline/visualizer: also write MIDI files
--no_html               # pipeline/visualizer: skip HTML output
```

By default, notes missing fingering are skipped and listed in the validation
report. Use `--missing_fingering zero` to keep those notes with
`finger_number=0`. Each validation report also lists the tempo used and whether
it came from MusicXML, `--tempo`, or the fallback tempo.

The fallback tempo is not used when the MusicXML contains a readable tempo; it
only gives the converter a safe way to turn quarter-note offsets into seconds
when the export has no tempo marking. The default velocity values fill required
PIG TXT fields. MuseScore MusicXML exports usually do not include real per-note
performance velocities, so the converter writes neutral MIDI-like defaults
unless you choose different values.

## Output

For each input file, the converter writes:

```text
example.txt
example.validation.txt
```

The TXT file uses the same base filename as the MusicXML file.

## Inspect Validation Reports

Each validation report includes:

```text
total notes
converted notes
skipped rests
notes missing fingering
notes with ambiguous staff/hand
invalid finger labels
chord notes without individual fingering
substitutions detected
```

If a note cannot be converted, the report includes details such as part,
measure, offset, pitch, and staff. Start by fixing missing staff values,
missing fingerings, and invalid labels in MuseScore, then export MusicXML again.


## Visualize Existing PIG TXT Results

Use `visualize_pig_txt.py` directly when you already have a PIG fingering TXT file and only want to create the verifier. MIDI output is optional.

```bash
python3 visualize_pig_txt.py \
  --input examples/001-1_fingering.txt \
  --output_dir pig_visualizations
```

This writes:

```text
pig_visualizations/001-1_fingering.html
```

Add `--midi` when you also want a playable MIDI file for quick listening checks. The HTML file keeps the piano-roll style from the local `piano_roll` templates and shows note timing, pitch, hand, and fingering labels, including substitutions like `4_1`.


## Project Layout

```text
app.py                         # Flask web UI
convert_and_visualize.py       # One-step MusicXML -> PIG TXT -> verifier HTML
convert_musicxml_to_pig.py     # MusicXML folder -> PIG TXT files
visualize_pig_txt.py           # PIG TXT -> piano-roll HTML verifier, optional MIDI
template_renderer.py           # Minimal Jinja2 renderer for the verifier
piano_roll/                    # Template, CSS, and JS for the verifier HTML
web/templates/                 # Flask page templates
web/static/                    # Flask UI styles
examples/                      # Small sample PIG TXT input
tests/                         # Unit tests for CLI tools and Flask app
```
