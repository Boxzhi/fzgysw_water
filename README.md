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

## HACS 图标

如果你想在 HACS 列表中显示图标，请将 `icon.png` 与 `logo.png` 上传到仓库根目录（默认分支），然后在 HACS 中刷新自定义仓库或重新加载 HACS。HACS 会自动读取这两个文件显示在集成列表与详情页中。
