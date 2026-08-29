# 库存管理系统（Android）

本仓库是一个本地化的库存管理 App：自定义仓库 → 类目 → 物品，物品属性完全由用户自由定义（文本 / 数字 / 单选 / 参考图），支持入库、出库与流水追溯。所有数据保存在 App 私有目录，无需联网与特殊权限。

## 功能

- **仓库管理**：首次启动引导创建仓库；支持多仓库、重命名、删除（级联清理）。
- **类目管理**：仓库下自定义类目（如：饮料、零食），展示物品数量。
- **类目与自定义属性**：类目下创建物品（如：可乐）；属性在类目级统一定义，类目下所有物品共用同一套属性、各自填值：
  - 文本（如：供应商）、数字（如：单价、克数）、单选（如：有糖/无糖）、参考图（拍照或从相册选择）。
- **出入库**：物品详情页入库 / 出库，入库必填本次总价（最多两位小数），物品维护平均单价与剩余总价；出库超量拦截；每次操作记录流水（操作前后库存、金额、时间、备注）。
- **老库存定价**：旧数据物品（有库存但无价格）首次入库时可选计价方式：整批按本次单价 / 本次总价摊薄 / 手动修正老库存总价。
- **流水追溯**：仓库级流水（主页菜单）与物品级流水（详情页）。
- **物品总览**：支持三种视图：单行列表（默认）与双列网格均展示库存量、平均单价（元/计量单位）、在库天数（自本批入库起点起算，出清后重新计时）；三列缩略图仅展示图、名称与标签；支持按在库天数排序。
- **图片本地管理**：参考图存于 App 私有目录，数据库只保存相对路径链接。

## 技术栈与架构

- Kotlin + Android Views（ViewBinding）、Material 3、RecyclerView。
- 数据层：手写 `SQLiteOpenHelper`（`data/DbHelper.kt`）+ 门面 `data/Repository.kt`；单线程执行器串行化读写（`util/Bg.kt`）。
- 图片层：`data/ImageStore.kt` 负责重采样压缩（最长边 1600、JPEG 85%）、EXIF 转正、目录管理与级联清理。

## 数据库 Schema（stock.db）

| 表 | 说明 |
| --- | --- |
| `warehouse` | 仓库（名称、备注） |
| `category` | 类目，归属仓库，级联删除 |
| `item` | 物品，归属类目；`quantity` 为当前库存（出入库实时维护）；`avg_price`/`total_value` 为平均单价与剩余总价（入库按总价加权、出库按均价折算，保留两位小数）；`stock_since` 为当前这批库存的入库起点（出清后置空） |
| `attribute_def` | 属性定义，归属类目（该类目下所有物品共用）；`type` ∈ TEXT/NUMBER/CHOICE/IMAGE；`options` 为单选候选值（\| 分隔） |
| `attribute_value` | 属性值（主键 = 定义 + 物品）；IMAGE 类型存相对图片路径 |
| `stock_record` | 出入库流水（物品名快照、数量、操作前/后库存、`total_price` 本次入库总价/出库折算金额、备注、时间）；不随物品删除而消失 |

## 图片目录结构（files/images/）

```
images/
├── tmp/{uuid}.jpg                  # 拍照 / 相册暂存，保存物品后转正，启动时清理
└── items/{itemId}/{defId}/{uuid}.jpg   # 物品属性参考图；随物品/属性删除级联清理
```

拍照通过 `TakePicture` 合约 + `FileProvider` 直出到暂存区，无需 CAMERA 与存储权限；相册走系统照片选择器（Photo Picker），无需权限。

## 页面结构

```
WarehouseListActivity（选择/创建仓库）
  └── MainActivity（类目列表、仓库菜单：出入库记录 / 仓库信息）
        ├── RecordListActivity（仓库流水）
        └── ItemListActivity（类目下物品列表）
              ├── CategoryAttrsActivity（类目属性设置：定义该物品的同类共享属性）
              ├── ItemEditActivity（物品新建/编辑：填写类目属性值，参考图拍照/相册）
              └── ItemDetailActivity（属性展示、入库/出库、物品流水）
```

## 构建与测试

```bash
./gradlew :app:assembleDebug        # 产出 app/build/outputs/apk/debug/app-debug.apk
./gradlew :app:testDebugUnitTest    # 单元测试（数量运算、选项编码等）
```
