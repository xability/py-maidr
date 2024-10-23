# CHANGELOG


## v0.10.2 (2024-10-17)

### Fixes

* fix: address iframe resizing issue in jupyter notebooks (#124) ([`b437831`](https://github.com/xability/py_maidr/commit/b43783130eaa34df7d47efc57b0eb2a5819d9986))


## v0.10.1 (2024-10-17)

### Fixes

* fix: correct import statement in maidr.py ([`e7d072a`](https://github.com/xability/py_maidr/commit/e7d072a3d94d573f06fd76c68cf57679f9c7584e))

* fix: address dynamic resizing of iframes on ipython (#123) ([`3159fc1`](https://github.com/xability/py_maidr/commit/3159fc1f4ccfff081f001bf41eff7b949b95a3c4))


## v0.10.0 (2024-10-15)

### Code Style

* style(example): replace `py-shiny` folder name with `shiny` ([`4bb9e77`](https://github.com/xability/py_maidr/commit/4bb9e7766a2dcdee1e8467750c14cbb891878074))

### Features

* feat(maidr.show): use tempfile for interactive sessions (#121) ([`ef668ee`](https://github.com/xability/py_maidr/commit/ef668ee2b9619883b3abbb6e9be3b9371b9372e6))


## v0.9.2 (2024-10-09)

### Documentation

* docs(example): update scripts to comment out `plt.show()` (#118) ([`164d6fa`](https://github.com/xability/py_maidr/commit/164d6fa0e038b04f323c1eba98536f65a09c306e))

### Fixes

* fix: suppress wrapt warning messages (#116)

Co-authored-by: JooYoung Seo <jseo1005@illinois.edu> ([`1283be5`](https://github.com/xability/py_maidr/commit/1283be5fe4c15012ae5385665f48da6300db69d0))


## v0.9.1 (2024-10-08)

### Chores

* chore(semantic-release): update `exclude_commit_patterns` in pyproject.toml to clean up CHANGELOG ([`794816d`](https://github.com/xability/py_maidr/commit/794816d27d1289e6d8904a12ff06e077c1616b85))

### Documentation

* docs(example): update ipynb to exclude inline rendering (#113) ([`c6ee419`](https://github.com/xability/py_maidr/commit/c6ee419c3bfb28c48f80b9715eb177fd4a67c89f))

### Fixes

* fix: address an issue where rendered result is not displayed when ipy… (#114) ([`ccb1ae4`](https://github.com/xability/py_maidr/commit/ccb1ae42d4cefb9ad6962ea2fe10813745405602))


## v0.9.0 (2024-09-13)

### Chores

* chore(vscode): refine Copilot instruction ([`f049b44`](https://github.com/xability/py_maidr/commit/f049b441ab980c6e9a1c3f9a47ff7c16ecffe836))

* chore(vscode): add Copilot instructions for coding style and documentation ([`b7037d8`](https://github.com/xability/py_maidr/commit/b7037d83a1e4485f178a26951d5187247602689b))

* chore(vscode): add a missing space to window title format in `.vscode/settings.json` ([`aa739d3`](https://github.com/xability/py_maidr/commit/aa739d3111b3dcaadc50fc940ae1cbf57b65af67))

* chore: refactor (#96) ([`a37b0f1`](https://github.com/xability/py_maidr/commit/a37b0f1a0ef1ea79483a5cd06b32dcb43c837cfa))

* chore: refactor (#95) ([`63b7f3f`](https://github.com/xability/py_maidr/commit/63b7f3fb791e7945d54ad6cdf73a7054ab5b7bea))

### Continuous Integration

* ci(semantic-release): exclude non-conventional commits from `CHANGELOG` (#106)

This pull request updates the `exclude_commit_patterns` in the
`pyproject.toml` file. The previous commits that don't match the
conventional commits prefixes and internal changes that do not
necessarily affect end-user interactions, such as `chore`, `ci`, and
`style`, are excluded from our CHANGELOG and GitHub release note moving
forward. This is not a direct fix, but after this change, it ensures
that only relevant commits are included in the release changelog as a
fair stopgap solution.

Closes #99 ([`d40a95c`](https://github.com/xability/py_maidr/commit/d40a95c1d380a43553328e246025faea760f5e04))

* ci: sort out semantic release config to display `feat` and `fix` first in the release notes ([`529c721`](https://github.com/xability/py_maidr/commit/529c721b6d0b70e5bfb6d2d46c40991027502ff2))

### Documentation

* docs(example): add `streamlit` dashboard demo with `maidr` (#107)

<!-- Suggested PR Title: [feat/fix/refactor/perf/test/ci/docs/chore] brief description of the change -->
<!-- Please follow Conventional Commits: https://www.conventionalcommits.org/en/v1.0.0/ -->

## Description
This PR includes an example streamlit web app to demonstrate interactivity capabilities with maidr. 

closes #84 

## Type of Change

- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change (fix or feature that would cause existing functionality to not work as expected)
- [x] Documentation update

## Checklist

- [x] My code follows the style guidelines of this project
- [x] I have performed a self-review of my code
- [x] I have commented my code, particularly in hard-to-understand areas
- [x] I have made corresponding changes to the documentation
- [x] My changes generate no new warnings
- [x] Any dependent changes have been merged and published in downstream modules

# Pull Request

## Description
Added a new file `example_streamlit_app.py` under streamlit folder in example directory.

## Screenshots (if applicable)
<img width="1964" alt="image" src="https://github.com/user-attachments/assets/bf3b5630-2e71-4057-87ad-5b9ca0940769"> ([`ae7bc15`](https://github.com/xability/py_maidr/commit/ae7bc15fabe2927c3377402eb4dbf4646dbe5806))

### Features

* feat: fetch LLM API keys from user env variables (#102)

<!-- Suggested PR Title: [feat/fix/refactor/perf/test/ci/docs/chore]
brief description of the change -->
<!-- Please follow Conventional Commits:
https://www.conventionalcommits.org/en/v1.0.0/ -->

## Description
This pull request fixes the handling of API keys for LLMs in the code.
It adds a JavaScript script to handle the API keys for LLMs and
initializes the LLM secrets in the MAIDR instance. The script injects
the LLM API keys into the MAIDR instance and sets the appropriate
settings based on the presence of the Gemini and OpenAI API keys. This
ensures that the LLM functionality works correctly with the updated API
key handling.

closes #76 

## Type of Change

- [x] Bug fix
- [ ] New feature
- [ ] Breaking change (fix or feature that would cause existing
functionality to not work as expected)
- [ ] Documentation update

## Checklist

- [x] My code follows the style guidelines of this project
- [x] I have performed a self-review of my code
- [x] I have commented my code, particularly in hard-to-understand areas
- [x] I have made corresponding changes to the documentation
- [x] My changes generate no new warnings
- [x] Any dependent changes have been merged and published in downstream
modules

# Pull Request

## Description
1. Added a new method called `initialize_llm_secrets()` in
environment.py which fetches the keys from the environment variable.
2. Injected the script when the maidr iframe loads initially.

## Checklist
<!-- Please select all applicable options. -->
<!-- To select your options, please put an 'x' in the all boxes that
apply. -->

- [x] I have read the [Contributor Guidelines](../CONTRIBUTING.md).
- [x] I have performed a self-review of my own code and ensured it
follows the project's coding standards.
- [x] I have tested the changes locally following
`ManualTestingProcess.md`, and all tests related to this pull request
pass.
- [x] I have commented my code, particularly in hard-to-understand
areas.
- [x] I have updated the documentation, if applicable.
- [x] I have added appropriate unit tests, if applicable.

## Additional Notes
<!-- Add any additional notes or comments here. -->
<!-- Template credit: This pull request template is based on Embedded
Artistry
{https://github.com/embeddedartistry/templates/blob/master/.github/PULL_REQUEST_TEMPLATE.md},
Clowder
{https://github.com/clowder-framework/clowder/blob/develop/.github/PULL_REQUEST_TEMPLATE.md},
and TalAter {https://github.com/TalAter/open-source-templates}
templates. --> ([`fc84593`](https://github.com/xability/py_maidr/commit/fc84593a9b01904d24fd86da88f79e25db02417a))


## v0.8.0 (2024-08-27)

### Build System

* build: remove `sphinx` from package dev dependencies ([`41f61a9`](https://github.com/xability/py_maidr/commit/41f61a915d9b3dea27419d984c8cd9408de794d5))

* build: move `black` formatter to `dev` dependencies ([`ca460b4`](https://github.com/xability/py_maidr/commit/ca460b4cca26418bee3cab2ce4949b96d5e60147))

### Chores

* chore: update `poetry.lock` ([`ac89fd7`](https://github.com/xability/py_maidr/commit/ac89fd78d5df129caeef3c57518463a6812cf4fb))

* chore: hide `chore` and `ci` updates from future release notes ([`e886067`](https://github.com/xability/py_maidr/commit/e88606736a9b9a481b5aa463e7231ca83f63521f))

* chore: clean up messy CHANGELOG ([`20785a8`](https://github.com/xability/py_maidr/commit/20785a8b95ff17132c900dc96035814d34821974))

### Features

* feat: pick up seaborn heatmap fmt towards maidr (#90) ([`fb5dde0`](https://github.com/xability/py_maidr/commit/fb5dde0c7b2d65f6649342ff5474f032e4e36bae))


## v0.7.0 (2024-08-24)

### Continuous Integration

* ci: rectify commit-lint job crash (#92)

<!-- Suggested PR Title: [feat/fix/refactor/perf/test/ci/docs/chore]
brief description of the change -->
<!-- Please follow Conventional Commits:
https://www.conventionalcommits.org/en/v1.0.0/ -->

## Description

This PR resolves an issue related to the `commit-lint` job in
`.github/workflows/ci.yml`.

Closes [#91]

## Type of Change

- [X] Bug fix
- [ ] New feature
- [ ] Breaking change (fix or feature that would cause existing
functionality to not work as expected)
- [ ] Documentation update

## Checklist

- [X] My code follows the style guidelines of this project
- [X] I have performed a self-review of my code
- [ ] I have commented my code, particularly in hard-to-understand areas
- [ ] I have made corresponding changes to the documentation
- [X] My changes generate no new warnings
- [ ] Any dependent changes have been merged and published in downstream
modules

# Pull Request

## Description
This PR addresses an issue where `commit-lint` job crashes when
validating pull requests.

## Changes Made
Currently, the commitlint config file is getting loaded as an ES module
whilst it contains vanilla javascript configurations. This causes the
job to crash because it expects a common javascript config but finds an
ES module config. To address this issue The commit-lint config file has
been changed to a `common-js` file instead of a `js` file and the
conventional commit dependancy will now be installed during the job via
npm.

## Screenshots (if applicable)
After making the changes, I tested the commit-lint job locally and here
is an excerpt of the execution:
```
(py-maidr) ➜  py_maidr git:(Krishna/fix-commitlint) act -j commit-lint -W .github/workflows/ci.yml --container-architecture linux/amd64

INFO[0000] Using docker host 'unix:///var/run/docker.sock', and daemon socket 'unix:///var/run/docker.sock' 
[CI/commit-lint] 🚀  Start image=catthehacker/ubuntu:act-latest
INFO[0000] Parallel tasks (0) below minimum, setting to 1 
[CI/commit-lint]   🐳  docker pull image=catthehacker/ubuntu:act-latest platform=linux/amd64 username= forcePull=true
[CI/commit-lint] using DockerAuthConfig authentication for docker pull
INFO[0001] Parallel tasks (0) below minimum, setting to 1 
[CI/commit-lint]   🐳  docker create image=catthehacker/ubuntu:act-latest platform=linux/amd64 entrypoint=["tail" "-f" "/dev/null"] cmd=[] network="host"
[CI/commit-lint]   🐳  docker run image=catthehacker/ubuntu:act-latest platform=linux/amd64 entrypoint=["tail" "-f" "/dev/null"] cmd=[] network="host"
[CI/commit-lint]   ☁  git clone 'https://github.com/wagoid/commitlint-github-action' # ref=v6
[CI/commit-lint] ⭐ Run Main actions/checkout@v3
[CI/commit-lint]   🐳  docker cp src=/Users/krishnaanandan/Desktop/maidr_krishna/py_maidr/. dst=/Users/krishnaanandan/Desktop/maidr_krishna/py_maidr
[CI/commit-lint]   ✅  Success - Main actions/checkout@v3
[CI/commit-lint] ⭐ Run Main Install commitlint dependencies
[CI/commit-lint]   🐳  docker exec cmd=[bash --noprofile --norc -e -o pipefail /var/run/act/workflow/1] user= workdir=
| 
| added 11 packages in 3s
| 
| 1 package is looking for funding
|   run `npm fund` for details
[CI/commit-lint]   ✅  Success - Main Install commitlint dependencies
[CI/commit-lint] ⭐ Run Main Lint commit messages
[CI/commit-lint]   🐳  docker pull image=wagoid/commitlint-github-action:6.1.1 platform=linux/amd64 username= forcePull=true
[CI/commit-lint] using DockerAuthConfig authentication for docker pull
[CI/commit-lint]   🐳  docker create image=wagoid/commitlint-github-action:6.1.1 platform=linux/amd64 entrypoint=[] cmd=[] network="container:act-CI-commit-lint-6b355268bbbb8e27234c3c935b66fc686b070544b9a3b02b47d79688837a12ff"
[CI/commit-lint]   🐳  docker run image=wagoid/commitlint-github-action:6.1.1 platform=linux/amd64 entrypoint=[] cmd=[] network="container:act-CI-commit-lint-6b355268bbbb8e27234c3c935b66fc686b070544b9a3b02b47d79688837a12ff"
| Lint free! 🎉
[CI/commit-lint]   ✅  Success - Main Lint commit messages
[CI/commit-lint]   ⚙  ::set-output:: results=[]
[CI/commit-lint] Cleaning up container for job commit-lint
[CI/commit-lint] 🏁  Job succeeded
(py-maidr) ➜  py_maidr git:(Krishna/fix-commitlint)
```

## Checklist
<!-- Please select all applicable options. -->
<!-- To select your options, please put an 'x' in the all boxes that
apply. -->

- [X] I have read the [Contributor Guidelines](../CONTRIBUTING.md).
- [X] I have performed a self-review of my own code and ensured it
follows the project's coding standards.
- [X] I have tested the changes locally following
`ManualTestingProcess.md`, and all tests related to this pull request
pass.
- [ ] I have commented my code, particularly in hard-to-understand
areas.
- [ ] I have updated the documentation, if applicable.
- [ ] I have added appropriate unit tests, if applicable. ([`ae50904`](https://github.com/xability/py_maidr/commit/ae509047d6063e2cebc291c94b72281f00fa3617))

* ci(commitlint): disable commitlint line length and total length checking (#87)

closes #86 ([`3f718a7`](https://github.com/xability/py_maidr/commit/3f718a7dd12c9569ef63c9318d120d00650b5995))

### Features

* feat(maidr.show): support py-shiny renderer (#67) ([`a944826`](https://github.com/xability/py_maidr/commit/a9448263f413246213bfc2bedf8d859b3cf74695))


## v0.6.0 (2024-08-21)

### Chores

* chore: add bug report and feature request templates (#81)

Added bug report and feature request templates to improve the issue creation process. These templates provide a standardized structure for reporting bugs and requesting new features, making it easier for contributors to provide clear and concise information. This will help streamline the issue triage and resolution process.

The bug report template includes sections for describing the bug, steps to reproduce, actual and expected behavior, screenshots, and additional information. The feature request template includes sections for describing the requested feature, motivation, proposed solution, and additional context.

This commit follows the established commit message convention of starting with a verb in the imperative form, followed by a brief description of the change. It also includes a type prefix ("feat") to indicate that it is a new feature.

closes #80 ([`5af72c2`](https://github.com/xability/py_maidr/commit/5af72c2cc1f01f4b1b1d1ac1944ed06c789891d8))

* chore(vscode): update shiny extension ([`483a075`](https://github.com/xability/py_maidr/commit/483a0758a68960de0670e36c312cfbc1ee90c110))

### Continuous Integration

* ci: add repo name condidtion to docs workflow (#75) ([`0fb17e9`](https://github.com/xability/py_maidr/commit/0fb17e9c86d92d29b315dd3af254ae187a853abb))

### Features

* feat: support interactivity within ipython and quarto (#64) ([`620ddc9`](https://github.com/xability/py_maidr/commit/620ddc9d57175d5ca663d9dfaef4d2704809462f))


## v0.5.1 (2024-08-14)

### Chores

* chore(vscode): update settings to use numpy docstring ([`e9b0c4d`](https://github.com/xability/py_maidr/commit/e9b0c4d08eacdb4d9e40e46ffd74e13799da42d7))

### Continuous Integration

* ci: remove poetry.lock (#73) ([`da1cd26`](https://github.com/xability/py_maidr/commit/da1cd26d8db10aabfe989a760e8df9a62a4bfe3a))

* ci: fixate python version in docs action (#71) (#72) ([`513780d`](https://github.com/xability/py_maidr/commit/513780d732ea2feb3890ace6c7028ebf5f193b17))

* ci: fixate python version in docs action (#71) ([`c0f981a`](https://github.com/xability/py_maidr/commit/c0f981a1d3741709c929af1d8616b39313501c62))

* ci: update poetry.lock (#70) ([`87ffb06`](https://github.com/xability/py_maidr/commit/87ffb06d49f4062a35f5ebee0fa0e28265ceeec5))

* ci: upgrade quartodoc version (#62) ([`36fe34f`](https://github.com/xability/py_maidr/commit/36fe34fe52abca4be8e2101a10b76d887cd17bf2))

### Fixes

* fix: update poetry.lock (#74) ([`6216959`](https://github.com/xability/py_maidr/commit/621695940075fe195b0310c544c117bdc5a9d35e))


## v0.5.0 (2024-07-25)

### Features

* feat: support hightlighing except for segmented plots and boxplots (#59) ([`c2cb99d`](https://github.com/xability/py_maidr/commit/c2cb99d8d7668b177dcf8b800b137eb994c85d6f))


## v0.4.2 (2024-07-02)

### Fixes

* fix: seaborn multi plots in same session (#58) ([`c32fdfd`](https://github.com/xability/py_maidr/commit/c32fdfd32473dd354d292d33a19610a4c0a2eb63))


## v0.4.1 (2024-06-25)

### Fixes

* fix(boxplot): support seaborn axes flip (#56) ([`023907f`](https://github.com/xability/py_maidr/commit/023907fd2482631c42803c7504bf9b838fb035c6))


## v0.4.0 (2024-06-16)

### Features

* feat(boxplot): support horizontal orientation (#52) ([`aebfd89`](https://github.com/xability/py_maidr/commit/aebfd89d90c5d64432425745186b1fe9cceab49d))

### Fixes

* fix(example): take out unused param from seaborn barplot example ([`a58001d`](https://github.com/xability/py_maidr/commit/a58001d06f19756ac9a625257301482a75c9dc6e))


## v0.3.0 (2024-06-11)

### Chores

* chore(deps-dev): bump black from 23.3.0 to 24.3.0 (#45)

Bumps [black](https://github.com/psf/black) from 23.3.0 to 24.3.0.
- [Release notes](https://github.com/psf/black/releases)
- [Changelog](https://github.com/psf/black/blob/main/CHANGES.md)
- [Commits](https://github.com/psf/black/compare/23.3.0...24.3.0)

---
updated-dependencies:
- dependency-name: black
  dependency-type: direct:development
...

Signed-off-by: dependabot[bot] <support@github.com>
Co-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com> ([`53818c9`](https://github.com/xability/py_maidr/commit/53818c9478301376461e64d1cf5a5d32ef730df2))

### Continuous Integration

* ci: add workflow for publishing docs (#44)

`docs.yml` automates the publishing of py-maidr documentation to GitHub Pages. This builds the
static sources using `quarto` for the website and `quartodoc` for the API Reference.
The rendering and publishing are accomplished using Quarto's github actions, which can be found
at https://github.com/quarto-dev/quarto-actions.

Resolves: #43 ([`a6c5886`](https://github.com/xability/py_maidr/commit/a6c5886cc66339eabdfac3c8dc8bb10ee2c037c6))

### Fixes

* fix: black formatting ci (#49) ([`20c4fa2`](https://github.com/xability/py_maidr/commit/20c4fa231bd5a78679cce7698d2a42077c97f330))

* fix: remove docs (#48) ([`9b8cae5`](https://github.com/xability/py_maidr/commit/9b8cae5c1e4071be6edbfdbab8f4b498516f9caf))


## v0.2.0 (2024-05-16)

### Continuous Integration

* ci: setup release pipeline (#42)

`release.yml` configures the github workflow to lint the commit message, format of the code, 
and the unit tests. After successfully completing those jobs, the pipeline builds the package,
updates the semantic version according to the commit message and publishes to the GitHub
Release as well as to the PyPi.

Resolves: #41 ([`634f91c`](https://github.com/xability/py_maidr/commit/634f91cdf5a806f2b451727ccc94b970c7af6a90))

* ci: setup pr github workflow (#40)

Combined the black, commit-message-lint, and the unit test workflow into one called ci.yml. This is beneficial because it could be reused in the release pipeline.

Resolves: #39 ([`4ea4bb6`](https://github.com/xability/py_maidr/commit/4ea4bb6de14854dec9234dc36938d24ed04e9902))

### Documentation

* docs: add quarto and quartodoc for static website (#38)

`_quarto.yml` includes the base structure of the static website with a navbar and the main site.  The navbar includes 'Overview', 'Get Started', and 'API Referece' sections, which are structured in `_index.qmd`, `_get_started.qmd`, and the quartodoc section of `_quarto.yml` respectively. Currently, the 'Overview' and 'Get Started' sections are left empty, which will be generated in the upcoming releases. The 'API Reference' section will include the docstring in a neat format generated by `quartodoc`.

Resolves: #17 ([`011b1b2`](https://github.com/xability/py_maidr/commit/011b1b2b916df3036644d43cd6741f663ca64bc3))

* docs: add docstring (#34) ([`59f0ca1`](https://github.com/xability/py_maidr/commit/59f0ca1551643f9077fe2891af153e5038ddefe8))

### Features

* feat: use htmltools instead of str (#33)

* feat: use htmltools instead of str

* feat: show html using htmltools

* chore: move mixin to utils package ([`8b0a838`](https://github.com/xability/py_maidr/commit/8b0a838bf7cd73ecd5e036d9be28e8ed0523a9ed))

* feat(boxplot): support matplotlib library (#32) ([`060ccfd`](https://github.com/xability/py_maidr/commit/060ccfda80bb168df00c78354b543dbd72c24f1b))


## v0.1.2 (2024-05-13)

### Chores

* chore: update project homepage URL ([`2aeb15c`](https://github.com/xability/py_maidr/commit/2aeb15c4625aface3db289d6e7634ed30516bb58))

* chore: add homepage URL to pyproject.toml ([`582a23f`](https://github.com/xability/py_maidr/commit/582a23f4bb98327edac8b8ae2ed60a59bbf6e3e4))

* chore: update pyproject.toml with additional metadata ([`314cd38`](https://github.com/xability/py_maidr/commit/314cd386d2f6a4ecaa5635dd433bd68e9b67fe9b))

* chore(vscode): add GitLens extension ([`3491ecc`](https://github.com/xability/py_maidr/commit/3491ecc6e5f7ade3fc9fe78d2d31e7616a41215e))

* chore(vscode): remove brackets from the title ([`99ecd10`](https://github.com/xability/py_maidr/commit/99ecd10d4e7b19b05a22fd21276b5fcb54406e6a))

* chore(vscode): add git.ignoreRebaseWarning setting to .vscode/settings.json ([`97c27a8`](https://github.com/xability/py_maidr/commit/97c27a8c694b3c84870a82bfb60d9ae05c6cbec2))

* chore(vscode): add ms-python.debugpy extension to extensions.json ([`ac1b619`](https://github.com/xability/py_maidr/commit/ac1b61957db84631f6616787d404e4053ec5ab26))

* chore(vscode): update window title in VS Code settings.json ([`065800e`](https://github.com/xability/py_maidr/commit/065800ede282c861678c71b0a3e258a6e2bd496f))

* chore(.vscode): add conventional commits extensions ([`492d23f`](https://github.com/xability/py_maidr/commit/492d23ff70803ab2c82e71fee487c019ee743dd1))

* chore(.vscode): :wrench: add conventional commits settings ([`7cb39cd`](https://github.com/xability/py_maidr/commit/7cb39cd1af091eecc35f448fbe20ff610f7ed7c8))

* chore(.vscode): :wrench: add conventional commits settings ([`e8e782f`](https://github.com/xability/py_maidr/commit/e8e782f198cba310494ef817e71bddd0374ce58a))

* chore: use copilot to describe pr ([`5bc8803`](https://github.com/xability/py_maidr/commit/5bc8803684eaaf17c34301b08a677a5b02bc505e))

* chore: remove spellright extension ([`85b7bdf`](https://github.com/xability/py_maidr/commit/85b7bdf590c9ed6a6b9588e6e33d22f502848bd1))

* chore: add more vscode settings and extensions ([`0bf19ba`](https://github.com/xability/py_maidr/commit/0bf19ba68094f46d08af7297a4c93c0e5215ad62))

### Continuous Integration

* ci: update version to 0.1.1 (#27) ([`4ceff90`](https://github.com/xability/py_maidr/commit/4ceff90c6841e4d08fa1b3316a2ee6be75e50f92))

* ci: :wrench: fix commmit linter gh action to be triggered against the latest commit only ([`dbb86d3`](https://github.com/xability/py_maidr/commit/dbb86d38e48e7f44908b61fab1d3122b09ce8bfc))

* ci: :wrench: fix commmit linter gh action to be triggered against the latest commit only ([`f53251c`](https://github.com/xability/py_maidr/commit/f53251c5510901b51b7f615e49f565bc0a9bf351))

* ci: add conventional commits linter to gh workflowFixes #5

* ci: add conventional commits linter to gh workflow
Fixes #5 ([`f1babab`](https://github.com/xability/py_maidr/commit/f1babab54ba44f211657386be17e839523c5c92f))

* ci: :wrench: add python-semantic-release dependencies and settings ([`f928eff`](https://github.com/xability/py_maidr/commit/f928eff5e923a5130b3cfbdb45d93ae9b2174346))

* ci: :sparkles: add conventional commits linter to gh action ([`fc4b758`](https://github.com/xability/py_maidr/commit/fc4b758fb9b9ebd84dc83c9d4423bb3bdc6f4940))

### Documentation

* docs(readme): add logo ([`8702ce5`](https://github.com/xability/py_maidr/commit/8702ce5b9097fcec2a856129841d17c73e5c4415))

* docs(heatmap): add matplotlib example (#25) ([`7cb9433`](https://github.com/xability/py_maidr/commit/7cb9433ad6908a0a882bf7e7897914e1d2479a48))

* docs(readme): update base URL ([`6463477`](https://github.com/xability/py_maidr/commit/6463477cff6458d77c4bad3dc5b683cf52ee958b))

* docs: add documentation for classes and methods (#16)

* docs: add documentation for classes and methods, following numpy docstring style

* fix: convert maidr data to numpy array

* docs: add docstring

* chore: change | none to optional typing

* chore: rever to | none typing

---------

Co-authored-by: SaaiVenkat <greenghost1100@gmail.com> ([`4b5387e`](https://github.com/xability/py_maidr/commit/4b5387e0026b375e37e9097a4abaad7c8d110f94))

* docs: update installation instructions in README.md ([`a5134ed`](https://github.com/xability/py_maidr/commit/a5134ed20d544220cee4f89ae132b750a8005807))

* docs: update py-maidr installation instructions ([`0185aec`](https://github.com/xability/py_maidr/commit/0185aece83c66a85baea3d0ff4a9abbb6fa2f771))

* docs: add development environment setup instructions ([`36ecba2`](https://github.com/xability/py_maidr/commit/36ecba242c680b9ed5e405d6e3924dd3c0b88b0c))

* docs: add CONTRIBUTING.md file ([`2e4cf10`](https://github.com/xability/py_maidr/commit/2e4cf10800d75773e87981fb1665430c7c0a1306))

* docs: add code of conduct ([`777f850`](https://github.com/xability/py_maidr/commit/777f85088e49f3be3faa2e10cc3f6bce14c168b8))

* docs: add CHANGELOG file ([`f19c78c`](https://github.com/xability/py_maidr/commit/f19c78c6c80cb5050765bbe6b7154dbe3a80dc17))

### Features

* feat(scatter): support matplotlib and seaborn library (#30) ([`d2d1202`](https://github.com/xability/py_maidr/commit/d2d12028350deec664614dac462f83d4e362a139))

* feat(boxplot): support seaborn library (#29) ([`5506242`](https://github.com/xability/py_maidr/commit/55062427a2f363be9eeba5abe58725a7f55aa99e))

* feat(stacked): support maidr for matplotlib and seaborn (#28) ([`9e95186`](https://github.com/xability/py_maidr/commit/9e951865b444ba3bbb932d7b8fd7b06885df0f2b))

* feat: support seaborn bar and count plot (#12) ([`fd622bd`](https://github.com/xability/py_maidr/commit/fd622bdd51236627cd37babf9e20ef1378311ff7))

* feat: redesign python binder (#10)

* feat: redesign python binder

* docs: add example bar plot ([`2fe4901`](https://github.com/xability/py_maidr/commit/2fe490158c7cba8fb40d939a079e4c0817ed349a))

### Fixes

* fix: support seaborn breaking changes (#31) ([`afe5382`](https://github.com/xability/py_maidr/commit/afe538209e313f7a42c355c7234ba5f1d1ebf97b))

* fix(version): start from 0.0.1 ([`6bf23bb`](https://github.com/xability/py_maidr/commit/6bf23bb3bff2056f7b1b8d54abc1539d666269ae))

* fix: update pyproject.toml version and htmltools dependency (#14) ([`fcaca48`](https://github.com/xability/py_maidr/commit/fcaca486dff79ac6861d9561986088f432d74b64))

### Testing

* test(barplot): add unit tests for barplot (#20)

* test(barplot): add unit tests for barplot

* chore: add mocks for inputs

* test: add common fixtures

* chore: correct test input

* test: add unit tests for bar plot

* test: add tox workflow

* test: add correct python version

* test: remove non-deterministic assert comment ([`af81cd9`](https://github.com/xability/py_maidr/commit/af81cd935a5bfc1f76c43e4ed16665d11c383605))
