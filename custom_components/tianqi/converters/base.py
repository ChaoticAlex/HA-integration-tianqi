"""上游字段 -> HA 标准实体/属性的转换器。"""

from dataclasses import dataclass
from typing import Any, Optional, TYPE_CHECKING
import re

from .const import as_float, wind_bearing_to_degrees, wind_force_to_kmh

if TYPE_CHECKING:
    from .. import TianqiClient as Client


@dataclass
class Converter:
    attr: str  # hass attribute
    domain: Optional[str] = None  # hass domain

    prop: Optional[str] = None
    parent: Optional[str] = None

    enabled: Optional[bool] = True  # support: True, False, None (lazy setup)
    poll: bool = False  # hass should_poll
    ignore_prop: bool = False

    # don't init with dataclass because no type:
    childs = None  # set or dict? of children attributes
    option = None

    # to hass
    def decode(self, client: "Client", payload: dict, value: Any):
        payload[self.attr] = value

    # from hass
    def encode(self, client: "Client", payload: dict, value: Any):
        payload[self.prop or self.attr] = value

    def with_option(self, option: dict):
        self.option = option
        return self


@dataclass
class SensorConv(Converter):
    domain: Optional[str] = 'sensor'


@dataclass
class NumberSensorConv(SensorConv):
    unit: Optional[str] = ' '
    precision: Optional[int] = 1

    def decode(self, client: "Client", payload: dict, value: Any):
        val = as_float(value)
        payload[self.attr] = round(val, self.precision) if val is not None else None


@dataclass
class WindSpeedSensorConv(NumberSensorConv):
    """风速传感器，HA 标准 wind_speed + km/h。"""

    attr: str = 'wind_speed'
    prop: Optional[str] = 'wse'
    unit: Optional[str] = 'km/h'
    option = {
        'device_class': 'wind_speed',
        'state_class': 'measurement',
        'unit_of_measurement': 'km/h',
    }


@dataclass
class WindBearingSensorConv(Converter):
    """风向传感器，HA 标准 wind_direction + 度（0=北，顺时针），文本进属性。"""

    attr: str = 'wind_bearing'
    prop: Optional[str] = 'WD'
    domain: Optional[str] = 'sensor'
    option = {
        'device_class': 'wind_direction',
        'state_class': 'measurement_angle',
        'unit_of_measurement': '°',
        'icon': 'mdi:compass-outline',
    }

    def decode(self, client: "Client", payload: dict, value: Any):
        dataSK = client.data.get('dataSK') or {}
        text = value or dataSK.get('wde')
        payload[self.attr] = wind_bearing_to_degrees(text)
        payload['wind_bearing_text'] = dataSK.get('WD') or dataSK.get('wde')


@dataclass
class WindForceSensorConv(Converter):
    """蒲福风级（上游 "2级"），无标准 device_class，默认不启用。"""

    attr: str = 'wind_force'
    prop: Optional[str] = 'WS'
    domain: Optional[str] = 'sensor'
    enabled: Optional[bool] = False
    option = {
        'state_class': 'measurement',
        'unit_of_measurement': '级',
        'icon': 'mdi:weather-windy',
    }

    def decode(self, client: "Client", payload: dict, value: Any):
        text = f'{value or ""}'
        match = re.search(r'\d+(?:\.\d+)?', text)
        payload[self.attr] = float(match.group(0)) if match else None


@dataclass
class ForecastMinutelySensorConv(SensorConv):
    attr: str = 'forecast_minutely'
    prop: Optional[str] = 'msg'
    option = {
        'icon': 'mdi:tooltip',
        'payload_attrs': True,
    }

    def decode(self, client: "Client", payload: dict, value: Any):
        minutely = client.data.get('minutely') or {}
        times = minutely.get('times', [])
        values = minutely.get('values', [])
        minutes = dict(zip(times, values)) if len(times) == len(values) else {}
        payload.update({
            'forecast_minutely': minutely.get('msg'),
            **minutes,
        })


@dataclass
class AlarmsBinarySensorConv(Converter):
    attr: str = 'warning'
    prop: Optional[str] = 'alarms'
    domain: Optional[str] = 'binary_sensor'
    option = {
        'device_class': 'problem',
    }
    childs = {
        'title',
        'alarms',
    }

    def decode(self, client: "Client", payload: dict, value: Any):
        super().decode(client, payload, value)
        code = None
        titles = []
        alarms = []
        raw_alarms = sorted(
            client.data.get(self.prop) or [],
            key=lambda v: v.get('w6', ''),
            reverse=True,
        )
        for v in raw_alarms:
            alarm_code = f'{v.get("w4")}{v.get("w6")}'
            if code is None:
                code = alarm_code
            title = v.get('w13', '')
            titles.append(re.sub(r'.+发布的?(.+预警)', r'\1', title))
            alarms.append({
                'title': title,
                'description': v.get('w9', ''),
                'province': v.get('w1'),
                'city': v.get('w2'),
                'code': alarm_code,
                'alert_id': v.get('w16'),
                'link': client.web_url('warning/publish_area.shtml?code=%s' % client.area_id),
            })
        payload['warning'] = len(alarms) > 0
        payload['title'] = ', '.join(dict.fromkeys(titles))
        payload['alarms'] = alarms
