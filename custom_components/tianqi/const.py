"""Constants and unit conversion helpers for the tianqi integration.

所有单位/枚举换算集中在这里，实体层只消费 HA 标准值：
- 风向 -> 角度（度，0=北，顺时针）
- 风力等级（蒲福）-> km/h
- 上游带单位的字符串 -> float
"""

from __future__ import annotations

import logging
import re
from typing import NamedTuple

_LOGGER = logging.getLogger(__name__)

# 中文/英文风向 -> 角度（风的来向，0 = 正北，顺时针）
WIND_BEARINGS: dict[str, float] = {
    '北风': 0.0, '北': 0.0, '偏北风': 0.0,
    '东北风': 45.0, '东北': 45.0, '偏东北风': 45.0, '东北偏北风': 22.5, '东北偏东风': 67.5,
    '东风': 90.0, '东': 90.0, '偏东风': 90.0, '东南偏东风': 112.5,
    '东南风': 135.0, '东南': 135.0, '偏东南风': 135.0, '东南偏南风': 157.5,
    '南风': 180.0, '南': 180.0, '偏南风': 180.0, '西南偏南风': 202.5,
    '西南风': 225.0, '西南': 225.0, '偏西南风': 225.0, '西南偏西风': 247.5,
    '西风': 270.0, '西': 270.0, '偏西风': 270.0, '西北偏西风': 292.5,
    '西北风': 315.0, '西北': 315.0, '偏西北风': 315.0, '西北偏北风': 337.5,
    # 上游 wde 英文缩写
    'N': 0.0, 'NNE': 22.5, 'NE': 45.0, 'ENE': 67.5,
    'E': 90.0, 'ESE': 112.5, 'SE': 135.0, 'SSE': 157.5,
    'S': 180.0, 'SSW': 202.5, 'SW': 225.0, 'WSW': 247.5,
    'W': 270.0, 'WNW': 292.5, 'NW': 315.0, 'NNW': 337.5,
}

# 上游表示"风向不定"的文本 -> 无标准角度，返回 None
VARIABLE_WINDS: set[str] = {'无持续风向', '风向不定', '静风', '微风', '旋转风', '不定'}

# 蒲福风级 -> 该级风速中值（km/h），用于把"3-4级"这类预报换算成风速
BEAUFORT_KMH: dict[int, float] = {
    0: 0.5, 1: 3.0, 2: 8.5, 3: 15.5, 4: 24.0, 5: 33.5, 6: 44.0,
    7: 55.5, 8: 68.0, 9: 81.5, 10: 95.5, 11: 110.0, 12: 125.0,
}

_NUMBER_RE = re.compile(r'-?\d+(?:\.\d+)?')
_RANGE_RE = re.compile(r'(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)')


def as_float(value, default=None):
    """把 '73%' / '7km/h' / '1011' 之类转成 float，失败返回 default。"""
    if value is None or isinstance(value, (int, float)):
        return value if value is not None else default
    match = _NUMBER_RE.search(f'{value}')
    if not match:
        return default
    try:
        return float(match.group(0))
    except ValueError:
        return default


def wind_bearing_to_degrees(value) -> float | None:
    """风向文本 -> 角度（度）。无法识别或风向不定返回 None（HA 标准允许 None）。"""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value) % 360
    text = f'{value}'.strip().upper().replace(' ', '')
    if not text:
        return None
    if text in VARIABLE_WINDS:
        return None
    # 上游有时给纯数字角度
    if text.replace('.', '', 1).isdigit():
        return float(text) % 360
    if (bearing := WIND_BEARINGS.get(text)) is not None:
        return bearing
    # '西北风转东南风' 之类：取第一个可识别风向
    for token in re.split(r'[转至到,，/]', text):
        if (bearing := WIND_BEARINGS.get(token)) is not None:
            return bearing
    _LOGGER.debug('Unknown wind direction: %s', value)
    return None


def wind_force_to_kmh(value) -> float | None:
    """'3-4级' / '2级' / '<3级' -> 风速 km/h（蒲福中值，取区间平均）。"""
    if value is None:
        return None
    text = f'{value}'.replace('级', '').replace('≤', '').replace('<', '').strip()
    if not text:
        return None
    if match := _RANGE_RE.search(text):
        low, high = float(match.group(1)), float(match.group(2))
        level = (low + high) / 2
    elif (num := as_float(text)) is not None:
        level = num
    else:
        return None
    level = max(0.0, min(12.0, level))
    low_i, high_i = int(level), min(12, int(level) + 1)
    if low_i == high_i or level == low_i:
        return BEAUFORT_KMH[low_i]
    ratio = level - low_i
    return round(BEAUFORT_KMH[low_i] + (BEAUFORT_KMH[high_i] - BEAUFORT_KMH[low_i]) * ratio, 1)

# --- 天气代码映射 ---------------------------------------------------------
# 这里的 condition 取 homeassistant.components.weather.ATTR_CONDITION_* 的字面值，
# 用字面值是为了让换算层不依赖 HA，便于单测。
CONDITION_VALUES = {
    'sunny', 'clear-night', 'partlycloudy', 'cloudy', 'rainy', 'pouring',
    'lightning', 'lightning-rainy', 'hail', 'snowy', 'snowy-rainy',
    'fog', 'windy', 'windy-variant', 'exceptional',
}


