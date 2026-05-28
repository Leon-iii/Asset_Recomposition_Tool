from __future__ import annotations

import unittest

from psd_decomposer.aseprite_codec import decode_aseprite_bytes
from psd_decomposer.aseprite_codec.constants import CHUNK_TAGS

from .ase_fixtures import make_aseprite_bytes, make_frame, make_tags_chunk


class AseTagsChunkTests(unittest.TestCase):
    def test_tags_chunk_collects_tag_names_and_frame_ranges(self) -> None:
        data = make_aseprite_bytes(
            frames=[
                make_frame(
                    chunks=[
                        make_tags_chunk(
                            [
                                {"name": "Idle", "from_frame": 0, "to_frame": 1, "loop_direction": 0, "repeat": 0},
                                {
                                    "name": "Walk",
                                    "from_frame": 2,
                                    "to_frame": 5,
                                    "loop_direction": 2,
                                    "repeat": 3,
                                    "color_rgb": (10, 20, 30),
                                },
                            ]
                        )
                    ]
                )
            ]
        )

        ase_file = decode_aseprite_bytes(data)

        self.assertEqual(ase_file.chunk_types_by_frame, [[CHUNK_TAGS]])
        self.assertEqual([tag.name for tag in ase_file.tags], ["Idle", "Walk"])
        self.assertEqual((ase_file.tags[1].from_frame, ase_file.tags[1].to_frame), (2, 5))
        self.assertEqual(ase_file.tags[1].loop_direction, 2)
        self.assertEqual(ase_file.tags[1].repeat, 3)
        self.assertEqual(ase_file.tags[1].color_rgb, (10, 20, 30))


if __name__ == "__main__":
    unittest.main()
