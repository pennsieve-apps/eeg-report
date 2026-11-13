FROM --platform=linux/amd64 python:3.12.16-slim-bookworm@sha256:e697c81897302a4c4333bade000d98038fbb21eb064f8ee1fd42d02ebcd9d337

ENV DEBIAN_FRONTEND=noninteractive PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /processor

# WeasyPrint lays out text with Pango/HarfBuzz/fontconfig (Debian packages, pinned) and the DejaVu
# fonts. The fontconfig cache is built here into /var/cache/fontconfig (read-only at run time is
# fine); anything fontconfig wants to write at run time goes to $XDG_CACHE_HOME under $TMPDIR.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       libpango-1.0-0=1.50.12+ds-1 libpangoft2-1.0-0=1.50.12+ds-1 libharfbuzz-subset0=6.0.0+dfsg-3 \
       fontconfig=2.14.1-4 fonts-dejavu-core=2.37-6 \
    && fc-cache -f \
    && rm -rf /var/lib/apt/lists/* /usr/share/doc/* /usr/share/man/*

# Pinned Python dependencies, binary wheels only, no dependency resolution at build time.
# Pyphen's hyphenation dictionaries (LibreOffice, GPL/LGPL/MPL) are removed: the report never
# hyphenates, and Pyphen's own code is used under its MPL 1.1 option.
COPY requirements.txt /processor/requirements.txt
RUN pip install --no-cache-dir --no-deps --only-binary=:all: --root-user-action=ignore -r /processor/requirements.txt \
    && rm -f /usr/local/lib/python3.12/site-packages/pyphen/dictionaries/*.dic \
    && find /usr/local/lib/python3.12 -depth -type d -name __pycache__ -exec rm -rf {} + \
    && python3 -c "import jinja2, PIL, weasyprint; weasyprint.HTML(string='<p>ok</p>').write_pdf(); print('weasyprint', weasyprint.__version__)"

COPY processor/ /processor/processor/
COPY VERSION /processor/VERSION

# No caches in the image or HOME: on Lambda only INPUT_DIR, OUTPUT_DIR, HOME and TMPDIR are
# writable (processor/main.py sets XDG_CACHE_HOME under TMPDIR).
ENV PYTHONPATH="/processor" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# uid 1000 on ECS; any uid works (nothing in the image is written at run time).
RUN useradd --uid 1000 --no-create-home --shell /usr/sbin/nologin app
USER 1000

ENTRYPOINT ["python3", "-m", "processor.main"]
