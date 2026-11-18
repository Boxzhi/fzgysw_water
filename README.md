# 抚州公用水务 Home Assistant 集成

此仓库提供一个 Home Assistant 自定义集成，供“抚州公用水务有限公司”用户查询账号余额与近 12 个月的用水账单。

## 使用步骤

1. 将 `custom_components/fzgysw_water` 目录复制到你的 Home Assistant 配置目录下的 `custom_components/` 中。
2. 重启 Home Assistant。
3. 在 Home Assistant 中进入 **设置 → 设备与服务 → 添加集成**，搜索 **Fuzhou Water** 并添加。
4. 填写微信公众号接口中的 `apid` 参数（必填，支持原始值或 Base64 值），可选填写水表账号 `yhbh`（如有多个账号时用于指定）。
5. 完成配置后，会新增两个传感器：
   - **Water Balance**：显示当前账户余额并附带账号详情。
   - **Latest Water Bill**：显示最新一期账单金额，并包含近 12 个月账单列表。

## 数据刷新与抓取时间（v0.2.2）

- 集成默认每 **30 分钟**查询一次账户余额和最近 12 个月的账单；原有实体 ID 和账单属性保持不变。
- 余额和账单两个实体均新增 `last_successful_fetch` 属性，值为 UTC 时区的 ISO 8601 时间，例如 `2026-11-18T09:52:22+00:00`。前端可转换为 Home Assistant 配置的本地时区。
- 只有账户接口和账单接口都成功、返回有效响应后，该时间才会更新；余额或账单内容没有变化也会刷新时间。
- 请求失败、账单接口明确返回 `Success=false` 或数据格式异常时，本次更新标记为失败，不把错误伪装成空账单，也不会覆盖上一次成功抓取时间。
- 账单接口成功返回空数组 `[]` 表示确实没有账单，仍视作成功抓取。此时账单实体的状态可以为空，但 `last_successful_fetch` 属性仍会更新。

在 Home Assistant「开发者工具 → 模板」中查看抓取时间：

```jinja2
{{ state_attr('sensor.fuzhou_water_0000363994_bill', 'last_successful_fetch') }}
```
