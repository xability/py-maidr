# CHANGELOG


## v1.23.0 (2026-08-31)

### Bug Fixes

- **seaborn**: Read a box or boxen chart's grouping from the legend that names it
  ([#676](https://github.com/xability/py-maidr/pull/676),
  [`50b2197`](https://github.com/xability/py-maidr/commit/50b2197539de5c8bc14443e4246fa855cc1cf953))

Three readers still asked `ax.get_legend()` directly after #672 and #617 moved everything else onto
  `legend_of`. Measured, a box chart whose legend sits on the figure lost its `z` label, and a boxen
  chart lost every ladder's level as well — two ladders in one category announced identically, the
  shape xability/maidr#828 exists to prevent.

`BoxPlot` names each box by colour through `names_for`, which already read the chosen legend, so
  only the variable's name was dropped. `BoxenPlot` reads its levels from the legend's own list of
  names, which was empty with no axes legend.

The label and the levels now come from the same legend.

Closes #674.

- **seaborn-objects**: Name a colour split from the legend wherever it was put
  ([#673](https://github.com/xability/py-maidr/pull/673),
  [`c5c76f5`](https://github.com/xability/py-maidr/commit/c5c76f50ca3d27bd6953b1d24ca90828f1ce26f7))

A colour-split `so.Line` drew two lines and read as two series carrying no names at all -- no
  per-point `z`, and no `axes.z` naming the variable they were split by, where the classic
  `sns.lineplot(hue=)` named both.

A `so.Plot`'s legend is the figure's, never the axes'. `legend_of` has known that since #617 and the
  scatter and bar paths moved onto it then; `MultiLinePlot`'s `legend_labels` and
  `MaidrPlot._legend_title` never did. Both now go through it, and every rule about which legend
  answers stays `legend_of`'s.

`_legend_title` had become identical to `legend_names.title_of` and now delegates to it, so the
  settled version has one copy. Coverage added for `ScatterPlot` and `PointPlot`, the other two
  callers that reach the same method.

Closes #672.

- **seaborn-objects**: Split a colour-split Dash into one layer per level
  ([#682](https://github.com/xability/py-maidr/pull/682),
  [`0481e71`](https://github.com/xability/py-maidr/commit/0481e7119d01c1772c5750ed65c85b0cb2a9529c))

A `so.Dash()` given `color=` was read as one anonymous cloud of forty ticks (#680). `hue_groups`
  inverts a collection's colours against the legend that names them and asked for face colours,
  which a `LineCollection` has none of — measured, 0 face colours against 40 edge colours.

`drawn_colours` reads faces where the artist has them and edges otherwise. The split takes
  `so.Bars`' shape rather than `so.Dot`'s: the layer is handed one collection and reads a slice of
  it, so the members travel with the name as `DASH_MEMBERS` and the selectors keep numbering against
  the collection.

Closes #680.

### Documentation

- Add a word cloud example to the gallery ([#689](https://github.com/xability/py-maidr/pull/689),
  [`686a7ef`](https://github.com/xability/py-maidr/commit/686a7efa2aeda4df8952f8a183ba715c658c385c))

`word_cloud` merged with only a row in `docs/stability.qmd` naming it, so a reader could learn the
  type exists but not how to produce one -- an inconsistency, since four other experimental types
  already carried example sections in the same file.

The section sits after Pie Chart, the other chart here with no positional scale, and covers what is
  not obvious from the API:

* The weights are relative. `generate_from_frequencies` divides by the largest frequency and keeps
  only the ratio, so 412 is announced as 1.0 and the axis is named "Relative frequency". Naming it
  after counts would hand a reader "accessibility, 1.0" for a term that occurred 412 times. The R
  binding is handed the raw counts and can honestly say "Occurrences" -- same chart, two honest
  readings. * Show the object, not the picture: `to_array()` / `to_image()` hand `imshow` a plain
  RGB array with the terms nowhere in it. * No highlighting, because `imshow` rasterises the cloud
  into one element and there is no per-term element to outline.

Review caught the example overriding the very default the prose described, so a reader would never
  have seen it; the labels were dropped and the defaults now fire in the shown output.

The prototype callout is applied to all five experimental sections rather than this one alone, so
  Hexbin, Boxen, Error Bar and Area no longer imply a stability they do not have.

Also adds the standalone sample under `example/wordcloud/matplotlib/`. The example was run before
  being written down.

- Add gallery examples for three experimental matplotlib plot types
  ([#690](https://github.com/xability/py-maidr/pull/690),
  [`6a9d780`](https://github.com/xability/py-maidr/commit/6a9d78089928e5c96dd98e02fab14a9f3fd4836b))

Co-authored-by: Claude <noreply@anthropic.com>

- Mark the roadmap's new plot types as experimental
  ([#687](https://github.com/xability/py-maidr/pull/687),
  [`110c135`](https://github.com/xability/py-maidr/commit/110c135eda776f12362f28d400bf82a9b60edfb7))

`PlotType` defined 15 members when the plot coverage roadmap (#345) was filed and defines 37 now.
  The 22 that arrived with it are not on the same footing as the 15 that predate it -- most landed
  inside about two weeks, and none has been through a user study -- but nothing in the enum or the
  docs said so.

Adds `docs/stability.qmd`, in the navbar, splitting the enum and stating what the experimental half
  does not promise: no deprecation period, no support commitment, and measured against the chart
  rather than validated with a reader. Measuring that a reading is faithful to the drawing is a
  different claim from establishing that it is useful, and only the first has been done.

The boundary is the diff of `PlotType` against `d9f7aee`, the last commit before #345 was filed, and
  the page carries the command to re-derive it.

`tests/core/test_plot_type_stability.py` fails if a member lands in neither table or in both, checks
  each row's emitted string against the enum since that is what reaches the schema, and pins the
  whole stable set rather than a sample -- the partition check alone is satisfied by any split that
  covers the enum, including a wrong one.

Review also caught CLAUDE.md still naming the pre-roadmap 25, which is the same drift in the file an
  agent reads first; it now names all 37, split the same way and pointing at the page.

- Tell deck authors how to keep off-slide charts out of the tab order
  ([#686](https://github.com/xability/py-maidr/pull/686),
  [`99913b7`](https://github.com/xability/py-maidr/commit/99913b77fb5d3e4873286524cebab13092c1c395))

A chart already hands focus back to its slide, but reveal.js keeps the slides on either side of the
  current one rendered and marking them `hidden` does not take them out of the tab order, so one Tab
  lands on an off-screen slide's chart. reveal.js `master` now marks every slide but the current one
  `inert`, and until that reaches a Quarto release the quarto-revealjs-a11y extension does the same
  for a deck.

### Features

- Read a word cloud as its terms and their weights
  ([#688](https://github.com/xability/py-maidr/pull/688),
  [`451cf8a`](https://github.com/xability/py-maidr/commit/451cf8a925a979cf8f354c2a82477b7e38104e9d))

A `wordcloud.WordCloud` shown with `ax.imshow` registered no layer at all, so a figure holding only
  a cloud raised UnsupportedPlotError: the cloud rasterises to an (M, N, 3) colour array, and the
  heatmap patch declines exactly that shape (#564). It was unread rather than misread, so the
  reading is additive.

The layer reads `words_`, not `layout_` -- `layout_` lists a term once per placement under
  `repeat=True`, which would announce one term twice at two different weights for a repetition that
  is the packer rather than the data.

The weights are relative and the axis label says so. `WordCloud` divides every frequency by the
  largest and keeps only the ratio, and the raw counts are on no attribute of the object. That is
  also what the chart draws, so "Relative frequency" is the honest name; the R binding is handed the
  counts directly and can say "Occurrences" instead.

No selectors: `imshow` rasterises the whole cloud into one element, so there is no per-term element
  to point at. The core supports a layer without them.

Marked experimental in docs/stability.qmd alongside the rest of the plot coverage roadmap.

- **core**: Read a baseline-anchored vlines as the spike chart it draws
  ([#665](https://github.com/xability/py-maidr/pull/665),
  [`6e7900d`](https://github.com/xability/py-maidr/commit/6e7900d583bbb0901631bb8de91942e73c3eb0f7))

A bare `ax.vlines([1, 2, 3], 0, [5, 3, 7])` registered no layer at all, so the figure fell back to a
  static picture and the three measurements were announced nowhere. The same values drawn any other
  way read fine: `ax.stem` and `ax.acorr` emit a lollipop, and a `vlines` whose ends both vary emits
  a gantt.

The span reading declines when either end is shared, on the grounds that "the markers drawn at their
  tips already say it" -- and with a bare `vlines` there are no markers, which is the gap
  `patch/correlogram.py` already records for `acorr`.

Not a schedule is not the same as not a chart. Where exactly one end is shared the call drew stems
  from a baseline, and it is now registered as the `lollipop` `ax.stem` emits, through the machinery
  `acorr` already uses. The value is the free end, found rather than assumed. Where both ends are
  shared -- reference lines across the frame -- and where there is only one segment, nothing is
  registered, unchanged.

Closes #664

- **plotly**: Read a scatterpolargl as the radar it draws
  ([#669](https://github.com/xability/py-maidr/pull/669),
  [`18d9a56`](https://github.com/xability/py-maidr/commit/18d9a56f9485aa5d5b850b1360a77c3bbe4d4cda))

`go.Scatterpolargl` carries the same `r` and `theta` as `go.Scatterpolar` and differs only in being
  painted by regl, but the polar branch listed two trace types by name and read it as nothing. It
  now reads as a radar, declines its selector as the canvas trace it is, and is left out of the
  subplot's scatter numbering.

Closes #668

- **plotly**: Read a splom as the grid of scatters it draws
  ([#667](https://github.com/xability/py-maidr/pull/667),
  [`b1a6eeb`](https://github.com/xability/py-maidr/commit/b1a6eebef4bfe4866c2baea3b387103b219cedcd))

A `splom` produced a one-by-one grid whose only cell held no layers at all, and `render()` succeeded
  on it -- so a reader was handed a chart that announced itself as navigable and contained nothing.
  `px.scatter_matrix` produces the same trace type, so the commonest spelling was affected too.

A splom is one trace carrying `n` dimensions and drawing an `n` by `n` grid of scatters, which is
  what MAIDR's subplot grid is, and the plotly path already builds real grids. Panel `(i, j)` is
  dimension `j` on x against dimension `i` on y, and becomes an ordinary scatter layer at its own
  position.

`diagonal.visible`, `showupperhalf` and `showlowerhalf` are each read rather than assumed: a blanked
  panel is left out entirely, so the grid keeps its shape and the blanks are holes in it. A
  dimension the chart hides, or one carrying no values, is not a row or a column at all.

No panel claims a selector -- a splom's per-panel DOM has not been measured, and a selector that
  resolves to nothing is a highlight that silently never appears.

Closes #666

- **plotly**: Read the seven map traces that registered nothing
  ([#684](https://github.com/xability/py-maidr/pull/684),
  [`62a6b03`](https://github.com/xability/py-maidr/commit/62a6b0353c25ae45a3c453ac554256f3eb244b9b))

`go.Choropleth` was read; every other trace plotly draws on a map registered no layer at all, so the
  whole figure fell back to a picture. Measured on plotly 6.7.0: Scattergeo, Scattermap,
  Scattermapbox, Densitymap, Densitymapbox, Choroplethmap and Choroplethmapbox all produced n=0.

The two tiled choropleths read through the class that already existed — same `locations`, same `z`,
  a different base map painted underneath. The five scatter-shaped traces get a class of their own:
  a placed marker has a position and a name and no magnitude, so it is a scatter of degrees with the
  place name on `ScatterPoint.label`, and a density trace's `z` travels on `ScatterPoint.z`. Which
  layout block a map names is measured per family rather than assumed to be `geo`.

Closes #683.

- **seaborn-objects**: Read a Band or a Range as the interval it draws
  ([#677](https://github.com/xability/py-maidr/pull/677),
  [`a592ca4`](https://github.com/xability/py-maidr/commit/a592ca4dbba56ef4963008015972eeac4bc5ccf2))

`so.Band` and `so.Range` registered nothing, so a chart of estimates and their uncertainty fell back
  to a static image. They are the same reading from two drawings — a `Polygon` folded
  lower-forward-then-upper-backward, and a `LineCollection` of one segment per position — so one
  class takes both.

Neither draws a centre, and `ErrorBarPoint.y` is optional for exactly that. Orientation comes from
  the geometry: the two bounds at one position share the coordinate that position sits on, and a
  degenerate interval shares both so the first with a spread decides. A colour split is named
  through the legend and becomes the grouped `ErrorBarPoint[][]` shape.

Highlighting is offered only where there is an element per interval: a range's own paths, addressed
  by position in its group. A band has one path over every position, and a split range's paths run
  in drawing order while its payload is grouped by level, so both decline rather than outline the
  wrong thing.

Part of #670.

- **seaborn-objects**: Read a Bars mark as the histogram it draws
  ([#678](https://github.com/xability/py-maidr/pull/678),
  [`a701761`](https://github.com/xability/py-maidr/commit/a7017618c05ecbd168f6e32ee6b26bfa658c8728))

Co-authored-by: Claude <noreply@anthropic.com>

- **seaborn-objects**: Read a Dash mark as the scatter of ticks it draws
  ([#679](https://github.com/xability/py-maidr/pull/679),
  [`6d06e30`](https://github.com/xability/py-maidr/commit/6d06e30cc7eed71a1018a37cb8da024515bd5b87))

Co-authored-by: Claude <noreply@anthropic.com>

- **seaborn-objects**: Read a Lines or Paths mark as the line it draws
  ([#675](https://github.com/xability/py-maidr/pull/675),
  [`8a44ebf`](https://github.com/xability/py-maidr/commit/8a44ebf2d08863d80648c8b78638d97be76e00ed))

`so.Lines` and `so.Paths` registered nothing, so a plot built from them was silent. They leave a
  single `LineCollection` holding one segment per group where `so.Line` leaves a `Line2D` each, so
  `MultiLinePlot`'s walk of `ax.lines` found nothing.

`SegmentLinePlot` reads the collection: a `Line2D` stand-in per segment so the multi-line walk is
  reused unchanged, then the tagged element swapped back to the collection itself. A series is
  addressed by `nth-of-type` within the collection's group, and the drawn colours are cycled rather
  than indexed because `get_colors()` returns one colour for every segment by default.

Part of #670.

- **seaborn-objects**: Read a Text mark as the labelled scatter it draws
  ([#681](https://github.com/xability/py-maidr/pull/681),
  [`2105f9e`](https://github.com/xability/py-maidr/commit/2105f9ee8fed780349f3d64d39cc0f2f3b350385))

Co-authored-by: Claude <noreply@anthropic.com>

- **seaborn-objects**: Read an Area mark as the band it draws
  ([#671](https://github.com/xability/py-maidr/pull/671),
  [`fec7c1e`](https://github.com/xability/py-maidr/commit/fec7c1e2cba7e629e4f768939bf7689cd0073f8b))

`so.Area` is the first `seaborn.objects` mark to need something extracted rather than handed
  straight to a plot class: its polygon folds the baseline forward and the values backward, and
  `AreaPlot` takes the positions and the series. Both orientations read; a colour split declines
  until its groups can be named, and that same polygon count covers a position transform.

Part of #670


## v1.22.0 (2026-08-24)

### Bug Fixes

- **altair**: Say that use_cdn=False cannot be honoured, instead of ignoring it
  ([#523](https://github.com/xability/py-maidr/pull/523),
  [`263dc4e`](https://github.com/xability/py-maidr/commit/263dc4e4f8c47d9f3db6a955252b92e43a5db5fe))

`maidr.render(chart, use_cdn=False)` accepted the flag on an Altair chart and discarded it. The
  emitted HTML was identical with the flag on and off once the generated UUIDs are normalised away,
  and no warning was raised.

`api.py` returns for Altair before `use_cdn` is even resolved, and `maidr/altair/altair_maidr.py`
  has nothing to pass it to. The path renders through the upstream Vega-Lite adapter, which is
  published only on a CDN, so there is genuinely nothing to inline.

The reader this fails is the one who set the flag: `use_cdn=False` means they cannot reach a CDN, so
  they got a chart that never initialised and no reason why -- the same class as #358 and #455.

No behaviour changes. Only an explicit `False` warns, resolved through `_resolve_use_cdn` so a
  process-wide `set_use_cdn(False)` is caught too. All three entry points warn, and `render`'s
  docstring gains the caveat `show` and `save_html` already carried.

Whether the flag could one day be honoured is a packaging question about maidr's own `vegalite.js`,
  left open on #521.

Closes #521.

- **area**: Name the axis a sideways band was actually drawn against
  ([#567](https://github.com/xability/py-maidr/pull/567),
  [`dae2a5b`](https://github.com/xability/py-maidr/commit/dae2a5b4f757c75f27ef4e0ec5cbb7efa036d609))

`fill_betweenx(y, x1)` fills between the vertical positions `y` and the horizontal curve `x1`, so
  its positions belong to the y axis and its magnitudes to the x axis -- the mirror of every other
  chart `AreaPlot` reads. Emitted unchanged, the two spellings produced byte-identical payloads for
  charts that are transposes of each other, and a reader was told "horizontal 1, vertical 2" where
  the chart draws the point at vertical 1, horizontal 2.

The titles move rather than the data, and each half is wrong on its own.

Moving the data would put the positions in `y`, which the core sonifies: every sideways band would
  then play a rising ramp, whatever its data says, because those are positions. And `orientation` --
  the field that says a chart is drawn sideways -- would be a promise the core does not keep: AREA
  is marked as not oriented on purpose, since it navigates along the series either way.

So the two `AxisConfig` entries are exchanged, after the format config is merged into each: a
  currency formatter set on the x axis describes the horizontal numbers, which are the ones that
  move. The core's Vega-Lite adapter does the same exchange for the same reason on a horizontal
  waterfall, a type whose axes it cannot swap either.

What it does not fix is navigation: left and right still walk the trace's `x`, which for a sideways
  band is the vertical axis. That is what `orientation` would carry, and whether AREA should join
  the oriented types is a core question with a rationale already written down against it.

Closes #566

- **box**: Announce every box a hue-grouped box plot draws
  ([#594](https://github.com/xability/py-maidr/pull/594),
  [`beda9fa`](https://github.com/xability/py-maidr/commit/beda9fa09b3615b7050da9a5c3085cd3cc6c3ce8))

`sns.boxplot(hue=...)` draws one box per category per level and announced only the first level's --
  three of six boxes absent from the schema entirely, with nothing raising. One `zip` did it: the
  per-box lists were paired against the axis's tick labels, one per category, and `zip` ends at the
  shortest. The same chart also emitted six selectors against three rows.

Each box is now named from the drawing: the category from its position by nearest tick, and the
  level from its colour matched against the legend swatch. Engaged only where there are more boxes
  than ticks, so every chart that was already right keeps the reading it had.

Closes #593.

- **box**: Name each catplot box layer for the level it holds
  ([#596](https://github.com/xability/py-maidr/pull/596),
  [`f9be78b`](https://github.com/xability/py-maidr/commit/f9be78bfc4d9cbed836ef96754504eaae70fefb4))

`sns.catplot(kind="box", hue=...)` announced every box across two layers a reader could not tell
  apart: both carried the same three categories on `z` and neither carried a name. The name is now
  deferred to render, because `catplot` builds its legend at the figure after every panel is drawn,
  so there is none to read when the layers register.

`name_for` is the one-colour half of `names_for`, which declines a lone artist -- right where the
  artists of one layer are named against each other, wrong where a layer is the artist. A `bxp` call
  draws one level's boxes, so the layer's one colour says which level it is.

The axes-level `sns.boxplot` is untouched: its boxes reach one layer together, so the level belongs
  per box.

Also factors the `GROUP_NAME` read into `group_name_of`, which the three opting-in layers had
  already begun to diverge on.

Closes #595.

- **cdn**: Pin to the bundled version when the resolver answers backwards
  ([#509](https://github.com/xability/py-maidr/pull/509),
  [`38a44fb`](https://github.com/xability/py-maidr/commit/38a44fbf4b7a50b23460dcc713f8b2222ebf0317))

Nothing about the resolver request obliges the answer to be the current version: a compromised
  registry or a hostile caching proxy could name an older-but-well-formed one and have it spliced
  into every CDN URL the page emits. Refusing it is only a defence if the fallback is not the same
  party, so the guard pins to the version bundled in this wheel.

Not a tamper detector, and it does not claim to be: a bundled copy ahead of what is published is
  normal between releases and after a yank, so the log line is debug and leads with the ordinary
  cause. Explicit pins are left alone, and `bundle_status()` keeps seeing the unfiltered answer.

Closes #297

- **core**: Make figure registration atomic ([#506](https://github.com/xability/py-maidr/pull/506),
  [`6629cb4`](https://github.com/xability/py-maidr/commit/6629cb407a610e91bab78bed24da606f7729c7e8))

`_get_maidr`, `get_maidr` and `destroy` guarded their `figs` access with nothing, so two threads
  registering layers on one figure could both find it missing and both create a `Maidr` for it --
  the loser dropped from `figs` while its layers were not, a chart rendering with layers silently
  missing. `create_maidr` appended to `plots` and `selector_ids` in two separate atomic steps, so a
  concurrent registration could interleave them and leave every surviving layer wearing its
  neighbour's selector id.

All three paths now hold the pre-existing `_lock`, with the paired appends inside one critical
  section. `MaidrPlotFactory.create` stays outside it.

Both new tests were falsified against an unguarded build before being trusted: the pairing test
  drives two threads through an explicit handoff inside `Maidr._unique_id` -- the seam between the
  two appends -- rather than racing a crowd off a barrier, so it detects on every run rather than 3
  of 5. Its deadline is 0.3s, measured as the point where detection is still 5/5.

Closes #505

- **core**: Read a bivariate histogram as the heatmap it draws
  ([#525](https://github.com/xability/py-maidr/pull/525),
  [`fe5a46b`](https://github.com/xability/py-maidr/commit/fe5a46b8a13b4f120c411dc89ed70a9db9a1d315))

`sns.histplot(x=..., y=...)` draws a `QuadMesh` of joint counts, exactly as `ax.hist2d` and
  `ax.pcolormesh` do. Those read as `heat`; this raised `UnsupportedPlotError` and the figure was
  unreadable, while the same chart through `sns.displot(x=..., y=...)` read as `heat` all along.

Three correct decisions composed into a wrong one. `common()` sets the internal context so a patched
  seaborn call does not register twice; the inner `Axes.pcolormesh` therefore drew quietly and
  registered nothing; and `_drew_bars` then declined, rightly, because a mesh is not a histogram.
  The guard assumed the outer patch would make a registration of its own, and the outer patch
  declined. `displot` escaped only by not being patched.

So the histogram patch now makes the one the chart is owed: having declined `hist`, it registers
  `heat` when the call added a mesh, naming the `z` axis from `stat` so a density is not announced
  as a count. `_drew_mesh` asks what this call drew, the way `_drew_bars` does.

That exposed a second defect it had to land on. `extract_scalar_mappable` took the first
  `ScalarMappable` on the axes, and a scatter's `PathCollection` is one too, so a heatmap drawn
  beside a scatter was read from an artist with no grid. It now prefers a mesh or an image, and
  reaches `None` on an empty axes rather than raising `StopIteration` through a bare `next()`.

`sns.jointplot(kind="hist")` gains its joint panel, which is the worse symptom of the two: it
  returned both marginal histograms and nothing for the middle, so nothing raised and the chart
  sounded complete.

Closes #522

- **core**: Render one figure at a time for every caller, not just two doors
  ([#538](https://github.com/xability/py-maidr/pull/538),
  [`7a2640b`](https://github.com/xability/py-maidr/commit/7a2640b092f042029619c5694890182defd3c124))

The dpi race is in the render path, not in the integrations. savefig writes fig.dpi for its duration
  and restores it, so two renders of one figure at once race on that attribute and the loser draws
  its whole chart at the other call's dpi -- a well-formed SVG at 72% scale, raising nothing.
  Measured through maidr.render with no widget involved, six threads on one figure: 1 of 5 trials
  returned two distinct outputs.

The lock sat in maidr/widget/, so it covered the two doors this package ships and nothing else; a
  threaded Flask app met the race unprotected. Maidr._create_html_tag now takes it. Every render of
  a matplotlib figure funnels through that method and nothing re-enters it, so one lock site covers
  every caller and a plain Lock stays safe. The doors drop theirs -- a second lock above this one
  would deadlock rather than nest.

Locking by the figure the Maidr instance already holds also removes the resolution step the doors
  needed, and with it the class of bug where that resolution disagreed with the renderer and locked
  a figure the render never touched.

Closes #532.

- **core**: Stop a colorbar from moving its panel out of its grid position
  ([#519](https://github.com/xability/py-maidr/pull/519),
  [`c113708`](https://github.com/xability/py-maidr/commit/c1137083c999af107d7d6970b196ab148ffe8c16))

Two `sns.heatmap` calls into a `subplots(1, 2)` were emitted as one grid position holding two `heat`
  layers, so a reader was handed a single panel to page two layers of -- one set of titles, one set
  of axis labels, one position announcement -- instead of two charts to move between.

Attaching a colorbar re-parents its panel into a fresh sub-gridspec where the panel sits at the
  origin, and a panel is keyed by where its span starts, so both heatmaps reported (0, 0) and
  grouped into the same cell. `get_topmost_subplotspec` walks up through the nesting to the gridspec
  the figure was laid out with, where the two are still the (0, 0) and (0, 1) their author wrote.

Only figures with more than one colorbar-bearing panel were affected; a heatmap beside a bar chart
  was already fine, and is kept as a control alongside a lone heatmap -- resolving through the
  nesting must not invent a position either.

One helper rather than the call inlined at both sites, since the two would otherwise have to be kept
  in step by hand.

Closes #518.

- **core**: Stop a single empty grid position from breaking the whole figure
  ([#512](https://github.com/xability/py-maidr/pull/512),
  [`db766a1`](https://github.com/xability/py-maidr/commit/db766a1d030aed9e00b419ab3cbf7a906402050a))

A subplot grid is sized from the largest row and column any layer reports, so a figure whose axes do
  not tile it leaves holes. Those holes were emitted as bare `{}`: the backfill meant to fill them
  tested `cell is not None`, but the placeholder it checked is `{}`, so the branch never ran and the
  loop was dead code.

The core does not tolerate that. `Subplot`'s constructor reads `subplot.layers.length` unguarded, so
  one position with no `layers` key throws during figure construction and the entire chart fails to
  initialise -- not just the empty position. The SVG still draws, so the page looks finished and the
  key that should start navigation does nothing.

Covered twice, because neither check reaches the other's end: a schema contract test across all
  three gap shapes, and a browser test that drives Chromium to assert the core accepts it.

- **core**: Stop emitting a layout gridspec's padding as empty panels
  ([#517](https://github.com/xability/py-maidr/pull/517),
  [`6a0817f`](https://github.com/xability/py-maidr/commit/6a0817f72bbeb579dabd667edbd81ba138bd0eb5))

`seaborn.jointplot` drew three panels and emitted twelve grid positions, nine of them holding
  nothing. `JointGrid` lays its panels out on a 6x6 gridspec to get the marginal-to-joint size
  ratio, so sizing the grid from the largest span start forced six columns for two occupied ones,
  and a reader arrowing between the three real panels met nine that were only there for proportion.

Panels are now keyed by the rank of their span start among the starts some axes actually uses, which
  collapses the rows and columns no axes begins in. jointplot becomes the 2x2 it looks like.

Ranked over every axes on the figure rather than only the ones carrying a layer, which is what keeps
  a position the author left empty -- the middle panel of a `subplots(1, 3)` drawn on twice is an
  axes on the screen and a reader should meet it. An axes ranked but never occupied costs nothing,
  because the grid is still sized from the largest rank a panel reaches, so a heatmap's colorbar
  adds a rank rather than a row.

Each of those three choices has a test that fails without it.

Closes #513.

- **core**: Stop reading a figure caption as every panel's x-axis label
  ([#516](https://github.com/xability/py-maidr/pull/516),
  [`2d85781`](https://github.com/xability/py-maidr/commit/2d857818f8f05e718f34aba0af05c292396b412e))

A figure with a bottom caption and an unlabelled x axis announced the caption as the axis label, on
  every data point of every panel, with nothing marking it as a guess and no way to turn it off.

`extract_shared_xlabel` took any figure-level text below y=0.2 as the x label, and
  `extract_shared_ylabel` did the same on the left margin. The scan is load-bearing -- it arrived
  with facet support and the shipped facet example writes its shared labels that way -- and position
  cannot separate a shared label from a caption, since both sit centred in the margin.

Whether the axes shares its axis at all can. The scan now runs only when the sibling group has more
  than one member: an axes that shares its x with nobody has no *shared* label to recover.
  `supxlabel`/`supylabel` are consulted first and without that condition, because a figure that
  calls them has said what the text means rather than leaving it to be inferred from position.

Also removes the unreachable merge branch in `_flatten_maidr` (closes #515), raised in review on
  #512 and confirmed by replacing its body with a raise and finding the suite still green.

Closes #514.

- **core**: Stop retaining every figure for the life of the process
  ([#508](https://github.com/xability/py-maidr/pull/508),
  [`df1e9d5`](https://github.com/xability/py-maidr/commit/df1e9d5d2a023cffd457149363bb844fa24160f6))

`FigureManager.figs` was a class-level dict, so a figure stayed reachable forever once maidr
  registered it. Registration happens when a chart is *plotted* rather than rendered, so this
  applied to every supported figure. The `plt.show()` path escaped it only because the backend calls
  `destroy` explicitly; a Shiny or Streamlit render never goes through `plt.show`, so a long-lived
  server accumulated one figure -- and every artist maidr extracted from it -- per render.

The record now lives on the figure itself, making the whole graph one isolated cycle once the
  application lets go. 25 renders, each building its own figure and closing it:

chart before after 10 bars 17.65 MB, figs +25 0.26 MB, figs +0 200 bars 177.80 MB, figs +25 2.30 MB,
  figs +0

The `after` column matches a control that drops the entry by hand, so what remains is baseline
  allocation rather than retention. Registration costs 0.63 us more per layer, of which the new lock
  is 0.03 us.

Deliberately not a `WeakKeyDictionary`: every value reaches its own key -- `Maidr._fig`,
  `MaidrPlot.ax`, each subclass's artist handles -- so the entry keeps the figure alive and the weak
  key never dies. Keeping the value *on* the key sidesteps that, since a value reaching its key is
  what a cycle is. It also avoids a bounded cache's eviction hazard and the cached-figure hazard of
  dropping on close (#452) -- which measurement showed would have been inert anyway, because
  `plt.close()` fires no `close_event` under Agg, in exactly the headless servers that leak.

`figs` keeps the mapping interface it had, so its callers are unchanged. Storing on the figure did
  introduce hazards the dict could not have, each reproduced before being fixed: a shallow copy
  claimed the original's chart, a membership test raised after `destroy`, a copied figure was
  invisible to enumeration, `del` and `pop` disagreed, and a mismatched write silently did not
  stick.

Every guarantee is pinned by a test falsified against a build without its mechanism, including a
  deterministic mutual-exclusion test for the registry's own lock.

Closes #456

- **ecdf**: Name each curve of a hue-grouped ECDF from its own colour
  ([#584](https://github.com/xability/py-maidr/pull/584),
  [`74a8813`](https://github.com/xability/py-maidr/commit/74a881380927c53ddcfba714e279560e04da689b))

Co-authored-by: Claude <noreply@anthropic.com>

- **extract**: Bind a layer to the artist its own call drew
  ([#554](https://github.com/xability/py-maidr/pull/554),
  [`86d5b40`](https://github.com/xability/py-maidr/commit/86d5b405614e62c0518df4d1b7abcd357b3298ee))

`HeatPlot` found its artist by searching the axes rather than by being told which one it was
  registered for, so two heatmaps on one axes were both announced with the first one's values -- the
  second chart's numbers appearing nowhere, and nothing raising (#527).

The layer is now handed the artist its own call drew, as `ScatterPlot._own_points` already was, with
  the axes search kept as the fallback. `seaborn.heatmap` returns an `Axes` rather than its mesh, so
  the patch finds it on the axes and takes the last grid: the call registering right now drew the
  newest one.

The audit the issue asked for found the identical defect in `HistPlot` -- two `ax.hist()` calls both
  announcing the first histogram's bins -- fixed here on both the matplotlib and the seaborn paths.
  Two `ax.bar()` and two `ax.plot()` calls were measured correct.

It also surfaced a crash that predates all of this: `ax.hist([a, b])` raises from the user's own
  plotting line because the patch hands a list of containers to `get_axes`. Filed as #553.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>

- **heatmap**: Name a heatmap's cells from the grid, not from the axis ticks
  ([#551](https://github.com/xability/py-maidr/pull/551),
  [`54eb6da`](https://github.com/xability/py-maidr/commit/54eb6daaf6ed725058dd19f4467c324ccb4950b3))

A numeric heatmap took its column and row names from the axis ticks, which are positions a locator
  chose to look tidy and have no relation to where the cells fall. Measured on matplotlib 3.9.4, a 2
  x 3 `ax.hist2d(a, b, bins=(3, 2))` produced nine x labels for three columns, so a reader moving to
  the second column heard a number off the locator with no way to tell it was somebody else's
  coordinate (#526).

The ticks are now checked against the cells rather than assumed to be them, and the artist is asked
  when they disagree -- a mesh carries its boundaries as coordinates, an image as its extent. A cell
  is named by its centre, following `HexbinPoint`, at the shortest precision that keeps the names
  distinct.

A curvilinear `pcolormesh(X, Y, Z)` whose columns do not share an x has no one name per column, and
  declines rather than naming every column after the first row. A `shading="gouraud"` mesh returns
  one coordinate per cell rather than one per boundary, so those coordinates are the positions and
  are used directly.

`extract_level` and `extract_level_positions` now share one `_ticks_in_view()` filter, so their
  answers are index-aligned by construction.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>

- **heatmap**: Tell a picture from a grid of values instead of dying on both
  ([#565](https://github.com/xability/py-maidr/pull/565),
  [`6d1e0ee`](https://github.com/xability/py-maidr/commit/6d1e0ee33160b5ed7aaf21666e15a0d29374d7e4))

`ax.imshow` accepts three shapes. `(M, N)` of numbers is a heatmap; `(M, N, 3)` and `(M, N, 4)` are
  pictures, their last axis colour rather than value. A boolean `(M, N)` mask is a fourth case, and
  the one `ax.spy()` draws.

All three of the last ones raised at render, after the plotting line had already returned, from one
  line of `HeatPlot`:

[list(map(lambda x: float(format(x, self._fmt)), row)) for row in array]

`self._fmt` is "" unless seaborn's caller set one, and `format` with an empty spec is `str`: 'True'
  for a numpy bool, '[0.5 0.5 0.5]' for a row of an RGB image. It was never confined to the
  offending axes either -- a bar chart drawn beside a photograph died with it.

A mask is read. True and False are 1 and 0, and showing where a matrix is non-zero is the whole
  purpose of `spy()`. It only failed at the default format; `format(np.True_, ".2f")` was already
  "1.00", so the array is converted rather than the formatting special-cased, and both spellings now
  give the same numbers.

A colour image is not registered. There is no number per cell to announce and nothing for the
  colourbar the `z` axis describes to mean, so the layer is declined and the figure renders without
  it -- what `ax.quiver` and `ax.streamplot` already do. Inventing a reading for it, a luminance or
  a channel mean, would announce a number the chart does not show.

Closes #564

- **hist**: Name the hue groups of a filled step or poly histogram
  ([#589](https://github.com/xability/py-maidr/pull/589),
  [`5c24824`](https://github.com/xability/py-maidr/commit/5c24824cc2fe11d62348f489b9626943818c745d))

`sns.histplot(hue=..., element="step"|"poly")` split into one layer per group and named none of
  them, leaving two `hist` announcements over one axis with nothing to tell them apart.
  `element="bars"` named both, and #585 gave the unfilled outline its names, so the filled spelling
  was the only one still losing them.

Two halves, both needed: the patch computed no name at all, and `SteppedHistPlot.__init__` dropped
  its kwargs, so one handed over would not have arrived. The name comes off the outline's face
  colour rather than its edge, because `edgecolor=` colours every group's edge alike and an
  edge-based match then names nothing.

Closes #587.

- **hist**: Read a multi-dataset histogram instead of raising on it
  ([#556](https://github.com/xability/py-maidr/pull/556),
  [`1bf3713`](https://github.com/xability/py-maidr/commit/1bf37134175f66e28060ac2be1a77d6a86db3574))

`ax.hist([a, b])` -- the documented way to draw two distributions in one call -- killed the figure
  from the user's own plotting line, on all four histtypes (#553). `Axes.hist` returns a *list* of
  containers for several datasets, and a list of `Polygon` lists for the two step forms;
  `FigureManager.get_axes` read `.axes` off the first element, which neither has. Its list branch
  now recurses through `get_axes` itself, and every branch answers `None` rather than a bare
  `StopIteration`.

With the crash gone the reading is one layer per dataset: reading one container would announce one
  distribution and drop the rest. `barstacked` is read the same way, measured -- each container's
  bar heights are still its own dataset's counts, the stacking living in the bars' `bottom`.

Nothing is registered where there is no container, which is the two step histtypes. The layer
  registered for them raised `ExtractionError` at render and took the whole figure with it,
  single-dataset or not; they now take the static-image fallback. Reading them is filed as #555.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>

- **hist**: Read every group of a hue-grouped histogram, not just the first
  ([#559](https://github.com/xability/py-maidr/pull/559),
  [`3043d3b`](https://github.com/xability/py-maidr/commit/3043d3b46bf9292f46acb6db388a9c6aff21ba77))

Co-authored-by: Claude <noreply@anthropic.com>

- **hue**: Name a faceted panel's lone group from the legend that names it
  ([#609](https://github.com/xability/py-maidr/pull/609),
  [`40a8ba4`](https://github.com/xability/py-maidr/commit/40a8ba40ce5a77621ed9fef95b342c3a2a9b6bf8))

`names_for` declines a lone artist -- "a lone container needs nothing to tell it apart from" --
  which asks whether an artist is alone on its *axes*. That is right about one chart and wrong about
  one panel of a grid, where the figure holds several distributions and the panel holds one of them.

Measured on seaborn 0.13.2, three groups with `col` putting `a` and `b` in one panel and `c` alone
  in the other, `displot` gave `['b', 'a', None]` for bars, step outlines and KDE curves alike,
  while the same data drawn unfaceted named all three. The name was there for the asking: `name_for`
  on that panel's single colour returns `'c'`.

`names_for_panel` states the rule once and the five resolvers that reach the floor route through it.
  `faceted` is `len(plotter_axes(instance)) > 1`, read once per draw in each per-panel loop; both
  axes-level entry points keep the default `False`, so `histplot` and `kdeplot` are untouched.

The panel count decides it, not where the legend was hung: `FacetGrid` builds a figure legend for a
  single panel too, so reading that as licence would leave `displot(one_level, hue=...)` named and
  `histplot(one_level, hue=...)` unnamed. Both still emit `None`, and the one place the proxy
  diverges -- a grid whose hue has a single level -- is pinned rather than left to be discovered.

Closes #608

- **hue**: Name a pairplot's diagonals from the legend it builds afterwards
  ([#569](https://github.com/xability/py-maidr/pull/569),
  [`dc925ba`](https://github.com/xability/py-maidr/commit/dc925bad26c9828c3a028a5e39138497661f52e2))

#559 and #560 name a hue's layers by matching each artist's colour against the legend swatch that
  names it, and both did the match at registration. `sns.pairplot(hue=...)` is the one chart where
  that cannot fire, and the reason is timing rather than the match: `PairGrid.add_legend()` builds
  one figure-level legend after every panel has been drawn, so when the diagonals register there is
  no legend anywhere. Every diagonal came out anonymous while the scatters beside it were named.

Three things, and none of them works alone.

`GROUP_NAME` now takes a callable as well as a string, and the two classes that honour it resolve
  one at render. A caller who relabels the legend between drawing and rendering therefore changes
  what the chart says, which is the divergence `MaidrPlot._legend_title` already accepts for
  `axes.z`.

The legend is looked for on the figure when the axes has none of its own, which is where a
  `PairGrid` puts it -- and only when the figure carries exactly one. That reads one legend as
  naming every axes, which no artist can contradict: panels with independent hues draw the same
  default colour cycle. The axes' own legend always winning is the mitigation, and both halves are
  pinned.

`_group_names` delegates to `kdeplot._names_for` rather than matching inline. A pairplot draws its
  bars translucent and its swatches opaque -- measured, alpha 0.5 against 1.0 with identical hues --
  so the exact-RGBA comparison it made named nothing, and the guarded hue-only second pass the KDE
  side already had is what answers.

Closes #561

- **hue**: Name an lmplot's hue groups from the legend that names their colours
  ([#613](https://github.com/xability/py-maidr/pull/613),
  [`adcc871`](https://github.com/xability/py-maidr/commit/adcc8711653cb85848ce6040b0fb8cb36bbe0266))

`lmplot(hue=...)` is one `regplot` call per level, and each call registers a scatter and a fitted
  curve. The split was right -- the two point layers hold disjoint halves of the frame -- and all
  four layers came out anonymous, so a reader was handed point, curve, point, curve over one axes
  with nothing saying which pair was which, while the same data through `scatterplot(hue=...)` named
  both.

The colour has to name one *layer*, not one artist among several, so `name_for` rather than
  `names_for` -- #595's shape, since a `regplot` call draws one group entire. And the match has to
  be deferred: `FacetGrid.add_legend()` runs after every panel is drawn, so at registration there is
  no legend anywhere, which is the timing #561 hit with `pairplot` and the reason `GROUP_NAME`
  accepts a callable. The curve's colour is asked first, and the scatter's collection answers for
  `fit_reg=False`.

`ScatterPlot` and `ErrorBarPlot` opt into `GROUP_NAME` as part of this, so a binned
  `lmplot(x_estimator=...)` no longer announces a group and its own uncertainty as unrelated layers.
  A bare `regplot`, and an `lmplot` without a hue, draw one group against no legend and read exactly
  as they did.

Found while sweeping the seaborn coverage issues in #255; the rest of that sweep reads correctly
  today and is recorded in the issue.

Closes #612

- **hue**: Read a shared-axis panel's legend, so a jointplot's marginals are named
  ([#611](https://github.com/xability/py-maidr/pull/611),
  [`eac5141`](https://github.com/xability/py-maidr/commit/eac51417c27876439d4294f19ca560c809801f8b))

A `JointGrid` draws three panels off one hue mapping and hangs the one legend that names it on
  `ax_joint`. `legend_of` reads an axes' own legend and, failing that, a figure legend -- which is
  where a `PairGrid` puts one (#561). A `JointGrid` puts it in neither place as far as a marginal is
  concerned, so both marginals came back with two density curves and identical announcements, the
  defect #558 named on the two panels where it was not yet fixed.

The third place read is narrower than the figure fallback rather than wider: an axes an axis is
  *shared* with. A `JointGrid` builds its marginals sharing one with the joint axes, and matplotlib
  records it. Two panels of a hand-built figure do not share by default, so the hazard `legend_of`
  documents is untouched and still answers None; what is newly in scope is `plt.subplots(1, 2,
  sharex=True)` with a legend on one panel only.

The axes' own legend still wins, two sharers still decline, and two figure legends decline rather
  than falling through to a sharer.

Found while sweeping `pairplot`/`jointplot` against the roadmap in #345/#342; the other fourteen
  chart/kind combinations read correctly and are recorded in the issue.

Closes #610

- **kde**: Name each curve of a hue-grouped density, not just its bars
  ([#560](https://github.com/xability/py-maidr/pull/560),
  [`ff7dbd6`](https://github.com/xability/py-maidr/commit/ff7dbd6e686afd226baca2769156b9354c2051a3))

Co-authored-by: Claude <noreply@anthropic.com>

- **line**: Carry the interval a chart shades around a line
  ([#563](https://github.com/xability/py-maidr/pull/563),
  [`0755aa0`](https://github.com/xability/py-maidr/commit/0755aa0a04e608495efdb01c7125c70991e953f7))

Co-authored-by: Claude <noreply@anthropic.com>

- **line**: Decline a band shaded across the page rather than up it
  ([#603](https://github.com/xability/py-maidr/pull/603),
  [`e83a56a`](https://github.com/xability/py-maidr/commit/e83a56a5c4b3ea4d72458063c72592e9def07574))

`band_edges_at` reads the lowest and highest vertex at each x, which is a reading of a vertical
  interval, and its docstring claimed to assume nothing about orientation. Bracketing does not catch
  the difference: a horizontal band around a horizontal line surrounds it vertically too, because it
  surrounds it.

Measured, `plot(val, pos)` under `fill_betweenx(pos, val - .5, val + .5)` announced the polygon's
  vertical extent as yMin/yMax -- an artefact of the band being sloped, on the axis carrying the
  positions, which the chart states no uncertainty about at all.

`fill_betweenx` is the horizontal spelling outright, so the patch tags every region it draws with
  which way the fill runs and the reader skips a horizontal one. LinePoint carries no xMin/xMax, so
  the band is dropped rather than transposed.

Closes #601.

- **line**: Name each series from the legend entry that is its own
  ([#581](https://github.com/xability/py-maidr/pull/581),
  [`c136e5a`](https://github.com/xability/py-maidr/commit/c136e5a88ca3a308f6ea36c9ef359d46dff9beb4))

Co-authored-by: Claude <noreply@anthropic.com>

- **line**: Stop announcing matplotlib's own label as a series name
  ([#576](https://github.com/xability/py-maidr/pull/576),
  [`056b433`](https://github.com/xability/py-maidr/commit/056b433071526e4e1105aaeaf84f5a71ccaf4a92))

Co-authored-by: Claude <noreply@anthropic.com>

- **patch**: A drawing call that drew nothing registers nothing
  ([#624](https://github.com/xability/py-maidr/pull/624),
  [`f6ce07c`](https://github.com/xability/py-maidr/commit/f6ce07c156caef6275dc5f84ac71d44dfe1ff044))

`ax.bar([], [])` raised `ValueError("No plot found.")` out of the caller's own drawing call — not
  out of `maidr.render()`. An empty `BarContainer` has no children, so `FigureManager.get_axes()`
  found no axes on it and `create_maidr` raised, at the plotting line rather than at save time. So
  `import maidr` decided whether an existing script's `ax.bar()` returned at all. The chart itself
  was fine: rendering after catching the error succeeded.

A decline is a reading decision; an exception is a broken call.

Measured, four real observations plus a second call drawing nothing: an empty scatter beside a real
  one gave `point(4) point(0)` and now gives `point(4)`; an empty bar raised and now reads `bar(2)`;
  a chart that is only an empty call announced itself as interactive with `data: []` and now falls
  back to a static image through #443's existing path.

`drew_nothing()` reads only the artists whose emptiness is unambiguous — `Container`, `Collection`,
  `Line2D`, and a list of those. Everything else registers as before, so the change is additive by
  construction. That is also why the seaborn half of #623 stays open: `seaborn.scatterplot` returns
  the axes rather than its collection, so what it drew cannot be read off its return value, and an
  empty call still sweeps the axes and finds an earlier call's points.

Found by carrying xability/r-maidr#232's question across to this side.

Part of #623.

- **patch**: Forget a cleared axes' layers instead of appending beside them
  ([#500](https://github.com/xability/py-maidr/pull/500),
  [`9a4a690`](https://github.com/xability/py-maidr/commit/9a4a6900fbad959927f443e19b0ba906a11e4b0c))

`Figure.clear` was patched to drop a figure's registered layers; `Axes.clear` was not. Re-plotting
  into a cleared axes therefore appended a layer rather than replacing one, and the reader was
  offered a layer describing artists that are no longer drawn -- announced with confident values,
  and with a highlight resolving to nothing, because those artists never reach
  `HighlightContextManager`. A sighted reviewer sees one correct chart.

ax.clear() layers=2 y=[[1.0, 2.0, 3.0], [9.0, 9.0, 9.0]] plt.cla() layers=2 y=[[1.0, 2.0, 3.0],
  [9.0, 9.0, 9.0]] fig.clear() layers=1 y=[[9.0, 9.0, 9.0]]

It accumulated: five clear cycles left six layers. `ax.clear()` is the ordinary way to redraw into a
  reused axes, so the two spellings of one intent behaved differently and the correct one was the
  less common.

`clear_axes` rather than reusing `clear()`: on a figure with several axes, clearing one must leave
  the others registered. Keyed by `_layer_axes_key`, so a `twinx` twin -- a second axes at the same
  grid cell -- does not take the axes it was twinned from with it. Both `Axes.clear` and `Axes.cla`
  are patched because they delegate to each other, and the inner call resolves to the patched
  method, so a single `ax.cla()` fires the hook twice by construction; `clear_axes` is idempotent
  for that reason.

Dropping the layers is not sufficient on its own. `lineplot` keeps its own "already registered"
  latch on the axes, which matplotlib does not reset because it does not own it. Clearing the layers
  while leaving the latch set made the next `ax.plot()` register nothing, taking the chart from
  mis-described to completely undescribed -- `subplots: [[{}]]`. `forget_axes_state` removes it, and
  runs before the registration lookup, since that state outlives any maidr entry. Audited:
  `lineplot` is the only module keeping state on an axes; `mplfinance` sets three attributes, but on
  `Line2D` artists, which a clear discards.

Also fixes a second defect in the same area: `Maidr.clear()` emptied `_plots` and left
  `selector_ids` behind. The two are paired by index in both directions -- `_drop_superseded_layers`
  documents the invariant -- so the next layer registered wore the id minted for a layer that no
  longer existed. Nothing raised.

Tests are the first coverage the clear patch has had, and each was falsified against the code it
  pins: unpatching `Axes` fails 5, dropping every axes instead of one fails 3, skipping
  `forget_axes_state` fails 3, and leaving `selector_ids` behind fails 1. An AST guard fails when a
  future patch module stashes its own state on an axes without registering the cleanup, with its own
  limits stated rather than implied.

Closes #499

- **patch**: Say which seaborn is installed when it is too old
  ([#486](https://github.com/xability/py-maidr/pull/486),
  [`f90fde5`](https://github.com/xability/py-maidr/commit/f90fde5d24321bada544f1a523d990611c9c5c8b))

Every patch module wraps a seaborn internal by name, and the ones under `_CategoricalPlotter` and
  `_DistributionPlotter` arrived in 0.13. On an older seaborn wrapt raises while `maidr.patch` is
  being imported:

AttributeError: type object '_CategoricalPlotter' has no attribute 'plot_bars'

Nothing there names seaborn, names a version, or says what to do, and it arrives before any of the
  user's code runs. `pyproject.toml` declares `seaborn>=0.13` so a resolver will not pick 0.12 on
  its own, but `--no-deps`, a conflicting pin, or an old lockfile all still land there.

This does not make an old seaborn work. It replaces an error that says nothing with one naming the
  installed version, the required version, and the upgrade command. An unreadable or absent version
  is allowed through: refusing to import on a string we merely failed to parse would break installs
  that work.

Reproduced against a real seaborn 0.12.2, which raised on `plot_bars` rather than the `plot_boxes`
  in the issue -- the boxplot site had already been fixed and four others had not.

Refs #441

- **plotly**: Decline a category order on a date axis too
  ([#493](https://github.com/xability/py-maidr/pull/493),
  [`086d2e6`](https://github.com/xability/py-maidr/commit/086d2e6d86d0bb723b2c33fa64d5231c31daca19))

#491 guarded against plotly resolving a linear axis from numeric-looking labels, on which
  categoryorder and categoryarray are ignored. It did not guard against a date axis, which ignores
  them the same way -- so a heatmap over ISO dates had a declared order applied to a chart plotly
  draws chronologically.

Measured: year-first and hyphen-separated is a date; slashes, day-first and month names all stay
  categories and keep their array. Plotly is more lenient about the shape than a regex naturally is
  -- it accepts single digits and leading whitespace -- and stricter about the parts, rejecting
  February 30th. So the shape is matched loosely and the parts handed to datetime.date, which
  rejects an impossible day for the same reason plotly does.

A declared type: "category" still brings the order back, as it does for numbers.

Falsified: dropping the date half of the guard fails exactly the ISO cases, and restoring the
  pattern-only check fails the two spellings it missed plus the impossible day it wrongly accepted.

- **plotly**: Drop a layer whose payload holds nothing
  ([#638](https://github.com/xability/py-maidr/pull/638),
  [`686758f`](https://github.com/xability/py-maidr/commit/686758f1523bbde91eb7d1c709dedf1fd4f1880b))

#421 established that a trace plotly draws nothing for forms no layer, and implemented it by
  excluding an undrawn trace from the line and area groupings. Every other family appended
  unconditionally, so an empty pie, sankey, hierarchy, polar or parcoords became a layer with an
  empty payload — a cell the reader can tab into and find nothing in, and for the line-family types
  a render that throws.

One guard on the rendered payload, after the build blocks, so every trace type reaches the same
  answer and a new one inherits it. `draws_marks()` stays: it also keeps the positions of the
  surviving series contiguous, which a later filter cannot recover.

Asked of the payload because there are three shapes and one question — a list, the gauge's `{value,
  min, max}`, and the heatmap's `{points: [...]}`. A mapping carries data when any field is a scalar
  or a non-empty collection, so a dial reading `0` on a `[0, 0]` range survives while an empty
  heatmap does not. One level only: a heatmap of one empty row is kept, because guessing at nested
  emptiness risks dropping a layer that should have shipped.

Five tests that pinned the old behaviour now pin the new one. One of them asked for exactly this:
  "pinned so a later widening of the predicate is a deliberate choice rather than a side effect."

Closes #636.

- **plotly**: Emit a heatmap top row first so ArrowUp moves up
  ([#488](https://github.com/xability/py-maidr/pull/488),
  [`1a31dd5`](https://github.com/xability/py-maidr/commit/1a31dd5d777cdded7fa52fed7244e4541c8cdad1))

Closes #487. Python-side counterpart of xability/maidr#971.

The MAIDR grammar's heatmap data runs top-first, and the core reverses it so its own row 0 is the
  bottom of the drawn grid. Plotly numbers a heatmap's rows from the bottom and `_extract_plot_data`
  passed `z` and `y` through untouched, so the cursor entered at the top row and ArrowUp walked
  down.

A reversed y axis is left alone. Detection differs from the JavaScript side: the resolved layout
  there reports `autorange: true` either way, while the declared layout here still carries
  "reversed" verbatim, so both spellings are read.

The selector is `.heatmaplayer image`, whose overlay rects the core corrected in maidr#972. That
  correction and this one used to cancel, so without this the next bundle bump would have started
  mis-highlighting a chart that only navigated wrongly before.

The matplotlib path is unaffected: seaborn draws its row 0 at the top and HeatPlot emits it first.

- **plotly**: Fill a contour's holes before tracing it, the way plotly does
  ([#654](https://github.com/xability/py-maidr/pull/654),
  [`b88554a`](https://github.com/xability/py-maidr/commit/b88554a396f89a1e4d396c670f7d08b12c6028a5))

Closes #651.

A missing point in a contour's `z` was masked, on the reading that the curves should stop at it.
  Plotly runs `findEmpties` and `interp2d` over the grid first and traces the curves through what
  was missing, so the emitted curves were up to 0.91 data units away from the drawn ones on a grid
  whose cells are 0.5 across, against a 0.16 sampling floor.

`maidr/plotly/holes.py` transcribes the rule from the shipped bundle rather than approximating it;
  thirteen filled fields match plotly's own `calcdata` to 1e-9.

- **plotly**: Honour a bin spec that names a start or an end but no size
  ([#652](https://github.com/xability/py-maidr/pull/652),
  [`ef1b59f`](https://github.com/xability/py-maidr/commit/ef1b59fae5715e658dc26ffd4affc5846c338529))

`compute_bin_edges` read `xbins.start` and `xbins.end` only inside its explicit-size branch, so a
  spec that named a window without a width fell through to the automatic path, which never looked at
  either. Measured: `xbins=dict(start=0.5)` over twenty integers is drawn by plotly as five bars of
  5, 3, 6, 3, 3 and was announced as six bins of 2, 5, 5, 3, 4, 1.

The two paths become one: work out the width, then apply the author's start and end over it. Four
  things measured on the way, each its own test -- a window that is not a whole number of bins keeps
  its part-bin; the last bin is half-open like the rest; a `size` of 0 is an absence and takes an
  `nbins` hint with it; a sample with no spread is one bin wide. A negative width declines rather
  than answering with one bin holding everything.

168 emitted bins matched the drawn bars across four samples, fourteen `xbins` shapes and three
  `nbinsx` settings; 44 more on the 2-D path.

Also, from review: a grouped histogram counts its bins through the same assignment a single one
  does, so the two paths in that file cannot disagree about a value on the window's end; and a value
  that is not a number is outside every bin rather than one past the last.

Closes #650

- **plotly**: Name a markers-only radar's markers, not a path it has none of
  ([#657](https://github.com/xability/py-maidr/pull/657),
  [`a02ab88`](https://github.com/xability/py-maidr/commit/a02ab8841b42e3ecdd54efe68cebae54157b0067))

Closes #656.

`PolarPlot._get_selector` named `path.js-line`, on a measurement that held for every mode drawing a
  line and for none that does not. A `mode="markers"` scatterpolar draws no line, so the selector
  resolved to nothing and the layer shipped a highlight that finds no element.

The markers are named instead -- one `path.point` per sample, which is the shape
  `LineTrace.mapViaDomElements` already takes. A `mode="text"` trace draws neither and keeps no
  selector, for the reason `barpolar` has none.

Found by resolving every emitted plotly selector against the drawn chart in Chromium: twenty-seven
  figures, and this was the one selector that matched zero elements.

- **plotly**: Read a bar chart in the order categoryorder draws it
  ([#614](https://github.com/xability/py-maidr/pull/614),
  [`58d9f2b`](https://github.com/xability/py-maidr/commit/58d9f2b30b0d28e245ead18d9fd708f093cbbd99))

`categoryorder` sorts the category axis and leaves the trace's own `x` and `y` exactly as the author
  wrote them, so a chart written `charlie, alpha, bravo` and drawn `alpha, bravo, charlie` was
  emitted in the trace's order. Every label still carried its own value and the highlight still
  landed on the right bar, so nothing read as broken -- what was wrong is everything that treats the
  index as a position: arrowing direction, the stereo pan, the braille line, the autoplay sweep, and
  which cells a stacked summary sums together.

`_drawn_category_order` and the three axis-type helpers it needs move from `PlotlyHeatmapPlot` to
  `PlotlyPlot`, unchanged and with their limits intact: only `array` and the two `category` sorts
  are resolved offline, and a numeric or ISO-date axis ignores `categoryorder` outright.

The selectors move with the data, because a reordered payload against an unmoved selector is a right
  reading with a wrong highlight. Measured in Chromium: `.point` groups are written in the trace's
  order, and

`.point:nth-of-type(k)` names the kth of them exactly. A grouped or stacked layer gets the
  `string[][]` grid its cells are addressed by, one row per trace.

Each trace resolves its own permutation. They share the axis, so they share the drawn sequence of
  category names; they do not share the positions those names sit at, and applying one trace's
  indices to another puts a point in a column belonging to a different category. Traces whose name
  sequences differ are declined whole.

A chart that declares no order, or one that cannot be resolved, keeps the single selector string it
  has always had.

Closes #495

- **plotly**: Read a heatmap in the order plotly draws it
  ([#491](https://github.com/xability/py-maidr/pull/491),
  [`8beebeb`](https://github.com/xability/py-maidr/commit/8beebebb6e411510e959ca361c474b7cefca21dd))

categoryorder sorts a categorical axis and leaves the trace's own x, y and z exactly as the author
  wrote them, so the emitted payload described a grid plotly was not drawing. Every label still sat
  on its own value, which is why nothing looked broken; what was wrong was where the cells were, and
  the core's highlight -- placed purely by index over the rasterised image -- outlined a different
  cell from the one announced.

Resolves the sort from the declared layout, since there is no browser here, and permutes both the
  labels and the grid to match. The reversal check is generalised to either axis while it is here,
  so a reversed x axis turns the columns over the way a reversed y axis already turned the rows.

Only the forms a declared spec can answer exactly are resolved: array with a categoryarray -- what
  plotly express's category_orders compiles to -- and the two category sorts. The aggregate orders
  are declined rather than rebuilt offline, where a sort that is subtly not plotly's would be just
  as silently wrong.

Declines too when the axis is not categorical (plotly resolves a linear axis for numeric-looking
  labels and ignores the order there), when the resolved order is not a permutation of what the
  trace names, and when the grid is ragged.

Falsified per fix rather than in aggregate: reverting any one of the six changes fails exactly its
  own cases and leaves the rest green.

Closes #489.

- **plotly**: Round a bin width up strictly, the way plotly does
  ([#648](https://github.com/xability/py-maidr/pull/648),
  [`eebbdf7`](https://github.com/xability/py-maidr/commit/eebbdf7d5aea9bbfb8bc52fe07f780ecd8002081))

`_plotly_dtick` rounded a rough bin width up to a 1/2/5x10^n value with `>=` and a tolerance, where
  plotly's `Lib.roundUp` is strictly greater: its binary search advances on `arrayIn[mid] <= val`,
  which steps past an exact match. The two agree everywhere except where `size0 / base` lands
  exactly on 2, 5 or 10, and there the loose reading picked the width below the one plotly draws --
  twice as many bins, half as wide, every count wrong to match.

Measured: `go.Histogram(x=linspace(0, 30, 61), nbinsx=15)` draws bins of 5 and py-maidr computed 2.

The fix is to stop keeping a second copy of `roundUp`. The helper beside it had the search right all
  along, so `_plotly_dtick` now goes through it and the duplicate loop is gone.

Closes #646.

- **plotly**: Scope a heatmap's selector to its own image
  ([#655](https://github.com/xability/py-maidr/pull/655),
  [`6a38c21`](https://github.com/xability/py-maidr/commit/6a38c213d3576731302cf3bcd0a6a7435ba41fec))

Closes #647.

`.heatmaplayer image` named the first image on the subplot rather than this trace's, so a subplot
  holding two of them had both layers outlining the same one. Plotly appends one `g.hm` per
  image-drawing trace in declaration order, counting `heatmap` and `histogram2d` together, so both
  now take their position from `layer_position` and the selector names the group:
  `g.hm:nth-of-type(N) image`.

`image:nth-of-type(N)` does not work -- each image is the only one inside its own `g.hm`, so
  `:nth-of-type(1)` matched both of two and `:nth-of-type(2)` matched none.

- **pointplot**: Keep a hued point plot's confidence intervals
  ([#501](https://github.com/xability/py-maidr/pull/501),
  [`5095f3d`](https://github.com/xability/py-maidr/commit/5095f3d5fbd3a1ff8605c6ab74a4e9bf8f7190a8))

`sns.pointplot(..., hue=...)` read as a plain `line` layer. The estimates survived; the intervals
  did not -- a reader of a grouped point plot was handed the means of a chart drawn to show the
  uncertainty around them.

That was the right call at the time: the error bar layer carried a single flat series with no field
  naming the group, so pairing n groups' interval lines onto it would have attached one group's
  bound to another's estimate. maidr 4.4.0 gave the grammar a grouped shape -- `ErrorBarPoint[][]`
  with a `z`, xability/maidr#942 -- and it is in the bundle this package ships, so the intervals now
  have somewhere to go.

Seaborn draws the interval polylines estimate-major: every category of the first group, then every
  category of the second. Measured rather than assumed, with each estimate's value falling inside
  the span of the interval its slice pairs it with. Group names come from the legend, the only place
  they appear, and its title becomes `axes.z`.

Driven in Chromium against the bundled `maidr.js` rather than stopping at a schema that matches the
  docs:

g is a, value v is 0.82, grp is p g is a, upper bound v is 1.15, grp is p g is a, lower bound v is
  0.77, grp is q g is a, value v is 1.06, grp is q g is a, upper bound v is 1.35, grp is q

p's upper and q's lower are adjacent moves, so the overlap the chart exists to show is audible --
  the ordering xability/maidr#943 designed for.

The ungrouped path is untouched and still emits the flat form.

Naming is all-or-nothing. A legend that does not list exactly one entry per drawn group names none
  of them, so the schema can never declare an `axes.z` while some of its series carry no `z`. That
  count check is also the only guard available on the assumption underneath the naming -- that
  seaborn lists legend handles in draw order -- since a name has no geometry to check it against;
  recorded as #502.

Guards added where the module would otherwise have guessed: intervals that do not divide evenly
  among the groups are refused, which catches a list one *too long* (one too short was already
  caught downstream). A hue level padded into a category it was never observed in emits `null`
  rather than the raw NaN, which is not JSON and stopped the chart initialising (#429).

Four tests that pinned the old fallback now pin the new behaviour, each keeping its original
  subject. `test_a_horizontal_dodge_names_its_groups` moved its assertion from `y` to `x`: an error
  bar layer carries the category as `x` in both orientations and lets `orientation` say which is on
  screen, so that is a change of key rather than of behaviour.

New tests target the failure modes rather than the happy path: three groups, because a two-group
  off-by-one still lands inside the interval list; a genuine single-observation group, because three
  identical observations still draw an interval and the first version of that test therefore never
  reached the branch it named; and a `hue_order` reversal over levels whose names are recoverable
  from their values, because every other fixture uses interchangeable labels where a swapped naming
  reads identically to a correct one.

Closes #462

- **pointplot**: Name a hue group by the colour it was drawn in
  ([#507](https://github.com/xability/py-maidr/pull/507),
  [`1b2ca24`](https://github.com/xability/py-maidr/commit/1b2ca24abe00f37d4fd183ea7b1b202482d20d01))

`_group_labels` handed the legend's names to the estimate lines positionally, which is only right
  while seaborn lists its handles in the order it drew the series -- true today, not part of its
  public API. A release that kept the count and reordered the legend would put every name on the
  wrong group, with the estimates and bounds all correct.

The hue mapping that names a group is the same one that colours it, so matching each legend handle's
  colour to an estimate line's is independent evidence rather than the same assumption restated.
  Legend order stays the fallback for the cases colour cannot settle.

Closes #502

- **seaborn**: An empty scatterplot no longer announces the previous call's points
  ([#625](https://github.com/xability/py-maidr/pull/625),
  [`036bdf7`](https://github.com/xability/py-maidr/commit/036bdf7f0a7923900dcb2dc5139c6c9c24d0f172))

A second `seaborn.scatterplot(data=<empty>)` registered a layer holding the first call's points —
  the same four points twice, under two layers, with nothing to say they were the same. Not an empty
  layer but a wrong one, and the worst of the three defects #623 recorded.

`seaborn.scatterplot` returns the axes rather than its collection, so `drew_nothing()` (added in
  #624) has nothing to read, and `_points_of` falls back to sweeping the axes — right for a call
  that drew one collection, and finding a stranger's for a call that drew none.

Told apart by the collection count: a call that drew points adds one, a call that drew none adds
  none. The count is taken before the draw and used only when the axes counted is the one the call
  came back with, so a wrong guess about which axes seaborn drew on decides nothing and registers as
  before.

The guard rail is asserted rather than assumed: two genuine seaborn scatters must still give two
  layers, since a rule keyed on "the axes already has a collection" would have folded them together
  — a worse failure than the one being fixed.

Closes #623.

- **seaborn**: Split a colour-grouped seaborn.objects bar, and get its categories back
  ([#619](https://github.com/xability/py-maidr/pull/619),
  [`10cb434`](https://github.com/xability/py-maidr/commit/10cb434dc1c536ca53dae5b4ab804b6fc9ea174f))

A colour-split `so.Bar` read as a bar chart whose categories were coordinates: `BarPlot._labels_for`
  announces bar positions whenever the tick labels do not number the bars, and every level's bars
  land on one axes against one tick per category. Measured with `Dodge()`, a reader was told the
  categories were `-0.2`, `0.2`, `0.8`, `1.2` — the dodge offsets.

`bar_groups()` does for a `BarContainer` what `hue_groups()` does for a `PathCollection`, and both
  now end in one shared `groups_from_colours()`. The handover is a synthetic `BarContainer` per
  group, so the selectors resolve unchanged and each layer addresses its own bars. `BarPlot` opts
  into `GROUP_NAME`.

Review follow-up in the same branch moved the decline reasoning into `groups_from_colours`, where it
  runs, and closed a live coverage hole: dropping `orientation=` from the synthetic container passed
  the whole suite before, and would have made a split horizontal bar default to vertical.

Part of #617.

- **seaborn**: Split a colour-grouped seaborn.objects scatter into its groups
  ([#618](https://github.com/xability/py-maidr/pull/618),
  [`bad5cc2`](https://github.com/xability/py-maidr/commit/bad5cc2abfa45e4422cf667f6ff6a28c28cdea0f))

#615 made every so.Dot register; it registered as one layer holding every point, where the classic
  spelling of the same chart has split and named its groups since #544. Measured, two levels of
  three:

so.Plot(frame, x=, y=, color="g").add(so.Dot()) point None (6) sns.scatterplot(data=frame, x=, y=,
  hue="g") point 'p' (3) point 'q' (3)

Two things had to change, and neither alone is enough.

hue_groups asked the wrong legend. It read ax.get_legend() where the rest of the module goes through
  legend_of, which also reads a lone figure legend (#561) and a lone shared-axis sibling's (#610). A
  so.Plot puts its one legend on the figure, so the axes had none and the split declined before
  looking at a colour. The full suite is unchanged by the widening: no existing chart read
  differently for having asked the narrower question.

The split was asked too early. Plotter._plot_layer is the only place that can say which artists a
  layer drew, and Plotter._make_legend runs after every layer is on the page. A name can be deferred
  to render as a callable, which is what #612 did for FacetGrid; a split cannot, because it decides
  how many layers there are. So the reading is recorded during the draw and registered from
  Plot.plot, which show(), save() and _repr_png_() all reach.

so.Line(color=) is deliberately unchanged: it reads as one layer of two series, exactly what
  seaborn.lineplot(hue=) already does. so.Bar(color=) draws every level into one container, unlike
  seaborn.barplot(hue=), and its split needs an answer this does not have.

Part of #617.

Co-Authored-By: Claude <noreply@anthropic.com>

- **shiny**: Keep the reader on the chart across a re-render
  ([#485](https://github.com/xability/py-maidr/pull/485),
  [`9fe0978`](https://github.com/xability/py-maidr/commit/9fe09781ede781ee9a9a2651f9b88f33da217a9a))

A Shiny output is replaced wholesale on every reactive flush, taking the focused element with it. A
  reader partway through navigating a chart who changed any input was returned to the top of the
  document, silently -- for a keyboard-driven, sonification-first interface, the difference between
  a dashboard being usable and not.

Focus is restored only when the element that held it left the document and focus landed nowhere, so
  a reader who moved to another control on purpose is never pulled back, and a chart nobody focused
  never takes focus.

Two findings rule out an event-driven version, both established in a browser: removing the focused
  element does not reliably fire blur, and focusing *into* an iframe fires no focusin in the parent
  document at all.

Adds tests/browser/, a Playwright suite driving real Shiny and Streamlit apps in Chromium, behind
  --run-browser and a CI job. It covers the fix from both directions, the offline runtime report,
  the iframe's accessible name, and the key collision the Streamlit iframe exists to prevent.

Closes #484 EOF

- **streamlit**: Render one figure at a time, as the Shiny door already does
  ([#531](https://github.com/xability/py-maidr/pull/531),
  [`dbaa35c`](https://github.com/xability/py-maidr/commit/dbaa35cf3c947175762d59c1a3af403109b311d4))

Streamlit runs every session's script in its own ScriptRunner thread, and nothing serialised the
  render, so two sessions sharing one figure could be inside savefig together. savefig writes
  fig.dpi for its duration, so the loser drew its whole chart at the other call's dpi: a well-formed
  SVG at 72% scale, measured at 1 in 30 concurrent renders.

The per-figure lock added for Shiny in #504 moves to maidr/util/figure_lock.py and both doors take
  it, from one registry -- two registries would let a Shiny render and a Streamlit render of the
  same figure overlap.

Resolving which figure to lock moved with it and gained two shapes it was silently missing: a Figure
  and None both resolved to no figure, so a Shiny render function returning fig rather than ax was
  unsynchronised. Resolution now follows maidr.render's own, resolved once per call so a concurrent
  plt.figure() cannot move the current figure between the lock and the write.

Refs #454.

- **triplot**: Decline a triangulation mesh instead of reading it as a line
  ([#573](https://github.com/xability/py-maidr/pull/573),
  [`5bc029d`](https://github.com/xability/py-maidr/commit/5bc029d2feb7f48ee095e3ab2a08a371ce9b7d3d))

`ax.triplot` draws the mesh by handing the flattened edge list to `Axes.plot`, so the line patch saw
  an ordinary plot call and registered a LINE layer. Measured on eight scattered points: a line of
  *thirty-two*, x running 0.04 -> 0.64 -> 0.04 -> 0.27, the first point appearing again as the
  third.

That is the mesh's edge traversal -- three vertices per triangle and a separator -- not a sequence
  of observations. A line trace tells a reader there is a trend through ordered values and offers to
  play it as one; here there is no order, points repeat, and the count bears no relation to the
  data. Worse than being unread, because nothing about it looks wrong.

Declined rather than given a reading: the mesh states which points were joined, and no trace in the
  core carries that. Suppressed by drawing inside the internal context so the inner `plot` calls
  register nothing, which has to happen in the patch -- a layer that refuses while the schema is
  built takes the whole figure with it (#564).

A `triplot` is usually drawn under a `tricontour`, and that half still reads, in either drawing
  order. An ordinary `plot` after one still reads too, which pins that the internal context does not
  leak. A mesh labelled "fit" or "smooth" is still declined, which pins that the second patch on
  `Axes.plot` cannot slip a layer past the decline.

The rest of what #568 left over turns out to be declining correctly already, and is now pinned
  rather than merely unobserved: `contourf`, `tricontourf`, `tripcolor`, `ax.fill`, `quiver`,
  `barbs` and `streamplot`.

The filled contours are the interesting ones, because their unfilled twins do read. Measured on one
  field with `levels=[1, 2, 4]`: an unfilled path sits at a single level, a filled one spans two --
  path 0 runs z = 1.0 to 2.0, the band *between* levels. Announcing that outline as a level's own
  curve would be right for about half its vertices, which is the rule xability/r-maidr's
  `Ggplot2ContourLayerProcessor` already states for `geom_contour_filled()`. Both bindings agreeing
  is worth keeping, so the measurement is asserted rather than described.

Closes #572

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>

Claude-Session: https://claude.ai/code/session_015TFhhzxcMetSHV7z9NCrJ8

- **util**: Let extract_collection answer where its caller handles None
  ([#552](https://github.com/xability/py-maidr/pull/552),
  [`1704abb`](https://github.com/xability/py-maidr/commit/1704abbe843e86d2fdc75bad57cc83279e0e5689))

`CollectionExtractorMixin.extract_collection` reached "no collection of that type" through a bare
  `next()`, so an axes holding none raised `StopIteration` rather than returning `None` (#529).
  Every caller is written for `None` and opens with a guard that could never run; inside a generator
  PEP 479 turns the bare `StopIteration` into a `RuntimeError` naming neither the axes nor the type,
  and it kills the whole render rather than the one layer.

`next()` now takes a `None` default, so the three sibling extractors agree: nothing found is `None`,
  not an exception. This is the same shape of failure #388 removed from `extract_container` and #520
  from `extract_scalar_mappable`.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>

### Continuous Integration

- Gate the release on the accessibility browser tests
  ([#492](https://github.com/xability/py-maidr/pull/492),
  [`b059ecd`](https://github.com/xability/py-maidr/commit/b059ecd91c54298f26e0b906746572a0dba908d0))

`release.yml` is the last check before PyPI and ran a strictly weaker suite than the CI that gates a
  pull request.

`tests/browser/` is opt-in behind `--run-browser`, which only `ci.yml` passed, so every browser test
  silently skipped on the release path -- the focus restore, the offline runtime report, the
  iframe's accessible name, and the Streamlit key-collision check. The release job also installed
  `--extra test --extra visualization`, and `streamlit` is deliberately not in the `test` extra, so
  every `importorskip("streamlit")` test skipped there too.

The release refreshes the bundled maidr.js, which is exactly the change able to break navigation
  while every markup assertion still passes, and the tests that would notice were the ones not
  running.

`release` now needs the browser job, so a chart that cannot be driven from the keyboard blocks the
  publish. Also adds the `uv lock --check` step `ci.yml` runs and `release.yml` had in no job.

Closes #490

### Documentation

- Point the websocket-payload note at an issue that is still open
  ([#537](https://github.com/xability/py-maidr/pull/537),
  [`e057902`](https://github.com/xability/py-maidr/commit/e0579023dcf0a68152e5dea6c29edf37d7b4eb46))

The "Shiny and other async servers" callout said the per-flush payload was "still open in #454".
  That issue closed once the event-loop work shipped, so the link now lands a reader on a resolved
  issue and implies the payload question is settled too. Serving the chart out of band was never
  actioned and is tracked in #534, which is where the callout points.

Also notes that the same-figure lock is shared with the Streamlit path rather than private to the
  Shiny one, which is what #531 changed.

- Stop telling Shiny users their event loop is blocked
  ([#511](https://github.com/xability/py-maidr/pull/511),
  [`af0ae1e`](https://github.com/xability/py-maidr/commit/af0ae1e831f9f28c5e788873cfa81654bde5f184))

`docs/index.qmd`'s async callout still described the state of things before #504 -- "the render
  itself still blocks", "for as long as one render runs, the loop does not run at all", "one render
  holds the loop for about 55 ms". #504 moved the render to a worker thread, so that paragraph has
  been wrong since it landed, and a reader today concluded their app stalls once per reactive flush
  when it does not.

Found by checking the doc against the code. Nobody files a bug against documentation that is merely
  out of date.

Re-measured through the shipped renderer on a 50-bar chart, longest gap between successive ticks of
  a 1 ms ticker, after a warm-up:

idle, no rendering 1.4 ms render on the loop, as it was 609.3 ms render on a worker thread, now 12.5
  ms

Same throughput either way, and 609.3 ms independently reproduces the 602.7 ms measured on #454 with
  a prototype.

The callout now also states what the fix does not buy, so the correction does not over-claim in the
  other direction: same-figure renders are still serialised because they race on `fig.dpi`, and the
  chart still crosses the websocket every flush, which is #454's remaining option.

`tests/core/test_render_is_synchronous.py` keeps its assertion -- the underlying `maidr.render()` is
  still synchronous, which is what makes moving it off the loop necessary -- but no longer claims
  "every other session on that worker is stopped", a statement about `render_maidr` rather than
  about the function it measures. Its failure message now names both files to update.

Verified by rendering the page with Quarto: the table, which is the first one inside a callout in
  this file, nests in the callout body, and all three stale strings are absent from the built HTML.
  `docs.yml` runs only on push to main, so nothing in PR CI would have caught a broken render.

- Tell Shiny readers what the render lock does not cover
  ([#549](https://github.com/xability/py-maidr/pull/549),
  [`58db3e5`](https://github.com/xability/py-maidr/commit/58db3e538bc5dea257550aad943f7b8476258466))

The async callout ended on the render lock, which reads as though shared figures are handled. They
  are not: the lock serialises renders against each other, and an app drawing into a figure another
  session is rendering still produces a chart whose SVG and announced data disagree -- visible to a
  sighted reader, invisible to a screen-reader one.

Since #541 that says so when it happens, and the audience for the warning is exactly the reader of
  this callout: someone running concurrent sessions against a figure they cache. The callout now
  shows the message, how to silence it when the sharing is deliberate, and the limit the warning
  cannot state about itself -- it notices artists appearing, disappearing and being relabelled, not
  values changed in place, so its silence is not a guarantee that a render was clean.

A test holds the quoted message to the one the code raises, comparing them with the figure's name
  removed from both sides. Quoting a warning verbatim makes it part of the public-facing contract,
  and this is the third drift of that kind found today, after a docs link to a closed issue (#537)
  and a test naming a symbol that had moved (#541).

Refs #530.

### Features

- **core**: Read a correlogram as the lollipop chart it draws
  ([#580](https://github.com/xability/py-maidr/pull/580),
  [`f1d9554`](https://github.com/xability/py-maidr/commit/f1d95540cef57506ac40b73324d506998ee3e64e))

Co-authored-by: Claude <noreply@anthropic.com>

- **core**: Read a hue-grouped scatter as one layer per group
  ([#545](https://github.com/xability/py-maidr/pull/545),
  [`5e316bd`](https://github.com/xability/py-maidr/commit/5e316bd456f939bbb690c770491dbc560803c351))

Co-authored-by: Claude <noreply@anthropic.com>

- **core**: Read ax.eventplot as the raster of event times it draws
  ([#550](https://github.com/xability/py-maidr/pull/550),
  [`c7cac64`](https://github.com/xability/py-maidr/commit/c7cac64cbc08efad2ffa0e377f95cac093bb26db))

An event plot -- a spike train, an arrival timeline, a raster -- registered no layer at all. Each
  row is read as a scatter of its event positions, one layer per row, named from the axis ticks by
  the row's own offset.

Rows are read through `get_segments()` rather than `get_positions()`, which raises on a row holding
  a single non-finite value, and the gid the selectors address is assigned at registration because
  matplotlib stamps one only at draw time.

- **core**: Read ax.tricontour as the field it draws
  ([#547](https://github.com/xability/py-maidr/pull/547),
  [`6af3358`](https://github.com/xability/py-maidr/commit/6af33589c35a21ac9cf7acdd65fa54e088210cfc))

Co-authored-by: Claude <noreply@anthropic.com>

- **core**: Read Axes.broken_barh as the gantt chart it draws
  ([#533](https://github.com/xability/py-maidr/pull/533),
  [`86bd78f`](https://github.com/xability/py-maidr/commit/86bd78f1b0144efea135cfd79c96fe19ade93d90))

Closes #524 (the first of the three it names).

One `broken_barh` call is one lane: the `yrange` places it, each `(start, width)` in `xranges` is an
  interval in it. A later call on the same axes becomes another lane of the layer already there, so
  a multi-lane schedule is one chart rather than several one-lane ones.

A lane is named by the single explicit tick inside it — `set_yticks` installs a `FixedLocator`,
  matplotlib's own choice is an `AutoLocator` — and by its position otherwise, so an unlabelled
  chart is never named after its own axis.

- **core**: Read Axes.contour as the scalar field it draws
  ([#540](https://github.com/xability/py-maidr/pull/540),
  [`f076d98`](https://github.com/xability/py-maidr/commit/f076d98cde161a397431ee868315646d5d2ee0ab))

Closes #539 — the last of the three readings #524 recorded.

`ax.contour` and a bivariate `sns.kdeplot` were silent, and `sns.jointplot(kind="kde")` read its two
  marginals and nothing for the joint panel. `QuadContourSet.levels` is the data and `get_paths()`
  gives one path per level, so both halves invert exactly — the value is a number here rather than a
  colour.

A level is not one curve: a field with two peaks crosses it twice and matplotlib draws both islands
  in one compound path, which read as one series would announce a straight line across the saddle. A
  filled contour is a different chart — `contourf` draws the bands between levels — and is declined,
  as is a filled bivariate kdeplot.

`kdeplot` sets the internal context around its own call, so the patched `Axes.contour` declines and
  the seaborn patch makes the registration itself, for the sets that call added.

`test_bivariate_kdeplot_is_not_registered_yet` was the pin written to fail the day a contour trace
  arrived. It has, and is replaced by the two cases it stood in for.

- **core**: Read Axes.stairs as the pre-binned histogram it draws
  ([#536](https://github.com/xability/py-maidr/pull/536),
  [`4e4537e`](https://github.com/xability/py-maidr/commit/4e4537e1ba2667676bf6a6330be96a45af6296f9))

Closes #535.

`ax.step` read as `step` and `ax.hist` as `hist`, but `ax.stairs` — the spelling matplotlib's own
  documentation reaches for once `np.histogram` has done the binning — raised
  `UnsupportedPlotError`. `StepPatch.get_data()` returns the counts and the bin edges unrounded, so
  `StairsPlot` reads the same layer from a different place; the point builder both use is now
  shared, which makes the two spellings emit the same payload rather than two that resemble each
  other.

A staircase is one `<path>` for every bin where `ax.hist` is one per bar, so the layer emits no
  selectors: a selector matching that path would outline the whole chart identically at every bin. A
  bin whose count is NaN keeps its place and reports null; a bin whose edge is infinite has no
  position and is dropped. Both keep `JSON.parse` able to read the schema.

- **core**: Read Axes.stem as the lollipop chart it draws
  ([#579](https://github.com/xability/py-maidr/pull/579),
  [`47af1ff`](https://github.com/xability/py-maidr/commit/47af1ff09968eee91be55e866884f798a94c62ca))

Co-authored-by: Claude <noreply@anthropic.com>

- **core**: Read the histogram seaborn draws as an outline
  ([#543](https://github.com/xability/py-maidr/pull/543),
  [`8167113`](https://github.com/xability/py-maidr/commit/81671137fe27d5bd23baa4ec8acf1007cc5ef915))

Co-authored-by: Claude <noreply@anthropic.com>

- **core**: Say when a figure was drawn into while it was being rendered
  ([#541](https://github.com/xability/py-maidr/pull/541),
  [`d2a7047`](https://github.com/xability/py-maidr/commit/d2a7047b95402bb329597c88b0adb94e9a11f479))

A render reads the schema from the artists and writes the SVG from them afterwards, so anything that
  draws into the figure between those two points lands in one and not the other: a chart that shows
  something it never announces, or announces something it does not show. The per-figure lock stops
  another render from doing that; it cannot stop the application itself, on a figure it still holds.
  Measured through the Shiny renderer, one session's render function drawing into a shared figure
  while another session rendered it: the change reached the SVG and not the payload, 3 of 3 runs,
  with nothing raised.

Reported rather than repaired. Re-reading the schema would race the same way, and only the caller
  knows whether the figure was supposed to be still, so the warning names both remedies instead of
  guessing one.

Two things to know about it:

* It sees artists appearing, disappearing and being relabelled -- not data changed in place. A
  `set_height` or `set_ydata` mid-render moves no count and no label and passes unnoticed, because
  catching it would mean hashing the data on every render. Its silence is therefore not a guarantee
  that a render was clean. * Importing maidr now registers a permanent `always` filter for the new
  `MaidrRenderRaceWarning` category. Python's default rule is once per source line, which in a
  long-running server would report the first collision and silently drop every later one. Downstream
  projects that assert on `warnings.filters`, or run `-W error` without an exemption, will want to
  know. `warnings.filterwarnings("ignore", category=maidr.MaidrRenderRaceWarning)` silences it
  alone.

Refs #530.

- **eventplot**: Give a raster the axis bounds its braille is built from
  ([#607](https://github.com/xability/py-maidr/pull/607),
  [`9d5b675`](https://github.com/xability/py-maidr/commit/9d5b675195ec92ba54f1bdb0936e38d1934da19f))

A point layer renders braille only in grid mode, and grid mode is built from
  `axes.{x,y}.{min,max,tickStep}`. An event plot emitted labels alone, so maidr's `ScatterTrace`
  returned `{empty: true}` and a raster was the second chart -- after a rug, fixed in #605 -- with
  no braille surface reachable by any keystroke.

Each row gets the cell it was drawn in, `one_row_around(get_lineoffset())` rather than one centred
  on zero: handed the zero-centred cell, the second row's points all fall outside the surface and it
  reads back as empty.

One grid per row rather than one for the chart, settled by architecture: `ScatterTrace` holds
  `gridCells` as instance state and never sees a sibling layer's points, so a whole-chart surface is
  not something a producer can ask for.

`RugPlot._observation_bounds` moves to `maidr/util/grid_axes.bounds_along` beside `tick_step`, with
  `one_row_around` for the single cell across the entries. `ScatterPlot` keeps its own two-axis
  rule, deliberately.

Closes #606

- **gantt**: Read hlines and vlines as the schedule of intervals they draw
  ([#570](https://github.com/xability/py-maidr/pull/570),
  [`8e951bb`](https://github.com/xability/py-maidr/commit/8e951bbaf363e3a5180436fbea3cc5f6bf911b6b))

`ax.hlines` and `ax.vlines` draw one segment per row of the data and hand back a single
  `LineCollection` carrying every end exactly. That is a gantt -- an interval per lane -- and it
  registered nothing, so a figure made of them fell back to a picture whose numbers were in the call
  (#568).

A new `SpanPlot` reads that collection into the payload `broken_barh` already produces, dispatched
  by the artist the patch hands over rather than by a new plot type. `_lane_name` is generalised to
  take the axis the lanes were laid out on, so a `vlines` names its lanes from the x ticks and an
  `hlines` from the y ticks.

What is not a schedule is decided in the patch, before anything registers, by the rule
  xability/maidr#1100 and #1122 settled for the Observable and Vega-Lite `rule` marks: if every
  segment shares an end, that end is the frame or the baseline rather than anything measured.
  Lollipop stems, reference lines and single segments are handed back untouched. Deciding it before
  registration matters because a layer that refuses at extraction takes the whole figure with it,
  which is the defect #564 was about.

Two defects found while reviewing this and fixed here:

- `gantt._lane_of` matched on `isinstance(plot, GanttPlot)`, and `SpanPlot` subclasses it. A
  `broken_barh` following an `hlines` on the same axes had its lane appended where extraction never
  looks -- drawn, accepted without error, announced nowhere. Now matched on the exact type, so both
  orders read every interval and two `broken_barh` calls still merge.

- The shared-end test compared floats exactly, so a lollipop whose baseline was computed rather than
  typed could stop sharing it by 5e-17 and be read as a schedule. Now compared against the extent
  the chart covers on that axis.

Closes #568

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>

Claude-Session: https://claude.ai/code/session_015TFhhzxcMetSHV7z9NCrJ8

- **heatmap**: Read ax.pcolorfast as the grid its three siblings draw
  ([#626](https://github.com/xability/py-maidr/pull/626),
  [`860678b`](https://github.com/xability/py-maidr/commit/860678b4697a9288fae7fc38eb82dcd5aad17a06))

Co-authored-by: Claude <noreply@anthropic.com>

- **hist**: Read a step-outlined histogram instead of falling back
  ([#557](https://github.com/xability/py-maidr/pull/557),
  [`4526f38`](https://github.com/xability/py-maidr/commit/4526f385bb5ef15b795c49b5f48265b8d5ff6122))

Co-authored-by: Claude <noreply@anthropic.com>

- **hist**: Read every element displot draws, not only bars
  ([#592](https://github.com/xability/py-maidr/pull/592),
  [`fafa76e`](https://github.com/xability/py-maidr/commit/fafa76ed94e2b4598e44b85f2b0e35f0c409b928))

`sns.displot(element="step"|"poly")` registered no layer at all and the figure fell back to a static
  image, filled or not, while the same chart through `histplot` read fine. Those elements draw a
  `PolyCollection` or a bare `Line2D` and leave no `BarContainer`, so the bar registrar passed over
  them; both readings already existed and only the branch reaching them was missing. It is now
  shared between the two interfaces rather than copied.

Found while measuring it: a faceted panel's group names all resolved from the last panel, because
  the deferred resolver closed over the loop variables. Measured on a grid whose panels hold
  different groups, every layer came back unnamed.

Verified across all twelve element x fill x orientation combinations that the schema `displot` emits
  is now identical to `histplot`'s.

Closes #590 and #591.

- **hist**: Read the seaborn histogram outlines drawn without fill
  ([#585](https://github.com/xability/py-maidr/pull/585),
  [`df83461`](https://github.com/xability/py-maidr/commit/df834611eb998b8d224449c679c7fe6e0d123c26))

`sns.histplot(..., fill=False)` draws its distribution as a `Line2D` rather than as patches, and
  nothing looked at lines: four of ten element x fill x hue combinations registered no layer at all.
  New `OutlinedHistPlot` recovers the bins from the outline's vertices -- edges for a stepped one,
  centres for a poly -- and reuses `HistPlot`'s payload so the schema matches the filled twin
  exactly. An uneven poly declines rather than inventing edges, as does `element="poly", fill=False,
  kde=True`, which no signal separates from the density it is drawn beside.

Two review rounds each found a real defect, both fixed here: the hue group name was computed and
  then dropped on the way into the layer, and a horizontal poly outline whose counts climbed was
  read transposed -- bin edges built out of the counts. The orientation is now handed over by the
  patch and used only where the drawing genuinely reads either way.

Closes #583.

- **plotly**: Read a 2-D histogram as the heatmap it draws
  ([#645](https://github.com/xability/py-maidr/pull/645),
  [`9b4f660`](https://github.com/xability/py-maidr/commit/9b4f6602c3df476cd4b4fecfd1458c7f95643577))

`go.Histogram2d` produced a figure with no layers (#627).

A rectangular grid of cells each carrying a number is a heatmap, and plotly agrees: measured in
  Chromium, a `histogram2d` draws a single `<image>` into its subplot's `heatmaplayer`, the same
  element a `go.Heatmap` draws. So the layer extends `PlotlyHeatmapPlot` and shares its selector,
  its ordering and its axis titles.

What differs is where the grid comes from. A `histogram2d` carries raw samples and lets plotly bin
  them in the browser, on the rule py-maidr already matches for a 1-D histogram with exactly one
  change: a 2-D axis divides by `n ** 0.25` rather than `n ** 0.4`. The same thirty values are
  binned five wide by `go.Histogram` and ten wide by `go.Histogram2d`.

A cell is named by the range it covers rather than its index or centre, which is how r-maidr settled
  it for `geom_bin_2d`.

Every cell and label checked against `gd.calcdata` across 18 figures, and an 18-mutation sweep that
  found a real defect on the way: a sample sitting exactly on a bin's closing edge is dropped, not
  folded into the bin below.

Closes part of #627.

- **plotly**: Read a choropleth map ([#641](https://github.com/xability/py-maidr/pull/641),
  [`38802c2`](https://github.com/xability/py-maidr/commit/38802c2df63778c22ae40bfddd975677760f6fa3))

`go.Choropleth` shades named regions by a value. It fell through to `PlotlyPlotFactory`, which
  returned `None`, so the figure had no layers at all.

Each region becomes a point — its name and the number it is shaded by, in declared order — with the
  colour bar's title naming the value where the author wrote one. A region with no `z` is dropped,
  because plotly leaves it unshaded.

The centroids are not here to be read: `ChoroplethPoint` takes an optional `lon`/`lat` pair and
  `neighbors`, and a `go.Choropleth` carries none of them. The grammar anticipates this — without
  them the map is read as a region list in declared order.

No selector, and this one is a limit rather than a decision. Plotly fetches its geometry from
  cdn.plot.ly at render time, and with no network the map never draws — measured, zero `path`
  elements while `calcdata` has its entry. A selector that has never resolved would be a guess.
  Filed as #640.

A geo subplot is placed like a polar one rather than like a pie: the rectangle is
  `layout.geo.domain`, named by the trace's `geo` field. So `_polar_domain_start` generalises to
  `_block_domain_start` and `subplot_block()` moves to `plotly_plot.py`, where both trace families
  reach it — one helper and one layout branch instead of a second near-copy.

Closes part of #627.

- **plotly**: Read a contour at the levels its author declared
  ([#643](https://github.com/xability/py-maidr/pull/643),
  [`c190dbd`](https://github.com/xability/py-maidr/commit/c190dbd431ad4f0d1a667368e6ff0fdface2c054))

`go.Contour` produced a figure with no layers (#627). The core has had `TraceType.CONTOUR` since the
  matplotlib side was read (#539).

The curves are not in the trace: plotly ships a grid and a level spacing and traces them in the
  browser, so reading the chart means running the same marching squares here, with contourpy.

Only an explicit `contours.start`/`end`/`size` is read; plotly's own rule for picking levels did not
  reduce to a formula and is left to #642. The level list was pinned by measurement: plotly steps
  while the level is below `end + size / 10`.

A layer is highlighted only when each of its drawn levels draws a single curve. Across 33 fields and
  207 levels, plotly and contourpy always found the same number of curves in a level and put them in
  the same order all but 18 times, so within a level with one curve the mapping is forced and with
  an island anywhere it would be a guess. That layer keeps its audio, braille and text instead
  (#145).

Closes part of #627.

- **plotly**: Read a contour at the levels plotly picks for itself
  ([#649](https://github.com/xability/py-maidr/pull/649),
  [`c5ab6a8`](https://github.com/xability/py-maidr/commit/c5ab6a8ab80182df4676acc7f35fa163357511ff))

A contour that leaves out `start` or `end` -- or sets `autocontour` -- has its levels chosen in the
  browser, and #643 declined those traces rather than guess, which left every default `go.Contour`
  unread.

The rule is a rough step of `(zmax - zmin) / (ncontours or 15)` rounded *strictly* up to a 1/2/5x10ⁿ
  value (#646), then the multiples of it strictly inside the field's range, and a single level at
  their midpoint when the two ends cross. A trace naming both ends but no width is no longer
  declined either -- plotly derives one for it through the same round-up.

Both the round-up and the two endpoint tests turn on binary ties, in opposite directions: the
  multiple is taken with a tolerance, because `-0.3 / 0.05` is -5.999999999999999 and rounding that
  at face value starts the list a level late; whether it then lands *on* the bound is tested
  exactly, because `0.009 / 0.0001` rounds up to a top level 1.7e-18 from the ceiling that plotly
  keeps and a tolerance would drop. Measured against the browser's drawn levels on 49 figures, all
  agreeing level for level, with each of the four roundings the difference on at least one.

Level groups that hold no curve still count: plotly gives one a `g.contourlevel` of its own, so the
  selectors index the whole list.

Also, from review: a declared spec that runs away past the level cap declines outright rather than
  falling through to levels of maidr's own choosing, and the field's range is read through the mask
  rather than around it.

Closes #642

- **plotly**: Read a funnel trace ([#630](https://github.com/xability/py-maidr/pull/630),
  [`d669330`](https://github.com/xability/py-maidr/commit/d6693302df06a8e8999a7f17f6dc8cd065090670))

Co-authored-by: Claude <noreply@anthropic.com>

- **plotly**: Read a funnelarea trace ([#631](https://github.com/xability/py-maidr/pull/631),
  [`c614bd1`](https://github.com/xability/py-maidr/commit/c614bd1b34c16a8e45cafa7a43ccbdf107f38394))

Co-authored-by: Claude <noreply@anthropic.com>

- **plotly**: Read a histogram2dcontour as the contour of its binned counts
  ([#653](https://github.com/xability/py-maidr/pull/653),
  [`0cc4e0e`](https://github.com/xability/py-maidr/commit/0cc4e0eeb66f783159b2da73561d11d186d82d37))

The fifteenth and last of #627's declined trace types, and the only one that is two readings at
  once: it bins samples the way a `histogram2d` does and then draws the curves along which those
  counts are constant, the way a `contour` does. `PlotlyHistogram2dContourPlot` extends
  `PlotlyContourPlot` and overrides exactly two things -- which grid the curves run through, and
  which values the levels come from.

Three things differ from either half alone, all measured:

- The grid is one bin wider at each automatic edge, so the curves have somewhere to close. Which
  edges move is per-side: the low edge moves unless a `size` was named -- not unless a `start` was
  -- and the high edge moves unless an `end` was. - The curves run through the bin centres, not the
  edges. - A cell nothing landed in traces as zero, because plotly hands the grid to a tracer where
  a `null` compares as below every level. The levels, though, come from the values that are there.

Read end to end against the browser on 13 figures; 11 agree curve for curve, and the two that do not
  are levels whose curves reach the grid's own edge, where plotly's paths are region outlines rather
  than curves -- levels the layer declines its selectors on anyway.

Two changes reach the plain contour too: a curve that spans nothing is no longer emitted as a series
  of one point repeated, and the shared reading of a colour bar title is in one place rather than
  three.

Closes #627

- **plotly**: Read a parallel coordinates trace
  ([#637](https://github.com/xability/py-maidr/pull/637),
  [`5f0ae40`](https://github.com/xability/py-maidr/commit/5f0ae403388b888e85d95923f7bfc5cbb22afd47))

`go.Parcoords` draws one polyline per observation across a row of vertical axes, each a different
  variable. It fell through `_extract_plots` to `PlotlyPlotFactory`, which returned `None`, so the
  figure had no layers at all.

The payload is a line's, because `ParallelTrace` extends `LineTrace`: a list of series, each a list
  of `{x: axis name, y: value}`. plotly declares the chart by column and the core reads it by row,
  so the transpose happens here. The axis name is per point rather than per layer — that is the
  whole difference from a line chart, and what lets the trace pitch each value against its own
  column's extent.

Three answers were measured in Chromium: a `visible: False` dimension draws no axis and is excluded;
  ragged columns are truncated to the shortest, because plotly reports `_length` as the minimum for
  every one of them; and the observations render to WebGL, so there is nothing to point at and the
  layer ships without a highlight, keeping its audio, braille and text.

`parcoords` joins `_PLACED_BY_DOMAIN` — placed by its own `domain` rectangle like a pie, and now
  that maidr renders it, its rectangle belongs in the figure's column universe. `go.Parcats` takes
  over its row in `TestPlotlyUnrenderedDomainTraces`.

An empty `go.Parcoords` still emits a ghost layer, which an empty pie, sankey and scatterpolar do
  too — filed as #636 and fixed for all of them in one place.

Closes part of #627.

- **plotly**: Read a parallel sets trace ([#639](https://github.com/xability/py-maidr/pull/639),
  [`893dd52`](https://github.com/xability/py-maidr/commit/893dd5227a5c492338e87a37903c1bdf67cc0006))

`go.Parcats` puts categorical dimensions side by side and draws a ribbon between adjacent ones for
  every combination that occurs. It fell through to `PlotlyPlotFactory`, which returned `None`, so
  the figure had no layers at all.

The core reads it as `ALLUVIAL`, sharing `FlowTrace` with `SANKEY` and `CHORD`: one weighted flow
  between two named nodes. So a ribbon spanning several dimensions becomes one flow per adjacent
  pair — the grammar's unit, and also the reading, since what the chart shows is how a population is
  re-divided at each step.

Measured: plotly merges duplicate combinations (five rows drew four ribbons, the shared one at the
  summed count), and it lays its ribbons out in its own order (`key` = 0, 2, 1, 3 in document
  order), which is not computable offline — so a positional selector would resolve to real elements
  and the wrong ones. The layer ships without a highlight and keeps its audio, braille and text.

A node is named for its dimension, because the grammar derives its nodes from the flows and a level
  name repeated across dimensions would otherwise collapse two columns into one node with a flow to
  itself.

`go.Table` takes back the "undrawn domain trace" test row, which `parcoords` and then `parcats` had
  each held until they started rendering.

Closes part of #627.

- **plotly**: Read a sankey trace ([#634](https://github.com/xability/py-maidr/pull/634),
  [`9efd251`](https://github.com/xability/py-maidr/commit/9efd25174cacf676c8c82514ee6c10179f5251db))

Co-authored-by: Claude <noreply@anthropic.com>

- **plotly**: Read a waterfall trace ([#629](https://github.com/xability/py-maidr/pull/629),
  [`98e4ee8`](https://github.com/xability/py-maidr/commit/98e4ee80d5f16de0eb506b4207dd1bb43c00b44c))

Co-authored-by: Claude <noreply@anthropic.com>

- **plotly**: Read an indicator that draws a gauge
  ([#632](https://github.com/xability/py-maidr/pull/632),
  [`a5920d0`](https://github.com/xability/py-maidr/commit/a5920d0706c2aac01a9660ea438516716ae138c1))

Co-authored-by: Claude <noreply@anthropic.com>

- **plotly**: Read the three hierarchy paintings
  ([#633](https://github.com/xability/py-maidr/pull/633),
  [`8be278b`](https://github.com/xability/py-maidr/commit/8be278b70e08215385302a12e1bf00bd84c83581))

Co-authored-by: Claude <noreply@anthropic.com>

- **plotly**: Read the two polar traces ([#635](https://github.com/xability/py-maidr/pull/635),
  [`46b215e`](https://github.com/xability/py-maidr/commit/46b215ecb3e5c9712f988486ad32fe18eb5cd78e))

Reads `go.Scatterpolar` as a `radar` and `go.Barpolar` as a `polar_area` — both spokes around a
  circle, which the core builds on one `RadarTrace`.

`theta` is the angle and `r` the radius, wrapped as one series for the list-of-series shape a radar
  layer takes. A spoke with no radius is dropped, whether it arrives as `None` or as the `nan` a
  numpy array decodes to: `RadarTrace` places its spokes by count, so a kept gap rotates every later
  one.

Each trace is read against its own polar subplot — its grid cell from `layout.polar*.domain`, its
  selector scoped to `> g.polar2`, its position counted within that subplot's own `.scatterlayer`,
  and its axis titles from its own layout block. A polar trace names no axis pair, so all four were
  being taken from a group holding every polar trace in the figure.

A barpolar ships without a highlight: it draws one bar per spoke and no per-series path, and a radar
  layer resolves one selector per series.

Closes part of #627.

- **rug**: Give a rug the axis bounds its braille is built from
  ([#605](https://github.com/xability/py-maidr/pull/605),
  [`ff904ff`](https://github.com/xability/py-maidr/commit/ff904ff3aca808427fb8d31ef3f251ce76f68bc1))

A point layer renders braille only in grid mode, and grid mode is built from
  `axes.{x,y}.{min,max,tickStep}`. A rug emitted labels alone, so measured against maidr's
  `ScatterTrace` its braille state came back empty -- leaving a rug the one chart with no braille
  surface reachable by any keystroke.

With the bounds, four observations at 1, 2, 3 and 9 over a 0-10 axis give `values [[2, 1, 0, 1]]`:
  the observation count per cell. That is the clustering a rug is drawn to show, and the one thing
  its audio cannot carry -- every tick sits at the same place on the axis pitch is mapped from.

The observation axis takes the chart's own bounds, declined on the same grounds `ScatterPlot`
  declines them; the axis across the ticks is supplied whole as 0 to 1 in one step, a rug being one
  row deep by construction.

The tick-step reading both need moves to `maidr/util/grid_axes.tick_step` rather than being borrowed
  across classes. Each caller keeps its own validity rule, because a scatter declines both axes
  together where a rug asks only of the axis its observations lie along.

Additive only: walking the ticks with and without the bounds gives identical audio, panning and text
  at every step.

Refs xability/maidr#1132.

- **rug**: Read a seaborn rug plot as the observations it marks
  ([#571](https://github.com/xability/py-maidr/pull/571),
  [`c07b98c`](https://github.com/xability/py-maidr/commit/c07b98cb28ba67e827ced3a809cf78932e09da32))

`sns.rugplot` draws one short tick per observation against the frame and handed back a plain
  `LineCollection` that no patch claimed. So a figure whose only layer was a rug fell back to a
  picture, and a rug drawn over a density curve left the raw observations -- the one thing a
  smoothed curve does not state -- unread (#250).

Read as a scatter, for the reason `EventPlot` gives about an event plot's ticks: `height` is one
  number for the whole call, so a tick's length is decoration and only its position is data. A rug's
  ticks are held constant on the axis carrying the observations and stretched across the other, so
  the constant coordinate is the measurement.

Three calls worth stating:

- The strip the ticks sit in is renamed rather than left carrying the chart's own label. A rug over
  a `kdeplot` has a real "Density" label there and every emitted point sits at 0, so keeping it
  would announce each observation as "Density 0" -- a number the chart does not show. This differs
  from `EventPlot`'s "Row", which only fills a blank, because a row offset is a real place and a
  rug's strip is not.

- One layer per collection, not per call: `rugplot(x=..., y=...)` marks two margins, and merging
  them would announce one series whose coordinates come off two different axes.

- A rug beside another layer is registered rather than declined as a duplicate -- the opposite of
  xability/maidr#1124's call for Vega-Lite text overlays, because those labels sit *on* the marks
  they duplicate whereas a rug occupies its own strip. It carries `name` so a reader can tell it
  from its neighbour.

Two limits are measured, documented and pinned rather than left to be found: a rug drawn onto an
  axis another plot already labelled takes that label, since the artist carries no record of its own
  column; and `rugplot(height=0)` draws ticks of no length and is declined, because announcing them
  would describe a chart that is not on the screen.

`tests/core/test_unsupported_fallback.py` used a rug as its example of an unsupported chart, which
  it no longer is; it now uses `ax.barbs`.

Closes #250

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>

Claude-Session: https://claude.ai/code/session_015TFhhzxcMetSHV7z9NCrJ8

- **rug**: Read the hue a rug plot was grouped by
  ([#598](https://github.com/xability/py-maidr/pull/598),
  [`aff664d`](https://github.com/xability/py-maidr/commit/aff664d5dda22ac2c8c602c35ec47943e7f78ede))

A hue-grouped rugplot emitted exactly the schema of the same call without hue: one layer named after
  the variable, no z. Seaborn draws the whole rug as one LineCollection with a colour per tick and
  builds the legend that names those colours inside the call, so the split is made in the patch --
  one artist becoming one layer per level, each keeping to its own ticks and addressing them per
  segment.

Declined for a numeric hue, which is a colour scale rather than a grouping, read off the plotter's
  own map_type; for a chart drawn legend=False; and for any tick no swatch names.

The z label is read off whichever legend named the groups, including the figure-level fallback a
  panel with no legend of its own uses.

Closes #597.

- **scatter**: Read the hue a strip or swarm plot was grouped by
  ([#588](https://github.com/xability/py-maidr/pull/588),
  [`1bc1fc4`](https://github.com/xability/py-maidr/commit/1bc1fc4a966ba0975180cb7a2e6d74eb68b9bc47))

`sns.stripplot(..., hue=...)` emitted exactly the schema of the same call without a hue: three
  layers, one per category, unnamed, with the grouping absent rather than merely unnamed.
  `swarmplot` and `catplot(kind="strip"/ "swarm")` were the same.

Registration happened at the inner `Axes.scatter` calls, and `plot_strips` assigns the per-point hue
  colours and builds the legend only after those return -- measured, one uniform colour and no
  legend at every call, so the split declined on both counts. The reading moves to the plotter
  method, which `catplot` drives too, and takes the grouping from the plotter's own hue mapping
  rather than from a legend a faceted panel does not have.

A grouped panel now gets one layer per hue level, spanning the categories, named by the level with
  the hue variable on `z` -- the shape a hue-grouped `scatterplot` already emits. A chart with no
  hue is untouched.

Closes #586.

- **seaborn**: Name a strip or swarm layer by the category it holds
  ([#663](https://github.com/xability/py-maidr/pull/663),
  [`947558c`](https://github.com/xability/py-maidr/commit/947558c398f8d064d5630ee553fdf14d5c6becae))

Closes #662.

A category-split strip or swarm plot emitted one layer per category, all unnamed, while the same
  call with a `hue=` that changes nothing about the split named all three. A reader switching layers
  on the first heard "point plot" three times, on a chart whose layers are the categories.

The split itself is #426's and is not in question. What was missing is the name on each, the
  position `MaidrLayer.name` was added for -- and the name was already in hand, since every point of
  layer k carries the category on its `xLabel`. It is read off the layer's own points against the
  same tick lookup `ScatterPlot` uses for that field. Both axes are asked, because `y="g"` puts the
  names on y.

A hue that reads still takes the other branch and is still named by its level; a numeric axis still
  names nothing.

Six existing tests changed: each asserted `names(figure) == [None, None, None]` as evidence that a
  *hue* had been declined, which the names no longer show either way, so they now assert it on the
  `z` axis. Their subject is unchanged.

Two things the tests caught that were wrong first time: a numerically grouped strip IS categorised
  by seaborn and named by the tick it draws (the points already carry the same string), and a
  faceted panel's empty collection is deliberately left unnamed.

4 mutations killed. Three redundancies were removed after measuring the guarantee they duplicated:
  an empty-collection guard (offsets come back shaped (0, 2)), an early numeric-axis exit, and a
  blank-label check.

- **seaborn**: Name every panel of a pairplot and a jointplot
  ([#661](https://github.com/xability/py-maidr/pull/661),
  [`60f8980`](https://github.com/xability/py-maidr/commit/60f898062d706c72eedc50e1f263314c761f53c6))

Closes #660.

A layer's title is the axes title, and it is what the core reads back when a reader arrows across a
  multi-panel figure's lobby. seaborn titles neither grid's cells -- it labels the grid's outer edge
  with axis labels instead -- so a nine-panel pairplot announced six `point` panels and three `hist`
  ones with nothing to tell them apart. A reader looking for "flipper length against bill depth" had
  to enter each panel, read a data point for its axis labels, and back out, nine times.

The name is looked up, not inferred: `PairGrid` declares its `x_vars`, `y_vars` and `diag_vars`, and
  `JointGrid` names its three axes structurally, so nothing here reads a panel's meaning off where
  it sits. An off-diagonal panel is "y vs x", in the order its own axis labels announce once a
  reader is inside it; a diagonal or a marginal is the one variable it draws. A caller's own
  `set_title` still wins.

Measured, and the reason the diagonal needs its own pass: `map_diag` draws a pairplot's univariate
  panels on twin axes, so a title recorded against the grid cell reaches nothing.

12 tests, 8 mutations killed. Four survived a first sweep and each was resolved rather than argued
  away: the jointplot test was sharpened to pin each panel by its own axis labels (a sorted bag
  could not see the two marginals swapped), and three redundancies were removed after measuring them
  -- a Series-name read that never disagreed with the axis label across five spellings, a bounds
  check on a grid that is always exactly its declared size, and a blank-title branch nothing could
  observe.

- **seaborn**: Read a seaborn.objects 100% stacked bar as one
  ([#622](https://github.com/xability/py-maidr/pull/622),
  [`2e645e7`](https://github.com/xability/py-maidr/commit/2e645e7a7448211cfe8b51ca59f50208d86b346a))

`so.Norm(func="sum", by=["x"])` before `so.Stack()` draws a 100% stacked bar — each category's
  segments sum to exactly 1 — and it read as `stacked_bar`. The segments were announced; that they
  are shares of a whole was not.

`PlotType.NORMALIZED` was plotly-only in this package, with no factory branch at all.
  `GroupedBarPlot` now serves all three grouped types; nothing is computed here, since seaborn has
  already written the shares into the bars.

The spelling cannot decide it. `Norm` takes a `func` and a `by`, and only some combinations
  normalise within the category — measured, `by=["x","color"]` names the category axis, looks right,
  and normalises each level to 1 so the stacks reach twice the whole. So the drawn bars are asked
  instead, and both halves are required: a sum-normalisation among the moves, which no plain
  `Stack()` has, and every category landing on a whole. An ordinary stack whose categories happen to
  total alike keeps reading as `stacked_bar`.

Order is not checked, and the totals are why: after `Stack()` then `Norm()` the tops are all wholes
  only when every level but the last is at zero, and seaborn draws no rectangle for a zero, so no
  grouped layer is made at all. An order check would only refuse charts that never reach the
  function — it was written, survived its mutation, and was removed.

Review follow-up in the same branch reads a `Norm` written with a callable (`numpy.sum` draws what
  `"sum"` draws) and asserts the `Dodge()`-beside-the-stack boundary: the dodge splits the position
  keys with the bars, so each column is one slot's share and none is a whole.

Closes #620, #617.

- **seaborn**: Read the marks of seaborn.objects, which registered nothing
  ([#616](https://github.com/xability/py-maidr/pull/616),
  [`4df5bd5`](https://github.com/xability/py-maidr/commit/4df5bd5e1b133d4e9c7befa421dda31bf5c168b2))

seaborn.objects is seaborn's declarative interface and py-maidr read none of it -- not one plot type
  missing, the whole front door. Measured before, each row one .add():

so.Plot(frame, x=, y=).add(so.Dot()) NOTHING REGISTERED .add(so.Line()) NOTHING REGISTERED
  .add(so.Bar()) NOTHING REGISTERED sns.scatterplot(...) ['point'] sns.lineplot(...) ['line']
  sns.barplot(...) ['bar']

maidr/patch/ wraps the user-facing drawing calls -- Axes.scatter, Axes.plot, Axes.bar. A Mark calls
  none of them; it draws through the artist API, so nothing was there to fire.

Plotter._plot_layer runs once per .add() and draws that layer across every panel, which makes it the
  one place where "which artists belong to which layer" is still answerable. Taking each axes'
  artists before and after answers it without predicting how many a mark makes. A panel a layer
  never drew on registers nothing, so a col/row grid's empty combinations do not become layers a
  reader can walk into and find nothing in (#421).

Dot, Dots, Line, Path and Bar need no new extraction: ScatterPlot already takes a collection,
  LinePlot a list of lines, and BarPlot a container.

Marks are matched by class name, not by ancestry, because seaborn's hierarchy does not track what a
  mark draws -- Dash and Range are Paths subclasses that draw a LineCollection. Every unnamed mark
  is drawn and left entirely alone, so it registers exactly what it registered before: nothing.

The wrap is guarded rather than assumed. Plotter._plot_layer is a private method of a private module
  with no version floor to state, and letting a rename take `import maidr` down would break every
  classic seaborn chart over a mark nobody in that process drew.

Closes #615

Co-Authored-By: Claude <noreply@anthropic.com>

- **seaborn**: Type a colour-split seaborn.objects bar from its position transform
  ([#621](https://github.com/xability/py-maidr/pull/621),
  [`489c9f0`](https://github.com/xability/py-maidr/commit/489c9f052ee605665af348445052db217b6af5ce))

A colour-split `so.Bar` with `so.Dodge()` or `so.Stack()` read as plain `bar` layers, where the same
  chart written `seaborn.barplot(hue=)` answers `dodged_bar` — so a reader lost the grouping
  structure, the `z` axis naming it, and cross-group navigation between levels at one category.

`so` states the transform outright as a `Move` on the layer, which is a cleaner signal than anything
  the classic path gets: `seaborn.barplot(hue=)` is read as dodged by counting containers, and a
  stacked bar has to be declared through `maidr.stacked()`. `Dodge()` now gives `dodged_bar` and
  `Stack()` `stacked_bar`, emitting the same list-of-groups payload with `z` per point that the
  classic path already does.

Plain `color=` keeps the per-group split: it carries no transform and overplots the levels at one
  position, which is neither a dodge nor a stack.

Two supporting changes: `GroupedBarPlot` can be handed its containers instead of sweeping the axes
  (the sweep cannot serve a layer whose levels arrive in one container), and its two legend reads go
  through `legend_of`, since `so.Plot` hangs its legend on the figure.

`so.Norm()` is deliberately not read as a 100% stack — measured, it draws negative heights after
  `Stack()` and does not sum to 1 before it. The spelling that is one needs an emitter this side
  lacks; filed as #620.

Closes #617.

### Performance Improvements

- **shiny**: Render off the event loop, one render per figure at a time
  ([#504](https://github.com/xability/py-maidr/pull/504),
  [`1e46499`](https://github.com/xability/py-maidr/commit/1e46499df059df7a94e33649ba4ed4481e283b19))

`maidr.render` never awaits, so on Shiny's event loop it held it for its whole duration -- every
  other session on that worker waited, once per reactive flush (#454). Measured through the renderer
  itself, eight renders of a 50-bar chart, longest gap in a 1 ms ticker:

idle control 1.3 ms on the loop 484.9 ms wall 484 ms off the loop 13.4 ms wall 565 ms

It is not free: the same eight renders take ~17% longer in wall-clock, because each pays a thread
  handoff. A lone user rendering sequentially is slightly slower so that concurrent users stop
  blocking each other.

Moving it works because the expensive part releases the GIL -- `savefig` is 87-88% of a render at
  every chart size. Had it held the GIL throughout, this would have relocated the work without
  unblocking anything, which is why that was checked first.

Two locks' worth of shared state, both measured by watching the attribute from another thread while
  renders ran.

`savefig` mutates the figure it is writing: `fig.dpi` goes 100 -> 72 -> 100, and `fig.canvas` is
  swapped to the format's canvas and back. Two concurrent writes to one figure race on both, and the
  loser renders its whole chart at the other's dpi -- a 640x480 chart came out 460.8x345.6, as a
  valid SVG, raising nothing, on 1 of 6 attempts. Hence a per-figure lock, weak-keyed so it adds no
  retention while #456/#498 are open. Per figure rather than process-wide because distinct figures
  are safe in parallel, which is the parallelism this is for.

That last claim is also what made the second problem reachable, and it is the one this PR nearly
  shipped. `HighlightContextManager` held each render's element-to-selector wiring in plain class
  attributes, read by class-wide patches on the artist `draw` methods and on `XMLWriter.start`. Safe
  only while renders were serialised on one thread. With distinct figures now genuinely concurrent,
  they overwrote each other's wiring:

serial [61, 61, 61, 61] concurrent [ 7, 1, 1, 1]

Valid SVGs with the interactive layer almost entirely gone, on the common path, only under
  concurrent traffic. Fixed with `contextvars`, matching `ContextManager` in the same file: a
  render's wiring is genuinely per-render, and `to_thread` runs the call in a copy of the context,
  so distinct figures stay parallel where a wider lock would have given that back.
  `set_maidr_elements` installs a fresh mapping per render because `copy_context()` copies the
  variable-to-value mapping, not the values.

Every guarantee falsified: putting the render back on the loop, making the lock unstable or
  per-call, making the lock map strong, removing the debug log, and restoring the original class
  attributes each fail their own test.

Refs #454, #505

### Refactoring

- **hue**: Give the shared hue-group tail one home
  ([#604](https://github.com/xability/py-maidr/pull/604),
  [`e1c16e1`](https://github.com/xability/py-maidr/commit/e1c16e1c9b463a868cb9a20cee3b3143a1ff0bff))

Scatter and rug reached the same three decisions -- decline on a thing no name claims, decline on
  fewer than two groups, come out in the legend's order -- by two different routes.
  `grouped_by_name` takes that tail; what a chart is read *from* stays per artist, because that is
  genuinely per artist.

Strip and swarm keep their own: their members are a list per collection rather than flat positions,
  and a panel holding one level is deliberately kept rather than declined.

The mutation sweep found what it is for. Two of the three rules were killed only by the new direct
  tests, so moving them had left their callers no longer testing them. Both now have a chart behind
  them where they are reachable -- legend ordering on the scatter, fewer-than-two on the rug; the
  scatter cannot reach the latter, which is recorded rather than left as a hole.

No behaviour change intended, and none measured.

Closes #599.

- **util**: Give CDN version resolution its own module
  ([#503](https://github.com/xability/py-maidr/pull/503),
  [`a48ffc6`](https://github.com/xability/py-maidr/commit/a48ffc65c45d3f8ac5c2e640a46a364bbd5178f7))

The last half of #293's suggested shape. `maidr/util/cdn.py` takes the resolver -- the endpoints,
  the timeout budget, the semver pin handling, the `latest` lookup and its caching, and the URL
  builders. `dependencies.py` goes 1781 -> 835 lines and is finally what the issue asked for:
  reaching the copy bundled inside the wheel.

The direction is one-way, measured before moving anything rather than assumed: no asset-side
  function references a CDN name, so `cdn` imports `dependencies` and nothing imports back.

Three names stayed behind, for the reason #293 records after the first cut. `_version_key` and
  `_UNKNOWN_VERSION` are used by `bundle_freshness`, so they are shared version primitives rather
  than CDN ones -- moving them would have made freshness depend on the resolver to compare two local
  strings. `_warn_placeholder_css` stayed for the same reason, found later by ruff:
  `bundled_css_path` calls it too, and it is about the placeholder asset.

The back-compat shim is weaker here than for the earlier cuts. It forwards attribute reads, so
  `dependencies.get_cdn_version` still resolves to the same object; it cannot forward a write,
  because `setattr` goes straight to the module dict. So `monkeypatch.setattr(dependencies,
  "urlopen", ...)` would set an attribute nothing in `cdn` reads -- a patch that silently does
  nothing. Since 18 tests patch that name, leaving them to the shim would have produced a green
  suite testing nothing. Only the public names are forwarded, the resolver's state is deliberately
  absent from `_MOVED_TO_CDN`, and 266 test references were repointed.
  `test_the_shim_forwards_reads_but_cannot_forward_a_patch` asserts the asymmetry so a future change
  that starts forwarding writes has to edit it.

Two tests needed real updates, both predicted.
  `test_no_render_path_references_the_unresolved_constants` is the exclusion #293's third note said
  would need repointing once another module owned the constants; it now allows the owner and the
  shim's forwarding list, which is not a render path. And `maidr_css_cdn_url`'s deprecation named
  `cdn_url(MAIDR_MATH_CSS_FILENAME) from maidr.util.dependencies`, which after the move sent readers
  to a module where neither name lives -- `test_deprecation_names_only_importable_symbols` caught
  it.

Verified rather than assumed: identity is preserved through the shim for all 15 public moved names,
  which matters because `except` and `isinstance` compare class objects; nothing is missing from
  `maidr.__all__`; the laziness guard flags all three import spellings of `cdn`; and the resolver
  still pins, falls back to the bundled version without a pin, refuses a traversal or
  shell-metacharacter or non-ASCII-digit pin, and reports offline status without a request.

Closes #293

- **util**: Give the shared warning policy its own module
  ([#496](https://github.com/xability/py-maidr/pull/496),
  [`2e43684`](https://github.com/xability/py-maidr/commit/2e4368400d1fb78b2adb3998bb2bddf8894d2d2c))

Prerequisite for the next cut of #293, and a fix for a wart four reviews of #494 flagged in a row:
  `bundle_capability` imported the private `_bundle_warning_enabled` from `dependencies` across a
  module boundary, because the warning policy belongs to neither half.

`maidr/util/warn.py` is deliberately a leaf -- it imports nothing from the package -- so both halves
  import it eagerly, with none of the lazy shim machinery `bundle_capability` needs. `_warn_once`
  and `_bundle_warning_enabled` lose their underscores now that they cross a module boundary on
  purpose.

One behaviour change rather than pure motion: `warn_once` logs through `maidr.util.warn` instead of
  `maidr.util.dependencies`. Filtering on the `maidr` prefix is unaffected; only a filter naming the
  old module exactly would notice.

Refs #293

- **util**: Move bundle staleness reporting into its own module
  ([#497](https://github.com/xability/py-maidr/pull/497),
  [`abf50bc`](https://github.com/xability/py-maidr/commit/abf50bc21bc7c52c5fc962313688e8c7d72b958f))

`maidr/util/bundle_freshness.py` takes staleness reporting -- `bundle_status`, `BundleStatus`,
  `warn_if_bundle_is_stale`, `warn_bundle_unreadable`, `resolver_outcome`, `STALE_MINOR_GAP`,
  `MaidrBundleStaleWarning`. `dependencies.py` goes 2033 -> 1781 lines.

This advances #293 without closing it: the issue's suggested shape asks for a `cdn.py` as well, and
  that half is untouched, so `dependencies.py` still holds asset access alongside the whole CDN
  resolver.

Three things this cut needed that the capability cut did not:

- `_RELEASE_RE` stays behind. It sits inside the moved section, but `_version_key` uses it and it is
  a version-parsing primitive rather than a freshness one. - There is one edge back into
  `dependencies`: `inline_bundle_tags` calls `warn_bundle_unreadable`. Imported inside the function
  so the module-scope dependency stays one-way. - Reads that tests patch go through the module
  object -- `_deps.maidr_js_version()` rather than a from-import, which binds at import time and
  would have silently stopped receiving `monkeypatch.setattr(dependencies, ...)`. 29 tests failed
  and said so.

One observable change, not covered by "no behaviour change": the records these functions emit now
  carry a different logger name -- the `use_cdn="auto"` drift from `maidr.util.bundle_freshness`,
  and bundle-unreadable from `maidr.util.warn`. Message text, level and trigger conditions are
  unchanged; only a caller filtering on `logging.getLogger("maidr.util.dependencies")` is affected.
  `docs/index.qmd` now names both and points at `maidr.util` as the filter that survives a move.

That also broke six tests without failing any of them. `test_bundle_freshness.py` had six
  `caplog.at_level(..., logger=dependencies.__name__)` calls left naming a logger that no longer
  emits, still passing because `caplog.records` collects by handler rather than by name. Which of
  the six belonged to which module was settled by spying on `logging.Logger.handle` while they ran
  -- a first pass sorted them by call site and misfiled one, and nothing in the suite could have
  caught that.

`BUNDLE_WARNING_ENV_VAR` is imported straight from `warn`, its actual owner, rather than forwarded
  through the `__getattr__` shim to `bundle_freshness`, which carried it only because that module
  imports it for its own message text. Pinned by a test that fails if the shim is put back in the
  path.

- **util**: Move the bundle capability check into its own module
  ([#494](https://github.com/xability/py-maidr/pull/494),
  [`c68e197`](https://github.com/xability/py-maidr/commit/c68e19754d74bbe20668959e0bc2a3d4206ad239))

First cut of the split #293 asks for. `dependencies.py` owns three separable concerns and had grown
  to 2248 lines; this takes the one that answers "can the bundled maidr.js draw what we are about to
  hand it".

The seam is one the tests already drew: `tests/core/test_bundle_capability.py` and
  `tests/core/test_bundle_freshness.py` split along exactly this line before the module did.

`_RELEASE_RE` deliberately stays behind despite sitting in the moved region -- `_version_key` uses
  it, and it is a version-parsing primitive rather than a capability one. `_bundle_warning_enabled`
  and `BUNDLE_WARNING_ENV_VAR` stay too, and are imported: the warning policy is shared with the
  freshness side, so it belongs to neither alone.

`maidr.util.dependencies` keeps resolving the moved names through a lazy module `__getattr__` rather
  than a re-export. That is load-bearing rather than defensive: since the internal call sites now
  import `bundle_capability` directly, it starts loading first, and an eager re-export finds it
  partially initialised. `test_the_shim_must_stay_lazy` asserts the shape on the parse tree so the
  invariant survives a future "simplification" even when the cycle is not currently live.

Refs #293

### Testing

- **altair**: Hold the warning's script list to what the adapter fetches
  ([#528](https://github.com/xability/py-maidr/pull/528),
  [`e099ef8`](https://github.com/xability/py-maidr/commit/e099ef8dbc1fb1bf60f7caed5b03efb7235de629))

Turn _ALTAIR_REMOTE_RUNTIME into a tuple of script tokens and build the warning prose from it, so a
  test can compare the named set against what the rendered markup actually fetches. Prose comparison
  could not do this exactly: "vega" is a substring of "vega-lite", so a substring test passed
  whether or not plain vega was still requested. The warning text itself is unchanged.

- **plotly**: Resolve every emitted selector against the chart it describes
  ([#659](https://github.com/xability/py-maidr/pull/659),
  [`44709c2`](https://github.com/xability/py-maidr/commit/44709c2972a80d9e97d2b730daba47f7508ec7f1))

Closes #644.

`tests/plotly/` asserts on the emitted strings, which checks that the code built the string it meant
  to build and not that the string finds anything. A selector that silently stops matching passed
  every test in the repo and reached users as a chart whose highlight had quietly stopped working.

Twenty-five figures are rendered in Chromium and every emitted selector resolved against the drawn
  chart: each finds at least one element, and finds as many as the layer announces. The layers that
  name nothing are listed with the measured reason for each. For the bar and the scatter, the
  resolved elements are matched against the datum plotly bound to them.

Run for the first time it found #656, the markers-only radar naming a path plotly never draws.

- **shiny**: Assert concurrent renders of one figure agree, not just exclude
  ([#510](https://github.com/xability/py-maidr/pull/510),
  [`e3d5aa0`](https://github.com/xability/py-maidr/commit/e3d5aa00ef4d759ddc0cadebd6eab6929ce96889))

Delivers the regression test offered on #454 for its third finding.

`test_two_renders_of_one_figure_do_not_overlap` already fails without the per-figure lock, so this
  is a complement rather than a gap-filler -- the PR opened claiming otherwise and was corrected.
  What that test cannot do is see what the exclusion protects: it monkeypatches `maidr.render` to a
  sleeping stub, proving non-overlap and nothing about the output.

This runs the real render and asserts the consequence. `savefig` writes `fig.dpi` for its duration,
  so two renders of one figure race on one mutable attribute and the loser draws the whole chart at
  the other call's dpi -- 460.8x345.6 for a 640x480 figure. Not garbled markup and not an exception:
  a complete, well-formed SVG at the wrong scale, in the geometry the highlight overlay and the
  tactile export are positioned against.

Six renders start from a barrier rather than from whenever each thread is scheduled, so a quiet
  runner cannot stagger them into a silent no-op. Growing the chart was measured and is not the
  variable: detection was 8 of 8 at 30, 100 and 200 bars alike. Falsified 8 of 8 with the lock
  removed and 8 of 8 passing with it.

The docstring records what the test does not cover -- the comparison strips `maidr="..."`, which
  carries the embedded schema, so a data race that moved no coordinate would pass -- and that the
  barrier synchronises the start rather than the duration, naming the sibling test to trust on a
  slow runner instead.

Also hardens the file's existing concurrency tests: two unbounded joins are bounded with a liveness
  assertion, and all three tests use daemon workers, so a real deadlock fails the test rather than
  wedging the interpreter at shutdown.

- **widget**: Cover the iframe a hosted render wraps the chart in
  ([#520](https://github.com/xability/py-maidr/pull/520),
  [`769803b`](https://github.com/xability/py-maidr/commit/769803bac03b7ccff0901a520670f34ea297ec09))

Under a live host the schema is nested inside an iframe's `srcdoc`, escaped a second time on top of
  lxml's escaping of the `<svg>`. That is the form a Shiny or Flask reader receives, and nothing
  asserted the grid still reads in it -- every other grid test goes through `_flatten_maidr`
  directly, where no wrapping happens.

The three entry points are checked together, but not because they branch. `Environment.is_shiny()`
  asks whether a session is live, not which door was called, so all three wrap or all three do not
  -- measured byte-identical in both states. What holds them together is weaker and still worth
  pinning: no door may grow post-processing of its own, which is the #443 class of bug.

The figures are the shapes #512, #517 and #519 corrected: an authored gap, a proportions gridspec,
  and panels re-parented by their colorbars.

Three mutations, each biting only its own tests -- a wrong shared grid, a door that post-processes,
  and wrapping suppressed.


## v1.21.0 (2026-08-17)

### Bug Fixes

- Describe the lines a layer's own calls drew, and declare a seaborn floor that imports
  ([#442](https://github.com/xability/py-maidr/pull/442),
  [`7890d33`](https://github.com/xability/py-maidr/commit/7890d333bab1808843f131d551494ac06aa76895))

`MultiLinePlot._series()` swept every data-space line on the axes. Box plots, violins and boxen
  plots render their whiskers, caps and medians as `Line2D` objects in data space, so one reference
  line over any of them made the line layer describe the box's own geometry as a chart -- 11 series
  where there was 1, each two points long, announced exactly as data would be.

The internal context already separated the two, so the fix turns on something that was there: a
  companion chart draws its lines inside its own patch's context, while a user's `ax.plot` arrives
  with the context clear. The lines accumulate on the axes and the list is handed over by reference,
  which keeps the one thing the sweep was right about -- several `ax.plot()` calls forming one
  multi-series layer.

Two reads of the axes remained a level down, in `step_utils`, and both decide things about a step
  chart: a step drawn after a box plot registered as `line` rather than `step`, losing the ordinal
  level names with it, and a box plot drawn after a step line was enough for `stepDirection` to be
  dropped at render time. Both helpers now take the lines a layer owns, and `is_step_axes` is
  renamed `is_step_layer` because "axes" was the scope that invited the bug.

The before-snapshot is skipped on the `Axes.plot` path, where the return value already is the lines
  the call drew: measured at 2,000 lines on one axes, `list(ax.get_lines())` cost 369 us against
  ~600 us for the whole patched call, and 2,000 calls in a loop went from 1213 ms to 749 ms.

Separately, `pyproject.toml` declared `seaborn>=0.12` while `patch/boxplot.py` reached for
  `_CategoricalPlotter.plot_boxes`, which arrived in 0.13 -- so `import maidr` raised an
  `AttributeError` on any 0.12 environment, before anything the user wrote could run. The floor is
  raised to what the package can actually import, and the dead version branch (which passed a
  version string where the wrapper function goes) is dropped rather than repaired.

Closes #440, #441

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>

- Highlight the mark being read, and name the axis that carries the categories
  ([#359](https://github.com/xability/py-maidr/pull/359),
  [`8f5e8ed`](https://github.com/xability/py-maidr/commit/8f5e8ede214cc9f8a2f45c3d9ce65193d4e9f064))

Closes #354 and #353.

MaidrPlot._elements was appended to during extraction and never cleared, so it grew by a full set of
  artists per render. It is the ordered list the highlight machinery tags, and the frontend indexes
  into it by point index, so a doubled list left point n pointing at the artist for point n mod
  count. Extraction owns the list now: render() clears it first.

Three things that alone would have left it wrong. ViolinKdePlot registered its bodies in __init__,
  so a central clear would have dropped them; CandlestickPlot, MplfinanceBarPlot and
  MplfinanceLinePlot re-ran their own extraction inside render(), which doubled within one render
  and after the clear; and BoxPlot, ViolinBoxPlot and ViolinKdePlot each keep gid lists beside
  _elements that accumulated or were reversed in place, so a box chart emitted three selectors per
  box after a third render and a horizontal violin paired its selectors with the wrong bodies on
  every even one.

Separately, LineExtractorMixin recovered category names from the x ticks only, so a horizontal
  categorical chart announced the positions its groups were drawn at -- and a dodged one the offsets
  it shifted them to. Both axes are asked the same question now, gated on which one matplotlib
  actually mapped strings onto. That gate also stops a point sitting on a numeric tick from taking
  the tick's label text, so a plain line chart reports x as 1.0 rather than as the string "1.00".

- Read trace types from the enum, and report a positioned sample with no reading
  ([#437](https://github.com/xability/py-maidr/pull/437),
  [`05f9f15`](https://github.com/xability/py-maidr/commit/05f9f1548f56054b73babb9e5878d82ec922219f))

Co-authored-by: Claude <noreply@anthropic.com>

- **a11y**: Name the iframe every chart is rendered into
  ([#463](https://github.com/xability/py-maidr/pull/463),
  [`388885e`](https://github.com/xability/py-maidr/commit/388885ea12e0d08a7680d31c83714f1078ca1776))

Every iframed render -- notebook, Shiny, Flask -- emitted an <iframe> with no title, so a screen
  reader announced an unnamed frame. A reader arriving at a chart was told a frame was there and
  nothing else: not that it held a chart, and on a page carrying several, not which one.

The chart's own title now leads the name, because that is the part that tells one frame from the
  next; the qualifier follows so the name also says what kind of thing the frame is.

ax.set_title("Body mass by species") "Body mass by species, accessible chart" no title "Accessible
  chart"

The title is read off the emitted schema rather than the figure, so the frame is named what the
  chart announces itself as and the rule lives once for matplotlib, Plotly and Altair. A
  figure-level title wins; failing that a single title shared by every layer is the figure's name
  too. Panels titled differently take the bare label.

Also fixes a Python 3.9 import break the first version introduced -- a PEP 604 union with no future
  import, which raises at definition time on the oldest supported interpreter -- and enables ruff's
  FA102 with a CI step that can fail on it, since `check --diff` cannot.

Closes #453

- **api**: Fall back to a static image instead of raising a KeyError
  ([#444](https://github.com/xability/py-maidr/pull/444),
  [`7e88d90`](https://github.com/xability/py-maidr/commit/7e88d9042fbb8bdf0e0a95d56571077e5bb4216d))

The same figure behaved two completely different ways depending on which door the user went through.
  `plt.show()` warned and drew a static image; `maidr.render()`, `maidr.show()` and
  `maidr.save_html()` raised `KeyError: 'No MAIDR found for figure'`. Measured through
  `maidr.render()`: `sns.rugplot`, `ax.quiver`, `ax.pcolorfast` and a bare `plt.subplots()` all
  reached the same line.

The graceful path existed and worked -- it was wired into the matplotlib backend and nothing else,
  so the three functions a user is actually told to call were the ones that crashed.

`KeyError` was the wrong shape as well as the wrong outcome. It is what Python raises when you index
  a dict wrong, and "No MAIDR found for figure" describes maidr's own bookkeeping: no chart type, no
  supported list, no next step, even though the backend already computed exactly that sentence a few
  modules away. For an accessibility library the asymmetry ran the wrong way: the user who
  explicitly asked for accessible output was the one who got nothing.

All four paths now fall back, which is what r-maidr does through every one of its entry points. The
  HTML carries the reason as well as the image, since a warning is seen by whoever ran the code and
  the page is what reaches everyone afterwards.

An empty figure gets its own message -- "your chart type is unsupported" is misleading advice for
  someone who called `maidr.render()` a moment too early, and telling the two apart is one pass over
  the axes' artist lists.

`UnsupportedPlotError` subclasses `KeyError` so the backend's existing `except KeyError` still
  catches it, and overrides `__str__` so it does not inherit `KeyError`'s quoting -- an uncaught one
  in a traceback would otherwise read as the dict-lookup failure this change exists to remove.

Closes #443

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>

- **bar**: Announce a bar's position when no tick label names it
  ([#383](https://github.com/xability/py-maidr/pull/383),
  [`7b9ae9c`](https://github.com/xability/py-maidr/commit/7b9ae9c7480897fc1c7e542431889b03054b8f0d))

`BarPlot` paired its bars with the labels on the categorical axis and raised when the counts
  disagreed. For a categorical x matplotlib puts exactly one tick per category, so they agree by
  construction. For a numeric x the tick locator picks its own breaks, so they have no reason to --
  and `ExtractionError` is fatal to the whole render, so the figure produced no HTML at all.

bars labels render x = np.arange(len(labels)) [mpl's own recipe] 3 5 raised x = np.arange(...), +
  set_xticks(x, labels) 3 3 ok plain categorical strings 3 3 ok numeric x, barh 3 8 raised numeric
  x, many bars (20) 20 8 raised

The first row is matplotlib's own grouped bar chart, which survives in the gallery only because the
  example goes on to call `set_xticks(x + width, species)` and make the counts line up by accident.
  Hiding tick marks -- a styling choice -- deleted the chart for the same reason.

The count check was guarding something real: three bars against five labels would announce the wrong
  name for every bar. So it still decides, but between labels when they line up and the bars' own
  drawn centres when they do not, rather than between a reading and nothing. Labels are one
  presentation of x, not x itself.

Positions are printed the way an axis prints them: integers exactly, so a bar at 1234567 does not
  become "1.23457e+06", and fractions through `:g`, since the centre comes from the rectangle's
  geometry and printing float noise exactly would be worse than printing it short.

Two existing tests asserted the old raising and now assert the new reading. Both were rewritten
  rather than deleted: neither argued that raising was right -- one guarded `ExtractionError` rather
  than `TypeError`, the other guarded against blank labels -- and both guarantees survive.

Scope: this fixes the plain `ax.bar()`/`ax.barh()` half. `GroupedBarPlot` carries its own copy of
  the count check and a stacked chart over numeric x still renders nothing; that is #384, since its
  fix has to decide per container and agree across the `z` series.

Full suite: 1218 passed.

Closes #382.

- **bar**: Announce a segmented bar's position when no tick label names it
  ([#386](https://github.com/xability/py-maidr/pull/386),
  [`d2d3810`](https://github.com/xability/py-maidr/commit/d2d38105b9936dbed28602bb4357ac0385861ad7))

The segmented half of #382. `GroupedBarPlot` carried its own copy of the count check that #383
  replaced in `BarPlot`, so a stacked chart over numeric positions produced no HTML at all:

stacked, categorical x ok stacked, NUMERIC x ** ExtractionError stacked, numeric x + set_xticks ok

which is the stacked half of how anyone writes it:

x = np.arange(len(species)) ax.bar(x, first, label="first") ax.bar(x, second, bottom=first,
  label="second")

Same rule as #383 -- tick labels when there is one per bar, the bars' own drawn centres otherwise --
  with one difference that is why it was not a transplant: the labels are decided once for the layer
  rather than per container. Every series of a segmented chart shares one category axis, so a
  per-container answer could name a category in one series and a position in the next. The
  per-container length check stays, guarding only what that cannot: a container of a different
  length from its siblings.

`z` comes from the legend and is untouched, asserted in both readings -- a reader who loses "upper"
  and "lower" cannot tell the series apart however good the categories are.

`_bar_position` is now `BarPositionMixin` in `maidr/util/mixin/`, shared by both extractors. This
  change created the second caller, and two copies of the geometry would drift: the horizontal
  branch is the kind of thing that gets corrected in one extractor and not the other, and a chart
  whose bars are announced at the wrong positions reads as a working chart.

Also pins a boundary found while writing the horizontal mirror: `ax.barh(..., left=...)` is not
  recognised as stacked at all, since the patch classifies on `"bottom" in kwargs` alone, so a
  horizontal stack arrives as two independent bar layers. Filed as #385.

Full suite: 1223 passed.

Closes #384.

- **bar**: Ask per axes which bar layer supersedes which
  ([#377](https://github.com/xability/py-maidr/pull/377),
  [`b7d7f33`](https://github.com/xability/py-maidr/commit/b7d7f3375faf294e996728f9cbcb699a58819ae1))

`BarPlot` and `GroupedBarPlot` both read every `BarContainer` on their axes rather than the bars
  their own call drew, so a stacked chart built from three `ax.bar()` calls registers three layers
  that each describe the whole chart. One has to survive and the rest are duplicates. How the
  survivor was chosen was the bug: a figure-wide "highest priority type seen" gated the collapse,
  and it then kept the first layer registered at each grid cell, whatever its type.

Three things followed, and none of them errored:

* a stacked bar in one panel deleted an unrelated scatter overlay from another panel, one with no
  bars in it at all; * which layer survived was registration order, so a reference line drawn before
  the bars meant the bar chart was the thing dropped; * matplotlib's own documented stacked bar --
  `bottom` omitted on the first call, as the gallery writes it -- registered BAR then STACKED, kept
  the BAR, and that layer's extractor found six patches against three tick labels and raised
  `ExtractionError`, which is fatal to the whole figure. Writing `bottom=np.zeros(n)` on the first
  call avoided it, which is why every test wrote it that way.

The question is now asked per axes and answered by class. The axes, not the grid cell, because
  `ax.twinx()` puts a second axes in the same cell and keying by cell dropped one of two independent
  stacked bars. By class, not by `PlotType`, because `MplfinanceBarPlot` also carries `PlotType.BAR`
  while reading the volume patches handed to it rather than sweeping the axes -- the premise that
  justifies dropping a layer is a property of its extractor.

Two details are load-bearing: the collapse runs before the artists are collected, since reading
  `plot.elements` renders the layer and the superseded `BarPlot` raised there, one step before the
  schema was built; and `selector_ids` is filtered in step with `_plots`, since the two are paired
  by index in both directions and a shift would hand every surviving layer its neighbour's id,
  moving the highlight with nothing raised.

`FigureManager.PLOT_TYPE_PRIORITY` and the priority-raising it served are removed, since nothing
  consults the figure-wide type any more.

Full suite: 1200 passed.

Closes #376.

- **bar**: Emit a bar with no height as a gap rather than as NaN
  ([#431](https://github.com/xability/py-maidr/pull/431),
  [`51ab7d4`](https://github.com/xability/py-maidr/commit/51ab7d494e4bf5e3a01b21a9c8e4f129e0edec18))

Co-authored-by: Claude <noreply@anthropic.com>

- **bar**: Read `left` as a stacked bar's baseline, as `bottom` is
  ([#387](https://github.com/xability/py-maidr/pull/387),
  [`ebf3fdc`](https://github.com/xability/py-maidr/commit/ebf3fdcaea3015a43bd97be89c24e56405e2edff))

A stacked bar is the one that says where its baseline is. `bottom` is how a vertical bar says it and
  `left` is how a horizontal one does -- the same argument for the two orientations -- and only the
  first was read. So the standard horizontal stacked bar arrived as two independent bar layers:

horizontal stack (left=) before ['bar', 'bar'] after ['stacked_bar']

The numbers were right and the layer count was plausible, so nothing looked wrong. What a reader was
  not told is that the second bar sits on top of the first -- the whole content of a stacked chart,
  and the reason `stacked_bar` exists as a distinct trace rather than as a label.

`test_a_horizontal_stack_is_not_recognised_as_one`, added by #386 and named for the defect precisely
  so it would fail the day it was fixed, did exactly that. It is rewritten as the horizontal mirror
  #386 could not write, since the case never reached `GroupedBarPlot` at all.

Reading the baseline's value rather than testing for its key also fixes a second defect:
  `bottom=None`, which matplotlib treats as omitting it, used to skip the dodge-detection branch
  entirely, so a dodged chart spelled that way was announced as a plain bar. Covered by its own test
  so it is deliberate rather than incidental.

Falsification: reading `bottom` only fails 1 of 7; treating every bar as stacked fails 23 of the
  suite -- the second being the regression that matters, since a baseline check firing
  unconditionally would announce every plain bar chart as a stack of one.

Full suite: 1225 passed.

Closes #385.

- **bar**: Read the bars this call drew, not every bar on the axes
  ([#381](https://github.com/xability/py-maidr/pull/381),
  [`faba998`](https://github.com/xability/py-maidr/commit/faba9985e8fec9da09a1ada5c6dfc6f01c091738))

`BarPlot` swept every `BarContainer` on its axes rather than the bars its own call drew, so two
  overlaid `ax.bar()` calls each found six patches against three tick labels, failed the count
  check, and raised `ExtractionError` -- fatal to the whole figure rather than to its own layer.

2 calls, no bottom (overlaid) before ExtractionError after ['bar', 'bar'] 10/20/30 and 30/20/10

#377 fixed the neighbouring case, where one call passes `bottom` and so registers a segmented layer
  for the collapse to keep. Here neither does, both register as plain BAR, and nothing supersedes
  anything. The twin axes case was always the tell: two `BarPlot`s are fine on different axes,
  because then each sweeps only its own containers.

What two overlapping bar layers should be announced as is a real question rather than an oversight.
  Two series drawn over one another with alpha are two series, so two layers -- each describing its
  own bars -- is the reading that loses no data and matches what is drawn.

Only the matplotlib entry point can name the container, so `common()` gains an optional `drawn_as`:
  the artist the call returned is handed to the layer under that keyword, after the draw so it
  cannot reach the wrapped function.

The sweep stays where it is right. seaborn draws one bar layer as several containers, one per hue
  group, and registers it from `sns_bar`, where no single container is the answer; narrowing that
  path would announce a hued chart as one group and drop the rest. `GroupedBarPlot` keeps sweeping
  too, since a stacked layer describes every bar on its axes by design. Both have their own
  regression guard.

The superseding rationale in `maidr.py` is corrected with it: it rested on `BarPlot` and
  `GroupedBarPlot` both sweeping, which is now only half true. The collapse is class-based rather
  than behaviour-based, so it still fires correctly -- but the reason is that the segmented layer
  covers the `BarPlot`'s bars either way, and that is what the comments say now.

Full suite: 1212 passed.

Closes #380.

- **ci**: Keep breaking commits in the changelog
  ([#336](https://github.com/xability/py-maidr/pull/336),
  [`2d3ba0f`](https://github.com/xability/py-maidr/commit/2d3ba0fdd650eca19efcc7694a982d3bd80dea09))

`exclude_commit_patterns` is an allowlist written out type by type, and every alternative ended in a
  literal `): ` or `: `. A breaking subject is `feat(deps)!: ...` -- after `feat(` the regex looks
  for `): ` and finds `)!: `, so no alternative matched and the commit was dropped.

The parser reads `!` correctly and returns `bump: major`, so a breaking change cut a major release
  whose changelog did not mention it. With `!` used without a `BREAKING CHANGE:` footer there is no
  breaking-changes section to fall back on either: the version jumped and nothing said why.

Collapsing the alternation to one pattern with an optional `!` fixes it. Compared against the
  written-out form over 125 subjects, the only treatment that changes is of the `!`-marked ones;
  `chore` stays out, marker or not.

The new test reads the pattern from `pyproject.toml` rather than restating it, and applies it the
  way `ReleaseHistory.from_git_history` does. This value has been wrong twice, both times silently,
  because nothing read it back.

Closes #335.

- **colorbar**: A colorbar is a legend, not a second chart
  ([#370](https://github.com/xability/py-maidr/pull/370),
  [`344caec`](https://github.com/xability/py-maidr/commit/344caec2ae75bfcc462f3ede00b73c9f9953b6a4))

A colorbar paints its gradient onto its own axes through the same entry points the heatmap patch
  wraps, so MAIDR registered it as a `heat` layer of its own. A phantom layer first -- a reader
  handed a second "heatmap" to page through that the figure does not contain -- and then the render
  died: extraction reaches the colorbar's outline, a LineCollection where a mappable is expected,
  and raises. `ExtractionError` is not confined to the layer that raised it, so a chart that would
  have read perfectly well produced nothing at all.

Not specific to heatmaps. `pcolormesh`, `scatter` and `hexbin` all came out with a spurious second
  layer and all three failed to render.

Hidden this long because `sns.heatmap()` creates its colorbar inside the patched call, where the
  recursion guard already suppressed it, and every worked example in the documentation happens to
  take that path.

The guard runs `Colorbar._draw_all` inside that same recursion context. There rather than on a test
  for "is this axes a colorbar", because `Figure.colorbar`, `plt.colorbar` and an explicitly
  supplied `cax` diverge well before the draw and converge on it -- and because `ax._colorbar` is
  not assigned until after the draw that registers the layer.

Closes #369.

- **deps**: Declare the packages `import maidr` needs
  ([#474](https://github.com/xability/py-maidr/pull/474),
  [`da5e0e8`](https://github.com/xability/py-maidr/commit/da5e0e868b4f1725a159fdc6cd335c63295cc9a0))

`pip install -U maidr` -- the install the README and the docs both give -- produces a package that
  raises `ModuleNotFoundError` on import. scipy is declared nowhere and is imported by
  `violin_kde_plot`; seaborn is declared only in extras and is imported by `wrap_seaborn` at import
  time; matplotlib is declared only in extras and survives on being an mplfinance dependency.

Every CI job installs `--all-extras`, so none of them sees the environment a user gets. Adds one
  that installs the package alone and imports it.

Closes #473

- **deps**: Never resolve the CDN version on an event loop
  ([#363](https://github.com/xability/py-maidr/pull/363),
  [`b7d5294`](https://github.com/xability/py-maidr/commit/b7d52947755899669689c12c0b4f9a5cd709c8f8))

`maidr.render()` is synchronous and Shiny calls it from `render_maidr.render()`, which is `async` --
  so under the default `use_cdn="auto"` the first figure in an app performed a blocking `urlopen` on
  the event loop. Every concurrent session queued behind it on `_fetch_lock` while it ran, for up to
  `MAIDR_CDN_TIMEOUT`, and that budget is only approximate: `urlopen`'s timeout applies per socket
  operation and does not reliably cover `getaddrinfo`.

`get_cdn_version()` now answers from the bundled version when a lookup would have to be made from a
  thread running a loop. The bundled version is a real published one, so the URL resolves and is
  immutable -- not the mutable `@latest` tag this module exists to stop emitting.

The trade is that an async app no longer picks up a release newer than its wheel automatically. That
  is the trade the docs already recommended making by hand: `MAIDR_CDN_VERSION=bundled` was the
  advice for Shiny apps, and this makes the default do it in the context the advice was written for.
  An app that wants the newer release can pin, or call `get_cdn_version()` once from synchronous
  code at start-up -- which is also what keeps this from being context-dependent for the life of the
  process, since a completed lookup is used on the loop like anywhere else.

`bundled_cdn_url()` spelled out the same pin-then-cache-then-bundled fallback separately, and its
  own comment records what happened when the two disagreed: one page loading two builds of maidr.js.
  Both now read `_offline_version()`.

Not fixed, and said so rather than implied: synchronous threads still queue on `_fetch_lock` while
  the first of them resolves. It is the event loop specifically that must not be made to wait.

Closes #296

- **deps**: Stop emitting @latest on the failure path, and warn on a mistyped pin
  ([#367](https://github.com/xability/py-maidr/pull/367),
  [`1594502`](https://github.com/xability/py-maidr/commit/159450272a04ea2e600d5bd0058858f485ca2fba))

Three follow-ups from #291.

A failed lookup emitted the mutable tag. `@latest` carries a seven-day `Cache-Control`, which is the
  whole of #290, so degrading to it when the lookup failed meant the fix stopped applying in exactly
  the case it was written to survive -- an offline browser could still be handed a week-old build.
  It now falls back to the bundled version: a real published release, immutable, and the same copy
  py-maidr would serve with `use_cdn=False`. Three other paths had already moved there (#363, #366),
  and being the last one still emitting the mutable tag was not a place worth defending. An explicit
  `latest` pin is untouched -- asking for the mutable tag is not a failure.

`set_cdn_version("3.74")` did nothing, quietly. A missing patch component logged a line and was
  otherwise ignored, so the caller got no return value, no exception, and a log line they may never
  see. It now raises a `FutureWarning` at the call, and says a future major will raise `ValueError`
  instead. Not raising today, because that would break a script quietly mistyping its pin and
  rendering fine -- which is exactly the caller this is trying to reach. `MAIDR_CDN_VERSION` stays
  lenient, and the asymmetry is documented rather than implicit.

`STALE_MINOR_GAP = 5` was picked without the release histories. Measured against them, the deciding
  number is not upstream's cadence but how many minors accumulate between the py-maidr releases that
  refresh the bundle: over seventeen cycles, median 1, and 5 is reached once -- the 68-day gap with
  nothing released. 3 would fire on a third of all cycles. The measurement is recorded beside the
  constant, re-derived from npm and PyPI as well as from the GitHub API.

Closes #295 Closes #294 Closes #292

- **errorbar**: Emit only the estimates matplotlib drew
  ([#433](https://github.com/xability/py-maidr/pull/433),
  [`51c27d0`](https://github.com/xability/py-maidr/commit/51c27d049d2877a20ee542fbc33a6631abe987c1))

Co-authored-by: Claude <noreply@anthropic.com>

- **hist**: Do not read a 2D histogram as a bar histogram
  ([#389](https://github.com/xability/py-maidr/pull/389),
  [`b1e3ff3`](https://github.com/xability/py-maidr/commit/b1e3ff360d76594e3451150221d94fe2465302dd))

`sns.histplot(x=..., y=...)` is a bivariate histogram: seaborn draws it as a `QuadMesh` of joint
  counts, not as bars. It registered as `hist` anyway, and extraction reached for the first
  `BarContainer` on an axes that has none -- raising a bare `StopIteration`, fatal to the whole
  figure and naming nothing.

2D histplot alone ['hist'] ** StopIteration scatter + 2D histplot overlay ['point', 'hist'] **
  StopIteration jointplot(kind='hist') ** StopIteration

`sns.jointplot(kind="hist")` is a documented, mainstream call and produced no HTML at all -- as did
  any supported chart sharing the axes.

Two defects, and fixing either alone is not enough. `extract_container`'s branches disagreed: the
  list branch returned empty, the single branch raised, so the `if plot is None` handling every
  caller opens with could never run. Both now answer with a value. That alone turns `StopIteration`
  into `ExtractionError`, still fatal -- so the patch also declines to register when its call drew
  no `BarContainer`.

Asked of the containers *this call added*, not of everything on the axes, which is the difference
  between declining and lying. An axes that already holds bars would otherwise answer for someone
  else's artists and the `hist` layer would describe the barplot's bars with bin edges invented for
  them -- right numbers, wrong chart, nothing raised. The snapshot holds the containers by reference
  rather than by `id()`, since an id is unique only while its object lives, and a set would hash
  `BarContainer` by value because it extends `tuple`.

A bivariate histogram is now simply unsupported, as `sns.kdeplot(x=..., y=...)` already was -- and
  the figure it appears in survives.

Full suite: 1235 passed.

Closes #388.

- **line**: Drop samples that have no position on the axis
  ([#430](https://github.com/xability/py-maidr/pull/430),
  [`ed59a84`](https://github.com/xability/py-maidr/commit/ed59a8465db40df1b88008cfc940e9af0dcdca43))

Co-authored-by: Claude <noreply@anthropic.com>

- **line**: Stop announcing a reference line as data
  ([#435](https://github.com/xability/py-maidr/pull/435),
  [`e745b24`](https://github.com/xability/py-maidr/commit/e745b246ea85e9dea3033434bdc203ea0575a589))

Co-authored-by: Claude <noreply@anthropic.com>

- **mplfinance**: Keep the title the caller gave the chart
  ([#465](https://github.com/xability/py-maidr/pull/465),
  [`554db5b`](https://github.com/xability/py-maidr/commit/554db5bc034934c6bcc86fe40426acbeb4c1b818))

CandlestickPlot, MplfinanceBarPlot and MplfinanceLinePlot each overwrote the layer's title with a
  fixed description of the chart type, so a caller naming their chart with ax.set_title() lost that
  name.

It mattered more after #453, which names the iframe every chart renders into after the chart's own
  title: the fixed string became the accessible name too, so every candlestick on a page was
  announced identically and a reader tabbing between them could not tell which they had reached.

The caller's title now wins and the description stays as the fallback, which tells a reader given no
  name what kind of chart they are on. Whitespace counts as absent, matching the trimmed check used
  elsewhere.

mpf.plot(title=...) was never affected -- it sets the figure suptitle -- and is covered so the two
  spellings are pinned as agreeing.

Also removes MplfinanceBarPlot.set_title, which nothing called and whose `self._title` was never
  read.

Closes #464

- **plotly**: Address a box by its trace group and its position within it
  ([#417](https://github.com/xability/py-maidr/pull/417),
  [`a9cd784`](https://github.com/xability/py-maidr/commit/a9cd7841e43f037b380f0209c4bbf6c8f74ba12a))

A box needs two indices and was given one. Plotly puts one `<g>` in the `boxlayer` per trace and
  draws that trace's boxes as direct `path.box` children of it, so a categorical `go.Box` puts all
  of its boxes inside a single group. Numbering them as though each were its own group made box 1
  match every box in the trace and boxes 2..n match nothing.

Three failures, each measured in Chromium. A trace with three categories emitted `g:nth-child(1..3)`
  into a DOM holding one group of three boxes. `layer_position` widened its search to boxlayer-mates
  only when the trace was itself a candlestick, so a candlestick counted the boxes beside it while a
  box ignored the candlestick and claimed the group it had already taken. And `PlotlyMultiBoxPlot`
  looped over traces rather than boxes, so two traces of two categories produced four boxes of data
  and two selectors -- half addressing nothing while the frontend paired the rest positionally.

A lone box is built in `_extract_plots` rather than left to the factory, which sees one trace and
  cannot know what shares its layer.

Verified in Chromium: 15 of 15 box selectors resolve to exactly one element across a categorical
  trace, three plain traces, two categorical traces, both candlestick orderings, and a figure whose
  outliers fall in some categories and not others.

Closes #395.

- **plotly**: Aggregate a histogram's bars the way histfunc does
  ([#408](https://github.com/xability/py-maidr/pull/408),
  [`36a1e32`](https://github.com/xability/py-maidr/commit/36a1e323af88c95259018e464f9afa95337f9679))

`histfunc` selects what a bar measures. `_extract_plot_data` called `np.histogram`, which returns
  bin populations, and never read the attribute, so every aggregating mode was announced as a count.

Two things widen this past how it was raised in review. It is not only `sum` -- `avg`, `min` and
  `max` are ignored too. And it is not only the categorical path: numeric binning has it as well,
  where a reader gets 2 for a bar the chart draws at 30, inside a layer whose bin bounds are all
  correct, so nothing else in the announcement looks wrong.

The empty-bin behaviour could not be reasoned out and was measured. `count` and `sum` announce a
  zero for a bin nothing landed in; `avg`, `min` and `max` have no answer and plotly emits no point
  at all -- interior bins included, not just the edges #402 trims. But setting any `histnorm` brings
  them back as zeros, across all three functions and all four norms. So the two attributes do not
  compose as one step after the other, and applying them in sequence would be wrong for exactly the
  figures that use both.

A non-numeric value is dropped rather than counted as zero -- a bin holding ['z', 'w', 8] averages
  to 8, not 8/3, and its min and max are 8 as well. A bin left with nothing numeric is then empty,
  and takes the same path as a bin nothing landed in.

Plotly also pairs the two arrays positionally and reads only as far as the shorter one, for the
  binning as well as the values and whatever `histfunc` says. `go.Histogram(x=[1..9], y=[10..50])`
  draws three bins spanning 1 to 5, so the count path was already wrong for such a figure before any
  aggregation existed; slicing only the value array left it shorter than the bin assignment and
  raised an IndexError out of a rendering path.

Verified against `gd.calcdata[0]` after `Plotly.newPlot` in Chromium: all 60 figure shapes agree
  elementwise, both orientations.

Closes #405

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>

- **plotly**: Announce a barnorm layer's shares rather than its counts
  ([#414](https://github.com/xability/py-maidr/pull/414),
  [`86d032b`](https://github.com/xability/py-maidr/commit/86d032b37ed1a0d445abdf65e7d47042e97bd584))

`layout.barnorm` rescales each stack position to a common total, so the bars a reader sees are
  shares of their category. The layer was typed `stacked_normalized_bar` for it while the values
  underneath stayed the raw counts -- the type saying the bars are proportions while the numbers
  were the tallies, so adding them up never reached 100.

Adds `maidr/plotly/barnorm.py` and applies it to the bar and histogram paths together, since the two
  were matched on purpose and changing one alone would make them disagree. The core does not do this
  arithmetic: `SegmentedTrace` normalises nothing, so a normalised layer is expected to arrive
  carrying shares, as both r-maidr paths already do.

Rules measured against calcdata in Chromium, two of them non-obvious. The denominator depends on the
  barmode -- `relative` normalises each sign against its own total, `stack` pools them -- and under
  `stack` it is the absolute value of the signed sum, so `[0, -4]` draws `0, -100` where a plain
  signed sum would give `+100`. A position totalling zero becomes a gap that keeps its x, matching
  plotly, so the point count never changes. `barnorm` rescales the histnormed values rather than the
  raw counts, which only an unequal-sized pair of series can demonstrate.

Closes #409.

- **plotly**: Build no layer for a scatter trace that draws nothing
  ([#422](https://github.com/xability/py-maidr/pull/422),
  [`740068d`](https://github.com/xability/py-maidr/commit/740068d0223055ff70cec0bbf1737f7ce7811552))

A trace with nothing to plot gets no group from plotly, so there is nothing to announce and nothing
  to highlight. The core does worse than ignore such a layer: a series with no points makes
  LineTrace.text dereference an undefined point and throw, and the throw propagates out of Figure,
  taking the whole render rather than the one layer.

Exclude undrawn scatter-family traces from the line and area groupings, and seed the handled set
  with their ids so the fallback factory does not build them either. Scoped to the scatter family
  because draws_marks reads x/y, which a pie carries neither of.

Closes #421.

- **plotly**: Do not read a trace the chart does not draw
  ([#400](https://github.com/xability/py-maidr/pull/400),
  [`19869e5`](https://github.com/xability/py-maidr/commit/19869e55fda3a95d5cc7717c00f712fe8d13692f))

`visible=False` and `visible="legendonly"` both tell plotly to draw nothing, and plotly obeys
  completely: it renders no group at all for such a trace. Measured across bar, scatter, pie, box
  and violin, two traces with one hidden produce a single group in the layer.

`_extract_plots` read `to_dict()["data"]` without asking, so every hidden trace became a layer.
  Nothing errored -- a reader was told about series that are not on the chart, with nothing saying
  the series is switched off.

The bar case was the worst: plotly's default barmode stacks, so a hidden bar trace beside a visible
  one was merged into a `stacked_bar`. A plain one-series bar chart was announced as a stack of two,
  with the invisible series contributing segments nobody can see and totals that do not exist.

Underneath that, every selector scoped by position among its layer-mates -- candlestick, violin, pie
  -- counted the hidden trace as holding a slot it does not have, so the drawn trace's selector
  pointed at a group that does not exist. The audio, braille and text stayed correct, so only a
  sighted reader could tell the highlight had stopped.

Filtered once where the traces enter rather than guarded in each branch, so bar merging, line
  grouping, the position counters and the subplot grid all see only what was drawn. `visible` is
  read by membership rather than truthiness, since `visible=True` is a value a figure may set
  explicitly.

Closes #399

- **plotly**: Emit the histogram bins plotly actually draws
  ([#406](https://github.com/xability/py-maidr/pull/406),
  [`d62760b`](https://github.com/xability/py-maidr/commit/d62760baceb19dff144dbf9412baa977d12f0b76))

Three defects on the explicit-bin-size path, all identical on both orientations. An empty bin is not
  a harmless extra row: plotly draws no `.point` element for one, and the layer's selector resolves
  positionally, so a phantom bin shifts the highlight of every bin after it. A leading phantom
  shifts all of them.

Empty edge bins were emitted. Plotly emits bins from the first that holds an observation to the last
  and keeps every empty bin between them, but not the empty ones outside that span -- so a window
  wider than the data announced thirteen phantom bins, all before the first real one.

The bin start skipped plotly's anti-clustering shift. Only the autobin path ran `_auto_shift_bins`;
  an explicit `size` took a bare round multiple. `go.Histogram(x=[0, 1, 2, 3, 4],
  xbins=dict(size=2))` was therefore announced from 0 where plotly draws from -0.5, putting every
  value in a different bin than the one drawn around it, with the bin count unchanged.

The `end` fallback is now expressed on the grid the bins actually use. That change is not observable
  -- both forms reach at least the upper edge of the bin holding the maximum, and the trim removes
  the surplus either way.

The trimming rule took a window narrower than its data on both sides to pin down. "Span the data,
  clamped to the caller's range" fits every wider window and predicts one bin too many there: plotly
  discards the out-of-window values rather than piling them into the edge bin.

`_auto_shift_bins` now states the contract its two callers depend on -- the seed need only be some
  multiple of the width within one width of the true start, not one particular formula -- and a
  parametrised test pins the convergence rather than leaving it to be re-derived.

Measured against `gd.calcdata[0]` after `Plotly.newPlot` in Chromium. All 29 figure shapes agree
  elementwise, bin bounds and counts alike, on both orientations -- up from 16. Six of the thirteen
  disagreements had the right number of bins on the wrong grid, so a length comparison would have
  called them equal.

Closes #402

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>

- **plotly**: Generate the positions plotly generates when an axis is omitted
  ([#419](https://github.com/xability/py-maidr/pull/419),
  [`c8d3669`](https://github.com/xability/py-maidr/commit/c8d36693a1f86442237e929b61a214c811196643))

Both `x` and `y` are optional in plotly, and it fills in whichever is missing with `0, 1, 2, ...` --
  which is how most quick plots are written. py-maidr paired the two arrays with `zip(as_list(x),
  as_list(y))`, and `as_list(None)` answers `[]`, so the zip yielded nothing: every such trace
  produced a layer of the right type carrying no data at all, and hid the traces beside it in the
  same layer.

One shared `paired_axes` helper replaces the same pairing in the bar, scatter, line, grouped-bar and
  line-series paths, and the scatter's axis range is measured over the generated positions too --
  reading them raw left min/max at None, which failed the grid precondition and dropped
  min/max/tickStep for a layer that now carries points.

Symmetric rather than keyed by which axis holds the magnitudes: a horizontal bar puts its values on
  `x` and needs `y` supplied. An absent array is distinguished from an explicitly empty one, because
  plotly draws those differently -- `y` absent generates and draws, `y: []` comes back a single null
  point and draws nothing -- and conflating them would have put back the phantom-series misalignment
  #316 removed.

Closes #418.

- **plotly**: Keep data and selector aligned when a series is empty
  ([#350](https://github.com/xability/py-maidr/pull/350),
  [`0faa7fc`](https://github.com/xability/py-maidr/commit/0faa7fc46677557afecb8430e2034b857afa7a36))

`PlotlyStepPlot` and `PlotlyMultiLinePlot` built `data` and `selector` from the same traces by two
  different rules: a trace whose `x`/`y` came out empty was dropped from the data and still consumed
  a selector. The frontend pairs selector *i* with series *i*, so every series after the empty one
  addressed its predecessor's element.

The failure was silent in the way `nth-child` failures always are -- audio, braille and text were
  all correct, and only the visual highlight was wrong, so a sighted collaborator saw the wrong line
  highlighted while the person using the announcements had no way to notice.

Both lists now come from `_line_series_with_positions`, which filters the series and the positions
  by the same predicate. `data` is unchanged: an empty trace still produces no series, it just no
  longer takes a selector with it.

Closes #316

- **plotly**: Match a grouped histogram's layout to the orientation it declares
  ([#483](https://github.com/xability/py-maidr/pull/483),
  [`6f75119`](https://github.com/xability/py-maidr/commit/6f75119a3c61c684fb5a810c0cd293e24b079003))

Co-authored-by: Claude <noreply@anthropic.com>

- **plotly**: Number scatter positions by what plotly draws
  ([#420](https://github.com/xability/py-maidr/pull/420),
  [`2a2d6f3`](https://github.com/xability/py-maidr/commit/2a2d6f3361a89b2dbaa48cf0df034bf9729b2a52))

A scatter-family trace with nothing to plot gets no DOM node at all -- not an empty one -- so every
  trace after it moves up a position in the `scatterlayer`. Selectors were numbered by declared
  index, so three lines with an empty one in the middle emitted `nth-child(1)` and `nth-child(3)`
  into a two-node layer: the second surviving line announced correctly and highlighted nothing.

The empty sibling of the hidden-trace rule `is_drawn` implements for #400. `draws_marks` asks
  through `paired_axes`, so it agrees with #418 -- a trace omitting one axis is drawn, because
  plotly generates the missing array. Undrawn traces are numbered after the drawn ones rather than
  skipped: their indices are never rendered but are still validated, so uniqueness has to hold.

Fixes the line, step and area paths together, since all three read the same map, and a per-layer fix
  was impossible anyway -- an empty trace in one layer shifts the traces in another.

Verified in Chromium: 10 of 10 selectors resolve to exactly one element.

Closes #412.

- **plotly**: Read a histogram's bins from the axis it bins
  ([#403](https://github.com/xability/py-maidr/pull/403),
  [`5eadbd9`](https://github.com/xability/py-maidr/commit/5eadbd974f9aee163cac7f008e8d47e2c19c96e3))

A histogram bins one axis and counts into the other. `PlotlyHistogramPlot` read the sample from `x`
  and returned early when it was absent, so every horizontal histogram emitted a layer with an empty
  `data` list -- correctly typed, both axes correctly named from `layout`, and nothing in it to
  navigate. Nothing errored, and nothing in the schema's metadata showed the emptiness, so it read
  as a histogram of nothing rather than one that failed to read.

Which axis is binned is not always stated: `px.histogram(y=...)` writes `orientation` onto the
  trace, `go.Histogram(y=...)` writes nothing and leaves Plotly.js to infer it. `binned_axis`
  applies plotly's own rule, taken from `gd._fullData[i].orientation` read back out of Chromium
  rather than from the documentation. `go.Histogram(x=v, orientation='h')` settles the precedence:
  plotly honours the attribute and bins the absent `y`, drawing an empty trace rather than falling
  back to `x`.

The bin spec follows the binned axis too. Plotly discards the other axis's spec outright instead of
  falling back to it -- a horizontal trace given `xbins` autobins exactly as if none were given, and
  a vertical one given `ybins` does the same -- so reading `xbins`/`nbinsx` for every trace both
  honoured a spec plotly ignores and missed the one it uses.

Categorical samples move with it: plotly draws those as a count bar chart, and on a horizontal one
  the labels belong on `y`. Left on `x` they would be announced as counts and the counts as labels.

Verified against what Plotly.js drew for the same figures -- `gd.calcdata[0]` after `Plotly.newPlot`
  in Chromium. Across eighteen shapes the emitted bins agree elementwise on both orientations. Four
  still disagree, all on the explicit-bin-size path and all identically on `x` and `y`; that is
  #402, which predates this.

Closes #401

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>

- **plotly**: Read a stacked bar chart as stacked
  ([#391](https://github.com/xability/py-maidr/pull/391),
  [`4b55b66`](https://github.com/xability/py-maidr/commit/4b55b66b0e3478687a67bb41c31726b2281b9d0e))

The plotly bar classification is a lookup on `layout.barmode`, and it was missing a row while
  carrying the wrong fallback:

plotly draws maidr said no barmode relative (default) ['dodged_bar'] barmode=relative relative
  ['bar', 'bar'] barmode=stack stack ['stacked_bar'] barmode=group group ['dodged_bar']
  barmode=overlay overlay ['bar', 'bar']

Row 1 inverts the relationship rather than losing it. Plotly's default barmode is `relative`, which
  stacks; the code defaulted to `group`, which dodges. A reader was told the bars sit side by side
  when plotly drew them on top of each other -- so every segment means something other than what was
  announced, and the totals a stack is read for are absent from the reading entirely. Nothing
  errored.

Row 2 is how `px.bar(color=...)` arrives, the ordinary way to draw a stacked bar chart in plotly
  express: asking for stacking explicitly fell through to two independent layers.

`relative` is plotly's name for a stack that lets negative values run below the axis, so it joins
  `group` and `stack` as a mode that combines traces. `overlay` deliberately does not -- those bars
  are drawn over one another rather than joined.

Unlike the matplotlib side, where stacking has to be inferred from a `bottom=` argument, plotly
  states this in the layout, so this is a table to correct rather than a heuristic to design. Every
  value plotly accepts is enumerated in a test, three of the five rows having been wrong in a way
  nothing downstream could detect, and the default is asserted against plotly's own reported value
  rather than a literal.

Full suite: 1243 passed.

Closes #390.

- **plotly**: Report when a plotly chart runs out of maidr.js sources
  ([#467](https://github.com/xability/py-maidr/pull/467),
  [`7e7ab26`](https://github.com/xability/py-maidr/commit/7e7ab26e09cd427a89774c9a5062872c464fc684))

#468 gave the matplotlib loader a `reportNoRuntime` for the case where neither the CDN nor the
  bundled fallback loads. The Plotly loader has the same shape and the same failure, and was not
  covered: its relative-path fallback set `fb.src` and appended it with no `onerror` at all, and its
  notebook path swallowed a missing parent-window stash in a bare `catch`.

So a Plotly chart in a Shiny, Flask, or Jupyter frame with no network became an image with no MAIDR
  runtime -- no sonification, no braille, no keyboard navigation -- and said nothing, which is what
  #468 fixed one file over.

Rather than a second diagnostic, the helper moves from `maidr/core/maidr.py` to
  `maidr/util/dependencies.py`, which both renderers already import from, and Plotly calls the same
  `reportNoRuntime`. Leaving it beside one renderer would have meant either the Plotly path
  importing from `maidr.core` for a JS string, or two wordings for one failure -- and an earlier
  revision of this branch did exactly the latter before #468 landed, which is what the shared
  constant and `test_both_renderers_say_the_same_thing` now prevent.

The two notebook failures are reported apart, matching the matplotlib path: a readable parent with
  no stash and an unreachable parent end the same way but send the reader somewhere different.
  `use_cdn=False` keeps its own single message, because there the fix is `init_notebook()` whichever
  happened, and telling a caller who already passed `use_cdn=False` to pass `use_cdn=False` helps
  nobody.

Not verified in a browser: the tests assert on emitted script text, so that a 404 on a `<script>`
  fires `onerror` remains the one behavioural assumption underneath this that nothing here proves.

- **plotly**: Rescale a histogram's bars the way histnorm does
  ([#407](https://github.com/xability/py-maidr/pull/407),
  [`8aab79e`](https://github.com/xability/py-maidr/commit/8aab79ebd6a2bccdaa3c5c76785e5e1156e3b8fe))

`histnorm` decides what a bar measures. `_extract_plot_data` called `np.histogram`, which returns
  counts, and never read the attribute -- so a `px.histogram(histnorm='percent')` layer carried an
  axis labelled "percent" and a first value of 2, where plotly draws 3.33.

The label was right; it comes from `layout`, which plotly express fills in from `histnorm`. Only the
  values were untransformed, so the two halves of one layer disagreed with nothing marking which to
  trust. A reader working from the announced numbers concludes the first bin holds 2% where it holds
  3.33%, and finds the bars do not sum to 100 either.

The denominator is the part worth stating. It is the total of the bars' own values, not the number
  of observations. Those coincide under the default `histfunc='count'`, which is why the wrong
  reading survives the obvious test: measured with `histfunc='sum'` and `histfunc='avg'` over the
  same data, `histnorm='percent'` returns identical output -- impossible if the denominator were the
  sample size, since the two aggregates differ by a constant factor, and required if it is their own
  total. `apply_histnorm` therefore takes the values it is handed rather than recomputing from the
  sample, so the aggregate flows through unchanged when #405 lands.

The trim from #402 still runs on the raw counts rather than the rescaled values, because that is
  what "a bin nothing landed in" means. Every mode maps zero to zero so the two agree, but only the
  counts say it without depending on that.

A count stays an integer. Rescaled values do not become integers, since rounding a 3.33% share to 3
  would put back the defect this removes from the other side.

Verified against `gd.calcdata[0]` after `Plotly.newPlot` in Chromium: all 38 figure shapes agree
  elementwise, both orientations, including the nine new histnorm ones.

Closes #404

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>

- **plotly**: Run the shared line-series pass once per render
  ([#362](https://github.com/xability/py-maidr/pull/362),
  [`897baa9`](https://github.com/xability/py-maidr/commit/897baa948347ad646805abf6038d8cd9282cddff))

`PlotlyStepPlot` and `PlotlyMultiLinePlot` filter their series and their positions by one predicate
  so that series *i* always addresses the element series *i* is drawn as (#316). `render()` asks for
  the two halves separately, and each half was calling that pass for itself -- so the pass that
  exists to be shared ran twice.

Repeating it also assumes it can be repeated, and it cannot. `as_list` materialises a trace array
  with `list(value)`, so a one-shot iterable is spent by the first walk and reads as empty on the
  second: the layer reports its series and then no selector at all. That is the same silent
  no-highlight the pairing was written to prevent, reached from the other side. `Figure.to_dict()`
  never produces an iterator, so the export path does not hit it; a caller constructing a layer
  directly does.

`_drawn_line_series` caches the pass against the identity of the two lists it was built from, so
  whichever of `_extract_plot_data` / `_get_selector` runs first computes it and the other reads it.
  Keying on the inputs rather than stashing the result during `_extract_plot_data` -- the
  `PlotlyBoxPlot` idiom -- keeps it independent of `render()`'s call order.

The performance point the review on #350 raised is the same fix. 50 series x 10,000 points,
  `PlotlyMultiLinePlot.render()`, median of five: 1.859s before, 0.923s after, which is the 2x a
  doubled walk predicts.

Closes #361

- **plotly**: Say a horizontal bar chart is horizontal
  ([#481](https://github.com/xability/py-maidr/pull/481),
  [`a66b8f9`](https://github.com/xability/py-maidr/commit/a66b8f9a3fcd597bc7acc38dbdaa7da1a74686f3))

Co-authored-by: Claude <noreply@anthropic.com>

- **render**: Report when use_cdn="auto" runs out of sources
  ([#468](https://github.com/xability/py-maidr/pull/468),
  [`e92154e`](https://github.com/xability/py-maidr/commit/e92154ef6395a64bb9639f4fb52f1a9eae94d630))

`use_cdn="auto"` is documented as "try the CDN, fall back to the bundled copy". Inside a `srcdoc`
  iframe -- what a notebook, Shiny or Flask render produces -- neither fallback can resolve, and
  both failed in silence: the notebook path acts only `if (jsSrc)` and swallowed the miss in a bare
  `catch`, and the other never set `onerror` at all.

The reader was left with a chart that renders, looks like a chart, and says nothing about why it
  cannot be navigated -- while the setting that works, `use_cdn=False`, is otherwise only
  discoverable by reading the source.

Every path out of the fallback now reports through one `reportNoRuntime` helper that names the fix.

Closes #455

- **scatter**: Emit only the points matplotlib drew
  ([#432](https://github.com/xability/py-maidr/pull/432),
  [`9b5f967`](https://github.com/xability/py-maidr/commit/9b5f967641570682220ca3d3a1f2cddbcdbee04c))

Co-authored-by: Claude <noreply@anthropic.com>

- **scatter**: Read the collection each scatter call drew
  ([#428](https://github.com/xability/py-maidr/pull/428),
  [`ac040cd`](https://github.com/xability/py-maidr/commit/ac040cdb51df844d793e4e45cf45fb0ea03de509))

Co-authored-by: Claude <noreply@anthropic.com>

- **seaborn**: A colour probe is not a chart ([#375](https://github.com/xability/py-maidr/pull/375),
  [`b2ff1eb`](https://github.com/xability/py-maidr/commit/b2ff1ebfff24bdb44cbe3facc94dfb0a15ed5462))

`seaborn.utils._default_color` resolves a default colour by drawing a throwaway artist, reading its
  face colour, and removing it again. Every branch ends in `scout.remove()` -- it is a probe, never
  a chart. But it draws through `Axes.fill_between`, `Axes.plot`, `Axes.scatter` and `Axes.bar`, all
  of which are patched, and it runs before any seaborn-level patch has set a recursion context, so
  nothing suppressed it. Since #339 taught MAIDR to read `fill_between` as an area chart, the probe
  registered a layer describing a fill of two empty arrays.

rugplot ExtractionError -> renders ecdfplot line -> step stripplot 4 layers -> 3 boxenplot area,
  line, ... -> line, ...

`rugplot` is the #369 shape exactly. Its ticks are a `LineCollection` MAIDR does not read, so the
  probe's layer was the only one registered -- and reading its data raised `ExtractionError`, which
  is fatal to the whole render rather than to its own layer. A scatter with a rug over it, which is
  how `rugplot` is actually used, produced no HTML at all.

`ecdfplot` is the one worth reading twice: the layer count and the numbers were already right, but
  the probe registered first and its `ax.plot([], [])` carried no `drawstyle`, so the shared line
  pass settled on `line` for a curve drawn `steps-post`.

Suppressing the whole function rather than teaching `fill_between` to decline an empty call is the
  honest scope: the probe also drives `plot`, `scatter` and `bar`, and the next patch added to any
  of them would reintroduce this somewhere new.

Wrapped at every seaborn module holding a reference rather than at `__module__` alone:
  `_default_color` is a private helper imported by name into `categorical`, `distributions` and
  `relational`, so `__module__` names one binding out of four and the call sites take the other
  three.

Full suite: 1191 passed.

Closes #373.

- **seaborn**: Patch boxplot and violinplot at both names too
  ([#374](https://github.com/xability/py-maidr/pull/374),
  [`c926e40`](https://github.com/xability/py-maidr/commit/c926e40d47ce712d8c2b0030cc560a05a000be77))

#372 wrapped nine seaborn functions at both the package re-export and the module that defines them,
  and left `boxplot` and `violinplot` on the re-export alone. Measured, the gap was a real reading,
  not a consistency nicety:

seaborn.violinplot violin_box, violin_kde seaborn.categorical.violinplot area, line seaborn.boxplot
  box seaborn.categorical.boxplot area, box

A violin announced as a line chart -- not a degraded violin, a different chart -- plus a phantom
  area layer from the colour probe in `seaborn.utils._default_color`, which had no recursion context
  to suppress it because no seaborn-level patch had run.

Unlike the other nine, no seaborn grid reaches these two: `catplot` drives `_CategoricalPlotter`
  directly. What took the unpatched binding is ordinary user code importing from the defining
  module. The phantom area is fixed here only for these two functions; the probe still registers one
  wherever no seaborn-level patch runs, filed as #373.

Two corrections. The `wrap_seaborn` docstring listed `catplot` and `displot` among the grids that
  ran the unpatched function; measured by counting calls that reach the defining-module binding, the
  grids that did are `pairplot`, `jointplot`, `relplot` and `lmplot`. And a comment on #344 said
  these two were matplotlib-level only, which was wrong.

Every early return in `wrap_seaborn` now warns, except the one that is not a gap: a function whose
  `__module__` is `seaborn` is defined at the package root, so the re-export IS the defining binding
  and the wrap is complete. The warning names no grids -- which grids are exposed varies per
  function, and a fixed list would be wrong for someone.

Full suite: 1180 passed.

- **seaborn**: Patch each function at both names it answers to
  ([#372](https://github.com/xability/py-maidr/pull/372),
  [`4fbc97f`](https://github.com/xability/py-maidr/commit/4fbc97f4a8eb7690594d29569563ba98a704615c))

seaborn re-exports its plotting functions from the package root, and its own figure-level functions
  import them from the defining module, inside the function body (`from .relational import
  scatterplot # Avoid circular import`). Those are two separate bindings to one function object, so
  wrapping `seaborn.scatterplot` left `seaborn.relational.scatterplot` untouched and every grid in
  `seaborn/axisgrid.py` ran the unpatched function.

A `histplot` panel therefore arrived as bars -- `Axes.bar` cannot know it is drawing a histogram,
  and the seaborn-level patch that would have known never ran. And every panel registered twice:
  `seaborn.utils._default_color` draws a throwaway artist to resolve a default colour and removes it
  again, and with no seaborn-level patch there was no recursion context to suppress it.

pairplot before bar, dodged_bar, bar, dodged_bar, point x 4 after hist, hist, point, point jointplot
  before point, dodged_bar, dodged_bar after point, hist, hist lmplot before point, line after
  point, smooth

`lmplot` is the clearest illustration: its layer count was already right, so nothing looked wrong,
  while the fitted curve was announced as though it were the data.

`wrap_seaborn()` locates the defining module through `__module__` rather than a table of names, and
  checks identity before wrapping.

`displot` and `catplot` drive seaborn's plotter classes directly rather than importing the
  module-level functions, so they are untouched and still wrong; both are pinned by a test so the
  boundary is visible.

Closes #344.

- **seaborn**: Read a binned regplot's intervals as uncertainty, not as fits
  ([#458](https://github.com/xability/py-maidr/pull/458),
  [`75c2c37`](https://github.com/xability/py-maidr/commit/75c2c375f865fb53bacdcbbe6adcef01642f95f7))

sns.regplot(x_estimator=...) drew a confidence bar per bin as an ordinary line, and the patch asked
  the axes which of its lines were fits rather than knowing which lines its own call drew. Each
  interval became its own two-point `smooth` layer, so the layer count scaled with the data (61
  layers for a continuous x) and the uncertainty was unreachable from the estimate it bounds.

The same label heuristic matched `_child0`, which is what matplotlib names any unlabelled artist, so
  a line drawn before a regplot was announced twice -- once correctly and once as a model of itself.

Replaced by a before/after artist snapshot plus a geometric split: an interval bar stands at one x,
  the fitted curve spans the axis. The estimates and their intervals then travel as one ERRORBAR
  layer through the same PointPlot that sns.pointplot uses, so the two now agree.

Collections are snapshotted too, so the scatter layer is handed its own points rather than sweeping
  the axes.

Closes #451

- **seaborn**: Read displot as the distribution it draws
  ([#447](https://github.com/xability/py-maidr/pull/447),
  [`66e5383`](https://github.com/xability/py-maidr/commit/66e538378dcfca8bd97be476c286c06ce290447d))

`displot` is seaborn's figure-level interface for distributions, and its default kind draws a
  histogram. maidr read it as a dodged bar chart.

It does not import `histplot` -- it drives `_DistributionPlotter` directly -- so neither name
  `wrap_seaborn` patches was ever bound, and the panel was seen only by `Axes.bar`, which cannot
  know it is drawing a histogram:

sns.displot(df, x="v", bins=3) dodged_bar {'x': '-1.61082', 'z': '_container0', 'y': 9.0}
  sns.histplot(df, x="v", bins=3) hist {'y': 9.0, 'x': -1.6108, 'xMin': -2.3250, 'xMax': -0.8966}

Three losses at once. The type names a chart that compares groups side by side, which a distribution
  is not. The bin edges are gone, so the bin centre is announced where a bar chart puts its category
  name -- a precise-looking number that is neither an observation nor a boundary. And `z`, the name
  a reader hears to tell series apart, carried `_container0`, maidr's own internal identifier for a
  `BarContainer`.

`kind="kde"` had the smaller version: `line` where `kdeplot` gives `smooth`. A fitted curve is not a
  series of observations.

Both are fixed by patching the plotter methods the two interfaces share, the idiom
  `maidr/patch/boxplot.py` already uses for `_CategoricalPlotter.plot_boxes`. `histplot` and
  `kdeplot` set the internal context before calling through, so the inner patch declines for them
  and nothing registers twice.

One call covers the whole grid, and `plotter.ax` is None in exactly the faceted case, so the panels
  are taken from the `FacetGrid` -- reading `ax` alone would have registered nothing at all there.

`test_seaborn_floor.py` now guards every private seaborn attribute a patch reaches at import time,
  not only the one that caused #441: an attribute that moves breaks `import maidr` for every user,
  not only users of that chart type.

`catplot` remains unreached and is still pinned in `tests/core/test_seaborn_patch_reach.py`, which
  is where `displot` was pinned until now.

Closes #446

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>

- **seaborn**: Read every catplot kind as the chart it draws
  ([#450](https://github.com/xability/py-maidr/pull/450),
  [`1d42eed`](https://github.com/xability/py-maidr/commit/1d42eed9e11c7e3ec2a18e5db6eef8a889c5610e))

`sns.catplot` drives `_CategoricalPlotter` directly and imports nothing, so it reached neither
  binding `wrap_seaborn` patches and its panels were read by the matplotlib-level patches alone. Six
  of eight kinds disagreed with the axes-level function that draws the same chart, failing in three
  ways: a distribution announced as a line chart (`violin`, `boxen`), uncertainty dropped (`point`),
  and a wrong type plus a phantom layer (`bar`, `count`).

Registration moves to the plotter method the grid and the axes-level function share, so the two
  interfaces agree by construction. All eight kinds are now asserted equal to their axes-level
  equivalents.

Two further defects surfaced on the way, both from the same cause -- the patch re-reading the
  caller's keywords instead of asking seaborn what it resolved. An inferred-horizontal violin raised
  `TypeError` out of `render()` and produced no HTML for the figure, and a positionally-passed frame
  silently lost its `violin_box` layer. Both are answered by reading `plotter.orient`,
  `plotter.plot_data` and `plotter.var_levels`.

Registering per panel also needed a guard: a `row`/`col` grid allocates an axes for combinations the
  data does not hold, and registering those promised a layer whose extraction has nothing to read,
  taking the whole figure's HTML down. The panel list now comes from seaborn's own
  `iter_data(allow_empty=False)`.

Review found a real collision in the hue labelling -- two unnamed variables compared equal, so four
  violins came out under two names -- and a live sweep in `_register_kde_layer`, where a
  `fill_between` already on the axes replaced the violin's density with its own four vertices.

Closes #448. Closes #449.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>

- **shiny**: Let @output_args size a chart in Shiny Express
  ([#472](https://github.com/xability/py-maidr/pull/472),
  [`bf3ee9d`](https://github.com/xability/py-maidr/commit/bf3ee9d206d90638d080056ccbf3ccd78bdb2cdd))

Shiny splats `@output_args(...)` into `auto_output_ui()`, so a renderer that takes no keywords there
  raises `TypeError` rather than sizing the container. `shiny.render.plot` accepts `**kwargs` for
  exactly this reason; `render_maidr` did not, which left the documented way to size an Express
  output broken.

Arguments given to `@output_args` now take precedence over the ones given to the decorator, and
  anything `output_maidr` does not know raises there rather than being absorbed.

- **smooth**: Ask per axes which curve supersedes which line
  ([#379](https://github.com/xability/py-maidr/pull/379),
  [`fe7b429`](https://github.com/xability/py-maidr/commit/fe7b4292ff45aa1acf6e3c55831b658fee888948))

`regplot` draws its fit through `ax.plot`, so one curve registers both a LINE and a SMOOTH, and the
  line is the duplicate. That much was right. The question was asked of the whole figure -- any
  smooth anywhere, then drop every line anywhere -- which is the same shape of defect as #376, one
  function call below the code that fixed it.

A regression line in one panel deleted an unrelated line chart in another, and took that panel with
  it: the grid's column count comes from the surviving layers' indices, and nothing left carried
  column 1.

registered ['point', 'smooth', 'line'] before [[['point', 'smooth']]] after [[['point', 'smooth'],
  ['line']]]

Neither that filter nor the duplicate-gid one touched `selector_ids`, which is paired with `_plots`
  by index in both directions, so every layer after a dropped one inherited its predecessor's id and
  the highlight landed one layer off with nothing raised. It only bites when the drop is not last,
  which is why it survived.

All three rules -- segmented bars, fitted curves, duplicate gids -- now answer into one set and one
  lockstep filter, so there is one place the pairing invariant is stated instead of three that could
  each forget it. `maidr/util/dedup_utils.py` is deleted: leaving a helper whose whole shape is the
  bug invites it back.

Two limits are deliberate and pinned by tests rather than left implicit. The gid rule stays
  figure-wide, since whether one `_smooth_gid` can span two axes was not measured here; it also sees
  a later snapshot than its neighbours, because the gid is assigned during extraction, and its
  docstring records why that is inert rather than a misattribution. And a reference line on the same
  axes as a fit is still dropped, because per-axes scoping cannot tell an annotation from the fit's
  own line.

Full suite: 1207 passed.

Closes #378.

- **violin**: Emit box statistics raw instead of rounded to four decimals
  ([#415](https://github.com/xability/py-maidr/pull/415),
  [`89f15a4`](https://github.com/xability/py-maidr/commit/89f15a4ae7b3f2ede390a88e127a49a59b6b9718))

`round(x, 4)` is absolute, not significant: it discards everything below 1e-4 rather than keeping
  four digits of precision. For data in micrograms, molar concentrations, failure probabilities or
  seconds of a fast benchmark, min/q1/q2/q3/max all came out 0.0, so the box read as a flat line at
  zero and the distribution stopped being announced. Nothing errored -- the chart drew correctly and
  only the numbers were gone.

The frontend already guards this and needs the raw value to do it: `defaultFormat` rounds to two
  decimals for the announcement, then falls back to three significant digits when that would erase a
  non-zero value. Rounding here destroyed the small value before that guard could see it, and
  sonification, braille and extrema read the underlying numbers too.

Also brings this path in line with `boxplot.py` and the plotly violin path, which both emit raw, and
  with the outliers in its own record, which were never rounded.

Closes #398.

- **violin**: Stop naming a violin after an axis tick
  ([#470](https://github.com/xability/py-maidr/pull/470),
  [`2725364`](https://github.com/xability/py-maidr/commit/2725364898eb6f39e05a097e548eb0adb95f5e1c))

Co-authored-by: Claude <noreply@anthropic.com>

### Continuous Integration

- Refresh the bundled maidr.js when upstream publishes
  ([#355](https://github.com/xability/py-maidr/pull/355),
  [`03228f7`](https://github.com/xability/py-maidr/commit/03228f704a1303dccbf73fe11ddf1f3a447ca960))

The bundle only ever moved at py-maidr release time, so between releases `main` carried whatever
  upstream version the last release happened to pin. Checking out `main` to reproduce or test a
  freshly published upstream fix meant refreshing the bundle by hand first.

maidr's release workflow now sends a repository_dispatch here the moment `npm publish` succeeds,
  carrying the version it just published, and this workflow commits the refresh to `main` as it
  already did on manual dispatch. The payload names the version rather than leaving this side to
  re-resolve `latest`, which sidesteps the window where the dist-tag has not propagated; with
  neither supplied the script resolves `latest` exactly as before.

What users receive is unchanged, and deliberately so. The commit keeps its `chore:` prefix, so
  python-semantic-release still does not treat a bundle refresh as a release: an upstream release
  alone does not reach PyPI, and the refreshed bundle ships with the next feat:/fix:/perf: release.
  This makes `main` current, not PyPI. release.yml remains the authority on the released artifact --
  it re-resolves the newest upstream at release time and now simply finds nothing to commit when
  `main` is already current.

No scheduled backstop is added, unlike r-maidr's. That repository has no release pipeline --
  whatever sits on `main` at CRAN submission time is what ships -- so a missed refresh there is a
  missed shipment. Here the release-time refresh already re-resolves upstream, so a missed dispatch
  costs only the currency of `main`, never the released artifact.

The updater job joins release.yml's concurrency group. A group is scoped to the repository rather
  than to a workflow, so sharing the name is what serialises them, and they need serialising: both
  push to `main`, one through git-auto-commit-action and the other through semantic-release, and
  overlapping the second push is a non-fast-forward whose loser is a failed release. The schedules
  used to keep them apart and no longer do, since an off-schedule upstream release now fires a
  dispatch at any hour.

No new trust is granted. `client_payload` is written by whoever holds the sending token, but that
  token already needs write access here, and the version still goes through the same strict pattern
  check in fetch-maidr-bundle.sh and the same registry integrity verification.

Also corrects the release.yml comment that claimed the bundle never reaches `main` between releases,
  which this change makes untrue.

Sending side: xability/maidr#832.

### Documentation

- Say that the render blocks the loop, and that "auto" has no offline path
  ([#471](https://github.com/xability/py-maidr/pull/471),
  [`7e2d4da`](https://github.com/xability/py-maidr/commit/7e2d4da3b0b4d5f528a54779245ca660e0b07973))

The async callout was headed "No lookup happens on an event loop", which is true of the version
  lookup and easy to read as "the loop is fine". maidr.render() is synchronous and never awaits, so
  nothing preempts it: for as long as one render runs, the loop does not run at all.

The offline section did not mention that "auto" cannot fall back inside a srcdoc iframe, so on the
  default setting an air-gapped notebook, Shiny or Flask deployment gets the CDN or nothing. Stated
  as intended behaviour rather than a pending fix.

Adds tests/core/test_render_is_synchronous.py, skipped unless --run-benchmark, so the timing claim
  can be re-checked.

Documents #454.

### Features

- Give a seaborn regression its confidence band
  ([#425](https://github.com/xability/py-maidr/pull/425),
  [`14a6477`](https://github.com/xability/py-maidr/commit/14a6477f9ac217dda75614a9b1d098563075532f))

Co-authored-by: Claude <noreply@anthropic.com>

- Read seaborn's categorical charts as their data rather than as how they were drawn
  ([#438](https://github.com/xability/py-maidr/pull/438),
  [`289c699`](https://github.com/xability/py-maidr/commit/289c699f8d6e4ed8fce273834d6c481471a41975))

Two defects of one kind: a seaborn categorical chart announcing something the renderer invented as
  though it were a measurement.

**boxen (#253).** `sns.boxenplot` draws a letter-value plot -- the box plot's five-number summary
  generalised to a variable-depth ladder of quantiles. MAIDR had no type that could hold that, so
  the chart fell through to the generic matplotlib patches and produced a reading that was wrong
  rather than partial: a `line` layer of the three median segments, each read as a two-sample
  series, plus one `point` layer per category holding only the outliers at numeric slots. Every rung
  of every ladder -- the entire chart -- was absent, and nothing said so.

maidr 4.3.0 shipped `TraceType.BOXEN`. `BoxenPlot` emits it, reading the ladder off the boxes
  seaborn drew rather than recomputing statistics: rungs from the box edges, the median from the
  segment spanning the ladder, the fliers from the collection on its own category slot, and only the
  tail probability inferred -- from seaborn's own `LetterValues` construction.

**strip and swarm (#439).** Both scatter points sideways so overlapping observations stay separable,
  and that offset is what `get_offsets` returns, so it is what was announced -- a precise number for
  a quantity that does not exist, on an axis whose ticks read a, b, c, and for a strip plot a
  different number on every run. It also cost the chart its shape: `ScatterTrace` groups by exact x,
  so 90 jittered points became 90 columns of one instead of 3 of 30. Points now report their nearest
  tick when, and only when, the axis is genuinely categorical.

Nine rounds of review found real defects, each reproduced before being fixed: a horizontal boxen had
  its axis labels swapped; `showfliers=False` plus a strip overlay made a ladder claim 14 outliers
  from the other layer; an `axhline` with an explicit span, and a short data-space segment, were
  each read as a median; `gap=` renamed hue levels outright; and nine methods were defined twice,
  with the live `_levels` being the version an edit had meant to replace.

Closes #253, #439

- **area**: Read a baseline-to-curve fill_between as an area chart
  ([#371](https://github.com/xability/py-maidr/pull/371),
  [`0450d0e`](https://github.com/xability/py-maidr/commit/0450d0ebb2a36da17d3fc6fc8a00ce9bcc29acb9))

`Axes.fill_between` was unregistered, so a filled area chart drew and read as a static image --
  while `ax.stackplot()` already emitted an area layer for the same picture, making the gap
  arbitrary from a reader's side.

`fill_between(x, y1)` fills from zero up to a curve, which measures what a one-series stackplot band
  measures, and is registered as an area.

Three shapes are declined rather than described, because each draws something an area layer would
  misreport:

- a band between two curves, whose content is the gap rather than either edge, so an area would
  announce `hi` as a magnitude and drop `lo`; - a constant non-zero second edge, whose heights are
  measured from somewhere the announcement would not mention; - a `where=` mask, which fills only
  part of the range -- three separate bands out of an eight-point series -- where an area layer is
  one continuous series and would report the gaps as filled.

A mask that holds everywhere, and an explicit array of zeros, are the default spelled out and read
  as the areas they draw.

Values come from the call's own arguments rather than the polygon, as `stackplot`'s patch already
  does: the artist is a closed outline running forward along the curve and back along the baseline.
  `fill_betweenx` is the same chart turned over.

Part of #339; the band-around-a-line case stays open there.

- **area**: Read a stackplot as the area chart it is
  ([#356](https://github.com/xability/py-maidr/pull/356),
  [`23c49e3`](https://github.com/xability/py-maidr/commit/23c49e309b489a475742dfc8c5cdb0fd18c096a7))

`Axes.stackplot` registered nothing at all, so a stacked area chart was invisible to a MAIDR reader
  rather than partially described.

The area layer reads its arguments rather than its drawn geometry, which is the inverse of
  ErrorBarPlot and PointPlot and for the same reason: a stackplot's polygons carry the running
  total, and the band height a reader wants is not recoverable from them. A single series is AREA
  and several is STACKED_AREA -- the count is the whole rule, since a baseline mode changes where
  the stack sits rather than what is stacked.

A DataFrame argument is read by row, as matplotlib's own np.row_stack does, via np.asarray(...).ndim
  rather than by shape guessing.

`ax.fill_between` is deliberately not registered: a two-curve uncertainty ribbon is not a value
  against a baseline, and reading it as one would misdescribe it.

- **bundle**: Warn when the bundle cannot draw the layer being emitted
  ([#360](https://github.com/xability/py-maidr/pull/360),
  [`331b3b8`](https://github.com/xability/py-maidr/commit/331b3b824279122cd27613795b4d0ebf2e124c42))

Closes #358.

STALE_MINOR_GAP measures drift in minor versions, which answers how old a bundle is. The question a
  reader needs answered is whether it can draw what is about to be handed to it, and the two come
  apart in both directions: a bundle five minors behind may render everything, and one minor behind
  may render none of a newly added type. The gap that prompted this was a bundle nine minors short
  of qualifying as stale while unable to render seven of the emitted layer types.

Asked of the bundle rather than of a table kept in step by hand: its own factory switches on the
  trace-type strings, so the shipped file already knows the answer and cannot forget a line when a
  type is added.

It also reaches an audience the staleness warning documents itself as unable to reach. That one
  compares against a published version it will not fetch, so a process rendering use_cdn=False
  offline stays silent however old its bundle is. This reads the installed file and makes no request
  at all.

Deliberately biased towards silence: an unreadable bundle, a CDN-only render and a supported chart
  all say nothing, each with a test. The warning names every unsupported type at once, once per type
  per severity, and is silenced by the same env switch as the staleness one.

- **deps**: Give the resolver's two silent failures a voice
  ([#366](https://github.com/xability/py-maidr/pull/366),
  [`0f3c5cf`](https://github.com/xability/py-maidr/commit/0f3c5cfd013a5dcfbb593298e2c7000a27b516b7))

Two silent failures on the CDN version path, one facing a user and one facing a monitor.

A broken bundle emitted `@latest` with nothing said. `_offline_version()` ended at `LATEST_TAG` when
  `maidr/static/VERSION` would not read -- the mutable dist-tag this module exists to stop emitting,
  which jsDelivr serves with a seven-day `max-age`. The URL is well-formed and the page works, so
  the only symptom was someone occasionally being served an old bundle for reasons nothing in the
  output explained. Only the broken-install road warns; a failed lookup is a routine operating
  condition and stays quiet, because warning on both would train people to ignore the message. The
  message names the consequence, and says which fault it is -- an absent VERSION reported as `is
  unreadable ('0.0.0')` claims the file contains those characters, which is the one thing it does
  not.

The freshness job went green forever when the resolver died. Passing on a failed lookup is right for
  a hiccup and wrong for a persistent failure: a green check that verifies nothing is worse than a
  red one because it is indistinguishable from a real pass. `ResolverOutcome` splits the endpoints
  into those that never answered -- the network, which nobody reading the job can fix -- and those
  that answered with something py-maidr could not use, which is py-maidr being wrong about their
  shape and will not fix itself. An unrecognised failure counts as unreachable, the quiet direction;
  an endpoint the budget never reached counts as neither.

Kept as a separate accessor rather than a wider `BundleStatus`, so the render path keeps its shape
  and its contract that a lookup failure cannot break a chart.

Closes #364 Closes #298

- **deps**: Warn that the placeholder maidr.css accessors are going
  ([#334](https://github.com/xability/py-maidr/pull/334),
  [`0e5b645`](https://github.com/xability/py-maidr/commit/0e5b64526cd82445d8dfa70c67b7107cadb657f1))

`maidr/static/maidr.css` has been a 406-byte placeholder since maidr 3.75.1, nothing in `maidr/`
  links a stylesheet, and r-maidr stopped bundling it on the same upstream release. It cannot simply
  be deleted: `bundled_css_path` is in `__all__`, so removing the file would leave a public function
  returning a path that does not exist. Both accessors warn now, the file keeps shipping, and the
  two go together at the next major.

`FutureWarning` rather than `DeprecationWarning`. Python's guidance splits them by audience, and
  someone calling this is assembling a dashboard rather than extending py-maidr. The practical half
  matters more: `DeprecationWarning` is silenced by default outside `__main__`, so a caller inside a
  Shiny app would meet the removal as a breakage instead of a warning.

Each accessor names a replacement of its own return type and spelled as a path that actually imports
  -- one returns a `Path` and the other a URL, and only one of the two is re-exported at top level.
  The tests resolve every symbol the messages name rather than substring-matching them, and check
  that the filter muting this in `test_cdn_version.py` has not gone stale.

Not touched, deliberately: `maidr-math.css` keeps its base64 KaTeX fonts. r-maidr strips them for
  CRAN's size limit at the cost of glyph fallback; py-maidr has no such limit and the saving is
  under 9% of a package whose JS bundle is five times larger.

Refs #333.

- **errorbar**: Read an estimate together with its interval
  ([#349](https://github.com/xability/py-maidr/pull/349),
  [`791df0d`](https://github.com/xability/py-maidr/commit/791df0d5627532108b17edf824aebf08aa633362))

`Axes.errorbar` was not patched, so any chart carrying uncertainty -- the majority of published
  statistical figures -- lost that information entirely.

Bounds are read off the drawn LineCollection rather than recomputed from the `yerr` the caller
  passed. Those are different quantities: matplotlib takes an offset while the schema carries an
  absolute position, and the offset has three shapes (scalar, (N,), (2, N)) before uplims/lolims
  change what the bar means again. The rendered geometry has already resolved all of them.

The patch hands the layer the exact container its own call produced. Looking one up on the axes
  would find the first container for both layers of a figure with two errorbar calls, describing one
  series twice and dropping the other.

Handles fmt="none" (no data line, so centres come from the call arguments, since an asymmetric bar
  is not centred on its midpoint), NaN errors (an empty segment that keeps its position, emitted as
  a sample with no bounds rather than as NaN, which would poison the trace's pitch range), xerr
  (horz orientation), both errors at once (y wins, and the collection order is x-first), capsize,
  and date axes (which previously raised, taking out the user's whole figure -- errorbar was the
  only patched type that crashed rather than degrading).

Derived bounds are cleaned of float noise: matplotlib draws at y - err, and 4.2 - 0.4 is
  3.8000000000000003, which a screen reader spells out in full.

`x` and `y` mean category and magnitude here in both orientations, unlike BarPlot and HistPlot,
  because ErrorBarTrace reads the magnitude as y/yMin/yMax with no orientation branch and
  ErrorBarPoint declares no xMin/xMax to hold a bound. The axis labels stay screen-aligned and the
  trace pairs them; both halves are asserted together so neither can drift alone.

- **heatmap**: Highlight a pcolor grid, and cover z_label
  ([#347](https://github.com/xability/py-maidr/pull/347),
  [`cbb13c0`](https://github.com/xability/py-maidr/commit/cbb13c0f11e6358ad3a317470bfde5caf3666700))

`Axes.pcolor` renders a PolyQuadMesh where `pcolormesh` renders a QuadMesh, and `patch/highlight.py`
  tagged only the latter. A pcolor heatmap read through audio, text and braille but carried no
  visual highlight, leaving low-vision users without a cursor on a chart every other reader could
  follow.

The wrapper goes on PolyQuadMesh and deliberately NOT on its PolyCollection base, which also backs
  violin bodies and `fill_between`. PolyQuadMesh inherits `draw` rather than defining one, so
  wrapping it installs a subclass-only override and the base keeps the unwrapped method; a test
  asserts both halves of that.

The two mesh classes also disagree about the shape they keep values in, so the reshape is now driven
  by the array's dimensionality rather than by the class.

Also adds the `z_label` coverage the previous round left open, across all three matplotlib entry
  points, and the NumPy docstring `heat` never had.

- **heatmap**: Register pcolormesh and pcolor heatmaps
  ([#346](https://github.com/xability/py-maidr/pull/346),
  [`54cb65a`](https://github.com/xability/py-maidr/commit/54cb65af1adf1d74f9163d8ae760c92d34ec37b5))

Only `Axes.imshow` and `seaborn.heatmap` were patched, so a heatmap drawn with `pcolormesh`
  registered nothing at all -- no layer, no warning, just silence. That is not an obscure path:
  `pcolormesh` is what you reach for whenever the grid is irregular or the axes carry real
  coordinates rather than array indices.

The extraction side already worked, because `seaborn.heatmap` draws through `pcolormesh` and has
  always taken that branch. Only the patch registration was missing.

Patching it exposed two more things. `heat` never consulted ContextManager, so with both
  `seaborn.heatmap` and `Axes.pcolormesh` patched the inner call registered a duplicate layer. And
  `fmt` -- which is seaborn's parameter -- was left in kwargs, where `pcolormesh` swallows it into
  `**kwargs` and the artist raises `AttributeError: QuadMesh.set() got an unexpected keyword
  argument 'fmt'`. It is now forwarded only to a function that declares it.

Closes #337.

- **hexbin**: Read Axes.hexbin as a hexagonal bin lattice
  ([#368](https://github.com/xability/py-maidr/pull/368),
  [`f723a86`](https://github.com/xability/py-maidr/commit/f723a86044247551d363d04f2acb008ba646a6de))

A hexbin is the standard answer to an overplotted scatter: bin the points into hexagons and encode
  the count as fill. Read that way it is a heatmap, and the navigation, braille and pitch all
  transfer. maidr.js has carried a `hexbin` trace since v4.2.0 and nothing here emitted one.

Two things about how matplotlib builds the lattice do not survive a naive reading. `get_offsets()`
  is built lattice by lattice and, within each, x index by x index, so consecutive offsets walk up a
  column and the offset rows come after the aligned ones -- grouping into rows is a permutation, and
  the selector list is permuted with them, or every bin past the first row boundary highlights
  someone else's hexagon while still announcing a real centre and a real count. And the rows are
  ragged by construction, so they are left that way rather than padded with bins that were never
  drawn.

The colour axis is named for what the fill encodes rather than always "count": `C=` replaces it with
  a reduction, a numeric `bins=` replaces it with the interval the value landed in, and `bins=` wins
  over `C=` because matplotlib applies it last.

A log-scaled lattice is declined rather than translated. matplotlib bins in the transformed space
  and hands the offsets back in it, so a bin centred at x = 3.4 would announce 0.53; on 3.9 the
  centres are not in `get_offsets()` at all. The figure keeps its static image instead.

The selector test resolves the emitted CSS against the real exported SVG and checks each match is
  the hexagon whose centre and count that bin announces.

Closes #341.

- **plotly**: Keep the step convention of a filled staircase
  ([#423](https://github.com/xability/py-maidr/pull/423),
  [`24734c0`](https://github.com/xability/py-maidr/commit/24734c0b0850829323d4f1002b6e698794389f61))

line.shape and stackgroup are independent plotly attributes, so a trace can be both a staircase and
  a filled band. The area classification runs first, so such a trace became a plain area layer with
  no stepDirection; before that it kept the direction but was announced as a line. One of the two
  facts was always dropped.

They are orthogonal, so the layer carries both. A stack cannot be split by direction the way the
  step layers are, so a stack whose bands disagree withholds the key rather than describing one of
  them wrongly. Both layer types now read one resolver, shared_step_direction.

Closes #413.

- **plotly**: Read a 100% stacked bar as one ([#393](https://github.com/xability/py-maidr/pull/393),
  [`1d5c9c7`](https://github.com/xability/py-maidr/commit/1d5c9c7901ceee55330e276f1d400b4e34b67b6e))

`layout.barnorm` is plotly's switch for normalising each stack to a common total -- `percent` scales
  to 100, `fraction` to 1. Either way the segment values are shares of their category rather than
  counts. MAIDR did not read it, so such a chart arrived as `stacked_bar`.

The numbers were announced correctly; what was lost is what they are. A `stacked_bar` invites the
  reading that each segment is a count and that the categories happen to total the same, when the
  equal totals are a property of the chart rather than of the data.

The core has carried `TraceType.NORMALIZED = 'stacked_normalized_bar'` for some time; `PlotType` had
  no member to emit it with, so the type was unreachable from Python. This adds it.

Read as a lookup rather than a heuristic, and only where plotly declares it. matplotlib and seaborn
  have no equivalent, so those paths are untouched. The dodge check stays ahead of the normalisation
  check, and membership of the normalising set decides rather than key presence -- plotly's own
  "off" value is the empty string.

Closes #338

- **plotly**: Read a plotly.express trendline as a smooth layer
  ([#424](https://github.com/xability/py-maidr/pull/424),
  [`386eb38`](https://github.com/xability/py-maidr/commit/386eb3820600325d76d9d0676471706456061dd2))

px.scatter(..., trendline="ols") appends a second scatter trace carrying the fit. Nothing structural
  separates it from a line the user drew -- same type, same mode, no name, the scatter's own colour
  -- so it was merged into the multi-line layer and read as data, and a reader was told a model's
  prediction was a measurement.

The one thing that separates it is hovertemplate, a display string, and that is the convention this
  package already uses for the same question: SMOOTH_KEYWORDS has matched a matplotlib artist's
  label to find seaborn's regression lines since long before the plotly path existed.

The rule matches the shape plotly generates rather than scanning for a word: the fit's name in bold
  as the whole opening of the template, which all five px trendline modes write and which prose
  about a chart does not. Split before the line branches, because a layer carries one type for every
  series it holds.

Closes the remaining sub-item of #343.

- **plotly**: Read an area chart as an area rather than a line
  ([#411](https://github.com/xability/py-maidr/pull/411),
  [`86e3816`](https://github.com/xability/py-maidr/commit/86e3816159b81f4084fc84d20d0622d9e03e612a))

`px.area` produces a `Scatter` whose only mark of being an area is `stackgroup`, and the adapter had
  no area handling, so every one fell through to `line`. The numbers were already right -- plotly
  keeps each series' own values in `trace.y` and stacks in the browser -- so what was missing is the
  name and the relationship: a reader was not told the bands are filled, that they stack, or what
  the total at each x is.

Adds `maidr/plotly/area.py` with `is_area_trace`, `area_stack_groups`, `area_plot_type` and
  `PlotlyAreaPlot`, plus `PlotType.NORMALIZED_AREA` for `groupnorm`. Area traces are split out of
  `connected_traces` before the line machinery sees them, or an area -- which passes every
  structural test for a connected line -- is emitted twice.

Measured against real Plotly.js in Chromium rather than documentation: a `stackgroup` trace resolves
  to `fill: "tonexty"` with calcdata carrying both `s` (own value) and `y` (running total);
  `scattergl` is excluded because plotly stacks no such thing; and an empty band gets no DOM node,
  so it is dropped from data and selectors together.

Closes #392.

- **plotly**: Read candlestick and OHLC charts
  ([#396](https://github.com/xability/py-maidr/pull/396),
  [`393539c`](https://github.com/xability/py-maidr/commit/393539c3326cffa3000a930bb1a3db962c8c14d1))

`maidr/plotly/` builds its schema in Python and needs its own handling per trace type. It had none
  for `candlestick` or `ohlc`, and neither errored -- both fell through to the factory, which
  returned `None`, so the figure arrived with no layers at all. The HTML rendered and MAIDR loaded;
  what a reader got was an empty shell with nothing to navigate and no error saying why.

Nothing is inferred: both trace types state every number they draw. `trend` and `volatility` are not
  emitted because the core derives both from OHLC and overwrites what it is sent, and no plotly OHLC
  trace carries a volume.

The selectors were measured in a browser rather than reasoned about. Plotly gives a candlestick
  chart a rangeslider by default, holding a full second copy of the plot, so an unscoped selector
  matches every mark twice; a `go.Box` shares `g.boxlayer` and draws its own `path.box`, so the
  position is an index among box-family traces; and `ohlc` draws into `g.ohlclayer` entirely,
  needing a different selector despite being one MAIDR type.

Part of #343; violin and the smooth/trendline naming remain.

- **plotly**: Read stacked and dodged histograms as one layer
  ([#410](https://github.com/xability/py-maidr/pull/410),
  [`879a40b`](https://github.com/xability/py-maidr/commit/879a40bcb40b26829848f9269830267dbe0839b4))

`_extract_plots` collected `bar` traces for merging and left `histogram` traces to the factory, one
  layer each. So every multi-series histogram -- `px.histogram(color=...)` is the ordinary way to
  draw one, and plotly's default barmode stacks -- was announced as several separate distributions,
  with nothing saying the bars stack or that `barnorm` had rescaled them.

The bins were wrong as well, which the issue did not name and which is worse than the missing
  relationship. Plotly bins a group jointly: one grid from every trace's values together. Binned per
  trace, two well-separated samples had the first announced as 13 bins of width 0.2 where the chart
  draws 4 of width 1.

That needed no new arithmetic. Feeding the existing autoBin port the union returns plotly's own
  `size=1, start=-2, end=12` for that figure, so what the issue called inference was transcription
  with the wrong input.

The group's bin spec comes from whichever trace supplies one rather than from the first: with
  `xbins=dict(size=3)` on the second of two traces, plotly resolves it onto both and bins the pair
  at that width.

Merging settles the highlight too. Left separate, every histogram in a subplot emitted the identical
  selector -- `.trace.bars .point > path` matches every bar in the panel -- so each layer
  highlighted its neighbours' bars as well as its own.

A categorical group declines rather than half-describing itself, and `overlay` stays separate layers
  as it does for bars.

Values under `barnorm` stay raw, matching what the merged bar path has emitted since #338 and #393.
  Plotly draws shares and both paths diverge from it identically; that is #409, filed to cover the
  two together.

Measured against `gd.calcdata[i][j]` in Chromium, per series: eight of ten grouped shapes agree
  elementwise, and the two that do not are the `barnorm` pair above.

Closes #394

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>

- **plotly**: Read violin plots ([#397](https://github.com/xability/py-maidr/pull/397),
  [`9ffc510`](https://github.com/xability/py-maidr/commit/9ffc510d76b8476083409320642cffb74e95a6ec))

`_extract_plots` had no branch for the `violin` trace type, so a violin fell through to the factory,
  which returned `None`, and the figure arrived with no layers at all. Nothing errored -- what a
  reader got was an empty shell.

A violin is announced as two layers, matching the matplotlib path and the browser-side plotly
  adapter: `violin_box` summarises the distribution and `violin_kde` is the shape the chart draws.
  Both are built from one list of violins, so row `i` of the box and curve `i` of the KDE cannot
  come to mean different violins.

Plotly runs the kernel density estimate in the browser, so the curve is not in the Python figure and
  has to be recomputed. That is only honest if it reproduces the curve plotly draws, so
  `violin_stats` ports plotly's own rules -- the Silverman bandwidth with its range floor, the soft
  span, the third-of-a-bandwidth sampling, and quartiles by the Hazen rule rather than numpy's
  default -- and the port is pinned against density values captured from plotly's `calcdata` in a
  browser. Measured agreement across eight sample sizes is 5.9e-15 relative at worst, with identical
  point counts.

The three ways a sample can be empty pull against each other, and all three were measured: a
  category whose values are all equal is drawn by plotly and so is announced and takes an index; one
  whose values are all missing is drawn as nothing and takes neither; a hidden trace likewise takes
  no group slot and is not announced at all.

The box layer emits `BoxSelector` objects rather than strings, since the frontend reads the sections
  off an object, with `mean` addressed separately -- `path.mean` inside a box and `path.meanline`
  without one.

Part of #343.

- **pointplot**: Read a seaborn point plot's estimates with their intervals
  ([#352](https://github.com/xability/py-maidr/pull/352),
  [`e3a64c5`](https://github.com/xability/py-maidr/commit/e3a64c514ea32489e792b716d8b76c963cf0b1c8))

A point plot estimates a group mean and draws the interval around it, which is the same quantity
  Axes.errorbar carries, so it emits the same error bar layer.

Seaborn draws no container to read it from -- the estimates are one line and each interval another
  -- so the generic Axes.plot wrapper had been describing a three-group chart as four series, three
  of them cap geometry with NaN coordinates and raw offsets among the category names. This is as
  much a removal as an addition.

The split into estimates and intervals is verified rather than assumed, falling back to describing
  the drawn lines when a future seaborn renders this differently. A group with a single observation
  draws no interval and keeps its place rather than shifting the others'; a chart where none does
  reads as the line of estimates it is. Orientation comes from the string-category machinery seaborn
  leaves on its category axis, and from the intervals themselves under native_scale.

A hue splits the chart into series the error bar layer cannot yet name, so it reads as the
  multi-line chart it is -- with each series now named after its hue level and the interval
  polylines no longer travelling as series of their own.

- **scatter**: Name the category a point sits in
  ([#445](https://github.com/xability/py-maidr/pull/445),
  [`64a1ef9`](https://github.com/xability/py-maidr/commit/64a1ef95cd3cf353f14bbd32ece65c71d14888e4))

#439 fixed the position: a strip plot's jitter and a swarm plot's packing are chosen by the
  renderer, and the offset -- not the observation -- was what `get_offsets()` returned and what was
  announced. Snapping to the tick stopped a rendering artefact being reported as a measurement.

It could not fix the name. `ScatterPoint.x` was typed `number`, and the core subtracts x values to
  sort, to index columns and to resolve a highlight, so a string there gives an unstable sort and a
  broken index rather than an announcement. A reader still heard "g is 0" where the chart says "a".

xability/maidr#927 added `xLabel` / `yLabel` for exactly this, so the name now travels alongside the
  position rather than in place of it -- which is also what the chart is: a category at a slot.

The map was already being built and then thrown away down to its keys: `_category_tick_labels`
  returns {tick coordinate: name}, and the snapping only ever needed the coordinates. Naming the
  point costs one lookup in a dict that was already in hand.

Both axes are asked, because either can be the categorical one. A numeric axis is untouched:
  `_category_tick_labels` is empty unless matplotlib mapped strings onto the axis, so a measurement
  cannot be renamed after whichever tick it falls nearest.

Closes #439

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>

- **shiny**: Rebuild render_maidr on Shiny's Renderer contract
  ([#452](https://github.com/xability/py-maidr/pull/452),
  [`2197548`](https://github.com/xability/py-maidr/commit/2197548420ef99db5891cda5dc9be3875bba4846))

`render_maidr` subclassed `shiny.render.ui` and overrode `render()` with a copy of the base
  implementation. Shiny's documented extension point is `Renderer`; subclassing a concrete renderer
  inherits its value type, so the class was typed `Renderer[TagChild]` and a checker rejected this
  repository's own example, whose render function returns an `Axes`. There was no UI function to
  pair it with, no options, no declared dependency on `shiny`, and no test had ever imported the
  file.

`output_maidr()` is now the container and `auto_output_ui()` returns it, so Shiny Express places it
  too. `render()` rather than `transform()` is overridden, matching `shiny.render.plot`, which does
  the same because it too needs to bracket the value function -- here to close the pyplot figures a
  render opened, since a render function runs once per reactive flush and 25 flushes left 25 figures
  open. Only figures that were not open beforehand are closed, so a figure the app builds lazily and
  caches keeps maidr's record of it and does not degrade to a static image. `width`, `height` and
  `use_cdn` are new; `use_cdn` in particular, since the only previous lever was the process-wide
  `maidr.set_use_cdn()` that the docs already warn against for multi-session apps.

Two defects found while doing it:

`Environment.is_shiny()` asked whether `import shiny` succeeds, and the comparison it made is true
  for any successful import. Six call sites gate on it, so every process that merely had Shiny
  installed took the Shiny path -- a plain script got a 28 KB iframe carrying no dependency instead
  of a 15 KB div carrying one, and a Streamlit app got a maidr iframe nested inside Streamlit's own.
  It now asks `get_current_session()`, mirroring `is_flask()`.

An iframed `use_cdn=False` render shipped no source for `maidr.js` at all, in both Shiny and Flask:
  `Tag.get_html_string()` drops `HTMLDependency` children, and the other branch reads a global that
  only `init_notebook()` populates. The chart arrived as a picture -- no sonification, no braille,
  no keyboard navigation, and nothing to say why. The bundle now travels inline, read once per
  process, falling back to the CDN with a warning if it cannot be read.

Backwards compatible: `from maidr.widget.shiny import render_maidr` is unchanged, both decorator
  spellings work, and `ui.output_ui("id")` still pairs with it.

Follow-ups filed as #453, #454, #455, #456 and #457.

- **streamlit**: Add a first-class Streamlit integration
  ([#459](https://github.com/xability/py-maidr/pull/459),
  [`1087b7a`](https://github.com/xability/py-maidr/commit/1087b7aca07f223940bf3d6e77bf616e0caaf833))

py-maidr had no Streamlit code at all. The only guidance was the example app, which hand-rolled
  `components.html(maidr.render(plot).get_html_string(), scrolling=True, height=fig_height * 100,
  ...)` -- and every part of that line is now wrong, one part always was.

`components.v1.html` is deprecated with a removal date that has passed. Its height had to be guessed
  from the figure size, because its own default renders as 150 px and crops the chart. It sets no
  tab order. And `get_html_string()` drops `HTMLDependency` children, so `use_cdn=False` produced a
  chart with no MAIDR runtime behind it at all: the same silent failure #452 fixed on the Shiny
  path, by the same mechanism.

`render_maidr()` answers all four. It prefers `st.iframe` and falls back to `components.v1.html`,
  where a symbolic size becomes a concrete one rather than cropping, and where `tab_index` is
  forwarded when the installed function accepts it -- it reached `components.v1.html` eleven
  releases before `st.iframe` existed, so "no st.iframe" does not mean "no tab_index".
  `height="content"` lets Streamlit measure the chart, which is what keeps maidr's braille and text
  panels visible when they open. `use_cdn=False` inlines the bundle, reusing the helper added for
  Shiny.

`maidr_html()` is separate because the useful lever against Streamlit's rerun-everything model is
  caching the *string*, and that needs a string-returning entry point to cache.

`_warn_if_no_runtime` checks the emitted HTML actually carries a source for maidr.js, naming the
  maidr package specifically -- every Plotly chart carries a `cdn.plot.ly` tag of its own, and
  vouching for a runtime on the strength of an unrelated one is the failure this exists to catch. A
  chart with no runtime still looks right, being the SVG unchanged, while being silently unusable,
  and that is invisible to a sighted developer testing their own app.

The chart stays inside an iframe deliberately, and the module says why: Streamlit binds `r`, `c` and
  `esc` at the document level, exempting only form fields, and maidr binds all three. The iframe is
  what keeps maidr's keyboard interface intact, which is also why components v2 is not the target.

`streamlit` is an optional extra, imported lazily so `maidr_html` works without it, and reporting a
  missing package differently from a broken one via the `_extras` helper now shared with the Shiny
  integration.

Follow-ups filed as #460 and #461.

### Refactoring

- Drop the unreachable pyplot guard in `set_backend`
  ([#478](https://github.com/xability/py-maidr/pull/478),
  [`14faf9c`](https://github.com/xability/py-maidr/commit/14faf9ce09868c7e77b216a128cffa9dccb75a9c))

`set_backend()` is reachable only after `import maidr` succeeded, and `import maidr` loads pyplot on
  the way through -- the module docstring at the top of this file exists to work around exactly
  that. So the `import matplotlib.pyplot` here is a `sys.modules` lookup and cannot raise
  `ImportError`.

Were the branch ever taken it would fail badly for public API: `return` is `set_backend`'s ordinary
  return, so a caller would get `None` back having changed no backend, told only at `DEBUG`.
  `_activate_backend` already imports pyplot unguarded a few lines above.

Closes #477

- Drop the useless matplotlib guard in `_activate_backend`
  ([#476](https://github.com/xability/py-maidr/pull/476),
  [`8e7836b`](https://github.com/xability/py-maidr/commit/8e7836b01eb618ff0466739a7bf91147d4823db3))

The `except ImportError` is reachable, on the first of the two calls (`maidr/__init__.py:192`,
  before `from .api import` at 194) -- but it cannot do what it says. It returns, and two lines
  later `maidr/api.py:8` imports `matplotlib.axes` at module scope and `import maidr` fails anyway.
  All it buys is a traceback pointing at `api.py` instead of at the line that actually wanted
  matplotlib.

The cost is the comment rather than the branch: it tells the next reader that maidr degrades
  gracefully without matplotlib, which no part of this codebase does, and which the package metadata
  has contradicted since #474.

Closes #475

- **plotly**: Read the normalising barnorm values from one place
  ([#416](https://github.com/xability/py-maidr/pull/416),
  [`837bb36`](https://github.com/xability/py-maidr/commit/837bb360ca3e7c61192e75602bb7575ea05a7b53))

`plotly_maidr` and `barnorm` each held their own copy of the two values `layout.barnorm` takes when
  plotly rescales a stack, under the same name in two modules -- one deciding the layer's type, the
  other whether its values were actually rescaled.

They agreed, so nothing was broken. But editing either without the other is how #409 comes back: a
  `barnorm` one recognised and the other did not would type the layer `stacked_normalized_bar` while
  leaving its values the raw counts, contradicting each other silently. The classification now asks
  `barnorm_scale`, so there is one list, and a test asserts the equivalence over every value plotly
  will accept rather than over a remembered pair.

Also skips building the `(position, value)` tuples on the un-normalised path, and gives the
  dodged-histogram case its own class beside the bar one so the parity between the two paths is
  visible from the structure.

### Testing

- **bundle**: Stand in for an unbuildable trace with a name no release can ship
  ([#365](https://github.com/xability/py-maidr/pull/365),
  [`73b231a`](https://github.com/xability/py-maidr/commit/73b231ada4a2d5644c623ecffe771ca0ead26e8f))

`test_bundle_capability.py` used "treemap" and "sankey" as its examples of a type the bundle cannot
  build. They were real types the bundle genuinely lacked when the file was written. maidr 4.2.0
  shipped both, `a734020` updated the bundle, and six cases went from testing the warning to
  asserting that a supported type warns.

They failed, which is not the same as being caught. The same release could as easily have made them
  pass -- the file would have stayed green while testing nothing, which is one version of the
  failure mode the check itself exists to prevent.

Nothing about the check depends on the name being real: it is a set difference between the types a
  schema carries and the types the bundle quotes, so an absent name is an absent name. The stand-ins
  are now spelled so that no release can turn them into types it can build, and
  `test_the_stand_ins_are_really_absent` asserts they stay outside `bundle_trace_types()` -- with
  "bar" asserted inside it, so an empty set cannot satisfy that vacuously.

- **heatmap**: Pin hist2d, which reads only by accident
  ([#348](https://github.com/xability/py-maidr/pull/348),
  [`b74a51e`](https://github.com/xability/py-maidr/commit/b74a51e1ba51bc59e66da669f93e62ae02fd07eb))

`Axes.hist2d` draws through `Axes.pcolormesh`, so patching the latter made a rectangular 2D
  histogram register as a heatmap without anyone deciding it should. That works, and would break
  silently: narrowing the heatmap patch or adding a nested-draw guard would leave a chart that used
  to be navigable simply not, with no error anywhere.

Pins the layer type, the single registration through the recursion guard, the mesh tagging, and the
  transposition -- `hist2d` returns counts indexed [x, y] while the mesh it draws is [y, x], so a
  grid the wrong way round would still navigate and merely describe a different chart.

Also pins `hexbin` and bivariate `kdeplot` as NOT registering, so the boundary sits in one place
  rather than being found per bug report. Both are written to fail the day core support lands, which
  is the reminder to rewrite them.

- **streamlit**: Cover the `components.v1.html` fallback end to end
  ([#479](https://github.com/xability/py-maidr/pull/479),
  [`93266d4`](https://github.com/xability/py-maidr/commit/93266d4577596430d15a275babc2d92b700842a0))

The one real-Streamlit test skipped itself when `st.iframe` was absent, on the grounds that "the
  fallback covers it" -- but nothing did. The fallback had stub coverage only, and it is the path
  every user on a pre-1.56 Streamlit takes, including CI's own Python 3.9 job, which pins streamlit
  1.50.

Both APIs marshal into the same `IFrame` proto, so one set of assertions covers both and the skip is
  unnecessary. Verified on Python 3.9 with streamlit 1.50 (the fallback) and Python 3.11 with 1.61.1
  (`st.iframe`).

Also asserts that `tab_index=None` reaches the frame absent rather than as 0, which are different
  behaviours the default depends on telling apart.


## v1.20.0 (2026-08-10)

### Bug Fixes

- **bar**: Bind a hued seaborn bar plot as a grouped layer
  ([#317](https://github.com/xability/py-maidr/pull/317),
  [`13002c3`](https://github.com/xability/py-maidr/commit/13002c3e377d0da9a05884d6b738482725b10763))

Whether a hue splits a bar layer into groups is seaborn's own decision, taken from its auto dodge
  and the data, and it never reaches matplotlib. Classifying from the seaborn arguments only caught
  the calls that asked to dodge by hand, so every other hued bar plot was bound as a plain bar
  layer, where the grouped bars outnumber the tick labels and extraction fails.

Classify the layer from the bars seaborn drew instead: one container per hue level, each holding one
  bar per category. A hue that repeats the category variable draws one single-bar container per
  category and stays a plain bar layer, which is what it is.

The grouped extractor read every bar's height against the x tick labels, so a horizontal grouped
  layer reported bar thicknesses against the wrong axis. Read the magnitude off the dimension the
  bars grow along and the labels off the axis they sit on, and report the orientation in the schema,
  as bar, box and violin layers do.

- **patch**: Draw every patched plot type through the scoped warning filter
  ([#330](https://github.com/xability/py-maidr/pull/330),
  [`c73d2c1`](https://github.com/xability/py-maidr/commit/c73d2c116677e842c732ff0c4add4ed1869e7045))

Only `common` and the pie patch drew through `_draw_quietly`. Nine modules called `wrapped()`
  directly and had been inheriting the old process-wide filter by accident, so whether a violin plot
  was quiet depended on whether a bar chart had been drawn first in that process. #327 scoped the
  filter to its call, which removed the accident and left those nine consistently unsuppressed
  instead.

18 call sites across the nine modules. Return values and FigureManager registration are untouched;
  only which call is wrapped changed.

The warning-scope tests grew from 5 kinds to 21, one or more per patch module, so a module left
  calling `wrapped()` directly fails on its own row. The `plot_boxes` wrap needed its own test: the
  shared injection fires on the first artist added, which for a box draw is inside the
  separately-suppressed `Axes.bxp`, so a plain catplot row passes either way.

Closes #328.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>

- **patch**: Read box and violin orientation the way matplotlib does
  ([#301](https://github.com/xability/py-maidr/pull/301),
  [`fcc52f4`](https://github.com/xability/py-maidr/commit/fcc52f40ef51d64603fa5f2d0cf0bf9a1f367614))

- **patch**: Serialise the warning suppression so concurrent draws cannot leak it
  ([#331](https://github.com/xability/py-maidr/pull/331),
  [`bc70987`](https://github.com/xability/py-maidr/commit/bc7098718f8a7c7fc196ea3a080061161ecbcf09))

`catch_warnings` saves the global filter list on entry and restores it on exit, and two threads
  drawing at once do not merely race on that -- they corrupt it, because the restores nest wrongly.
  B puts back a snapshot taken while A was suppressing, so a process-wide `ignore` outlives every
  draw: the leak #327 removed, reintroduced under concurrency and permanently.

Measured before writing the fix. Eight threads drawing sixty times each leave one ('ignore', None,
  Warning, None, 0) behind, and a warning raised long afterwards -- nowhere near a figure -- is
  swallowed. The issue described this as a narrow race; the window is neither narrow nor transient.

An RLock around the suppression makes the save and restore pair up. Reentrant because patches nest:
  `regplot.patched_plot` wraps `Axes.plot`, which `lineplot.line` wraps too, so one draw enters
  twice on one thread.

Concurrent draws now serialise. Shiny renders on one asyncio loop so the caller that motivated this
  sees no contention, and matplotlib's own guidance is that a figure belongs to one thread. Python
  3.14's context-aware filters would remove the need for the lock.

Closes #329.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>

- **plotly**: Decode typed arrays, and scope the patch warning filter to its call
  ([#327](https://github.com/xability/py-maidr/pull/327),
  [`d72822b`](https://github.com/xability/py-maidr/commit/d72822bfd350b47b99e70f38f4d8d32d013a4659))

Closes #325. Refs #326.

Since plotly 6.x a numeric column is exported as a base64 typed-array spec rather than a list, and
  every extractor but pie iterated it literally — walking the spec's two keys and emitting "dtype"
  and "bdata" as the data. The issue named three extractors; auditing all of them with
  plotly.express figures found every one affected, in three ways: bar, line, multiline, scatter,
  grouped_bar and step emitted the key names; box and multibox raised; histogram fell to its
  categorical path; heatmap emitted the letters of the key names. The chart draws correctly in each
  case, so only the accessible layer is wrong — confidently rather than visibly.

Pie's decoder moves to a shared `as_list` every extractor now reads through. A spec that will not
  decode logs and returns empty: silently empty is better than silently garbled, but it is still
  silent, and silence is the fault this decoder exists to fix.

Two things the issue did not name. Heatmap's 2-D spec carries its own extents, so the decode
  reshapes rather than flattening. And `_trace_point_count` was miscounting: a spec's length is 2
  whatever it holds, so a 30-point numpy-backed scatter counted as 2 and was classified
  `lines+markers` where the same data as a list was `lines`.

An unreadable array must not cost more than itself, so the boxplot extractors now bound their
  precomputed loop by the shortest statistic and drop a box with no samples rather than letting
  `np.percentile` raise — either would have taken the whole figure down, including the layers that
  read perfectly well.

Warning suppression is now scoped to the wrapped call. The process-wide filter it replaces was still
  installed at render time, so one plot muted every later `warnings.warn` in the process — MAIDR's
  own diagnostics among them. Nine patch modules that never routed through the helper are tracked in
  #328, and the scoped filter's thread safety in #329.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>

- **plotly**: Resolve an absent mode the way plotly does before classifying
  ([#313](https://github.com/xability/py-maidr/pull/313),
  [`8c3f5ab`](https://github.com/xability/py-maidr/commit/8c3f5ab6d41abece553ecbb4277870d78f4ec013))

Figure.to_dict() omits mode unless the author set one, and the classifier read that absence as
  markers-only. So a line chart written as add_scatter(x=..., y=...) was exported as SCATTER and
  announced as loose points while plotly drew a connected line — the connectivity of the data lost
  for a screen-reader user.

An absent mode is not "no drawing mode", it is "whatever plotly's default resolves to". plotly
  documents that on scatter.mode: "If there are less than 20 points and the trace is not stacked
  then the default is 'lines+markers'. Otherwise, 'lines'." default_mode() reproduces both halves,
  and is_connected_line_trace() stands it in before applying the existing rule.

Mirroring plotly rather than treating every absent mode as lines keeps one classification rule
  instead of two: a mode-less six-point trace and an explicit "lines+markers" six-point trace are
  drawn identically by plotly and are now classified identically here.

Verified that scattergl shares the same default by reading plotly.js and by reading back plotly's
  own resolved gd._fullData[i].mode in Chromium.

Closes #308

- **plotly**: Stop claiming a highlight for canvas-painted traces
  ([#314](https://github.com/xability/py-maidr/pull/314),
  [`7550aff`](https://github.com/xability/py-maidr/commit/7550aff5c9ae6ed3bc66af63a863ef32d066423c))

A scattergl trace is painted into a shared <canvas>, not drawn as SVG, so the path.js-line and
  .point selectors built for it resolved to zero elements. The layer sonified, brailled and
  described correctly and the highlight simply never appeared — with nothing in the output to say
  why. WebGL layers now emit no selector at all, which says the same thing honestly.

Upstream leaves no alternative: maidr's highlight service rejects a non-SVGElement outright, and
  canvas-backed libraries are served instead by the onNavigate callback, which grammar.ts documents
  as "not serializable as JSON" — unreachable from an exported figure by construction rather than
  merely unused.

Rendering plotly's own bundle in Chromium turned up a second half to the defect. A gl trace never
  enters the SVG scatterlayer at all: with one declared before an svg trace, the scatterlayer holds
  exactly one child — the svg trace, at nth-child(1) — and nth-child(2) matches nothing. Counting gl
  traces in the position index therefore pushed every svg sibling one place along, so a single
  scattergl trace silently disabled highlighting for the ordinary traces beside it.

Positions are now numbered per renderer, so an svg trace keeps its real scatterlayer index while a
  gl trace gets one that is well-formed but never rendered. Lines and steps likewise group within
  one renderer rather than across two, since a layer's selector list is positional and
  all-or-nothing and so cannot describe a mixed layer.

Verified in the browser after the fix: the emitted selector for an svg line sharing a subplot with a
  gl line matches exactly one element.

Closes #309

- **smooth**: Keep a regression line navigable point by point
  ([#319](https://github.com/xability/py-maidr/pull/319),
  [`8b190d0`](https://github.com/xability/py-maidr/commit/8b190d0dc32afe29c8919ffa0642ae9ca85fc8b9))

The smooth layer thinned its fitted line with Ramer-Douglas-Peucker, which preserves shape by
  dropping vertices that sit on the chord between their neighbours. A seaborn regplot fit is a
  straight line sampled on a 100-point grid, so every interior vertex is exactly collinear and the
  whole line collapsed to its two endpoints: pressing Page Up onto the layer left two navigable
  points and one arrow press ran out of data.

The same thinning warped the KDE curve overlaid on a histogram, clustering its 30 surviving vertices
  around the bends until the step along x varied by 16x. Since the trace is navigated and
  auto-played one vertex at a time at a fixed rate, that stretches the flat parts of the trend and
  crams the steep ones.

Thin the curve by resampling it evenly along x instead, so a straight fit keeps the full point
  budget and every smooth layer paces its sweep the same way. Sampling by vertex index alone would
  have left a lowess fit clustered, since it lands on the observed x values rather than a uniform
  grid.

Fixes #318

- **smooth**: Pace a smooth layer by drawn distance, not data distance
  ([#320](https://github.com/xability/py-maidr/pull/320),
  [`ffa24cf`](https://github.com/xability/py-maidr/commit/ffa24cf3f96ba5da8397f35a28510815537e8c93))

Points evenly spaced along x are evenly spaced on screen only while the axis is linear. A log x-axis
  stretched the same points into a 102:1 spread across the plot, so auto-play swept the picture
  unevenly even though the announced x values stepped uniformly. A smooth trace is meant to let a
  blind reader follow the trend a sighted reader sees moving left to right, so drawn distance is
  what has to stay even.

Thin in scale space and map back. What remains between scale space and the display is an affine map,
  which cannot change distance ratios, so the answer holds under any figure layout. A linear axis is
  untouched, its scale transform being the exact identity.

Return the vertices unchanged when the curve already fits the budget, since the scale round trip is
  not bit-exact and would otherwise shift a short fit off the line it used to sit on. Thin in data
  space when a scale cannot represent the line at all.

Guard that last case three ways, because no single check sees every refusal: a scale answering with
  infinity or NaN, a clipping scale's sentinel that reads as an ordinary coordinate, and a value
  that maps somewhere it cannot come back from. Two of them catch cases the round trip reports as
  perfectly fine -- a log scale's sentinel inverts back to zero, and logit's infinity inverts back
  to one -- which left a fit touching zero dragging 29 of its 30 points off the canvas.

Follows #318 and #319.

### Continuous Integration

- Harden Claude workflows (skip Dependabot PRs, gate @claude)
  ([#300](https://github.com/xability/py-maidr/pull/300),
  [`a32c216`](https://github.com/xability/py-maidr/commit/a32c216b51437f05de2f5e0cb2eff0af96d33972))

- Let the Claude action post under its own identity again
  ([#302](https://github.com/xability/py-maidr/pull/302),
  [`968c19a`](https://github.com/xability/py-maidr/commit/968c19a3098a0b595f8fc2140cb09d1578c65b86))

- Release weekly like upstream maidr, and keep chore out of the changelog
  ([#306](https://github.com/xability/py-maidr/pull/306),
  [`a8104f5`](https://github.com/xability/py-maidr/commit/a8104f55398df5bbc18a912506d5f870930898b7))

### Features

- **bar**: Support horizontal bar and histogram layers
  ([#307](https://github.com/xability/py-maidr/pull/307),
  [`d4af984`](https://github.com/xability/py-maidr/commit/d4af984097c44bfacc6fcaa1849015c3fb7079e7))

Bar labels were always read off the x axis, so a horizontal layer never matched its patch count and
  raised while extracting. A horizontal histogram did not crash but took its counts from the bar's
  height, which is the bin thickness rather than the count.

Read the orientation matplotlib records on the container and extract along it, emitting the mirror
  layout the renderer reads, and report orientation in the schema so the layer announces as
  horizontal.

- **cdn**: Resolve @latest to a concrete version and report bundle drift
  ([#291](https://github.com/xability/py-maidr/pull/291),
  [`d865b4e`](https://github.com/xability/py-maidr/commit/d865b4e81719f3ddbe1f87f7904cf37f04e31c3f))

Fixes #290.

Emitted CDN URLs named the mutable `maidr@latest` dist-tag, which jsDelivr serves with a seven-day
  cache lifetime, so a browser kept replaying a week-old `maidr.js` after every release. The
  published version is now resolved once per process and spliced into the URL, which changes the
  cache key on each release and lets the browser cache each build permanently. The lookup is bounded
  by a total budget shared across both resolver endpoints, caches success and failure alike,
  validates every version before it reaches a URL, and degrades to `@latest` rather than raising.
  `use_cdn=False` never touches the network; a pin, an env var, or the `latest` tag opts out
  entirely.

Resolving the published version also makes the bundled copy's age observable, so `bundle_status()`
  reports drift, a one-shot warning surfaces it on the paths where the bundle can actually run, and
  a scheduled workflow fails when the bundle falls far enough behind. That workflow runs on a
  schedule and on dispatch; it is not called at release time.

The branch also carries the upstream stylesheet split. maidr 3.75.1 made `dist/maidr.css` a 406-byte
  placeholder and moved KaTeX to `dist/maidr-math.css`, which `maidr.js` fetches at runtime relative
  to its own URL. The bundle script fetched two filenames given to it years ago, so the next release
  would have shipped the placeholder and no maths stylesheet, leaving LaTeX in AI chat responses
  unstyled for anyone who opened the chat. The script now takes `maidr-math.css`, both bundle
  workflows stage `maidr/static` wholesale rather than a filename list that can go stale, and the
  bundle moves 3.73.0 to 3.75.1 — about 1 MB smaller in the wheel. No render path links a stylesheet
  any more: where maidr.js loads by URL the runtime finds the file itself, and where it is evaluated
  inline in a srcdoc iframe the rules travel as a source string and are marked so the runtime does
  not report them missing. Pinning the CDN below 3.75.1 warns once, since that is the one
  configuration the removal regresses.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>

- **pie**: Support matplotlib and plotly pie charts
  ([#322](https://github.com/xability/py-maidr/pull/322),
  [`810c9ca`](https://github.com/xability/py-maidr/commit/810c9ca09ce0ab9f6d5060053fdb875ef0bc7f87))

Adds `PlotType.PIE`, a `PiePlot` extractor, a wrapt patch on `Axes.pie`, and plotly `go.Pie`/donut
  support, emitting the flat pie wire format the renderer expects.

Values come from the patched call's arguments rather than from the drawn wedges. `Axes.pie`
  normalises its input when the values sum to more than one, and each `Wedge` keeps only its angles
  — so recovering magnitudes from the geometry would report 0.3/0.5/0.2 for a caller who passed
  30/50/20, and lose precision doing it.

Labels resolve the way matplotlib does: the `labels` argument, then the wedge's own label, then the
  slice index.

A `go.Pie` is a domain trace with no axis pair, so its grid cell comes from its own `domain`
  rectangle rather than from the default axis group every pie would otherwise share — which had
  collapsed a `make_subplots` grid of pies into a single cell. Its subplot title is anchored the
  same way. Only domain traces maidr renders are folded into that grid, so a figure containing no
  pie is placed exactly as before.

An empty pie emits an empty layer rather than raising, so a working subplot beside it still renders.
  Slice order mirrors plotly's own `pie/calc.js` — merge, filter, sort, and the `hiddenlabels` rule
  that compares against the stringified label — because the selector is positional and the first
  divergence lands every later slice on the wrong wedge.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>

- **plotly**: Bind a plotly step chart as a step trace, not a line
  ([#303](https://github.com/xability/py-maidr/pull/303),
  [`3471a0d`](https://github.com/xability/py-maidr/commit/3471a0ddfd4f93ca3d4c632c8904df1a31857b2e))

- **step**: Add step plot support with ordinal level names
  ([#299](https://github.com/xability/py-maidr/pull/299),
  [`72c1a8a`](https://github.com/xability/py-maidr/commit/72c1a8adfdd76ac19a2d21d11a4ba4dba2070c4b))

### Refactoring

- **plotly**: Require a selector position instead of guessing one
  ([#315](https://github.com/xability/py-maidr/pull/315),
  [`b126419`](https://github.com/xability/py-maidr/commit/b12641913b04ce04813437d1943ab29448fa2214))

The three line-family classes disagreed about what to do when nobody told them where their traces
  sit in the subplot, and the two fallbacks failed in different ways. PlotlyLinePlot fell back to an
  unscoped selector, which over-matches — a step trace renders as path.js-line too. PlotlyStepPlot
  and PlotlyMultiLinePlot fell back to leading order, which is worse because it is silent:
  constructed off-position they emitted nth-child(1), nth-child(2), ... pointing at whichever
  elements happened to sit there, with no error and the wrong element highlighted.

Both are removed and the parameter is required, so a missing position is a TypeError at the call
  site rather than a wrong element at runtime. _extract_plots already passed positions
  unconditionally, so no production path changes behaviour.

A shared _validate_scatter_positions additionally rejects a list that is the wrong length, negative,
  duplicated or not a list of int — the same silent failure reached by supplying a wrong list rather
  than none. Lists are stored by value, so a caller mutating one afterwards cannot change an
  already-validated layer's selectors.

PlotlyPlotFactory is the one caller that genuinely cannot know a position, so it passes 0
  explicitly, with the cost of that assumption recorded at the call site.

Closes #311

- **smooth**: Move resample_curve out of the RDP module
  ([#321](https://github.com/xability/py-maidr/pull/321),
  [`4a107e9`](https://github.com/xability/py-maidr/commit/4a107e928d6c17e26b747421d8a329f7410f5618))

rdp_utils.py mirrors r-maidr's R/rdp_utils.R, which holds the RDP trio and nothing else. Adding
  resample_curve here left the name describing three of its four functions and put the two ports out
  of step.

Renaming the module, as review suggested, would have widened that gap: the R side keeps the name
  while the Python side loses it. Move the odd function out instead, into resample_utils.py, so
  rdp_utils.py is again exactly what its name and its mirror say. Each module now points at the
  other for the objective it does not serve.

The move also surfaced a reference that had been resolving only by accident: resample_curve pointed
  at :func:`simplify_curve` unqualified, which worked while the two shared a module and would have
  rendered as inert text once they did not.

No behaviour change. Follows #318, #319 and #320.

### Testing

- **plotly**: Cover steps beside bar/box traces and across a subplot grid
  ([#312](https://github.com/xability/py-maidr/pull/312),
  [`3875431`](https://github.com/xability/py-maidr/commit/3875431f54c015d507e70d475051a13014f333e2))

Step selector indexing was covered only on a single subplot holding nothing but scatter-family
  traces. A bar or box on the same subplot, and steps across a make_subplots grid, were untested —
  and both fail silently, since a wrong nth-child index does not raise, it highlights somebody
  else's element.

Each assertion was checked against a deliberately broken build rather than trusted for passing.

Closes #310


## v1.19.1 (2026-07-21)

### Bug Fixes

- Recover shared y-axis label from sibling axes and figure text
  ([#287](https://github.com/xability/py-maidr/pull/287),
  [`954926a`](https://github.com/xability/py-maidr/commit/954926a4671a9aa0a3c37956c528269e018fded5))


## v1.19.0 (2026-07-13)

### Continuous Integration

- Bundle upstream maidr.js at release time, attribute to xabilitylab
  ([#286](https://github.com/xability/py-maidr/pull/286),
  [`21c33ac`](https://github.com/xability/py-maidr/commit/21c33aca9b71988a4a0e700f6eef109b2a9e3920))

### Features

- Emit figure-wide title and axes labels in the MAIDR schema
  ([#285](https://github.com/xability/py-maidr/pull/285),
  [`59b1c7c`](https://github.com/xability/py-maidr/commit/59b1c7c26240e09b4449eb198e43d5f565dea84e))


## v1.18.0 (2026-05-06)

### Features

- Add Altair charting library support ([#268](https://github.com/xability/py-maidr/pull/268),
  [`984e637`](https://github.com/xability/py-maidr/commit/984e6374df9f5e56fc5a372bf2d0046a9d42719d))

Co-authored-by: Claude Opus 4.6 <noreply@anthropic.com>

Co-authored-by: nk46-cloud <nk46@illinois.edu>


## v1.17.3 (2026-04-28)

### Bug Fixes

- Correct x-label for line plots ([#284](https://github.com/xability/py-maidr/pull/284),
  [`281d411`](https://github.com/xability/py-maidr/commit/281d411ffefa91603082bcff7bc2780b8eebc47a))

Co-authored-by: nk1408 <196366666+nk1408@users.noreply.github.com>


## v1.17.2 (2026-04-23)

### Bug Fixes

- Refactor axes in maidr payload ([#283](https://github.com/xability/py-maidr/pull/283),
  [`12c8316`](https://github.com/xability/py-maidr/commit/12c83169de75948f25c06afbf60e45dbaaef52db))


## v1.17.1 (2026-04-21)

### Bug Fixes

- Change fill to z label and maidr asset bundling
  ([#282](https://github.com/xability/py-maidr/pull/282),
  [`15cc54b`](https://github.com/xability/py-maidr/commit/15cc54b530d0a951a1ecdf37c928587c07674fbf))


## v1.17.0 (2026-04-03)

### Features

- Fix iframe resizing bug and grid nav mode in plotly
  ([#281](https://github.com/xability/py-maidr/pull/281),
  [`0172654`](https://github.com/xability/py-maidr/commit/0172654337905972a254a07de6d88080e91e29f8))


## v1.16.0 (2026-04-01)

### Features

- Support grid nav in scatter plots ([#278](https://github.com/xability/py-maidr/pull/278),
  [`ed3f482`](https://github.com/xability/py-maidr/commit/ed3f48246b2f27fe263b06d94e958bfb0059b401))


## v1.15.0 (2026-03-30)

### Features

- Support maidr as a matplotlib backend ([#280](https://github.com/xability/py-maidr/pull/280),
  [`0a8e8d1`](https://github.com/xability/py-maidr/commit/0a8e8d171817fc2c8a545b0b7e169f3fc03094a3))


## v1.14.0 (2026-03-25)

### Documentation

- Add Google Analytics and MS Clarity tracking
  ([#275](https://github.com/xability/py-maidr/pull/275),
  [`50621bc`](https://github.com/xability/py-maidr/commit/50621bc9dd410e09e89680d26488edc475836df2))

Co-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

- Add SEO and GEO improvements ([#277](https://github.com/xability/py-maidr/pull/277),
  [`6830a11`](https://github.com/xability/py-maidr/commit/6830a1172e4181f31566846fc5fee8397be6e9b4))

Co-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

- Address analytics PR review feedback ([#276](https://github.com/xability/py-maidr/pull/276),
  [`5fb4561`](https://github.com/xability/py-maidr/commit/5fb45617f2ecde8ea47c63e91e46cc26ef89de59))

Co-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

### Features

- Add maidr as a matplotlib backend ([#263](https://github.com/xability/py-maidr/pull/263),
  [`816c6ed`](https://github.com/xability/py-maidr/commit/816c6ed259af228454d4c30a29fe0079773eba1f))

Co-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>


## v1.13.0 (2026-03-13)

### Features

- Support plotly ([#264](https://github.com/xability/py-maidr/pull/264),
  [`227361d`](https://github.com/xability/py-maidr/commit/227361d0d884d6742dc3bd2c8843df3cd126c840))

Co-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

Co-authored-by: nk46-cloud <nk46@illinois.edu>


## v1.12.2 (2026-03-06)

### Bug Fixes

- Restore jsDelivr CDN URL for maidr.js
  ([`3c5a3c0`](https://github.com/xability/py-maidr/commit/3c5a3c0dd5e5c6f54cb8bcafbee367b3d6bcceaa))


## v1.12.1 (2026-03-05)

### Bug Fixes

- Support horizontal orientation violin plot ([#274](https://github.com/xability/py-maidr/pull/274),
  [`2140c8d`](https://github.com/xability/py-maidr/commit/2140c8d8df10ccec2a30ad1352ec3c0237e07751))

### Continuous Integration

- Add github_token to bypass OIDC in claude review workflow
  ([`f22e318`](https://github.com/xability/py-maidr/commit/f22e3187521ae2dd84cfe2705d65c3db46804cee))

- Update claude review to pull_request_target with write permissions
  ([`a35b592`](https://github.com/xability/py-maidr/commit/a35b592593991147b6a6c95b054e272e4eee83e9))


## v1.12.0 (2026-03-04)

### Bug Fixes

- Install uv in semantic-release build command
  ([`dea1114`](https://github.com/xability/py-maidr/commit/dea1114663de2b04f7e5dbd86f6c6d8816814245))

### Continuous Integration

- Add claude code reviews ([#272](https://github.com/xability/py-maidr/pull/272),
  [`a5e9f66`](https://github.com/xability/py-maidr/commit/a5e9f66ee3a1ef0b18fd4fb8a45a42905f7a6d9a))

- Add devcontainer and copilot-setup-steps configuration
  ([#271](https://github.com/xability/py-maidr/pull/271),
  [`3cd75d3`](https://github.com/xability/py-maidr/commit/3cd75d3d1e43ef9054cfd717e0e9ccd1a5d200ba))

Co-authored-by: Claude Opus 4.6 <noreply@anthropic.com>

- Install claude github app ([#273](https://github.com/xability/py-maidr/pull/273),
  [`5b38610`](https://github.com/xability/py-maidr/commit/5b38610c3c646b05f53c5e1ed0b61a3b4ec29755))

- Sync uv.lock during semantic-release version bump
  ([#270](https://github.com/xability/py-maidr/pull/270),
  [`716b658`](https://github.com/xability/py-maidr/commit/716b658a1b880c00948877414038cb2c0b203ce5))

Co-authored-by: Claude Opus 4.6 <noreply@anthropic.com>

### Features

- Implement violin plot support with dual-layer registration
  ([#259](https://github.com/xability/py-maidr/pull/259),
  [`3abaf17`](https://github.com/xability/py-maidr/commit/3abaf175ba2a458e11cf10628a71a06d8c98f41e))

Authored-by: nk46-cloud <nk46@illinois.edu>


## v1.11.1 (2026-02-23)

### Bug Fixes

- Use UTF-8 encoding when saving HTML on Windows
  ([#266](https://github.com/xability/py-maidr/pull/266),
  [`a97e4c1`](https://github.com/xability/py-maidr/commit/a97e4c1ede879ad4e11b430a03c5b9042ad4e9f2))

Co-authored-by: Claude Opus 4.6 <noreply@anthropic.com>

### Continuous Integration

- Update uv.lock to match pyproject.toml v1.11.0
  ([#265](https://github.com/xability/py-maidr/pull/265),
  [`cb44939`](https://github.com/xability/py-maidr/commit/cb44939a50fc438467bda864dc6ede148b8b493b))

Co-authored-by: Claude Opus 4.6 <noreply@anthropic.com>


## v1.11.0 (2026-02-04)

### Features

- Include format configuration from plot api ([#262](https://github.com/xability/py-maidr/pull/262),
  [`59eb82f`](https://github.com/xability/py-maidr/commit/59eb82f880d370eab4cf437e22dee3cd4856158c))


## v1.10.0 (2026-01-31)

### Features

- Remove candlestick formatting and add ylabel to dodged plots
  ([#260](https://github.com/xability/py-maidr/pull/260),
  [`70b2626`](https://github.com/xability/py-maidr/commit/70b2626bb31e109e8cdb29051f809fe03bfb6275))


## v1.9.0 (2025-10-31)

### Features

- Add data_in_svg parameter for save_html ([#257](https://github.com/xability/py-maidr/pull/257),
  [`17d65ee`](https://github.com/xability/py-maidr/commit/17d65eee06ac3209ef3a91ebd623a5a6d0b16e79))


## v1.8.1 (2025-10-16)

### Bug Fixes

- Address container label issue in seaborn dodged plots
  ([#256](https://github.com/xability/py-maidr/pull/256),
  [`3b09039`](https://github.com/xability/py-maidr/commit/3b09039ba33a10903797559a27d53869ba6b9d2f))


## v1.8.0 (2025-09-17)

### Features

- Remove maidr.show params ([#244](https://github.com/xability/py-maidr/pull/244),
  [`493cf57`](https://github.com/xability/py-maidr/commit/493cf5713068b1514b4836e46763c3619a51dd23))

### Refactoring

- **maidr.api**: Improve lazy figure detection, eliminate code duplication, and resolve merge
  conflicts ([#241](https://github.com/xability/py-maidr/pull/241),
  [`15a966e`](https://github.com/xability/py-maidr/commit/15a966ea2ca9170ddf8bc28634705fb6233a1d58))

Co-authored-by: copilot-swe-agent[bot] <198982749+Copilot@users.noreply.github.com>

Co-authored-by: jooyoungseo <19754711+jooyoungseo@users.noreply.github.com>


## v1.7.3 (2025-09-15)

### Bug Fixes

- Ensure all subplots are accessible and improve dodged plot detection
  ([#242](https://github.com/xability/py-maidr/pull/242),
  [`979b971`](https://github.com/xability/py-maidr/commit/979b9713d07be8bc9046056e7f1c0519336ddd22))

Co-authored-by: copilot-swe-agent[bot] <198982749+Copilot@users.noreply.github.com>

Co-authored-by: jooyoungseo <19754711+jooyoungseo@users.noreply.github.com>

Co-authored-by: JooYoung Seo <jseo1005@illinois.edu>


## v1.7.2 (2025-09-12)

### Bug Fixes

- Prevent iframe resizing when modal is open ([#237](https://github.com/xability/py-maidr/pull/237),
  [`89a4253`](https://github.com/xability/py-maidr/commit/89a42537a32025b286b8089b7f4b21b7c409c4e4))


## v1.7.1 (2025-09-03)

### Bug Fixes

- Address categorical x-values in line plot ([#236](https://github.com/xability/py-maidr/pull/236),
  [`d4e0eea`](https://github.com/xability/py-maidr/commit/d4e0eea6e558fc6540eb9500b82dedb339f739b4))


## v1.7.0 (2025-08-21)

### Features

- Format date in candlestick ([#234](https://github.com/xability/py-maidr/pull/234),
  [`ffe03f7`](https://github.com/xability/py-maidr/commit/ffe03f7a2368ef33a4266692e7b652daafa14a30))


## v1.6.1 (2025-08-13)

### Bug Fixes

- Add new selector logic for candlestick plots
  ([#231](https://github.com/xability/py-maidr/pull/231),
  [`66cd73a`](https://github.com/xability/py-maidr/commit/66cd73adb04f77c0b83fd6e2d9cf757ee909bd69))

### Continuous Integration

- Remove virtualenv dependecny ([#228](https://github.com/xability/py-maidr/pull/228),
  [`b8e1423`](https://github.com/xability/py-maidr/commit/b8e1423c2ecd073bd1037466f68577242872df6b))

### Documentation

- Update user manual to reflect all supported plot types with proper technical descriptions
  ([#230](https://github.com/xability/py-maidr/pull/230),
  [`bae1163`](https://github.com/xability/py-maidr/commit/bae116322cb580f5c528da2857a7ca3ec2a655a7))

Co-authored-by: copilot-swe-agent[bot] <198982749+Copilot@users.noreply.github.com>

Co-authored-by: jooyoungseo <19754711+jooyoungseo@users.noreply.github.com>

Co-authored-by: JooYoung Seo <jseo1005@illinois.edu>


## v1.6.0 (2025-08-04)

### Continuous Integration

- Update uv.lock ([#227](https://github.com/xability/py-maidr/pull/227),
  [`f162971`](https://github.com/xability/py-maidr/commit/f162971f4e2585e055de3c837ce9342b292cb378))

### Features

- Add WSL compatibility for opening HTML files
  ([#224](https://github.com/xability/py-maidr/pull/224),
  [`2f2a899`](https://github.com/xability/py-maidr/commit/2f2a899b1df4137db94aeb843099ee6f0df952f0))


## v1.5.0 (2025-08-04)

### Features

- Detect if running in a flask app and render in an iframe
  ([#225](https://github.com/xability/py-maidr/pull/225),
  [`dcd0e0f`](https://github.com/xability/py-maidr/commit/dcd0e0fb1f7a995e4eb2578e9f67cc31e45171ea))


## v1.4.10 (2025-07-30)

### Bug Fixes

- **candlestick**: Address rendering error ([#222](https://github.com/xability/py-maidr/pull/222),
  [`af14bec`](https://github.com/xability/py-maidr/commit/af14bec9c25163c2c3b7b86d3e97e038db2f667b))

### Continuous Integration

- Sync lock ([#223](https://github.com/xability/py-maidr/pull/223),
  [`d8dedf7`](https://github.com/xability/py-maidr/commit/d8dedf73f3001f484a747dd943856fb1e0383e68))


## v1.4.9 (2025-07-25)

### Bug Fixes

- Add layer id for layers ([#220](https://github.com/xability/py-maidr/pull/220),
  [`3a50a5c`](https://github.com/xability/py-maidr/commit/3a50a5c97dfbfa7c4c17d6856080c9ad8e3ad65c))

### Continuous Integration

- Remove redundant github releases ([#218](https://github.com/xability/py-maidr/pull/218),
  [`6a3874a`](https://github.com/xability/py-maidr/commit/6a3874acf92f4c8bad95ee2b8f10065df55ef25a))

- Sync uv.lock ([#219](https://github.com/xability/py-maidr/pull/219),
  [`bbfbc31`](https://github.com/xability/py-maidr/commit/bbfbc314553f944ef102e1e0d2fa5741f05701c2))


## v1.4.8 (2025-07-15)

### Bug Fixes

- Adress pyproject versioning ([#217](https://github.com/xability/py-maidr/pull/217),
  [`fd7c2ca`](https://github.com/xability/py-maidr/commit/fd7c2ca53c20c9262b470ff050cfd8c320ad5e3a))


## v1.4.7 (2025-07-15)

### Bug Fixes

- Address versioning updates ([#216](https://github.com/xability/py-maidr/pull/216),
  [`4b236e4`](https://github.com/xability/py-maidr/commit/4b236e4bb0299f6adbe7e8bfcae9b3db93ecce41))


## v1.4.6 (2025-07-15)

### Bug Fixes

- Address release issue ([#215](https://github.com/xability/py-maidr/pull/215),
  [`c03a55c`](https://github.com/xability/py-maidr/commit/c03a55ca2b1343e96524137181a6ef1c5f2da733))

- Address semantic-release config in pyproject.toml
  ([#213](https://github.com/xability/py-maidr/pull/213),
  [`0735fea`](https://github.com/xability/py-maidr/commit/0735feacd89bb8ee47475a6456e6a7f08878c332))

- Semantic relase with uv build validation ([#214](https://github.com/xability/py-maidr/pull/214),
  [`cbaebd9`](https://github.com/xability/py-maidr/commit/cbaebd920bea8feca82f64a4a3f7e81cf1ba077b))

### Continuous Integration

- Fix release gh wf ([#211](https://github.com/xability/py-maidr/pull/211),
  [`ae679a5`](https://github.com/xability/py-maidr/commit/ae679a529f98642a9165278b985cfd4f110565d3))

- Semantic release poetry to uv ([#212](https://github.com/xability/py-maidr/pull/212),
  [`b300d1c`](https://github.com/xability/py-maidr/commit/b300d1ca3d83418b0f7dde8e341783d41fbc567e))


## v1.4.5 (2025-07-14)

### Bug Fixes

- **candlestick**: Address bull and bear logic gap
  ([#210](https://github.com/xability/py-maidr/pull/210),
  [`77308c5`](https://github.com/xability/py-maidr/commit/77308c5a1b055523db972a3c33fd977ac6bd0c80))

### Build System

- Migrate to uv from poetry ([#209](https://github.com/xability/py-maidr/pull/209),
  [`2d36e42`](https://github.com/xability/py-maidr/commit/2d36e422fdf449215bd9e416ac33cae405f9e85b))

Co-authored-by: Krishna Anandan Ganesan <krishna1729atom@gmail.com>

Co-authored-by: JooYoung Seo <jseo1005@illinois.edu>


## v1.4.4 (2025-07-01)

### Bug Fixes

- Revert maidr-version npmjs fetch ([#208](https://github.com/xability/py-maidr/pull/208),
  [`969ee31`](https://github.com/xability/py-maidr/commit/969ee317c8fe47f204133ea685665e05b266c6d7))


## v1.4.3 (2025-06-27)

### Bug Fixes

- Address bugs in candlestick & line plots ([#207](https://github.com/xability/py-maidr/pull/207),
  [`0883878`](https://github.com/xability/py-maidr/commit/088387880e17abb3e9d72f937dd59c62193f8cb3))

Co-authored-by: Copilot <175728472+Copilot@users.noreply.github.com>


## v1.4.2 (2025-06-27)

### Bug Fixes

- Address reg plot multi-line detection ([#206](https://github.com/xability/py-maidr/pull/206),
  [`9ef8607`](https://github.com/xability/py-maidr/commit/9ef86070d52c9897b6237593a0138f3076b5321c))


## v1.4.1 (2025-06-26)

### Bug Fixes

- Add label & title for `mpl.plot()` ([#205](https://github.com/xability/py-maidr/pull/205),
  [`07cfe0b`](https://github.com/xability/py-maidr/commit/07cfe0b3014a065868358b490166fc784229d239))


## v1.4.0 (2025-06-25)

### Features

- Support `mpl.plot()` for candlestick plots ([#203](https://github.com/xability/py-maidr/pull/203),
  [`0653747`](https://github.com/xability/py-maidr/commit/06537475a39b318590a191bbe9523306d8da16c3))


## v1.3.0 (2025-06-23)

### Features

- Support Pyodide ([#204](https://github.com/xability/py-maidr/pull/204),
  [`3aeae97`](https://github.com/xability/py-maidr/commit/3aeae97a79e1d5ce4dc59e4b361e5ff68a3a95f6))


## v1.2.2 (2025-06-23)

### Bug Fixes

- Address multiline plot highlight ([#201](https://github.com/xability/py-maidr/pull/201),
  [`7d541e3`](https://github.com/xability/py-maidr/commit/7d541e3425894bb8470e3d528794ee1301cf91ba))

### Continuous Integration

- Address `CHANGELOG.md` update issue ([#200](https://github.com/xability/py-maidr/pull/200),
  [`d8a6540`](https://github.com/xability/py-maidr/commit/d8a65407af1373ed40c3ad70fe128ea31ba0d066))


## v1.2.1 (2025-06-19)

### Bug Fixes

- Address semantic release deprecation warning
  ([#196](https://github.com/xability/py-maidr/pull/196),
  [`b223bd1`](https://github.com/xability/py-maidr/commit/b223bd1247712e2cf61b920572f5818b3a2b10bb))


## v1.2.0 (2025-06-19)

### Features

- Support candlestick chart ([#195](https://github.com/xability/py-maidr/pull/195),
  [`a5bd8f5`](https://github.com/xability/py-maidr/commit/a5bd8f5e4f547a1f97a6f25025ae43c1d1291dab))

Co-authored-by: Daksh Pokar <dakshp2@illinois.edu>

Co-authored-by: JooYoung Seo <jseo1005@illinois.edu>


## v1.1.0 (2025-06-18)

### Bug Fixes

- Address iframe tag issue in `save_html()` ([#192](https://github.com/xability/py-maidr/pull/192),
  [`97b3432`](https://github.com/xability/py-maidr/commit/97b3432d8ee6ceb7ba32d12462079c8f880e50e7))

- **boxplot**: Enhance outlier handling by separting outliers
  ([#180](https://github.com/xability/py-maidr/pull/180),
  [`102df14`](https://github.com/xability/py-maidr/commit/102df14a05d62dfe1b3a171d1a50ffbf2ecc8210))

Co-authored-by: Copilot <175728472+Copilot@users.noreply.github.com>

### Features

- Add density layer support in kde and hist plot
  ([#189](https://github.com/xability/py-maidr/pull/189),
  [`d2cab63`](https://github.com/xability/py-maidr/commit/d2cab632c6519741fbb0e97e3a160a0c1e55cf50))

Co-authored-by: JooYoung Seo <jseo1005@illinois.edu>


## v1.0.0 (2025-06-11)

### Bug Fixes

- Change maidrjs version ([#187](https://github.com/xability/py-maidr/pull/187),
  [`e0bc7f0`](https://github.com/xability/py-maidr/commit/e0bc7f0f496d49b93d1d6f936dd6580584939845))

### Documentation

- **user guide**: Update keyboard shortcuts following new design
  ([`6495734`](https://github.com/xability/py-maidr/commit/64957340a394c8c0b6cfc7223cfb1deb1e7d582f))


## v0.25.2 (2025-05-01)

### Bug Fixes

- Update logo image URLs
  ([`b22389f`](https://github.com/xability/py-maidr/commit/b22389fbe307d0c37881b08acdaf47db374dfa47))


## v0.25.1 (2025-05-01)

### Bug Fixes

- Address figures are duplicated in jupyter notebook and quarto doc
  ([#177](https://github.com/xability/py-maidr/pull/177),
  [`12e5eef`](https://github.com/xability/py-maidr/commit/12e5eefc45847c705089ce0930c8739cd7394a57))


## v0.25.0 (2025-05-01)

### Features

- Update MAIDR CDN URLs for JavaScript and CSS files
  ([`2b31712`](https://github.com/xability/py-maidr/commit/2b31712bbb81812fbe239bc46a547694128ac8fc))


## v0.24.0 (2025-05-01)

### Features

- Support box-plot highlight ([#174](https://github.com/xability/py-maidr/pull/174),
  [`3c065b8`](https://github.com/xability/py-maidr/commit/3c065b8bc21d10f33b06d35e5ec526d2225be491))


## v0.23.1 (2025-04-29)

### Bug Fixes

- **stacked barplot**: Address an issue where fill label is not working
  ([#175](https://github.com/xability/py-maidr/pull/175),
  [`a4c36f2`](https://github.com/xability/py-maidr/commit/a4c36f2924f3afaa099d10cdc9e759f6d2d479b7))


## v0.23.0 (2025-04-29)

### Features

- Support facet plot in py-maidr using maidr-ts
  ([#148](https://github.com/xability/py-maidr/pull/148),
  [`d6d6b9a`](https://github.com/xability/py-maidr/commit/d6d6b9a06ad281ec567952d3e9b7f243a1664b8f))


## v0.22.2 (2025-04-28)

### Bug Fixes

- Ensure dodge plot type is correctly set in seaborn
  ([#172](https://github.com/xability/py-maidr/pull/172),
  [`2d43c9b`](https://github.com/xability/py-maidr/commit/2d43c9bda5744249555e4e214736ff0395d8d3ae))

- Shiny app maidr render issue
  ([`17f431d`](https://github.com/xability/py-maidr/commit/17f431de3584f3cc7951f8fd395e62c4206f7a67))


## v0.22.1 (2025-04-22)

### Bug Fixes

- Remove redundant _child0 label as a fill parameter for line plot
  ([#169](https://github.com/xability/py-maidr/pull/169),
  [`e543890`](https://github.com/xability/py-maidr/commit/e543890af0a89b38561a8760292cd996adadac22))

Co-authored-by: Copilot <175728472+Copilot@users.noreply.github.com>

### Documentation

- Add quartodoc examples for multiline, subplots, dodged bar plot, stacked …
  ([#168](https://github.com/xability/py-maidr/pull/168),
  [`5a2235a`](https://github.com/xability/py-maidr/commit/5a2235ac3da0372f3e17ddde35adc45c1dfd60b7))

### Refactoring

- Clean up example gallery examples
  ([`337a653`](https://github.com/xability/py-maidr/commit/337a65346aca82f4805bbbac850d1ef9e6146702))

- Remove legacy JS engine support and related code
  ([#165](https://github.com/xability/py-maidr/pull/165),
  [`e7fcae8`](https://github.com/xability/py-maidr/commit/e7fcae88b3555e98539b8844168209d9c3b0e9b8))


## v0.22.0 (2025-04-17)

### Bug Fixes

- Replace caching for Poetry dependencies in CI workflow
  ([#164](https://github.com/xability/py-maidr/pull/164),
  [`d719156`](https://github.com/xability/py-maidr/commit/d719156171a6d788290a01c0393db95bcc1b6090))

- Streamline Python setup in Quarto CI
  ([`2621e1e`](https://github.com/xability/py-maidr/commit/2621e1e0ffcbe3d11677807e310b69ef4d33f33e))

- Update Python setup step and improve Poetry installation in release workflow
  ([`3dc9f1e`](https://github.com/xability/py-maidr/commit/3dc9f1e81b0cdb46e9e822e557c278a92792104e))

- Update selector logic in ScatterPlot for correct element targeting
  ([#162](https://github.com/xability/py-maidr/pull/162),
  [`4c763af`](https://github.com/xability/py-maidr/commit/4c763af538875ed97c55a15a444152f1afd1eaa4))

### Features

- Support highlight in dodged and stacked bar plot using maidr-ts
  ([#161](https://github.com/xability/py-maidr/pull/161),
  [`04c874c`](https://github.com/xability/py-maidr/commit/04c874cf9683e0ac10ba4a40df04aa13ef1d5bf5))


## v0.21.0 (2025-04-15)

### Features

- Update py-maidr backend to use latest maidr-ts engine
  ([#158](https://github.com/xability/py-maidr/pull/158),
  [`16a8f3e`](https://github.com/xability/py-maidr/commit/16a8f3e47cdc4e70ea814aab444486ed8e068b3d))

BREAKING CHANGE: Using Maidr TS Engine by default, deprecating the JS engine.

### Breaking Changes

- Using Maidr TS Engine by default, deprecating the JS engine.


## v0.20.0 (2025-04-08)

### Features

- Support boxplot using maidr-ts ([#151](https://github.com/xability/py-maidr/pull/151),
  [`ce42413`](https://github.com/xability/py-maidr/commit/ce4241335e34939afc18073d64966aff228dc9ed))


## v0.19.1 (2025-03-27)

### Bug Fixes

- Address type hints for _extract_line_data method in MultiLinePlot
  ([#152](https://github.com/xability/py-maidr/pull/152),
  [`c91425c`](https://github.com/xability/py-maidr/commit/c91425c4dd6e3c701a3b2692ec4bdc39d3d6ddaf))


## v0.19.0 (2025-03-27)

### Features

- Support histogram plot using maidr-ts ([#150](https://github.com/xability/py-maidr/pull/150),
  [`bcc7269`](https://github.com/xability/py-maidr/commit/bcc726932d8fda6c55a46f94303637c619749a81))

- Support scatter plot using maidr-ts ([#149](https://github.com/xability/py-maidr/pull/149),
  [`b7223c8`](https://github.com/xability/py-maidr/commit/b7223c8d6f57276300bf3cb2e864a6e200108da9))


## v0.18.0 (2025-03-18)

### Features

- Support subplots in py-maidr using maidr-ts
  ([#147](https://github.com/xability/py-maidr/pull/147),
  [`5349f63`](https://github.com/xability/py-maidr/commit/5349f630c74bf348bba1cae373d06bf14c2424f5))


## v0.17.0 (2025-03-18)

### Features

- Support multilayer plot using maidr-ts ([#145](https://github.com/xability/py-maidr/pull/145),
  [`74218fb`](https://github.com/xability/py-maidr/commit/74218fb7faf934938746e797ffe53c093d7d6a5a))


## v0.16.1 (2025-03-13)

### Bug Fixes

- Prevent appending empty line data in MultiLinePlot
  ([#146](https://github.com/xability/py-maidr/pull/146),
  [`9e4217d`](https://github.com/xability/py-maidr/commit/9e4217df037176d0e44b5c03f086c915425f5d20))


## v0.16.0 (2025-03-12)

### Features

- Support multilayer plot using maidr-ts
  ([`a697c73`](https://github.com/xability/py-maidr/commit/a697c739601538368c807ae280dde0fc13072a20))


## v0.15.0 (2025-03-11)

### Features

- Support multiline plot in maidr-ts ([#144](https://github.com/xability/py-maidr/pull/144),
  [`3f2cf85`](https://github.com/xability/py-maidr/commit/3f2cf85be773949f5fbe874781c14851a9e27f62))


## v0.14.0 (2025-03-10)

### Features

- Support py-maidr lineplot on maidr-ts ([#143](https://github.com/xability/py-maidr/pull/143),
  [`d03e240`](https://github.com/xability/py-maidr/commit/d03e240598872b04103e88f20444320749bc15e6))


## v0.13.0 (2025-03-06)

### Features

- Add typescript maidr engine support for bar plot
  ([#141](https://github.com/xability/py-maidr/pull/141),
  [`0e21779`](https://github.com/xability/py-maidr/commit/0e21779a414335327dc41c0df8c6147a0cd341cc))


## v0.12.3 (2025-03-06)

### Bug Fixes

- Address pyshiny initialization in maidr ([#142](https://github.com/xability/py-maidr/pull/142),
  [`c22fff6`](https://github.com/xability/py-maidr/commit/c22fff61b407e87c2e17c59d26a945422625f6e7))


## v0.12.2 (2025-02-28)

### Bug Fixes

- Update initialization method to use window.init on DOMContentLoaded
  ([#140](https://github.com/xability/py-maidr/pull/140),
  [`8bfd8fd`](https://github.com/xability/py-maidr/commit/8bfd8fdfbb0f027d8e91645b6cc056c9c65ad9bf))


## v0.12.1 (2025-02-28)

### Bug Fixes

- Remove iframe in support of iframeless rendering
  ([#139](https://github.com/xability/py-maidr/pull/139),
  [`cf7cc26`](https://github.com/xability/py-maidr/commit/cf7cc265edfdeb54e28c869f7a14a88203cf95d7))


## v0.12.0 (2025-02-20)

### Features

- Add 'maidr-data' attribute to SVG elements ([#138](https://github.com/xability/py-maidr/pull/138),
  [`25d2ee3`](https://github.com/xability/py-maidr/commit/25d2ee31d6f21054d6c3b907edcc194fd7370028))


## v0.11.0 (2025-02-19)

### Features

- Add dodged bar plot support along with an matplotlib example
  ([#136](https://github.com/xability/py-maidr/pull/136),
  [`81197ce`](https://github.com/xability/py-maidr/commit/81197cef9f32746a53545713c63bfb8963b25c27))


## v0.10.6 (2025-02-11)

### Bug Fixes

- Stacked bar plot with new api ([#132](https://github.com/xability/py-maidr/pull/132),
  [`003be7c`](https://github.com/xability/py-maidr/commit/003be7cc1c4fbaa7d24df61ab85b1273cfe8f663))

### Continuous Integration

- Remove --no-update execution from poetry setup in ci and docs action
  ([#131](https://github.com/xability/py-maidr/pull/131),
  [`17c4bc1`](https://github.com/xability/py-maidr/commit/17c4bc1e2095a232cc47178b154926fdd306cb51))

- Update poetry.lock to adhere to v2.0.0 ([#129](https://github.com/xability/py-maidr/pull/129),
  [`d8a695e`](https://github.com/xability/py-maidr/commit/d8a695e70481fe55c084de71fdd29716053fb6ff))

- Update virtualenv to higher than 20.26.6 ([#128](https://github.com/xability/py-maidr/pull/128),
  [`a3052e1`](https://github.com/xability/py-maidr/commit/a3052e1a5e793950731cd31c7e5ec2707ba15e0b))

### Documentation

- Add box plot example to documentation with note on visual highlight feature
  ([`4ad7362`](https://github.com/xability/py-maidr/commit/4ad7362d93529a7c5537e982e9275684f91cb99a))

- Add Braille generation section with detailed encoding for various plot types
  ([`62f4c07`](https://github.com/xability/py-maidr/commit/62f4c077807dd3575da04c18fcb443f10b251629))

- Add link to original maidr engine repository for additional context
  ([`bf71a01`](https://github.com/xability/py-maidr/commit/bf71a010b1a1c204f0a34b3b651b83724b0ce8c4))

- Add link to Quarto scientific publishing system in reproducibility section
  ([`c177c78`](https://github.com/xability/py-maidr/commit/c177c789373aa9c4399e523966204afcd69e4dcb))

- Add note about "Unlabeled 0 Button" issue in Streamlit dashboard example
  ([`12e35b7`](https://github.com/xability/py-maidr/commit/12e35b7853dff76d20815040029202f249dc8bee))

- Add note to save and share accessible version of plot
  ([`7a05f2b`](https://github.com/xability/py-maidr/commit/7a05f2b62fa12ba52c005c98806c265e881793bb))

- Add section on requesting refreshable Braille display loaners
  ([`e4efd56`](https://github.com/xability/py-maidr/commit/e4efd56766bfc9202972b371375016dd244b2f2a))

- Add supported data visualization libraries section to documentation
  ([`2f2b78e`](https://github.com/xability/py-maidr/commit/2f2b78e6685e2a6d7abc40d1e78739967fab872e))

- Correct axis description for horizontal box plot in documentation
  ([`ddd5e4c`](https://github.com/xability/py-maidr/commit/ddd5e4c9df620c1c707a296c5034a8f7768ad588))

- Enable external link icons and new window behavior in Quarto configuration
  ([`671e1c3`](https://github.com/xability/py-maidr/commit/671e1c3ee3cbec5ac0f2786ff0ecff507a748bcf))

- Enhance documentation for Shiny and AI feature usage
  ([`212f709`](https://github.com/xability/py-maidr/commit/212f709d487368133fe778b23440547cee180a49))

- Enhance note formatting for clarity in AI model and chat modal sections
  ([`dad1389`](https://github.com/xability/py-maidr/commit/dad138916bb5cb1c9cd5362f0ce7364c20457d68))

- Update introduction to include link to original maidr engine repository
  ([`5cbd7a0`](https://github.com/xability/py-maidr/commit/5cbd7a0ffe8aa19a78babf4cd069e4266a56bf31))

- Update keyboard shortcuts section with detailed controls for maidr interaction
  ([`dd3b79f`](https://github.com/xability/py-maidr/commit/dd3b79f633cb3c84125567c025d95aa169d0f0cf))

- Update save function name for bar plot in documentation
  ([`ead96c1`](https://github.com/xability/py-maidr/commit/ead96c17a99296d56e49b437139d808c3444b921))

- Update Streamlit dashboard link in examples.qmd
  ([`4c2bcc1`](https://github.com/xability/py-maidr/commit/4c2bcc1f1c0b1afa460465a44d03ae0204467041))


## v0.10.5 (2024-12-18)

### Bug Fixes

- Address an issue where is_notebook returns false in Google Colab
  ([#127](https://github.com/xability/py-maidr/pull/127),
  [`a50b4c1`](https://github.com/xability/py-maidr/commit/a50b4c1d5aa264731d4135e38b6f06eac0932e04))

### Continuous Integration

- Update actions/cache to v4
  ([`4cd8533`](https://github.com/xability/py-maidr/commit/4cd853384f3dc73e99991534813e69ba772dda4f))

### Documentation

- Add CNAME under docs directory
  ([`54de423`](https://github.com/xability/py-maidr/commit/54de423e4ff73907b2616e5613185703389c6c50))

- Adjust figure sizes and formatting in examples.qmd
  ([#126](https://github.com/xability/py-maidr/pull/126),
  [`5bf07f3`](https://github.com/xability/py-maidr/commit/5bf07f3019d42b336a7ffbc59652d42cd9fec5cd))

- Simplify Google Colab link in examples.qmd
  ([`229a3ac`](https://github.com/xability/py-maidr/commit/229a3acd2f707730c2dd197e305185ad96326545))

- Update endpoint url in quartodoc
  ([`9aa93b5`](https://github.com/xability/py-maidr/commit/9aa93b516309c477f3aaa0389139cf0d1d6430e2))

- Update keyboard shortcuts for Windows, Linux, and Mac
  ([`c1ff8c8`](https://github.com/xability/py-maidr/commit/c1ff8c8e8507ef42789aa18895b2982e15910a02))

- Update README to include user guide and example pointers
  ([`dd3fe56`](https://github.com/xability/py-maidr/commit/dd3fe56c7a19e2846b1912894938b9ba7ca04b3c))


## v0.10.4 (2024-12-06)

### Bug Fixes

- Set QUARTO_PYTHON environment variable in docs workflow
  ([#125](https://github.com/xability/py-maidr/pull/125),
  [`532b687`](https://github.com/xability/py-maidr/commit/532b6872c8bcf91340a4737dedf7fa610d08b360))


## v0.10.3 (2024-12-06)

### Bug Fixes

- Update repository references from 'py_maidr' to 'py-maidr'
  ([`9749835`](https://github.com/xability/py-maidr/commit/9749835aeb81c58a5c750830f61ab6d4c1ec362d))

### Documentation

- Update index.qmd to improve example clarity and remove unused plots
  ([`783d7d8`](https://github.com/xability/py-maidr/commit/783d7d88afc95769dc2f361d33782ad76050ba0a))

- Update quartodoc to include getting started and examples
  ([#110](https://github.com/xability/py-maidr/pull/110),
  [`a95ff96`](https://github.com/xability/py-maidr/commit/a95ff96cef061941fc04e6dea051572dd3a6615e))

- **example**: Simplify plot titles in demo.qmd for clarity
  ([`1e72335`](https://github.com/xability/py-maidr/commit/1e723354e409ad6d1d021a4cc1436e4b58a55097))


## v0.10.2 (2024-10-17)

### Bug Fixes

- Address iframe resizing issue in jupyter notebooks
  ([#124](https://github.com/xability/py-maidr/pull/124),
  [`b437831`](https://github.com/xability/py-maidr/commit/b43783130eaa34df7d47efc57b0eb2a5819d9986))


## v0.10.1 (2024-10-17)

### Bug Fixes

- Address dynamic resizing of iframes on ipython
  ([#123](https://github.com/xability/py-maidr/pull/123),
  [`3159fc1`](https://github.com/xability/py-maidr/commit/3159fc1f4ccfff081f001bf41eff7b949b95a3c4))

- Correct import statement in maidr.py
  ([`e7d072a`](https://github.com/xability/py-maidr/commit/e7d072a3d94d573f06fd76c68cf57679f9c7584e))


## v0.10.0 (2024-10-15)

### Code Style

- **example**: Replace `py-shiny` folder name with `shiny`
  ([`4bb9e77`](https://github.com/xability/py-maidr/commit/4bb9e7766a2dcdee1e8467750c14cbb891878074))

### Features

- **maidr.show**: Use tempfile for interactive sessions
  ([#121](https://github.com/xability/py-maidr/pull/121),
  [`ef668ee`](https://github.com/xability/py-maidr/commit/ef668ee2b9619883b3abbb6e9be3b9371b9372e6))


## v0.9.2 (2024-10-09)

### Bug Fixes

- Suppress wrapt warning messages ([#116](https://github.com/xability/py-maidr/pull/116),
  [`1283be5`](https://github.com/xability/py-maidr/commit/1283be5fe4c15012ae5385665f48da6300db69d0))

Co-authored-by: JooYoung Seo <jseo1005@illinois.edu>

### Documentation

- **example**: Update scripts to comment out `plt.show()`
  ([#118](https://github.com/xability/py-maidr/pull/118),
  [`164d6fa`](https://github.com/xability/py-maidr/commit/164d6fa0e038b04f323c1eba98536f65a09c306e))


## v0.9.1 (2024-10-08)

### Bug Fixes

- Address an issue where rendered result is not displayed when ipy…
  ([#114](https://github.com/xability/py-maidr/pull/114),
  [`ccb1ae4`](https://github.com/xability/py-maidr/commit/ccb1ae42d4cefb9ad6962ea2fe10813745405602))

### Documentation

- **example**: Update ipynb to exclude inline rendering
  ([#113](https://github.com/xability/py-maidr/pull/113),
  [`c6ee419`](https://github.com/xability/py-maidr/commit/c6ee419c3bfb28c48f80b9715eb177fd4a67c89f))


## v0.9.0 (2024-09-13)

### Continuous Integration

- Sort out semantic release config to display `feat` and `fix` first in the release notes
  ([`529c721`](https://github.com/xability/py-maidr/commit/529c721b6d0b70e5bfb6d2d46c40991027502ff2))

- **semantic-release**: Exclude non-conventional commits from `CHANGELOG`
  ([#106](https://github.com/xability/py-maidr/pull/106),
  [`d40a95c`](https://github.com/xability/py-maidr/commit/d40a95c1d380a43553328e246025faea760f5e04))

This pull request updates the `exclude_commit_patterns` in the `pyproject.toml` file. The previous
  commits that don't match the conventional commits prefixes and internal changes that do not
  necessarily affect end-user interactions, such as `chore`, `ci`, and `style`, are excluded from
  our CHANGELOG and GitHub release note moving forward. This is not a direct fix, but after this
  change, it ensures that only relevant commits are included in the release changelog as a fair
  stopgap solution.

Closes #99

### Documentation

- **example**: Add `streamlit` dashboard demo with `maidr`
  ([#107](https://github.com/xability/py-maidr/pull/107),
  [`ae7bc15`](https://github.com/xability/py-maidr/commit/ae7bc15fabe2927c3377402eb4dbf4646dbe5806))

<!-- Suggested PR Title: [feat/fix/refactor/perf/test/ci/docs/chore] brief description of the change
  --> <!-- Please follow Conventional Commits: https://www.conventionalcommits.org/en/v1.0.0/ -->

## Description This PR includes an example streamlit web app to demonstrate interactivity
  capabilities with maidr.

closes #84

## Type of Change

- [ ] Bug fix - [ ] New feature - [ ] Breaking change (fix or feature that would cause existing
  functionality to not work as expected) - [x] Documentation update

## Checklist

- [x] My code follows the style guidelines of this project - [x] I have performed a self-review of
  my code - [x] I have commented my code, particularly in hard-to-understand areas - [x] I have made
  corresponding changes to the documentation - [x] My changes generate no new warnings - [x] Any
  dependent changes have been merged and published in downstream modules

# Pull Request

## Description Added a new file `example_streamlit_app.py` under streamlit folder in example
  directory.

## Screenshots (if applicable) <img width="1964" alt="image"
  src="https://github.com/user-attachments/assets/bf3b5630-2e71-4057-87ad-5b9ca0940769">

### Features

- Fetch LLM API keys from user env variables ([#102](https://github.com/xability/py-maidr/pull/102),
  [`fc84593`](https://github.com/xability/py-maidr/commit/fc84593a9b01904d24fd86da88f79e25db02417a))

<!-- Suggested PR Title: [feat/fix/refactor/perf/test/ci/docs/chore] brief description of the change
  --> <!-- Please follow Conventional Commits: https://www.conventionalcommits.org/en/v1.0.0/ -->

## Description This pull request fixes the handling of API keys for LLMs in the code. It adds a
  JavaScript script to handle the API keys for LLMs and initializes the LLM secrets in the MAIDR
  instance. The script injects the LLM API keys into the MAIDR instance and sets the appropriate
  settings based on the presence of the Gemini and OpenAI API keys. This ensures that the LLM
  functionality works correctly with the updated API key handling.

closes #76

## Type of Change

- [x] Bug fix - [ ] New feature - [ ] Breaking change (fix or feature that would cause existing
  functionality to not work as expected) - [ ] Documentation update

## Checklist

- [x] My code follows the style guidelines of this project - [x] I have performed a self-review of
  my code - [x] I have commented my code, particularly in hard-to-understand areas - [x] I have made
  corresponding changes to the documentation - [x] My changes generate no new warnings - [x] Any
  dependent changes have been merged and published in downstream modules

# Pull Request

## Description 1. Added a new method called `initialize_llm_secrets()` in environment.py which
  fetches the keys from the environment variable. 2. Injected the script when the maidr iframe loads
  initially.

## Checklist <!-- Please select all applicable options. --> <!-- To select your options, please put
  an 'x' in the all boxes that apply. -->

- [x] I have read the [Contributor Guidelines](../CONTRIBUTING.md). - [x] I have performed a
  self-review of my own code and ensured it follows the project's coding standards. - [x] I have
  tested the changes locally following `ManualTestingProcess.md`, and all tests related to this pull
  request pass. - [x] I have commented my code, particularly in hard-to-understand areas. - [x] I
  have updated the documentation, if applicable. - [x] I have added appropriate unit tests, if
  applicable.

## Additional Notes <!-- Add any additional notes or comments here. --> <!-- Template credit: This
  pull request template is based on Embedded Artistry
  {https://github.com/embeddedartistry/templates/blob/master/.github/PULL_REQUEST_TEMPLATE.md},
  Clowder
  {https://github.com/clowder-framework/clowder/blob/develop/.github/PULL_REQUEST_TEMPLATE.md}, and
  TalAter {https://github.com/TalAter/open-source-templates} templates. -->


## v0.8.0 (2024-08-27)

### Build System

- Move `black` formatter to `dev` dependencies
  ([`ca460b4`](https://github.com/xability/py-maidr/commit/ca460b4cca26418bee3cab2ce4949b96d5e60147))

- Remove `sphinx` from package dev dependencies
  ([`41f61a9`](https://github.com/xability/py-maidr/commit/41f61a915d9b3dea27419d984c8cd9408de794d5))

### Features

- Pick up seaborn heatmap fmt towards maidr ([#90](https://github.com/xability/py-maidr/pull/90),
  [`fb5dde0`](https://github.com/xability/py-maidr/commit/fb5dde0c7b2d65f6649342ff5474f032e4e36bae))


## v0.7.0 (2024-08-24)

### Continuous Integration

- Rectify commit-lint job crash ([#92](https://github.com/xability/py-maidr/pull/92),
  [`ae50904`](https://github.com/xability/py-maidr/commit/ae509047d6063e2cebc291c94b72281f00fa3617))

<!-- Suggested PR Title: [feat/fix/refactor/perf/test/ci/docs/chore] brief description of the change
  --> <!-- Please follow Conventional Commits: https://www.conventionalcommits.org/en/v1.0.0/ -->

## Description

This PR resolves an issue related to the `commit-lint` job in `.github/workflows/ci.yml`.

Closes [#91]

## Type of Change

- [X] Bug fix - [ ] New feature - [ ] Breaking change (fix or feature that would cause existing
  functionality to not work as expected) - [ ] Documentation update

## Checklist

- [X] My code follows the style guidelines of this project - [X] I have performed a self-review of
  my code - [ ] I have commented my code, particularly in hard-to-understand areas - [ ] I have made
  corresponding changes to the documentation - [X] My changes generate no new warnings - [ ] Any
  dependent changes have been merged and published in downstream modules

# Pull Request

## Description This PR addresses an issue where `commit-lint` job crashes when validating pull
  requests.

## Changes Made Currently, the commitlint config file is getting loaded as an ES module whilst it
  contains vanilla javascript configurations. This causes the job to crash because it expects a
  common javascript config but finds an ES module config. To address this issue The commit-lint
  config file has been changed to a `common-js` file instead of a `js` file and the conventional
  commit dependancy will now be installed during the job via npm.

## Screenshots (if applicable) After making the changes, I tested the commit-lint job locally and
  here is an excerpt of the execution: ``` (py-maidr) ➜ py_maidr git:(Krishna/fix-commitlint) act -j
  commit-lint -W .github/workflows/ci.yml --container-architecture linux/amd64

INFO[0000] Using docker host 'unix:///var/run/docker.sock', and daemon socket
  'unix:///var/run/docker.sock' [CI/commit-lint] 🚀 Start image=catthehacker/ubuntu:act-latest
  INFO[0000] Parallel tasks (0) below minimum, setting to 1 [CI/commit-lint] 🐳 docker pull
  image=catthehacker/ubuntu:act-latest platform=linux/amd64 username= forcePull=true
  [CI/commit-lint] using DockerAuthConfig authentication for docker pull INFO[0001] Parallel tasks
  (0) below minimum, setting to 1 [CI/commit-lint] 🐳 docker create
  image=catthehacker/ubuntu:act-latest platform=linux/amd64 entrypoint=["tail" "-f" "/dev/null"]
  cmd=[] network="host" [CI/commit-lint] 🐳 docker run image=catthehacker/ubuntu:act-latest
  platform=linux/amd64 entrypoint=["tail" "-f" "/dev/null"] cmd=[] network="host" [CI/commit-lint] ☁
  git clone 'https://github.com/wagoid/commitlint-github-action' # ref=v6 [CI/commit-lint] ⭐ Run
  Main actions/checkout@v3 [CI/commit-lint] 🐳 docker cp
  src=/Users/krishnaanandan/Desktop/maidr_krishna/py_maidr/.
  dst=/Users/krishnaanandan/Desktop/maidr_krishna/py_maidr [CI/commit-lint] ✅ Success - Main
  actions/checkout@v3 [CI/commit-lint] ⭐ Run Main Install commitlint dependencies [CI/commit-lint] 🐳
  docker exec cmd=[bash --noprofile --norc -e -o pipefail /var/run/act/workflow/1] user= workdir= |
  | added 11 packages in 3s | | 1 package is looking for funding | run `npm fund` for details
  [CI/commit-lint] ✅ Success - Main Install commitlint dependencies [CI/commit-lint] ⭐ Run Main Lint
  commit messages [CI/commit-lint] 🐳 docker pull image=wagoid/commitlint-github-action:6.1.1
  platform=linux/amd64 username= forcePull=true [CI/commit-lint] using DockerAuthConfig
  authentication for docker pull [CI/commit-lint] 🐳 docker create
  image=wagoid/commitlint-github-action:6.1.1 platform=linux/amd64 entrypoint=[] cmd=[]
  network="container:act-CI-commit-lint-6b355268bbbb8e27234c3c935b66fc686b070544b9a3b02b47d79688837a12ff"
  [CI/commit-lint] 🐳 docker run image=wagoid/commitlint-github-action:6.1.1 platform=linux/amd64
  entrypoint=[] cmd=[]
  network="container:act-CI-commit-lint-6b355268bbbb8e27234c3c935b66fc686b070544b9a3b02b47d79688837a12ff"
  | Lint free! 🎉 [CI/commit-lint] ✅ Success - Main Lint commit messages [CI/commit-lint] ⚙
  ::set-output:: results=[] [CI/commit-lint] Cleaning up container for job commit-lint
  [CI/commit-lint] 🏁 Job succeeded (py-maidr) ➜ py_maidr git:(Krishna/fix-commitlint) ```

## Checklist <!-- Please select all applicable options. --> <!-- To select your options, please put
  an 'x' in the all boxes that apply. -->

- [X] I have read the [Contributor Guidelines](../CONTRIBUTING.md). - [X] I have performed a
  self-review of my own code and ensured it follows the project's coding standards. - [X] I have
  tested the changes locally following `ManualTestingProcess.md`, and all tests related to this pull
  request pass. - [ ] I have commented my code, particularly in hard-to-understand areas. - [ ] I
  have updated the documentation, if applicable. - [ ] I have added appropriate unit tests, if
  applicable.

- **commitlint**: Disable commitlint line length and total length checking
  ([#87](https://github.com/xability/py-maidr/pull/87),
  [`3f718a7`](https://github.com/xability/py-maidr/commit/3f718a7dd12c9569ef63c9318d120d00650b5995))

closes #86

### Features

- **maidr.show**: Support py-shiny renderer ([#67](https://github.com/xability/py-maidr/pull/67),
  [`a944826`](https://github.com/xability/py-maidr/commit/a9448263f413246213bfc2bedf8d859b3cf74695))


## v0.6.0 (2024-08-21)

### Continuous Integration

- Add repo name condidtion to docs workflow ([#75](https://github.com/xability/py-maidr/pull/75),
  [`0fb17e9`](https://github.com/xability/py-maidr/commit/0fb17e9c86d92d29b315dd3af254ae187a853abb))

### Features

- Support interactivity within ipython and quarto
  ([#64](https://github.com/xability/py-maidr/pull/64),
  [`620ddc9`](https://github.com/xability/py-maidr/commit/620ddc9d57175d5ca663d9dfaef4d2704809462f))


## v0.5.1 (2024-08-14)

### Bug Fixes

- Update poetry.lock ([#74](https://github.com/xability/py-maidr/pull/74),
  [`6216959`](https://github.com/xability/py-maidr/commit/621695940075fe195b0310c544c117bdc5a9d35e))

### Continuous Integration

- Fixate python version in docs action ([#71](https://github.com/xability/py-maidr/pull/71),
  [`c0f981a`](https://github.com/xability/py-maidr/commit/c0f981a1d3741709c929af1d8616b39313501c62))

- Fixate python version in docs action (#71) ([#72](https://github.com/xability/py-maidr/pull/72),
  [`513780d`](https://github.com/xability/py-maidr/commit/513780d732ea2feb3890ace6c7028ebf5f193b17))

- Remove poetry.lock ([#73](https://github.com/xability/py-maidr/pull/73),
  [`da1cd26`](https://github.com/xability/py-maidr/commit/da1cd26d8db10aabfe989a760e8df9a62a4bfe3a))

- Update poetry.lock ([#70](https://github.com/xability/py-maidr/pull/70),
  [`87ffb06`](https://github.com/xability/py-maidr/commit/87ffb06d49f4062a35f5ebee0fa0e28265ceeec5))

- Upgrade quartodoc version ([#62](https://github.com/xability/py-maidr/pull/62),
  [`36fe34f`](https://github.com/xability/py-maidr/commit/36fe34fe52abca4be8e2101a10b76d887cd17bf2))


## v0.5.0 (2024-07-25)

### Features

- Support hightlighing except for segmented plots and boxplots
  ([#59](https://github.com/xability/py-maidr/pull/59),
  [`c2cb99d`](https://github.com/xability/py-maidr/commit/c2cb99d8d7668b177dcf8b800b137eb994c85d6f))


## v0.4.2 (2024-07-02)

### Bug Fixes

- Seaborn multi plots in same session ([#58](https://github.com/xability/py-maidr/pull/58),
  [`c32fdfd`](https://github.com/xability/py-maidr/commit/c32fdfd32473dd354d292d33a19610a4c0a2eb63))


## v0.4.1 (2024-06-25)

### Bug Fixes

- **boxplot**: Support seaborn axes flip ([#56](https://github.com/xability/py-maidr/pull/56),
  [`023907f`](https://github.com/xability/py-maidr/commit/023907fd2482631c42803c7504bf9b838fb035c6))


## v0.4.0 (2024-06-16)

### Bug Fixes

- **example**: Take out unused param from seaborn barplot example
  ([`a58001d`](https://github.com/xability/py-maidr/commit/a58001d06f19756ac9a625257301482a75c9dc6e))

### Features

- **boxplot**: Support horizontal orientation ([#52](https://github.com/xability/py-maidr/pull/52),
  [`aebfd89`](https://github.com/xability/py-maidr/commit/aebfd89d90c5d64432425745186b1fe9cceab49d))


## v0.3.0 (2024-06-11)

### Bug Fixes

- Black formatting ci ([#49](https://github.com/xability/py-maidr/pull/49),
  [`20c4fa2`](https://github.com/xability/py-maidr/commit/20c4fa231bd5a78679cce7698d2a42077c97f330))

- Remove docs ([#48](https://github.com/xability/py-maidr/pull/48),
  [`9b8cae5`](https://github.com/xability/py-maidr/commit/9b8cae5c1e4071be6edbfdbab8f4b498516f9caf))

### Continuous Integration

- Add workflow for publishing docs ([#44](https://github.com/xability/py-maidr/pull/44),
  [`a6c5886`](https://github.com/xability/py-maidr/commit/a6c5886cc66339eabdfac3c8dc8bb10ee2c037c6))

`docs.yml` automates the publishing of py-maidr documentation to GitHub Pages. This builds the
  static sources using `quarto` for the website and `quartodoc` for the API Reference. The rendering
  and publishing are accomplished using Quarto's github actions, which can be found at
  https://github.com/quarto-dev/quarto-actions.

Resolves: #43

### Features

- Support syntaxless-api ([#47](https://github.com/xability/py-maidr/pull/47),
  [`415d6f1`](https://github.com/xability/py-maidr/commit/415d6f1c2c9bf3f62b29da1dd752cb34a18168a3))


## v0.2.0 (2024-05-16)

### Continuous Integration

- Setup pr github workflow ([#40](https://github.com/xability/py-maidr/pull/40),
  [`4ea4bb6`](https://github.com/xability/py-maidr/commit/4ea4bb6de14854dec9234dc36938d24ed04e9902))

Combined the black, commit-message-lint, and the unit test workflow into one called ci.yml. This is
  beneficial because it could be reused in the release pipeline.

Resolves: #39

- Setup release pipeline ([#42](https://github.com/xability/py-maidr/pull/42),
  [`634f91c`](https://github.com/xability/py-maidr/commit/634f91cdf5a806f2b451727ccc94b970c7af6a90))

`release.yml` configures the github workflow to lint the commit message, format of the code, and the
  unit tests. After successfully completing those jobs, the pipeline builds the package, updates the
  semantic version according to the commit message and publishes to the GitHub Release as well as to
  the PyPi.

Resolves: #41

### Documentation

- Add docstring ([#34](https://github.com/xability/py-maidr/pull/34),
  [`59f0ca1`](https://github.com/xability/py-maidr/commit/59f0ca1551643f9077fe2891af153e5038ddefe8))

- Add quarto and quartodoc for static website ([#38](https://github.com/xability/py-maidr/pull/38),
  [`011b1b2`](https://github.com/xability/py-maidr/commit/011b1b2b916df3036644d43cd6741f663ca64bc3))

`_quarto.yml` includes the base structure of the static website with a navbar and the main site. The
  navbar includes 'Overview', 'Get Started', and 'API Referece' sections, which are structured in
  `_index.qmd`, `_get_started.qmd`, and the quartodoc section of `_quarto.yml` respectively.
  Currently, the 'Overview' and 'Get Started' sections are left empty, which will be generated in
  the upcoming releases. The 'API Reference' section will include the docstring in a neat format
  generated by `quartodoc`.

Resolves: #17

### Features

- Use htmltools instead of str ([#33](https://github.com/xability/py-maidr/pull/33),
  [`8b0a838`](https://github.com/xability/py-maidr/commit/8b0a838bf7cd73ecd5e036d9be28e8ed0523a9ed))

* feat: use htmltools instead of str

* feat: show html using htmltools

* chore: move mixin to utils package

- **boxplot**: Support matplotlib library ([#32](https://github.com/xability/py-maidr/pull/32),
  [`060ccfd`](https://github.com/xability/py-maidr/commit/060ccfda80bb168df00c78354b543dbd72c24f1b))


## v0.1.2 (2024-05-13)

### Bug Fixes

- Support seaborn breaking changes ([#31](https://github.com/xability/py-maidr/pull/31),
  [`afe5382`](https://github.com/xability/py-maidr/commit/afe538209e313f7a42c355c7234ba5f1d1ebf97b))

- Update pyproject.toml version and htmltools dependency
  ([#14](https://github.com/xability/py-maidr/pull/14),
  [`fcaca48`](https://github.com/xability/py-maidr/commit/fcaca486dff79ac6861d9561986088f432d74b64))

- **version**: Start from 0.0.1
  ([`6bf23bb`](https://github.com/xability/py-maidr/commit/6bf23bb3bff2056f7b1b8d54abc1539d666269ae))

### Continuous Integration

- :sparkles: add conventional commits linter to gh action
  ([`fc4b758`](https://github.com/xability/py-maidr/commit/fc4b758fb9b9ebd84dc83c9d4423bb3bdc6f4940))

- :wrench: add python-semantic-release dependencies and settings
  ([`f928eff`](https://github.com/xability/py-maidr/commit/f928eff5e923a5130b3cfbdb45d93ae9b2174346))

- :wrench: fix commmit linter gh action to be triggered against the latest commit only
  ([`dbb86d3`](https://github.com/xability/py-maidr/commit/dbb86d38e48e7f44908b61fab1d3122b09ce8bfc))

- :wrench: fix commmit linter gh action to be triggered against the latest commit only
  ([`f53251c`](https://github.com/xability/py-maidr/commit/f53251c5510901b51b7f615e49f565bc0a9bf351))

- Add conventional commits linter to gh workflowFixes #5
  ([`f1babab`](https://github.com/xability/py-maidr/commit/f1babab54ba44f211657386be17e839523c5c92f))

* ci: add conventional commits linter to gh workflow Fixes #5

- Update version to 0.1.1 ([#27](https://github.com/xability/py-maidr/pull/27),
  [`4ceff90`](https://github.com/xability/py-maidr/commit/4ceff90c6841e4d08fa1b3316a2ee6be75e50f92))

### Documentation

- Add CHANGELOG file
  ([`f19c78c`](https://github.com/xability/py-maidr/commit/f19c78c6c80cb5050765bbe6b7154dbe3a80dc17))

- Add code of conduct
  ([`777f850`](https://github.com/xability/py-maidr/commit/777f85088e49f3be3faa2e10cc3f6bce14c168b8))

- Add CONTRIBUTING.md file
  ([`2e4cf10`](https://github.com/xability/py-maidr/commit/2e4cf10800d75773e87981fb1665430c7c0a1306))

- Add development environment setup instructions
  ([`36ecba2`](https://github.com/xability/py-maidr/commit/36ecba242c680b9ed5e405d6e3924dd3c0b88b0c))

- Add documentation for classes and methods ([#16](https://github.com/xability/py-maidr/pull/16),
  [`4b5387e`](https://github.com/xability/py-maidr/commit/4b5387e0026b375e37e9097a4abaad7c8d110f94))

* docs: add documentation for classes and methods, following numpy docstring style

* fix: convert maidr data to numpy array

* docs: add docstring

* chore: change | none to optional typing

* chore: rever to | none typing

---------

Co-authored-by: SaaiVenkat <greenghost1100@gmail.com>

- Update installation instructions in README.md
  ([`a5134ed`](https://github.com/xability/py-maidr/commit/a5134ed20d544220cee4f89ae132b750a8005807))

- Update py-maidr installation instructions
  ([`0185aec`](https://github.com/xability/py-maidr/commit/0185aece83c66a85baea3d0ff4a9abbb6fa2f771))

- **heatmap**: Add matplotlib example ([#25](https://github.com/xability/py-maidr/pull/25),
  [`7cb9433`](https://github.com/xability/py-maidr/commit/7cb9433ad6908a0a882bf7e7897914e1d2479a48))

- **readme**: Add logo
  ([`8702ce5`](https://github.com/xability/py-maidr/commit/8702ce5b9097fcec2a856129841d17c73e5c4415))

- **readme**: Update base URL
  ([`6463477`](https://github.com/xability/py-maidr/commit/6463477cff6458d77c4bad3dc5b683cf52ee958b))

### Features

- Redesign python binder ([#10](https://github.com/xability/py-maidr/pull/10),
  [`2fe4901`](https://github.com/xability/py-maidr/commit/2fe490158c7cba8fb40d939a079e4c0817ed349a))

* feat: redesign python binder

* docs: add example bar plot

- Support seaborn bar and count plot ([#12](https://github.com/xability/py-maidr/pull/12),
  [`fd622bd`](https://github.com/xability/py-maidr/commit/fd622bdd51236627cd37babf9e20ef1378311ff7))

- **boxplot**: Support seaborn library ([#29](https://github.com/xability/py-maidr/pull/29),
  [`5506242`](https://github.com/xability/py-maidr/commit/55062427a2f363be9eeba5abe58725a7f55aa99e))

- **scatter**: Support matplotlib and seaborn library
  ([#30](https://github.com/xability/py-maidr/pull/30),
  [`d2d1202`](https://github.com/xability/py-maidr/commit/d2d12028350deec664614dac462f83d4e362a139))

- **stacked**: Support maidr for matplotlib and seaborn
  ([#28](https://github.com/xability/py-maidr/pull/28),
  [`9e95186`](https://github.com/xability/py-maidr/commit/9e951865b444ba3bbb932d7b8fd7b06885df0f2b))

### Testing

- **barplot**: Add unit tests for barplot ([#20](https://github.com/xability/py-maidr/pull/20),
  [`af81cd9`](https://github.com/xability/py-maidr/commit/af81cd935a5bfc1f76c43e4ed16665d11c383605))

* test(barplot): add unit tests for barplot

* chore: add mocks for inputs

* test: add common fixtures

* chore: correct test input

* test: add unit tests for bar plot

* test: add tox workflow

* test: add correct python version

* test: remove non-deterministic assert comment
