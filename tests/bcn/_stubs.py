"""BCN: stub third-party modules so the guards can be tested offline.

Only what the code under test touches is faked: ftrack_api, ayon_api,
pyblish, ayon_core and ayon_applications. The real 'common' package is
loaded twice, as 'ayon_ftrack.common' (client) and 'ftrack_common'
(services), exactly as the addon and the service images use it.
"""

import importlib.util
import os
import sys
import types
import logging
from unittest import mock

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
CLIENT = os.path.join(REPO, "client", "ayon_ftrack")
PROCESSOR = os.path.join(REPO, "services", "processor", "processor")


def _module(name, **attrs):
    mod = types.ModuleType(name)
    mod.__dict__.update(attrs)
    sys.modules[name] = mod
    return mod


def _mock_module(name):
    mod = mock.MagicMock(name=name)
    mod.__path__ = []
    mod.__spec__ = None
    sys.modules[name] = mod
    return mod


def _load_package(name, path):
    spec = importlib.util.spec_from_file_location(
        name, os.path.join(path, "__init__.py"),
        submodule_search_locations=[path],
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def load_file(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


class _Plugin:
    """Minimal pyblish plugin base."""
    log = logging.getLogger("bcn-test-plugin")
    order = 0
    label = ""
    families = []
    hosts = []


class PublishError(Exception):
    pass


_done = False


def install():
    global _done
    if _done:
        return
    _done = True
    for name in (
        "ftrack_api", "ftrack_api.entity", "ftrack_api.entity.base",
        "ftrack_api.event", "ftrack_api.event.base", "ftrack_api.symbol",
        "ftrack_api.operation", "ftrack_api.exception",
        "ayon_api", "ayon_api.utils", "ayon_api.entity_hub",
        "clique",
    ):
        _mock_module(name)
    api_stub = sys.modules["ayon_api"]
    api_stub.get_base_url.return_value = "http://ayon.test"
    api_stub.get_service_addon_name.return_value = "ftrack"
    api_stub.get_service_addon_version.return_value = "1.6.9-bcn.1"

    pyblish = _module("pyblish")
    api = _module(
        "pyblish.api",
        ContextPlugin=_Plugin, InstancePlugin=_Plugin,
        CollectorOrder=0, ValidatorOrder=1, ExtractorOrder=2,
        IntegratorOrder=3, current_host=lambda: "nuke",
    )
    pyblish.api = api

    _module("ayon_core")
    _module("ayon_core.lib", filter_profiles=lambda *a, **k: None)
    _module(
        "ayon_core.pipeline",
        PublishError=PublishError, KnownPublishError=PublishError,
    )
    _module(
        "ayon_core.pipeline.publish",
        PublishValidationError=PublishError,
        KnownPublishError=PublishError,
        OptionalPyblishPluginMixin=object,
        ValidateContentsOrder=1,
    )
    _module(
        "ayon_applications",
        PostLaunchHook=type("PostLaunchHook", (), {}),
        PreLaunchHook=type("PreLaunchHook", (), {}),
        LaunchTypes=types.SimpleNamespace(local="local", farm="farm"),
    )
    _module("ayon_core.settings", get_project_settings=lambda *a: {})

    # Client side: a light 'ayon_ftrack' package with the real 'common'
    pkg = _module("ayon_ftrack")
    pkg.__path__ = [CLIENT]
    common = _load_package("ayon_ftrack.common", os.path.join(CLIENT, "common"))
    pkg.common = common
    pipeline = _module("ayon_ftrack.pipeline")
    pipeline.__path__ = []
    plugin = _module(
        "ayon_ftrack.pipeline.plugin",
        FtrackPublishContextPlugin=_Plugin,
        FtrackPublishInstancePlugin=_Plugin,
    )
    pipeline.plugin = plugin

    # Service side: same 'common' under the name the images use
    _load_package("ftrack_common", os.path.join(CLIENT, "common"))
    processor = _module("processor")
    processor.__path__ = [PROCESSOR]
    _module("processor.lib", SyncFromFtrack=mock.MagicMock(name="SyncFromFtrack"))
