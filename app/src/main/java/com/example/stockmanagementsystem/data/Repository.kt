package com.example.stockmanagementsystem.data

import android.content.ContentValues
import android.content.Context
import android.database.Cursor
import android.database.sqlite.SQLiteDatabase

/** 单选属性选项编码：内部以 | 分隔存储；用户输入支持逗号/顿号/竖线分隔 */
object AttrOptions {
    fun encode(options: List<String>): String =
        options.map { it.trim() }.filter { it.isNotEmpty() }.joinToString("|")

    fun decode(raw: String): List<String> =
        raw.split('|').map { it.trim() }.filter { it.isNotEmpty() }

    fun parseUserInput(raw: String): List<String> =
        raw.split(',', '，', '、', '|').map { it.trim() }.filter { it.isNotEmpty() }
}

class Repository private constructor(context: Context) {

    private val dbHelper = DbHelper(context.applicationContext)
    val imageStore = ImageStore(context.applicationContext)

    private val db: SQLiteDatabase get() = dbHelper.writableDatabase

    // ---------------- 仓库 ----------------

    fun listWarehouses(): List<Warehouse> = db.rawQuery(
        "SELECT id, name, remark, created_at FROM warehouse ORDER BY id", null
    ).use { c -> buildList { while (c.moveToNext()) add(c.toWarehouse()) } }

    fun getWarehouse(id: Long): Warehouse? = db.rawQuery(
        "SELECT id, name, remark, created_at FROM warehouse WHERE id=?", arrayOf(id.toString())
    ).use { c -> if (c.moveToFirst()) c.toWarehouse() else null }

    fun createWarehouse(name: String, remark: String): Long = db.insertOrThrow(
        "warehouse", null,
        ContentValues().apply {
            put("name", name)
            put("remark", remark)
            put("created_at", System.currentTimeMillis())
        }
    )

    fun updateWarehouse(id: Long, name: String, remark: String) {
        db.update(
            "warehouse",
            ContentValues().apply {
                put("name", name)
                put("remark", remark)
            },
            "id=?", arrayOf(id.toString())
        )
    }

    fun deleteWarehouse(id: Long) {
        db.beginTransaction()
        try {
            itemIdsOfWarehouse(id).forEach { imageStore.deleteItemImages(it) }
            db.delete("warehouse", "id=?", arrayOf(id.toString()))
            db.setTransactionSuccessful()
        } finally {
            db.endTransaction()
        }
    }

    private fun itemIdsOfWarehouse(warehouseId: Long): List<Long> =
        db.rawQuery(
            """SELECT i.id FROM item i
               JOIN category c ON i.category_id = c.id
               WHERE c.warehouse_id=?""",
            arrayOf(warehouseId.toString())
        ).use { c -> buildList { while (c.moveToNext()) add(c.getLong(0)) } }

    // ---------------- 类目 ----------------

    fun listCategories(warehouseId: Long): List<Category> = db.rawQuery(
        """SELECT c.id, c.warehouse_id, c.name,
                  (SELECT COUNT(*) FROM item i WHERE i.category_id = c.id) AS item_count
           FROM category c WHERE c.warehouse_id=? ORDER BY c.id""",
        arrayOf(warehouseId.toString())
    ).use { c ->
        buildList {
            while (c.moveToNext()) {
                add(Category(c.getLong(0), c.getLong(1), c.getString(2), c.getInt(3)))
            }
        }
    }

    fun createCategory(warehouseId: Long, name: String): Long = db.insertOrThrow(
        "category", null,
        ContentValues().apply {
            put("warehouse_id", warehouseId)
            put("name", name)
            put("created_at", System.currentTimeMillis())
        }
    )

    fun renameCategory(id: Long, name: String) {
        db.update("category", ContentValues().apply { put("name", name) }, "id=?",
            arrayOf(id.toString()))
    }

    fun deleteCategory(id: Long) {
        db.beginTransaction()
        try {
            db.rawQuery("SELECT id FROM item WHERE category_id=?", arrayOf(id.toString()))
                .use { c -> while (c.moveToNext()) imageStore.deleteItemImages(c.getLong(0)) }
            db.delete("category", "id=?", arrayOf(id.toString()))
            db.setTransactionSuccessful()
        } finally {
            db.endTransaction()
        }
    }

