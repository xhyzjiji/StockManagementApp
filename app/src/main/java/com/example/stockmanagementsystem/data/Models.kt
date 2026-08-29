package com.example.stockmanagementsystem.data

import java.io.File

/** 属性类型：文本 / 数字 / 单选 / 多选标签 / 参考图 */
enum class AttrType(val wire: String) {
    TEXT("TEXT"),
    NUMBER("NUMBER"),
    CHOICE("CHOICE"),
    TAGS("TAGS"),
    IMAGE("IMAGE");

    companion object {
        fun of(wire: String?): AttrType = entries.firstOrNull { it.wire == wire } ?: TEXT
    }
}

enum class StockType(val wire: String) {
    IN("IN"),
    OUT("OUT");

    companion object {
        fun of(wire: String?): StockType = if (wire == OUT.wire) OUT else IN
    }
}

data class Warehouse(
    val id: Long,
    val name: String,
    val remark: String,
    val createdAt: Long,
)

/** 回收站行：仓库或物品 */
data class DeletedRow(
    val id: Long,
    val title: String,
    val subtitle: String,
    val deletedAt: Long,
)

data class Category(
    val id: Long,
    val warehouseId: Long,
    val name: String,
    val itemCount: Int,
)

data class Item(
    val id: Long,
    val categoryId: Long,
    val name: String,
    /** 计量单位：入库/出库/库存展示用，如 件、米、㎡、公斤 */
    val unit: String,
    val quantity: Double,
    /** 平均单价（元，两位小数），随入库总价加权、出库折算维护 */
    val avgPrice: Double,
    /** 剩余总价（元，两位小数） */
    val totalValue: Double,
    /** 当前这批库存的入库起点（在库天数由此计算）；无库存 / 出清后为 null */
    val stockSince: Long?,
    val createdAt: Long,
)

/** 物品列表摘要：附带属性摘要与首张参考图 */
data class ItemSummary(
    val id: Long,
    val categoryId: Long,
    val name: String,
    val unit: String,
    val quantity: Double,
    /** 平均单价（元/计量单位，两位小数） */
    val avgPrice: Double,
    /** 剩余总价（元）；列表快捷入库时用它判断老库存是否已定价 */
    val totalValue: Double,
    /** 当前这批库存的入库起点；无库存为 null */
    val stockSince: Long?,
    /** 标签（TAGS 类型属性的多选值，已拆好） */
    val tags: List<String>,
    val attrSummary: String,
    val firstImage: String?,
    val createdAt: Long,
)

/** 属性定义，归属于某个仓库（仓库级自定义属性，仓库下所有物品共用） */
data class AttributeDef(
    val id: Long,
    val warehouseId: Long,
    val name: String,
    val type: AttrType,
    /** CHOICE 类型的候选值，已按分隔符拆分 */
    val options: List<String>,
    val sortOrder: Int,
)

/** 物品详情页用的属性+值合体 */
data class AttrWithValue(
    val def: AttributeDef,
    val value: String,
)

data class ItemDetail(
    val item: Item,
    val attrs: List<AttrWithValue>,
)

data class StockRecord(
    val id: Long,
    val warehouseId: Long,
    val itemId: Long,
    val itemName: String,
    /** 发生出入库时物品的单位快照 */
    val unit: String,
    val type: StockType,
    val quantity: Double,
    val beforeQty: Double,
    val afterQty: Double,
    /** 入库：本次入库总价（必填）；出库：按当时均价折算的金额；旧数据为 null */
    val totalPrice: Double?,
    val note: String,
    val createdAt: Long,
)

class InsufficientStockException(
    val available: Double,
    val requested: Double,
) : Exception("库存不足：当前 $available，需要 $requested")

/** 一次入库的单价点：入库时间 + 当批单价（总价 ÷ 数量） */
data class PricePoint(
    val time: Long,
    val price: Double,
)

/** 某物品在某标签字段下的标签值（统计页聚合用；tags 已按分隔符拆分） */
data class TagValue(
    val defId: Long,
    val itemId: Long,
    val tags: List<String>,
)

/** 属性定义草稿（类目属性设置页提交用） */
data class AttrDefDraft(
    val defId: Long?,          // null 表示新增
    val name: String,
    val type: AttrType,
    val options: List<String>,
)

/** 物品属性值输入（物品编辑页提交用）：只有值，没有定义 */
data class AttrValueInput(
    val defId: Long,
    val value: String,         // 文本/数字/单选的值
    val stagedImage: File?,    // IMAGE 类型新拍/新选的暂存文件
    val removeImage: Boolean,  // IMAGE 类型要求清除已有图片
)
