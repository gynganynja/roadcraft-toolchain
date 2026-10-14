"""RC077 save-compat: a candidate's savable descriptors against the baseline existing saves were written with
(C:/RC_RE/research/save_semantics.md, library/save-compatibility.md).  Synthetic classes only."""

import contextlib
import io
import json
import tempfile
import unittest
import warnings
import zipfile
from pathlib import Path

from roadcraft import validate

NO_GAME = str(Path(tempfile.gettempdir()) / "roadcraft-no-game-root")
TRUCK = "ssl/auto_ute_ute.cls"
DESCS = ("SavableUidPropDesc", "TruckFuelSavablePropDesc", "TruckConstraintsSavablePropDesc")


def ute(*, descs=DESCS, powered=(), controllable=(), chains="", sequential=None, cargo=None) -> str:
    """A truck class with the save-relevant blocks. ``sequential`` is {chain: [(stage, [joint or (addon, joint)])]}"""
    holders = "\n".join(f"         {{ desc = {{ __type = \"{t}\" }} }}," for t in descs)
    power = "\n".join(f"         {{ constraintName = \"{n}\" }}," for n in powered)
    ctrl = "\n".join(f"         {{ constraintName = \"{n}\" angularSpeed = 45 }}," for n in controllable)
    seq = ""
    for chain, stages in (sequential or {}).items():
        links = ""
        for stage, joints in stages:
            items = []
            for j in joints:
                addon, name = j if isinstance(j, tuple) else (None, j)
                items.append(f"{{ constraintName = \"{name}\"" + (f" addon = \"{addon}\"" if addon else "") + " }")
            links += f"            {stage} = {{ constraints = [ {', '.join(items)} ] }}\n"
        seq += f"         {chain} = {{\n            links = {{\n{links}            }}\n         }}\n"
    cargo_block = ""
    if cargo is not None:
        slots = "\n".join(f"      {s} = {{ bone = \"BoneCargo_cdt\" __type = \"CargoSlot\" }}" for s in cargo)
        cargo_block = f"   prop_truck_cargo_controller = {{\n{slots}\n   }}\n"
    return (
        "properties = {\n"
        "   prop_savable_object = {\n      savablePropDescs = [\n" + holders + "\n      ]\n   }\n"
        "   prop_truck_constraint_view = {\n"
        f"      powerConstraints = [\n{power}\n      ]\n"
        f"      controllableConstraints = [\n{ctrl}\n      ]\n"
        f"      constraintChains = {{\n{chains}\n      }}\n"
        f"      constraintSequentialChains = {{\n{seq}      }}\n"
        "   }\n" + cargo_block + "}\n")


class SaveCompatBase(unittest.TestCase):
    def pak(self, members: dict[str, str], name: str) -> Path:
        folder = Path(tempfile.mkdtemp())
        path = folder / name
        self.addCleanup(lambda: (path.unlink(missing_ok=True), folder.rmdir()))
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            with zipfile.ZipFile(path, "w") as archive:
                for member, data in members.items():
                    archive.writestr(member, data)
        return path

    def run_pair(self, old: str, new: str, *, old_name=TRUCK, new_name=TRUCK):
        base = self.pak({old_name: old}, "installed.pak")
        cand = self.pak({new_name: new}, "candidate.pak")
        return validate.validate(cand, rules=["save-compat"], game_root=NO_GAME, baseline=base)

    @staticmethod
    def rows(findings):
        return sorted((f.code, f.severity, f.key.rsplit(".", 1)[-1]) for f in findings)


class SequentialChainTests(SaveCompatBase):
    def test_l275_v35_new_chain_is_an_error(self) -> None:
        old = ute(controllable=("toolbox_lh", "toolbox_rh"))
        new = ute(sequential={"Toolboxes": [("Stage1", ["toolbox_lh", "toolbox_rh"])]})
        found = self.run_pair(old, new)
        self.assertIn(("RC077", "error", "Toolboxes"), self.rows(found))
        self.assertIn(("RC077", "warning", "toolbox_lh"), self.rows(found))
        error = next(f for f in found if f.severity == "error")
        self.assertIn("data.Get('Toolboxes')", error.message)
        self.assertEqual(error.member, TRUCK)

    def test_v35b_dropping_the_constraint_desc_only_warns(self) -> None:
        old = ute(controllable=("toolbox_lh", "toolbox_rh"))
        new = ute(descs=DESCS[:2], sequential={"Toolboxes": [("Stage1", ["toolbox_lh", "toolbox_rh"])]})
        self.assertEqual(self.rows(self.run_pair(old, new)),
                         [("RC077", "warning", "TruckConstraintsSavablePropDesc")])

    def test_baseline_without_the_desc_restores_nothing(self) -> None:
        old = ute(descs=DESCS[:2], controllable=("a",))
        new = ute(sequential={"Chain": [("S1", ["a"])]})
        self.assertEqual(self.rows(self.run_pair(old, new)),
                         [("RC077", "info", "TruckConstraintsSavablePropDesc")])

    def test_stage_count_and_stage_members(self) -> None:
        old = ute(sequential={"Arm": [("S1", ["boom"]), ("S2", ["stick"])]})
        more = ute(sequential={"Arm": [("S1", ["boom"]), ("S2", ["stick"]), ("S3", ["bucket"])]})
        self.assertEqual(self.rows(self.run_pair(old, more)), [("RC077", "error", "links")])
        gained = ute(sequential={"Arm": [("S1", ["boom", ("bucket_addon", "pin")]), ("S2", [])]})
        self.assertEqual(self.rows(self.run_pair(old, gained)),
                         [("RC077", "error", "pin"), ("RC077", "warning", "stick")])
        renamed_stage = ute(sequential={"Arm": [("Raise", ["boom"]), ("Curl", ["stick"])]})
        self.assertEqual(self.run_pair(old, renamed_stage), [])          # stages are matched by index
        removed = ute(sequential={})
        self.assertEqual(self.rows(self.run_pair(old, removed)), [("RC077", "warning", "Arm")])


