from unittest import TestCase, mock
from roadcraft import cli, core, transaction


class TransactionProcessScopeTests(TestCase):
    def checker(self, rows):
        def inspect(*, tokens=None):
            values = tokens or ("roadcraft", "modeditor", "integrationstudio", "blender", "painter", "furnace", "mod_pak_builder")
            return [r for r in rows if any(t in r["name"].lower() for t in values)], None
        return mock.patch.object(core, "_editor_processes", side_effect=inspect)

    def test_dcc_and_connector_processes_do_not_block_pinned_package_transactions(self):
        rows = [{"pid": i, "name": name} for i, name in enumerate(
            ("blender.exe", "blender-mcp.exe", "mcp-for-blender.exe", "Substance Painter.exe"))]
        with self.checker(rows):
            transaction._processes_clear(cli._transaction_process_check)

    def test_native_readers_and_builders_still_block_mutation(self):
        for name in ("Roadcraft - Retail.exe", "Roadcraft - Editor.exe", "IntegrationStudio.exe",
                     "ModEditor.exe", "furnace.exe", "mod_pak_builder.exe"):
            with self.subTest(name=name), self.checker([{"pid": 101, "name": name}]):
                with self.assertRaises(transaction.TransactionBusyError):
                    transaction._processes_clear(cli._transaction_process_check)

    def test_inspection_failure_still_fails_closed(self):
        with mock.patch.object(core, "_editor_processes", return_value=([], "snapshot failed")):
            with self.assertRaises(transaction.TransactionBusyError):
                transaction._processes_clear(cli._transaction_process_check)
