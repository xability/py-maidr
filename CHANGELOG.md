# CHANGELOG


## v1.24.0 (2026-09-21)

### Bug Fixes

- Follow-ups from the reviews of #722, #724, #727 and #757
  ([#763](https://github.com/xability/py-maidr/pull/763),
  [`b99a4c4`](https://github.com/xability/py-maidr/commit/b99a4c40e455fcc2663e9eee9d1fbddb926722cd))

- **api**: Resolve the figure once so close, clear_fig, save_html and seaborn grids behave
  ([#728](https://github.com/xability/py-maidr/pull/728),
  [`3514373`](https://github.com/xability/py-maidr/commit/3514373763579a8e31514be3c1f2a9cf48a69c71))

- **axes**: Read a tz-aware date axis as numeric rather than as string categories
  ([#730](https://github.com/xability/py-maidr/pull/730),
  [`8aa7a65`](https://github.com/xability/py-maidr/commit/8aa7a652b3f27f557366ac0768bb915cda42113e))

- **band**: Read confidence band edges in numpy and reject a signed area that touches both edges
  ([#742](https://github.com/xability/py-maidr/pull/742),
  [`191108f`](https://github.com/xability/py-maidr/commit/191108f7d908311690b2537026bb47334aa2bd14))

- **bar**: Read a constant baseline with no bar beneath it as an offset
  ([#761](https://github.com/xability/py-maidr/pull/761),
  [`b49371e`](https://github.com/xability/py-maidr/commit/b49371e1da303c8937f0b49da33c40b0be7b1185))

- **bar**: Read a positional stacking baseline and a zero one as none
  ([#758](https://github.com/xability/py-maidr/pull/758),
  [`69e7c81`](https://github.com/xability/py-maidr/commit/69e7c81d900a303888d0986a3640ac7a56068e81))

- **box**: Read a box whose caps or fliers are hidden and drop one whose statistics are NaN
  ([#726](https://github.com/xability/py-maidr/pull/726),
  [`fe602cf`](https://github.com/xability/py-maidr/commit/fe602cfa9af98ce31b83cc8c8d239c90985aab28))

- **candlestick**: Name each candle's own paths when a gap row is left out
  ([#762](https://github.com/xability/py-maidr/pull/762),
  [`9653a4b`](https://github.com/xability/py-maidr/commit/9653a4b2220b6021c95f00790cf2e322ff1ad14f))

- **candlestick**: Skip a NaN row and read the frame by column rather than by cell
  ([#739](https://github.com/xability/py-maidr/pull/739),
  [`e29df00`](https://github.com/xability/py-maidr/commit/e29df0038757fbca3f324892839c1e582196e2ee))

- **cdn**: Discard an abandoned lookup's verdict after a reset and say notebooks never resolve
  ([#740](https://github.com/xability/py-maidr/pull/740),
  [`a2ebade`](https://github.com/xability/py-maidr/commit/a2ebadea2bbeb27f453519bfa5b0ee2d9ff12d5f))

- **ci**: Stop the page-size report failing the docs build with SIGPIPE
  ([#769](https://github.com/xability/py-maidr/pull/769),
  [`32e9495`](https://github.com/xability/py-maidr/commit/32e9495888e4bf6e1883ac50570acc624ce4cb14))

- **ci**: Wait out the registry's publish lag when fetching a just-released bundle
  ([#806](https://github.com/xability/py-maidr/pull/806),
  [`f0fb131`](https://github.com/xability/py-maidr/commit/f0fb13151be342a83d08d483a2e2c5e572a32038))

- **clear**: Drop the layers on the child axes a clear discards
  ([#795](https://github.com/xability/py-maidr/pull/795),
  [`930ed40`](https://github.com/xability/py-maidr/commit/930ed404683958f9123bd79189cdf13eeb32e49f))

- **dodged**: Read a hue level missing a category as a gap
  ([#764](https://github.com/xability/py-maidr/pull/764),
  [`16d1e21`](https://github.com/xability/py-maidr/commit/16d1e21b9af75e520c6f98cbbb2e35e53b383a16))

- **dotpad**: Refuse a manifest path that leaves its directory
  ([#787](https://github.com/xability/py-maidr/pull/787),
  [`8e8e8b9`](https://github.com/xability/py-maidr/commit/8e8e8b9fec8912ad93c1c2e1bae427775f07f57a))

- **format**: Announce percent axes at matplotlib's scale and date axes from their day numbers
  ([#722](https://github.com/xability/py-maidr/pull/722),
  [`914ac98`](https://github.com/xability/py-maidr/commit/914ac98e6186b2f33dab87896ad89d842a063dba))

- **highlight**: Leave gids alone outside a render and keep a user-set gid inside one
  ([#757](https://github.com/xability/py-maidr/pull/757),
  [`0ab9c67`](https://github.com/xability/py-maidr/commit/0ab9c675a6eba68a7305fc8b331593aaeb5ce3a2))

- **kdeplot**: Register only the curves and bands this call drew
  ([#736](https://github.com/xability/py-maidr/pull/736),
  [`75570bf`](https://github.com/xability/py-maidr/commit/75570bfaba2e77da2bfab1d69620edaefef15600))

- **mplfinance**: Show a plain mpf.plot() and keep addplot labels
  ([#747](https://github.com/xability/py-maidr/pull/747),
  [`f81f34c`](https://github.com/xability/py-maidr/commit/f81f34cd65e337344675b2b5f53d932c0676b64f))

- **patch**: Resolve data= column names in fill_between, stackplot and errorbar
  ([#738](https://github.com/xability/py-maidr/pull/738),
  [`e652ac0`](https://github.com/xability/py-maidr/commit/e652ac0b8f2536addc5570ab1ed0306e2bdf77b6))

- **pie**: Walk matplotlib's counterclockwise slices clockwise so Right moves clockwise
  ([#800](https://github.com/xability/py-maidr/pull/800),
  [`23caf76`](https://github.com/xability/py-maidr/commit/23caf76acffe46294961056950f42b83a42fbf13))

- **plotly**: Compute box statistics the way plotly draws them and bound the violin kernel's memory
  ([#724](https://github.com/xability/py-maidr/pull/724),
  [`b28b500`](https://github.com/xability/py-maidr/commit/b28b500b690219fb34adbf9284cc55654bd89f0a))

- **plotly**: Give the polar trace position the default its factory assumes
  ([#799](https://github.com/xability/py-maidr/pull/799),
  [`df0e446`](https://github.com/xability/py-maidr/commit/df0e446db3c8e12d8e54bd43d560cd58c6b14922))

- **plotly**: Read date axes as ISO strings and bin a histogram over its finite samples
  ([#729](https://github.com/xability/py-maidr/pull/729),
  [`c3a1bdd`](https://github.com/xability/py-maidr/commit/c3a1bddeed98f7f6b35a9549793d1741f7d87ef4))

- **plotly**: Rescale a groupnorm area to the shares plotly draws
  ([#751](https://github.com/xability/py-maidr/pull/751),
  [`8c444a3`](https://github.com/xability/py-maidr/commit/8c444a320357fde6456e95765e3ea3f4556e6582))

- **plotly**: Weight parcats rows by a scalar counts and give an empty pie no grid cell
  ([#734](https://github.com/xability/py-maidr/pull/734),
  [`c5b5d7f`](https://github.com/xability/py-maidr/commit/c5b5d7f4708a3cf9365fd831e678de7bb7aa9051))

- **regplot**: Match a phrase keyword on word boundaries; pin autobin blank count
  ([#756](https://github.com/xability/py-maidr/pull/756),
  [`bc3baff`](https://github.com/xability/py-maidr/commit/bc3baff9c7a9f8973271d9851fd74082751bf119))

- **regplot**: Match a smooth keyword as a whole word so 'Profit' is not a fit
  ([#733](https://github.com/xability/py-maidr/pull/733),
  [`cf6165e`](https://github.com/xability/py-maidr/commit/cf6165eef69a856c8bffb0f3086480f132d2ade6))

- **schema**: Emit a gap rather than a NaN token for heatmap cells, stacked bars and areas
  ([#727](https://github.com/xability/py-maidr/pull/727),
  [`36558d1`](https://github.com/xability/py-maidr/commit/36558d1630370ed98865484c75e6dfa80bc6ec6f))

- **step**: Resolve stepDirection from the data-bearing lines only
  ([#744](https://github.com/xability/py-maidr/pull/744),
  [`37bdc7d`](https://github.com/xability/py-maidr/commit/37bdc7d01474f8bcd01023974275a1f64d88ef64))

- **streamlit**: Warn when a render falls back to the current figure
  ([#737](https://github.com/xability/py-maidr/pull/737),
  [`d7bd109`](https://github.com/xability/py-maidr/commit/d7bd109f289c5291d23533ebddf615163f353198))

- **violin**: Match matplotlib dataset shapes and keep every violin's bottom level
  ([#746](https://github.com/xability/py-maidr/pull/746),
  [`9ade9db`](https://github.com/xability/py-maidr/commit/9ade9dba589301e384292e237c238aebb1bce265))

### Continuous Integration

- Keep the commit body out of the changelog ([#767](https://github.com/xability/py-maidr/pull/767),
  [`e785aad`](https://github.com/xability/py-maidr/commit/e785aad487d97fdf7489440725f5b5232e0e079a))

- Post Claude reviews as claude[bot] and let the reviewer run the tests
  ([#777](https://github.com/xability/py-maidr/pull/777),
  [`cbc03d5`](https://github.com/xability/py-maidr/commit/cbc03d509f10a94a60a7753d398377703946b364))

- Review every fork pull request, since author_association hides private members
  ([#782](https://github.com/xability/py-maidr/pull/782),
  [`d0fc0f6`](https://github.com/xability/py-maidr/commit/d0fc0f692ee498c610aa28f634f03452aeb28f57))

- Review fork pull requests again, without running their code
  ([#781](https://github.com/xability/py-maidr/pull/781),
  [`cf44788`](https://github.com/xability/py-maidr/commit/cf44788ad17a224420f227571d3df06901299fcd))

- Review fork pull requests from the diff, without fetching their code
  ([#783](https://github.com/xability/py-maidr/pull/783),
  [`2d42e82`](https://github.com/xability/py-maidr/commit/2d42e82710f6e8122ba389f1159397207d07df89))

- Stop setting the env scrub that keeps Claude Code from starting
  ([#779](https://github.com/xability/py-maidr/pull/779),
  [`72b10b0`](https://github.com/xability/py-maidr/commit/72b10b0de270f9a726b97528c05fa09855a0fde4))

- Tell the fork reviewer, too, to wait for CI in the foreground
  ([#785](https://github.com/xability/py-maidr/pull/785),
  [`ed087ff`](https://github.com/xability/py-maidr/commit/ed087ffe00bc9d665c9863515acf97b7187958d2))

- Test on python 3.13 and stop syncing the project for lint
  ([#750](https://github.com/xability/py-maidr/pull/750),
  [`84c6cf1`](https://github.com/xability/py-maidr/commit/84c6cf12a63851b9384386d5a71f00de3e07515d))

### Documentation

- Add keyboard shortcut table and the maidr-skill agent skill to the README
  ([`7596eb0`](https://github.com/xability/py-maidr/commit/7596eb0da0f2a226664e64dd761916bb5cbef442))

- Carry the landing-page copy-edits that survive review
  ([#793](https://github.com/xability/py-maidr/pull/793),
  [`c125bb5`](https://github.com/xability/py-maidr/commit/c125bb5ce1df748c7443d9a7bee3178b9ba66abb))

- Describe what py-maidr does in the README and package metadata
  ([#765](https://github.com/xability/py-maidr/pull/765),
  [`0e75347`](https://github.com/xability/py-maidr/commit/0e753471a0d5e4acca65515a386a84b0cf9fd72d))

- Keep every page under Googlebot's 2 MB fetch and add canonical, entity and citation metadata
  ([#768](https://github.com/xability/py-maidr/pull/768),
  [`e7f4a30`](https://github.com/xability/py-maidr/commit/e7f4a303b844b15a99495a5b660f9a11588fe01d))

- List Plotly under the supported visualization libraries
  ([#788](https://github.com/xability/py-maidr/pull/788),
  [`d2b2030`](https://github.com/xability/py-maidr/commit/d2b203005966501045e4bd907eeb0058a1bd9b48))

- Make the shortcut table canonical for help, chat and settings
  ([#789](https://github.com/xability/py-maidr/pull/789),
  [`f89b2d0`](https://github.com/xability/py-maidr/commit/f89b2d068314dd1a67d68816a80846802cd21829))

- Replace the AI instructions with the settings flow they describe today
  ([#790](https://github.com/xability/py-maidr/pull/790),
  [`7449693`](https://github.com/xability/py-maidr/commit/7449693ccfdbefa160706d5c4a606122c978d074))

- Rewrite CONTRIBUTING.md around uv and drop tox
  ([#745](https://github.com/xability/py-maidr/pull/745),
  [`d59a06d`](https://github.com/xability/py-maidr/commit/d59a06d62aaae3d25720d081b21eb5d70ff75f5a))

- Settle on one spelling, one capitalization and one plot-name form
  ([#792](https://github.com/xability/py-maidr/pull/792),
  [`02a2a82`](https://github.com/xability/py-maidr/commit/02a2a82ec976442ebafd780c4b08d999255dbe63))

- Source the downloads badge from pepy instead of pypistats
  ([#766](https://github.com/xability/py-maidr/pull/766),
  [`35fb1b5`](https://github.com/xability/py-maidr/commit/35fb1b59cc221f9f6a013e53df7d146321868f7b))

- State the real minimum Python version, and pin it to the metadata
  ([#791](https://github.com/xability/py-maidr/pull/791),
  [`4d34f58`](https://github.com/xability/py-maidr/commit/4d34f58b1ea5e4de472981313320d3c88f94720f))

- **seo**: Give reference managers real bibliographic metadata
  ([#770](https://github.com/xability/py-maidr/pull/770),
  [`ee8b008`](https://github.com/xability/py-maidr/commit/ee8b008e5dad8001de664ff9ba69dc5894e67253))

### Features

- Carry a downloaded DotPad SDK with offline documents
  ([#784](https://github.com/xability/py-maidr/pull/784),
  [`3f69287`](https://github.com/xability/py-maidr/commit/3f6928731d6126da531ad3ccfca1848f2c916120))

- **core**: Read a scikit-learn RocCurveDisplay as the ROC curve it draws
  ([#801](https://github.com/xability/py-maidr/pull/801),
  [`50d4cc3`](https://github.com/xability/py-maidr/commit/50d4cc370e8e0b48352b1f4b46273f7eda7a0ef0))

- **dotpad**: Read the SDK pins from the shipped manifest and move to 3.0.3
  ([#786](https://github.com/xability/py-maidr/pull/786),
  [`614efd8`](https://github.com/xability/py-maidr/commit/614efd8d30d80516bd93c955067a4d13ac350809))

- **iframe**: Let the chart frame reach a tactile display
  ([#602](https://github.com/xability/py-maidr/pull/602),
  [`459ff2c`](https://github.com/xability/py-maidr/commit/459ff2c0840617443f981ff86d112f411f6c6318))

- **pie**: Say where the dial starts and which way plotly drew it
  ([#802](https://github.com/xability/py-maidr/pull/802),
  [`4afccb1`](https://github.com/xability/py-maidr/commit/4afccb19f4c2d140db98eed2a6b2fa37782650a6))

- **plotly**: Outline a contour level with islands instead of declining the layer
  ([#797](https://github.com/xability/py-maidr/pull/797),
  [`627b39b`](https://github.com/xability/py-maidr/commit/627b39b5bdef898eb4390c83995c109edec4711f))

- **plotly**: Outline the region a choropleth reader is standing on
  ([#798](https://github.com/xability/py-maidr/pull/798),
  [`19d228a`](https://github.com/xability/py-maidr/commit/19d228a6affd9790073272e81e9da92c37b20d93))

- **shiny**: Serve the chart from a session route instead of over the websocket
  ([#803](https://github.com/xability/py-maidr/pull/803),
  [`25cc7a0`](https://github.com/xability/py-maidr/commit/25cc7a0dacf0b5a8fcbfc38df9910820377a3a5a))

### Performance Improvements

- **highlight**: Look each drawn artist up in a per-render dict instead of scanning the tagged list
  ([#723](https://github.com/xability/py-maidr/pull/723),
  [`2deadb3`](https://github.com/xability/py-maidr/commit/2deadb31744197e65dffdb83b4ff04be9f2b11ca))

- **import**: Do not import IPython, altair or shiny to learn they are not in use
  ([#732](https://github.com/xability/py-maidr/pull/732),
  [`cd88767`](https://github.com/xability/py-maidr/commit/cd88767683043755d53e8ec09c6f0380a409ea9b))

- **plotly**: Count autobin samples in numpy and trace contour curves without per-vertex calls
  ([#735](https://github.com/xability/py-maidr/pull/735),
  [`b1717b9`](https://github.com/xability/py-maidr/commit/b1717b94bbbfcf42700da00e0937ac4dd6d087f9))

- **render**: Embed the schema compactly, build the page once for the browser and read trace types
  off the layers ([#725](https://github.com/xability/py-maidr/pull/725),
  [`768056f`](https://github.com/xability/py-maidr/commit/768056f481ab8b348bd28f724c35bc85ef4db248))

- **scatter**: Stop re-sorting slots per point and rebuilding stand-ins to count
  ([#748](https://github.com/xability/py-maidr/pull/748),
  [`3094276`](https://github.com/xability/py-maidr/commit/30942766500826d145a64708270427c8a4f95fde))

- **stripplot**: Convert each distinct facecolour once instead of once per point
  ([#741](https://github.com/xability/py-maidr/pull/741),
  [`71ac31d`](https://github.com/xability/py-maidr/commit/71ac31de1008a1d91ed52e7979101931809ccc5e))

- **violin**: Settle the figure layout once per extraction instead of once per point
  ([#731](https://github.com/xability/py-maidr/pull/731),
  [`86a5021`](https://github.com/xability/py-maidr/commit/86a50214d3855e32d5e18719a1fcba109405372b))

### Refactoring

- Drop the unreachable LLM key injector ([#794](https://github.com/xability/py-maidr/pull/794),
  [`46b2f1a`](https://github.com/xability/py-maidr/commit/46b2f1ac4a0f1f13814fc014f2905857078a735e))

- Use US spelling in the Python source, as the docs now do
  ([#796](https://github.com/xability/py-maidr/pull/796),
  [`f885733`](https://github.com/xability/py-maidr/commit/f885733810fe43051e64a15b5fbbb86cbbb874fd))

### Testing

- Keep collection alive without the shiny or plotly extra and close figures after each test
  ([#743](https://github.com/xability/py-maidr/pull/743),
  [`fcbf8b5`](https://github.com/xability/py-maidr/commit/fcbf8b57bc18a349efd6c510c07302e2610fa791))

- Pin every matplotlib call that draws but is unread as a decision
  ([#805](https://github.com/xability/py-maidr/pull/805),
  [`5283f11`](https://github.com/xability/py-maidr/commit/5283f11d5ee7631a03fe07afdb9922087b7bd04a))

- **docs**: Run every gallery chunk and pin what each section emits
  ([#804](https://github.com/xability/py-maidr/pull/804),
  [`800e94c`](https://github.com/xability/py-maidr/commit/800e94c74f57d2df12a3b2217598859b82de65b5))


## v1.23.0 (2026-08-31)

### Bug Fixes

- **seaborn**: Read a box or boxen chart's grouping from the legend that names it
  ([#676](https://github.com/xability/py-maidr/pull/676),
  [`50b2197`](https://github.com/xability/py-maidr/commit/50b2197539de5c8bc14443e4246fa855cc1cf953))

- **seaborn-objects**: Name a colour split from the legend wherever it was put
  ([#673](https://github.com/xability/py-maidr/pull/673),
  [`c5c76f5`](https://github.com/xability/py-maidr/commit/c5c76f50ca3d27bd6953b1d24ca90828f1ce26f7))

- **seaborn-objects**: Split a colour-split Dash into one layer per level
  ([#682](https://github.com/xability/py-maidr/pull/682),
  [`0481e71`](https://github.com/xability/py-maidr/commit/0481e7119d01c1772c5750ed65c85b0cb2a9529c))

### Documentation

- Add a word cloud example to the gallery ([#689](https://github.com/xability/py-maidr/pull/689),
  [`686a7ef`](https://github.com/xability/py-maidr/commit/686a7efa2aeda4df8952f8a183ba715c658c385c))

- Add gallery examples for three experimental matplotlib plot types
  ([#690](https://github.com/xability/py-maidr/pull/690),
  [`6a9d780`](https://github.com/xability/py-maidr/commit/6a9d78089928e5c96dd98e02fab14a9f3fd4836b))

- Mark the roadmap's new plot types as experimental
  ([#687](https://github.com/xability/py-maidr/pull/687),
  [`110c135`](https://github.com/xability/py-maidr/commit/110c135eda776f12362f28d400bf82a9b60edfb7))

- Tell deck authors how to keep off-slide charts out of the tab order
  ([#686](https://github.com/xability/py-maidr/pull/686),
  [`99913b7`](https://github.com/xability/py-maidr/commit/99913b77fb5d3e4873286524cebab13092c1c395))

### Features

- Read a word cloud as its terms and their weights
  ([#688](https://github.com/xability/py-maidr/pull/688),
  [`451cf8a`](https://github.com/xability/py-maidr/commit/451cf8a925a979cf8f354c2a82477b7e38104e9d))

- **core**: Read a baseline-anchored vlines as the spike chart it draws
  ([#665](https://github.com/xability/py-maidr/pull/665),
  [`6e7900d`](https://github.com/xability/py-maidr/commit/6e7900d583bbb0901631bb8de91942e73c3eb0f7))

- **plotly**: Read a scatterpolargl as the radar it draws
  ([#669](https://github.com/xability/py-maidr/pull/669),
  [`18d9a56`](https://github.com/xability/py-maidr/commit/18d9a56f9485aa5d5b850b1360a77c3bbe4d4cda))

- **plotly**: Read a splom as the grid of scatters it draws
  ([#667](https://github.com/xability/py-maidr/pull/667),
  [`b1a6eeb`](https://github.com/xability/py-maidr/commit/b1a6eebef4bfe4866c2baea3b387103b219cedcd))

- **plotly**: Read the seven map traces that registered nothing
  ([#684](https://github.com/xability/py-maidr/pull/684),
  [`62a6b03`](https://github.com/xability/py-maidr/commit/62a6b0353c25ae45a3c453ac554256f3eb244b9b))

- **seaborn-objects**: Read a Band or a Range as the interval it draws
  ([#677](https://github.com/xability/py-maidr/pull/677),
  [`a592ca4`](https://github.com/xability/py-maidr/commit/a592ca4dbba56ef4963008015972eeac4bc5ccf2))

- **seaborn-objects**: Read a Bars mark as the histogram it draws
  ([#678](https://github.com/xability/py-maidr/pull/678),
  [`a701761`](https://github.com/xability/py-maidr/commit/a7017618c05ecbd168f6e32ee6b26bfa658c8728))

- **seaborn-objects**: Read a Dash mark as the scatter of ticks it draws
  ([#679](https://github.com/xability/py-maidr/pull/679),
  [`6d06e30`](https://github.com/xability/py-maidr/commit/6d06e30cc7eed71a1018a37cb8da024515bd5b87))

- **seaborn-objects**: Read a Lines or Paths mark as the line it draws
  ([#675](https://github.com/xability/py-maidr/pull/675),
  [`8a44ebf`](https://github.com/xability/py-maidr/commit/8a44ebf2d08863d80648c8b78638d97be76e00ed))

- **seaborn-objects**: Read a Text mark as the labelled scatter it draws
  ([#681](https://github.com/xability/py-maidr/pull/681),
  [`2105f9e`](https://github.com/xability/py-maidr/commit/2105f9ee8fed780349f3d64d39cc0f2f3b350385))

- **seaborn-objects**: Read an Area mark as the band it draws
  ([#671](https://github.com/xability/py-maidr/pull/671),
  [`fec7c1e`](https://github.com/xability/py-maidr/commit/fec7c1e2cba7e629e4f768939bf7689cd0073f8b))


## v1.22.0 (2026-08-24)

### Bug Fixes

- **altair**: Say that use_cdn=False cannot be honoured, instead of ignoring it
  ([#523](https://github.com/xability/py-maidr/pull/523),
  [`263dc4e`](https://github.com/xability/py-maidr/commit/263dc4e4f8c47d9f3db6a955252b92e43a5db5fe))

- **area**: Name the axis a sideways band was actually drawn against
  ([#567](https://github.com/xability/py-maidr/pull/567),
  [`dae2a5b`](https://github.com/xability/py-maidr/commit/dae2a5b4f757c75f27ef4e0ec5cbb7efa036d609))

- **box**: Announce every box a hue-grouped box plot draws
  ([#594](https://github.com/xability/py-maidr/pull/594),
  [`beda9fa`](https://github.com/xability/py-maidr/commit/beda9fa09b3615b7050da9a5c3085cd3cc6c3ce8))

- **box**: Name each catplot box layer for the level it holds
  ([#596](https://github.com/xability/py-maidr/pull/596),
  [`f9be78b`](https://github.com/xability/py-maidr/commit/f9be78bfc4d9cbed836ef96754504eaae70fefb4))

- **cdn**: Pin to the bundled version when the resolver answers backwards
  ([#509](https://github.com/xability/py-maidr/pull/509),
  [`38a44fb`](https://github.com/xability/py-maidr/commit/38a44fbf4b7a50b23460dcc713f8b2222ebf0317))

- **core**: Make figure registration atomic ([#506](https://github.com/xability/py-maidr/pull/506),
  [`6629cb4`](https://github.com/xability/py-maidr/commit/6629cb407a610e91bab78bed24da606f7729c7e8))

- **core**: Read a bivariate histogram as the heatmap it draws
  ([#525](https://github.com/xability/py-maidr/pull/525),
  [`fe5a46b`](https://github.com/xability/py-maidr/commit/fe5a46b8a13b4f120c411dc89ed70a9db9a1d315))

- **core**: Render one figure at a time for every caller, not just two doors
  ([#538](https://github.com/xability/py-maidr/pull/538),
  [`7a2640b`](https://github.com/xability/py-maidr/commit/7a2640b092f042029619c5694890182defd3c124))

- **core**: Stop a colorbar from moving its panel out of its grid position
  ([#519](https://github.com/xability/py-maidr/pull/519),
  [`c113708`](https://github.com/xability/py-maidr/commit/c1137083c999af107d7d6970b196ab148ffe8c16))

- **core**: Stop a single empty grid position from breaking the whole figure
  ([#512](https://github.com/xability/py-maidr/pull/512),
  [`db766a1`](https://github.com/xability/py-maidr/commit/db766a1d030aed9e00b419ab3cbf7a906402050a))

- **core**: Stop emitting a layout gridspec's padding as empty panels
  ([#517](https://github.com/xability/py-maidr/pull/517),
  [`6a0817f`](https://github.com/xability/py-maidr/commit/6a0817f72bbeb579dabd667edbd81ba138bd0eb5))

- **core**: Stop reading a figure caption as every panel's x-axis label
  ([#516](https://github.com/xability/py-maidr/pull/516),
  [`2d85781`](https://github.com/xability/py-maidr/commit/2d857818f8f05e718f34aba0af05c292396b412e))

- **core**: Stop retaining every figure for the life of the process
  ([#508](https://github.com/xability/py-maidr/pull/508),
  [`df1e9d5`](https://github.com/xability/py-maidr/commit/df1e9d5d2a023cffd457149363bb844fa24160f6))

- **ecdf**: Name each curve of a hue-grouped ECDF from its own colour
  ([#584](https://github.com/xability/py-maidr/pull/584),
  [`74a8813`](https://github.com/xability/py-maidr/commit/74a881380927c53ddcfba714e279560e04da689b))

- **extract**: Bind a layer to the artist its own call drew
  ([#554](https://github.com/xability/py-maidr/pull/554),
  [`86d5b40`](https://github.com/xability/py-maidr/commit/86d5b405614e62c0518df4d1b7abcd357b3298ee))

- **heatmap**: Name a heatmap's cells from the grid, not from the axis ticks
  ([#551](https://github.com/xability/py-maidr/pull/551),
  [`54eb6da`](https://github.com/xability/py-maidr/commit/54eb6daaf6ed725058dd19f4467c324ccb4950b3))

- **heatmap**: Tell a picture from a grid of values instead of dying on both
  ([#565](https://github.com/xability/py-maidr/pull/565),
  [`6d1e0ee`](https://github.com/xability/py-maidr/commit/6d1e0ee33160b5ed7aaf21666e15a0d29374d7e4))

- **hist**: Name the hue groups of a filled step or poly histogram
  ([#589](https://github.com/xability/py-maidr/pull/589),
  [`5c24824`](https://github.com/xability/py-maidr/commit/5c24824cc2fe11d62348f489b9626943818c745d))

- **hist**: Read a multi-dataset histogram instead of raising on it
  ([#556](https://github.com/xability/py-maidr/pull/556),
  [`1bf3713`](https://github.com/xability/py-maidr/commit/1bf37134175f66e28060ac2be1a77d6a86db3574))

- **hist**: Read every group of a hue-grouped histogram, not just the first
  ([#559](https://github.com/xability/py-maidr/pull/559),
  [`3043d3b`](https://github.com/xability/py-maidr/commit/3043d3b46bf9292f46acb6db388a9c6aff21ba77))

- **hue**: Name a faceted panel's lone group from the legend that names it
  ([#609](https://github.com/xability/py-maidr/pull/609),
  [`40a8ba4`](https://github.com/xability/py-maidr/commit/40a8ba40ce5a77621ed9fef95b342c3a2a9b6bf8))

- **hue**: Name a pairplot's diagonals from the legend it builds afterwards
  ([#569](https://github.com/xability/py-maidr/pull/569),
  [`dc925ba`](https://github.com/xability/py-maidr/commit/dc925bad26c9828c3a028a5e39138497661f52e2))

- **hue**: Name an lmplot's hue groups from the legend that names their colours
  ([#613](https://github.com/xability/py-maidr/pull/613),
  [`adcc871`](https://github.com/xability/py-maidr/commit/adcc8711653cb85848ce6040b0fb8cb36bbe0266))

- **hue**: Read a shared-axis panel's legend, so a jointplot's marginals are named
  ([#611](https://github.com/xability/py-maidr/pull/611),
  [`eac5141`](https://github.com/xability/py-maidr/commit/eac51417c27876439d4294f19ca560c809801f8b))

- **kde**: Name each curve of a hue-grouped density, not just its bars
  ([#560](https://github.com/xability/py-maidr/pull/560),
  [`ff7dbd6`](https://github.com/xability/py-maidr/commit/ff7dbd6e686afd226baca2769156b9354c2051a3))

- **line**: Carry the interval a chart shades around a line
  ([#563](https://github.com/xability/py-maidr/pull/563),
  [`0755aa0`](https://github.com/xability/py-maidr/commit/0755aa0a04e608495efdb01c7125c70991e953f7))

- **line**: Decline a band shaded across the page rather than up it
  ([#603](https://github.com/xability/py-maidr/pull/603),
  [`e83a56a`](https://github.com/xability/py-maidr/commit/e83a56a5c4b3ea4d72458063c72592e9def07574))

- **line**: Name each series from the legend entry that is its own
  ([#581](https://github.com/xability/py-maidr/pull/581),
  [`c136e5a`](https://github.com/xability/py-maidr/commit/c136e5a88ca3a308f6ea36c9ef359d46dff9beb4))

- **line**: Stop announcing matplotlib's own label as a series name
  ([#576](https://github.com/xability/py-maidr/pull/576),
  [`056b433`](https://github.com/xability/py-maidr/commit/056b433071526e4e1105aaeaf84f5a71ccaf4a92))

- **patch**: A drawing call that drew nothing registers nothing
  ([#624](https://github.com/xability/py-maidr/pull/624),
  [`f6ce07c`](https://github.com/xability/py-maidr/commit/f6ce07c156caef6275dc5f84ac71d44dfe1ff044))

- **patch**: Forget a cleared axes' layers instead of appending beside them
  ([#500](https://github.com/xability/py-maidr/pull/500),
  [`9a4a690`](https://github.com/xability/py-maidr/commit/9a4a6900fbad959927f443e19b0ba906a11e4b0c))

- **patch**: Say which seaborn is installed when it is too old
  ([#486](https://github.com/xability/py-maidr/pull/486),
  [`f90fde5`](https://github.com/xability/py-maidr/commit/f90fde5d24321bada544f1a523d990611c9c5c8b))

- **plotly**: Decline a category order on a date axis too
  ([#493](https://github.com/xability/py-maidr/pull/493),
  [`086d2e6`](https://github.com/xability/py-maidr/commit/086d2e6d86d0bb723b2c33fa64d5231c31daca19))

- **plotly**: Drop a layer whose payload holds nothing
  ([#638](https://github.com/xability/py-maidr/pull/638),
  [`686758f`](https://github.com/xability/py-maidr/commit/686758f1523bbde91eb7d1c709dedf1fd4f1880b))

- **plotly**: Emit a heatmap top row first so ArrowUp moves up
  ([#488](https://github.com/xability/py-maidr/pull/488),
  [`1a31dd5`](https://github.com/xability/py-maidr/commit/1a31dd5d777cdded7fa52fed7244e4541c8cdad1))

- **plotly**: Fill a contour's holes before tracing it, the way plotly does
  ([#654](https://github.com/xability/py-maidr/pull/654),
  [`b88554a`](https://github.com/xability/py-maidr/commit/b88554a396f89a1e4d396c670f7d08b12c6028a5))

- **plotly**: Honour a bin spec that names a start or an end but no size
  ([#652](https://github.com/xability/py-maidr/pull/652),
  [`ef1b59f`](https://github.com/xability/py-maidr/commit/ef1b59fae5715e658dc26ffd4affc5846c338529))

- **plotly**: Name a markers-only radar's markers, not a path it has none of
  ([#657](https://github.com/xability/py-maidr/pull/657),
  [`a02ab88`](https://github.com/xability/py-maidr/commit/a02ab8841b42e3ecdd54efe68cebae54157b0067))

- **plotly**: Read a bar chart in the order categoryorder draws it
  ([#614](https://github.com/xability/py-maidr/pull/614),
  [`58d9f2b`](https://github.com/xability/py-maidr/commit/58d9f2b30b0d28e245ead18d9fd708f093cbbd99))

- **plotly**: Read a heatmap in the order plotly draws it
  ([#491](https://github.com/xability/py-maidr/pull/491),
  [`8beebeb`](https://github.com/xability/py-maidr/commit/8beebebb6e411510e959ca361c474b7cefca21dd))

- **plotly**: Round a bin width up strictly, the way plotly does
  ([#648](https://github.com/xability/py-maidr/pull/648),
  [`eebbdf7`](https://github.com/xability/py-maidr/commit/eebbdf7d5aea9bbfb8bc52fe07f780ecd8002081))

- **plotly**: Scope a heatmap's selector to its own image
  ([#655](https://github.com/xability/py-maidr/pull/655),
  [`6a38c21`](https://github.com/xability/py-maidr/commit/6a38c213d3576731302cf3bcd0a6a7435ba41fec))

- **pointplot**: Keep a hued point plot's confidence intervals
  ([#501](https://github.com/xability/py-maidr/pull/501),
  [`5095f3d`](https://github.com/xability/py-maidr/commit/5095f3d5fbd3a1ff8605c6ab74a4e9bf8f7190a8))

- **pointplot**: Name a hue group by the colour it was drawn in
  ([#507](https://github.com/xability/py-maidr/pull/507),
  [`1b2ca24`](https://github.com/xability/py-maidr/commit/1b2ca24abe00f37d4fd183ea7b1b202482d20d01))

- **seaborn**: An empty scatterplot no longer announces the previous call's points
  ([#625](https://github.com/xability/py-maidr/pull/625),
  [`036bdf7`](https://github.com/xability/py-maidr/commit/036bdf7f0a7923900dcb2dc5139c6c9c24d0f172))

- **seaborn**: Split a colour-grouped seaborn.objects bar, and get its categories back
  ([#619](https://github.com/xability/py-maidr/pull/619),
  [`10cb434`](https://github.com/xability/py-maidr/commit/10cb434dc1c536ca53dae5b4ab804b6fc9ea174f))

- **seaborn**: Split a colour-grouped seaborn.objects scatter into its groups
  ([#618](https://github.com/xability/py-maidr/pull/618),
  [`bad5cc2`](https://github.com/xability/py-maidr/commit/bad5cc2abfa45e4422cf667f6ff6a28c28cdea0f))

- **shiny**: Keep the reader on the chart across a re-render
  ([#485](https://github.com/xability/py-maidr/pull/485),
  [`9fe0978`](https://github.com/xability/py-maidr/commit/9fe09781ede781ee9a9a2651f9b88f33da217a9a))

- **streamlit**: Render one figure at a time, as the Shiny door already does
  ([#531](https://github.com/xability/py-maidr/pull/531),
  [`dbaa35c`](https://github.com/xability/py-maidr/commit/dbaa35cf3c947175762d59c1a3af403109b311d4))

- **triplot**: Decline a triangulation mesh instead of reading it as a line
  ([#573](https://github.com/xability/py-maidr/pull/573),
  [`5bc029d`](https://github.com/xability/py-maidr/commit/5bc029d2feb7f48ee095e3ab2a08a371ce9b7d3d))

- **util**: Let extract_collection answer where its caller handles None
  ([#552](https://github.com/xability/py-maidr/pull/552),
  [`1704abb`](https://github.com/xability/py-maidr/commit/1704abbe843e86d2fdc75bad57cc83279e0e5689))

### Continuous Integration

- Gate the release on the accessibility browser tests
  ([#492](https://github.com/xability/py-maidr/pull/492),
  [`b059ecd`](https://github.com/xability/py-maidr/commit/b059ecd91c54298f26e0b906746572a0dba908d0))

### Documentation

- Point the websocket-payload note at an issue that is still open
  ([#537](https://github.com/xability/py-maidr/pull/537),
  [`e057902`](https://github.com/xability/py-maidr/commit/e0579023dcf0a68152e5dea6c29edf37d7b4eb46))

- Stop telling Shiny users their event loop is blocked
  ([#511](https://github.com/xability/py-maidr/pull/511),
  [`af0ae1e`](https://github.com/xability/py-maidr/commit/af0ae1e831f9f28c5e788873cfa81654bde5f184))

- Tell Shiny readers what the render lock does not cover
  ([#549](https://github.com/xability/py-maidr/pull/549),
  [`58db3e5`](https://github.com/xability/py-maidr/commit/58db3e538bc5dea257550aad943f7b8476258466))

### Features

- **core**: Read a correlogram as the lollipop chart it draws
  ([#580](https://github.com/xability/py-maidr/pull/580),
  [`f1d9554`](https://github.com/xability/py-maidr/commit/f1d95540cef57506ac40b73324d506998ee3e64e))

- **core**: Read a hue-grouped scatter as one layer per group
  ([#545](https://github.com/xability/py-maidr/pull/545),
  [`5e316bd`](https://github.com/xability/py-maidr/commit/5e316bd456f939bbb690c770491dbc560803c351))

- **core**: Read ax.eventplot as the raster of event times it draws
  ([#550](https://github.com/xability/py-maidr/pull/550),
  [`c7cac64`](https://github.com/xability/py-maidr/commit/c7cac64cbc08efad2ffa0e377f95cac093bb26db))

- **core**: Read ax.tricontour as the field it draws
  ([#547](https://github.com/xability/py-maidr/pull/547),
  [`6af3358`](https://github.com/xability/py-maidr/commit/6af33589c35a21ac9cf7acdd65fa54e088210cfc))

- **core**: Read Axes.broken_barh as the gantt chart it draws
  ([#533](https://github.com/xability/py-maidr/pull/533),
  [`86bd78f`](https://github.com/xability/py-maidr/commit/86bd78f1b0144efea135cfd79c96fe19ade93d90))

- **core**: Read Axes.contour as the scalar field it draws
  ([#540](https://github.com/xability/py-maidr/pull/540),
  [`f076d98`](https://github.com/xability/py-maidr/commit/f076d98cde161a397431ee868315646d5d2ee0ab))

- **core**: Read Axes.stairs as the pre-binned histogram it draws
  ([#536](https://github.com/xability/py-maidr/pull/536),
  [`4e4537e`](https://github.com/xability/py-maidr/commit/4e4537e1ba2667676bf6a6330be96a45af6296f9))

- **core**: Read Axes.stem as the lollipop chart it draws
  ([#579](https://github.com/xability/py-maidr/pull/579),
  [`47af1ff`](https://github.com/xability/py-maidr/commit/47af1ff09968eee91be55e866884f798a94c62ca))

- **core**: Read the histogram seaborn draws as an outline
  ([#543](https://github.com/xability/py-maidr/pull/543),
  [`8167113`](https://github.com/xability/py-maidr/commit/81671137fe27d5bd23baa4ec8acf1007cc5ef915))

- **core**: Say when a figure was drawn into while it was being rendered
  ([#541](https://github.com/xability/py-maidr/pull/541),
  [`d2a7047`](https://github.com/xability/py-maidr/commit/d2a7047b95402bb329597c88b0adb94e9a11f479))

- **eventplot**: Give a raster the axis bounds its braille is built from
  ([#607](https://github.com/xability/py-maidr/pull/607),
  [`9d5b675`](https://github.com/xability/py-maidr/commit/9d5b675195ec92ba54f1bdb0936e38d1934da19f))

- **gantt**: Read hlines and vlines as the schedule of intervals they draw
  ([#570](https://github.com/xability/py-maidr/pull/570),
  [`8e951bb`](https://github.com/xability/py-maidr/commit/8e951bbaf363e3a5180436fbea3cc5f6bf911b6b))

- **heatmap**: Read ax.pcolorfast as the grid its three siblings draw
  ([#626](https://github.com/xability/py-maidr/pull/626),
  [`860678b`](https://github.com/xability/py-maidr/commit/860678b4697a9288fae7fc38eb82dcd5aad17a06))

- **hist**: Read a step-outlined histogram instead of falling back
  ([#557](https://github.com/xability/py-maidr/pull/557),
  [`4526f38`](https://github.com/xability/py-maidr/commit/4526f385bb5ef15b795c49b5f48265b8d5ff6122))

- **hist**: Read every element displot draws, not only bars
  ([#592](https://github.com/xability/py-maidr/pull/592),
  [`fafa76e`](https://github.com/xability/py-maidr/commit/fafa76ed94e2b4598e44b85f2b0e35f0c409b928))

- **hist**: Read the seaborn histogram outlines drawn without fill
  ([#585](https://github.com/xability/py-maidr/pull/585),
  [`df83461`](https://github.com/xability/py-maidr/commit/df834611eb998b8d224449c679c7fe6e0d123c26))

- **plotly**: Read a 2-D histogram as the heatmap it draws
  ([#645](https://github.com/xability/py-maidr/pull/645),
  [`9b4f660`](https://github.com/xability/py-maidr/commit/9b4f6602c3df476cd4b4fecfd1458c7f95643577))

- **plotly**: Read a choropleth map ([#641](https://github.com/xability/py-maidr/pull/641),
  [`38802c2`](https://github.com/xability/py-maidr/commit/38802c2df63778c22ae40bfddd975677760f6fa3))

- **plotly**: Read a contour at the levels its author declared
  ([#643](https://github.com/xability/py-maidr/pull/643),
  [`c190dbd`](https://github.com/xability/py-maidr/commit/c190dbd431ad4f0d1a667368e6ff0fdface2c054))

- **plotly**: Read a contour at the levels plotly picks for itself
  ([#649](https://github.com/xability/py-maidr/pull/649),
  [`c5ab6a8`](https://github.com/xability/py-maidr/commit/c5ab6a8ab80182df4676acc7f35fa163357511ff))

- **plotly**: Read a funnel trace ([#630](https://github.com/xability/py-maidr/pull/630),
  [`d669330`](https://github.com/xability/py-maidr/commit/d6693302df06a8e8999a7f17f6dc8cd065090670))

- **plotly**: Read a funnelarea trace ([#631](https://github.com/xability/py-maidr/pull/631),
  [`c614bd1`](https://github.com/xability/py-maidr/commit/c614bd1b34c16a8e45cafa7a43ccbdf107f38394))

- **plotly**: Read a histogram2dcontour as the contour of its binned counts
  ([#653](https://github.com/xability/py-maidr/pull/653),
  [`0cc4e0e`](https://github.com/xability/py-maidr/commit/0cc4e0eeb66f783159b2da73561d11d186d82d37))

- **plotly**: Read a parallel coordinates trace
  ([#637](https://github.com/xability/py-maidr/pull/637),
  [`5f0ae40`](https://github.com/xability/py-maidr/commit/5f0ae403388b888e85d95923f7bfc5cbb22afd47))

- **plotly**: Read a parallel sets trace ([#639](https://github.com/xability/py-maidr/pull/639),
  [`893dd52`](https://github.com/xability/py-maidr/commit/893dd5227a5c492338e87a37903c1bdf67cc0006))

- **plotly**: Read a sankey trace ([#634](https://github.com/xability/py-maidr/pull/634),
  [`9efd251`](https://github.com/xability/py-maidr/commit/9efd25174cacf676c8c82514ee6c10179f5251db))

- **plotly**: Read a waterfall trace ([#629](https://github.com/xability/py-maidr/pull/629),
  [`98e4ee8`](https://github.com/xability/py-maidr/commit/98e4ee80d5f16de0eb506b4207dd1bb43c00b44c))

- **plotly**: Read an indicator that draws a gauge
  ([#632](https://github.com/xability/py-maidr/pull/632),
  [`a5920d0`](https://github.com/xability/py-maidr/commit/a5920d0706c2aac01a9660ea438516716ae138c1))

- **plotly**: Read the three hierarchy paintings
  ([#633](https://github.com/xability/py-maidr/pull/633),
  [`8be278b`](https://github.com/xability/py-maidr/commit/8be278b70e08215385302a12e1bf00bd84c83581))

- **plotly**: Read the two polar traces ([#635](https://github.com/xability/py-maidr/pull/635),
  [`46b215e`](https://github.com/xability/py-maidr/commit/46b215ecb3e5c9712f988486ad32fe18eb5cd78e))

- **rug**: Give a rug the axis bounds its braille is built from
  ([#605](https://github.com/xability/py-maidr/pull/605),
  [`ff904ff`](https://github.com/xability/py-maidr/commit/ff904ff3aca808427fb8d31ef3f251ce76f68bc1))

- **rug**: Read a seaborn rug plot as the observations it marks
  ([#571](https://github.com/xability/py-maidr/pull/571),
  [`c07b98c`](https://github.com/xability/py-maidr/commit/c07b98cb28ba67e827ced3a809cf78932e09da32))

- **rug**: Read the hue a rug plot was grouped by
  ([#598](https://github.com/xability/py-maidr/pull/598),
  [`aff664d`](https://github.com/xability/py-maidr/commit/aff664d5dda22ac2c8c602c35ec47943e7f78ede))

- **scatter**: Read the hue a strip or swarm plot was grouped by
  ([#588](https://github.com/xability/py-maidr/pull/588),
  [`1bc1fc4`](https://github.com/xability/py-maidr/commit/1bc1fc4a966ba0975180cb7a2e6d74eb68b9bc47))

- **seaborn**: Name a strip or swarm layer by the category it holds
  ([#663](https://github.com/xability/py-maidr/pull/663),
  [`947558c`](https://github.com/xability/py-maidr/commit/947558c398f8d064d5630ee553fdf14d5c6becae))

- **seaborn**: Name every panel of a pairplot and a jointplot
  ([#661](https://github.com/xability/py-maidr/pull/661),
  [`60f8980`](https://github.com/xability/py-maidr/commit/60f898062d706c72eedc50e1f263314c761f53c6))

- **seaborn**: Read a seaborn.objects 100% stacked bar as one
  ([#622](https://github.com/xability/py-maidr/pull/622),
  [`2e645e7`](https://github.com/xability/py-maidr/commit/2e645e7a7448211cfe8b51ca59f50208d86b346a))

- **seaborn**: Read the marks of seaborn.objects, which registered nothing
  ([#616](https://github.com/xability/py-maidr/pull/616),
  [`4df5bd5`](https://github.com/xability/py-maidr/commit/4df5bd5e1b133d4e9c7befa421dda31bf5c168b2))

- **seaborn**: Type a colour-split seaborn.objects bar from its position transform
  ([#621](https://github.com/xability/py-maidr/pull/621),
  [`489c9f0`](https://github.com/xability/py-maidr/commit/489c9f052ee605665af348445052db217b6af5ce))

### Performance Improvements

- **shiny**: Render off the event loop, one render per figure at a time
  ([#504](https://github.com/xability/py-maidr/pull/504),
  [`1e46499`](https://github.com/xability/py-maidr/commit/1e46499df059df7a94e33649ba4ed4481e283b19))

### Refactoring

- **hue**: Give the shared hue-group tail one home
  ([#604](https://github.com/xability/py-maidr/pull/604),
  [`e1c16e1`](https://github.com/xability/py-maidr/commit/e1c16e1c9b463a868cb9a20cee3b3143a1ff0bff))

- **util**: Give CDN version resolution its own module
  ([#503](https://github.com/xability/py-maidr/pull/503),
  [`a48ffc6`](https://github.com/xability/py-maidr/commit/a48ffc65c45d3f8ac5c2e640a46a364bbd5178f7))

- **util**: Give the shared warning policy its own module
  ([#496](https://github.com/xability/py-maidr/pull/496),
  [`2e43684`](https://github.com/xability/py-maidr/commit/2e4368400d1fb78b2adb3998bb2bddf8894d2d2c))

- **util**: Move bundle staleness reporting into its own module
  ([#497](https://github.com/xability/py-maidr/pull/497),
  [`abf50bc`](https://github.com/xability/py-maidr/commit/abf50bc21bc7c52c5fc962313688e8c7d72b958f))

- **util**: Move the bundle capability check into its own module
  ([#494](https://github.com/xability/py-maidr/pull/494),
  [`c68e197`](https://github.com/xability/py-maidr/commit/c68e19754d74bbe20668959e0bc2a3d4206ad239))

### Testing

- **altair**: Hold the warning's script list to what the adapter fetches
  ([#528](https://github.com/xability/py-maidr/pull/528),
  [`e099ef8`](https://github.com/xability/py-maidr/commit/e099ef8dbc1fb1bf60f7caed5b03efb7235de629))

- **plotly**: Resolve every emitted selector against the chart it describes
  ([#659](https://github.com/xability/py-maidr/pull/659),
  [`44709c2`](https://github.com/xability/py-maidr/commit/44709c2972a80d9e97d2b730daba47f7508ec7f1))

- **shiny**: Assert concurrent renders of one figure agree, not just exclude
  ([#510](https://github.com/xability/py-maidr/pull/510),
  [`e3d5aa0`](https://github.com/xability/py-maidr/commit/e3d5aa00ef4d759ddc0cadebd6eab6929ce96889))

- **widget**: Cover the iframe a hosted render wraps the chart in
  ([#520](https://github.com/xability/py-maidr/pull/520),
  [`769803b`](https://github.com/xability/py-maidr/commit/769803bac03b7ccff0901a520670f34ea297ec09))


## v1.21.0 (2026-08-17)

### Bug Fixes

- Describe the lines a layer's own calls drew, and declare a seaborn floor that imports
  ([#442](https://github.com/xability/py-maidr/pull/442),
  [`7890d33`](https://github.com/xability/py-maidr/commit/7890d333bab1808843f131d551494ac06aa76895))

- Highlight the mark being read, and name the axis that carries the categories
  ([#359](https://github.com/xability/py-maidr/pull/359),
  [`8f5e8ed`](https://github.com/xability/py-maidr/commit/8f5e8ede214cc9f8a2f45c3d9ce65193d4e9f064))

- Read trace types from the enum, and report a positioned sample with no reading
  ([#437](https://github.com/xability/py-maidr/pull/437),
  [`05f9f15`](https://github.com/xability/py-maidr/commit/05f9f1548f56054b73babb9e5878d82ec922219f))

- **a11y**: Name the iframe every chart is rendered into
  ([#463](https://github.com/xability/py-maidr/pull/463),
  [`388885e`](https://github.com/xability/py-maidr/commit/388885ea12e0d08a7680d31c83714f1078ca1776))

- **api**: Fall back to a static image instead of raising a KeyError
  ([#444](https://github.com/xability/py-maidr/pull/444),
  [`7e88d90`](https://github.com/xability/py-maidr/commit/7e88d9042fbb8bdf0e0a95d56571077e5bb4216d))

- **bar**: Announce a bar's position when no tick label names it
  ([#383](https://github.com/xability/py-maidr/pull/383),
  [`7b9ae9c`](https://github.com/xability/py-maidr/commit/7b9ae9c7480897fc1c7e542431889b03054b8f0d))

- **bar**: Announce a segmented bar's position when no tick label names it
  ([#386](https://github.com/xability/py-maidr/pull/386),
  [`d2d3810`](https://github.com/xability/py-maidr/commit/d2d38105b9936dbed28602bb4357ac0385861ad7))

- **bar**: Ask per axes which bar layer supersedes which
  ([#377](https://github.com/xability/py-maidr/pull/377),
  [`b7d7f33`](https://github.com/xability/py-maidr/commit/b7d7f3375faf294e996728f9cbcb699a58819ae1))

- **bar**: Emit a bar with no height as a gap rather than as NaN
  ([#431](https://github.com/xability/py-maidr/pull/431),
  [`51ab7d4`](https://github.com/xability/py-maidr/commit/51ab7d494e4bf5e3a01b21a9c8e4f129e0edec18))

- **bar**: Read `left` as a stacked bar's baseline, as `bottom` is
  ([#387](https://github.com/xability/py-maidr/pull/387),
  [`ebf3fdc`](https://github.com/xability/py-maidr/commit/ebf3fdcaea3015a43bd97be89c24e56405e2edff))

- **bar**: Read the bars this call drew, not every bar on the axes
  ([#381](https://github.com/xability/py-maidr/pull/381),
  [`faba998`](https://github.com/xability/py-maidr/commit/faba9985e8fec9da09a1ada5c6dfc6f01c091738))

- **ci**: Keep breaking commits in the changelog
  ([#336](https://github.com/xability/py-maidr/pull/336),
  [`2d3ba0f`](https://github.com/xability/py-maidr/commit/2d3ba0fdd650eca19efcc7694a982d3bd80dea09))

- **colorbar**: A colorbar is a legend, not a second chart
  ([#370](https://github.com/xability/py-maidr/pull/370),
  [`344caec`](https://github.com/xability/py-maidr/commit/344caec2ae75bfcc462f3ede00b73c9f9953b6a4))

- **deps**: Declare the packages `import maidr` needs
  ([#474](https://github.com/xability/py-maidr/pull/474),
  [`da5e0e8`](https://github.com/xability/py-maidr/commit/da5e0e868b4f1725a159fdc6cd335c63295cc9a0))

- **deps**: Never resolve the CDN version on an event loop
  ([#363](https://github.com/xability/py-maidr/pull/363),
  [`b7d5294`](https://github.com/xability/py-maidr/commit/b7d52947755899669689c12c0b4f9a5cd709c8f8))

- **deps**: Stop emitting @latest on the failure path, and warn on a mistyped pin
  ([#367](https://github.com/xability/py-maidr/pull/367),
  [`1594502`](https://github.com/xability/py-maidr/commit/159450272a04ea2e600d5bd0058858f485ca2fba))

- **errorbar**: Emit only the estimates matplotlib drew
  ([#433](https://github.com/xability/py-maidr/pull/433),
  [`51c27d0`](https://github.com/xability/py-maidr/commit/51c27d049d2877a20ee542fbc33a6631abe987c1))

- **hist**: Do not read a 2D histogram as a bar histogram
  ([#389](https://github.com/xability/py-maidr/pull/389),
  [`b1e3ff3`](https://github.com/xability/py-maidr/commit/b1e3ff360d76594e3451150221d94fe2465302dd))

- **line**: Drop samples that have no position on the axis
  ([#430](https://github.com/xability/py-maidr/pull/430),
  [`ed59a84`](https://github.com/xability/py-maidr/commit/ed59a8465db40df1b88008cfc940e9af0dcdca43))

- **line**: Stop announcing a reference line as data
  ([#435](https://github.com/xability/py-maidr/pull/435),
  [`e745b24`](https://github.com/xability/py-maidr/commit/e745b246ea85e9dea3033434bdc203ea0575a589))

- **mplfinance**: Keep the title the caller gave the chart
  ([#465](https://github.com/xability/py-maidr/pull/465),
  [`554db5b`](https://github.com/xability/py-maidr/commit/554db5bc034934c6bcc86fe40426acbeb4c1b818))

- **plotly**: Address a box by its trace group and its position within it
  ([#417](https://github.com/xability/py-maidr/pull/417),
  [`a9cd784`](https://github.com/xability/py-maidr/commit/a9cd7841e43f037b380f0209c4bbf6c8f74ba12a))

- **plotly**: Aggregate a histogram's bars the way histfunc does
  ([#408](https://github.com/xability/py-maidr/pull/408),
  [`36a1e32`](https://github.com/xability/py-maidr/commit/36a1e323af88c95259018e464f9afa95337f9679))

- **plotly**: Announce a barnorm layer's shares rather than its counts
  ([#414](https://github.com/xability/py-maidr/pull/414),
  [`86d032b`](https://github.com/xability/py-maidr/commit/86d032b37ed1a0d445abdf65e7d47042e97bd584))

- **plotly**: Build no layer for a scatter trace that draws nothing
  ([#422](https://github.com/xability/py-maidr/pull/422),
  [`740068d`](https://github.com/xability/py-maidr/commit/740068d0223055ff70cec0bbf1737f7ce7811552))

- **plotly**: Do not read a trace the chart does not draw
  ([#400](https://github.com/xability/py-maidr/pull/400),
  [`19869e5`](https://github.com/xability/py-maidr/commit/19869e55fda3a95d5cc7717c00f712fe8d13692f))

- **plotly**: Emit the histogram bins plotly actually draws
  ([#406](https://github.com/xability/py-maidr/pull/406),
  [`d62760b`](https://github.com/xability/py-maidr/commit/d62760baceb19dff144dbf9412baa977d12f0b76))

- **plotly**: Generate the positions plotly generates when an axis is omitted
  ([#419](https://github.com/xability/py-maidr/pull/419),
  [`c8d3669`](https://github.com/xability/py-maidr/commit/c8d36693a1f86442237e929b61a214c811196643))

- **plotly**: Keep data and selector aligned when a series is empty
  ([#350](https://github.com/xability/py-maidr/pull/350),
  [`0faa7fc`](https://github.com/xability/py-maidr/commit/0faa7fc46677557afecb8430e2034b857afa7a36))

- **plotly**: Match a grouped histogram's layout to the orientation it declares
  ([#483](https://github.com/xability/py-maidr/pull/483),
  [`6f75119`](https://github.com/xability/py-maidr/commit/6f75119a3c61c684fb5a810c0cd293e24b079003))

- **plotly**: Number scatter positions by what plotly draws
  ([#420](https://github.com/xability/py-maidr/pull/420),
  [`2a2d6f3`](https://github.com/xability/py-maidr/commit/2a2d6f3361a89b2dbaa48cf0df034bf9729b2a52))

- **plotly**: Read a histogram's bins from the axis it bins
  ([#403](https://github.com/xability/py-maidr/pull/403),
  [`5eadbd9`](https://github.com/xability/py-maidr/commit/5eadbd974f9aee163cac7f008e8d47e2c19c96e3))

- **plotly**: Read a stacked bar chart as stacked
  ([#391](https://github.com/xability/py-maidr/pull/391),
  [`4b55b66`](https://github.com/xability/py-maidr/commit/4b55b66b0e3478687a67bb41c31726b2281b9d0e))

- **plotly**: Report when a plotly chart runs out of maidr.js sources
  ([#467](https://github.com/xability/py-maidr/pull/467),
  [`7e7ab26`](https://github.com/xability/py-maidr/commit/7e7ab26e09cd427a89774c9a5062872c464fc684))

- **plotly**: Rescale a histogram's bars the way histnorm does
  ([#407](https://github.com/xability/py-maidr/pull/407),
  [`8aab79e`](https://github.com/xability/py-maidr/commit/8aab79ebd6a2bccdaa3c5c76785e5e1156e3b8fe))

- **plotly**: Run the shared line-series pass once per render
  ([#362](https://github.com/xability/py-maidr/pull/362),
  [`897baa9`](https://github.com/xability/py-maidr/commit/897baa948347ad646805abf6038d8cd9282cddff))

- **plotly**: Say a horizontal bar chart is horizontal
  ([#481](https://github.com/xability/py-maidr/pull/481),
  [`a66b8f9`](https://github.com/xability/py-maidr/commit/a66b8f9a3fcd597bc7acc38dbdaa7da1a74686f3))

- **render**: Report when use_cdn="auto" runs out of sources
  ([#468](https://github.com/xability/py-maidr/pull/468),
  [`e92154e`](https://github.com/xability/py-maidr/commit/e92154ef6395a64bb9639f4fb52f1a9eae94d630))

- **scatter**: Emit only the points matplotlib drew
  ([#432](https://github.com/xability/py-maidr/pull/432),
  [`9b5f967`](https://github.com/xability/py-maidr/commit/9b5f967641570682220ca3d3a1f2cddbcdbee04c))

- **scatter**: Read the collection each scatter call drew
  ([#428](https://github.com/xability/py-maidr/pull/428),
  [`ac040cd`](https://github.com/xability/py-maidr/commit/ac040cdb51df844d793e4e45cf45fb0ea03de509))

- **seaborn**: A colour probe is not a chart ([#375](https://github.com/xability/py-maidr/pull/375),
  [`b2ff1eb`](https://github.com/xability/py-maidr/commit/b2ff1ebfff24bdb44cbe3facc94dfb0a15ed5462))

- **seaborn**: Patch boxplot and violinplot at both names too
  ([#374](https://github.com/xability/py-maidr/pull/374),
  [`c926e40`](https://github.com/xability/py-maidr/commit/c926e40d47ce712d8c2b0030cc560a05a000be77))

- **seaborn**: Patch each function at both names it answers to
  ([#372](https://github.com/xability/py-maidr/pull/372),
  [`4fbc97f`](https://github.com/xability/py-maidr/commit/4fbc97f4a8eb7690594d29569563ba98a704615c))

- **seaborn**: Read a binned regplot's intervals as uncertainty, not as fits
  ([#458](https://github.com/xability/py-maidr/pull/458),
  [`75c2c37`](https://github.com/xability/py-maidr/commit/75c2c375f865fb53bacdcbbe6adcef01642f95f7))

- **seaborn**: Read displot as the distribution it draws
  ([#447](https://github.com/xability/py-maidr/pull/447),
  [`66e5383`](https://github.com/xability/py-maidr/commit/66e538378dcfca8bd97be476c286c06ce290447d))

- **seaborn**: Read every catplot kind as the chart it draws
  ([#450](https://github.com/xability/py-maidr/pull/450),
  [`1d42eed`](https://github.com/xability/py-maidr/commit/1d42eed9e11c7e3ec2a18e5db6eef8a889c5610e))

- **shiny**: Let @output_args size a chart in Shiny Express
  ([#472](https://github.com/xability/py-maidr/pull/472),
  [`bf3ee9d`](https://github.com/xability/py-maidr/commit/bf3ee9d206d90638d080056ccbf3ccd78bdb2cdd))

- **smooth**: Ask per axes which curve supersedes which line
  ([#379](https://github.com/xability/py-maidr/pull/379),
  [`fe7b429`](https://github.com/xability/py-maidr/commit/fe7b4292ff45aa1acf6e3c55831b658fee888948))

- **violin**: Emit box statistics raw instead of rounded to four decimals
  ([#415](https://github.com/xability/py-maidr/pull/415),
  [`89f15a4`](https://github.com/xability/py-maidr/commit/89f15a4ae7b3f2ede390a88e127a49a59b6b9718))

- **violin**: Stop naming a violin after an axis tick
  ([#470](https://github.com/xability/py-maidr/pull/470),
  [`2725364`](https://github.com/xability/py-maidr/commit/2725364898eb6f39e05a097e548eb0adb95f5e1c))

### Continuous Integration

- Refresh the bundled maidr.js when upstream publishes
  ([#355](https://github.com/xability/py-maidr/pull/355),
  [`03228f7`](https://github.com/xability/py-maidr/commit/03228f704a1303dccbf73fe11ddf1f3a447ca960))

### Documentation

- Say that the render blocks the loop, and that "auto" has no offline path
  ([#471](https://github.com/xability/py-maidr/pull/471),
  [`7e2d4da`](https://github.com/xability/py-maidr/commit/7e2d4da3b0b4d5f528a54779245ca660e0b07973))

### Features

- Give a seaborn regression its confidence band
  ([#425](https://github.com/xability/py-maidr/pull/425),
  [`14a6477`](https://github.com/xability/py-maidr/commit/14a6477f9ac217dda75614a9b1d098563075532f))

- Read seaborn's categorical charts as their data rather than as how they were drawn
  ([#438](https://github.com/xability/py-maidr/pull/438),
  [`289c699`](https://github.com/xability/py-maidr/commit/289c699f8d6e4ed8fce273834d6c481471a41975))

- **area**: Read a baseline-to-curve fill_between as an area chart
  ([#371](https://github.com/xability/py-maidr/pull/371),
  [`0450d0e`](https://github.com/xability/py-maidr/commit/0450d0ebb2a36da17d3fc6fc8a00ce9bcc29acb9))

- **area**: Read a stackplot as the area chart it is
  ([#356](https://github.com/xability/py-maidr/pull/356),
  [`23c49e3`](https://github.com/xability/py-maidr/commit/23c49e309b489a475742dfc8c5cdb0fd18c096a7))

- **bundle**: Warn when the bundle cannot draw the layer being emitted
  ([#360](https://github.com/xability/py-maidr/pull/360),
  [`331b3b8`](https://github.com/xability/py-maidr/commit/331b3b824279122cd27613795b4d0ebf2e124c42))

- **deps**: Give the resolver's two silent failures a voice
  ([#366](https://github.com/xability/py-maidr/pull/366),
  [`0f3c5cf`](https://github.com/xability/py-maidr/commit/0f3c5cfd013a5dcfbb593298e2c7000a27b516b7))

- **deps**: Warn that the placeholder maidr.css accessors are going
  ([#334](https://github.com/xability/py-maidr/pull/334),
  [`0e5b645`](https://github.com/xability/py-maidr/commit/0e5b64526cd82445d8dfa70c67b7107cadb657f1))

- **errorbar**: Read an estimate together with its interval
  ([#349](https://github.com/xability/py-maidr/pull/349),
  [`791df0d`](https://github.com/xability/py-maidr/commit/791df0d5627532108b17edf824aebf08aa633362))

- **heatmap**: Highlight a pcolor grid, and cover z_label
  ([#347](https://github.com/xability/py-maidr/pull/347),
  [`cbb13c0`](https://github.com/xability/py-maidr/commit/cbb13c0f11e6358ad3a317470bfde5caf3666700))

- **heatmap**: Register pcolormesh and pcolor heatmaps
  ([#346](https://github.com/xability/py-maidr/pull/346),
  [`54cb65a`](https://github.com/xability/py-maidr/commit/54cb65af1adf1d74f9163d8ae760c92d34ec37b5))

- **hexbin**: Read Axes.hexbin as a hexagonal bin lattice
  ([#368](https://github.com/xability/py-maidr/pull/368),
  [`f723a86`](https://github.com/xability/py-maidr/commit/f723a86044247551d363d04f2acb008ba646a6de))

- **plotly**: Keep the step convention of a filled staircase
  ([#423](https://github.com/xability/py-maidr/pull/423),
  [`24734c0`](https://github.com/xability/py-maidr/commit/24734c0b0850829323d4f1002b6e698794389f61))

- **plotly**: Read a 100% stacked bar as one ([#393](https://github.com/xability/py-maidr/pull/393),
  [`1d5c9c7`](https://github.com/xability/py-maidr/commit/1d5c9c7901ceee55330e276f1d400b4e34b67b6e))

- **plotly**: Read a plotly.express trendline as a smooth layer
  ([#424](https://github.com/xability/py-maidr/pull/424),
  [`386eb38`](https://github.com/xability/py-maidr/commit/386eb3820600325d76d9d0676471706456061dd2))

- **plotly**: Read an area chart as an area rather than a line
  ([#411](https://github.com/xability/py-maidr/pull/411),
  [`86e3816`](https://github.com/xability/py-maidr/commit/86e3816159b81f4084fc84d20d0622d9e03e612a))

- **plotly**: Read candlestick and OHLC charts
  ([#396](https://github.com/xability/py-maidr/pull/396),
  [`393539c`](https://github.com/xability/py-maidr/commit/393539c3326cffa3000a930bb1a3db962c8c14d1))

- **plotly**: Read stacked and dodged histograms as one layer
  ([#410](https://github.com/xability/py-maidr/pull/410),
  [`879a40b`](https://github.com/xability/py-maidr/commit/879a40bcb40b26829848f9269830267dbe0839b4))

- **plotly**: Read violin plots ([#397](https://github.com/xability/py-maidr/pull/397),
  [`9ffc510`](https://github.com/xability/py-maidr/commit/9ffc510d76b8476083409320642cffb74e95a6ec))

- **pointplot**: Read a seaborn point plot's estimates with their intervals
  ([#352](https://github.com/xability/py-maidr/pull/352),
  [`e3a64c5`](https://github.com/xability/py-maidr/commit/e3a64c514ea32489e792b716d8b76c963cf0b1c8))

- **scatter**: Name the category a point sits in
  ([#445](https://github.com/xability/py-maidr/pull/445),
  [`64a1ef9`](https://github.com/xability/py-maidr/commit/64a1ef95cd3cf353f14bbd32ece65c71d14888e4))

- **shiny**: Rebuild render_maidr on Shiny's Renderer contract
  ([#452](https://github.com/xability/py-maidr/pull/452),
  [`2197548`](https://github.com/xability/py-maidr/commit/2197548420ef99db5891cda5dc9be3875bba4846))

- **streamlit**: Add a first-class Streamlit integration
  ([#459](https://github.com/xability/py-maidr/pull/459),
  [`1087b7a`](https://github.com/xability/py-maidr/commit/1087b7aca07f223940bf3d6e77bf616e0caaf833))

### Refactoring

- Drop the unreachable pyplot guard in `set_backend`
  ([#478](https://github.com/xability/py-maidr/pull/478),
  [`14faf9c`](https://github.com/xability/py-maidr/commit/14faf9ce09868c7e77b216a128cffa9dccb75a9c))

- Drop the useless matplotlib guard in `_activate_backend`
  ([#476](https://github.com/xability/py-maidr/pull/476),
  [`8e7836b`](https://github.com/xability/py-maidr/commit/8e7836b01eb618ff0466739a7bf91147d4823db3))

- **plotly**: Read the normalising barnorm values from one place
  ([#416](https://github.com/xability/py-maidr/pull/416),
  [`837bb36`](https://github.com/xability/py-maidr/commit/837bb360ca3e7c61192e75602bb7575ea05a7b53))

### Testing

- **bundle**: Stand in for an unbuildable trace with a name no release can ship
  ([#365](https://github.com/xability/py-maidr/pull/365),
  [`73b231a`](https://github.com/xability/py-maidr/commit/73b231ada4a2d5644c623ecffe771ca0ead26e8f))

- **heatmap**: Pin hist2d, which reads only by accident
  ([#348](https://github.com/xability/py-maidr/pull/348),
  [`b74a51e`](https://github.com/xability/py-maidr/commit/b74a51e1ba51bc59e66da669f93e62ae02fd07eb))

- **streamlit**: Cover the `components.v1.html` fallback end to end
  ([#479](https://github.com/xability/py-maidr/pull/479),
  [`93266d4`](https://github.com/xability/py-maidr/commit/93266d4577596430d15a275babc2d92b700842a0))


## v1.20.0 (2026-08-10)

### Bug Fixes

- **bar**: Bind a hued seaborn bar plot as a grouped layer
  ([#317](https://github.com/xability/py-maidr/pull/317),
  [`13002c3`](https://github.com/xability/py-maidr/commit/13002c3e377d0da9a05884d6b738482725b10763))

- **patch**: Draw every patched plot type through the scoped warning filter
  ([#330](https://github.com/xability/py-maidr/pull/330),
  [`c73d2c1`](https://github.com/xability/py-maidr/commit/c73d2c116677e842c732ff0c4add4ed1869e7045))

- **patch**: Read box and violin orientation the way matplotlib does
  ([#301](https://github.com/xability/py-maidr/pull/301),
  [`fcc52f4`](https://github.com/xability/py-maidr/commit/fcc52f40ef51d64603fa5f2d0cf0bf9a1f367614))

- **patch**: Serialise the warning suppression so concurrent draws cannot leak it
  ([#331](https://github.com/xability/py-maidr/pull/331),
  [`bc70987`](https://github.com/xability/py-maidr/commit/bc7098718f8a7c7fc196ea3a080061161ecbcf09))

- **plotly**: Decode typed arrays, and scope the patch warning filter to its call
  ([#327](https://github.com/xability/py-maidr/pull/327),
  [`d72822b`](https://github.com/xability/py-maidr/commit/d72822bfd350b47b99e70f38f4d8d32d013a4659))

- **plotly**: Resolve an absent mode the way plotly does before classifying
  ([#313](https://github.com/xability/py-maidr/pull/313),
  [`8c3f5ab`](https://github.com/xability/py-maidr/commit/8c3f5ab6d41abece553ecbb4277870d78f4ec013))

- **plotly**: Stop claiming a highlight for canvas-painted traces
  ([#314](https://github.com/xability/py-maidr/pull/314),
  [`7550aff`](https://github.com/xability/py-maidr/commit/7550aff5c9ae6ed3bc66af63a863ef32d066423c))

- **smooth**: Keep a regression line navigable point by point
  ([#319](https://github.com/xability/py-maidr/pull/319),
  [`8b190d0`](https://github.com/xability/py-maidr/commit/8b190d0dc32afe29c8919ffa0642ae9ca85fc8b9))

- **smooth**: Pace a smooth layer by drawn distance, not data distance
  ([#320](https://github.com/xability/py-maidr/pull/320),
  [`ffa24cf`](https://github.com/xability/py-maidr/commit/ffa24cf3f96ba5da8397f35a28510815537e8c93))

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

- **cdn**: Resolve @latest to a concrete version and report bundle drift
  ([#291](https://github.com/xability/py-maidr/pull/291),
  [`d865b4e`](https://github.com/xability/py-maidr/commit/d865b4e81719f3ddbe1f87f7904cf37f04e31c3f))

- **pie**: Support matplotlib and plotly pie charts
  ([#322](https://github.com/xability/py-maidr/pull/322),
  [`810c9ca`](https://github.com/xability/py-maidr/commit/810c9ca09ce0ab9f6d5060053fdb875ef0bc7f87))

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

- **smooth**: Move resample_curve out of the RDP module
  ([#321](https://github.com/xability/py-maidr/pull/321),
  [`4a107e9`](https://github.com/xability/py-maidr/commit/4a107e928d6c17e26b747421d8a329f7410f5618))

### Testing

- **plotly**: Cover steps beside bar/box traces and across a subplot grid
  ([#312](https://github.com/xability/py-maidr/pull/312),
  [`3875431`](https://github.com/xability/py-maidr/commit/3875431f54c015d507e70d475051a13014f333e2))


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


## v1.17.3 (2026-04-28)

### Bug Fixes

- Correct x-label for line plots ([#284](https://github.com/xability/py-maidr/pull/284),
  [`281d411`](https://github.com/xability/py-maidr/commit/281d411ffefa91603082bcff7bc2780b8eebc47a))


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

- Add SEO and GEO improvements ([#277](https://github.com/xability/py-maidr/pull/277),
  [`6830a11`](https://github.com/xability/py-maidr/commit/6830a1172e4181f31566846fc5fee8397be6e9b4))

- Address analytics PR review feedback ([#276](https://github.com/xability/py-maidr/pull/276),
  [`5fb4561`](https://github.com/xability/py-maidr/commit/5fb45617f2ecde8ea47c63e91e46cc26ef89de59))

### Features

- Add maidr as a matplotlib backend ([#263](https://github.com/xability/py-maidr/pull/263),
  [`816c6ed`](https://github.com/xability/py-maidr/commit/816c6ed259af228454d4c30a29fe0079773eba1f))


## v1.13.0 (2026-03-13)

### Features

- Support plotly ([#264](https://github.com/xability/py-maidr/pull/264),
  [`227361d`](https://github.com/xability/py-maidr/commit/227361d0d884d6742dc3bd2c8843df3cd126c840))


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

- Install claude github app ([#273](https://github.com/xability/py-maidr/pull/273),
  [`5b38610`](https://github.com/xability/py-maidr/commit/5b38610c3c646b05f53c5e1ed0b61a3b4ec29755))

- Sync uv.lock during semantic-release version bump
  ([#270](https://github.com/xability/py-maidr/pull/270),
  [`716b658`](https://github.com/xability/py-maidr/commit/716b658a1b880c00948877414038cb2c0b203ce5))

### Features

- Implement violin plot support with dual-layer registration
  ([#259](https://github.com/xability/py-maidr/pull/259),
  [`3abaf17`](https://github.com/xability/py-maidr/commit/3abaf175ba2a458e11cf10628a71a06d8c98f41e))


## v1.11.1 (2026-02-23)

### Bug Fixes

- Use UTF-8 encoding when saving HTML on Windows
  ([#266](https://github.com/xability/py-maidr/pull/266),
  [`a97e4c1`](https://github.com/xability/py-maidr/commit/a97e4c1ede879ad4e11b430a03c5b9042ad4e9f2))

### Continuous Integration

- Update uv.lock to match pyproject.toml v1.11.0
  ([#265](https://github.com/xability/py-maidr/pull/265),
  [`cb44939`](https://github.com/xability/py-maidr/commit/cb44939a50fc438467bda864dc6ede148b8b493b))


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


## v1.7.3 (2025-09-15)

### Bug Fixes

- Ensure all subplots are accessible and improve dodged plot detection
  ([#242](https://github.com/xability/py-maidr/pull/242),
  [`979b971`](https://github.com/xability/py-maidr/commit/979b9713d07be8bc9046056e7f1c0519336ddd22))


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


## v1.4.4 (2025-07-01)

### Bug Fixes

- Revert maidr-version npmjs fetch ([#208](https://github.com/xability/py-maidr/pull/208),
  [`969ee31`](https://github.com/xability/py-maidr/commit/969ee317c8fe47f204133ea685665e05b266c6d7))


## v1.4.3 (2025-06-27)

### Bug Fixes

- Address bugs in candlestick & line plots ([#207](https://github.com/xability/py-maidr/pull/207),
  [`0883878`](https://github.com/xability/py-maidr/commit/088387880e17abb3e9d72f937dd59c62193f8cb3))


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


## v1.1.0 (2025-06-18)

### Bug Fixes

- Address iframe tag issue in `save_html()` ([#192](https://github.com/xability/py-maidr/pull/192),
  [`97b3432`](https://github.com/xability/py-maidr/commit/97b3432d8ee6ceb7ba32d12462079c8f880e50e7))

- **boxplot**: Enhance outlier handling by separting outliers
  ([#180](https://github.com/xability/py-maidr/pull/180),
  [`102df14`](https://github.com/xability/py-maidr/commit/102df14a05d62dfe1b3a171d1a50ffbf2ecc8210))

### Features

- Add density layer support in kde and hist plot
  ([#189](https://github.com/xability/py-maidr/pull/189),
  [`d2cab63`](https://github.com/xability/py-maidr/commit/d2cab632c6519741fbb0e97e3a160a0c1e55cf50))


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

### Documentation

- **example**: Add `streamlit` dashboard demo with `maidr`
  ([#107](https://github.com/xability/py-maidr/pull/107),
  [`ae7bc15`](https://github.com/xability/py-maidr/commit/ae7bc15fabe2927c3377402eb4dbf4646dbe5806))

### Features

- Fetch LLM API keys from user env variables ([#102](https://github.com/xability/py-maidr/pull/102),
  [`fc84593`](https://github.com/xability/py-maidr/commit/fc84593a9b01904d24fd86da88f79e25db02417a))


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

- **commitlint**: Disable commitlint line length and total length checking
  ([#87](https://github.com/xability/py-maidr/pull/87),
  [`3f718a7`](https://github.com/xability/py-maidr/commit/3f718a7dd12c9569ef63c9318d120d00650b5995))

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

### Features

- Support syntaxless-api ([#47](https://github.com/xability/py-maidr/pull/47),
  [`415d6f1`](https://github.com/xability/py-maidr/commit/415d6f1c2c9bf3f62b29da1dd752cb34a18168a3))


## v0.2.0 (2024-05-16)

### Continuous Integration

- Setup pr github workflow ([#40](https://github.com/xability/py-maidr/pull/40),
  [`4ea4bb6`](https://github.com/xability/py-maidr/commit/4ea4bb6de14854dec9234dc36938d24ed04e9902))

- Setup release pipeline ([#42](https://github.com/xability/py-maidr/pull/42),
  [`634f91c`](https://github.com/xability/py-maidr/commit/634f91cdf5a806f2b451727ccc94b970c7af6a90))

### Documentation

- Add docstring ([#34](https://github.com/xability/py-maidr/pull/34),
  [`59f0ca1`](https://github.com/xability/py-maidr/commit/59f0ca1551643f9077fe2891af153e5038ddefe8))

- Add quarto and quartodoc for static website ([#38](https://github.com/xability/py-maidr/pull/38),
  [`011b1b2`](https://github.com/xability/py-maidr/commit/011b1b2b916df3036644d43cd6741f663ca64bc3))

### Features

- Use htmltools instead of str ([#33](https://github.com/xability/py-maidr/pull/33),
  [`8b0a838`](https://github.com/xability/py-maidr/commit/8b0a838bf7cd73ecd5e036d9be28e8ed0523a9ed))

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
