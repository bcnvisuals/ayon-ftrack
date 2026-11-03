"""BCN: offline tests for the ftrack bridge guards (1.6.9-bcn.1).

Run from the repo root:  python3 -m unittest discover -s tests/bcn -v
"""

import os
import sys
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
import _stubs  # noqa: E402

_stubs.install()
sys.modules.setdefault("arrow", mock.MagicMock(name="arrow"))

import ftrack_common  # noqa: E402

HANDLERS = os.path.join(_stubs.PROCESSOR, "default_handlers")
PUBLISH = os.path.join(_stubs.CLIENT, "plugins", "publish")


def handler(name):
    return _stubs.load_file(
        f"bcn_test_{name}", os.path.join(HANDLERS, f"{name}.py"))


def bare(cls, **attrs):
    """Instance of cls without __init__, with 'log' and attrs overridden."""
    attrs.setdefault("log", mock.MagicMock())
    sub = type(f"Test{cls.__name__}", (cls,), attrs)
    return object.__new__(sub)


def publish_plugin(name):
    return _stubs.load_file(
        f"bcn_test_pub_{name}", os.path.join(PUBLISH, f"{name}.py"))


# --- fakes ---------------------------------------------------------------

class Entity(dict):
    """dict that also answers 'entity_type' like an ftrack entity."""

    def __init__(self, entity_type="Project", **data):
        super().__init__(**data)
        self.entity_type = entity_type


def project(bridged=None, auto_sync=False, name="bcn_bridgetest_new",
            status="active", pid="p1"):
    attrs = {"auto_sync_enabled": auto_sync}
    if bridged is not None:
        attrs["ayon_bridged"] = bridged
    return Entity("Project", id=pid, full_name=name, name=name,
                  status=status, custom_attributes=attrs)


class Result:
    def __init__(self, items):
        self._items = list(items)

    def first(self):
        return self._items[0] if self._items else None

    def one(self):
        assert len(self._items) == 1, self._items
        return self._items[0]

    def all(self):
        return list(self._items)


class FakeSession:
    """Answers queries from a list of (substring, items) rules."""

    def __init__(self, rules=None):
        self.rules = list(rules or [])
        self.queries = []
        self.api_user = "tester"
        self.event_hub = mock.MagicMock()

    def query(self, expression):
        self.queries.append(expression)
        for needle, items in self.rules:
            if needle in expression:
                return Result(items)
        return Result([])


# --- the flag ------------------------------------------------------------

class TestBridgedFlag(unittest.TestCase):
    def test_values(self):
        f = ftrack_common.is_project_bridged
        self.assertTrue(f(project(True)))
        self.assertTrue(f(project("1")))
        self.assertFalse(f(project(False)))
        self.assertFalse(f(project("0")))
        self.assertFalse(f(project(None)), "attribute missing -> stock")
        self.assertFalse(f(None))
        self.assertFalse(f({}))

    def test_by_name_quotes(self):
        s = FakeSession([("Project", [project(True)])])
        self.assertTrue(ftrack_common.is_project_bridged_by_name(s, 'a"b'))
        self.assertIn('a\\"b', s.queries[-1])
        self.assertFalse(ftrack_common.is_project_bridged_by_name(s, ""))

    def test_attribute_definition(self):
        src = open(os.path.join(
            _stubs.CLIENT, "common", "custom_attributes.py")).read()
        self.assertIn("CUST_ATTR_BRIDGED", src)
        roles = sys.modules["ayon_ftrack.common.custom_attributes"]
        self.assertEqual(
            roles._DEFAULT_MANDATORY_ROLES["ayon_bridged"]["write_security_roles"],
            ["API", "Administrator"],
        )
        server_src = open(os.path.join(
            _stubs.REPO, "server", "settings", "custom_attributes.py")).read()
        self.assertIn('"ayon_bridged": {', server_src)
        self.assertIn("ayon_bridged: CustomAttributeModel", server_src)


# --- processor guards -----------------------------------------------------

