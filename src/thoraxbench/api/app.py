# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Loopback-only FastAPI application sharing the CLI research engine."""

import ipaddress
from collections.abc import Awaitable, Callable
from pathlib import Path
from threading import RLock
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID, uuid4

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, ConfigDict, Field

from thoraxbench import __version__
from thoraxbench.adapters.base import list_model_configs
from thoraxbench.adapters.factory import require_local_endpoint
from thoraxbench.analysis import DISCLAIMER, analyze_study
from thoraxbench.api.licenses import runtime_libraries
from thoraxbench.cli.main import _guard_study_input
from thoraxbench.config import Settings, get_settings
from thoraxbench.index import SUPPORTED, IndexEntry, load_index, open_study
from thoraxbench.reports import render_study_report
from thoraxbench.reports.html_report import render_html_report, require_results_path
from thoraxbench.splits import CaseGuard, Phase
from thoraxbench.study import Study, load_study_dir
from thoraxbench.synthetic import PhantomSpec, make_phantom, write_dicom_series
from thoraxbench.views import render_slice_png

ASSETS = Path(__file__).parent


class AnalyzeBody(BaseModel):
    """Bounded analysis request selecting an existing, guarded local study."""

    model_config = ConfigDict(extra="forbid")
    dataset: str = Field(pattern=r"^[A-Za-z0-9_.-]+$", max_length=100)
    case_id: str = Field(pattern=r"^[A-Za-z0-9_.-]+$", max_length=200)
    model_id: str = Field(default="heuristic-hu", pattern=r"^[A-Za-z0-9_.-]+$", max_length=100)
    n_images: int = Field(default=4, ge=1, le=16)


def _local_host(host: str) -> bool:
    try:
        parsed = urlsplit(f"//{host}")
        _ = parsed.port
        if parsed.username is not None or parsed.path or parsed.query or parsed.fragment:
            return False
        name = parsed.hostname
        return name in {"localhost", "testserver"} or (
            name is not None and ipaddress.ip_address(name).is_loopback
        )
    except ValueError:
        return False


