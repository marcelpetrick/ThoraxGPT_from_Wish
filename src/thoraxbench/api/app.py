# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Loopback-only FastAPI application sharing the CLI research engine."""

import contextlib
import hashlib
import ipaddress
import json
from collections.abc import Awaitable, Callable
from pathlib import Path
from threading import RLock
from typing import Any, Literal
from urllib.parse import urlsplit
from uuid import UUID, uuid4

import httpx
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, ConfigDict, Field

from thoraxbench import __version__
from thoraxbench.adapters.base import ModelConfig, list_model_configs
from thoraxbench.adapters.factory import load_model, require_local_endpoint
from thoraxbench.analysis import DISCLAIMER, AnalysisResult, analyze_study
from thoraxbench.api.abortable_http import abortable_client
from thoraxbench.api.diagnostics import RECOVERY, failure_code, header_warning_diagnostic
from thoraxbench.api.evaluation import Evaluation, EvaluationError
from thoraxbench.api.jobs import (
    JobCancelledError,
    JobContext,
    JobError,
    JobManager,
    JobOutcome,
    QueueFullError,
)
from thoraxbench.api.licenses import runtime_libraries
from thoraxbench.api.local_studies import (
    LocalStudies,
    SourceChangedError,
    absolute_folder,
    browse_folders,
    local_identity,
    source_signature,
)
from thoraxbench.api.model_pulls import ModelPullJobs, PullBusyError
from thoraxbench.api.presentation import finding_presentation
from thoraxbench.config import Settings, get_settings
from thoraxbench.fullreview import run_full_review
from thoraxbench.index import SUPPORTED, IndexEntry, load_index, open_study
from thoraxbench.reports import render_study_report
from thoraxbench.reports.candidates import candidate_review
from thoraxbench.reports.full_review import SHORT_DISCLAIMER, render_full_review_html
from thoraxbench.reports.html_report import (
    render_comparison_report,
    render_html_report,
    require_results_path,
)
from thoraxbench.reports.llm_summary import llm_summary
from thoraxbench.reports.outcome import build_outcome
from thoraxbench.splits import CaseGuard, Phase
from thoraxbench.study import Study, load_study_dir
from thoraxbench.study_access import guard_study_input, guard_study_path
from thoraxbench.synthetic import PhantomSpec, make_phantom, write_dicom_series
from thoraxbench.views import render_slice_png

ASSETS = Path(__file__).parent
# Local text model that may rephrase the deterministic verdict (fact-checked, optional).
SUMMARY_MODEL = "medgemma1.5-q4"
RECOMMENDED_MODELS = (
    "monai-lung-nodule",
    "heuristic-hu",
    "medgemma1.5-q4",
    "medgemma1.5-q8",
    "gemma3-4b",
    "qwen3-vl-4b-nothink",
)


def _service_available(model: ModelConfig, config: Settings) -> bool:
    endpoint = model.base_url or config.service_urls.get(model.service or "")
    if not endpoint:
        return False
    try:
        require_local_endpoint(endpoint)
        with httpx.Client(timeout=0.5, trust_env=False, follow_redirects=False) as client:
            response = client.get(f"{endpoint.rstrip('/')}/health")
            response.raise_for_status()
            body = response.json()
            return isinstance(body, dict) and body.get("status") == "ok"
    except httpx.HTTPError, ValueError, RuntimeError:
        return False


class LocalStudyBody(BaseModel):
    """A server-side folder path, never file bytes or a client filesystem upload."""

    model_config = ConfigDict(extra="forbid")
    path: str = Field(min_length=1, max_length=4096, strict=True)


class PullBody(BaseModel):
    """Explicit operator acknowledgement before asking Ollama to acquire weights."""

    model_config = ConfigDict(extra="forbid")
    terms_acknowledged: bool = Field(strict=True)


class ComparisonOmission(BaseModel):
    """Bounded display-only explanation for a model without a completed result."""

    model_config = ConfigDict(extra="forbid")
    model_id: str = Field(min_length=1, max_length=100)
    status: Literal["skipped", "error"]
    detail: str = Field(max_length=500)


class SummaryBody(BaseModel):
    """Request a verdict in one report language."""

    model_config = ConfigDict(extra="forbid")
    lang: Literal["en", "de"] = "en"
    use_llm: bool = False