class ConditionSpec(NamedTuple):
    condition: str
    text: str


# 上游天气代码 -> (HA condition, 原文)。只做一一映射，不夹带降水/云量推测值。
CONDITION_CODES: dict[str, ConditionSpec] = {
    'd00': ConditionSpec('sunny', '晴'),
    'd01': ConditionSpec('partlycloudy', '多云'),
    'd02': ConditionSpec('cloudy', '阴'),
    'd03': ConditionSpec('rainy', '阵雨'),
    'd04': ConditionSpec('lightning-rainy', '雷阵雨'),
    'd05': ConditionSpec('hail', '雷阵雨伴有冰雹'),
    'd06': ConditionSpec('snowy-rainy', '雨夹雪'),
    'd07': ConditionSpec('rainy', '小雨'),
    'd08': ConditionSpec('rainy', '中雨'),
    'd09': ConditionSpec('rainy', '大雨'),
    'd10': ConditionSpec('pouring', '暴雨'),
    'd11': ConditionSpec('pouring', '大暴雨'),
    'd12': ConditionSpec('pouring', '特大暴雨'),
    'd13': ConditionSpec('snowy', '阵雪'),
    'd14': ConditionSpec('snowy', '小雪'),
    'd15': ConditionSpec('snowy', '中雪'),
    'd16': ConditionSpec('snowy', '大雪'),
    'd17': ConditionSpec('snowy', '暴雪'),
    'd18': ConditionSpec('fog', '雾'),
    'd19': ConditionSpec('snowy-rainy', '冻雨'),
    'd20': ConditionSpec('exceptional', '沙尘暴'),
    'd21': ConditionSpec('rainy', '小到中雨'),
    'd22': ConditionSpec('rainy', '中到大雨'),
    'd23': ConditionSpec('pouring', '大到暴雨'),
    'd24': ConditionSpec('pouring', '暴雨到大暴雨'),
    'd25': ConditionSpec('pouring', '大暴雨到特大暴雨'),
    'd26': ConditionSpec('snowy', '小到中雪'),
    'd27': ConditionSpec('snowy', '中到大雪'),
    'd28': ConditionSpec('snowy', '大到暴雪'),
    'd29': ConditionSpec('exceptional', '浮尘'),
    'd30': ConditionSpec('exceptional', '扬沙'),
    'd31': ConditionSpec('exceptional', '强沙尘暴'),
    'd32': ConditionSpec('fog', '浓雾'),
    'd33': ConditionSpec('lightning', '雷电'),
    'd49': ConditionSpec('fog', '强浓雾'),
    'd53': ConditionSpec('fog', '霾'),
    'd54': ConditionSpec('fog', '中度霾'),
    'd55': ConditionSpec('fog', '重度霾'),
    'd56': ConditionSpec('fog', '严重霾'),
    'd57': ConditionSpec('fog', '大雾'),
    'd58': ConditionSpec('fog', '特强浓雾'),
    'd301': ConditionSpec('rainy', '雨'),
    'd302': ConditionSpec('snowy', '雪'),
}


# --- 预报行构造 -----------------------------------------------------------
# 输入上游原始 item，输出只含 HA Forecast 标准键的 dict（datetime 由实体层补）。
# 字段语义均经实测确认，未确认的字段一律不使用。

def build_daily_row(item: dict) -> dict | None:
    """weixinfc.f[] -> Forecast（不含 datetime / condition 之外的修饰）。"""
    spec = CONDITION_CODES.get(f'd{item.get("fa")}')
    if spec is None:
        return None
    row = {'condition': spec.condition}
    if (val := as_float(item.get('fc'))) is not None:
        row['native_temperature'] = val
    if (val := as_float(item.get('fd'))) is not None:
        row['native_templow'] = val
    if (val := wind_bearing_to_degrees(item.get('fe'))) is not None:
        row['wind_bearing'] = val
    # 上游只给蒲福风级（fg="3-4级"），按中值换算 km/h
    if (val := wind_force_to_kmh(item.get('fg'))) is not None:
        row['native_wind_speed'] = val
    return row


def build_hourly_row(item: dict) -> dict | None:
    """wap_180h.jh[] -> Forecast。

    实测字段：ja=天气码 jb=气温 je=相对湿度 jg=降水量(mm/h)
              jh=云量(%) ji=风向角度 jj=气压(hPa)
    """
    spec = CONDITION_CODES.get(f'd{item.get("ja")}')
    if spec is None:
        return None
    row = {'condition': spec.condition}
    if (val := as_float(item.get('jb'))) is not None:
        row['native_temperature'] = val
    if (val := as_float(item.get('je'))) is not None:
        row['humidity'] = val
    if (val := as_float(item.get('jj'))) is not None:
        row['native_pressure'] = val
    if (val := as_float(item.get('jg'))) is not None:
        row['native_precipitation'] = val
    if (val := as_float(item.get('jh'))) is not None and 0 <= val <= 100:
        row['cloud_coverage'] = int(val)
    if (val := wind_bearing_to_degrees(item.get('ji'))) is not None:
        row['wind_bearing'] = val
    return row
