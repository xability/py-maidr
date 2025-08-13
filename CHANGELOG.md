# CHANGELOG


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

### Chores

- Revert semantic release plugin change ([#197](https://github.com/xability/py-maidr/pull/197),
  [`eda9f09`](https://github.com/xability/py-maidr/commit/eda9f09ee7a281616cb8918f5ba4308b3eff6724))


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

### Chores

- **vscode**: Add Copilot instructions and update VSCode settings for code generation
  ([`27f96fc`](https://github.com/xability/py-maidr/commit/27f96fc3351971fc9dc70c5ea03bb2ecf0e71084))

### Features

- Add 'maidr-data' attribute to SVG elements ([#138](https://github.com/xability/py-maidr/pull/138),
  [`25d2ee3`](https://github.com/xability/py-maidr/commit/25d2ee31d6f21054d6c3b907edcc194fd7370028))


## v0.11.0 (2025-02-19)

### Chores

- Update project metadata in pyproject.toml for version 0.10.6
  ([`3f3dcc1`](https://github.com/xability/py-maidr/commit/3f3dcc11b7f616654b23e9f01242e39aa93f1dbc))

- Update VSCode window title format to include activeEditorState
  ([`6b84d53`](https://github.com/xability/py-maidr/commit/6b84d53bde194ed9564fa17e17fef723b9636718))

### Features

- Add dodged bar plot support along with an matplotlib example
  ([#136](https://github.com/xability/py-maidr/pull/136),
  [`81197ce`](https://github.com/xability/py-maidr/commit/81197cef9f32746a53545713c63bfb8963b25c27))


## v0.10.6 (2025-02-11)

### Bug Fixes

- Stacked bar plot with new api ([#132](https://github.com/xability/py-maidr/pull/132),
  [`003be7c`](https://github.com/xability/py-maidr/commit/003be7cc1c4fbaa7d24df61ab85b1273cfe8f663))

### Chores

- Add instructions for conventional commit message format in VSCode settings
  ([`7940ce6`](https://github.com/xability/py-maidr/commit/7940ce654035ec51ee6d2342d6f29d2c2d8e822e))

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

### Chores

- Remove CNAME
  ([`452a594`](https://github.com/xability/py-maidr/commit/452a594f65575b170748c8c7fc5a27164b7d3f36))

- Update .gitignore to ignore all quarto_ipynb files
  ([`9d47725`](https://github.com/xability/py-maidr/commit/9d477256e517309efc92eca03ebd369946fef655))

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

### Chores

- Add CNAME file to redirect to py.maidr.ai
  ([`0268394`](https://github.com/xability/py-maidr/commit/02683945f55dfa1e5ec9486c7513c3936de52fbe))


## v0.10.3 (2024-12-06)

### Bug Fixes

- Update repository references from 'py_maidr' to 'py-maidr'
  ([`9749835`](https://github.com/xability/py-maidr/commit/9749835aeb81c58a5c750830f61ab6d4c1ec362d))

### Chores

- **vscode**: Format settings.json for clarity
  ([`2040c4a`](https://github.com/xability/py-maidr/commit/2040c4affbb81e5498ec7a2f624a4379d58d174f))

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

### Chores

- **semantic-release**: Update `exclude_commit_patterns` in pyproject.toml to clean up CHANGELOG
  ([`794816d`](https://github.com/xability/py-maidr/commit/794816d27d1289e6d8904a12ff06e077c1616b85))

### Documentation

- **example**: Update ipynb to exclude inline rendering
  ([#113](https://github.com/xability/py-maidr/pull/113),
  [`c6ee419`](https://github.com/xability/py-maidr/commit/c6ee419c3bfb28c48f80b9715eb177fd4a67c89f))


## v0.9.0 (2024-09-13)

### Chores

- Refactor ([#95](https://github.com/xability/py-maidr/pull/95),
  [`63b7f3f`](https://github.com/xability/py-maidr/commit/63b7f3fb791e7945d54ad6cdf73a7054ab5b7bea))

- Refactor ([#96](https://github.com/xability/py-maidr/pull/96),
  [`a37b0f1`](https://github.com/xability/py-maidr/commit/a37b0f1a0ef1ea79483a5cd06b32dcb43c837cfa))

- **vscode**: Add a missing space to window title format in `.vscode/settings.json`
  ([`aa739d3`](https://github.com/xability/py-maidr/commit/aa739d3111b3dcaadc50fc940ae1cbf57b65af67))

- **vscode**: Add Copilot instructions for coding style and documentation
  ([`b7037d8`](https://github.com/xability/py-maidr/commit/b7037d83a1e4485f178a26951d5187247602689b))

- **vscode**: Refine Copilot instruction
  ([`f049b44`](https://github.com/xability/py-maidr/commit/f049b441ab980c6e9a1c3f9a47ff7c16ecffe836))

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

### Chores

- Clean up messy CHANGELOG
  ([`20785a8`](https://github.com/xability/py-maidr/commit/20785a8b95ff17132c900dc96035814d34821974))

- Hide `chore` and `ci` updates from future release notes
  ([`e886067`](https://github.com/xability/py-maidr/commit/e88606736a9b9a481b5aa463e7231ca83f63521f))

- Update `poetry.lock`
  ([`ac89fd7`](https://github.com/xability/py-maidr/commit/ac89fd78d5df129caeef3c57518463a6812cf4fb))

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

### Chores

- Add bug report and feature request templates ([#81](https://github.com/xability/py-maidr/pull/81),
  [`5af72c2`](https://github.com/xability/py-maidr/commit/5af72c2cc1f01f4b1b1d1ac1944ed06c789891d8))

Added bug report and feature request templates to improve the issue creation process. These
  templates provide a standardized structure for reporting bugs and requesting new features, making
  it easier for contributors to provide clear and concise information. This will help streamline the
  issue triage and resolution process.

The bug report template includes sections for describing the bug, steps to reproduce, actual and
  expected behavior, screenshots, and additional information. The feature request template includes
  sections for describing the requested feature, motivation, proposed solution, and additional
  context.

This commit follows the established commit message convention of starting with a verb in the
  imperative form, followed by a brief description of the change. It also includes a type prefix
  ("feat") to indicate that it is a new feature.

closes #80

- **vscode**: Update shiny extension
  ([`483a075`](https://github.com/xability/py-maidr/commit/483a0758a68960de0670e36c312cfbc1ee90c110))

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

### Chores

- **vscode**: Update settings to use numpy docstring
  ([`e9b0c4d`](https://github.com/xability/py-maidr/commit/e9b0c4d08eacdb4d9e40e46ffd74e13799da42d7))

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

### Chores

- **deps-dev**: Bump black from 23.3.0 to 24.3.0
  ([#45](https://github.com/xability/py-maidr/pull/45),
  [`53818c9`](https://github.com/xability/py-maidr/commit/53818c9478301376461e64d1cf5a5d32ef730df2))

Bumps [black](https://github.com/psf/black) from 23.3.0 to 24.3.0. - [Release
  notes](https://github.com/psf/black/releases) -
  [Changelog](https://github.com/psf/black/blob/main/CHANGES.md) -
  [Commits](https://github.com/psf/black/compare/23.3.0...24.3.0)

--- updated-dependencies: - dependency-name: black dependency-type: direct:development ...

Signed-off-by: dependabot[bot] <support@github.com>

Co-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>

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

### Chores

- Add homepage URL to pyproject.toml
  ([`582a23f`](https://github.com/xability/py-maidr/commit/582a23f4bb98327edac8b8ae2ed60a59bbf6e3e4))

- Add more vscode settings and extensions
  ([`0bf19ba`](https://github.com/xability/py-maidr/commit/0bf19ba68094f46d08af7297a4c93c0e5215ad62))

- Remove spellright extension
  ([`85b7bdf`](https://github.com/xability/py-maidr/commit/85b7bdf590c9ed6a6b9588e6e33d22f502848bd1))

- Update project homepage URL
  ([`2aeb15c`](https://github.com/xability/py-maidr/commit/2aeb15c4625aface3db289d6e7634ed30516bb58))

- Update pyproject.toml with additional metadata
  ([`314cd38`](https://github.com/xability/py-maidr/commit/314cd386d2f6a4ecaa5635dd433bd68e9b67fe9b))

- Use copilot to describe pr
  ([`5bc8803`](https://github.com/xability/py-maidr/commit/5bc8803684eaaf17c34301b08a677a5b02bc505e))

- **.vscode**: :wrench: add conventional commits settings
  ([`7cb39cd`](https://github.com/xability/py-maidr/commit/7cb39cd1af091eecc35f448fbe20ff610f7ed7c8))

- **.vscode**: :wrench: add conventional commits settings
  ([`e8e782f`](https://github.com/xability/py-maidr/commit/e8e782f198cba310494ef817e71bddd0374ce58a))

- **.vscode**: Add conventional commits extensions
  ([`492d23f`](https://github.com/xability/py-maidr/commit/492d23ff70803ab2c82e71fee487c019ee743dd1))

- **vscode**: Add git.ignoreRebaseWarning setting to .vscode/settings.json
  ([`97c27a8`](https://github.com/xability/py-maidr/commit/97c27a8c694b3c84870a82bfb60d9ae05c6cbec2))

- **vscode**: Add GitLens extension
  ([`3491ecc`](https://github.com/xability/py-maidr/commit/3491ecc6e5f7ade3fc9fe78d2d31e7616a41215e))

- **vscode**: Add ms-python.debugpy extension to extensions.json
  ([`ac1b619`](https://github.com/xability/py-maidr/commit/ac1b61957db84631f6616787d404e4053ec5ab26))

- **vscode**: Remove brackets from the title
  ([`99ecd10`](https://github.com/xability/py-maidr/commit/99ecd10d4e7b19b05a22fd21276b5fcb54406e6a))

- **vscode**: Update window title in VS Code settings.json
  ([`065800e`](https://github.com/xability/py-maidr/commit/065800ede282c861678c71b0a3e258a6e2bd496f))

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
