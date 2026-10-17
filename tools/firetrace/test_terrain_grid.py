import unittest
from PIL import Image

from terrain_grid import terrain_grid, validate_origin, tile_pixel


class TerrainGridTests(unittest.TestCase):
    def test_decodes_terrarium_elevation_without_a_flat_fallback(self):
        def loader(key):
            return Image.new('RGB', (256, 256), (132, 210, 128)), {'url': 'test-fixture', 'sha256': 'fixture'}
        result = terrain_grid([-119.027914, 36.86508], tile_loader=loader)
        self.assertEqual(result['elevations'][20][20], 1234.5)
        self.assertEqual(len(result['elevations']), 41)
        self.assertTrue(all(len(row) == 41 for row in result['elevations']))
        self.assertEqual(result['origin'], [-119.027914, 36.86508])

    def test_rejects_remote_failure_and_impossible_elevation(self):
        def failed(key):
            raise OSError('No tile')
        with self.assertRaises(OSError): terrain_grid([-119, 37], tile_loader=failed)
        def invalid(key):
            return Image.new('RGB', (256, 256), (0, 0, 0)), {}
        with self.assertRaises(ValueError): terrain_grid([-119, 37], tile_loader=invalid)

    def test_coordinates_and_tile_axes_are_validated(self):
        for origin in [[float('nan'), 37], [0, 0], [True, 37], [-119], 'camera']:
            with self.assertRaises(ValueError): validate_origin(origin)
        key, pixel = tile_pixel(-119, 37)
        north_key, north_pixel = tile_pixel(-119, 37.01)
        self.assertLess(north_key[1] * 256 + north_pixel[1], key[1] * 256 + pixel[1])


if __name__ == '__main__':
    unittest.main()