def create_app(settings: Settings | None = None) -> FastAPI:  # noqa: PLR0915 - colocated routes share guarded state
    """Create a local review app; no patient folders or sealed files are read at startup."""
    config = settings or get_settings()
    app = FastAPI(title="ThoraxBench Local", version=__version__, docs_url=None, redoc_url=None)
    templates = Jinja2Templates(directory=ASSETS / "templates")
    app.mount("/static", StaticFiles(directory=ASSETS / "static", check_dir=False), name="static")
    study_lock = RLock()
    cache: dict[tuple[str, str], Study] = {}
    downloads: dict[UUID, dict[str, Path]] = {}
    demo = config.data_path("demo", "ui")

    @app.middleware("http")
    async def local_requests(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        host = request.headers.get("host", "")
        if not _local_host(host):
            return JSONResponse({"detail": "Local host required"}, status_code=403)
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            origin = request.headers.get("origin")
            expected = f"{request.url.scheme}://{host}"
            if (origin is not None and origin != expected) or request.headers.get(
                "sec-fetch-site"
            ) == "cross-site":
                return JSONResponse({"detail": "Same-origin request required"}, status_code=403)
        response = await call_next(request)
        response.headers["X-Research-Only"] = "Experimental research output; not medical advice"
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data:; style-src 'self'; "
            "script-src 'self'; connect-src 'self'; frame-ancestors 'none'"
        )
        return response

    def entries(dataset: str) -> tuple[CaseGuard, dict[str, IndexEntry]]:
        if dataset not in SUPPORTED:
            raise HTTPException(404, "Unknown dataset or study")
        try:
            guard = CaseGuard.load(config.data_dir, config.manifests_dir, dataset)
            return guard, load_index(dataset, config)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise HTTPException(404, "Development index or split unavailable") from exc

    def get_study(dataset: str, case_id: str) -> Study:
        with study_lock:
            key = (dataset, case_id)
            if key == ("demo", "phantom"):
                if not demo.is_dir() or demo.resolve() != config.data_dir.resolve() / "demo" / "ui":
                    raise HTTPException(404, "Create the synthetic demo first")
                if key not in cache:
                    try:
                        _guard_study_input(demo, config)
                        cache[key] = load_study_dir(demo, dataset="demo", case_id="phantom")
                    except (OSError, ValueError, RuntimeError) as exc:
                        raise HTTPException(403, "Synthetic demo is unavailable") from exc
            else:
                guard, indexed = entries(dataset)
                try:
                    guard.check(case_id, Phase.DEVELOPMENT)
                    entry = indexed[case_id]
                    if key not in cache:
                        cache[key] = open_study(entry, config)
                except (KeyError, OSError, ValueError, RuntimeError) as exc:
                    raise HTTPException(403, "Study is unavailable for development") from exc
            study = cache[key]
            if len(cache) > 2:
                del cache[next(iter(cache))]
            return study

    def study_list() -> dict[str, Any]:
        studies: list[dict[str, Any]] = []
        if demo.is_dir():
            studies.append(
                {
                    "dataset": "demo",
                    "case_id": "phantom",
                    "n_slices": 64,
                    "phase": "synthetic",
                    "qc_adequate": True,
                }
            )
        for dataset in SUPPORTED:
            try:
                guard, indexed = entries(dataset)
            except HTTPException:
                continue
            for case_id in guard.cases(Phase.DEVELOPMENT):
                if case_id in indexed:
                    entry = indexed[case_id]
                    studies.append(
                        {
                            "dataset": dataset,
                            "case_id": case_id,
                            "n_slices": entry.n_slices,
                            "phase": str(guard.phase_of(case_id)),
                            "qc_adequate": entry.qc_adequate,
                        }
                    )
        return {"studies": studies, "disclaimer": DISCLAIMER}

    @app.get("/")
    @app.get("/about")
    def page(request: Request) -> Response:
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={"active_page": "about" if request.url.path == "/about" else "analysis"},
        )

    @app.get("/api/studies")
    def studies() -> dict[str, Any]:
        return study_list()

    @app.post("/api/demo")
    def generate_demo() -> dict[str, Any]:
        with study_lock:
            if demo.resolve() != config.data_dir.resolve() / "demo" / "ui":
                raise HTTPException(404, "Synthetic demo folder is unavailable")
            if not demo.exists():
                spec = PhantomSpec(nodule_radius_mm=6.0, effusion=True)
                write_dicom_series(make_phantom(spec), demo, spec.spacing_mm)
            get_study("demo", "phantom")
            return study_list()

    @app.get("/api/models")
    def models() -> dict[str, Any]:
        tags: set[str] = set()
        try:
            require_local_endpoint(config.ollama_url)
            with httpx.Client(timeout=2.0, trust_env=False, follow_redirects=False) as client:
                response = client.get(f"{config.ollama_url.rstrip('/')}/api/tags")
                response.raise_for_status()
                payload = response.json()
                if isinstance(payload, dict) and isinstance(payload.get("models"), list):
                    tags = {
                        item["name"]
                        for item in payload["models"]
                        if isinstance(item, dict) and isinstance(item.get("name"), str)
                    }
        except httpx.HTTPError, ValueError, KeyError, RuntimeError:
            pass
        configured = list_model_configs(config.configs_dir / "models")
        return {
            "models": [
                {
                    "id": item.id,
                    "adapter": item.adapter,
                    "tag": item.tag,
                    "available": item.adapter == "heuristic"
                    or (
                        item.adapter == "ollama"
                        and (item.tag if ":" in (item.tag or "") else f"{item.tag}:latest") in tags
                    ),
                }
                for item in configured
            ],
            "disclaimer": DISCLAIMER,
        }

    @app.get("/api/studies/{dataset}/{case_id}/slice/{index}.png")
    def slice_image(dataset: str, case_id: str, index: int, window: str = "lung") -> Response:
        if window not in {"lung", "mediastinum", "bone", "abdomen", "medgemma"}:
            raise HTTPException(422, "Unknown display window")
        study = get_study(dataset, case_id)
        if not 0 <= index < study.volume.shape[0]:
            raise HTTPException(422, "Slice index outside study")
        return Response(render_slice_png(study.volume.hu[index], window), media_type="image/png")

    @app.post("/api/analyze")
    def analyze(body: AnalyzeBody) -> dict[str, Any]:
        identifier = uuid4()
        folder = config.data_path("results", "ui", str(identifier))
        try:
            require_results_path(folder / "report.html", config)
        except ValueError as exc:
            raise HTTPException(403, "Research output directory is unavailable") from exc
        if body.model_id not in {
            item.id for item in list_model_configs(config.configs_dir / "models")
        }:
            raise HTTPException(422, "Unknown model")
        study = get_study(body.dataset, body.case_id)
        try:
            result = analyze_study(
                study, body.model_id, config, view_overrides={"n": body.n_images}
            )
        except (OSError, ValueError, RuntimeError) as exc:
            raise HTTPException(
                422, "Analysis could not run; check the local model configuration"
            ) from exc
        markdown = render_study_report(result)
        folder.mkdir(parents=True)
        json_path, markdown_path, html_path = (
            folder / "result.json",
            folder / "report.md",
            folder / "report.html",
        )
        json_path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
        markdown_path.write_text(markdown, encoding="utf-8")
        html_path.write_text(render_html_report(result, study), encoding="utf-8")
        downloads[identifier] = {"json": json_path, "markdown": markdown_path, "html": html_path}
        return {
            "id": str(identifier),
            "result": result.model_dump(mode="json"),
            "markdown": markdown,
            "downloads": {
                "json": f"/api/results/{identifier}/json",
                "markdown": f"/api/results/{identifier}/markdown",
                "html": f"/api/results/{identifier}/html",
            },
        }

    @app.get("/api/results/{identifier}/{kind}")
    def download(identifier: UUID, kind: str) -> FileResponse:
        if identifier not in downloads or kind not in {"json", "markdown", "html"}:
            raise HTTPException(404, "Unknown result")
        path = downloads[identifier][kind]
        try:
            require_results_path(path, config)
        except ValueError as exc:
            raise HTTPException(404, "Unknown result") from exc
        if not path.is_file():
            raise HTTPException(404, "Unknown result")
        return FileResponse(
            path,
            media_type={
                "json": "application/json",
                "markdown": "text/markdown",
                "html": "text/html",
            }[kind],
            filename=path.name,
        )

    @app.get("/api/about")
    def about() -> dict[str, Any]:
        return {
            "author": "Marcel Petrick",
            "email": "mail@marcelpetrick.it",
            "version": __version__,
            "license": "GPL-3.0-or-later",
            "description": "Local CT research: preprocessing, model findings, and reports.",
            "disclaimer": DISCLAIMER,
            "libraries": runtime_libraries(),
        }

    return app
