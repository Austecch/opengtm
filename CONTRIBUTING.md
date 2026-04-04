# Contributing to opengtm

## Setup

```bash
git clone https://github.com/buildingopen/opengtm
cd opengtm
pip install -e ".[dev]"
cp .env.example .env
# Add your GEMINI_API_KEY to .env
```

## Making changes

1. Fork the repo and create a branch: `git checkout -b my-feature`
2. Make your changes
3. Test with real data using `GEMINI_API_KEY` in your `.env`
4. Open a PR against `main`

For significant changes (new modules, breaking changes), open an issue first to discuss.

## Where to contribute

- **New ICP profiles** — add to `ICP_PROFILES` dict in `qualify.py`
- **New message frameworks** — add patterns to `message.py`, both EN and DE
- **CRM integrations** — add adapters in `sync.py` (HubSpot, Pipedrive, Airtable)
- **Language support** — extend `_STRINGS` dict in `message.py`
- **SERP volume** — integrate Serper or DataForSEO in `keywords.py` stage 6

## Code style

- Python 3.10+
- `from __future__ import annotations` at top of every module
- Use `DEFAULT_MODEL` from `opengtm/__init__.py` for all Gemini model references, never hardcode model strings
- All Gemini calls: try `google-genai` SDK first, fall back to `google-generativeai`
- No external runtime dependencies beyond those in `pyproject.toml`
