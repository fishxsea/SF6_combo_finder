# SF6 Combo Finder
<img width="2045" height="1284" alt="Screenshot 2026-10-08 at 2 50 13 PM" src="https://github.com/user-attachments/assets/f045ad4b-f411-47ae-b7ff-429b13379343" />
A Textual terminal browser and CLI for the combos in `sf_combo_finder/characters.json`.
Both interfaces use the same search rules, conditions, difficulty estimates and
raw damage calculations. The dataset contains all 31 fighters released as of
October 7, 2026, including Year 3 and Yasmine. Imported frame data is credited to
[SF6 Sensei / SuperCombo Wiki](DATA_NOTICE.md).

## Download and run (no Python needed)

Once a GitHub Release is published, download the ZIP matching your operating
system and CPU from the repository's **Releases** page. Extract the entire ZIP;
keep the executable and its `_internal` folder together.

- **Windows:** double-click `sf-combo-finder.exe`.
- **macOS:** double-click `Start SF Combo Finder.command` to open Terminal.
- **Linux:** open a terminal in the extracted folder and run `./sf-combo-finder`.
  If your extractor drops permissions, run `chmod +x sf-combo-finder` first.

The app opens a terminal browser. Press **Ctrl+Q** to quit.
These builds are unsigned, so your operating system may ask you to allow the app.
Each build targets the OS and CPU listed in its filename.

For CLI output, run the executable in a terminal with `--cli`, for example:

```bash
./sf-combo-finder --cli ryu --random 5
```

## Install with Python

Requires Python 3.10 or newer. From a downloaded or cloned checkout:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install .
sf-combo-finder
```

On Windows, activate with `.venv\Scripts\Activate.ps1` in PowerShell instead.
`sf-combo-finder-cli ryu --random 5` runs the CLI. You can also install directly
from GitHub with `python -m pip install git+https://github.com/OWNER/REPO.git`
once uploaded, replacing `OWNER/REPO` with this repository's actual address.

