# Libra group_id 补齐与用例分配（所有 case-gen 共用）

> 适用：`ui-md-event2case-gen` / `ui-xmind-case-gen` / `ui-md-case-gen` / `ui-xmind-case-specify` / `ui-md-case-upload`（转换落 `libra实验` 时）

## 0. 触发闸门（先判再问）

**本流程仅在用户已提供 Libra 链接时执行**（提测文档 / PRD / 对话里出现可识别的 Libra URL，例如 `https://libra-*.tiktok-row.net/libra/flight/{id}/...` 或含 `/flight/{id}` 的 Libra 域链接）。

| 输入情况 | 做什么 |
|---|---|
| **有 Libra 链接**，但无成对 `group_id` | 走下文 §1–§3：抽 `libra_id`/`region` → 分别问实验组/对照组 → 按 case 分配 |
| **无 Libra 链接**（只写了「要加实验」/flight 数字/实验名，没有 URL） | **不要**主动套本流程去追问实验组/对照组 group_id；按既有缺物料规则登记 `missing[]` / 一般反问即可，或等用户补链接后再启用本流程 |
| 用户已直接给出成对 group_id（无需链接） | 可直接分配，不必再为「有没有链接」纠缠 |

背景：裸访问 Libra URL 会落到 SSO，**当前 agent 无法可靠自动拉 version/group**。因此在**已有链接**却缺 `group_id` 时必须向用户补齐，禁止猜、禁止只问一个笼统的 group_id。

## 1. 能从链接自动抽出的

| 字段 | 来源 |
|---|---|
| `libra_id` | URL path `/flight/{id}/` |
| `region` | 域名：`libra-sg`→`sg`，`libra-va`/`libra-us`→`us`/`va`（按实际域）；抽不出则反问 |

## 2. 缺 `group_id` 时硬停反问（必须成对问）

**前提**：§0 已确认存在 Libra 链接。

**禁止**只问「请给 group_id」。必须分别问实验组与对照组（可一次消息里两项一起问）：

```
已拿到 Libra 链接 flight/<libra_id>（region=<region>），但缺 group_id；页面需 SSO，我拉不到版本表。
请分别提供：
1. 实验组 group_id（通常 v1 / 实验组 / treatment；打开 flight 页左侧版本号旁的数字）
2. 对照组 group_id（通常 v0 / 对照组 / control）
可选：各版本参数配置（如 karaoke_search_trending_opt=0/1）便于核对。
也可直接贴版本表截图 / 复制页面上的 v0、v1 行。
```

答完后写入 `test_kit.libra_flights[]`（或等价结构），例如：

```json
{
  "libra_id": "72226837",
  "region": "sg",
  "url": "https://libra-sg.tiktok-row.net/libra/flight/72226837/edit",
  "treatment_group_id": "76753738",
  "control_group_id": "76753737",
  "treatment_label": "v1 实验组",
  "control_label": "v0 对照组",
  "source": "user_supplied"
}
```

未齐前：`kb_gaps` / `test_kit.missing[]` 登记 `field=libra_flights.group_id`，**禁止**落 `libra实验` 工具空参，也禁止把 flight 塞进 `ttmock_preset`。

## 3. 按 case 分配（硬规则）

| 用例极性 | 挂哪个 group | `libra实验` 示例 |
|---|---|---|
| **正向**（实验命中才该出现的上报 / 新参 / 新事件） | **实验组** `treatment_group_id` | `libra实验 region=sg libra_id=72226837 group_id=76753738` |
| **对照 / 反向**（对照组或「不命中实验」时不上报 / 不带新参） | **对照组** `control_group_id` | `libra实验 region=sg libra_id=72226837 group_id=76753737` |
| AB 红线（RL-008）要求实验组+对照组都验 | **两条用例各挂一组**，不要一条里混两个 group | 各一条 `libra实验` |

`--precondition-tools-json` / xmind `preconditions`：**按用例**选对应 `group_id`，不要全集共用同一个 group 却写了正反两种断言。

多 flight：每个 **已提供链接** 的 flight 都成对问齐后再分配；多个实验工具节点可以并存。

## 4. 落 Bits 的 inputData（提醒）

转换后 `inputData` 形如：

```json
[{"key":"libraExperiment","value":["{\"region\":\"sg\",\"fids\":[\"72226837\"],\"libra\":[{\"libra_title\":\"...\",\"libra_id\":72226837,\"group_id\":76753738,\"region\":\"sg\"}]}"]}]
```

`fids` 为 string flight id；`libra[].libra_id` / `group_id` 为 number。

## 5. 反例检查清单

- ❌ 没有 Libra 链接却主动追问实验组/对照组 group_id  
- ❌ 只问一个 group_id，正反 case 全挂同一组  
- ❌ 有链接却静默省略 `libra实验` 或声称已加实验  
- ❌ `ttmock_preset ab_settings=flight:...` / `libra=` 顶替  
- ✅ 有链接 → 成对问齐 → 正向挂实验组、对照/反向挂对照组 → Precondition 文案与工具一致  
