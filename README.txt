Creatinine ascertainment source review companion

LOCAL RELEASE CANDIDATE — NOT PUBLISHED

Planned repository name: creatinine-ascertainment-source-review
Planned initial version: 0.1.0; tag: v0.1.0. No remote repository or tag has been created.

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

GitHub versioned release and Zenodo archiving are planned under the account liuyi-pp. The confirmed repository name is creatinine-ascertainment-source-review; the planned initial version is 0.1.0, with tag v0.1.0. No repository, remote tag, release or DOI has been created by this preparation.

Software creators, in order: Yi Liu; Qian Sun. Copyright (c) 2026 Yi Liu and Qian Sun. Original project code is licensed under MIT; see LICENSE, AUTHORS.txt and THIRD_PARTY_NOTICES.txt. These identities and ownership were explicitly confirmed by the authors.

CITATION.cff and .zenodo.json agree on title, version, creator order and licence. CITATION.cff is encoded using JSON, a YAML 1.2 subset. No publication date, repository URL, software DOI or manuscript DOI is invented. Zenodo uses .zenodo.json when both metadata files are present; GitHub uses CITATION.cff for citation display. The current package remains a local release candidate, not an uploaded or published record.
