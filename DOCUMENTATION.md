# Writing FLARE's documentation

The rules for `docs/`, and the vocabulary everything should use. This is
the single home for both — CLAUDE.md and CONTRIBUTING.md point here
rather than restating them, because three copies of a style guide
disagree within a month.

## Who each thing is for

FLARE's docs are split by audience, and mixing the audiences is the
mistake that keeps happening. Before writing, decide which of these
you're in:

| Where | Audience | Answers |
|---|---|---|
| `README.md` | someone deciding whether to try it | why this exists |
| `docs/index.md` | the same person, one click later | what it does |
| `docs/installation.md` | someone installing it | how do I start |
| `docs/dashboard.md` | someone using it | how do I see it |
| `docs/guides/` | someone using it who wants more from it | what do I write to make it do this |
| `docs/reference/` | someone looking something up | what does this input, entity or service do |
| `CONTRIBUTING.md`, `CLAUDE.md` | someone changing the code | how it works, and why it's shaped this way |

## The rules

**1. Site pages are for end users. Design rationale belongs in the code
comment or CLAUDE.md.** Not "we chose X because Y", not "this is what
makes Z work", not "the trade-off is". A reader wants to know what it
does and how to use it. If a decision feels worth writing down, that is
a signal it belongs in CLAUDE.md, not that the docs need a paragraph.

**2. Don't narrate history — with one exception.** No "previously",
"used to", "this replaced". The changelog is the changelog. The docs
describe what is true now, in the present tense, as though it had always
been that way.

The exception is a **breaking change**, where someone upgrading has to
do something. Say so, say which version it changed in, and put it in an
info block so it reads as an aside rather than as part of the
explanation:

```markdown
{: .note }
> **Changed in 1.2.0** — the Schedule input is now a device picker.
> Re-pick the schedule in each room's automation.
```

Rules for these:

- Only for changes that **break an existing setup**. A renamed input, a
  renamed strategy, a removed service. Not new features, not fixes, not
  anything that keeps working untouched.
- Always name the version. "Recently" and "in a previous release" are
  useless to someone working out whether it applies to them.
- Always an info block, never running prose. A reader who installed
  today should be able to skip it at a glance.
- Delete it once it stops being plausible that anyone is upgrading
  across it. These are not permanent.

**3. Reference goes first, and reference is a table.** A page called a
reference opens with the complete list of inputs or fields, not with
prose. Someone arriving already knows what they're looking for; make
them scroll for it and the page has failed. Prose goes after.

**4. Headings are the reader's question, not our component.** "Why
didn't my light change?" beats "Reachability and redundancy filtering".
"Handing a room to a scene" beats "Scene handoff". Nobody searches for
the name of our module.

**5. Use the external word from the lexicon, always.** If a term is
marked internal below, it must not appear in `docs/`. If it's marked
both, use it in the same sense the lexicon gives.

**6. Name inputs exactly as the UI labels them.** If the blueprint says
**Lights & Occupancy**, the docs say Lights & Occupancy — not "Room",
not "Room Target", not a tidier name we prefer. A user maps the docs
onto their screen; anything else breaks that.

**7. Show, then explain.** A worked YAML example beats three paragraphs
describing one. If both are needed, the example comes first.

**8. Describe behaviour as the default, not as what FLARE does.** Almost
everything is a setting. "By default it's bright and cool in the
morning", "with the default settings", not "Morning is bright and cool".

**9. No asides about how good it is.** Cut anything whose point is to
admire the design rather than to tell the reader something they'll use:
"the same code the card runs", "costs very little traffic", "so you never
have to remember", "for free", "not a picture of it". A feature is
described once, plainly, where someone would look for it.

**10. Each thing in one place.** If two pages explain the same thing, one
of them links to the other instead. Pick the page where a reader would go
looking, not the first page the thing comes up on.

**11. On the introductory pages, FLARE is one thing.** The README, the
homepage and the Quickstart talk about FLARE, not "the integration" and
"the blueprint" as separate products. The split, the services and
building your own automations belong to Reference; the most an
introductory page says is one line pointing at Examples.

**12. The Quickstart is only the steps.** Every line is something the
reader does to get a room working, or needs to know to do it. Notes about
things that happen on their own, alternatives to the standard setup and
explanations of how it works all live elsewhere.

**13. Write plain technical documentation.** Short declarative sentences
that say what happens. Each of these has been flagged in review as
sounding like AI prose rather than documentation; don't write them:

- A sentence that sounds knowledgeable but gives the reader nothing to
  act on: "it re-checks as it goes", "it bends to fit the room", "shifts
  in step with what's happening outside". Say what actually happens
  ("every minute it checks each light"), or cut it.
- Em-dash asides — like this one — in running prose. Use a full stop or
  a comma. A dash between a list item's label and its description is fine.