    // ---------------- 物品 ----------------

    fun listItems(categoryId: Long): List<ItemSummary> = db.rawQuery(
        """SELECT i.id, i.name, i.unit, i.quantity,
                  (SELECT group_concat(ad.name || ': ' || av.value, '  ')
                     FROM attribute_value av
                     JOIN attribute_def ad ON ad.id = av.attribute_def_id
                    WHERE av.item_id = i.id AND ad.type != 'IMAGE' AND av.value <> ''
                    ORDER BY ad.sort_order) AS summary,
                  (SELECT av2.value
                     FROM attribute_value av2
                     JOIN attribute_def ad2 ON ad2.id = av2.attribute_def_id
                    WHERE av2.item_id = i.id AND ad2.type = 'IMAGE' AND av2.value <> ''
                    ORDER BY ad2.sort_order LIMIT 1) AS image
           FROM item i WHERE i.category_id=? ORDER BY i.id DESC""",
        arrayOf(categoryId.toString())
    ).use { c ->
        buildList {
            while (c.moveToNext()) {
                add(
                    ItemSummary(
                        id = c.getLong(0),
                        name = c.getString(1),
                        unit = c.getString(2).orEmpty(),
                        quantity = c.getDouble(3),
                        attrSummary = c.getString(4).orEmpty(),
                        firstImage = c.getString(5).takeIf { !it.isNullOrEmpty() },
                    )
                )
            }
        }
    }

    fun getItemDetail(itemId: Long): ItemDetail? {
        val item = getItem(itemId) ?: return null
        val defs = listAttrDefs(item.categoryId)
        val values = HashMap<Long, String>()
        db.rawQuery(
            "SELECT attribute_def_id, value FROM attribute_value WHERE item_id=?",
            arrayOf(itemId.toString())
        ).use { c -> while (c.moveToNext()) values[c.getLong(0)] = c.getString(1) }
        return ItemDetail(item, defs.map { AttrWithValue(it, values[it.id].orEmpty()) })
    }

    fun getItem(itemId: Long): Item? = db.rawQuery(
        "SELECT id, category_id, name, unit, quantity, created_at FROM item WHERE id=?",
        arrayOf(itemId.toString())
    ).use { c -> if (c.moveToFirst()) c.toItem() else null }

    /** 类目级属性定义（类目下所有物品共用） */
    fun listAttrDefs(categoryId: Long): List<AttributeDef> = db.rawQuery(
        "SELECT id, category_id, name, type, options, sort_order FROM attribute_def WHERE category_id=? ORDER BY sort_order, id",
        arrayOf(categoryId.toString())
    ).use { c -> buildList { while (c.moveToNext()) add(c.toAttrDef()) } }

    /**
     * 保存类目属性定义：增删改。删除定义或图片类型变更时，
     * 该类目下所有物品对应的属性值与图片文件一并清除。
     */
    fun saveCategoryAttrDefs(categoryId: Long, drafts: List<AttrDefDraft>) {
        db.beginTransaction()
        try {
            val oldDefs = listAttrDefs(categoryId)
            val keptDefIds = drafts.mapNotNull { it.defId }.toHashSet()
            // 删除被移除的定义（值行随外键级联删除，图片文件手动清理）
            oldDefs.filter { it.id !in keptDefIds }.forEach { def ->
                purgeDefValues(categoryId, def.id, purgeImages = def.type == AttrType.IMAGE)
                db.delete("attribute_def", "id=?", arrayOf(def.id.toString()))
            }
            drafts.forEachIndexed { index, draft ->
                val oldDef = oldDefs.firstOrNull { it.id == draft.defId }
                if (oldDef == null) {
                    db.insertOrThrow(
                        "attribute_def", null,
                        ContentValues().apply {
                            put("category_id", categoryId)
                            put("name", draft.name)
                            put("type", draft.type.wire)
                            put("options", AttrOptions.encode(draft.options))
                            put("sort_order", index)
                        }
                    )
                } else {
                    if (oldDef.type != draft.type) {
                        // 类型变化：清空该类目下所有物品的该属性值
                        purgeDefValues(categoryId, oldDef.id, purgeImages = oldDef.type == AttrType.IMAGE)
                    }
                    db.update(
                        "attribute_def",
                        ContentValues().apply {
                            put("name", draft.name)
                            put("type", draft.type.wire)
                            put("options", AttrOptions.encode(draft.options))
                            put("sort_order", index)
                        },
                        "id=?", arrayOf(oldDef.id.toString())
                    )
                }
            }
            db.setTransactionSuccessful()
        } finally {
            db.endTransaction()
        }
    }

