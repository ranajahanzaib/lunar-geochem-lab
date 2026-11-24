# Contributing

Contributions that improve the software, documentation, data provenance, or scientific reliability are welcome. For substantial changes, open an issue first so the proposed scope can be discussed.

## Development setup

```bash
git clone https://github.com/ranajahanzaib/lunar-geochem-lab.git
cd lunar-geochem-lab
python3 -m venv .venv
.venv/bin/python -m pip install -e .
```

The application uses the official Astromat dataset, which is not included in the repository. Follow the acquisition instructions in the README only after reviewing the dataset's license and terms.

## Checks

Run the automated checks before opening a pull request:

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m py_compile server.py lunar_lab/*.py tests/*.py
node --check app.js
git diff --check
```

## Scientific and data guidelines

- Preserve source records, reported units, analytical context, and provenance.
- Keep missing measurements distinct from measured zeroes and invalid values.
- Do not combine observations from separate analyses into synthetic compositions.
- Cite sources for added datasets, reference compositions, and classification schemes.
- Add deterministic tests for scientific calculations and data handling.
- Do not commit downloaded datasets, generated databases, credentials, or local environment files.

## Pull requests

Describe the change, its motivation, and any scientific assumptions. Include the checks you ran and note any known limitations. Keep each pull request focused and update the README when user-facing behavior or setup changes.
