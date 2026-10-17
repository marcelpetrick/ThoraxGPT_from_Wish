# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Pinned, checksummed MONAI ``lung_nodule_ct_detection`` bundle files (inference only).

The bundle is published openly (not gated) by the MONAI organisation on Hugging Face under
Apache-2.0; its ``docs/data_license.txt`` names the training data: LUNA16 (CC BY 4.0), a
subset of LIDC-IDRI (CC BY 3.0). Every file is pinned to one repository revision, its byte
size and its SHA-256. Weights are fetched only by an explicit operator command
(``scripts/fetch_monai_bundle.py``) into the git-ignored data directory, never automatically
and never by inference code. Only the PyTorch state dict ``models/model.pt`` is fetched; the
TorchScript ``model.ts`` is not, because loading TorchScript executes serialized code.
"""

from __future__ import annotations

import hashlib
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import httpx

from thoraxbench.config import Settings

BUNDLE_NAME = "lung_nodule_ct_detection"
BUNDLE_REPO = "MONAI/lung_nodule_ct_detection"
BUNDLE_VERSION = "0.6.10"
BUNDLE_REVISION = "9d6622fda0e52be0a4155fed2e0afb9c17bcd80b"
BUNDLE_LICENSE = "Apache-2.0"
BUNDLE_HOST = "https://huggingface.co"
WEIGHTS_FILE = "models/model.pt"
MAX_FILE_BYTES = 200_000_000


@dataclass(frozen=True)
class BundleFile:
    """One pinned bundle file."""

    path: str
    size: int
    sha256: str


#: Files fetched by the explicit command. Text files are the license/terms snapshot and
#: the upstream inference configuration the adapter reproduces.
BUNDLE_FILES: tuple[BundleFile, ...] = (
    BundleFile(
        WEIGHTS_FILE, 83_709_381, "b5e79231466adae93a6fe8e8594029e9add142914e223b879aa0343bb2402d01"
    ),
    BundleFile(
        "LICENSE", 11_357, "c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4"
    ),
    BundleFile(
        "docs/data_license.txt",
        467,
        "4b841ee56f244d13db9b9a8eea2fc3823ef86775ded9e7a371012465181412ef",
    ),
    BundleFile(
        "configs/metadata.json",
        4_455,
        "bf621efe2b921a77f753ba58c2e562eb6d9afd3852ae2e4240b7a0e2bb278820",
    ),
    BundleFile(
        "configs/inference.json",
        6_991,
        "d8e69c1ac4fa419181d0af3a03d5a6aef7f8f4cb1e46cfecbc4dc6879090cda3",
    ),
)

WEIGHTS_ITEM = BUNDLE_FILES[0]
WEIGHTS_SHA256 = WEIGHTS_ITEM.sha256


class BundleIntegrityError(RuntimeError):
    """A local bundle file is missing, has the wrong size or the wrong SHA-256."""


def bundle_dir(settings: Settings) -> Path:
    """``<data>/models/monai/<bundle>/<revision>/`` (git-ignored)."""
    root = settings.data_path("models", "monai", BUNDLE_NAME, BUNDLE_REVISION)
    base = settings.data_dir.resolve()
    if not root.resolve().is_relative_to(base):
        raise BundleIntegrityError("bundle directory escapes the configured data directory")
    return root


def _safe_target(root: Path, item: BundleFile) -> Path:
    target = root / item.path
    if not target.resolve().is_relative_to(root.resolve()):
        raise BundleIntegrityError("bundle file escapes its directory")
    for part in (target, *target.parents):
        if part == root:
            break
        if part.is_symlink():
            raise BundleIntegrityError("bundle file path contains a symlink")
    return target


def file_url(item: BundleFile) -> str:
    """Pinned download URL of *item* (revision-addressed, not a moving branch)."""
    return f"{BUNDLE_HOST}/{BUNDLE_REPO}/resolve/{BUNDLE_REVISION}/{item.path}"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(1 << 20):
            digest.update(block)
    return digest.hexdigest()


def verify_file(root: Path, item: BundleFile) -> str:
    """Return the verified SHA-256 of ``root/item.path``.

    Raises:
        BundleIntegrityError: if the file is missing, a symlink, or its size/hash differs.
    """
    path = _safe_target(root, item)
    if path.is_symlink() or not path.is_file():
        raise BundleIntegrityError(f"bundle file missing: {item.path}")
    if path.stat().st_size != item.size:
        raise BundleIntegrityError(f"bundle file has an unexpected size: {item.path}")
    digest = _sha256(path)
    if digest != item.sha256:
        raise BundleIntegrityError(f"bundle file checksum mismatch: {item.path}")
    return digest


def verify_bundle(settings: Settings) -> dict[str, str]:
    """Verify every pinned file; return ``{path: sha256}``.

    Raises:
        BundleIntegrityError: on the first missing or altered file.
    """
    root = bundle_dir(settings)
    return {item.path: verify_file(root, item) for item in BUNDLE_FILES}


def weights_path(settings: Settings) -> Path:
    """Path of the pinned state dict (not verified; see :func:`verify_file`)."""
    return bundle_dir(settings) / WEIGHTS_FILE


def fetch_bundle(
    settings: Settings,
    *,
    acknowledge_license: bool,
    client: httpx.Client | None = None,
    progress: Callable[[str], None] = lambda _msg: None,
) -> dict[str, str]:
    """Download missing pinned files, verify each and move it into place atomically.

    Already verified files are kept. A partial or altered download is deleted and raises.

    Raises:
        PermissionError: without an explicit license acknowledgement.
        BundleIntegrityError: if a downloaded file fails the size or checksum check.
        httpx.HTTPError: on transport or HTTP errors.
    """
    if not acknowledge_license:
        raise PermissionError(
            "Read the bundle terms first (Apache-2.0 code/weights; training data LUNA16 "
            "CC BY 4.0 / LIDC-IDRI CC BY 3.0) and pass the explicit acknowledgement"
        )
    root = bundle_dir(settings)
    own = client is None
    http = client or httpx.Client(timeout=120.0, follow_redirects=True, trust_env=False)
    try:
        for item in BUNDLE_FILES:
            try:
                verify_file(root, item)
                progress(f"verified {item.path}")
                continue
            except BundleIntegrityError:
                pass
            target = _safe_target(root, item)
            target.parent.mkdir(parents=True, exist_ok=True)
            progress(f"downloading {item.path} ({item.size} bytes)")
            digest = hashlib.sha256()
            size = 0
            with tempfile.NamedTemporaryFile(
                dir=target.parent, prefix=target.name + ".", suffix=".partial", delete=False
            ) as handle:
                partial = Path(handle.name)
                try:
                    with http.stream("GET", file_url(item)) as response:
                        response.raise_for_status()
                        for block in response.iter_bytes():
                            size += len(block)
                            if size > min(item.size, MAX_FILE_BYTES):
                                break
                            digest.update(block)
                            handle.write(block)
                    if size != item.size or digest.hexdigest() != item.sha256:
                        raise BundleIntegrityError(
                            f"downloaded file failed verification: {item.path}"
                        )
                    handle.flush()
                    _safe_target(root, item)
                    partial.replace(target)
                finally:
                    partial.unlink(missing_ok=True)
            progress(f"verified {item.path}")
    finally:
        if own:
            http.close()
    return verify_bundle(settings)