class CompareBody(BaseModel):
    """Select completed local run identifiers without accepting filesystem paths."""

    model_config = ConfigDict(extra="forbid")
    result_ids: list[UUID] = Field(min_length=1, max_length=8)
    omissions: list[ComparisonOmission] = Field(default_factory=list, max_length=8)


class AnalyzeBody(BaseModel):
    """Bounded analysis request selecting an existing, guarded local study."""

    model_config = ConfigDict(extra="forbid")
    dataset: str = Field(pattern=r"^[A-Za-z0-9_.-]+$", max_length=100)
    case_id: str = Field(pattern=r"^[A-Za-z0-9_.-]+$", max_length=200)
    model_id: str = Field(default="heuristic-hu", pattern=r"^[A-Za-z0-9_.-]+$", max_length=100)
    n_images: int = Field(default=4, ge=1, le=16)


class JobBody(BaseModel):
    """Queue one analysis, a recommended-model comparison or a full thorax review."""

    model_config = ConfigDict(extra="forbid")
    kind: Literal["analysis", "comparison", "full-review"]
    dataset: str = Field(pattern=r"^[A-Za-z0-9_.-]+$", max_length=100)
    case_id: str = Field(pattern=r"^[A-Za-z0-9_.-]+$", max_length=200)
    model_id: str = Field(default="heuristic-hu", pattern=r"^[A-Za-z0-9_.-]+$", max_length=100)
    n_images: int = Field(default=4, ge=1, le=16)


def _ollama_tags(config: Settings) -> set[str]:
    try:
        require_local_endpoint(config.ollama_url)
        with httpx.Client(timeout=2.0, trust_env=False, follow_redirects=False) as client:
            response = client.get(f"{config.ollama_url.rstrip('/')}/api/tags")
            response.raise_for_status()
            payload = response.json()
            if isinstance(payload, dict) and isinstance(payload.get("models"), list):
                return {
                    item["name"]
                    for item in payload["models"]
                    if isinstance(item, dict) and isinstance(item.get("name"), str)
                }
    except httpx.HTTPError, ValueError, KeyError, RuntimeError:
        pass
    return set()