## Develop and run from source

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
python combo_tui.py
```

Alternatively, launch from the CLI and prefill its filters:

```bash
python combo_finder.py aki --tui --min-length 3 --max-length 8 --no-jumping
python combo_finder.py aki --tui --documented-only --position corner --opponent-poisoned --max-length 12 -v
```

The browser opens with empty results and waits for **Search** or **Ctrl+R**.
**Random count** always starts blank, even when launched with CLI flags; blank
shows all matches. Enter a count to request a random sample.
The dashboard uses a charcoal background, orange panel accents, purple
headers and plain combo rows, inspired by Bagels. Combos occupy the left
panel; search controls and a session summary sit on the right.
Edit filters in the right panel, then click **Search** or press **Ctrl+R**.
Opponent state defaults to grounded; select Airborne for published air-start routes.
Opponent posture can be unspecified, standing or crouching; it filters published
recipes with explicit posture requirements. It is shown only for fighters with
recorded posture requirements (or All characters). Changes apply on Search or Shuffle.
The panel scrolls to reveal additional filters; hover controls for descriptions.
After the first search, route-option checkboxes and **Opponent poisoned**
automatically refresh the results when toggled. Before that, changes wait for
**Search**. Documented only, Exclude jumping, Exclude specials, Optimistic links
and Explore light chains all reuse the completed cache. Both link/light-chain
modes are prepared during the first search, so toggling them never enumerates
combos again. Favorite/hidden filters and maximum difficulty also filter cached
routes. The first search includes a broader pool and can use more time/memory.
Other search fields apply when you press **Search** or **Shuffle**.
**Opponent poisoned** appears only when A.K.I. is selected; selecting another
fighter or All characters clears that setting. An A.K.I. search loads the selected
poison state first, then prepares the other state in the background. Toggling
poison reuses these pools, updates damage and frame details, and keeps displayed
routes that still connect. Missing sample slots are filled from the new pool;
the selected route stays selected when retained. Counts can change because
Toxic Blossom changes valid follow-ups and published routes have starting-state
requirements. If the alternate pool is still being prepared, current results
remain visible until it is ready. Character, length, meter or starting-condition
changes load a new pool. Route options preserve both poison caches.
**Ctrl+B** or **Filters** toggles the panel. In terminals narrower than 110
columns, it starts hidden and closes when searching to make room for results.
**Shuffle** chooses a fresh sample from the full cached matching pool, defaulting
to 25 when the field is blank. It becomes available after a search completes.
With unchanged filters, it samples and redraws without generating combos again.
Changing character, length, meter or starting conditions rebuilds the pool;
route options, maximum difficulty, Random count and prepared poison variants
reuse it. Samples retain your selected sort order. Search also reuses a matching
cache. Restart the app after changing the roster file to load new data.
Results initially sort by difficulty across lengths and show the bracket on the
left, followed by arrows and controller button colors. **SF notation** changes the
display without rerunning the search.

A.K.I. rows show a **[Poison]** badge beside their difficulty when a move has a
poison-dependent damage, hit-state or timing variant, or a published route
requires starting poisoned. The badge appears with the poison checkbox on or
off. Details name the affected moves and explain any starting-poison requirement.
Some routes apply poison during the combo, so the badge does not always mean
you must start poisoned. Ordinary normal-only strings remain unmarked unless a
published starting-poison condition applies to that route.

The default table columns are **Diff / len / dmg**, **Combo**, **Fighter**,
**Source**, and **Startup**. Damage in the first column is raw damage, with
**[Poison]** beside it when applicable. Click **Columns**, choose the columns
you want, then **Apply**. Your layout is saved for the next launch; **Defaults**
restores these five columns. At least one column must remain selected.
Column changes preserve the current results and selection without searching
or resampling. Hidden information remains available in Details.

Optional columns include **Position**, **Setup / requirements**, and **Published
setups**. A **[Corner]** badge marks a recorded corner
setup; **[CH]**, **[PC]**, and **[Airborne]** mark opening hit/state conditions.
Requirements include close range, charge, stance, height, Drive Rush, walking
and delayed timing when those requirements are recorded. Published setups lists
the known sourced starting-condition variations for the same input sequence,
including attack-ending prefixes. It does not claim exhaustive coverage.
Prefix setup labels inherit their recipe's conditions; a corner-labelled prefix
may also work elsewhere. The additional published setups column exposes known
alternatives. To browse corner and midscreen recipes together, choose Any position.

Source distinguishes published routes from timing candidates. Only recorded
position/setup requirements are shown; generated routes use a dash when no
requirement is recorded. Raw damage is the listed base total, before combo scaling
and poison damage over time. No scaled-damage estimate is displayed.

Use **Sort by** above the results to choose **Character**, **Difficulty**,
**Length**, **Raw damage** or **Startup**, with **Ascending** or **Descending** order.
Character sorting uses fighter display names; difficulty, length and raw damage
sort numerically. Changing the order preserves the selected combo and reorders
existing matches without searching again or choosing a new random sample.
Startup sorts the first damaging attack's startup in frames, using the opening
normal for target combos. It skips movement/stance actions and does not include
movement time, jump travel or charge preparation. Unknown startup stays last in
both directions. The Startup column and selected-combo details show the value.

Select a combo and click **☆ Star** (Ctrl+S) to save a favorite, or **Hide**
(Ctrl+X) to exclude it from future searches. Buttons change to **★ Unstar**
and **Restore** when marked. Rows show a star and, when revealed, `[hidden]`.
The **MY COMBOS** filters let you choose:

- **Starred only**: favorites matching your other search filters.
- **Show hidden**: include excluded combos alongside visible results.
- **Hidden only**: review excluded combos so you can restore them. This takes
  precedence over Show hidden and can be combined with Starred only.

Hidden favorites stay excluded unless Show hidden or Hidden only is enabled.
Marks are saved in `.combo_library.json` in your user app-data directory and survive restarts
and roster reimports. They apply to the exact fighter/input sequence across
starting conditions and sources; prefixes and longer routes remain separate.
Changing notation, difficulty or damage data does not lose your marks. Hiding
does not remove anything from `characters.json`.

These filters apply before random sampling, so hidden routes do not consume
your requested random count. Marking a star normally updates the current row;
when a mark changes filtered membership, the app refilters the cached pool and
refills the sample. Like other route options, these filters refresh after your first Search
and do not trigger a search at startup.

The Details panel shows each combo input vertically with startup, active frames,
recovery on hit and on-hit advantage. Durations use 60 FPS (one frame is
approximately 16.7 ms). Links show the opponent's remaining hitstun after your
recovery, the next attack's startup, the latest start delay and the nominal link
window. Between each input, a bold **Time to input next move** line shows the
window in milliseconds first, or **unknown** when the exact window is unavailable.
For example, A.K.I.'s standing MK (+6) into standing LP (5-frame startup)
allows a latest start delay of one frame (16.7 ms), with two possible start frames
(a nominal 2-frame / 33.3 ms window). This does not measure the game's input
buffer. Cancels show inferred hitstun and its margin, with exact input windows
marked unknown. Missing frame data and individual target-combo timings stay
unknown; hitstop, travel and spacing are not simulated.
The move sequence appears first in Details, followed by poison interactions,
recorded setups, difficulty explanations and source links. Research placeholders,
raw collision/scaling metadata and speculative measurement import code are omitted.

Difficulty gives tight link timing substantial weight across all characters:
1–2 frame links (16.7–33.3 ms) rate **hard**, and 3-frame links (50.0 ms) rate
at least **medium**, even in short combos. Multiple links add to the score.
Details explain each known link's timing and points. Unmeasured chain, cancel and
target-combo input windows stay unknown and are not assigned precision scores.

The selected-combo panel below the table shows its notation, estimated
difficulty, input count, raw damage, evidence type and Drive/Super usage bars.
The session summary shows the active fighter, length range, meter budget and
match counts.

Click **Themes** or press **Ctrl+T** to focus the **Color theme** selector.
Themes apply immediately without rerunning the search. Your choice is saved in
`.tui_preferences.json` in your user app-data directory and restored at the next launch.
All backgrounds, headers and selection surfaces stay dark; controller button colors
and difficulty colors remain consistent. The original Bagels theme is included
alongside these six palettes, in the order supplied:

| Theme | Background | Accents |
| --- | --- | --- |
| Tropical | `#073B4C` | Yellow and mint |
| Ember | `#001524` | Orange and cream |
| Deep Blue | `#001233` | Blue and silver |
| Sage | `#2F3E46` | Sage and pale green |
| Forest | `#081C15` | Emerald and mint |
| Slate | `#0D1B2A` | Steel blue and off-white |

