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
| `docs/blueprint.md`, `docs/dashboard.md` | someone using it | what does this input do |
| `docs/advanced/` | someone building on the services | what does this service take and return |
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
> **Changed in 0.14.0** — the schedule view was `custom:flare` before.
> A view still using the old name shows "Custom element doesn't exist".
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
| tracking scope | external | The named thing that remembers which lights FLARE is driving, one per room. |
| ~~state device~~ | internal | The subentry type behind a tracking scope. Code only — the UI and docs both say *tracking scope*. |
| scope (bare) | both | Write *tracking scope* on first use in a section. Bare *scope* is fine afterwards in `docs/advanced/`, where it reads better than repeating the full term; spell it out every time elsewhere. |

### Behaviour

| Term | Scope | Meaning, and what to avoid |
|---|---|---|
| override | external | A light changed by anything that isn't FLARE. The user's word for it. |
| override protection | external | Leaving an overridden light alone. |
| claim | both | A recorded write. Fine in `docs/advanced/` (the `claims_*` services are public); avoid on mainstream pages, where "what FLARE is driving" reads better. |
| scene handoff | external | Letting a scene own part or all of a room. |
| self-healing | external | Retrying a command that didn't land. |
| two-step transition | both | Sending brightness and colour separately. Users meet it via the label and the repair. |
| brightness multiplier | external | The per-light scaling factor. |
| ~~adaptive tick~~ | internal | Say *the regular update* or *the next update*. |
| ~~adaptive step~~ | internal | Say *when FLARE next sets the lights*. |
| ~~dispatch~~ | internal | As a noun for FLARE's own sending step. The ordinary verb (*issue the calls yourself*) is fine in `docs/advanced/`. |
| ~~bucket~~ / ~~bucketing~~ | internal | Grouping lights by multiplier. Never in `docs/`. |
| ~~the recovered trigger~~ | internal | Say *when a light comes back online*. |
| ~~grouping~~ | internal | The module. Users see its effects, never its name. |
| ~~write tracking~~ | internal | Say *override protection*. |
| ~~context~~ / ~~context.id~~ | internal | Home Assistant's own plumbing. Not a user concept. |
| ~~reconciliation~~ | internal | Kept only in the FLARE acronym. Describe the behaviour instead. |

### Things with exact names

Never paraphrase these. They are what the user types or clicks.

- **Blueprint inputs** — the UI labels, verbatim: FLARE Sensor,
  Lights & Occupancy, Additional Triggers, Prefer RGB During,
  Scene Template, Morning/Day/Evening/Night Scene,
  Brightness Multiplier Template, Lights Off During Morning/Day/Evening/Night,
  Wait time, Update Interval, Update Jitter,
  Motion On / Motion Off / Background Transition.
  Several carry a literal "(Optional)" in the label — keep it when
  quoting the label, drop it in running prose.
- **Services** — `flare.apply_lighting`, `flare.compute_lighting_groups`,
  `flare.compute_curve`, `flare.compute_scene_coverage`,
  `flare.claims_check`, `flare.claims_record`, `flare.claims_clear`.
- **Config entries** — FLARE Schedules, FLARE Tracking.
- **Dashboard views** — `custom:flare-schedule`, `custom:flare-tracking`.

## Keeping this honest

The lexicon is only worth having if it is applied. When a term here
changes, or a new one is added, grep `docs/` for the old one in the same
change — and check `strings.json` too, since a term the UI says is a term
the docs are then obliged to say.

Known gap: the code still calls a tracking scope's subentry type
`state`, and `SUBENTRY_TYPE_STATE` / `StateInstance` follow from that.
Nothing user-facing says it any more, so this is a rename to do when
something else is already touching those files, not on its own.
