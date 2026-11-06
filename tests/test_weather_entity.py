"""weather 实体端到端测试：喂真实结构的 payload，跑一遍 update_from_client。

覆盖 1.0.3 方案 B：实体只输出标准字段，雨量/AQI/分钟级/生活指数走状态属性，
并校验 twice_daily（is_daytime 必填）。
"""

import asyncio
import sys
import types
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_import import install_stubs  # noqa: E402

TZ = ZoneInfo('Asia/Shanghai')
NOW = datetime.now(TZ)


def _patch_dt_util():
    """把桩里的 dt 工具换成真实实现（实体层要用 now/start_of_local_day）。"""
    mod = sys.modules['homeassistant.util.dt']
    mod.now = lambda: datetime.now(TZ)
    mod.start_of_local_day = lambda value=None: (
        (value or datetime.now(TZ)).replace(hour=0, minute=0, second=0, microsecond=0)
    )


def _fi(offset_days: int) -> str:
    day = (NOW + timedelta(days=offset_days)).date()
    return f'{day.month}/{day.day}'


def _hour(offset_hours: int) -> str:
    return (NOW + timedelta(hours=offset_hours)).strftime('%Y%m%d%H00')


DATA = {
    'dataSK': {
        'cityname': '江南', 'city': '101300111',
        'temp': '24.1', 'sd': '81%', 'qy': '1006', 'njd': '22km',
        'WD': '东风', 'wde': 'E', 'WS': '2级', 'wse': '6km/h',
        'rain': '0', 'rain24h': '3.2', 'aqi': '19', 'aqi_pm25': '19',
        'weather': '阴', 'weathercode': 'd02', 'time': '11:10',
    },
    'dataZS': {
        'ct_name': '穿衣指数', 'ct_des_s': '建议穿长袖衬衫单裤等服装。',
        'ct_hint': '舒适',
        'yd_name': '运动指数', 'yd_des_s': '天气较好，尽情感受运动的快乐吧。',
    },
    'dailies': [
        {'fa': '07', 'fb': '01', 'fc': '30', 'fd': '22',
         'fe': '北风', 'ff': '无持续风向', 'fg': '3-4级', 'fh': '<3级',
         'fi': _fi(-1)},
        {'fa': '07', 'fb': '01', 'fc': '31', 'fd': '21',
         'fe': '无持续风向', 'ff': '无持续风向', 'fg': '<3级', 'fh': '<3级',
         'fi': _fi(0)},
        {'fa': '01', 'fb': '00', 'fc': '30', 'fd': '22',
         'fe': '东风', 'ff': '东北风', 'fg': '3-4级', 'fh': '<3级',
         'fi': _fi(1)},
    ],
    'hourlies': [
        {'ja': '00', 'jb': '22', 'je': '82', 'jf': _hour(-1),
         'jg': '0', 'jh': '10', 'ji': '0', 'jj': '1015'},
        {'ja': '02', 'jb': '24', 'je': '81', 'jf': _hour(0),
         'jg': '0.3', 'jh': '90', 'ji': '90', 'jj': '1014'},
        {'ja': '07', 'jb': '25', 'je': '80', 'jf': _hour(1),
         'jg': '1.6', 'jh': '95', 'ji': '135', 'jj': '1013'},
    ],
    'minutely': {
        'msg': '未来2小时不会下雨',
        'times': ['2026-11-06 11:36:00', '2026-11-06 11:42:00'],
        'values': [0.0, 0.3],
    },
    'alarms': [],
}


class _Station:
    area_id = '101300111'
    area_code = 'jiangnan'
    area_name = '江南'


class _Client:
    def __init__(self, data):
        self.hass = types.SimpleNamespace(data={}, config=types.SimpleNamespace(location_name='江南'))
        self.data = data
        self.entry_id = 'test-entry'
        self.config = {}
        self.entities = {}
        self.station = _Station()
        self.daily_calls = 0

    area_id = property(lambda self: self.station.area_id)
    station_code = property(lambda self: self.station.area_code)
    station_name = property(lambda self: self.station.area_name)
    device_info = property(lambda self: {'identifiers': {('tianqi', '101300111')}})

    async def update_dailies(self):
        self.daily_calls += 1

    async def update_hourlies(self):
        pass


