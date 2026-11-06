"""const.py 换算的单元测试（不依赖 Home Assistant，可直接 python3 -m unittest 跑）。

用例里的字符串全部取自上游真实返回（2026-11-06 实测）。
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'custom_components' / 'tianqi'))

from const import (  # noqa: E402
    as_float,
    wind_bearing_to_degrees,
    wind_force_to_kmh,
)


class TestAsFloat(unittest.TestCase):
    def test_upstream_units(self):
        self.assertEqual(as_float('73%'), 73.0)
        self.assertEqual(as_float('7km/h'), 7.0)
        self.assertEqual(as_float('30km'), 30.0)
        self.assertEqual(as_float('1011'), 1011.0)
        self.assertEqual(as_float('-3'), -3.0)
        self.assertEqual(as_float('28.7'), 28.7)

    def test_missing(self):
        for bad in (None, '', '--', '无'):
            self.assertIsNone(as_float(bad))
        self.assertIsNone(as_float(''), )

    def test_float_passthrough(self):
        self.assertEqual(as_float(12.5), 12.5)
        self.assertEqual(as_float(0), 0)


class TestWindBearing(unittest.TestCase):
    def test_chinese(self):
        cases = {
            '北风': 0.0,
            '东北风': 45.0,
            '东风': 90.0,
            '东南风': 135.0,
            '南风': 180.0,
            '西南风': 225.0,
            '西风': 270.0,
            '西北风': 315.0,
        }
        for text, deg in cases.items():
            self.assertEqual(wind_bearing_to_degrees(text), deg, text)

    def test_english_code(self):
        self.assertEqual(wind_bearing_to_degrees('NW'), 315.0)
        self.assertEqual(wind_bearing_to_degrees('E'), 90.0)

    def test_variable_wind_is_none(self):
        for text in ('无持续风向', '静风', '微风', '旋转风', '风向不定'):
            self.assertIsNone(wind_bearing_to_degrees(text), text)

    def test_numeric_string(self):
        self.assertEqual(wind_bearing_to_degrees('90'), 90.0)
        self.assertEqual(wind_bearing_to_degrees('265'), 265.0)
        self.assertEqual(wind_bearing_to_degrees(360), 0.0)

    def test_turn_phrase_takes_first(self):
        self.assertEqual(wind_bearing_to_degrees('西北风转东南风'), 315.0)

    def test_garbage(self):
        self.assertIsNone(wind_bearing_to_degrees(''))
        self.assertIsNone(wind_bearing_to_degrees(None))
        self.assertIsNone(wind_bearing_to_degrees('啥风'))


class TestWindForce(unittest.TestCase):
    def test_levels(self):
        self.assertEqual(wind_force_to_kmh('2级'), 8.5)
        self.assertEqual(wind_force_to_kmh('3-4级'), 19.8)  # (15.5+24)/2 = 19.75 -> 19.8
        self.assertEqual(wind_force_to_kmh('<3级'), 15.5)
        self.assertEqual(wind_force_to_kmh('12级'), 125.0)

    def test_range_clamp(self):
        self.assertEqual(wind_force_to_kmh('20级'), 125.0)
        self.assertEqual(wind_force_to_kmh('0级'), 0.5)

    def test_missing(self):
        self.assertIsNone(wind_force_to_kmh(None))
        self.assertIsNone(wind_force_to_kmh(''))
        self.assertIsNone(wind_force_to_kmh('不定'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
