# plugin-place

A curated [Claude Code](https://docs.claude.com/en/docs/claude-code) plugin
marketplace. Currently hosts K-Dense AI's scientific tooling split into
focused, individually-installable plugins so you only load what you need.

## Quick start

```sh
# Add the marketplace (one time)
claude plugin marketplace add galeep/plugin-place

# List what's available
claude plugin search @plugin-place

# Install whichever pieces you want
claude plugin install sci-bioinformatics-genomics@plugin-place
claude plugin install sci-machine-learning@plugin-place
claude plugin install kdense-document-skills@plugin-place
```

## What's in here

19 plugins, 135 skills, all sourced from [K-Dense AI](https://github.com/K-Dense-AI)
and licensed MIT. Two upstream repos vendor in, pinned to release tags:

- [K-Dense-AI/scientific-agent-skills](https://github.com/K-Dense-AI/scientific-agent-skills)
  @ `v2.38.0` — 135 scientific skills, split here into 17 domain plugins
  plus the general-purpose `kdense-document-skills` plugin
- [K-Dense-AI/claude-scientific-writer](https://github.com/K-Dense-AI/claude-scientific-writer)
  @ `v2.13.0` — full writer plugin with a `/scientific-writer-init` command

### The plugins

| Plugin | Skills | What it covers |
| --- | --- | --- |
| `sci-bioinformatics-genomics` | 20 | Sequence analysis, scRNA-seq, gene regulatory networks, variants, phylogenetics, biomedical DBs |
| `sci-cheminformatics-drug-discovery` | 9 | Cheminformatics, molecular ML, docking, medicinal chemistry |
| `sci-proteomics-mass-spec` | 3 | LC-MS/MS, spectral matching, glycoengineering |
| `sci-clinical-research` | 4 | CDS, clinical/case/trial reports, treatment plans, ISO 13485 |
| `sci-healthcare-ai` | 2 | PyHealth, NeuroKit2 biosignal processing |
| `sci-medical-imaging` | 4 | DICOM, WSI, computational pathology, NCI Imaging Data Commons |
| `sci-machine-learning` | 16 | scikit-learn, Lightning, transformers, RL, time series, GNNs, Bayesian, SHAP, GPU/compute helpers |
| `sci-materials-chemistry` | 2 | pymatgen, COBRApy |
| `sci-physics-astronomy` | 6 | astropy, sympy, qutip, qiskit, cirq, pennylane |
| `sci-engineering-simulation` | 4 | SimPy, pymoo, CFD, molecular dynamics |
| `sci-data-analysis-viz` | 14 | Stats, EDA, networks, survival, plotting, big-data dataframes, MATLAB, US fiscal data |
| `sci-geospatial` | 2 | GIS, remote sensing, earth-observation ML |
| `sci-lab-automation` | 11 | Benchling, DNAnexus, LatchBio, OMERO, Opentrons, protocols.io, PyLabRobot, flow cytometry, Neuropixels |
| `sci-scientific-communication` | 22 | Lit review, peer review, writing, citations, posters, slides, schematics, infographics, academic web search |
| `sci-multi-omics` | 3 | DepMap, PrimeKG, scvi-tools |
| `sci-protein-engineering` | 2 | ESM, Adaptyv Bio Foundry |
| `sci-research-methodology` | 7 | Hypothesis generation, grant writing, brainstorming, critical thinking, scenario analysis |
| `kdense-document-skills` | 4 | General-purpose .docx, .pdf, .pptx, .xlsx tools (useful with any plugin) |
| `claude-scientific-writer` | 23 | K-Dense's full writer plugin including the `/scientific-writer-init` command |

## Overlap warning: writer vs. sci-* plugins

The `claude-scientific-writer` plugin and the `sci-*` plugins share most of
their skills (K-Dense maintains the same skill code in both upstreams).
Specifically:

- 23 of the writer's 23 skills also appear in one of the `sci-*` plugins
  (mostly `sci-scientific-communication`, plus `sci-clinical-research` and
  `sci-research-methodology`)
- The writer's unique contribution is the `/scientific-writer-init` slash
  command (which the bare skills lack)

**Pick one approach**:

- **Install the writer**: get all the writing/clinical skills plus the
  init command, in a single plugin
- **Install individual `sci-*` plugins**: get exactly the domain slices
  you want, granular enable/disable

Installing both will give you duplicate skill names, which is unsupported
and will confuse Claude Code's skill router.

## How this is built

`plugins.yaml` is the source of truth. Everything else is generated:

```sh
git submodule update --init --recursive
bash scripts/build.sh
```

This regenerates `plugins/*` and `.claude-plugin/marketplace.json` from
the YAML and the pinned upstream submodules. The build is idempotent —
edits inside `plugins/*` will be overwritten.

The `built` plugin kind copies a chosen subset of skills from an upstream
submodule. The `vendored` plugin kind copies an entire upstream plugin
intact (skills, commands, agents, hooks) and generates a `plugin.json`
from its upstream marketplace metadata. A `local` kind is reserved for
plugins authored directly in this repo.

To add a new plugin, edit `plugins.yaml` and rerun `scripts/build.sh`.

## Staying in sync with upstream

A GitHub Actions workflow runs daily, checking each upstream submodule
for new release tags. When one is found, it bumps the submodule pointer,
rebuilds the plugins, and opens a pull request for review. Merging the PR
publishes the update.

Manual sync:

```sh
cd vendor/scientific-agent-skills && git fetch --tags && git checkout vX.Y.Z
cd ../claude-scientific-writer && git fetch --tags && git checkout vX.Y.Z
cd ../.. && bash scripts/build.sh
```

## License

The plugins distributed here are derivative works of K-Dense AI's MIT-licensed
upstream content. K-Dense's `LICENSE.md` files are preserved in each
`vendor/*/` submodule. This repository's own scaffolding (build scripts, YAML,
docs) is MIT-licensed; see `LICENSE`. All credit for the scientific skills
goes to [K-Dense Inc.](https://k-dense.ai).