class TestWeatherEntity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        install_stubs()
        _patch_dt_util()
        from custom_components.tianqi.weather import WeatherEntity

        cls.WeatherEntity = WeatherEntity

    def _entity(self, data=None):
        entity = self.WeatherEntity(_Client(data or DATA))
        asyncio.run(entity.update_from_client())
        return entity

    def test_standard_state(self):
        entity = self._entity()
        self.assertEqual(entity._attr_condition, 'cloudy')
        self.assertEqual(entity._attr_native_temperature, 24.1)
        self.assertEqual(entity._attr_humidity, 81.0)
        self.assertEqual(entity._attr_native_pressure, 1006.0)
        self.assertEqual(entity._attr_native_wind_speed, 6.0)
        self.assertEqual(entity._attr_wind_bearing, 90.0)  # 东风 -> 度
        self.assertEqual(entity._attr_native_visibility, 22.0)

    def test_entity_name_uses_device(self):
        entity = self._entity()
        self.assertIsNone(entity._attr_name)

    def test_extra_attributes_carry_non_weather_data(self):
        attrs = self._entity()._attr_extra_state_attributes
        self.assertEqual(attrs['precipitation_1h'], 0.0)
        self.assertEqual(attrs['precipitation_24h'], 3.2)
        self.assertEqual(attrs['aqi'], 19)
        self.assertEqual(attrs['wind_bearing_text'], '东风')
        self.assertEqual(attrs['forecast_minutely'], '未来2小时不会下雨')
        self.assertEqual(attrs['forecast_minutely_values'], [0.0, 0.3])
        self.assertEqual(attrs['forecast_minutely_start'], '2026-11-06 11:36:00')
        self.assertIn('穿衣指数', attrs['indexes'])

    def test_daily_filters_past(self):
        rows = asyncio.run(self._entity().async_forecast_daily())
        self.assertEqual(len(rows), 2)  # 昨天被过滤
        self.assertEqual(rows[0]['datetime'].date(), NOW.date())
        self.assertEqual(rows[0]['condition'], 'rainy')

    def test_hourly_uses_ji_and_jg(self):
        rows = asyncio.run(self._entity().async_forecast_hourly())
        self.assertEqual(len(rows), 2)  # 过去的那小时被过滤
        self.assertTrue(all('native_wind_speed' not in r for r in rows))
        self.assertEqual(rows[0]['wind_bearing'], 90.0)   # ji=90 东风
        self.assertEqual(rows[-1]['wind_bearing'], 135.0)  # ji=135 东南风
        self.assertEqual(rows[-1]['native_precipitation'], 1.6)  # jg 是降水
        self.assertEqual(rows[-1]['cloud_coverage'], 95)

    def test_twice_daily_has_is_daytime(self):
        rows = asyncio.run(self._entity().async_forecast_twice_daily())
        self.assertEqual([r['is_daytime'] for r in rows], [True, False, True, False])
        self.assertEqual([r['datetime'].hour for r in rows], [8, 20, 8, 20])
        stamps = [r['datetime'] for r in rows]
        self.assertEqual(stamps, sorted(stamps))
        # 白天用 fc/fe，夜间用 fd/ff
        self.assertEqual(rows[0]['native_temperature'], 31.0)
        self.assertEqual(rows[1]['native_temperature'], 21.0)
        self.assertEqual(rows[2]['wind_bearing'], 90.0)   # 白天东风
        self.assertEqual(rows[3]['wind_bearing'], 45.0)   # 夜间东北风

    def test_supported_features_include_twice_daily(self):
        entity = self._entity()
        self.assertTrue(entity._attr_supported_features & 4)  # FORECAST_TWICE_DAILY

    def test_unknown_condition_does_not_crash(self):
        entity = self._entity({**DATA, 'dataSK': {**DATA['dataSK'], 'weathercode': 'd99'}})
        self.assertIsNone(entity._attr_condition)
        self.assertEqual(entity._attr_native_temperature, 24.1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
