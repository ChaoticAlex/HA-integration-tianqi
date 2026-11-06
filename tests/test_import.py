"""导入冒烟测试：用最小 homeassistant 桩模块把整个集成 import 一遍。

目的：捕获 "自定义集成导入失败 -> Invalid handler specified" 这类错误
（相对导入层级写错、常量名写错、模块级异常等），无需真实 HA 环境。

不校验 HA 运行时行为，只保证 import 链路通。
"""

import sys
import types
import unittest
from pathlib import Path

INTEGRATION_ROOT = Path(__file__).resolve().parents[1]


def _mod(name, **attrs):
    mod = types.ModuleType(name)
    mod.__path__ = []  # 当作 package，允许子模块
    for key, value in attrs.items():
        setattr(mod, key, value)
    sys.modules[name] = mod
    return mod


class _Unit:
    def __init__(self, value):
        self.value = value


class _Platform:
    WEATHER = 'weather'
    SENSOR = 'sensor'
    BINARY_SENSOR = 'binary_sensor'


class _ConfigFlow:
    """支持 class X(ConfigFlow, domain=...)。"""

    def __init_subclass__(cls, domain=None, **kwargs):
        super().__init_subclass__(**kwargs)
        if domain is not None:
            cls.domain = domain


class _WeatherEntityFeature:
    FORECAST_DAILY = 1
    FORECAST_HOURLY = 2
    FORECAST_TWICE_DAILY = 4


def install_stubs():
    """注册足够让集成 import 通过的 homeassistant 桩。"""
    if 'voluptuous' not in sys.modules:
        _mod('voluptuous',
             Schema=lambda *a, **k: (a, k),
             Optional=lambda key, **k: key,
             Required=lambda key, **k: key,
             In=lambda *a, **k: a,
             ALLOW_EXTRA='extra')
    _mod('homeassistant')
    _mod('homeassistant.const',
         Platform=_Platform,
         CONF_DOMAIN='domain',
         EVENT_HOMEASSISTANT_STOP='homeassistant_stop',
         PERCENTAGE='%',
         STATE_ON='on',
         UnitOfLength=_Unit(''),
         UnitOfPressure=_Unit(''),
         UnitOfSpeed=_Unit(''),
         UnitOfTemperature=_Unit(''),
         CONCENTRATION_MICROGRAMS_PER_CUBIC_METER=_Unit(''),
         UnitOfAngle=_Unit('°'))
    _mod('homeassistant.util')
    _mod('homeassistant.util.dt',
         now=lambda: None,
         start_of_local_day=lambda *a: None)
    _mod('homeassistant.core',
         HomeAssistant=type('HomeAssistant', (), {}),
         State=type('State', (), {}),
         ServiceCall=type('ServiceCall', (), {}),
         SupportsResponse=type('SupportsResponse', (), {'OPTIONAL': 'optional'}),
         callback=lambda fn: fn)
    _mod('homeassistant.exceptions',
         IntegrationError=type('IntegrationError', (Exception,), {}))
    _mod('homeassistant.config_entries',
         ConfigEntry=type('ConfigEntry', (), {}),
         ConfigFlow=_ConfigFlow,
         OptionsFlow=type('OptionsFlow', (), {}),
         CONN_CLASS_CLOUD_POLL='cloud_poll')
    _mod('homeassistant.helpers')
    _mod('homeassistant.helpers.entity',
         Entity=type('Entity', (), {'async_write_ha_state': lambda self: None}),
         EntityCategory=type('EntityCategory', (), {'DIAGNOSTIC': 'diagnostic'}))
    _mod('homeassistant.helpers.aiohttp_client',
         async_create_clientsession=lambda *a, **k: None)
    _mod('homeassistant.helpers.device_registry',
         DeviceInfo=lambda **k: k,
         DeviceEntryType=type('DeviceEntryType', (), {'SERVICE': 'service'}))
    _mod('homeassistant.helpers.update_coordinator',
         DataUpdateCoordinator=type('DataUpdateCoordinator', (), {
             '__init__': lambda self, *a, **k: None,
         }))
    _mod('homeassistant.components')
    _mod('homeassistant.components.weather',
         DOMAIN='weather',
         WeatherEntity=type('WeatherEntity', (), {
             '_attr_should_poll': True,
             'async_write_ha_state': lambda self: None,
         }),
         Forecast=dict,
         WeatherEntityFeature=_WeatherEntityFeature,
         ATTR_CONDITION_SUNNY='sunny',
         ATTR_CONDITION_CLEAR_NIGHT='clear-night',
         ATTR_CONDITION_PARTLYCLOUDY='partlycloudy',
         ATTR_CONDITION_CLOUDY='cloudy',
         ATTR_CONDITION_RAINY='rainy',
         ATTR_CONDITION_POURING='pouring',
         ATTR_CONDITION_LIGHTNING='lightning',
         ATTR_CONDITION_LIGHTNING_RAINY='lightning-rainy',
         ATTR_CONDITION_HAIL='hail',
         ATTR_CONDITION_SNOWY='snowy',
         ATTR_CONDITION_SNOWY_RAINY='snowy-rainy',
         ATTR_CONDITION_FOG='fog',
         ATTR_CONDITION_WINDY='windy',
         ATTR_CONDITION_WINDY_VARIANT='windy-variant',
         ATTR_CONDITION_EXCEPTIONAL='exceptional')
    _mod('homeassistant.components.sensor',
         DOMAIN='sensor',
         SensorEntity=type('SensorEntity', (), {
             'async_write_ha_state': lambda self: None,
         }))
    _mod('homeassistant.components.binary_sensor',
         DOMAIN='binary_sensor',
         BinarySensorEntity=type('BinarySensorEntity', (), {
             'async_write_ha_state': lambda self: None,
         }))


class TestImport(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        install_stubs()
        sys.path.insert(0, str(INTEGRATION_ROOT))
        import custom_components  # noqa: F401
        import custom_components.tianqi  # noqa: F401

    def test_package_imports(self):
        import custom_components.tianqi as pkg

        self.assertEqual(pkg.DOMAIN, 'tianqi')

    def test_submodules_import(self):
        for name in (
            'custom_components.tianqi.weather',
            'custom_components.tianqi.sensor',
            'custom_components.tianqi.binary_sensor',
            'custom_components.tianqi.config_flow',
            'custom_components.tianqi.converters.base',
            'custom_components.tianqi.const',
        ):
            with self.subTest(name=name):
                __import__(name)

    def test_config_flow_handler(self):
        from custom_components.tianqi import DOMAIN
        from custom_components.tianqi.config_flow import TianqiConfigFlow

        self.assertEqual(TianqiConfigFlow.domain, DOMAIN)

    def test_converters_registered(self):
        from custom_components.tianqi import TianqiClient

        class _Hass:
            data = {}

        # 只验证转换器定义能构造出来（不触发网络）
        convs = [
            'WindSpeedSensorConv', 'WindBearingSensorConv',
            'WindForceSensorConv', 'AlarmsBinarySensorConv',
            'ForecastMinutelySensorConv',
        ]
        mod = __import__('custom_components.tianqi.converters.base', fromlist=convs)
        for name in convs:
            conv = getattr(mod, name)()
            self.assertTrue(conv.attr, name)
            self.assertIn(conv.domain, ('sensor', 'binary_sensor'), name)


if __name__ == '__main__':
    unittest.main(verbosity=2)
