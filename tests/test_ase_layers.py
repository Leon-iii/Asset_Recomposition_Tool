from __future__ import annotations

import unittest

from psd_decomposer.aseprite_codec import decode_aseprite_bytes
from psd_decomposer.aseprite_codec.constants import CHUNK_LAYER

from .ase_fixtures import make_aseprite_bytes, make_frame, make_layer_chunk


class AseLayerChunkTests(unittest.TestCase):
    def test_layer_index_is_layer_chunk_order(self) -> None:
        data = make_aseprite_bytes(
            frames=[
                make_frame(
                    chunks=[
                        make_layer_chunk(name="Background", flags=1),
                        make_layer_chunk(name="Hidden", flags=0, child_level=1, opacity=128),
                    ]
                )
            ]
        )

        ase_file = decode_aseprite_bytes(data)

        self.assertEqual([layer.index for layer in ase_file.layers], [0, 1])
        self.assertEqual([layer.name for layer in ase_file.layers], ["Background", "Hidden"])
        self.assertEqual([layer.visible for layer in ase_file.layers], [True, False])
        self.assertEqual(ase_file.layers[1].child_level, 1)
        self.assertEqual(ase_file.layers[1].opacity, 128)
        self.assertEqual(ase_file.chunk_types_by_frame, [[CHUNK_LAYER, CHUNK_LAYER]])


if __name__ == "__main__":
    unittest.main()