class TestSyncAction(unittest.TestCase):
    def setUp(self):
        self.mod = handler("action_sync_from_ftrack")
        self.action = bare(
            self.mod.SyncFromFtrackAction,
            session=property(lambda self: self._session),
            launch_identifier="sync.from.ftrack.to.ayon.launch",
        )
        self.action.get_project_from_entity = lambda e: e
        self.action.show_interface = mock.MagicMock()
        self.syncer_cls = mock.MagicMock()
        self.syncer_cls.return_value.report_items = []
        self.mod.SyncFromFtrack = self.syncer_cls

    def test_refuses_bridged(self):
        out = self.action.launch(None, [project(True)], {})
        self.assertEqual(out["success"], False)
        self.assertIn("ftrack Bridge", out["message"])
        self.syncer_cls.assert_not_called()

    def test_stock_project_syncs(self):
        self.assertTrue(self.action.launch(None, [project(False)], {}))
        self.syncer_cls.return_value.sync_to_server.assert_called_once()

    def test_leecher_start_skips_bridged(self):
        s = FakeSession([("User", [{"username": "u", "id": "1"}]),
                         ("Project", [
                             project(True, auto_sync=True, pid="b"),
                             project(False, auto_sync=True, pid="n"),
                             project(None, auto_sync=True, pid="old"),
                             project(False, auto_sync=False, pid="off"),
                         ])])
        self.action._session = s
        self.mod.ftrack_api.event.base.Event = lambda **kw: kw
        self.action._on_leecher_start(None)
        launched = [
            c.args[0]["data"]["selection"][0]["entityId"]
            for c in s.event_hub.publish.call_args_list
        ]
        self.assertEqual(sorted(launched), ["n", "old"])


class TestPrepareProject(unittest.TestCase):
    def setUp(self):
        self.mod = handler("action_prepare_project")
        self.action = bare(self.mod.PrepareProjectServer)
        self.mod.SyncFromFtrack = mock.MagicMock()

    def test_interface_refuses_bridged(self):
        out = self.action.interface(None, [project(True)], {"data": {}})
        self.assertFalse(out["success"])
        self.assertIn("ftrack Bridge", out["message"])

    def test_launch_refuses_bridged(self):
        out = self.action.launch(
            None, [project(True)], {"data": {"values": {"x": 1}}})
        self.assertFalse(out["success"])
        self.mod.SyncFromFtrack.assert_not_called()


class TestEventSync(unittest.TestCase):
    def setUp(self):
        self.mod = handler("event_sync_from_ftrack")

    def make(self, ft_project):
        proc = bare(self.mod.SyncProcess, session=FakeSession())
        proc._ft_project = ft_project
        proc._project_name = ft_project["full_name"]
        proc._project_settings = {"ftrack": {"enabled": True}}
        return proc

    def test_bridged_skipped(self):
        self.assertFalse(self.make(project(True, auto_sync=True))
                         ._project_enabled_validation())

    def test_stock_project_passes(self):
        self.mod.is_ftrack_enabled_in_settings = lambda s: True
        self.assertTrue(self.make(project(False, auto_sync=True))
                        ._project_enabled_validation())


class TestDeleteAction(unittest.TestCase):
    def setUp(self):
        self.mod = handler("action_delete_entities")
        self.action = bare(self.mod.DeleteEntitiesAction)
        self.action.valid_roles = lambda *a: True
        self.roles = ["administrator"]
        self.action.get_user_roles_from_event = (
            lambda s, e, lower=False: self.roles)
        self.ft_project = project(False)
        self.action.get_project_from_entity = (
            lambda e, s=None: self.ft_project)
        self.shot = Entity("Shot", id="s1")
        self.event = {"data": {"selection": [
            {"entityType": "task", "entityId": "s1"}]}}

    def test_admin_on_stock_project(self):
        self.assertTrue(self.action.discover(None, [self.shot], self.event))

    def test_bridged_hidden_and_refused(self):
        self.ft_project = project(True)
        self.assertFalse(self.action.discover(None, [self.shot], self.event))
        out = self.action.launch(None, [self.shot], self.event)
        self.assertFalse(out["success"])

    def test_non_admin_keeps_stock_behaviour_off_bridged(self):
        # Review fix: projects that aren't bridged keep the stock role rules
        self.roles = ["project manager"]
        self.assertTrue(self.action.discover(None, [self.shot], self.event))


# --- publish ---------------------------------------------------------------

class Ctx(list):
    def __init__(self, data, instances=()):
        super().__init__(instances)
        self.data = data


class Inst:
    def __init__(self, data):
        self.data = data

    def __repr__(self):
        return f"Inst({self.data.get('productName')})"


