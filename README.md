# 抚州公用水务 Home Assistant 集成

通过抚州公用水务微信公众号相关接口，向 Home Assistant 提供水费账户余额、用水账单及历史账单信息。支持通过 **HACS / Home Assistant Marketplace** 安装，也可手动安装。

- 当前版本：**v0.2.4**
- [正式版本与更新记录（Releases）](https://github.com/Boxzhi/fzgysw_water/releases)
- [问题反馈（Issues）](https://github.com/Boxzhi/fzgysw_water/issues)

## 主要功能

- 查询账户余额及账户相关信息。
- 获取最新一期水费账单、抄表日期、用水量和金额。
- 获取**最近 12 个自然月**范围内接口返回的历史账单（可能少于 12 笔；没有记录的月份不视为零用水）。
- **余额每 6 小时**查询一次，**历史账单每 12 小时**查询一次（账单失败时将在下一轮 6 小时刷新重试）。
- 余额和账单实体分别记录自身接口最近成功抓取时间 `last_successful_fetch`（v0.2.4 起独立记录）。

## 安装方式一：HACS / Marketplace（推荐）

1. 确认 Home Assistant 已安装并配置好 HACS / Marketplace。
2. 在 HACS / Marketplace 中选择 **「从 GitHub 链接添加」**，输入：

   ```text
   https://github.com/Boxzhi/fzgysw_water
   ```

   如果你使用的是提供「自定义存储库」入口的 HACS 版本，也可在该处添加上述地址，并选择 **Integration（集成）**。
3. 打开仓库详情，下载 / 安装 `fzgysw_water`，优先选择正式发布的稳定版本。
4. **重启 Home Assistant**。
5. 首次安装：进入 **设置 → 设备与服务 → 添加集成**，搜索「抚州公用水务」，按提示完成配置。

> HACS / Marketplace 负责下载和管理自定义集成文件；实际账户配置仍在 Home Assistant 的「设备与服务」中完成。

## 安装方式二：手动安装（备用）

1. 从 [Releases](https://github.com/Boxzhi/fzgysw_water/releases) 下载正式版本源码。
2. 将仓库中的 `custom_components/fzgysw_water` **整个文件夹**放入 Home Assistant 的 `/config/custom_components/` 下，最终目录应为：

   ```text
   /config/custom_components/fzgysw_water/
   ├── __init__.py
   ├── config_flow.py
   ├── const.py
   ├── coordinator.py
   ├── manifest.json
   ├── sensor.py
   └── translations/
   ```

3. 重启 Home Assistant。
4. 首次安装：进入「设置 → 设备与服务 → 添加集成」，搜索「抚州公用水务」并配置。

## 从手动安装迁移至 HACS

**可以保留原有账户配置和实体 ID，通常不必删除集成或重新绑定账户。**

1. 先创建一份 **Home Assistant 备份**，并备份 `/config/custom_components/fzgysw_water/`。
2. 按上文「HACS / Marketplace」步骤添加本 GitHub 仓库并下载正式版本，由 HACS 管理同一个集成目录。
3. 若 HACS 提示与现有手动安装文件冲突，先保留备份，再**只处理旧的集成代码目录**，然后重新下载；**不要删除「设置 → 设备与服务」中的原有配置项**。
4. 重启 Home Assistant，检查原有余额、账单实体是否仍正常显示。
5. 确认抓取时间属性 `last_successful_fetch` 已出现后，再结束迁移。

> 不要为了改用 HACS 而重新添加相同的水务账户，以免出现重复配置。升级或迁移不会自动更改原有实体 ID。

## 首次配置

添加「抚州公用水务」集成时：

| 参数 | 是否必填 | 说明 |
| --- | --- | --- |
| `apid` | 是 | 微信公众号查询接口使用的 `apid` 参数；支持原始值或 Base64 编码值 |
| `account_id` | 否 | 水表账户编号，对应接口中的 `yhbh`；可用于指定账户 |

请从你自己有权使用的抚州公用水务微信公众号查询流程中取得参数。**不要把实际 `apid` 或账户信息贴到公开 Issue 中。**

## 实体与属性

集成创建以下传感器，实际实体 ID 以 Home Assistant「开发者工具 → 状态」中的显示为准：

| 实体 ID 格式 | 内容 |
| --- | --- |
| `sensor.fuzhou_water_<水表账号>_balance` | 账户余额 |
| `sensor.fuzhou_water_<水表账号>_bill` | 最新一期账单金额及历史账单 |

常用属性：

| 实体 | 属性 | 含义 |
| --- | --- | --- |
| 余额 | `current_balance`、`amount_due` | 当前余额、应缴金额 |
| 账单 | `billing_month`、`read_date` | 账单月份、抄表日期 |
| 账单 | `usage`、`charge` | 本期用水量、账单金额 |
| 账单 | `start_meter`、`end_meter` | 上期与本期表读数 |
| 账单 | `payment_status`、`payment_date` | 缴费状态、缴费日期相关信息 |
| 账单 | `recent_bills` | 近 12 个自然月查询范围内的账单列表 |
| 余额 | `last_successful_fetch` | 最近一次账户余额接口成功抓取时间 |
| 账单 | `last_successful_fetch` | 最近一次历史账单接口成功抓取时间 |

## 数据更新与成功抓取时间

- 共用一个协调器，协调器**每 6 小时**运行一次；每轮尝试查询账户余额。
- 历史账单仅在距离**上一次成功抓取至少 12 小时**时请求。正常情况下每天余额 4 次、账单 2 次；实际时刻随集成启动时间变化。
- 启动或重新加载集成时，内存缓存为空，首次成功获取余额后会尝试获取账单，之后再按各自周期查询。
- 两个传感器的 `last_successful_fetch` 分别表示该接口最近一次成功响应的 UTC 时间，不再共用一次联合抓取时间。即使数据数值没变化，接口成功时对应时间也会更新。
- 账单请求失败时不覆盖旧账单及其抓取时间；余额成功仍正常更新。账单在下一轮 6 小时协调器更新时重试，而非重新等待 12 小时。
- 余额请求失败时保留旧余额及时间；如有已缓存的有效账户且账单到期，仍可尝试账单查询。两项均失败时保留原数据。
- 成功返回空账单列表时属于正常结果；明确返回 `Success=false` 或无效数据则视为账单请求失败。
- 水务卡片底部只读取**账单实体**的 `last_successful_fetch`；余额中途刷新不会改变卡片显示的抓取时间。
- 时间以 **UTC ISO 8601** 存储，例如 `2026-11-18T09:52:22+00:00`，前端可转换为 Home Assistant 本地时区。

在 **开发者工具 → 模板** 中查询（先将示例实体 ID 改为你自己的实际实体 ID）：

```jinja2
{% set entity_id = 'sensor.fuzhou_water_你的水表账号_bill' %}
{% set ts = state_attr(entity_id, 'last_successful_fetch') %}
最近成功抓取：
{{ as_local(as_datetime(ts)).strftime('%Y-%m-%d %H:%M:%S') if ts else '暂无数据' }}
```

> `last_changed`、`last_updated` 和 `last_reported` 是 Home Assistant 实体状态时间，不应直接视为水务平台的成功抓取时间。

## 更新与问题排查

- **HACS 安装**：在 HACS / Marketplace 中检查该仓库的更新，下载安装新版本并按提示重启 Home Assistant。
- **手动安装**：下载新的正式版本，覆盖 `/config/custom_components/fzgysw_water/`，然后重启。
- **升级后看不到抓取时间**：确认实际安装版本至少为 `v0.2.2`、已重启、集成更新成功，并核实实体 ID。
- **账单缺失**：先检查集成是否成功更新以及对应月份是否有官方账单记录；缺失月份不代表零用水。
- 仍有问题请通过 [GitHub Issues](https://github.com/Boxzhi/fzgysw_water/issues) 反馈，提供错误日志时请先隐藏 `apid`、户号等敏感信息。
