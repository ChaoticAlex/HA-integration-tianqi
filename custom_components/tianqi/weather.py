"""天气实体：只输出 Home Assistant 标准字段。

严格约定：
- 状态属性仅有 condition / native_temperature / humidity / native_pressure /
  native_wind_speed / wind_bearing(度) / native_visibility，单位用 native_*_unit。
- 预报只含 HA Forecast TypedDict 定义的键；缺数据就不给（None/省略），不伪造。
- 非标准数据（生活指数、预警、分钟级降水）走各自的 sensor / binary_sensor。
"""

from __future__ import annotations

import logging
from datetime import datetime

from homeassistant.components.weather import (
    DOMAIN as ENTITY_DOMAIN,
    WeatherEntity as BaseEntity,
    Forecast,
)
from homeassistant.const import (
    UnitOfLength,
    UnitOfPressure,
    UnitOfSpeed,
    UnitOfTemperature,
)
from homeassistant.util import dt as dt_util

try:  # hass 2023.9+
    from homeassistant.components.weather import WeatherEntityFeature
except (ModuleNotFoundError, ImportError):  # pragma: no cover
    WeatherEntityFeature = None

from . import TianqiClient, async_add_setuper
from .const import (
    CONDITION_CODES,
    as_float,
    build_daily_row,
    build_hourly_row,
    build_twice_daily_rows,
    wind_bearing_to_degrees,
)

_LOGGER = logging.getLogger(__name__)

DAILY_FORECAST_LIMIT = 15
HOURLY_FORECAST_LIMIT = 48


def setuper(add_entities):
    def setup(client: TianqiClient):
        if not (entity := client.entities.get(ENTITY_DOMAIN)):
            entity = WeatherEntity(client)
        if not entity.added:
            add_entities([entity])
    return setup


async def async_setup_entry(hass, config_entry, async_add_entities):
    await async_add_setuper(hass, config_entry, ENTITY_DOMAIN, setuper(async_add_entities))


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    await async_add_setuper(hass, config or discovery_info, ENTITY_DOMAIN, setuper(async_add_entities))


