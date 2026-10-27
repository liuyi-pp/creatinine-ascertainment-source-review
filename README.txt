Creatinine ascertainment source review companion

REVIEW CANDIDATE — PRIVATE REPOSITORY AND UNPUBLISHED DRAFTS

Repository: https://github.com/liuyi-pp/creatinine-ascertainment-source-review (private at the review snapshot)
Candidate version: 0.1.0; planned release tag: v0.1.0. A GitHub release draft and a Zenodo draft exist. The release and Zenodo record have not been published; the version tag is pending publication.

This companion supports inspection of archived operational rules used in the accompanying methodological study. It includes a computational subset, invented example records, boundary checks, an interface guide and a method-coverage map. It is not an end-to-end clinical reproduction package and does not reproduce the manuscript cohort, tables or figures.

Run from this directory with a local Python interpreter:
    python -B run_synthetic.py
    python -B run_example.py
    python -B check_methods_consistency.py
    python -B check_review_guard.py

The runtime modules use only the Python standard library. No pip installation is required. Tested interpreter details are recorded in validation_summary.json. Other versions have not been verified. Entry points accept no external records or file arguments. Fixtures are wholly invented, not patient samples, masked records or resampled clinical observations.

Retained engine files are byte-identical to the previously checked review subset. The internal archive retains the mapping to the source programs. The candidate provenance lists only portable module identifiers and source hashes. Synthetic checks support specified rule behavior and do not establish cohort-identification accuracy, clinical validity, independent extraction or full-pipeline reproducibility.

Raw clinical source files, patient-level records, source caches, observed aggregate numerical results, manuscript files, fitted artifacts and learned preprocessing constants are excluded. Method thresholds, time windows and conversion factors appearing in source are rule parameters, not observed study results.

The runner guard checks prohibited I/O and is not a security sandbox. Direct function imports bypass runner checks. Raw database rows are not accepted as a documented clinical input interface. Read INTERFACE_AND_LIMITATIONS.txt before interpreting any test.

Review snapshot, 2026-10-27: the repository exists under liuyi-pp and remains private. GitHub release v0.1.0 and Zenodo record 23691116 are unpublished drafts. A draft identifier or a reserved DOI is not evidence of publication, registration or public availability. Verify the final version-specific release and DOI at publication; none is asserted as a published citation here.

Software creators, in order: Yi Liu; Qian Sun. Copyright (c) 2026 Yi Liu and Qian Sun. Original project code is licensed under MIT; see LICENSE, AUTHORS.txt and THIRD_PARTY_NOTICES.txt. These identities and ownership were explicitly confirmed by the authors.

CITATION.cff and .zenodo.json agree on title, version, creator order and licence. CITATION.cff is encoded using JSON, a YAML 1.2 subset and includes the verified repository URL. No release date, published software DOI or manuscript DOI is asserted. Metadata are synchronized manually with the unpublished Zenodo draft. This candidate may be uploaded to private review drafts; public release and archive publication require a separate decision. The original local candidate is preserved internally. This revision changes documentation and metadata only, without changing source engines, synthetic fixtures or scientific behavior.
