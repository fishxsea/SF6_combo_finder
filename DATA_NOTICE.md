# Imported frame-data attribution

The imported character records in `characters.json` identified by
`data_source.provider`, and the upstream snapshots in `data/sf6-sensei/`, are offered
under **Creative Commons Attribution-ShareAlike 4.0 International**:
https://creativecommons.org/licenses/by-sa/4.0/

Original contributors: **SuperCombo Wiki contributors**.
Original work: https://wiki.supercombo.gg/w/Street_Fighter_6
Each move retains its character frame-data page URL in `sources`.

Structured dataset: **Ryo Sogawa / SF6 Sensei contributors**.
https://github.com/RyoSogawa/sf6-sensei
Source files: https://github.com/RyoSogawa/sf6-sensei/tree/main/packages/data/src/generated
Upstream notice: https://github.com/RyoSogawa/sf6-sensei/blob/main/NOTICE

Retrieved for this project on October 7, 2026. Original upstream fetch dates
remain in the snapshots and each character's `data_source.fetched_at`.
The files are snapshots, not live updates or guarantees of current-patch accuracy.

## Changes

Snapshots were retrieved through the browsing tool, reconstructed as JSON,
and formatted for local use. Literal line breaks within source strings were
escaped where necessary. The snapshot move arrays retain the supplied records,
including missing values and conditional variants. `sa-levels.json` supplies
the upstream mapping of inputs to Super Art levels.

`import_roster.py` converts those records to this project's move schema:

- Maps categories, notation, costs, explicit damage expressions and permissions.
- Marks unsupported/ambiguous variants and missing fields as excluded from
  automatic generation, preserving reasons and references to their source records.
- Requires known normal hitstun before using a normalized hit-advantage value
  as a grounded link, and preserves exceptional punish-counter values.
- Uses explicitly listed DL0 damage for Jamie's baseline moves when available.
- Adds conservative two-light patterns and explicitly documented chain destinations.
- Excludes charge, aerial-special, target-combo, grab, install and other unmodeled
  state-dependent routes from automatic generation.
- Leaves imported special continuations unknown instead of extrapolating juggles.

Derived imported records remain under CC-BY-SA-4.0. `data/sf6-sensei/aki.json`
contains the pre-existing reviewed A.K.I. records extracted from the app database,
with their existing sources. It uses the app schema and is not an SF6 Sensei
snapshot. The importer loads those records directly rather than converting them.
This notice concerns the imported data; no SF6 Sensei source code was copied.

`import_documented.py` makes recipe-local copies of imported records for target
combo stages, motion-free follow-ups and explicit meter costs. These derived
move records retain the upstream source index and attribution and remain under
CC-BY-SA-4.0. The published-route snapshot transcribes functional game commands
and retains guide/trial references; it does not redistribute guide prose.

Street Fighter, fighter names and related marks belong to their respective
owners. This project is not endorsed by Capcom or the source contributors.
