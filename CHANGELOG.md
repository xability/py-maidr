# CHANGELOG


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
