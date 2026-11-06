#!/usr/bin/env python3
"""干跑脚本：直接打上游接口，用集成里的换算逻辑打印"改造后"会输出的标准值。

不需要 Home Assistant，只验证 字段语义 / 风向角度 / 单位 是否正确。
用法：python3 scripts/live_check.py [area_id]
"""

from __future__ import annotations

import json
import re
import ssl
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'custom_components' / 'tianqi'))

from const import (  # noqa: E402
    CONDITION_CODES,
    as_float,
    build_daily_row,
    build_hourly_row,
    wind_bearing_to_degrees,
)

HEADERS = {
    'Referer': 'https://m.weather.com.cn/',
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
                  ' (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36',
}
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE  # mpf 证书已过期


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20, context=CTX) as resp:
        return resp.read().decode('utf-8', 'replace')


def main(area_id: str = '101280101') -> int:
    print(f'== area_id {area_id}')

    idx = fetch(f'https://d1.weather.com.cn/weather_index/{area_id}.html?_=1')
    sk = json.loads(re.search(r'dataSK\s*=\s*(\{.*?\})\s*;', idx, re.S).group(1))
    spec = CONDITION_CODES.get(sk.get('weathercode', ''))
    print('\n[实况 -> weather 实体标准字段]')
    print(f"  condition          = {spec.condition if spec else None!r}"
          f"    (原文 {sk.get('weather')}, code {sk.get('weathercode')})")
    print(f"  native_temperature = {as_float(sk.get('temp'))} °C")
    print(f"  humidity           = {as_float(sk.get('sd'))} %")
    print(f"  native_pressure    = {as_float(sk.get('qy'))} hPa")
    print(f"  native_wind_speed  = {as_float(sk.get('wse'))} km/h")
    print(f"  wind_bearing       = {wind_bearing_to_degrees(sk.get('WD') or sk.get('wde'))} °"
          f"    (原文 {sk.get('WD')} / {sk.get('wde')})")
    print(f"  native_visibility  = {as_float(sk.get('njd'))} km")

    fc = fetch(f'https://d1.weather.com.cn/weixinfc/{area_id}.html?_=1')
    dailies = json.loads(re.search(r'fc\s*=\s*(\{.*\})\s*;?', fc, re.S).group(1)).get('f', [])
    print('\n[日预报 -> Forecast（前 4 天）]')
    for item in dailies[:4]:
        row = build_daily_row(item)
        if row is None:
            print(f"  {item.get('fi')}: 未知天气码 fa={item.get('fa')}")
            continue
        print(f"  {item.get('fi'):>5} {row}")

    hh = fetch(f'https://d1.weather.com.cn/wap_180h/{area_id}.html?_=1')
    hourlies = json.loads(re.search(r'fc180\s*=\s*(\{.*\})\s*;?', hh, re.S).group(1)).get('jh', [])
    print('\n[逐时预报 -> Forecast（前 6 小时）]')
    for item in hourlies[:6]:
        row = build_hourly_row(item)
        if row is None:
            print(f"  {item.get('jf')}: 未知天气码 ja={item.get('ja')}")
            continue
        print(f"  {item.get('jf')} {row}")

    print('\n[分钟级降水]')
    try:
        mpf = json.loads(fetch('https://mpf.weather.com.cn/mpf_v3/webgis/minute'
                               '?lat=23.13&lon=113.26'))
        print(f"  msg={mpf.get('msg')!r} points={len(mpf.get('values') or [])}")
    except Exception as exc:  # noqa: BLE001
        print(f'  跳过：{exc}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main(*sys.argv[1:]))
