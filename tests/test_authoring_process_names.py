import unittest
from roadcraft.core import _is_authoring_process

class AuthoringProcessNames(unittest.TestCase):
    TOKENS = ("roadcraft", "modeditor", "integrationstudio", "blender", "painter", "furnace", "mod_pak_builder")
    def test_connector_servers_do_not_own_documents(self):
        for name in ("blender-mcp.exe", "mcp-for-blender.exe", "Blender-MCP.EXE"):
            self.assertFalse(_is_authoring_process(name, self.TOKENS), name)
    def test_real_authoring_and_native_processes_still_block(self):
        for name in ("blender.exe", "painter.exe", "RoadCraft.exe", "RoadCraftRetail.exe", "IntegrationStudio.exe", "Furnace.exe", "mod_pak_builder.exe", "custom-blender-worker.exe"):
            self.assertTrue(_is_authoring_process(name, self.TOKENS), name)
    def test_unrelated_process_and_selected_tokens(self):
        self.assertFalse(_is_authoring_process("python.exe", self.TOKENS))
        self.assertFalse(_is_authoring_process("blender.exe", ("roadcraft",)))
if __name__ == "__main__":
    unittest.main()
