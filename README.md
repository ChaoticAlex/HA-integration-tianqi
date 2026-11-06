# ☁️ 天气预报（中国天气网）

Home Assistant 自定义集成，用 `weather` 实体提供中国天气网的实况、15 日预报、逐时预报、气象预警与分钟级降水。
**严格输出 Home Assistant 标准字段**，不提供任何第三方卡片兼容层。

> 数据全部来自 `weather.com.cn` 自有接口（中国气象局/华风气象传媒）。本集成未申请任何 appkey，走的是网页/App 内部接口，上游改版会失效。
> 数据语义与字段换算见 [`CHANGES.md`](CHANGES.md)；改造前审计见 [`AUDIT.md`](AUDIT.md)。

## 实体

**一设备 2 个实体**，与 HA 内置天气集成（`xiaomi_weather` / `open_meteo` / `met`）保持同构：
天气数据只通过 `weather` 实体交付，其余信息进状态属性。

| 实体 | 说明 |
|---|---|
| `weather.<站>` | 实况 + 日预报 15 天 + 逐时 48 小时 + **白天/夜间（twice daily）** |
| `binary_sensor.<站>_warning` | `device_class: problem`，预警状态 + `alarms` 明细（供自动化 `state` 触发） |

`weather` 实体状态属性：

- 标准：`temperature` / `humidity` / `pressure` / `wind_bearing`(度) / `wind_speed` / `visibility`
- 该集成补充：`precipitation_1h` / `precipitation_24h` / `aqi` / `forecast_minutely` +
  `forecast_minutely_values` / `forecast_minutely_start` / `indexes`（生活指数）/ `condition_text`

> 这些补充值只作为属性提供：可用于模板与自动化，但**不进长期统计（statistics）**。
> 需要历史曲线时，可用 `template: sensor` 自行派生，或从上游页面取。

## 安装

1. HACS：添加自定义仓库 `https://github.com/<你的用户名>/tianqi`，类型 `Integration`。
2. 或手动：下载仓库，复制 `custom_components/tianqi` 到 HA 的 `custom_components/` 目录。

最低 Home Assistant `2023.9.0`。

## 配置

`设置 > 设备与服务 > 添加集成 > 天气预报`，搜索城市/区县后选择地点。地点留空则按 HA 配置的经纬度自动匹配最近站点。

> 注意：区县实况与所属城市站常为同一份观测数据，报的是城市站，不是你门口。

## 开发

```bash
python3 -m unittest discover -s tests -v   # 20 个断言，无需 HA
python3 scripts/live_check.py 101280101    # 打上游接口，打印"改造后"标准值
```

## 已知限制

- 15 日预报 48 小时后为延伸期预报，仅供趋势参考。
- 分钟级降水是雷达外推，只对已生成的降水有效。
- `mpf.weather.com.cn` 证书已过期（2026-09-28），集成对该节点跳过校验；上游修复后应改回。
- 无 24 小时后的真实降水量/云量，这些字段不再输出，不再用天气码硬造。

## 相关链接

- 上游接口来源：中国天气网 <https://www.weather.com.cn/>
- 原仓库：<https://github.com/hasscc/tianqi>
