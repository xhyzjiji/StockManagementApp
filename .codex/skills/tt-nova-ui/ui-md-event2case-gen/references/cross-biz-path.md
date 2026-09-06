# 跨业务场景 Path 写法指南（G10）

当本需求涉及**从另一个业务入口进入**（例如：从营收入口点进粉丝团面板、从短视频 FYP 进入音乐直播间）时，
agent 容易犯两类错误：

1. **完全不敢写跨业务 Path**：只写"从X业务进入"但不写出 App 主页起的导航链，导致用例不可执行。
2. **跨业务扩 dimension**：把其他业务的事件/参数也写进本需求 scope，违反 R12。

本文给出判断标准和正确写法。

## 判断标准

| 场景 | 处理方式 |
|------|----------|
| 其他业务入口是**本需求事件的触发起点**（例如从 FYP 进入直播间才会看到音乐锚点） | Path 导航链写完整（App 主页 → 其他业务页面 → 本需求入口），但 scope 只声明本需求事件 |
| 其他业务页面**内部的事件**需要验证 | 必须在 PRD/ETD 里明确声明是本需求新增参数/事件，否则写 out_of_scope |
| 其他业务入口**本身是否存在/样式**需要验证（UI 而非埋点） | 不归本埋点用例管，写 notes 说明需要 UI 用例覆盖 |
| 其他业务入口的点击/曝光事件是本需求新增的 | 正常进 scope，event_name 以 `livesdk_` 开头，按 R12 走 |

## Path 写法规则

### 1. 必须从 App 主页起，段段命中 route

导航链的每一段必须是以下两者之一：
- 命中 `tt-nova/ui/business/*/business-ui_routes/*.json` 中的 route 段（直接写段名）；
- 该段是**用户提供或 PRD 截图可证**（在 Precondition notes 里写 `evidence=user_supplied:<PRD链接#section>`）。

错误写法（只写跨业务目标，没有导航链）：
```
1. 设备A（主播）：直接进入音乐直播流量设置页。
```

正确写法（完整导航链）：
```
1. 设备A（主播）：冷启动 TikTok App。
2. 设备A（主播）：点击底部【+】进入开播页。
3. 设备A（主播）：点击【Go Live】开播。
4. 设备A（主播）：点击底部【...】更多面板。
5. 设备A（主播）：点击【音乐直播流量设置】进入设置页。
```

### 2. 入口事件的 entrances 字段写全

跨业务入口触发的事件，`entrances` 字段必须包含触发该事件的入口标识（而不是只有业务模块名）：

```json
{
  "event_name": "livesdk_music_live_traffic_setting_page_show",
  "entrances": ["live_more_panel", "music_live_setting_entry"],
  "roles": ["anchor"]
}
```

### 3. 跨业务 route 证据登记

如果导航链里某段在本地 routes 里找不到（其他业务的 route 未沉淀进 KB）：
- 必须在 Precondition 里写 evidence 引用：
  ```
  - assume | 从【更多面板】到【音乐直播流量设置页】的导航段 PRD 截图可证（evidence=user_supplied:PRD#3.2）。
  ```
- 同时在 `kb_gaps.json` 里登记 G-ROUTE-xxx，`severity: soft` 表示不阻塞交付（导航段可执行）；`severity: blocking` 表示 PRD 也没写清楚，必须反问用户。

### 4. 禁止反向扩维

从 FYP 进入音乐直播间这个场景里：
- ✅ scope 包含 `livesdk_fyp_live_music_anchor_show`（音乐锚点曝光，是本需求的）
- ❌ scope 不包含 `video_play`（普通短视频播放事件，虽然用例里会经过 FYP，但这不是本需求新增/修改）
- ❌ scope 不包含 `livesdk_live_play`（进房事件，不是本需求埋点）——除非 PRD/ETD 明确说本需求给这个事件加了新参数

判断方法：只把**ETD 里列出的、本需求新增或修改的事件**写进 scope。导航链上必经的其他业务事件，如果本需求没改它们，不写进 scope，也不做断言（可以写 `不校验，Path 必要步骤`）。

### 5. 跨业务角色一致

如果本需求是观众侧事件（例如从 FYP 点击锚点进入直播间的是观众），导航链全程都要从观众设备视角写：
```
1. 设备B（观众）：冷启动 TikTok App。
2. 设备B（观众）：在 FYP 浏览到带 Song -> Live 底部直播锚点的视频。   # 观众视角
3. 设备B（观众）：点击底部直播锚点进入直播间。                         # 观众点击
4. 设备B（观众）：...
```

不能出现"设备A（主播）：开播" + "设备B（观众）：直接看到锚点"——主播开播的操作必须明确写出来作为前置。

## 最小正反例

反例（缺导航链 + 扩 dimension）：
```markdown
> TC 点击音乐锚点
**Precondition**:
- 观众进入 FYP
**Steps**:
1. 观众点击音乐直播锚点。
    - Assert: data | 上报 `livesdk_fyp_live_music_anchor_click`；`trigger_reason` = `bgm_matched`。
```

正例：
```markdown
> TC-R-003 点击 FYP 音乐直播锚点上报 anchor_click
**Precondition**:
- mock | env=ppe_music_live
- mock | 账号已加实验 libra flight/72057031
- assume | 设备A（主播）已开播音乐直播间且满足 Song->Live 锚点触发条件（evidence=user_supplied:ETD#trigger_condition）
**Steps**:
1. 设备A（主播）：冷启动 TikTok App，点击底部【+】→【Go Live】开播，播放版权音乐。
2. 设备B（观众）：冷启动 TikTok App，在 FYP 浏览。
3. 设备B（观众）：浏览到带 Song -> Live 底部直播锚点的视频。
4. 设备B（观众）：点击底部直播锚点。
    - Assert: data | 设备B（观众）：上报 `livesdk_fyp_live_music_anchor_click` 埋点；`anchor_id` 有值；`trigger_reason` = `bgm_matched`；`content_genre` = `0`；`anchor_type` = `music_talent`。
```

## 违反本指南的门禁后果

- 导航链段段无 evidence 且未命中本地 routes → `run_gates.py` 的 scenario 校验会报"跨业务 Path 缺路由证据"。
- 把其他业务事件写进 scope → `check_etd_scope.py` ETD 反查会报"ETD 里没有的事件"（除非写 out_of_scope）。
- 跨业务场景角色错位 → `check_etd_scope.py` 的角色-设备一致性检查会报"scope 声明 viewer 但找不到观众设备"。