class WeatherEntity(BaseEntity):
    added = False
    _attr_should_poll = False
    _attr_attribution = '中国天气网 (weather.com.cn)'

    def __init__(self, client: TianqiClient):
        self.client = client
        self.hass = client.hass

        self.entity_id = f'{ENTITY_DOMAIN}.{client.station_code}'
        # 设备名已是「<站>天气」，实体名留空由设备名派生，避免「江南天气 江南」
        self._attr_name = None
        self._attr_unique_id = f'{client.entry_id}-{ENTITY_DOMAIN}'
        self._attr_native_temperature_unit = UnitOfTemperature.CELSIUS
        self._attr_native_pressure_unit = UnitOfPressure.HPA
        self._attr_native_wind_speed_unit = UnitOfSpeed.KILOMETERS_PER_HOUR
        self._attr_native_visibility_unit = UnitOfLength.KILOMETERS
        self._attr_native_precipitation_unit = UnitOfLength.MILLIMETERS
        self._attr_extra_state_attributes = {}
        self._attr_device_info = client.device_info
        if WeatherEntityFeature:
            features = WeatherEntityFeature.FORECAST_DAILY | WeatherEntityFeature.FORECAST_HOURLY
            if hasattr(WeatherEntityFeature, 'FORECAST_TWICE_DAILY'):
                features |= WeatherEntityFeature.FORECAST_TWICE_DAILY
            self._attr_supported_features = features

    async def async_added_to_hass(self):
        self.added = True
        self.client.entities[ENTITY_DOMAIN] = self

        await super().async_added_to_hass()
        await self.update_from_client()

    async def update_from_client(self):
        dat = self.client.data
        dataSK = dat.get('dataSK') or {}
        if not dataSK:
            return

        spec = CONDITION_CODES.get(f'{dataSK.get("weathercode") or ""}')
        if spec is None:
            _LOGGER.warning('Unknown condition code: %s', dataSK.get('weathercode'))
        self._attr_condition = spec.condition if spec else None
        self._attr_native_temperature = as_float(dataSK.get('temp'))
        self._attr_humidity = as_float(dataSK.get('sd'))
        self._attr_native_pressure = as_float(dataSK.get('qy'))
        self._attr_native_visibility = as_float(dataSK.get('njd'))
        self._attr_native_wind_speed = as_float(dataSK.get('wse'))
        self._attr_wind_bearing = wind_bearing_to_degrees(dataSK.get('WD') or dataSK.get('wde'))

        attrs = {
            'area_id': self.client.area_id,
            'condition_text': dataSK.get('weather'),
            'observation_time': dataSK.get('time'),
        }
        if dataSK.get('WD'):
            # 原始风向文本（"无持续风向" 时 wind_bearing 为 None，文本仍保留）
            attrs['wind_bearing_text'] = dataSK.get('WD')

        # 生活指数已搬到 sensor.<站>_living_index（状态可直接喂 Assist）
        # 以下数据 HA weather 域没有对应字段：作为属性而非独立实体
        if (val := as_float(dataSK.get('rain'))) is not None:
            attrs['precipitation_1h'] = val
        if (val := as_float(dataSK.get('rain24h'))) is not None:
            attrs['precipitation_24h'] = val
        if (val := as_float(dataSK.get('aqi'))) is not None:
            attrs['aqi'] = val

        minutely = dat.get('minutely') or {}
        if minutely.get('msg'):
            attrs['forecast_minutely'] = minutely['msg']
            if minutely.get('times') and minutely.get('values'):
                attrs['forecast_minutely_start'] = minutely['times'][0]
                attrs['forecast_minutely_values'] = minutely['values']
                attrs['forecast_minutely_step'] = 6

        self._attr_extra_state_attributes = attrs

        await self.async_forecast_daily()
        await self.async_forecast_hourly()
        await self.async_forecast_twice_daily()
        self.async_write_ha_state()

    async def async_forecast_daily(self) -> list[Forecast] | None:
        """日预报：只用上游真实字段，缺则省略。"""
        if 'dailies' not in self.client.data:
            await self.client.update_dailies()

        today = dt_util.start_of_local_day()
        lst: list[Forecast] = []
        prev = today
        for item in self.client.data.get('dailies', []):
            if len(lst) >= DAILY_FORECAST_LIMIT:
                break
            try:
                month, day = (int(v) for v in f'{item.get("fi")}'.split('/'))
                tim = today.replace(
                    year=today.year + 1 if month < today.month else today.year,
                    month=month,
                    day=day,
                )
            except (TypeError, ValueError):
                continue
            if tim < prev:
                continue

            row = build_daily_row(item)
            if row is None:
                continue
            row['datetime'] = tim
            lst.append(row)
            prev = tim
        return lst

    async def async_forecast_twice_daily(self) -> list[Forecast] | None:
        """白天/夜间预报：is_daytime 必填（HA 强校验），白天 08:00、夜间 20:00。"""
        if 'dailies' not in self.client.data:
            await self.client.update_dailies()

        today = dt_util.start_of_local_day()
        lst: list[Forecast] = []
        for item in self.client.data.get('dailies', []):
            if len(lst) >= DAILY_FORECAST_LIMIT * 2:
                break
            try:
                month, day = (int(v) for v in f'{item.get("fi")}'.split('/'))
                base = today.replace(
                    year=today.year + 1 if month < today.month else today.year,
                    month=month,
                    day=day,
                )
            except (TypeError, ValueError):
                continue

            rows = build_twice_daily_rows(item)
            for row in rows:
                tim = base.replace(hour=8 if row['is_daytime'] else 20)
                if tim < (lst[-1]['datetime'] if lst else today):
                    continue
                row['datetime'] = tim
                lst.append(row)
        return lst

    async def async_forecast_hourly(self) -> list[Forecast] | None:
        """逐时预报：jg=降水量(mm/h)、ji=风向角度、jh=云量(%)。"""
        if 'hourlies' not in self.client.data:
            await self.client.update_hourlies()

        now = dt_util.now()
        floor = now.replace(minute=0, second=0, microsecond=0)
        lst: list[Forecast] = []
        for item in self.client.data.get('hourlies', []):
            if len(lst) >= HOURLY_FORECAST_LIMIT:
                break
            try:
                day = datetime.strptime(f'{item.get("jf")}', '%Y%m%d%H%M')
            except (TypeError, ValueError):
                continue
            tim = floor.replace(
                month=day.month, day=day.day, hour=day.hour,
            )
            if tim < floor:
                continue

            row = build_hourly_row(item)
            if row is None:
                continue
            row['datetime'] = tim
            lst.append(row)
        return lst
