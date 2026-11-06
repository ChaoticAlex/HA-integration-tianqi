"""预报行构造的回归测试：只允许 HA 标准键，数值来自真实上游 payload。

payload 均为 2026-11-06 实测抓取。
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'custom_components' / 'tianqi'))

from const import (  # noqa: E402
    build_daily_row,
    build_hourly_row,
    build_twice_daily_rows,
)

# HA Forecast TypedDict 允许的键（datetime 由实体层补）
DAILY_KEYS = {
    'datetime', 'condition', 'native_temperature', 'native_templow',
    'native_apparent_temperature', 'humidity', 'precipitation_probability',
    'cloud_coverage', 'native_precipitation', 'native_pressure',
    'wind_bearing', 'native_wind_gust_speed', 'native_wind_speed',
    'native_dew_point', 'uv_index', 'is_daytime',
}
HOURLY_KEYS = DAILY_KEYS

# 广州 101280101 weixinfc.f[今天]
DAILY_GZ_TODAY = {
    'fa': '07', 'fb': '01', 'fc': '31', 'fd': '21', 'fe': '无持续风向',
    'ff': '无持续风向', 'fg': '<3级', 'fh': '<3级', 'fk': '0', 'fl': '0',
    'fm': '97.1', 'fn': '61.7', 'fi': '11/6', 'fj': '今天',
}

# 广州 昨天（应被实体层过滤，但构造本身要能处理）
DAILY_GZ_YESTERDAY = {**DAILY_GZ_TODAY, 'fi': '11/5', 'fj': '昨天'}

# 大连 101070201 wap_180h.jh[08:00] 晴
HOURLY_DL_CLEAR = {
    'ja': '00', 'jb': '4', 'jc': '0', 'jd': '8', 'je': '51',
    'jf': '202611060800', 'jg': '0', 'jh': '3', 'ji': '0',
    'jj': '1015', 'jk': '4',
}

# 湛江 101281001 wap_180h.jh[09:00] 小雨
HOURLY_ZJ_RAIN = {
    'ja': '07', 'jb': '27', 'jc': '1', 'jd': '2', 'je': '82',
    'jf': '202611060900', 'jg': '1.6', 'jh': '35', 'ji': '97',
    'jj': '1016', 'jk': '14',
}


class TestDailyRow(unittest.TestCase):
    def test_standard_keys_only(self):
        row = build_daily_row(DAILY_GZ_TODAY)
        self.assertLessEqual(set(row), DAILY_KEYS)
        for banned in ('skycon', 'native_precipitation', 'cloud_coverage'):
            self.assertNotIn(banned, row)

    def test_values(self):
        row = build_daily_row(DAILY_GZ_TODAY)
        self.assertEqual(row['condition'], 'rainy')  # fa=07 小雨
        self.assertEqual(row['native_temperature'], 31.0)
        self.assertEqual(row['native_templow'], 21.0)
        # "无持续风向" -> None -> 不写 wind_bearing
        self.assertNotIn('wind_bearing', row)
        # "<3级" -> 蒲福 3 级中值 15.5 km/h
        self.assertEqual(row['native_wind_speed'], 15.5)

    def test_unknown_code_returns_none(self):
        self.assertIsNone(build_daily_row({**DAILY_GZ_TODAY, 'fa': '99'}))


class TestHourlyRow(unittest.TestCase):
    def test_clear_day(self):
        row = build_hourly_row(HOURLY_DL_CLEAR)
        self.assertLessEqual(set(row), HOURLY_KEYS)
        self.assertEqual(row['condition'], 'sunny')
        self.assertEqual(row['native_temperature'], 4.0)
        self.assertEqual(row['humidity'], 51.0)
        self.assertEqual(row['native_pressure'], 1015.0)
        self.assertEqual(row['native_precipitation'], 0.0)
        self.assertEqual(row['cloud_coverage'], 3)
        self.assertEqual(row['wind_bearing'], 0.0)  # 北风

    def test_rainy(self):
        row = build_hourly_row(HOURLY_ZJ_RAIN)
        self.assertEqual(row['condition'], 'rainy')
        self.assertEqual(row['native_precipitation'], 1.6)  # jg 是降水，不是风速
        self.assertEqual(row['cloud_coverage'], 35)
        self.assertEqual(row['wind_bearing'], 97.0)
        self.assertNotIn('native_wind_speed', row)  # 上游无逐时风速，不编

    def test_no_fake_cloud(self):
        row = build_hourly_row({**HOURLY_DL_CLEAR, 'jh': '180'})
        self.assertNotIn('cloud_coverage', row)


class TestTwiceDailyRows(unittest.TestCase):
    def test_two_rows_with_is_daytime(self):
        rows = build_twice_daily_rows(DAILY_GZ_TODAY)
        self.assertEqual(len(rows), 2)
        self.assertEqual([r['is_daytime'] for r in rows], [True, False])

    def test_day_and_night_values(self):
        rows = build_twice_daily_rows(DAILY_GZ_TODAY)
        day, night = rows
        self.assertEqual(day['condition'], 'rainy')      # fa=07 小雨
        self.assertEqual(day['native_temperature'], 31.0)  # fc 最高
        self.assertEqual(night['condition'], 'partlycloudy')  # fb=01 多云
        self.assertEqual(night['native_temperature'], 21.0)  # fd 最低

    def test_is_daytime_always_present(self):
        """HA 对 twice_daily 强校验 is_daytime，缺了会 ValueError。"""
        for rows in (build_twice_daily_rows(DAILY_GZ_TODAY),
                     build_twice_daily_rows(DAILY_GZ_YESTERDAY)):
            for row in rows:
                self.assertIn('is_daytime', row)

    def test_unknown_codes(self):
        rows = build_twice_daily_rows({**DAILY_GZ_TODAY, 'fa': '99', 'fb': '99'})
        self.assertEqual(rows, [])


class TestConditionTable(unittest.TestCase):
    def test_no_duplicate_or_missing(self):
        from const import CONDITION_CODES, CONDITION_VALUES

        for code, spec in CONDITION_CODES.items():
            self.assertIn(spec.condition, CONDITION_VALUES, code)

    def test_haze_rows_have_no_precipitation_hint(self):
        # 回归：d54 曾是 [fog, 'MODERATE_HAZE', 90, 0]，把 90 当降水
        from const import CONDITION_CODES

        self.assertEqual(CONDITION_CODES['d54'].condition, 'fog')
        self.assertFalse(hasattr(CONDITION_CODES['d54'], 'precipitation'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
