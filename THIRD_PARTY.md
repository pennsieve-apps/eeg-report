# Third-party components in the eeg-report image

The image contains no model weights and no data. Python packages (pinned in `requirements.txt`, wheels only):

| Component | Authors / copyright holder | Licence | URL |
|---|---|---|---|
| WeasyPrint 70.0 (PDF) | Simon Sapin and contributors; maintained by CourtBouillon | BSD-3-Clause | https://github.com/Kozea/WeasyPrint |
| pydyf 0.13.0 | CourtBouillon | BSD-3-Clause | https://github.com/CourtBouillon/pydyf |
| tinycss2 1.5.1, cssselect2 0.10.1 | Kozea / CourtBouillon | BSD-3-Clause | https://github.com/Kozea/tinycss2, https://github.com/Kozea/cssselect2 |
| tinyhtml5 2.1.0 | CourtBouillon (fork of html5lib) | MIT | https://github.com/CourtBouillon/tinyhtml5 |
| Pyphen 0.18.1 | Kozea | GPL 2.0+/LGPL 2.1+/MPL 1.1 tri-licence; used under MPL 1.1. Its hyphenation dictionaries (LibreOffice) are deleted from the image | https://github.com/Kozea/Pyphen |
| Jinja2 3.1.6, MarkupSafe 3.0.4 (HTML) | Pallets | BSD-3-Clause | https://github.com/pallets/jinja |
| Pillow 13.0.0 (figure checks, PDF images) | Jeffrey A. Clark and contributors; Secret Labs AB; Fredrik Lundh | MIT-CMU | https://github.com/python-pillow/Pillow |
| fontTools 4.68.0 | Just van Rossum and the fontTools contributors | MIT | https://github.com/fonttools/fonttools |
| Brotli 1.2.1 | Google | MIT | https://github.com/google/brotli |
| zopfli (py-zopfli) 0.4.3 | Google; fonttools | Apache-2.0 | https://github.com/fonttools/py-zopfli |
| cffi 2.1.1 | Armin Rigo, Maciej Fijalkowski | MIT | https://github.com/python-cffi/cffi |
| pycparser 3.12 | Eli Bendersky | BSD-3-Clause | https://github.com/eliben/pycparser |
| webencodings 0.6.1 | Simon Sapin | BSD-3-Clause | https://github.com/gsnedders/python-webencodings |

Debian bookworm packages (pinned in the Dockerfile; dynamically loaded by WeasyPrint), with their dependencies:

| Component | Licence |
|---|---|
| Pango 1.50.12 (`libpango-1.0-0`, `libpangoft2-1.0-0`) | LGPL-2.0-or-later |
| HarfBuzz 6.0.0 (`libharfbuzz0b`, `libharfbuzz-subset0`) | MIT ("Old MIT") |
| fontconfig 2.14.1 | MIT-style (fontconfig licence) |
| FreeType 2.12.1 | FreeType Licence (FTL) or GPL-2.0, used under the FTL |
| GLib 2.74.6, FriBiDi 1.0.8 | LGPL-2.1-or-later |
| DejaVu fonts 2.37 (`fonts-dejavu-core`) | Bitstream Vera / Arev font licence (free, redistributable) |

Base image: `python:3.12.16-slim-bookworm` (Python Software Foundation Licence; Debian packages under their own
licences).
