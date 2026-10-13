import struct
import unittest

from roadcraft import tpl_reader


def _table(count: int) -> bytes:
    """Name list, node indices and identity world matrices in the compiled .tpl layout."""
    names = [f"node_{i:04d}".encode() for i in range(count)]
    data = b"\x00" * 16 + struct.pack("<I", count) + b"\x00"
    for n in names:
        data += struct.pack("<I", len(n)) + n
    data += struct.pack("<I", count) + struct.pack(f"<{count}H", *range(count))
    data += struct.pack("<I", count)
    identity = (1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1)
    data += struct.pack(f"<{16 * count}f", *(identity * count))
    return data


class NodeTableCountTests(unittest.TestCase):
    def test_counts_whose_low_byte_is_zero_or_one(self):
        # 512 and 513 nodes start the count with 00 / 01; the CAT 793D RC44 model has 513
        for count in (2, 255, 256, 257, 512, 513, 770):
            nodes = tpl_reader.read_nodes(_table(count))
            self.assertEqual(len(nodes.names), count)
            self.assertEqual(nodes.index["node_0000"], 0)


if __name__ == "__main__":
    unittest.main()
