package com.example.stockmanagementsystem.data

import java.io.File

/** 属性类型：文本 / 数字 / 单选 / 参考图 */
enum class AttrType(val wire: String) {
    TEXT("TEXT"),
    NUMBER("NUMBER"),
    CHOICE("CHOICE"),
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
    val quantity: Double,
    val createdAt: Long,
)

/** 物品列表摘要：附带属性摘要与首张参考图 */
data class ItemSummary(
    val id: Long,
    val name: String,
    val quantity: Double,
    val attrSummary: String,
    val firstImage: String?,
)

/** 属性定义，归属于某个类目（类目级自定义属性，类目下所有物品共用） */
data class AttributeDef(
    val id: Long,
    val categoryId: Long,
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
    val type: StockType,
    val quantity: Double,
    val beforeQty: Double,
    val afterQty: Double,
    val note: String,
    val createdAt: Long,
)

class InsufficientStockException(
    val available: Double,
    val requested: Double,
) : Exception("库存不足：当前 $available，需要 $requested")

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
