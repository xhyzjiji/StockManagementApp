# TTADK Mobile 常见问题与排障

## 入门指引

### Q：刚接触 TTADK Mobile，第一步是什么？

1. 安装 Claude Code（按平台参考对应安装文档）
2. 在工程最新分支根目录打开 Claude，输入 `/mcp` 确认 MCP 状态
3. 执行 `/adk:readiness` 了解仓库和模块的就绪度
4. 选择路径：
   - 有 PRD / 技术方案 / 本地需求文件 / 一句话需求：`/adk:sdd:spec <input>` 先生成 Spec 草稿
   - 有明确目标：`/adk:sdd:new <目标描述>` 直接启动工作流
   - 建设知识库：`kb-init-docs --analysis <path>`

### Q：如何用 TTADK Mobile 开始一个需求？

1. 执行 `/adk:readiness` 确认仓库和目标模块的就绪度。
2. **推荐**：先用 AI Technical Spec 模版对需求进行系统化描述。前期描述越清楚，需求设计生成质量越高。
3. 选择路径：
   - `/adk:sdd:spec <input>` → 补充完善 Spec → `/adk:sdd:new`
   - `/adk:sdd:new <功能描述>` 直接启动
4. 每个阶段仔细 Review & Approve。
5. 完成后：`/adk:sdd:save` → `/adk:commit`。

---

## 与 TTADK (Server/Web) 的关系

### Q：TTADK Mobile 和 TTADK (Server/Web) 有什么区别？

两者都是 SDD 工作流（Spec Driven Development），核心流程差异不大，都是 TT AI2D 项目组主推的 Spec Coding 方案。核心定位差异：
- **TTADK Core**：围绕前端、服务端建设
- **TTADK Mobile**：围绕客户端建设

差异细节：
- 整套流程围绕 TT Mobile 做定制，和客户端基建深度融合
- 客户端知识库搭建、管理和召回优化
- MCP 工具深度集成：D2C 流程集成、编译报错自动修复等
- 流程自动化：命令简化，自动流转
- Dashboard 模式：网页上做 Review，优化 Markdown 阅读和校准体验

---

## SDD 工作流问题

### Q：/adk:sdd:spec 和 /adk:sdd:new 的区别？

| 对比 | `/adk:sdd:spec` | `/adk:sdd:new` |
|------|-----------------|----------------|
| 输入 | 飞书/Lark 文档 URL、本地 Markdown/Text 文件或一句话需求 | 自然语言描述 / 本地文件 / 飞书 URL |
| 输出 | Spec 草稿（需人工补充） | 启动四阶段工作流 |
| 定位 | PRD → Spec 转换工具 | 工作流主入口 |

典型组合：先 `/adk:sdd:spec` 生成 Spec 草稿，人工补充后用 `/adk:sdd:new` 进入工作流。

### Q：SDD 各阶段有什么中间产物？

| 阶段 | 产出物 | 路径 |
|------|--------|------|
| Phase 1: Requirements | `requirements.md` | `.ttadk/.adk-mobile/specs/{spec-name}/` |
| Phase 2: Design | `design.md`、`explore.md` | 同上 |
| Phase 3: Tasks | `tasks.md` | 同上 |
| Phase 4: Implementation | 代码变更 | 项目代码目录 |

### Q：可以跳过某些阶段吗？

不可以。四个阶段（Requirements → Design → Tasks → Implementation）是强依赖关系，每个阶段需审批后才能进入下一阶段。

### Q：clarify 和 revert 什么区别？

- **clarify**：小更改用。发现需求/设计需要修改时，级联更新所有受影响的产物，确保一致性。
- **revert**：大改用。彻底清除状态（含已记录的实现生成代码）并回退到指定阶段重新开始。

### Q：/adk:sdd:clarify 可以执行多次吗？

可以。每次最多提出 5 个新问题并级联更新所有受影响的制品。可在任何阶段按需多次执行。确认没问题后告诉模型"continue/继续"，模型会自动流转工作流。

### Q：什么时候用 /adk:sdd:save？

通常在 Implementation 阶段全部任务完成后执行。Save 会将 Spec 中间产物保存至业务模块路径下（会自动推断也可指定），便于纳入 git 版本管理，随 MR 一起合入并沉淀。

### Q：中间产物在哪里？

在 `.ttadk/.adk-mobile/specs/{spec-name}/` 目录下。

---

## 中断与恢复

### Q：模型跑偏或者没有继续运行，怎么办？手动 interrupt 打断后会有问题吗？