class ConstraintTests(SaveCompatBase):
    def test_powered_by_index(self) -> None:
        old = ute(powered=("legs", "arm"))
        self.assertEqual(self.rows(self.run_pair(old, ute(powered=("legs",)))),
                         [("RC077", "error", "powerConstraints")])
        self.assertEqual(self.rows(self.run_pair(old, ute(powered=("legs", "arm", "tilt")))),
                         [("RC077", "error", "powerConstraints")])
        self.assertEqual(self.rows(self.run_pair(old, ute(powered=("arm", "legs")))),
                         [("RC077", "warning", "powerConstraints[0]"), ("RC077", "warning", "powerConstraints[1]")])

    def test_controllable_added_removed_and_used_by_a_chain(self) -> None:
        old = ute(controllable=("boom",))
        plain = ute(controllable=("boom", "swing"))
        self.assertEqual(self.rows(self.run_pair(old, plain)), [("RC077", "warning", "swing")])
        chained = ute(controllable=("boom", "swing"),
                      chains='fold = { links = [ { constraint = "swing" power = 1 } ] }')
        self.assertEqual(self.rows(self.run_pair(old, chained)), [("RC077", "error", "swing")])
        self.assertEqual(self.rows(self.run_pair(old, ute(controllable=("boom_v2",)))),
                         [("RC077", "warning", "boom"), ("RC077", "warning", "boom_v2")])

    def test_unchanged_truck_is_clean_and_tuning_is_free(self) -> None:
        old = ute(powered=("legs",), controllable=("boom",), sequential={"Arm": [("S1", ["boom"])]})
        self.assertEqual(self.run_pair(old, old), [])
        tuned = old.replace("angularSpeed = 45", "angularSpeed = 90")
        self.assertEqual(self.run_pair(old, tuned), [])


class IdentityAndCargoTests(SaveCompatBase):
    def test_truck_identity_is_the_truck_info_name(self) -> None:
        cls = ute(sequential={"Arm": [("S1", ["boom"])]})
        base = self.pak({TRUCK: cls, "ssl/auto_ute_truck_info_ute.sso.resource": "x"}, "installed.pak")
        same = self.pak({"ssl/auto_ute_v2.cls": cls, "ssl/auto_ute_truck_info_v2.sso.resource": "x"}, "same.pak")
        self.assertEqual(validate.validate(same, rules=["save-compat"], game_root=NO_GAME, baseline=base), [])
        other = self.pak({"ssl/auto_ute2_ute.cls": cls, "ssl/auto_ute2_truck_info_ute.sso.resource": "x"},
                         "other.pak")
        found = validate.validate(other, rules=["save-compat"], game_root=NO_GAME, baseline=base)
        self.assertEqual(self.rows(found), [("RC077", "warning", "ute")])
        self.assertIn("truck_manager_rb_ute", found[0].message)
        self.assertEqual(validate.truck_identities(validate.open_target(base)),
                         {"ute": "ssl/auto_ute_truck_info_ute.sso.resource"})

    def test_removed_cargo_slot(self) -> None:
        descs = DESCS + ("TruckStorageSavablePropDesc",)
        old = ute(descs=descs, cargo=("firstCargoSlot", "secondCargoSlot"))
        new = ute(descs=descs, cargo=("firstCargoSlot",))
        self.assertEqual(self.rows(self.run_pair(old, new)), [("RC077", "error", "secondCargoSlot")])


class CliTests(SaveCompatBase):
    def cli(self, argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = validate.main(argv)
        return code, out.getvalue()

    def test_runs_only_with_a_baseline_and_fails_on_new_errors(self) -> None:
        old = self.pak({TRUCK: ute(controllable=("a",))}, "installed.pak")
        new = self.pak({TRUCK: ute(sequential={"Chain": [("S1", ["a"])]})}, "candidate.pak")
        code, out = self.cli([str(new), "--json", "--game-root", NO_GAME, "--rules", "save-compat"])
        self.assertEqual((code, json.loads(out)["findings"]), (0, []))
        code, out = self.cli([str(new), "--baseline", str(old), "--json", "--game-root", NO_GAME,
                              "--rules", "save-compat"])
        report = json.loads(out)
        self.assertEqual(code, 1)
        self.assertEqual(report["baseline"]["newBySeverity"]["error"], 1)
        self.assertEqual({f["code"] for f in report["findings"]}, {"RC077"})


if __name__ == "__main__":
    unittest.main()
