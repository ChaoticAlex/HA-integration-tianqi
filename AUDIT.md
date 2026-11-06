# 改造前审计（HA 数据标准 / 上游字段语义）

> 状态：A、B 两项已在 `dev` 分支实施完毕，实施记录见 [`CHANGES.md`](CHANGES.md)。

基线：upstream `hasscc/tianqi` @ `bbc166f`（main），工作分支 `dev`。
验证方式：读源码 + 直接打上游接口比对真实返回值（2026-11-06 10:20-10:45 CST）。

## A. 风向：现状与标准不符

| 位置 | 现状 | 问题 |
|---|---|---|
| `weather.py:105` | `_attr_wind_bearing = dataSK['WD'] or dataSK['wde']` | 优先取汉字「西北风」 |
| `weather.py:211` | 日预报 `row['wind_bearing'] = item['fe']` | 汉字（「北风」/「无持续风向」） |
| `weather.py:269` | 逐时 `row['wind_bearing'] = observe['wind']` | 汉字，且是**实况**风，不是预报风 |
| `converters/base.py:66-83` | `wind_direction` 传感器输出汉字 | 文本型，无法参与数值比较 |

HA 侧标准（`components/weather/entity.py`）：
- `wind_bearing: float | str | None` —— 类型允许 str，所以汉字**不会报错**，但规范语义是「风从哪个方位来（度）」，前端只在数字时转罗盘；第三方卡片 / 自动化 / 图表按数值处理，汉字会直接失效。
- 风向传感器标准值：`SensorDeviceClass.WIND_DIRECTION` + 单位 `°` + `state_class: measurement_angle`（`components/sensor/const.py`）。

**关键发现（已实测）**：逐时接口 `wap_180h` 本来就带**风向角度** `ji`，代码完全没用，却把 `jg` 当风速。

实测证据（2026-11-06 10:00 前后）：

| 站点 | 实况 WD/wse | 逐时 `ji` | 逐时 `jg` |
|---|---|---|---|
| 湛江 101281001 | 东风(90°) / 10km/h | 90, 97, 104, 112, 113 | 0, 1.6, 0, 0.7, 2.3 |
| 大连 101070201 | 北风(0°) / 7km/h | 0, 224, 260, 281 | 0, 0, 0, 0 |
| 呼和浩特 101080101 | 东风(90°) / 5km/h | 135, 74, 85, 110 | 0, 0, 0, 0 |
| 广州 101280101 | 西北风(315°) / 7km/h | — | 0.7, 0.7, 0.9, 0.7, 0.7 |

推论：
- `ji` = 风向角度（与实况风、海陆风日变化吻合）。
- `jg` = **降水量 mm/h**，不是风速：大连/呼市无风无雨时 `jg=0`，而 `jg≠0` 的行 100% 落在 `ja=07`（小雨）行。
- ⇒ 当前 `weather.py:266` `native_wind_speed = jg` 是错的（把雨量当风速），同时真正的风资源 `ji` 被丢弃。

## B. 其它不符合标准/不可靠之处

1. **伪造降水**（`weather.py:176/236`）：日/时 `native_precipitation` 由天气代码映射成固定 mm/h（README 已承认）。会污染 Statistics / 图表 / 自动化阈值。建议无实测值时为 `None`。
2. **天气代码表错位**：`weather.py:328` `d54 = [FOG, 'MODERATE_HAZE', 90, 0, '中度霾']` → 降水 90mm/h、云量 0。应为 `0, 90`（同族 d53/d55 都是 0/90~100）。
3. **风力等级是汉字**：`WS="2级"` 作为 `wind_level` 字符串属性；建议同时给数值（蒲福级 int / 或由 km/h 换算 m/s），汉字保留为文本属性。
4. **`wind_speed_and_unit="8km/h"`** 冗余且不可计算，建议仅留数值 + 原生单位。
5. **`_attr_attribution = None`**：数据来源（中国天气网）未署名，建议写 `中国天气网 (weather.com.cn)`。
6. **解析健壮性**：`float(dataSK.get('sd','').replace('%',''))` 等裸 `float()`，字段缺失时抛 `ValueError` 直接打挂实体更新（无 try）。
7. **日预报 `today` 判定**用 `strftime('%m/%d').replace('/0','/').lstrip('0')` 字符串技巧，跨月/单位数日期易错；`datetime` 用 naive 本地时间，建议 `dt_util.start_of_local_day()`。
8. **`condition` 未知代码时 `return`**：早退导致其余字段（湿度/温度）全部不更新，且状态保留旧值，无 `unknown` 提示。
9. **配置/翻译**：只有 `translations/en.json`，界面中文硬编码在 `config_flow.py`；HA 规范应在 `strings.json` + `translations/zh-Hans.json`。
10. **无 `quality_scale`、无测试**：`manifest.json` 无 `integration_type`，仓库无 `tests/`。大改前建议先补最小回归测试（喂固定 payload 断言实体属性）。
11. 集成对 `d1/mpf` 节点 `verify_ssl=False`，因 `mpf.weather.com.cn` 证书 2026-09-28 已过期；改版时若上游修好证书应改回校验。

## C. 建议的改造顺序（等确认）

1. 新增 `const.py`：风向汉字→度数映射（含「无持续风向」「静风」「偏北风」等变体）+ 蒲福级换算。
2. `weather.py`：`wind_bearing` 三处改度数；逐时改用 `ji`；`jg` 改回 `native_precipitation`；删除伪造降水（或加开关）。
3. `converters/base.py`：`wind_direction` 传感器改 device_class `wind_direction` + `°` + `measurement_angle`，新增 `wind_direction_text`。
4. 修 `d54`、补 attribution、float 解析统一走安全转换函数。
5. `tests/`：3 个固定 payload（晴/小雨/无持续风向）+ 快照断言。
6. 最后再动 config_flow / translations。
