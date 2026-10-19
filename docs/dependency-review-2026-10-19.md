# Dependency recheck — 2026-10-19

Research use only. Software validation is not medical accuracy.

Checked all 27 direct/build/development/optional pins and 106 registry packages again at
2026-10-19T10:09:54.089364+00:00. FastAPI is the only direct pin below registry stable.
Update FastAPI 0.143.3 → 0.147.0; the resolver changes no other locked version.
Other direct pins remain unchanged. Provider-required CUDA and SymPy/mpmath constraints
remain as recorded in [the earlier review](dependency-review-2026-10-17.md).

This update is isolated from the recorder feature and uses the full commit gate.
Sources are current PyPI JSON release metadata, linked per package below.

| Direct package | Prior pin | Latest stable |
|---|---|---|
| [fastapi](https://pypi.org/pypi/fastapi/json) | 0.143.3 | 0.147.0 |
| [hatchling](https://pypi.org/pypi/hatchling/json) | 1.32.4 | 1.32.4 |
| [httpcore](https://pypi.org/pypi/httpcore/json) | 1.0.9 | 1.0.9 |
| [httpx](https://pypi.org/pypi/httpx/json) | 0.28.1 | 0.28.1 |
| [jinja2](https://pypi.org/pypi/jinja2/json) | 3.1.6 | 3.1.6 |
| [monai](https://pypi.org/pypi/monai/json) | 1.6.1 | 1.6.1 |
| [mypy](https://pypi.org/pypi/mypy/json) | 2.4.0 | 2.4.0 |
| [numpy](https://pypi.org/pypi/numpy/json) | 2.5.4 | 2.5.4 |
| [pillow](https://pypi.org/pypi/pillow/json) | 13.0.0 | 13.0.0 |
| [pip-audit](https://pypi.org/pypi/pip-audit/json) | 2.10.1 | 2.10.1 |
| [playwright](https://pypi.org/pypi/playwright/json) | 1.64.0 | 1.64.0 |
| [pydantic](https://pypi.org/pypi/pydantic/json) | 2.14.1 | 2.14.1 |
| [pydicom](https://pypi.org/pypi/pydicom/json) | 3.0.2 | 3.0.2 |
| [pytest](https://pypi.org/pypi/pytest/json) | 9.1.1 | 9.1.1 |
| [pytest-cov](https://pypi.org/pypi/pytest-cov/json) | 7.1.0 | 7.1.0 |
| [pytest-playwright](https://pypi.org/pypi/pytest-playwright/json) | 0.10.0 | 0.10.0 |
| [python-multipart](https://pypi.org/pypi/python-multipart/json) | 0.0.32 | 0.0.32 |
| [pyyaml](https://pypi.org/pypi/pyyaml/json) | 6.0.3 | 6.0.3 |
| [respx](https://pypi.org/pypi/respx/json) | 0.23.1 | 0.23.1 |
| [ruff](https://pypi.org/pypi/ruff/json) | 0.17.1 | 0.17.1 |
| [scikit-learn](https://pypi.org/pypi/scikit-learn/json) | 1.9.1 | 1.9.1 |
| [scipy](https://pypi.org/pypi/scipy/json) | 1.18.1 | 1.18.1 |
| [torch](https://pypi.org/pypi/torch/json) | 2.14.1 | 2.14.1 |
| [torchvision](https://pypi.org/pypi/torchvision/json) | 0.29.1 | 0.29.1 |
| [typer](https://pypi.org/pypi/typer/json) | 0.27.3 | 0.27.3 |
| [types-pyyaml](https://pypi.org/pypi/types-pyyaml/json) | 6.0.12.20260906 | 6.0.12.20260906 |
| [uvicorn](https://pypi.org/pypi/uvicorn/json) | 0.54.0 | 0.54.0 |