def _model_available(item: ModelConfig, tags: set[str], config: Settings) -> bool:
    if item.adapter == "monai_detector":
        return load_model(item.id, config).available()
    return (
        item.adapter == "heuristic"
        or (item.adapter == "http_service" and _service_available(item, config))
        or (
            item.adapter == "ollama"
            and (item.tag if ":" in (item.tag or "") else f"{item.tag}:latest") in tags
        )
    )


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
    local_studies = LocalStudies(config)
    downloads: dict[UUID, dict[str, Path]] = {}
    jobs = JobManager()
    pulls = ModelPullJobs(config.ollama_url, jobs)
    evaluation = Evaluation(config)
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
        response.headers.setdefault(
            "Content-Security-Policy",
            (
                "default-src 'self'; img-src 'self' data:; style-src 'self'; "
                "script-src 'self'; connect-src 'self'; frame-ancestors 'none'"
            ),
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
                        guard_study_input(demo, config)
                        cache[key] = load_study_dir(demo, dataset="demo", case_id="phantom")
                    except (OSError, ValueError, RuntimeError) as exc:
                        raise HTTPException(403, "Synthetic demo is unavailable") from exc
            elif dataset == "local":
                try:
                    local_entry, identity, signature = local_studies.checked(
                        case_id, require_headers=key not in cache
                    )
                    if key not in cache or local_entry.signature != signature:
                        loaded = load_study_dir(
                            local_entry.path, dataset=identity[0], case_id=identity[1]
                        )
                        local_identity(loaded, identity, case_id)
                        guard_study_input(local_entry.path, config)
                        if source_signature(local_entry.path, config) != signature:
                            raise SourceChangedError("source changed while loading")
                        local_studies.register(case_id, local_entry.path, loaded, signature)
                        cache[key] = loaded
                except (KeyError, OSError, ValueError, RuntimeError) as exc:
                    cache.pop(key, None)
                    raise HTTPException(403, "Local study is unavailable") from exc
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
        libraries: list[dict[str, Any]] = []
        for dataset in SUPPORTED:
            library: dict[str, Any] = {
                "dataset": dataset,
                "status": "ready",
                "available_studies": 0,
            }
            libraries.append(library)
            try:
                guard, indexed = entries(dataset)
            except HTTPException:
                if (
                    not config.data_path("splits", f"{dataset}.json").is_file()
                    or not (config.manifests_dir / "splits" / f"{dataset}.json").is_file()
                ):
                    library["status"] = "split_required"
                elif not config.data_path("index", f"{dataset}.json").is_file():
                    library["status"] = "not_indexed"
                else:
                    library["status"] = "unavailable"
                continue
            for case_id in guard.cases(Phase.DEVELOPMENT):
                if case_id in indexed:
                    entry = indexed[case_id]
                    library["available_studies"] += 1
                    studies.append(
                        {
                            "dataset": dataset,
                            "case_id": case_id,
                            "n_slices": entry.n_slices,
                            "phase": str(guard.phase_of(case_id)),
                            "qc_adequate": entry.qc_adequate,
                        }
                    )
        local_entries = local_studies.summaries()
        studies.extend(local_entries)
        synthetic = sum(study["dataset"] == "demo" for study in studies)
        return {
            "studies": studies,
            "libraries": libraries,
            "summary": {
                "total_studies": len(studies),
                "development_studies": len(studies) - synthetic - len(local_entries),
                "local_studies": len(local_entries),
                "synthetic_studies": synthetic,
            },
            "disclaimer": DISCLAIMER,
        }

    @app.get("/")
    @app.get("/about")
    @app.get("/evaluation")
    @app.get("/jobs")
    def page(request: Request) -> Response:
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={"active_page": request.url.path.strip("/") or "analysis"},
        )

    @app.get("/api/local-folders")
    def local_folders(path: str | None = None) -> dict[str, Any]:
        try:
            folder = absolute_folder(path) if path is not None else config.data_dir.absolute()
            return browse_folders(folder, config) | {"disclaimer": DISCLAIMER}
        except (OSError, ValueError, RuntimeError) as exc:
            raise HTTPException(403, "Local folder is unavailable or not permitted") from exc

    @app.post("/api/local-studies", status_code=202)
    def register_local_study(body: LocalStudyBody) -> dict[str, Any]:
        try:
            folder = absolute_folder(body.path)
            guard_study_path(folder, config)
            if not folder.is_dir():
                raise ValueError("not a directory")
        except (OSError, ValueError, RuntimeError) as exc:
            raise HTTPException(403, "Local folder is unavailable or not permitted") from exc
        identifier = str(uuid4())

        def work(context: JobContext) -> JobOutcome:
            context.stage("folder_check")
            try:
                identity = guard_study_input(folder, config, progress=context.progress)
                signature = source_signature(folder, config)
                context.stage("study")
                study = load_study_dir(
                    folder, dataset=identity[0], case_id=identity[1], progress=context.progress
                )
                # Recheck source/header access after loading, before retaining anything.
                guard_study_input(
                    folder,
                    config,
                    progress=lambda _operation, completed, total: context.progress(
                        "source_recheck", completed, total
                    ),
                )
                if source_signature(folder, config) != signature:
                    raise SourceChangedError("source changed while loading")
                local_identity(study, identity, identifier)
                context.stage("register")
                with study_lock:
                    local_studies.register(identifier, folder, study, signature)
                    cache[("local", identifier)] = study
                    if len(cache) > 2:
                        del cache[next(iter(cache))]
                summary = next(
                    item for item in local_studies.summaries() if item["case_id"] == identifier
                )
                unreadable = study.selection.get("discovery", {}).get("headers_unreadable", 0)
                warnings = (
                    [{"code": "unreadable_dicom_headers", "count": unreadable}]
                    if unreadable
                    else []
                )
                return JobOutcome(
                    "succeeded",
                    diagnostic=(
                        header_warning_diagnostic(
                            study.selection.get("discovery", {}),
                            study.selection.get("header_error_types", {}),
                        )
                        if warnings
                        else None
                    ),
                    result={
                        "study": summary,
                        "warnings": warnings,
                        "discovery": study.selection.get("discovery", {}),
                        "disclaimer": DISCLAIMER,
                    },
                )
            except (OSError, ValueError, RuntimeError, KeyError, TypeError) as exc:
                raise JobError(RECOVERY[failure_code(exc)]) from exc

        label = {"dataset": "local", "case_id": identifier, "models": []}
        key = "study-import|" + hashlib.sha256(str(folder).encode()).hexdigest()
        try:
            snapshot, created = jobs.submit("study-import", key, label, work)
        except QueueFullError as exc:
            raise HTTPException(429, str(exc)) from exc
        return {"job": snapshot, "created": created}

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
        tags = _ollama_tags(config)
        configured = list_model_configs(config.configs_dir / "models")
        return {
            "models": [
                {
                    "id": item.id,
                    "recommended": item.id in RECOMMENDED_MODELS,
                    "fit": item.fit,
                    "fit_reason": item.fit_reason,
                    "single_image_protocol": item.prompt == "P6",
                    "adapter": item.adapter,
                    "tag": item.tag,
                    "license": item.license,
                    "notes": item.notes,
                    "source_url": (
                        "https://huggingface.co/MONAI/lung_nodule_ct_detection"
                        if item.adapter == "monai_detector"
                        else f"https://ollama.com/library/{item.tag.split(':')[0]}"
                        if item.adapter == "ollama" and item.tag
                        else None
                    ),
                    "terms_url": (
                        "https://developers.google.com/health-ai-developer-foundations/terms"
                        if item.family == "medgemma"
                        else "https://ai.google.dev/gemma/terms"
                        if item.family == "gemma3"
                        else "https://www.apache.org/licenses/LICENSE-2.0"
                        if item.license == "Apache-2.0"
                        else None
                    ),
                    "download_supported": item.adapter == "ollama" and bool(item.tag),
                    "setup_steps": (
                        [
                            "Review the model terms and verify disk space and hardware capacity.",
                            "Start local Ollama, acknowledge applicable terms, then download.",
                        ]
                        if item.adapter == "ollama"
                        else [
                            "Obtain permitted weights and any required publisher access.",
                            "Provision suitable hardware and start the configured local service.",
                            "This interface cannot bypass access gates or install 3D services.",
                        ]
                        if item.adapter == "http_service"
                        else [
                            "uv sync --frozen --all-groups --extra detector",
                            "Read terms: uv run --extra detector python "
                            "scripts/fetch_monai_bundle.py",
                            "After review: uv run --extra detector python "
                            "scripts/fetch_monai_bundle.py --accept-terms",
                            "Launch with: uv run --extra detector thoraxbench serve",
                            "LUNA16 training overlaps LIDC-IDRI; "
                            "this is a research reference only.",
                        ]
                        if item.adapter == "monai_detector"
                        else ["Included deterministic baseline; no download required."]
                    ),
                    "available": _model_available(item, tags, config),
                }
                for item in configured
            ],
            "disclaimer": DISCLAIMER,
        }

    @app.post("/api/models/{model_id}/pull")
    def pull_model(model_id: str, body: PullBody) -> dict[str, Any]:
        configured = {item.id: item for item in list_model_configs(config.configs_dir / "models")}
        item = configured.get(model_id)
        if item is None:
            raise HTTPException(404, "Unknown model")
        if item.adapter != "ollama" or not item.tag:
            raise HTTPException(
                422, "This model requires manual setup; automatic download unavailable"
            )
        if not body.terms_acknowledged:
            raise HTTPException(422, "Review and acknowledge the model terms before downloading")
        try:
            return pulls.start(item.id, item.tag)
        except QueueFullError as exc:
            raise HTTPException(429, str(exc)) from exc
        except PullBusyError as exc:
            raise HTTPException(409, str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(
                422, "Downloads require a configured loopback Ollama endpoint"
            ) from exc

    @app.get("/api/model-pulls/{identifier}")
    def pull_status(identifier: UUID) -> dict[str, Any]:
        job = pulls.get(identifier)
        if job is None:
            raise HTTPException(404, "Unknown download job")
        return job

    @app.get("/api/studies/{dataset}/{case_id}/slice/{index}.png")
    def slice_image(dataset: str, case_id: str, index: int, window: str = "lung") -> Response:
        if window not in {"lung", "mediastinum", "bone", "abdomen", "medgemma"}:
            raise HTTPException(422, "Unknown display window")
        study = get_study(dataset, case_id)
        if not 0 <= index < study.volume.shape[0]:
            raise HTTPException(422, "Slice index outside study")
        return Response(render_slice_png(study.volume.hu[index], window), media_type="image/png")

    def check_study(dataset: str, case_id: str) -> None:
        """Apply the study access guard at submission without reading pixels."""
        if (dataset, case_id) == ("demo", "phantom"):
            if not demo.is_dir() or demo.resolve() != config.data_dir.resolve() / "demo" / "ui":
                raise HTTPException(404, "Create the synthetic demo first")
            return
        if dataset == "local":
            try:
                local_studies.checked(case_id)
            except (KeyError, OSError, ValueError, RuntimeError) as exc:
                raise HTTPException(403, "Local study is unavailable") from exc
            return
        guard, indexed = entries(dataset)
        try:
            guard.check(case_id, Phase.DEVELOPMENT)
            _ = indexed[case_id]
        except (KeyError, OSError, ValueError, RuntimeError) as exc:
            raise HTTPException(403, "Study is unavailable for development") from exc

    def result_folder() -> tuple[UUID, Path]:
        identifier = uuid4()
        folder = config.data_path("results", "ui", str(identifier))
        try:
            require_results_path(folder / "report.html", config)
        except ValueError as exc:
            raise HTTPException(403, "Research output directory is unavailable") from exc
        return identifier, folder

    def configured_models() -> dict[str, ModelConfig]:
        return {item.id: item for item in list_model_configs(config.configs_dir / "models")}

    def execute_analysis(
        dataset: str, case_id: str, model_id: str, n_images: int, context: JobContext
    ) -> dict[str, Any]:
        """Run one guarded analysis inside the job worker; the CLI engine does the work."""
        identifier, folder = result_folder()
        item = configured_models().get(model_id)
        if item is None:
            raise HTTPException(422, "Unknown model")
        context.stage("study")
        study = get_study(dataset, case_id)
        client: httpx.Client | None = None
        unregister: Callable[[], None] | None = None
        if item.adapter in {"ollama", "http_service"}:
            client, transport = abortable_client(item.timeout_s)
            unregister = context.on_abort(transport.abort)
        try:
            result = analyze_study(
                study,
                model_id,
                config,
                view_overrides={"n": n_images},
                client=client,
                on_stage=context.stage,
            )
        except (OSError, ValueError, RuntimeError) as exc:
            raise HTTPException(
                422, "Analysis could not run; check the local model configuration"
            ) from exc
        finally:
            if unregister is not None:
                unregister()
            if client is not None:
                client.close()
        context.stage("report")
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
            "presentation": finding_presentation(result),
            "candidate_review": candidate_review(result, study),
            "markdown": markdown,
            "downloads": {
                "json": f"/api/results/{identifier}/json",
                "markdown": f"/api/results/{identifier}/markdown",
                "html": f"/api/results/{identifier}/html",
            },
        }

    def export_comparison(
        result_ids: list[UUID], omissions: list[ComparisonOmission]
    ) -> dict[str, Any]:
        reports: list[tuple[AnalysisResult, str]] = []
        for identifier in dict.fromkeys(result_ids):
            files = downloads.get(identifier, {})
            try:
                json_path, html_path = files["json"], files["html"]
                require_results_path(json_path, config)
                require_results_path(html_path, config)
                reports.append(
                    (
                        AnalysisResult.model_validate_json(json_path.read_text(encoding="utf-8")),
                        html_path.read_text(encoding="utf-8"),
                    )
                )
            except (KeyError, OSError, ValueError) as exc:
                raise HTTPException(404, "Completed result is unavailable") from exc
        if len({(r.dataset, r.case_id, r.series_uid) for r, _ in reports}) != 1:
            raise HTTPException(422, "Comparison requires results from the same study")
        identifier = uuid4()
        path = config.data_path("results", "ui", str(identifier), "comparison.html")
        try:
            require_results_path(path, config)
        except ValueError as exc:
            raise HTTPException(403, "Research output directory is unavailable") from exc
        path.parent.mkdir(parents=True)
        path.write_text(
            render_comparison_report(reports, [item.model_dump() for item in omissions]),
            encoding="utf-8",
        )
        downloads[identifier] = {"html": path}
        return {"id": str(identifier), "downloads": {"html": f"/api/results/{identifier}/html"}}

    def outcome_of(payload: dict[str, Any]) -> Literal["succeeded", "abstained"]:
        result = payload["result"]
        return "abstained" if result["report"]["abstain"] or result["raw_error"] else "succeeded"

    def analysis_work(body: JobBody) -> Callable[[JobContext], JobOutcome]:
        def work(context: JobContext) -> JobOutcome:
            try:
                payload = execute_analysis(
                    body.dataset, body.case_id, body.model_id, body.n_images, context
                )
            except HTTPException as exc:
                raise JobError(str(exc.detail)) from exc
            return JobOutcome(outcome_of(payload), result=payload)

        return work

    def comparison_work(body: JobBody) -> Callable[[JobContext], JobOutcome]:
        def work(context: JobContext) -> JobOutcome:
            steps = context.steps()
            completed: list[UUID] = []
            omissions: list[ComparisonOmission] = []
            statuses: list[str] = []
            for index, step in enumerate(steps):
                model_id = step["model_id"]
                if step["status"] == "skipped":
                    omissions.append(
                        ComparisonOmission(
                            model_id=model_id, status="skipped", detail=step.get("detail") or ""
                        )
                    )
                    continue
                context.check()
                context.step(index, status="running")
                try:
                    payload = execute_analysis(
                        body.dataset, body.case_id, model_id, body.n_images, context
                    )
                except JobCancelledError:
                    context.step(index, status="cancelled")
                    raise
                except HTTPException as exc:
                    context.step(index, status="error", detail=str(exc.detail))
                    omissions.append(
                        ComparisonOmission(
                            model_id=model_id, status="error", detail=str(exc.detail)[:500]
                        )
                    )
                    statuses.append("error")
                    continue
                result = payload["result"]
                status = "abstained" if outcome_of(payload) == "abstained" else "completed"
                context.step_output(index, payload)
                context.step(
                    index,
                    status=status,
                    detail=result["raw_error"] or result["report"].get("uncertainty") or "",
                    result_id=payload["id"],
                )
                completed.append(UUID(payload["id"]))
                statuses.append(status)
            exported: dict[str, Any] | None = None
            if completed:
                context.stage("export")
                try:
                    exported = export_comparison(completed, omissions)
                except HTTPException as exc:
                    raise JobError(f"Comparison export failed: {exc.detail}") from exc
            final: Literal["succeeded", "failed", "abstained"] = (
                "succeeded"
                if "completed" in statuses
                else "abstained"
                if "abstained" in statuses
                else "failed"
            )
            return JobOutcome(
                final,
                result={"comparison_download": exported["downloads"]["html"] if exported else None},
                error=None if final != "failed" else "No model produced a result",
            )

        return work

    def execute_full_review(
        dataset: str, case_id: str, model_id: str, context: JobContext
    ) -> tuple[dict[str, Any], bool]:
        """Run the full thorax review; returns the payload and whether it was stopped."""
        identifier, folder = result_folder()
        item = configured_models().get(model_id)
        if item is None or item.adapter != "ollama":
            raise JobError("Full thorax review needs a local vision-language model")
        context.stage("study")
        try:
            study = get_study(dataset, case_id)
        except HTTPException as exc:
            raise JobError(str(exc.detail)) from exc
        client, transport = abortable_client(item.timeout_s)
        unregister = context.on_abort(transport.abort)

        def stage(name: str) -> None:
            # Stage names are display-only here; stops are handled between slabs.
            with contextlib.suppress(JobCancelledError):
                context.stage(name)

        def progress(done: int, total: int, rate: float | None) -> None:
            with contextlib.suppress(JobCancelledError):
                context.progress("review_images", done, total, seconds_per_item=rate)

        try:
            run = run_full_review(
                study,
                model_id,
                config,
                client=client,
                on_stage=stage,
                on_progress=progress,
                should_stop=lambda: context.cancelled,
            )
        except (OSError, ValueError, RuntimeError) as exc:
            raise JobError(
                "Full thorax review could not run; check the local model configuration"
            ) from exc
        finally:
            unregister()
            client.close()
        stopped = bool(run.summary["coverage"].get("stopped"))
        with contextlib.suppress(JobCancelledError):
            context.stage("report")
        folder.mkdir(parents=True)
        json_path, html_path = folder / "full-review.json", folder / "full-review.html"
        json_path.write_text(json.dumps(run.summary, indent=2), encoding="utf-8")
        html_path.write_text(render_full_review_html(run.summary, run.thumbnails), "utf-8")
        downloads[identifier] = {"json": json_path, "html": html_path}
        return {
            "id": str(identifier),
            "summary": run.summary,
            "disclaimer_short": SHORT_DISCLAIMER,
            "downloads": {
                "json": f"/api/results/{identifier}/json",
                "html": f"/api/results/{identifier}/html",
            },
        }, stopped

    def full_review_work(body: JobBody) -> Callable[[JobContext], JobOutcome]:
        def work(context: JobContext) -> JobOutcome:
            payload, stopped = execute_full_review(
                body.dataset, body.case_id, body.model_id, context
            )
            if stopped:
                raise JobCancelledError(result=payload)
            verdict = payload["summary"]["verdict"]
            return JobOutcome("abstained" if verdict == "not_assessable" else "succeeded", payload)

        return work

    def submit(body: JobBody) -> tuple[dict[str, Any], bool]:
        result_folder()
        configured = configured_models()
        if body.kind in {"analysis", "full-review"} and body.model_id not in configured:
            raise HTTPException(422, "Unknown model")
        if body.kind == "full-review" and configured[body.model_id].adapter != "ollama":
            raise HTTPException(422, "Full thorax review needs a local vision-language model")
        if (
            body.kind == "analysis"
            and configured[body.model_id].prompt == "P6"
            and body.n_images != 1
        ):
            raise HTTPException(422, "P6 requires exactly one prepared image")
        check_study(body.dataset, body.case_id)
        label: dict[str, Any] = {
            "dataset": body.dataset,
            "case_id": body.case_id,
            "n_images": body.n_images,
        }
        steps: list[dict[str, Any]] = []
        if body.kind == "analysis":
            key = f"analysis|{body.dataset}|{body.case_id}|{body.model_id}|{body.n_images}"
            label["models"] = [body.model_id]
            work = analysis_work(body)
        elif body.kind == "full-review":
            key = f"full-review|{body.dataset}|{body.case_id}|{body.model_id}"
            label["models"] = [body.model_id]
            label["n_images"] = None
            work = full_review_work(body)
        else:
            tags = _ollama_tags(config)
            candidates = [configured[m] for m in RECOMMENDED_MODELS if m in configured]
            steps = [
                {"model_id": item.id, "status": "waiting", "detail": ""}
                if _model_available(item, tags, config)
                else {
                    "model_id": item.id,
                    "status": "skipped",
                    "detail": "Model is not available locally",
                }
                for item in candidates
            ]
            key = f"comparison|{body.dataset}|{body.case_id}|{body.n_images}"
            label["models"] = [item.id for item in candidates]
            work = comparison_work(body)
        try:
            snapshot, created = jobs.submit(body.kind, key, label, work, steps)
        except QueueFullError as exc:
            raise HTTPException(429, str(exc)) from exc
        return snapshot, created

    @app.post("/api/jobs")
    def create_job(body: JobBody) -> dict[str, Any]:
        snapshot, created = submit(body)
        return {"job": snapshot, "created": created}

    @app.get("/api/jobs")
    def list_jobs() -> dict[str, Any]:
        return {
            "jobs": jobs.snapshots(),
            "downloads": pulls.snapshots(),
            "limits": {"max_queued": jobs.max_queued, "max_retained": jobs.max_retained},
            "disclaimer": DISCLAIMER,
        }

    @app.get("/api/jobs/{identifier}/diagnostics")
    def download_diagnostic(identifier: UUID) -> JSONResponse:
        snapshot = jobs.get(identifier)
        if snapshot is None or snapshot.get("diagnostic") is None:
            raise HTTPException(404, "Diagnostic unavailable for this job")
        diagnostic = snapshot["diagnostic"]
        return JSONResponse(
            {
                "job_id": str(identifier),
                "kind": snapshot["kind"],
                "status": snapshot["status"],
                "diagnostic": diagnostic,
                "disclaimer": DISCLAIMER,
            },
            headers={
                "Content-Disposition": (
                    f"attachment; filename=thoraxbench-diagnostic-{diagnostic['trace_id']}.json"
                )
            },
        )

    @app.get("/api/jobs/{identifier}")
    def job_status(identifier: UUID) -> dict[str, Any]:
        snapshot = jobs.get(identifier)
        if snapshot is None:
            raise HTTPException(404, "Unknown job")
        return snapshot

    @app.post("/api/jobs/{identifier}/cancel")
    def cancel_job(identifier: UUID) -> dict[str, Any]:
        snapshot = jobs.cancel(identifier)
        if snapshot is None:
            raise HTTPException(404, "Unknown job")
        return snapshot

    @app.post("/api/jobs/clear")
    def clear_jobs() -> dict[str, Any]:
        return {"removed": jobs.clear_finished()}

    @app.post("/api/analyze")
    def analyze(body: AnalyzeBody) -> dict[str, Any]:
        """Backward-compatible blocking analysis; it still runs through the job queue."""
        snapshot, _ = submit(JobBody(kind="analysis", **body.model_dump()))
        finished = jobs.wait(UUID(snapshot["id"]))
        if finished is None or finished["status"] == "cancelled":
            raise HTTPException(409, "Analysis job was cancelled")
        if finished["result"] is None:
            raise HTTPException(422, finished["error"] or "Analysis could not run")
        return dict(finished["result"])

    @app.post("/api/compare")
    def compare(body: CompareBody) -> dict[str, Any]:
        return export_comparison(body.result_ids, body.omissions)

    @app.post("/api/results/{identifier}/summary")
    def summary(identifier: UUID, body: SummaryBody) -> dict[str, Any]:
        """Deterministic verdict; optionally rephrased by a local LLM under a fact check."""
        if identifier not in downloads or "json" not in downloads[identifier]:
            raise HTTPException(404, "Unknown result")
        path = downloads[identifier]["json"]
        try:
            require_results_path(path, config)
            result = AnalysisResult.model_validate_json(path.read_text(encoding="utf-8"))
        except (ValueError, OSError) as exc:
            raise HTTPException(404, "Unknown result") from exc
        outcome = build_outcome(result, body.lang)
        template = " ".join(outcome.sentences)
        if not body.use_llm:
            return {"text": template, "source": "template", "rejection": None}
        model = configured_models().get(SUMMARY_MODEL)
        if model is None or not model.tag:
            return {"text": template, "source": "template", "rejection": "no summary model"}
        text, source, rejection = llm_summary(
            outcome, body.lang, base_url=config.ollama_url, tag=model.tag
        )
        return {"text": text, "source": source, "rejection": rejection}

    @app.get("/api/results/{identifier}/{kind}")
    def download(identifier: UUID, kind: str, inline: bool = False) -> FileResponse:
        if identifier not in downloads or kind not in downloads[identifier]:
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
            content_disposition_type="inline" if inline and kind == "html" else "attachment",
            headers={
                "Content-Security-Policy": (
                    "default-src 'none'; img-src data:; style-src 'unsafe-inline'; "
                    "base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
                )
            }
            if kind == "html"
            else None,
        )

    def evaluated(call: Callable[[], dict[str, Any]]) -> dict[str, Any]:
        try:
            return call()
        except EvaluationError as exc:
            raise HTTPException(exc.status, exc.message) from exc

    @app.get("/api/evaluation/runs")
    def evaluation_runs() -> dict[str, Any]:
        return evaluated(evaluation.runs)

    @app.get("/api/evaluation/runs/{experiment}/{run}")
    def evaluation_run(experiment: str, run: str) -> dict[str, Any]:
        return evaluated(lambda: evaluation.run(experiment, run))

    @app.get("/api/evaluation/runs/{experiment}/{run}/cases/{variant}/{dataset}/{case_id}")
    def evaluation_case(
        experiment: str, run: str, variant: str, dataset: str, case_id: str
    ) -> dict[str, Any]:
        return evaluated(lambda: evaluation.case(experiment, run, variant, dataset, case_id))

    @app.get("/api/evaluation/compare")
    def evaluation_compare(
        run: list[str] = Query(default_factory=list, max_length=8),  # noqa: B008 - FastAPI idiom
    ) -> dict[str, Any]:
        return evaluated(lambda: evaluation.compare(run))

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