    private fun purgeDefValues(categoryId: Long, defId: Long, purgeImages: Boolean) {
        if (purgeImages) {
            itemIdsOfCategory(categoryId).forEach { imageStore.deleteAttrDir(it, defId) }
        }
        db.delete("attribute_value", "attribute_def_id=?", arrayOf(defId.toString()))
    }

    private fun itemIdsOfCategory(categoryId: Long): List<Long> =
        db.rawQuery("SELECT id FROM item WHERE category_id=?", arrayOf(categoryId.toString()))
            .use { c -> buildList { while (c.moveToNext()) add(c.getLong(0)) } }

    /**
     * 保存物品：itemId 为 null 时新建。只写入属性值（属性定义由类目统一管理），
     * 暂存图转正入库，被移除/替换的图片文件同步清理。
     */
    fun saveItem(
        itemId: Long?,
        categoryId: Long,
        name: String,
        unit: String,
        values: List<AttrValueInput>,
    ): Long {
        db.beginTransaction()
        try {
            val id = itemId ?: db.insertOrThrow(
                "item", null,
                ContentValues().apply {
                    put("category_id", categoryId)
                    put("name", name)
                    put("unit", unit)
                    put("quantity", 0.0)
                    put("created_at", System.currentTimeMillis())
                }
            )
            if (itemId != null) {
                db.update(
                    "item",
                    ContentValues().apply {
                        put("name", name)
                        put("unit", unit)
                    },
                    "id=?", arrayOf(itemId.toString())
                )
            }

            val defTypes = listAttrDefs(categoryId).associate { it.id to it.type }
            values.forEach { v ->
                when (defTypes[v.defId]) {
                    AttrType.IMAGE -> saveImageValue(id, v)
                    AttrType.TEXT, AttrType.NUMBER, AttrType.CHOICE -> {
                        val s = v.value.trim()
                        if (s.isEmpty()) deleteValue(v.defId, id) else upsertValue(v.defId, id, s)
                    }
                    null -> Unit // 定义已被删除，忽略
                }
            }
            db.setTransactionSuccessful()
            return id
        } finally {
            db.endTransaction()
        }
    }

    private fun saveImageValue(itemId: Long, input: AttrValueInput) {
        when {
            input.stagedImage != null -> {
                imageStore.deleteAttrDir(itemId, input.defId)
                val rel = imageStore.commit(itemId, input.defId, input.stagedImage)
                if (rel != null) upsertValue(input.defId, itemId, rel) else deleteValue(input.defId, itemId)
            }
            input.removeImage -> {
                imageStore.deleteAttrDir(itemId, input.defId)
                deleteValue(input.defId, itemId)
            }
            else -> Unit // 保留原图片
        }
    }

    private fun upsertValue(defId: Long, itemId: Long, value: String) {
        db.insertWithOnConflict(
            "attribute_value", null,
            ContentValues().apply {
                put("attribute_def_id", defId)
                put("item_id", itemId)
                put("value", value)
            },
            SQLiteDatabase.CONFLICT_REPLACE
        )
    }

    private fun deleteValue(defId: Long, itemId: Long) {
        db.delete(
            "attribute_value", "attribute_def_id=? AND item_id=?",
            arrayOf(defId.toString(), itemId.toString())
        )
    }

    fun deleteItem(itemId: Long) {
        db.beginTransaction()
        try {
            db.delete("item", "id=?", arrayOf(itemId.toString()))
            imageStore.deleteItemImages(itemId)
            db.setTransactionSuccessful()
        } finally {
            db.endTransaction()
        }
    }

    // ---------------- 出入库 ----------------

