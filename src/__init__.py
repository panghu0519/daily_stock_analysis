"""Project package bootstrap.

Keep package import lightweight.  A one-shot finder wraps only
``src.core.pipeline`` so batch report coverage can be extended without
rewriting the large pipeline module.
"""

from __future__ import annotations

import importlib.abc
import importlib.machinery
import logging
import sys


_logger = logging.getLogger(__name__)
_TARGET = "src.core.pipeline"


class _PipelinePatchLoader(importlib.abc.Loader):
    def __init__(self, wrapped_loader):
        self._wrapped_loader = wrapped_loader

    def create_module(self, spec):
        create_module = getattr(self._wrapped_loader, "create_module", None)
        return create_module(spec) if callable(create_module) else None

    def exec_module(self, module):
        self._wrapped_loader.exec_module(module)
        try:
            from src.batch_report_summary import patch_pipeline_module

            patch_pipeline_module(module)
        except Exception as exc:  # fail-open: never block the stock analyzer import
            _logger.warning("batch report summary patch skipped: %s", exc)


class _PipelinePatchFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        if fullname != _TARGET:
            return None

        # One-shot hook: remove before delegating to PathFinder to avoid
        # recursion and leave the import system untouched afterwards.
        try:
            sys.meta_path.remove(self)
        except ValueError:
            pass

        spec = importlib.machinery.PathFinder.find_spec(fullname, path)
        if spec is not None and spec.loader is not None:
            spec.loader = _PipelinePatchLoader(spec.loader)
        return spec


if _TARGET not in sys.modules:
    sys.meta_path.insert(0, _PipelinePatchFinder())