class TestCollectFtrackApi(unittest.TestCase):
    """Folder /Film/SH010 is linked to ftrack shot 'ftshot'.

    AYON task 'comp' is linked to ftrack task 'fttask', which was renamed in
    ftrack to 'Comp_v2'. AYON task 'paint' has no link; ftrack has a task
    called 'paint' under the shot (a name match).
    """

    def setUp(self):
        self.mod = publish_plugin("collect_ftrack_api")
        self.ayon = mock.MagicMock()
        self.mod.ayon_api = self.ayon
        self.ayon.get_folders.side_effect = lambda project, folder_paths, **k: [
            {"path": p, "ownAttrib": {"ftrackId": "ftshot"}}
            for p in folder_paths if p == "/Film/SH010"
        ]
        self.ayon.get_folder_by_path.side_effect = (
            lambda project, path, **k: {"id": "f1"} if path in (
                "/Film/SH010", "/Film/SH099") else None)
        self.ayon.get_tasks.return_value = [
            {"name": "comp", "ownAttrib": {"ftrackId": "fttask"}},
            {"name": "paint", "ownAttrib": {}},
        ]
        self.shot = Entity("Shot", id="ftshot", name="SH010", parent_id="film",
                           project_id="ftproj")
        self.fttask = Entity("Task", id="fttask", name="Comp_v2",
                             parent_id="ftshot", project_id="ftproj")
        self.ftpaint = Entity("Task", id="ftpaint", name="paint",
                              parent_id="ftshot", project_id="ftproj")
        self.unlinked = Entity("Shot", id="ft99", name="SH099", parent_id="film",
                               project_id="ftproj")

    def run_plugin(self, bridged, folder, task):
        ft_project = project(bridged)
        session = FakeSession([
            ("Project where", [ft_project]),
            ("TypedContext where id in", [self.shot]),
            ('where id in ("fttask")', [self.fttask]),
            ("from TypedContext", [self.shot, self.unlinked]),
            ("select id, name from Task", [self.fttask, self.ftpaint]),
        ])
        fake_api = types.SimpleNamespace(Session=lambda **k: session)
        sys.modules["ftrack_api"] = fake_api
        ctx = Ctx({"projectName": "bcn_bridgetest_new",
                   "folderPath": folder, "task": task})
        plugin = bare(self.mod.CollectFtrackApi)
        plugin.process(ctx)
        return ctx, session

    def tearDown(self):
        sys.modules["ftrack_api"] = mock.MagicMock(name="ftrack_api")

    def test_linked_shot_and_renamed_task_by_id(self):
        for bridged in (True, False):
            ctx, _ = self.run_plugin(bridged, "/Film/SH010", "comp")
            self.assertIs(ctx.data["ftrackEntity"], self.shot)
            self.assertIs(ctx.data["ftrackTask"], self.fttask,
                          f"renamed task found by id (bridged={bridged})")

    def test_stale_copied_ftrackid_nonbridged_falls_back_to_name(self):
        # Review High 2: the AYON task links to a task under ANOTHER shot.
        # Stock picks by name under this shot; the fork must not use the link.
        # (the fake session doesn't filter by parent, so name it apart)
        self.fttask = Entity("Task", id="fttask", name="Comp_elsewhere",
                             parent_id="ftshot2", project_id="ftproj")
        self.ftcomp_here = Entity("Task", id="ftcomp", name="comp",
                                  parent_id="ftshot", project_id="ftproj")
        self.ftpaint = self.ftcomp_here      # name lookup returns this shot's comp
        ctx, _ = self.run_plugin(False, "/Film/SH010", "comp")
        self.assertIs(ctx.data["ftrackTask"], self.ftcomp_here)

    def test_moved_task_bridged_found_by_id(self):
        # Bridged: the ID is the link, even if the task moved to another shot
        self.fttask = Entity("Task", id="fttask", name="Comp_v2",
                             parent_id="ftshot2", project_id="ftproj")
        ctx, _ = self.run_plugin(True, "/Film/SH010", "comp")
        self.assertIs(ctx.data["ftrackTask"], self.fttask)

    def test_other_project_id_never_used(self):
        self.fttask = Entity("Task", id="fttask", name="Comp_v2",
                             parent_id="x", project_id="OTHER")
        ctx, _ = self.run_plugin(True, "/Film/SH010", "comp")
        self.assertIsNone(ctx.data["ftrackTask"])

    def test_unlinked_folder_bridged_publishes_without_ftrack(self):
        ctx, session = self.run_plugin(True, "/Film/SH099", "comp")
        self.assertIsNone(ctx.data["ftrackEntity"])
        self.assertIsNone(ctx.data["ftrackTask"])
        self.assertTrue(ctx.data["ftrackProjectBridged"])
        self.assertFalse(any("name in (" in q for q in session.queries),
                         "no lookup by names on a bridged project")

    def test_unlinked_folder_stock_still_fails(self):
        with self.assertRaises(_stubs.PublishError):
            self.run_plugin(False, "/Film/SH099", "comp")

    def test_unlinked_task_bridged_none_stock_by_name(self):
        ctx, _ = self.run_plugin(True, "/Film/SH010", "paint")
        self.assertIsNone(ctx.data["ftrackTask"])
        ctx, _ = self.run_plugin(False, "/Film/SH010", "paint")
        self.assertIs(ctx.data["ftrackTask"], self.ftpaint)