Choose **DISPLAY → Controller buttons → Xbox / PlayStation** to change symbols
without searching again. Your choice is saved alongside the theme. Table rows,
selected-combo details and clipboard copies use the selected layout. Favorites
and exclusions stay the same because they identify SF inputs, not button labels.

| Attack | Xbox | PlayStation |
| --- | --- | --- |
| LP | X (blue) | □ (pink) |
| MP | Y (yellow) | △ (green) |
| HP | RB (white) | R1 (white) |
| LK | A (green) | × (blue) |
| MK | B (red) | ○ (red) |
| HK | RT (white) | R2 (white) |

PlayStation uses the classic symbol colors. Colors are explicit RGB values,
so a terminal palette cannot turn Xbox X purple. Profiles live under
`notation.controllers` in `characters.json`; directions still use the existing
direction mapping. The legacy `notation.buttons` mapping remains supported for
custom Xbox layouts in older data files.

```bash
python3 combo_finder.py ryu --controller playstation --random 5
python3 combo_finder.py --tui --controller playstation
```

Use **Tab / Shift+Tab** to switch controls, arrows to select a result, and
**Enter** on a result or **Ctrl+D** to show details. Details include costs,
transitions, difficulty components, conditions, notes and source links. They
are hidden initially; `-v` opens them at launch. The Notes & sources panel now
uses 45% of the terminal height and grows or shrinks when you resize the terminal
(with a four-line minimum). The results table scrolls
horizontally for long combos and vertically for many results.

**Ctrl+Y** copies the selected combo using the terminal's clipboard protocol
(support depends on the terminal). **F1** opens help, **Escape** cancels a running
search, and **Ctrl+Q** quits. Search runs in a background worker and keeps the
full matching pool in memory for quick shuffling, even when only a sample is
displayed. A.K.I. retains both starting-poison variants after the background
search completes. Large length ranges can take time and use more memory. Cancelled or
failed searches do not retain partial pools. The cache lasts for this app session.

## CLI

The CLI remains available without Textual installed:

```bash
python3 combo_finder.py aki --min-length 3 --max-length 8 --random 5 --no-jumping
python3 combo_finder.py --help
python3 combo_finder.py --list-characters
python3 combo_finder.py ryu --random 5
python3 combo_finder.py chunli --tui
python3 combo_finder.py all --starred-only --random 5
python3 combo_finder.py ryu --hidden-only
python3 combo_finder.py all --show-hidden
```

Raw damage is before scaling and excludes poison damage over time. Difficulty
is a heuristic. Published routes may come from older patches; generated timing
candidates do not simulate hitboxes or accumulated pushback. See
[COMBO_RULES.md](COMBO_RULES.md) and [DATA_SOURCES.md](DATA_SOURCES.md) for search
rules, coverage and adding routes.

CLI searches share the TUI's favorites/exclusions and hide excluded combos by
default. `--library PATH` selects a different saved library, including when
launching `--tui`. `--show-hidden`, `--hidden-only`, and `--starred-only` combine
with the ordinary character, length, meter and route filters.

**Documented only** now works for all 31 characters. The database contains 298
published recipes, including community guide routes and 23 Capcom Combo Trial
transcriptions for Ryu and A.K.I. Source labels distinguish these from generated
timing candidates. The selected-combo panel and details show the source type;
the table has a Source column. CLI output includes the source label, and `-v`
shows links, conditions and the trial/guide entry. For example:

```bash
python3 combo_finder.py all --documented-only --random 5
python3 combo_finder.py ryu --documented-only --max-length 8 -v
python3 combo_finder.py guile --documented-only --no-jumping --random 5
```

Recipes include complete routes and attack-ending prefixes within your length
and meter limits. They are never stitched together. Charge and follow-up inputs
can appear in published recipes even when excluded from automatic generation.
Unknown damage displays as **unknown**, with JSON `raw_total: null`, and sorts
after known totals in both directions. Damage totals remain before scaling.

**This is not every official trial or every published combo.** Official trial
coverage is partial and based on older secondary transcriptions; the community
import covers reviewed starter routes. Ambiguous variants, incomplete strings,
setups and unmodeled conditions remain excluded. See [DOCUMENTED_COVERAGE.md](DOCUMENTED_COVERAGE.md)
for per-character counts and [DATA_SOURCES.md](DATA_SOURCES.md) for provenance.
No current-patch training-mode validation has been performed.

To rebuild the imported records from the bundled snapshot:

```bash
python3 import_roster.py
```

This preserves A.K.I. and regenerates the other characters, replacing manual
edits to their imported records. It also reapplies the reviewed recipe snapshot.
It requires no network or Textual dependency. To rebuild just published recipes:

```bash
python3 import_documented.py
```

## Personal storage

Favorites and preferences are kept outside the installed application:

- Windows: `%LOCALAPPDATA%\SF Combo Finder\`
- macOS: `~/Library/Application Support/SF Combo Finder/`
- Linux: `${XDG_DATA_HOME:-~/.local/share}/sf-combo-finder/`

Set `SF_COMBO_FINDER_HOME` to override this directory. When running a source
checkout, the app reads the old root-level personal files if no new files exist;
the next save writes to the new directory. The old files remain as a backup.
The bundled roster lives at `sf_combo_finder/characters.json`; use `--data`
to choose a different roster.

## Build downloads and publish a release

GitHub Actions tests the app, builds a Python wheel and source archive, and
builds native executable ZIPs on Windows, macOS, and Linux. Push this project
to GitHub and open **Actions → Test and build downloads** to download the build
artifacts. You can also run that workflow manually.

To make downloads available on the public **Releases** page, create and publish
a GitHub Release with a tag such as `v0.1.0`. The workflow builds that tag and
automatically attaches the three executable ZIPs after all builds pass.
Publishing another version repeats the same process. Update the version in
`pyproject.toml` before tagging a new version.

To build on your own machine:

```bash
python -m pip install ".[build]"
python -m unittest -v
python -m build
python scripts/build_release.py
```

Executable ZIPs appear in `dist/releases/`. Run the build on each target OS;
PyInstaller builds for the machine it runs on. The build verifies that the
executable can load its roster and open its browser in a headless test without
relying on checkout files. Executable
archives include the data attribution; the Python package also includes
`DATA_NOTICE.md`. When updating that notice, update the bundled copy in
`sf_combo_finder/` as well.

## Checks

```bash
python -m unittest -v
```


