# Combo search rules

Reviewed October 7, 2026. The output contains published recipes and timing
candidates, not in-game-verified combos. `characters.json` now contains 298
published recipes across 31 characters, including 23 historical Combo Trial
transcriptions. Official trial coverage remains incomplete. Published recipes
cover selected OD projectile follow-ups, Drive Rush, stance, poison, corner,
crumple and juggle routes. The automatic timing search assumes a grounded opponent, close range,
first-active-frame contact and immediate cancels. Jump-in starters additionally
require the appropriate height and position. Repeated attacks can push the
opponent out of range even when every individual transition fits the timing.
Default searches now restrict consecutive light strings to the prefixes listed
in `combo_search.supported_light_sequences` in `characters.json`. This prevents
pairwise chain permission from producing arbitrary long light strings.
Short pairs use known chain permissions or link timing; longer patterns use
published combo recipes. This filter is conservative and may omit real routes;
it does not verify the spacing of the preceding attack or following special.
`--explore-light-chains` restores unrestricted theoretical light strings and
marks them as exploration in verbose/JSON notes.

The full roster now includes 30 additional fighters from the bundled SF6 Sensei
snapshot. These entries use conservative baseline timing searches; unsupported
variants are retained in JSON with exclusion reasons. Imported specials have no
automatic continuations, and imported target combos require complete route
data. Source values and hit states can be incomplete. See
[DATA_NOTICE.md](DATA_NOTICE.md) for attribution and [DATA_SOURCES.md](DATA_SOURCES.md)
for import details. Roster coverage is separate from combo coverage.

## Timing and input rules

- Links require the next attack's startup to fit within the previous attack's
  on-hit advantage. Knockdown advantage describes wake-up timing and is never
  used as a grounded link window.
- A cancel flag establishes permission, not whether the next move combos.
  The earliest cancel budget is `on-hit advantage + active frames - 1 +
  recovery on hit`: the opponent's remaining hitstun after the contact frame.
  The next move must become active within that budget. This calculation is a
  timing inference; hitbox contact, projectile travel and cancel-window details
  still require testing. Unknown budgets are excluded.
  Imported normals can supply a smaller explicit `cancel.hitstun_budget` to
  account for source hitstun and known delayed cancel windows.
- Light chains use explicit destinations in `cancel.chain_targets`.
  A.K.I.'s standing LP can chain into crouching LP/LK; pressing standing LP
  again invokes Hun Dun. Hun Dun is represented by its two-input target-combo
  entry, with its own final-hit timing. Links/chains into a target combo are
  evaluated against its first normal.
- Counter-hit and punish-counter bonuses apply only to the opening hit.
  They do not increase a target combo's or multi-hit attack's final advantage.
  Explicit move-specific counter data takes precedence over the generic bonus.
- Super cancels require both individual move permission and the allowed super
  level: ordinary specials permit level 3, OD specials levels 2/3. Linking to
  a super is evaluated separately.
- Automatically generated routes with unknown juggle/crumple timing, projectile-follow-up timing,
  conditional hit-grab cancels, stance transitions or Drive Rush are omitted.
  Published recipes supply specific routes through these situations without
  treating them as permission to chain arbitrary moves together.

## Published recipes and conditions

Recipes are stored in `characters.<character>.documented_combos`, with complete move
lists, transitions, starting conditions and source links. The tool includes
the complete route and its prefixes ending in an attack. It never joins recipes
together or appends automatically generated attacks to a recipe. Identical
results are deduplicated, preferring the published recipe over a timing candidate.
`--documented-only` restricts results to this path.
Source labels distinguish community guides from Capcom trial transcriptions
published by secondary sources. Coverage gaps are recorded in
`characters.<character>.documented_coverage` and [DOCUMENTED_COVERAGE.md](DOCUMENTED_COVERAGE.md).
Recipe-local target-combo copies contain only that stage's damage and input;
follow-ups omit the already displayed parent motion and additional OD cost.
These copies are excluded from automatic generation. Missing attack damage
propagates to an unknown total instead of showing a misleading partial sum.

Starting conditions must match the selected opening hit, poison state and
opponent state. `--position midscreen|corner|any` defaults to midscreen;
`any` labels position-dependent output. `--opponent-state grounded|airborne`
defaults to grounded. Airborne searches currently return only published recipes.
Height, spacing and delayed inputs remain in the recipe notes (`-v` or JSON).
Sources include older game versions; inclusion does not establish current-patch
validity. See [DATA_SOURCES.md](DATA_SOURCES.md) for extending the data.

Drive Rush, Drive Rush Cancel and walking are explicit actions. Each counts as
one input toward `len`; target-combo entries count their constituent inputs.
Non-attacking movement and stance entries cannot be the last step of an output.
Drive Rush costs one Drive bar, Drive Rush Cancel three, and OD attacks two.
The OD Chaser follow-up costs no additional Drive bars. Resource regeneration
during a combo is not modeled, so some routes may need less starting meter in
the game than this conservative sum.

## Setup labels

The table labels recorded corner setups, starting states, opening hit conditions,
poison, stance/charge and movement requirements. It lists other published setups
for the same inputs. Prefixes inherit full-recipe conditions; a corner recipe
does not establish that every prefix requires the corner. Starting-posture
filters check explicitly recorded recipe requirements. No collision, pushback,
scaled-damage or measured-input-window subsystem is included.

## Data references

