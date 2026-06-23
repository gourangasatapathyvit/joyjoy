# joyjoy "fat" sandbox image: code-interpreter + headless browser in one.
# Base ships the Playwright browsers (/ms-playwright) + OS deps; we add the
# matching playwright package plus common data/document libraries so the agent
# can run code, do data analysis, convert files, and drive a browser.
FROM mcr.microsoft.com/playwright/python:v1.49.0-jammy

ENV PIP_NO_CACHE_DIR=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

RUN pip install --no-cache-dir \
    "playwright==1.49.0" \
    pandas numpy matplotlib openpyxl python-pptx pillow requests

# Quick sanity at build time: the package imports and sees the bundled browsers.
RUN python -c "import playwright, pandas, numpy, matplotlib; print('fat image deps OK')"
