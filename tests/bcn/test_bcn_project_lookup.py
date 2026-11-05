"""BCN 1.6.9-bcn.2: find_ftrack_project - the ftrack project of an AYON project.

Name match first (stock behaviour), then the ftrack id the bridge stores on
the AYON project, only when exactly one AYON project carries it.
"""
import importlib.util
import os
import sys
import types
import unittest
from unittest import mock

HERE = os.path.dirname(__file__)
BRIDGED = os.path.join(HERE, "..", "..", "client", "ayon_ftrack", "common", "bridged.py")


class _Loaded:
    """bridged.py plus a fake ayon_api, swapped into sys.modules only while used."""
    def __init__(self, projects):
        api = types.ModuleType("ayon_api")
        api.get_project = lambda name, fields=None: (
            {"name": name, "attrib": {"ftrackId": projects[name]}} if name in projects else None)
        api.get_projects = lambda active=True, fields=None: [
            {"name": n, "attrib": {"ftrackId": f}} for n, f in projects.items()]
        pkg = types.ModuleType("bcn_common_under_test")
        pkg.__path__ = [os.path.dirname(BRIDGED)]
        const = types.ModuleType("bcn_common_under_test.constants")
        const.CUST_ATTR_BRIDGED = "ayon_bridged"
        self.modules = {"ayon_api": api, "bcn_common_under_test": pkg,
                        "bcn_common_under_test.constants": const}
        with mock.patch.dict(sys.modules, self.modules):
            spec = importlib.util.spec_from_file_location("bcn_common_under_test.bridged", BRIDGED)
            self.mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(self.mod)

    def find_ftrack_project(self, *args, **kwargs):
        with mock.patch.dict(sys.modules, self.modules):
            return self.mod.find_ftrack_project(*args, **kwargs)


def load_bridged(projects):
    return _Loaded(projects)


class FakeQuery:
    def __init__(self, rows): self.rows = rows
    def first(self): return self.rows[0] if self.rows else None


class FakeSession:
    """ftrack projects as {id: full_name}; records the queries."""
    def __init__(self, projects): self.projects, self.queries = projects, []
    def query(self, expr):
        self.queries.append(expr)
        if "full_name is" in expr:
            name = expr.split('full_name is "', 1)[1].rsplit('"', 1)[0]
            return FakeQuery([{"id": i, "full_name": n} for i, n in self.projects.items() if n == name])
        pid = expr.split('id is "', 1)[1].rsplit('"', 1)[0]
        return FakeQuery([{"id": pid, "full_name": self.projects[pid]}] if pid in self.projects else [])


FT = "3bb1ac79-fc4c-4ebb-8274-83a969953411"


class TestFindFtrackProject(unittest.TestCase):
    def test_name_match_wins_like_stock(self):
        mod = load_bridged({"Disney": "aaaa-1111"})
        s = FakeSession({"aaaa-1111": "Disney", FT: "Other"})
        self.assertEqual(mod.find_ftrack_project(s, "Disney")["id"], "aaaa-1111")
        self.assertEqual(len(s.queries), 1)   # never consults AYON when the name matches

    def test_name_match_wins_even_if_attrib_points_elsewhere(self):
        mod = load_bridged({"Disney": FT})
        s = FakeSession({"aaaa-1111": "Disney", FT: "Other"})
        self.assertEqual(mod.find_ftrack_project(s, "Disney")["id"], "aaaa-1111")

    def test_bridge_project_found_by_stored_id(self):
        mod = load_bridged({"bcn_bridgetest_new": FT})
        s = FakeSession({FT: "Bridge test - new (pipeline only, do not use)"})
        self.assertEqual(mod.find_ftrack_project(s, "bcn_bridgetest_new")["id"], FT)

    def test_refuses_when_two_ayon_projects_claim_the_id(self):
        mod = load_bridged({"bcn_bridgetest_new": FT, "copied_from_preset": FT})
        s = FakeSession({FT: "Bridge test - new"})
        self.assertIsNone(mod.find_ftrack_project(s, "bcn_bridgetest_new"))

    def test_no_or_bad_id_returns_none(self):
        for value in (None, "", 'x" or id is "y'):
            mod = load_bridged({"p": value})
            self.assertIsNone(mod.find_ftrack_project(FakeSession({FT: "Other"}), "p"))

    def test_unknown_ayon_project_returns_none(self):
        mod = load_bridged({})
        self.assertIsNone(mod.find_ftrack_project(FakeSession({FT: "Other"}), "nope"))

    def test_quotes_in_name_are_escaped(self):
        mod = load_bridged({})
        s = FakeSession({})
        mod.find_ftrack_project(s, 'a"b')
        self.assertIn('full_name is "a\\"b"', s.queries[0])


if __name__ == "__main__":
    unittest.main()