放心，流程设计足够健壮，可随时打断。在不清理上下文的情况下，输入"继续/continue"会自动推进工作流。

### Q：模型降智幻觉严重，或者服务挂了，想重启 session 但担心工作状态丢失？

推荐 `/clear` + `/adk:sdd:continue {spec-name}` 清理上下文后继续当前需求。所有工作流状态持久化在 MCP 工作流目录中，不依赖对话上下文，重启 session 不会丢失进度。

---

## 知识库问题

### Q：kb-init-docs 生成的文档不满意怎么办？

可以自行修改文档内容（手动更改或和模型对话）。使用 `<nay-ai>...</nay-ai>` 标记保护修改后的内容不被后续 `kb-update-docs` 覆盖。

### Q：如何批量为多个模块生成文档？

使用 `kb-init-docs --analysis <top-level-path>`。如果仓库过大，难以决定在哪个路径下生成文件，`--analysis` 会对仓库做分析，自动选择多个路径做文件初始化。

### Q：知识更新怎么做？

手动调用 `kb-update-docs <path>` Skill 更新知识。在 Coding 任务结束后调用。

### Q：evals.json 放在哪里？

放在 `<doc-root>/docs/evals/evals.json`。

---

## 审批与 Review

### Q：Dashboard 模式和 CLI 模式怎么选？

在 `.ttadk/.adk-mobile/config.toml` 中配置 `approvalMode`：
- **dashboard**（默认）：Web 网页上 Review，体验更好，支持实时进度追踪和评论
- **cli**：命令行中 Review，适合不方便打开浏览器的场景

### Q：如何在 Review 中提修改意见？

- **Dashboard 模式**：选中对应内容 → 评论 → 请求修订
- **CLI 模式**：点击链接到 IDE 中查看 → 选中需要修改的内容 → 发送给 Claude → 提交修改意见

### Q：codeReview 开启后是什么效果？

开启 `codeReview = true` 后，每个 task 完成时 SDE 会暂停等待人工 Review 代码。适合复杂需求需要逐 task 把控代码质量的场景。

---

## D2C 集成

### Q：D2C 是什么？

Design-to-Code，从 Figma 设计稿自动生成代码。在 SDD 工作流的 Implementation 阶段，涉及 UI 的 task 会自动触发 D2C。

### Q：Android 和 iOS 的 D2C 有什么区别？

- **Android**：支持 Remote D2C（云端流水线）和 Local D2C。`config.toml` 中 `useRemoteD2C4Android` 控制是否开启 Remote D2C。
- **iOS**：使用 Local D2C MCP。

### Q：D2C 需要什么配置？

需要配置 Figma Key。具体参考各平台的 D2C 配置文档。在 Spec 的 UI/UX Structure 部分贴上 Figma node 链接，不同 UI 区块尽量贴独立的 node 链接。

---

## 业务定制

### Q：业务如何做定制和拓展？

- **插件化**：基于 TTADK 插件系统，业务线定制 command/skills/mcp 的隔离和插拔。
- **核心流程定制**（默认目录位于 `.ttadk/.adk-mobile/` 下；高级场景可通过 adk-mobile MCP 启动参数调整业务定制目录）：
  - `user-templates/`：中间产物模版的定制
  - `user-knowledge/`：业务知识库加载时机定制
  - `user-hooks/`：在不同阶段（requirements、design、tasks、implementation）开始和结束节点插入执行业务流程

---

## Readiness 问题

### Q：readiness 评估有哪些维度？

**仓库级**（5 个维度）：
1. Context Engineering：AI 指令文件、TTADK 配置、MCP 配置、知识库覆盖
2. Build & Dependencies：构建系统、依赖管理、CI/CD
3. Style & Validation：Lint 配置、格式化、预提交钩子
4. Security & Governance：gitignore、密钥管理、CODEOWNERS
5. SDD Readiness：TTADK 初始化、MCP 配置、Spec 历史

**模块级**（3 个维度）：
1. Module Documentation：CLAUDE.md、docs/ 存在性和质量
2. Module Testing：测试覆盖率、测试质量、evals 定义
3. Module Code Organization：接口清晰度、文件粒度、内部分层

### Q：如何提升 readiness 评分？

- 无 CLAUDE.md → `kb-init-docs <module-path>`
- 文档过时 → `kb-update-docs <module-path>`
- 无评测用例 → `kb-evals-creator`
- 校验文档 → `kb-docs-validator`

---

## MCP 连接问题

### Q：怎么检测 MCP 是否正常运行？

