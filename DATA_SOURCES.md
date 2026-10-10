# Extending combo coverage

The current roster has 31 fighters, including Yasmine, reviewed October 7, 2026.
The separately curated A.K.I. dataset and the imported datasets are incomplete.
Frame advantage alone cannot establish
every possible combo: projectile travel, hitboxes, accumulated pushback,
launch trajectories, juggle restrictions, stance timing and resource recovery
also matter. Allowing every move after knockdown or a cancel flag would restore
the impossible strings this project previously produced.

## Sources used

The additional 30 characters come from the
[SF6 Sensei generated dataset](https://github.com/RyoSogawa/sf6-sensei/tree/main/packages/data/src/generated),
derived from SuperCombo Wiki under CC-BY-SA-4.0. Source snapshots are bundled in
`data/sf6-sensei/`. The same directory includes `aki.json`, extracted from the
project's existing reviewed A.K.I. data. Its moves are a dictionary in the app's
schema, while the upstream snapshots have raw move arrays.
[DATA_NOTICE.md](DATA_NOTICE.md) records attribution and conversion changes.
`python3 import_roster.py` loads `aki.json` directly and converts the other
character snapshots into the shared `sf_combo_finder/characters.json` database.
It is an offline conversion,
not a patch updater; replace the snapshots with newer source JSON to update.

Every source move is retained, including unsupported variants, with
`source_record_id`, `source_index`, `search_eligible`, and `search_exclusions`.
The index identifies a record when upstream IDs are duplicated. Baseline
searches exclude unmodeled state requirements and unclear damage expressions.
Imported specials can end a timing route but cannot automatically extend into
other attacks. Only two consecutive light entries are admitted without a
whole published recipe. Exceptional punish-counter advantages are preserved;
unknown knockdown/juggle timing never becomes ordinary grounded links.

The upstream Yasmine snapshot lacks many startup/damage values; those moves
remain excluded. Imported target-combo entries retain constituent input counts
but require reviewed full routes before appearing in generated output. Frame
data sources do not supply published combo recipes; `--documented-only` uses
the separately imported published routes described below.

The original A.K.I. references are:

- [Ultimate Frame Data](https://ultimateframedata.com/sf6/aki): measured moves,
  follow-up windows and OD Chaser variants.
- [Frame Data Search](https://frame-search.com/?character_name=A.K.I&lang=en-us&pageNo=2):
  move timings and super-cancel permissions.
- [A.K.I. combo demonstrations](https://note.com/akino_outi/n/n7594fdffc1dc):
  grounded, poisoned, corner, counter, OD Pulse and airborne routes.
- [Additional A.K.I. recipes](https://note.com/konmaosan/n/n2a62ef155df9):
  Drive Rush and poison-conversion examples.
- [The AKI Guide](https://www.scribd.com/document/839104130/The-AKI-Guide):
  light starters, Chaser follow-ups and super extensions.

Published routes retain their source URLs and spacing notes in JSON. Older
recipes require retesting after balance changes. No training-mode verification
was performed for this update. The dataset records coverage limitations under
`characters.aki.combo_search.coverage`.

## Published routes across the roster

The offline snapshot in `data/documented_routes.json` adds 278 recipes to the
twenty existing A.K.I. recipes. It contains reviewed essential starter routes
from [Iori’s SF6 Lab](https://sf6-lab.net/en), with a separate source URL for
each fighter, and 23 historical trial transcriptions from Prima Games:
[Ryu](https://primagames.com/tips/all-ryu-combos-in-street-fighter-6-sf6-listed/)
and [A.K.I.](https://primagames.com/tips/all-a-k-i-combos-in-street-fighter-6-sf6-listed/).
The guide is community material. Prima Games transcribes Capcom trials but
is a secondary publisher, so those entries are labelled **Capcom trial
transcription**, not direct Capcom publications or current-patch verification.
The transcriptions do not specify all trial setup details.

`import_documented.py` compiles explicit move references; it does not generate
new combinations from move names or infer unsupported routes. Target-combo
stages and follow-ups use recipe-local move copies with their own input and
damage. System actions have explicit costs. Missing damage remains unknown.
The importer validates references, preserves separately curated recipes and
can be rerun without duplicating data. `import_roster.py` reapplies it after
regenerating frame records.

The snapshot retains source classes, retrieval/version notes, starting
conditions and unresolved entry numbers/reasons. Counts and limitations are
listed in [DOCUMENTED_COVERAGE.md](DOCUMENTED_COVERAGE.md). None of the character
catalogues is marked exhaustive. Review additional sections and obtain current
in-game trial inputs/setup data before expanding official coverage; do not
substitute guessed chains for missing recipes.

## Adding a complete route

In `data/sf6-sensei/aki.json`, add missing attacks/actions to `moves`, then
append a sourced entry to `documented_combos`. Run `python3 import_roster.py`
to rebuild the shared app database. Recipes marked `documented_import` are
rebuilt from `data/documented_routes.json`; edit that snapshot for those routes.
Use move IDs, not display strings:

```json
{
  "id": "od_pulse_chaser_sa2",
  "moves": ["od_nightshade_pulse", "od_nightshade_chaser", "sa2"],
  "transitions": ["followup", "documented_cancel"],
  "conditions": {
    "position": "midscreen",
    "opponent_state": "grounded",
    "opponent_poisoned": false,
    "hit_type": "normal"
  },
  "sources": ["https://www.scribd.com/document/839104130/The-AKI-Guide"],
  "notes": ["Projectile contact and follow-up timing depend on spacing."]
}
```

There must be one fewer transition than moves. Conditions require a position
(`midscreen`, `corner`, `any`), opponent state (`grounded`, `airborne`), poison
boolean and opening hit (`normal`, `counter`, `punish_counter`). A move's
`requires` prerequisite must immediately precede it. Missing move references,
conditions or prerequisites cause validation errors. Transition labels describe
the published route; they do not create new automatic cancel permissions.

Use `meter_cost: {"drive": 0, "super": 0}` for a follow-up with no additional
resource cost. Follow-up notation should contain only its own input, since the
route already displays the preceding attack. Record exact positional/height
requirements and game version when available. Test with Block After First Hit
before claiming a recipe works on the current patch.

## Obtaining deeper game data

[MMDK](https://github.com/alphazolam/MMDK) provides SF6 PC game-data dump tools
for hit rectangles, action triggers and damage/hit tables, including hitstun,
movement and juggle parameters. Its Dump controls can regenerate data from an
installed game version. This project does not currently import or simulate
those dumps. Unused collision/scaling fields are not copied into the runtime
roster; the source snapshots retain their original data for reference.

Current dumps plus replay/training-mode validation would support a more complete
search. A simulator would also need collision, pushback, airborne trajectories,
cancel windows, projectile state and resource changes. Even then, "all combos"
must specify input-length bounds and scenarios such as character match-up,
starting distance, poison, counter state and screen position. The current CLI
enumerates its supported candidates within the chosen bounds; it does not
guarantee exhaustive coverage of the game.