    /** 事务化出入库：更新库存并写入流水。出库超量时抛 [InsufficientStockException]。 */
    fun applyStock(itemId: Long, type: StockType, quantity: Double, note: String): StockRecord {
        require(quantity > 0) { "数量必须大于 0" }
        db.beginTransaction()
        try {
            val row = db.rawQuery(
                """SELECT i.name, i.unit, i.quantity, c.warehouse_id
                   FROM item i JOIN category c ON i.category_id = c.id
                   WHERE i.id=?""",
                arrayOf(itemId.toString())
            ).use { c ->
                if (!c.moveToFirst()) error("物品不存在")
                StockRow(c.getString(0), c.getString(1).orEmpty(), c.getDouble(2), c.getLong(3))
            }
            val before = row.quantity
            val after = if (type == StockType.IN) before + quantity else before - quantity
            if (type == StockType.OUT && after < 0.0) {
                throw InsufficientStockException(before, quantity)
            }
            db.update(
                "item", ContentValues().apply { put("quantity", after) }, "id=?",
                arrayOf(itemId.toString())
            )
            val now = System.currentTimeMillis()
            val recordId = db.insertOrThrow(
                "stock_record", null,
                ContentValues().apply {
                    put("warehouse_id", row.warehouseId)
                    put("item_id", itemId)
                    put("item_name", row.name)
                    put("unit", row.unit)
                    put("type", type.wire)
                    put("quantity", quantity)
                    put("before_qty", before)
                    put("after_qty", after)
                    put("note", note)
                    put("created_at", now)
                }
            )
            db.setTransactionSuccessful()
            return StockRecord(recordId, row.warehouseId, itemId, row.name, row.unit, type, quantity, before, after, note, now)
        } finally {
            db.endTransaction()
        }
    }

    private data class StockRow(
        val name: String,
        val unit: String,
        val quantity: Double,
        val warehouseId: Long,
    )

    fun listRecordsForWarehouse(warehouseId: Long, limit: Int = 500): List<StockRecord> =
        db.rawQuery(
            "SELECT * FROM stock_record WHERE warehouse_id=? ORDER BY id DESC LIMIT ?",
            arrayOf(warehouseId.toString(), limit.toString())
        ).use { c -> buildList { while (c.moveToNext()) add(c.toRecord()) } }

    fun listRecordsForItem(itemId: Long, limit: Int = 100): List<StockRecord> =
        db.rawQuery(
            "SELECT * FROM stock_record WHERE item_id=? ORDER BY id DESC LIMIT ?",
            arrayOf(itemId.toString(), limit.toString())
        ).use { c -> buildList { while (c.moveToNext()) add(c.toRecord()) } }

    // ---------------- 游标映射 ----------------

    private fun Cursor.toWarehouse() =
        Warehouse(getLong(0), getString(1), getString(2), getLong(3))

    private fun Cursor.toItem() =
        Item(getLong(0), getLong(1), getString(2), getString(3).orEmpty(), getDouble(4), getLong(5))

    private fun Cursor.toAttrDef() = AttributeDef(
        id = getLong(0),
        categoryId = getLong(1),
        name = getString(2),
        type = AttrType.of(getString(3)),
        options = AttrOptions.decode(getString(4).orEmpty()),
        sortOrder = getInt(5),
    )

    private fun Cursor.toRecord() = StockRecord(
        id = getLong(getColumnIndexOrThrow("id")),
        warehouseId = getLong(getColumnIndexOrThrow("warehouse_id")),
        itemId = getLong(getColumnIndexOrThrow("item_id")),
        itemName = getString(getColumnIndexOrThrow("item_name")),
        unit = getString(getColumnIndexOrThrow("unit")).orEmpty(),
        type = StockType.of(getString(getColumnIndexOrThrow("type"))),
        quantity = getDouble(getColumnIndexOrThrow("quantity")),
        beforeQty = getDouble(getColumnIndexOrThrow("before_qty")),
        afterQty = getDouble(getColumnIndexOrThrow("after_qty")),
        note = getString(getColumnIndexOrThrow("note")).orEmpty(),
        createdAt = getLong(getColumnIndexOrThrow("created_at")),
    )

    companion object {
        @Volatile private var instance: Repository? = null

        fun get(context: Context): Repository =
            instance ?: synchronized(this) {
                instance ?: Repository(context).also { instance = it }
            }
    }
}