class TestDownstreamPlugins(unittest.TestCase):
    def test_validator_skips_on_bridged(self):
        mod = publish_plugin("validate_custom_ftrack_attributes")
        plugin = bare(mod.ValidateFtrackAttributes)
        plugin._raise = mock.MagicMock(side_effect=AssertionError("raised"))
        inst = Inst({})
        inst.context = Ctx({"ftrackTask": None, "ftrackProjectBridged": True})
        plugin.process(inst)  # no raise
        inst.context = Ctx({"ftrackTask": None})
        with self.assertRaises(AssertionError):
            plugin.process(inst)

    def test_hierarchy_skipped_on_bridged(self):
        mod = publish_plugin("integrate_hierarchy_ftrack")
        plugin = bare(mod.IntegrateHierarchyToFtrack)
        plugin._get_active_hierarchy = lambda c: {"x": {}}
        plugin.import_to_ftrack = mock.MagicMock()
        for bridged, called in ((True, False), (False, True)):
            plugin.import_to_ftrack.reset_mock()
            ctx = Ctx({"hierarchyContext": {}, "projectName": "p",
                       "ftrackSession": FakeSession(
                           [("Project", [project(bridged)])])})
            plugin.process(ctx)
            self.assertEqual(plugin.import_to_ftrack.called, called)

    def test_api_integrator_skips_without_entities(self):
        mod = publish_plugin("integrate_ftrack_api")
        plugin = bare(mod.IntegrateFtrackApi)
        plugin.integrate_to_ftrack = mock.MagicMock()
        inst = Inst({"ftrackComponentsList": [{}], "ftrackEntity": None,
                     "ftrackTask": None})
        inst.context = Ctx({})
        plugin.process(inst)
        plugin.integrate_to_ftrack.assert_not_called()


class TestLaunchHook(unittest.TestCase):
    def setUp(self):
        self.mod = _stubs.load_file(
            "bcn_test_hook",
            os.path.join(_stubs.CLIENT, "launch_hooks", "post_ftrack_changes.py"))
        self.mod.ayon_api = mock.MagicMock()
        self.mod.ayon_api.get_folder_by_path.return_value = {
            "id": "f1", "attrib": {"ftrackId": "ftshot"}}
        self.hook = bare(self.mod.PostFtrackHook)
        self.shot = Entity("Shot", id="ftshot", project_id="ftproj")
        self.renamed = Entity("Task", id="fttask", name="Comp_v2",
                              parent_id="ftshot", project_id="ftproj")
        self.byname = Entity("Task", id="ftname", name="comp",
                             parent_id="ftshot", project_id="ftproj")

    def find(self, bridged, linked):
        self.mod.ayon_api.get_task_by_name.return_value = {
            "ownAttrib": {"ftrackId": "fttask"} if linked else {}}
        s = FakeSession([
            ("Project where", [project(bridged)]),
            ("TypedContext where id", [self.shot]),
            ("Task where id is 'fttask'", [self.renamed]),
            ("and name is", [self.byname]),
        ])
        return self.hook._find_ftrack_task_entity(s, "p", "/Film/SH010", "comp")

    def test_id_first(self):
        self.assertIs(self.find(True, True), self.renamed)
        self.assertIs(self.find(False, True), self.renamed)

    def test_name_fallback_only_on_stock(self):
        self.assertIsNone(self.find(True, False))
        self.assertIs(self.find(False, False), self.byname)


if __name__ == "__main__":
    unittest.main()
