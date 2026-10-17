# Dependency review — 2026-10-17

Research use only. Software checks do not establish medical accuracy.

## Scope and result

Checked 27 exact direct pins: runtime, development, detector extras and Hatchling.
Checked all 106 direct and locked registry packages against PyPI JSON release metadata.
Candidates exclude prereleases and releases with no non-yanked distributions.
Python remains >=3.14; CI uv remains 0.13.1.

Direct updates: FastAPI 0.143.2 → 0.143.3; Pillow 12.3.0 → 13.0.0.
Compatible lockfile updates: ast-serialize 0.13.0 → 0.13.1, filelock 4.2.0 → 4.2.1,
platformdirs 4.13.0 → 4.13.4. `uv lock --upgrade` resolves all remaining constraints.

Newer CUDA component versions are not compatible substitutions: PyTorch 2.14.1 pins
CUDA Toolkit 13.0.3 and several NVIDIA packages exactly; that toolkit pins its components.
SymPy 1.14.0 requires mpmath<1.4, so mpmath stays 1.3.0.
Do not force independently newer versions through those upstream contracts.
PyPI 13.0.3 and lockfile 13.0.3.0 normalize to the same CUDA Toolkit version.

Sources: [PyTorch metadata](https://pypi.org/pypi/torch/2.14.1/json),
[CUDA Toolkit metadata](https://pypi.org/pypi/cuda-toolkit/13.0.3/json),
[SymPy metadata](https://pypi.org/pypi/sympy/1.14.0/json).

## Registry snapshot

Checked at 2026-10-17T21:23:02.276217+00:00. “Latest” means registry stable, not resolver-compatible.

| Package | Scope | Before | Resolved | Latest stable |
|---|---|---|---|---|
| [annotated-doc](https://pypi.org/pypi/annotated-doc/json) | transitive | 0.0.5 | 0.0.5 | 0.0.5 |
| [annotated-types](https://pypi.org/pypi/annotated-types/json) | transitive | 0.8.0 | 0.8.0 | 0.8.0 |
| [anyio](https://pypi.org/pypi/anyio/json) | transitive | 4.15.1 | 4.15.1 | 4.15.1 |
| [ast-serialize](https://pypi.org/pypi/ast-serialize/json) | transitive | 0.13.0 | 0.13.1 | 0.13.1 |
| [boolean-py](https://pypi.org/pypi/boolean-py/json) | transitive | 5.0 | 5.0 | 5.0 |
| [cachecontrol](https://pypi.org/pypi/cachecontrol/json) | transitive | 0.14.4 | 0.14.4 | 0.14.4 |
| [certifi](https://pypi.org/pypi/certifi/json) | transitive | 2026.7.22 | 2026.7.22 | 2026.7.22 |
| [charset-normalizer](https://pypi.org/pypi/charset-normalizer/json) | transitive | 3.5.2 | 3.5.2 | 3.5.2 |
| [click](https://pypi.org/pypi/click/json) | transitive | 8.5.0 | 8.5.0 | 8.5.0 |
| [cloudpickle](https://pypi.org/pypi/cloudpickle/json) | transitive | 3.1.2 | 3.1.2 | 3.1.2 |
| [colorama](https://pypi.org/pypi/colorama/json) | transitive | 0.4.6 | 0.4.6 | 0.4.6 |
| [coverage](https://pypi.org/pypi/coverage/json) | transitive | 7.16.2 | 7.16.2 | 7.16.2 |
| [cuda-bindings](https://pypi.org/pypi/cuda-bindings/json) | transitive | 13.4.4 | 13.4.4 | 13.4.4 |
| [cuda-pathfinder](https://pypi.org/pypi/cuda-pathfinder/json) | transitive | 1.8.3 | 1.8.3 | 1.8.3 |
| [cuda-toolkit](https://pypi.org/pypi/cuda-toolkit/json) | transitive | 13.0.3.0 | 13.0.3.0 | 13.4.3 |
| [cyclonedx-python-lib](https://pypi.org/pypi/cyclonedx-python-lib/json) | transitive | 11.12.0 | 11.12.0 | 11.12.0 |
| [defusedxml](https://pypi.org/pypi/defusedxml/json) | transitive | 0.7.1 | 0.7.1 | 0.7.1 |
| [fastapi](https://pypi.org/pypi/fastapi/json) | direct | 0.143.2 | 0.143.3 | 0.143.3 |
| [filelock](https://pypi.org/pypi/filelock/json) | transitive | 4.2.0 | 4.2.1 | 4.2.1 |
| [fsspec](https://pypi.org/pypi/fsspec/json) | transitive | 2026.9.0 | 2026.9.0 | 2026.9.0 |
| [greenlet](https://pypi.org/pypi/greenlet/json) | transitive | 3.5.6 | 3.5.6 | 3.5.6 |
| [h11](https://pypi.org/pypi/h11/json) | transitive | 0.16.0 | 0.16.0 | 0.16.0 |
| [hatchling](https://pypi.org/pypi/hatchling/json) | direct | 1.32.4 | 1.32.4 | 1.32.4 |
| [httpcore](https://pypi.org/pypi/httpcore/json) | direct | 1.0.9 | 1.0.9 | 1.0.9 |
| [httpx](https://pypi.org/pypi/httpx/json) | direct | 0.28.1 | 0.28.1 | 0.28.1 |
| [idna](https://pypi.org/pypi/idna/json) | transitive | 3.20 | 3.20 | 3.20 |
| [iniconfig](https://pypi.org/pypi/iniconfig/json) | transitive | 2.3.1 | 2.3.1 | 2.3.1 |
| [jinja2](https://pypi.org/pypi/jinja2/json) | direct | 3.1.6 | 3.1.6 | 3.1.6 |
| [joblib](https://pypi.org/pypi/joblib/json) | transitive | 1.6.0 | 1.6.0 | 1.6.0 |
| [librt](https://pypi.org/pypi/librt/json) | transitive | 0.16.0 | 0.16.0 | 0.16.0 |
| [license-expression](https://pypi.org/pypi/license-expression/json) | transitive | 30.4.4 | 30.4.4 | 30.4.4 |
| [markdown-it-py](https://pypi.org/pypi/markdown-it-py/json) | transitive | 4.2.0 | 4.2.0 | 4.2.0 |
| [markupsafe](https://pypi.org/pypi/markupsafe/json) | transitive | 3.0.4 | 3.0.4 | 3.0.4 |
| [mdurl](https://pypi.org/pypi/mdurl/json) | transitive | 0.1.2 | 0.1.2 | 0.1.2 |
| [monai](https://pypi.org/pypi/monai/json) | direct | 1.6.1 | 1.6.1 | 1.6.1 |
| [mpmath](https://pypi.org/pypi/mpmath/json) | transitive | 1.3.0 | 1.3.0 | 1.4.1 |
| [msgpack](https://pypi.org/pypi/msgpack/json) | transitive | 1.2.3 | 1.2.3 | 1.2.3 |
| [mypy](https://pypi.org/pypi/mypy/json) | direct | 2.4.0 | 2.4.0 | 2.4.0 |
| [mypy-extensions](https://pypi.org/pypi/mypy-extensions/json) | transitive | 1.1.0 | 1.1.0 | 1.1.0 |
| [narwhals](https://pypi.org/pypi/narwhals/json) | transitive | 2.27.1 | 2.27.1 | 2.27.1 |
| [networkx](https://pypi.org/pypi/networkx/json) | transitive | 3.7 | 3.7 | 3.7 |
| [numpy](https://pypi.org/pypi/numpy/json) | direct | 2.5.4 | 2.5.4 | 2.5.4 |
| [nvidia-cublas](https://pypi.org/pypi/nvidia-cublas/json) | transitive | 13.1.1.3 | 13.1.1.3 | 13.8.1.7 |
| [nvidia-cuda-cupti](https://pypi.org/pypi/nvidia-cuda-cupti/json) | transitive | 13.0.85 | 13.0.85 | 13.4.92 |
| [nvidia-cuda-nvrtc](https://pypi.org/pypi/nvidia-cuda-nvrtc/json) | transitive | 13.0.88 | 13.0.88 | 13.4.92 |
| [nvidia-cuda-runtime](https://pypi.org/pypi/nvidia-cuda-runtime/json) | transitive | 13.0.96 | 13.0.96 | 13.4.92 |
| [nvidia-cudnn-cu13](https://pypi.org/pypi/nvidia-cudnn-cu13/json) | transitive | 9.24.0.43 | 9.24.0.43 | 9.27.0.42 |
| [nvidia-cufft](https://pypi.org/pypi/nvidia-cufft/json) | transitive | 12.0.0.61 | 12.0.0.61 | 12.4.0.43 |
| [nvidia-cufile](https://pypi.org/pypi/nvidia-cufile/json) | transitive | 1.15.1.6 | 1.15.1.6 | 1.19.1.55 |
| [nvidia-curand](https://pypi.org/pypi/nvidia-curand/json) | transitive | 10.4.0.35 | 10.4.0.35 | 10.4.4.72 |
| [nvidia-cusolver](https://pypi.org/pypi/nvidia-cusolver/json) | transitive | 12.0.4.66 | 12.0.4.66 | 12.3.5.3 |
| [nvidia-cusparse](https://pypi.org/pypi/nvidia-cusparse/json) | transitive | 12.6.3.3 | 12.6.3.3 | 12.8.6.72 |
| [nvidia-cusparselt-cu13](https://pypi.org/pypi/nvidia-cusparselt-cu13/json) | transitive | 0.8.1 | 0.8.1 | 0.10.0 |
| [nvidia-nccl-cu13](https://pypi.org/pypi/nvidia-nccl-cu13/json) | transitive | 2.30.7 | 2.30.7 | 2.32.3 |
| [nvidia-nvjitlink](https://pypi.org/pypi/nvidia-nvjitlink/json) | transitive | 13.4.92 | 13.4.92 | 13.4.92 |
| [nvidia-nvshmem-cu13](https://pypi.org/pypi/nvidia-nvshmem-cu13/json) | transitive | 3.4.5 | 3.4.5 | 3.8.0 |
| [nvidia-nvtx](https://pypi.org/pypi/nvidia-nvtx/json) | transitive | 13.0.85 | 13.0.85 | 13.4.92 |
| [opentelemetry-api](https://pypi.org/pypi/opentelemetry-api/json) | transitive | 1.45.1 | 1.45.1 | 1.45.1 |
| [packageurl-python](https://pypi.org/pypi/packageurl-python/json) | transitive | 0.17.6 | 0.17.6 | 0.17.6 |
| [packaging](https://pypi.org/pypi/packaging/json) | transitive | 26.3 | 26.3 | 26.3 |
| [pathspec](https://pypi.org/pypi/pathspec/json) | transitive | 1.1.1 | 1.1.1 | 1.1.1 |
| [pillow](https://pypi.org/pypi/pillow/json) | direct | 12.3.0 | 13.0.0 | 13.0.0 |
| [pip](https://pypi.org/pypi/pip/json) | transitive | 26.2.1 | 26.2.1 | 26.2.1 |
| [pip-api](https://pypi.org/pypi/pip-api/json) | transitive | 0.0.35 | 0.0.35 | 0.0.35 |
| [pip-audit](https://pypi.org/pypi/pip-audit/json) | direct | 2.10.1 | 2.10.1 | 2.10.1 |
| [pip-requirements-parser](https://pypi.org/pypi/pip-requirements-parser/json) | transitive | 32.0.1 | 32.0.1 | 32.0.1 |
| [platformdirs](https://pypi.org/pypi/platformdirs/json) | transitive | 4.13.0 | 4.13.4 | 4.13.4 |
| [playwright](https://pypi.org/pypi/playwright/json) | direct | 1.64.0 | 1.64.0 | 1.64.0 |
| [pluggy](https://pypi.org/pypi/pluggy/json) | transitive | 1.7.0 | 1.7.0 | 1.7.0 |
| [py-serializable](https://pypi.org/pypi/py-serializable/json) | transitive | 2.1.0 | 2.1.0 | 2.1.0 |
| [pydantic](https://pypi.org/pypi/pydantic/json) | direct | 2.14.1 | 2.14.1 | 2.14.1 |
| [pydantic-core](https://pypi.org/pypi/pydantic-core/json) | transitive | 2.50.1 | 2.50.1 | 2.50.1 |
| [pydicom](https://pypi.org/pypi/pydicom/json) | direct | 3.0.2 | 3.0.2 | 3.0.2 |
| [pyee](https://pypi.org/pypi/pyee/json) | transitive | 14.0.0 | 14.0.0 | 14.0.0 |
| [pygments](https://pypi.org/pypi/pygments/json) | transitive | 2.21.0 | 2.21.0 | 2.21.0 |
| [pyparsing](https://pypi.org/pypi/pyparsing/json) | transitive | 3.3.3 | 3.3.3 | 3.3.3 |
| [pytest](https://pypi.org/pypi/pytest/json) | direct | 9.1.1 | 9.1.1 | 9.1.1 |
| [pytest-cov](https://pypi.org/pypi/pytest-cov/json) | direct | 7.1.0 | 7.1.0 | 7.1.0 |
| [pytest-playwright](https://pypi.org/pypi/pytest-playwright/json) | direct | 0.10.0 | 0.10.0 | 0.10.0 |
| [python-multipart](https://pypi.org/pypi/python-multipart/json) | direct | 0.0.32 | 0.0.32 | 0.0.32 |
| [python-slugify](https://pypi.org/pypi/python-slugify/json) | transitive | 9.1.3 | 9.1.3 | 9.1.3 |
| [pyyaml](https://pypi.org/pypi/pyyaml/json) | direct | 6.0.3 | 6.0.3 | 6.0.3 |
| [requests](https://pypi.org/pypi/requests/json) | transitive | 2.34.2 | 2.34.2 | 2.34.2 |
| [respx](https://pypi.org/pypi/respx/json) | direct | 0.23.1 | 0.23.1 | 0.23.1 |
| [rich](https://pypi.org/pypi/rich/json) | transitive | 15.0.0 | 15.0.0 | 15.0.0 |
| [ruff](https://pypi.org/pypi/ruff/json) | direct | 0.17.1 | 0.17.1 | 0.17.1 |
| [scikit-learn](https://pypi.org/pypi/scikit-learn/json) | direct | 1.9.1 | 1.9.1 | 1.9.1 |
| [scipy](https://pypi.org/pypi/scipy/json) | direct | 1.18.1 | 1.18.1 | 1.18.1 |
| [setuptools](https://pypi.org/pypi/setuptools/json) | transitive | 84.0.0 | 84.0.0 | 84.0.0 |
| [shellingham](https://pypi.org/pypi/shellingham/json) | transitive | 1.5.4 | 1.5.4 | 1.5.4 |
| [sortedcontainers](https://pypi.org/pypi/sortedcontainers/json) | transitive | 2.4.0 | 2.4.0 | 2.4.0 |
| [starlette](https://pypi.org/pypi/starlette/json) | transitive | 1.8.0 | 1.8.0 | 1.8.0 |
| [sympy](https://pypi.org/pypi/sympy/json) | transitive | 1.14.0 | 1.14.0 | 1.14.0 |
| [text-unidecode](https://pypi.org/pypi/text-unidecode/json) | transitive | 1.3 | 1.3 | 1.3 |
| [threadpoolctl](https://pypi.org/pypi/threadpoolctl/json) | transitive | 3.7.0 | 3.7.0 | 3.7.0 |
| [tomli](https://pypi.org/pypi/tomli/json) | transitive | 2.5.0 | 2.5.0 | 2.5.0 |
| [tomli-w](https://pypi.org/pypi/tomli-w/json) | transitive | 1.2.0 | 1.2.0 | 1.2.0 |
| [torch](https://pypi.org/pypi/torch/json) | direct | 2.14.1 | 2.14.1 | 2.14.1 |
| [torchvision](https://pypi.org/pypi/torchvision/json) | direct | 0.29.1 | 0.29.1 | 0.29.1 |
| [triton](https://pypi.org/pypi/triton/json) | transitive | 3.8.0 | 3.8.0 | 3.8.0 |
| [typer](https://pypi.org/pypi/typer/json) | direct | 0.27.3 | 0.27.3 | 0.27.3 |
| [types-pyyaml](https://pypi.org/pypi/types-pyyaml/json) | direct | 6.0.12.20260906 | 6.0.12.20260906 | 6.0.12.20260906 |
| [typing-extensions](https://pypi.org/pypi/typing-extensions/json) | transitive | 4.16.0 | 4.16.0 | 4.16.0 |
| [typing-inspection](https://pypi.org/pypi/typing-inspection/json) | transitive | 0.4.4 | 0.4.4 | 0.4.4 |
| [urllib3](https://pypi.org/pypi/urllib3/json) | transitive | 2.8.0 | 2.8.0 | 2.8.0 |
| [uvicorn](https://pypi.org/pypi/uvicorn/json) | direct | 0.54.0 | 0.54.0 | 0.54.0 |

## Validation

The commit gate runs formatting, lint, strict typing, synthetic unit/integration/browser
tests, coverage, build, isolated wheel checks, medical-data checks and the all-extras
vulnerability audit. See the dependency commit and its pipeline logs for the outcome.
No real-study inference is part of this dependency gate.
