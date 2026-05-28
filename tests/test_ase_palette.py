from __future__ import annotations

import unittest

from psd_decomposer.aseprite_codec import decode_aseprite_bytes
from psd_decomposer.aseprite_codec.constants import CHUNK_PALETTE

from .ase_fixtures import make_aseprite_bytes, make_frame, make_header, make_palette_chunk


class AsePaletteChunkTests(unittest.TestCase):
    def test_palette_chunk_collects_entries_and_optional_color_names(self) -> None:
        frame = make_frame(
            chunks=[
                make_palette_chunk(
                    [
                        {"r": 255, "g": 0, "b": 0, "a": 255, "name": "red"},
                        {"r": 0, "g": 0, "b": 255, "a": 128},
                    ],
                    palette_size=2,
                    first_index=4,
                )
            ]
        )
        data = make_aseprite_bytes(
            header=make_header(file_size=128 + len(frame), color_depth=8),
            frames=[frame],
        )

        ase_file = decode_aseprite_bytes(data)
        palette = ase_file.palettes[0]

        self.assertEqual(ase_file.chunk_types_by_frame, [[CHUNK_PALETTE]])
        self.assertEqual(palette.palette_size, 2)
        self.assertEqual((palette.first_index, palette.last_index), (4, 5))
        self.assertEqual([(entry.index, entry.r, entry.g, entry.b, entry.a) for entry in palette.entries], [(4, 255, 0, 0, 255), (5, 0, 0, 255, 128)])
        self.assertEqual(palette.entries[0].name, "red")
        self.assertIsNone(palette.entries[1].name)


if __name__ == "__main__":
    unittest.main()
