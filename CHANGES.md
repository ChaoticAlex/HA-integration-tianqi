# 改造记录（严格 HA 标准版）

## 1.0.2 — 实体瘦身（非必要不增实体）

| 变更 | 说明 |
|---|---|
| 删除 7 个传感器 | `temperature` / `humidity` / `atmospheric_pressure` / `visibility` / `wind_speed` / `wind_bearing` / `wind_force` —— 数据已在 `weather` 实体状态属性里 |
| `pm25` → `aqi` | 实测 5 城 `aqi_pm25` 与 `aqi` 完全同值，是 AQI 指数而非 PM2.5 浓度；改 `device_class: aqi`、去单位 |
| `forecast_minutely` 属性压缩 | 从「每个时间戳一条属性（20 条）」改为 `forecast_minutely_values` + `forecast_minutely_start` + `forecast_minutely_step` |
| `weather` 实体名 | `_attr_name = None`，修掉「江南天气 江南」重复命名 |
| 实体总数 | 13 → **6**（weather 1 + sensor 4 + binary_sensor 1） |

受影响的自动化：`sensor.<站>_pm25`、`sensor.<站>_temperature` 等实体 ID 不再存在，
改用 `state_attr('weather.<站>', 'temperature')` 或对应的 `weather` 属性。

## 1.0.1 — 修复"无法加载配置向导 / Invalid handler specified"

- `converters/base.py` 的相对导入写错：`from .const import` → `from ..const import`。
  该错误让整个包 import 失败，HA 因此注册不到 config_flow。
- 新增 `tests/test_import.py`：用最小 homeassistant 桩模块把 `__init__ / weather / sensor /
  binary_sensor / config_flow / converters` 全量 import 一遍，专拦这类"导入即崩"的问题。
  （本轮测试数 20 → 24）

分支 `dev`，基线 `bbc166f`。原则：**只输出 Home Assistant 标准值，砍掉一切非标准兼容**（含彩云卡片兼容）。允许 breaking change。

## 1. 破坏性变更（升级前必读）

| 变更 | 影响 |
|---|---|
| 移除 `caiyun` 选项与全部彩云卡片兼容字段（`skycon`、`cloudrate`、`hourly_*`、顶层 `forecast` 属性） | 彩云卡片 `lovelace-colorfulclouds-weather-card` 不再可用 |
| `wind_bearing` 由中文（`西北风`）改为**角度**（`315.0`） | 依赖文本匹配风向的自动化/template 需改用角度或 `wind_bearing_text` |
| 新增 `sensor.<站>_wind_bearing`（`device_class: wind_direction`, `°`） | 对应旧属性 `wind_direction` / `wind_direction_code` 已删 |
| 删除 `wind_speed_and_unit`、`limit_number` 传感器 | 单项数据可从上游页面/其他集成获得 |
| 删除 `temphigh` / `templow` / `forecast_hourly` / `forecast_keypoint` / `forecast_alert` 属性 | 温度用 `forecast`，预警用 `binary_sensor.<站>_warning` |
| 逐时预报 `native_wind_speed` 不再输出（上游无该字段） | 原值是 `jg`，其实是降水量 |

## 2. 数据语义修正（实测确认）

- `jg` = **降水量 mm/h**（原代码当风速）；无风无雨时恒为 0，非 0 行 100% 落在小雨码。
- `ji` = **风向角度** 0-360（原代码完全未用）；夜间非 0、逐日稳定，与实况风一致。
- `jh` = **云量 %**（原代码用天气码硬编码假云量）。
- 逐时风速上游确实没有 → 不输出，不编。
- 日预报风速由蒲福级（`fg="3-4级"`）按中值换算 km/h；日预报无降水/湿度字段 → 不输出（原为按天气码硬造的固定 mm/h）。

## 3. HA 标准对齐

- 实体单位：`native_temperature_unit` / `native_pressure_unit` / `native_wind_speed_unit` / `native_visibility_unit` / `native_precipitation_unit` 统一在 `__init__` 设置一次。
- 预报只含 `Forecast` TypedDict 的键；缺数据即省略。
- 日预报 `datetime` 用 `dt_util.start_of_local_day()`（带时区），去掉 `'%m/%d'.replace('/0','/')` 字符串技巧，并过滤掉"昨天"行。
- `condition` 未知代码 → `None`（状态 `unknown`），不再早退保留旧值并丢字段。
- 单位/数值解析统一走 `as_float()`，字段缺失不再抛 `ValueError` 打断更新。
- `attribution` = `中国天气网 (weather.com.cn)`。
- 修正 `d54 中度霾` 曾把 90 当降水量（表已重写为纯 condition 映射，不再携带降水/云量推测值）。
- 霾/浮尘类映射统一：霾/雾 → `fog`，沙尘类 → `exceptional`，冻雨 → `snowy-rainy`（原为 `hail`）。
- 新增 `strings.json` + `translations/zh-Hans.json`，实体名走 `translation_key`。
- `manifest.json`：`integration_type: service`、`loggers`、版本 `1.0.0`；`hacs.json` 最低 HA `2023.9.0`（已核对该版本存在 `Forecast`、`native_visibility`、`FORECAST_*` feature）。

## 4. 新增文件

```
custom_components/tianqi/const.py        # 风向/风级换算 + 天气码表 + 预报行构造（无 HA 依赖）
custom_components/tianqi/strings.json
custom_components/tianqi/translations/{en,zh-Hans}.json
tests/test_const.py                      # 20 个断言，python3 -m unittest 直接跑
tests/test_rows.py
scripts/live_check.py                    # 干跑：打上游接口，打印"改造后"标准值
```

## 5. 未做 / 待定

1. `FORECAST_TWICE_DAILY`：上游日预报有白天/夜间两个天气码（`fa`/`fb`），可映射为 twice-daily，但需要 `is_daytime` 语义对齐，暂留 daily。
2. 生活指数仍是 weather 实体的 `indexes` 属性（非标准但非兼容 hack），如需彻底标准化应拆成独立 sensor。
3. 逐时 `jd` / `jk` 字段语义未确认（疑似降水概率/能见度），未使用。
4. 未在真实 HA 实例中跑过：本机无 HA 环境，`pip install homeassistant` 属第三方依赖安装，等你确认。
5. `verify_ssl=False` 保留（因 `mpf.weather.com.cn` 证书 2026-09-28 已过期），已在代码注释标注。
