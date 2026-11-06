"""上游字段 -> HA 标准实体/属性的转换器。"""

from dataclasses import dataclass
from typing import Any, Optional, TYPE_CHECKING
import re


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