运行 `/adk:readiness` 会自动执行 MCP 健康检测。也可以手动检测：

检测方式取决于客户端：

**Claude Code：** 调用 `ListMcpResourcesTool`，参数 `server` 设为 `"adk-mobile"`。响应中包含 `"Available servers: xxx, yyy, zzz"`，即所有可用 server 列表。用**包含匹配**核对（server 名可能带前缀，如 `plugin:common-plugin:core-ai`，包含 `core-ai` 即算匹配）。

**Cursor：** 对每个必备 server，调用 `CallMcpTool(server="<name>", toolName="_ping")`。返回正常结果或 "tool not found" = server 在运行；返回 "server not found" 或连接超时 = 未启动。

必备 server 列表：

**Android 必备 MCP：**

| # | Server | 用途 |
|---|--------|------|
| 1 | `adk-mobile` | SDD 工作流引擎 |
| 2 | `core-ai` | IDE 上下文（需 Android Studio 运行） |
| 3 | `build-ai` | 编译信息与错误修复 |
| 4 | `d2c4a` | Design-to-Code |

**iOS 必备 MCP：**

| # | Server | 用途 |
|---|--------|------|
| 1 | `adk-mobile` | SDD 工作流引擎 |
| 2 | `iOS_context` | iOS 项目上下文 |
| 3 | `titkok_arch_mcp` | 架构规范 |
| 4 | `tiktok_d2c_mcp` | Design-to-Code |
| 5 | `UI_Wiki` | UI 组件知识库 |

### Q：MCP 连接失败怎么办？

可能是 npm 包的权限或缓存问题。可以让 Claude Code 自行诊断并修复：

1. 用 `--debug` 启动 Claude Code，终端会显示 debug 日志路径（如 `~/.claude/debug/<uuid>.txt`）
2. 底部状态栏会显示 `X MCP server failed`
3. 直接对话询问："XX MCP 为什么启动失败了？" — Claude Code 会读取 debug 日志，定位错误原因并尝试自动修复（如清理 npm 缓存、重新安装依赖等）

### Q：推荐的 MCP 状态是什么？

确保平台必备 MCP 全部正常运行（Android 4 个，iOS 5 个）。非必备 MCP 不启用，会增加 context 占用影响性能。

---

## 工具支持

### Q：Cursor 能用吗？

支持。使用 `ttadk init` 初始化时选择 Cursor 即可。整套工作流基于 MCP 实现，支持任何支持 MCP 的工具。

### Q：Trae 能用吗？

目前未支持。

### Q：飞书 CLI 怎么安装？

飞书 CLI（lark-cli）用于让 AI Agent 直接操作飞书资源（读取飞书文档、PRD 等）。`/adk:sdd:spec <input>` 使用飞书/Lark URL 输入时需要。

安装步骤：

```bash
npm install -g @larksuite/cli
npx skills add https://github.com/larksuite/cli -y -g
lark-cli config init --new
```

配置完成后**重启 IDE 会话**以加载 skills。

可选：以个人身份操作飞书（访问个人日历、消息、文档等）：

```bash
lark-cli auth login
```

完整文档：[飞书 CLI 能力介绍与最佳实践](https://bytedance.larkoffice.com/docx/WnHkdJQM6oGpQFxm9i7ckVdenSh)

---

## 多仓库/子模块

### Q：子模块的 commit 顺序是什么？

`/adk:commit` 自动处理：先逐个 commit 有变更的子模块，最后 commit 主仓库（包含子模块引用更新）。顺序必须是先子模块后主仓库。

---

## AI 代码贡献率

### Q：使用 TTADK Mobile 的代码贡献会被统计吗？

使用推荐的安装方式启动 Claude Code，默认已支持 AI 代码贡献度统计。同时正在支持 TTADK Mobile 维度下的代码贡献统计。

统计时机为 commit 代码被 MR 合入（非仅 commit），更新频率约 T+2。

---

## iOS 特有问题

### Q：iOS 的工作目录在哪？

工作目录通过 `.mcp.json` 中 `--workflow-dir` 参数配置，统一为 `.ttadk/.adk-mobile`。

### Q：iOS 本地多个仓库同时修改代码，路径寻找异常？

Xcode 的 Context Sharing 可能影响模型的路径寻找。可尝试关闭：

```bash
export TIKTOK_CC_DISABLE_XCODE_CONTEXT=1
```

### Q：iOS 如何让 plugin 自动更新？

用 `plugin` 命令唤起，`update marketplaces` 后可看到 plugin 最新改动，或使用 `auto-update` 自动更新。
