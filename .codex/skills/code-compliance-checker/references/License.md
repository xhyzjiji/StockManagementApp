# License（开源许可证）

## 1. 执行标准

-   **核心原则**：
    -   **不可用**：不允许对外使用的许可证（如 `LicenseRef-LICENSE-INTERNAL`）和限制型许可证（如 `GPL`, `AGPL`）。
    -   **可用但需遵循义务**：弱限制型许可证（如 `LGPL`）和声明型许可证（如 `MIT`, `Apache-2.0`, `BSD`）可用，但必须严格遵循其声明和使用义务。
-   **声明要求**：
    -   任何引用的外部开源组件，必须保留其原始的版权（Copyright）和许可证（License）声明。
    -   未声明许可证（`No license found`）或许可证类型未知（`Unknown License`）的开源代码不可用，必须替换或由法务评估。
-   **修改声明**：如果对引用的开源文件进行了修改，必须在保留原始头部声明的基础上，额外添加一行声明：`This file may have been modified by ByteDance Ltd. and/or its affiliates.`

## 2. 处理方法

### 2.1 按检测类型处理

许可证合规扫描主要分为三种类型，需区别处理：

-   **Dependency (依赖检测)**：
    -   检查项目依赖的第三方库。高风险（如 `GPL`/`AGPL`）必须替换或重写；中风险（如 `LGPL`）需确保动态链接并满足相应开源义务。
    -   在 BlackDuck 等工具中校准组件版本与许可证信息，可忽略不进入最终产物的开发工具类依赖（如 `scope` 为 `test`, `dev`, `provided` 的依赖）。
-   **Codeprint (代码印记检测)**：
    -   以文件或文件夹为粒度进行代码相似度检测。处理方式同 Dependency，需定位到具体的文件或目录，确认其来源与许可证，并进行相应处理。
-   **Snippet (代码片段检测)**：
    -   当代码中包含超过 6 行与开源组件相似的代码片段时触发。
    -   需在文件头部注释中补充原始文件来源、Copyright 和 License 信息。格式如下：
        ```
        // Original Files: [文件名/组件名] ([来源链接])
        // Copyright [年份] [作者]
        // SPDX-License-Identifier: [许可证简写]
        ```
    -   SPDX 简写可从 [spdx.org/licenses/](https://spdx.org/licenses/) 查询。

### 2.2 声明方式示例

#### 方案一：文件头部声明 + 根目录 LICENSE 文件

1.  **文件头部**：在引用了外部代码的文件头部添加简要声明，指向根目录的 `LICENSE` 文件。
    ```c
    /*
     * Copyright (c) 2022 The Example Project authors. All Rights Reserved.
     *
     * Use of this source code is governed by a MIT-style license
     * that can be found in the LICENSE file in the root of the source
     * tree.
     */
    ```
2.  **根目录 `LICENSE` 文件**：在项目根目录的 `LICENSE` 或类似文件中，详细列出所有引用的第三方代码路径及其完整的许可证文本。
    ```
    This source tree contains third party source code which is governed by third party licenses. Paths to the files and associated licenses are collected here.

    ------------------------------------------------------------------------------
    Files:
    path/to/your/file.cpp

    License:
    /*
     * Copyright(c) 2023 Example Author
     * ... (完整的许可证文本) ...
     */
    ------------------------------------------------------------------------------
    ```

#### 方案二：在文件头部完整声明

直接在引用了外部代码的文件头部，完整地粘贴原始的 Copyright 和 License 文本。

```java
/*
 * Copyright 2018 The Android Open Source Project
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 *
 * This file may have been modified by ByteDance Ltd. and/or its affiliates.
 */
```

## 3. 常见问题与误报处理

-   **Snippet 误报**：Snippet 检测存在一定的误报率。如果命中的代码只是结构相似但逻辑不同，或是业界通用的标准写法，可以判定为误报，并联系合规运营同学进行处理。
-   **Unknown License**：对于被标记为 `Unknown License` 的组件，需要研发人员自行通过搜索引擎等方式查找其真实许可证。如果确实找不到，则该组件不可用，必须替换或重写。

## 4. 工具与链接

-   **SPDX 许可证列表**：[https://spdx.org/licenses/](https://spdx.org/licenses/)
-   **字节代码版权信息添加指南**：[https://bytedance.feishu.cn/docs/doccnM9EMnVg07mEqBqtmxKfuGc](https://bytedance.feishu.cn/docs/doccnM9EMnVg07mEqBqtmxKfuGc)

## 5. 细则与示例：许可证类别与合规义务

| 许可证类别 | 合规义务要点 | 常见许可证 |
| :--- | :--- | :--- |
| **限制型许可证 (不可用)** | 传染性强，要求衍生作品也以相同许可证开源。 | `GPL`, `AGPL` |
| **弱限制型许可证 (可用)** | 允许动态链接，但修改部分需以相同或兼容许可证开源。 | `LGPL`, `MPL 2.0`, `CDDL` |
| **声明型许可证 (可用)** | 限制最少，只需在代码中保留原始版权和许可证声明。 | `MIT`, `Apache-2.0`, `BSD` |
| **不允许对外使用的许可证 (不可用)** | 仅限内部使用，禁止在任何对外发布的产物中使用。 | `LicenseRef-LICENSE-INTERNAL` |

---