[Ultimate Frame Data's A.K.I. measurements](https://ultimateframedata.com/sf6/aki)
were checked against the
[SF6 Frame Data Search table](https://frame-search.com/?character_name=A.K.I&lang=en-us).
The latter supplies the current single-hit active/recovery values added to
`characters.json`. Standing MP recovery differs between these tables; the
search uses the shorter 14-frame recovery, yielding the smaller cancel budget.
Hun Dun uses the 15-frame recovery documented in the
[March 2026 patch breakdown](https://shoryu.site/character/aki), yielding a
17-frame immediate-cancel budget. Standing HK's grounded punish-counter
advantage is +12, treated as a final value rather than adding another +4.

Capcom's [A.K.I. frame table](https://www.streetfighter.com/6/character/aki/frame)
and [March 2026 patch notes](https://www.streetfighter.com/6/buckler/battle_change/20260317/aki)
returned HTTP 403 during this review, so this is not a claim of full official
patch validation. No game client was available to test these routes.

The longer light patterns come from the
[AKI Guide](https://www.scribd.com/document/839104130/The-AKI-Guide)
and a player's [A.K.I. combo demonstrations](https://note.com/akino_outi/n/n7594fdffc1dc),
including `2LP > 2LP > 5LK`. The March 2026 chain change permits crouching
LP/LK into Hun Dun. These are supporting references, not verification of every
whole route the tool constructs.

## Validation

Use `--no-jumping` to exclude jump-normal attacks and jump-in starters. It can
be combined with `--no-specials`, difficulty filters, and random sampling.

Run `python3 -m unittest -v` for timing, counter, target-combo, chain, meter,
notation and conditional-route regression tests.
In SF6 training mode, use **Block After First Hit**, the matching counter-hit
setting and the frame meter to check a route at the intended spacing. A block
or whiff after the first hit means the sequence did not form a continuous combo.
The default CLI prints a bracket such as `[easy | len=3 | raw dmg=900]` to the left of each combo;
`-v` displays each candidate's timing notes.

## Estimated execution difficulty

Every result includes a `difficulty` object in JSON. Default text output shows
the difficulty label, explicitly labeled input length (`len=N`), and raw damage to the left
of each combo. Add `-v` for the numeric score, component
breakdown, link windows and caveats.
Text and JSON output sort each character's results by increasing difficulty
score across all requested lengths. Equal scores put shorter combos first;
remaining ties preserve search order. Sorting collects results before printing.
Use `--random N` to sample up to N candidates without replacement after all
filters. The limit applies across all selected characters, not per character.
The sample is then sorted by difficulty and length within each character as
usual. If fewer than N routes remain, all are shown; if none remain, text output
is empty and JSON output is `[]`. N must be positive. Sampling limits output,
but still generates the candidate pool before selecting results.
`--max-difficulty easy|medium|hard` keeps that level and all easier levels;
omitting the option leaves results unfiltered. Difficulty never changes a
route's `candidate` status or validates its spacing.

`raw dmg` sums all hits in the move damage lists, applying the route's poison
and move-specific conditions. JSON exposes it as `damage.raw_total`, with
`damage.scaling_applied` set to false. This field does not apply combo scaling,
counter-hit damage multipliers or poison damage over time.
The raw total is base damage, not expected damage in training mode.
Projectile contact and aerial variants can change the number of connected hits;
the total uses the listed move variant rather than measuring those contacts.

This is a transparent heuristic, not a measured success rate. Points are:

- Length: one point per move input beyond two; target-combo inputs count.
- Motions: one point per consecutive direction sequence with at least two
  digits, or two for a sequence with at least six digits (e.g. `236236`).
- Simultaneous buttons: one point per `PP`, `KK` or `+` input.
- Links: ten points for a nominal one-frame window (16.7 ms), eight for two
  frames (33.3 ms), four for three (50.0 ms), two for four (66.7 ms), one for
  five (83.3 ms), and zero for wider windows. A single 1–2 frame link makes
  even a short route **hard**; a three-frame link makes it at least **medium**.
  These weights apply to all characters and add up across consecutive links.
  The window is
  `resolved on-hit advantage - next attack startup + 1`. Counter and poison
  changes are applied before this calculation. Variable advantage adds one
  point because contact timing matters.
- Jump-in positioning: two points per jump-normal entry.
- Published-route timing: two points per movement/system action and per
  juggle, crumple or delayed-cancel transition. Published links do not receive
  a numerical link-window score when their exact windows are unavailable.
  Where the conservative timing engine can measure a link, its regular window
  score is retained, including documented links with sufficient stored frame
  data. Unknown timing or timing requiring unmodeled setup is not assigned a
  precision score. Difficulty filtering happens after recipe deduplication.

Scores 0–3 are **easy**, 4–7 **medium**, and 8+ **hard**. These labels are
relative estimates and may need tuning based on playtesting. Actual input
buffers, cancel/chain input windows, spacing and accumulated pushback are not
measured. In particular, a nominal one-frame link is not a claim that the game
requires a single-frame button press. Unmeasured factors appear as caveats
rather than fabricated timing scores.

Examples:

```bash
python3 combo_finder.py aki --min-length 2 --max-length 4 --max-difficulty easy
python3 combo_finder.py aki --max-difficulty medium --color always -v
python3 combo_finder.py aki --random 5 --max-difficulty easy --color always
python3 combo_finder.py aki --json > combos.json
python3 combo_finder.py aki --documented-only --min-length 3 --max-length 8 --random 5
python3 combo_finder.py aki --documented-only --position corner --opponent-poisoned --max-length 12 -v
```