- "X, not Y" contrasts and rhetorical turns ("that's the trick", "that's
  what makes…", "whatever the time of day", "the one thing that…").
- A bold lead-in on every bullet. Bold a term only when the bullet
  defines it.
- Explaining why something matters when the reader only needs to know
  what it does, or repeating something another page already covers.

**14. Reference is the contract; Guides are how to use it.** A Reference
page says what an input accepts, what an entity holds, what a service
takes and returns, and what happens as a result. Worked examples, recipes
and "how to get X" live in Guides and link back.

## Lexicon

**External** terms are what users see and say; they may appear anywhere.
**Internal** terms are implementation, and must not appear in `docs/`.
**Both** are safe everywhere, in the sense given.

### The product

| Term | Scope | Meaning, and what to avoid |
|---|---|---|
| FLARE | external | The whole thing. Not "the integration" when you mean the whole thing. |
| the integration | both | Specifically the HACS-installed half — services, entities, dashboard. |
| the blueprint | both | The ready-made room automation. It is a worked example, not "the product". |
| phase | external | Morning, Day, Evening or Night. Always capitalised when naming one. |
| the curve | external | The day's brightness and colour over time. Not "the schedule" — see below. |
| schedule | external | The times that divide the day into phases. A *schedule sensor* publishes one. |
| transition | external | Two unrelated meanings, so always qualify. A *phase transition* is the easing between phases; a *transition duration* is how long a light takes to change. |
| zone | external | The named thing, usually one per room, that remembers which lights FLARE is driving and whose Tick tells the room's automation when to update. Not *tracking scope*. |
| Tick | external | A zone's `event.<name>_flare_tick` entity. Capitalised: it's the entity's name. The update it causes is still *the regular update*. |

### Behaviour

| Term | Scope | Meaning, and what to avoid |
|---|---|---|
| override | external | A light changed by anything that isn't FLARE. The user's word for it. |
| override protection | external | Leaving an overridden light alone. |
| claim | both | A recorded write. Fine in `docs/reference/` (the `claims_*` services are public); avoid on mainstream pages, where "what FLARE is driving" reads better. |
| scene handoff | external | Letting a scene own part or all of a room. |
| self-healing | external | Retrying a command that didn't land. |
| two-step transition | both | Sending brightness and colour separately. Users meet it via the label and the repair. |
| brightness multiplier | external | The per-light scaling factor. |
| ~~adaptive tick~~ | internal | Say *the regular update* or *the next update*. |
| ~~adaptive step~~ | internal | Say *when FLARE next sets the lights*. |
| ~~dispatch~~ | internal | As a noun for FLARE's own sending step. The ordinary verb (*issue the calls yourself*) is fine in `docs/reference/`. |
| ~~bucket~~ / ~~bucketing~~ | internal | Grouping lights by multiplier. Never in `docs/`. |
| ~~the recovered trigger~~ | internal | Say *when a light comes back online*. |
| ~~grouping~~ | internal | The module. Users see its effects, never its name. |
| ~~write tracking~~ | internal | Say *override protection*. |
| ~~context~~ / ~~context.id~~ | internal | Home Assistant's own plumbing. Not a user concept. |
| ~~reconciliation~~ | internal | Kept only in the FLARE acronym. Describe the behaviour instead. |

### Things with exact names

Never paraphrase these. They are what the user types or clicks.

- **Blueprint inputs** — the UI labels, verbatim: Schedule, Zone,
  Lights & Occupancy, Additional Triggers, Prefer RGB During,
  Scene Template, Morning/Day/Evening/Night Scene,
  Brightness Template, Lights Off During Morning/Day/Evening/Night,
  Idle Brightness Template, Morning/Day/Evening/Night Idle Brightness,
  Wait time,
  Motion On / Motion Off / Background Transition.
  Several carry a literal "(Optional)" in the label — keep it when
  quoting the label, drop it in running prose.
- **Services** — `flare.apply_lighting`, `flare.turn_off`, `flare.compute_lighting_groups`,
  `flare.compute_curve`, `flare.compute_scene_coverage`,
  `flare.claims_check`, `flare.claims_record`, `flare.claims_clear`.
- **Config entries** — FLARE Schedules, FLARE Zones.
- **Dashboard views** — `custom:flare-schedule`, `custom:flare-zone`.

## Keeping this honest

The lexicon is only worth having if it is applied. When a term here
changes, or a new one is added, grep `docs/` for the old one in the same
change — and check `strings.json` too, since a term the UI says is a term
the docs are then obliged to say.

A zone's subentry type is still stored as `state` (HA can't retype a
subentry), behind `SUBENTRY_TYPE_ZONE`. Nothing user-facing says it.
