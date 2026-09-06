package com.example.stockmanagementsystem.data

import android.content.ContentValues
import android.database.sqlite.SQLiteDatabase
import org.json.JSONArray
import org.json.JSONObject
import java.io.BufferedInputStream
import java.io.BufferedOutputStream
import java.io.ByteArrayOutputStream
import java.io.InputStream
import java.io.OutputStream
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.zip.ZipEntry
import java.util.zip.ZipInputStream
import java.util.zip.ZipOutputStream

/** 导出文件名与冲突改名的纯函数工具（可单测，不依赖 Android 类） */
object TransferNaming {

    /** 同名冲突时自动改名：base → "base (2)" → "base (3)" …，取第一个未被占用的名字 */
    fun uniqueName(base: String, taken: Set<String>): String {
        if (base !in taken) return base
        var index = 2
        while ("$base ($index)" in taken) index++
        return "$base ($index)"
    }

    /** 导出的建议文件名：清洗文件系统非法字符，追加时间戳，如 `五金仓_20260906_1530.zip` */
    fun suggestedFileName(warehouseName: String, nowMillis: Long): String {
        val clean = warehouseName
            .replace(Regex("""[\\/:*?"<>|]"""), "_")
            .trim()
            .ifBlank { "仓库" }
        val stamp = SimpleDateFormat("yyyyMMdd_HHmm", Locale.US).format(Date(nowMillis))
        return "${clean}_$stamp.zip"
    }
}

/** 文件格式非法或不完整 */
class BadExportFileException : Exception("不是有效的仓库数据文件")

/**
 * 仓库级数据导入导出。
 *
 * 导出：单个 zip 包——`manifest.json`（仓库/类目/物品/属性/流水，回收站数据不参与）
 * + `images/items/{itemId}/{defId}/{file}.jpg`（参考图原样字节，已是压缩图）。
 *
 * 导入：两阶段——[prepare] 先读清单做冲突预检；[import] 在单个事务里
 * 按全新 id 空间重建整棵「仓库 → 类目 → 物品」子树，图片随 zip 第二遍流式落盘，
 * 属性值中的图片相对路径同步重写。同名冲突由 UI 选择：保留两者（自动改名）
 * 或覆盖同名仓库（原仓库移入回收站，可恢复）。
 */
class WarehouseTransfer(
    private val db: SQLiteDatabase,
    private val imageStore: ImageStore,
) {

    // ---------------- 导出 ----------------

    /** 把指定（未删除）仓库完整导出到 [out]。仓库不存在时抛 IllegalStateException。 */
    fun exportWarehouse(warehouseId: Long, out: OutputStream) {
        val warehouseRow = db.rawQuery(
            "SELECT name, remark, created_at FROM warehouse WHERE id=? AND deleted_at IS NULL",
            arrayOf(warehouseId.toString())
        ).use { c ->
            if (c.moveToFirst()) Triple(c.getString(0), c.getString(1).orEmpty(), c.getLong(2))
            else throw IllegalStateException("仓库不存在或已删除")
        }

        val defs = db.rawQuery(
            "SELECT id, name, type, options, sort_order FROM attribute_def WHERE warehouse_id=? ORDER BY sort_order, id",
            arrayOf(warehouseId.toString())
        ).use { c ->
            buildList {
                while (c.moveToNext()) {
                    add(
                        JSONObject().apply {
                            put("id", c.getLong(0))
                            put("name", c.getString(1))
                            put("type", c.getString(2))
                            put("options", JSONArray(AttrOptions.decode(c.getString(3).orEmpty())))
                            put("sortOrder", c.getInt(4))
                        }
                    )
                }
            }
        }

        val categories = db.rawQuery(
            "SELECT id, name, created_at FROM category WHERE warehouse_id=? ORDER BY id",
            arrayOf(warehouseId.toString())
        ).use { c ->
            buildList {
                while (c.moveToNext()) {
                    add(
                        JSONObject().apply {
                            put("id", c.getLong(0))
                            put("name", c.getString(1))
                            put("createdAt", c.getLong(2))
                        }
                    )
                }
            }
        }

        val items = db.rawQuery(
            """SELECT i.id, i.category_id, i.name, i.unit, i.quantity, i.avg_price, i.total_value,
                      i.stock_since, i.created_at
               FROM item i JOIN category c ON i.category_id = c.id
               WHERE c.warehouse_id=? AND i.deleted_at IS NULL ORDER BY i.id""",
            arrayOf(warehouseId.toString())
        ).use { c ->
            buildList {
                while (c.moveToNext()) {
                    add(
                        JSONObject().apply {
                            put("id", c.getLong(0))
                            put("categoryId", c.getLong(1))
                            put("name", c.getString(2))
                            put("unit", c.getString(3).orEmpty())
                            put("quantity", c.getDouble(4))
                            put("avgPrice", c.getDouble(5))
                            put("totalValue", c.getDouble(6))
                            if (c.isNull(7)) put("stockSince", JSONObject.NULL)
                            else put("stockSince", c.getLong(7))
                            put("createdAt", c.getLong(8))
                        }
                    )
                }
            }
        }

        // 属性值：仅未删除物品；IMAGE 类型要求图片文件真实存在才带走
        val values = JSONArray()
        val imagePaths = ArrayList<String>()
        db.rawQuery(
            """SELECT av.attribute_def_id, av.item_id, av.value, ad.type
               FROM attribute_value av
               JOIN attribute_def ad ON ad.id = av.attribute_def_id
               JOIN item i ON i.id = av.item_id
               JOIN category c ON c.id = i.category_id
               WHERE c.warehouse_id=? AND i.deleted_at IS NULL""",
            arrayOf(warehouseId.toString())
        ).use { c ->
            while (c.moveToNext()) {
                val value = c.getString(2).orEmpty()
                if (c.getString(3) == AttrType.IMAGE.wire) {
                    if (value.isEmpty() || !imageStore.fileOf(value).isFile) continue
                    imagePaths.add(value)
                }
                values.put(
                    JSONObject().apply {
                        put("defId", c.getLong(0))
                        put("itemId", c.getLong(1))
                        put("value", value)
                    }
                )
            }
        }

        // 流水为仓库历史，全量导出（包括指向已删除物品的历史条目）
        val records = db.rawQuery(
            """SELECT item_id, item_name, unit, type, quantity, before_qty, after_qty,
                      total_price, note, created_at
               FROM stock_record WHERE warehouse_id=? ORDER BY id""",
            arrayOf(warehouseId.toString())
        ).use { c ->
            buildList {
                while (c.moveToNext()) {
                    add(
                        JSONObject().apply {
                            put("itemId", c.getLong(0))
                            put("itemName", c.getString(1))
                            put("unit", c.getString(2).orEmpty())
                            put("type", c.getString(3))
                            put("quantity", c.getDouble(4))
                            put("beforeQty", c.getDouble(5))
                            put("afterQty", c.getDouble(6))
                            if (c.isNull(7)) put("totalPrice", JSONObject.NULL)
                            else put("totalPrice", c.getDouble(7))
                            put("note", c.getString(8).orEmpty())
                            put("createdAt", c.getLong(9))
                        }
                    )
                }
            }
        }

        val manifest = JSONObject().apply {
            put("format", FORMAT)
            put("formatVersion", FORMAT_VERSION)
            put("exportedAt", System.currentTimeMillis())
            put("warehouse", JSONObject().apply {
                put("name", warehouseRow.first)
                put("remark", warehouseRow.second)
                put("createdAt", warehouseRow.third)
            })
            put("attrDefs", JSONArray(defs))
            put("categories", JSONArray(categories))
            put("items", JSONArray(items))
            put("attrValues", values)
            put("records", JSONArray(records))
        }

        ZipOutputStream(BufferedOutputStream(out)).use { zos ->
            zos.putNextEntry(ZipEntry(ENTRY_MANIFEST))
            zos.write(manifest.toString().toByteArray(Charsets.UTF_8))
            zos.closeEntry()
            imagePaths.forEach { rel ->
                val file = imageStore.fileOf(rel)
                zos.putNextEntry(ZipEntry("$ENTRY_IMAGE_PREFIX$rel"))
                file.inputStream().use { it.copyTo(zos) }
                zos.closeEntry()
            }
        }
    }

    // ---------------- 导入：预检 ----------------

    /** 预检结果：UI 展示与冲突决策用；[parsed] 内部数据由 [import] 消费 */
    class Prepared internal constructor(
        val warehouseName: String,
        val categoryCount: Int,
        val itemCount: Int,
        val recordCount: Int,
        val imageCount: Int,
        val hasConflict: Boolean,
        /** 冲突时「保留两者」将使用的最终名称（app 自动改名的预览） */
        val suggestedName: String,
        internal val parsed: Parsed,
    )

    enum class ConflictMode { KEEP_BOTH, OVERWRITE }

    data class ImportResult(
        val warehouseId: Long,
        val finalName: String,
        val categoryCount: Int,
        val itemCount: Int,
        val recordCount: Int,
        val imageCount: Int,
        /** 清单里有但 zip 中缺失（或落盘失败）的参考图数量 */
        val missingImageCount: Int,
        /** 覆盖模式下被移入回收站的同名仓库数量 */
        val overwrittenCount: Int,
    )

    /** 第一遍读包：解析清单并检测同名冲突。格式非法抛 [BadExportFileException]。 */
    fun prepare(input: InputStream): Prepared {
        val parsed = parseManifest(readManifestEntry(input))
        val taken = activeWarehouseNames()
        return Prepared(
            warehouseName = parsed.name,
            categoryCount = parsed.categories.size,
            itemCount = parsed.items.size,
            recordCount = parsed.records.size,
            imageCount = parsed.imageValues().size,
            hasConflict = parsed.name in taken,
            suggestedName = TransferNaming.uniqueName(parsed.name, taken),
            parsed = parsed,
        )
    }

    // ---------------- 导入：执行 ----------------

    /**
     * 第二遍读包：单事务重建仓库子树并把参考图落盘。
     * 冲突策略以执行时刻的库内状态为准（[Prepared] 中的冲突结论只是 UI 预检）。
     * 任何失败整体回滚，已写出的图片目录一并清理。
     */
    fun import(prepared: Prepared, input: InputStream, mode: ConflictMode): ImportResult {
        val p = prepared.parsed
        val writtenImageDirs = LinkedHashSet<String>()  // items/{itemId}/{defId}
        var succeeded = false
        var imageCount = 0
        var missingImageCount = 0
        var overwrittenCount = 0

        db.beginTransaction()
        try {
            val taken = activeWarehouseNames()
            val finalName = when {
                p.name !in taken -> p.name
                mode == ConflictMode.OVERWRITE -> {
                    overwrittenCount = softDeleteWarehousesNamed(p.name)
                    p.name
                }
                else -> TransferNaming.uniqueName(p.name, taken)
            }

            val newWarehouseId = db.insertOrThrow(
                "warehouse", null,
                ContentValues().apply {
                    put("name", finalName)
                    put("remark", p.remark)
                    put("created_at", p.createdAt)
                }
            )

            val defIdMap = HashMap<Long, Long>()
            val defTypes = HashMap<Long, AttrType>()
            p.defs.forEach { def ->
                val newId = db.insertOrThrow(
                    "attribute_def", null,
                    ContentValues().apply {
                        put("warehouse_id", newWarehouseId)
                        put("name", def.name)
                        put("type", def.type.wire)
                        put("options", AttrOptions.encode(def.options))
                        put("sort_order", def.sortOrder)
                    }
                )
                defIdMap[def.oldId] = newId
                defTypes[def.oldId] = def.type
            }

            val categoryIdMap = HashMap<Long, Long>()
            p.categories.forEach { cat ->
                categoryIdMap[cat.oldId] = db.insertOrThrow(
                    "category", null,
                    ContentValues().apply {
                        put("warehouse_id", newWarehouseId)
                        put("name", cat.name)
                        put("created_at", cat.createdAt)
                    }
                )
            }

            val itemIdMap = HashMap<Long, Long>()
            p.items.forEach { item ->
                val newCategoryId = categoryIdMap[item.oldCategoryId] ?: return@forEach
                itemIdMap[item.oldId] = db.insertOrThrow(
                    "item", null,
                    ContentValues().apply {
                        put("category_id", newCategoryId)
                        put("name", item.name)
                        put("unit", item.unit)
                        put("quantity", item.quantity)
                        put("avg_price", item.avgPrice)
                        put("total_value", item.totalValue)
                        if (item.stockSince != null) put("stock_since", item.stockSince)
                        put("created_at", item.createdAt)
                    }
                )
            }

            // 非图片属性值直接写入；图片值等文件落盘后再补
            val pendingImages = ArrayList<Triple<Long, Long, String>>()  // newDefId, newItemId, 旧相对路径
            p.values.forEach { v ->
                val newDefId = defIdMap[v.oldDefId] ?: return@forEach
                val newItemId = itemIdMap[v.oldItemId] ?: return@forEach
                if (defTypes[v.oldDefId] == AttrType.IMAGE) {
                    pendingImages += Triple(newDefId, newItemId, v.value)
                } else {
                    putValue(newDefId, newItemId, v.value)
                }
            }

            val pendingByEntry = HashMap<String, MutableList<Pair<Long, Long>>>()
            pendingImages.forEach { (defId, itemId, oldRel) ->
                pendingByEntry.getOrPut("$ENTRY_IMAGE_PREFIX$oldRel") { ArrayList() }.add(defId to itemId)
            }
            val writtenValues = ArrayList<Triple<Long, Long, String>>()  // newDefId, newItemId, 新相对路径
            forEachImageEntry(input) { entryName, stream ->
                val targets = pendingByEntry.remove(entryName) ?: return@forEachImageEntry
                val fileName = entryName.substringAfterLast('/')
                targets.forEach { (defId, itemId) ->
                    val rel = imageStore.importFile(itemId, defId, fileName, stream)
                    if (rel != null) {
                        writtenValues += Triple(defId, itemId, rel)
                        writtenImageDirs += rel.substringBeforeLast('/')
                    }
                }
            }
            missingImageCount = pendingImages.size - writtenValues.size
            writtenValues.forEach { (defId, itemId, rel) -> putValue(defId, itemId, rel) }
            imageCount = writtenValues.size

            p.records.forEach { r ->
                // 指向已删除物品的历史流水：映射不上时置负 id，保持「物品已删除」的悬空引用
                val mappedItemId = itemIdMap[r.oldItemId] ?: -r.oldItemId
                db.insertOrThrow(
                    "stock_record", null,
                    ContentValues().apply {
                        put("warehouse_id", newWarehouseId)
                        put("item_id", mappedItemId)
                        put("item_name", r.itemName)
                        put("unit", r.unit)
                        put("type", r.type.wire)
                        put("quantity", r.quantity)
                        put("before_qty", r.beforeQty)
                        put("after_qty", r.afterQty)
                        if (r.totalPrice != null) put("total_price", r.totalPrice)
                        put("note", r.note)
                        put("created_at", r.createdAt)
                    }
                )
            }

            db.setTransactionSuccessful()
            succeeded = true
            return ImportResult(
                warehouseId = newWarehouseId,
                finalName = finalName,
                categoryCount = p.categories.size,
                itemCount = p.items.size,
                recordCount = p.records.size,
                imageCount = imageCount,
                missingImageCount = missingImageCount,
                overwrittenCount = overwrittenCount,
            )
        } finally {
            db.endTransaction()
            if (!succeeded) {
                writtenImageDirs.forEach { imageStore.deleteAttrDirPath(it) }
            }
        }
    }

    // ---------------- 内部：清单解析 ----------------

    internal data class ParsedDef(
        val oldId: Long,
        val name: String,
        val type: AttrType,
        val options: List<String>,
        val sortOrder: Int,
    )

    internal data class ParsedCategory(val oldId: Long, val name: String, val createdAt: Long)

    internal data class ParsedItem(
        val oldId: Long,
        val oldCategoryId: Long,
        val name: String,
        val unit: String,
        val quantity: Double,
        val avgPrice: Double,
        val totalValue: Double,
        val stockSince: Long?,
        val createdAt: Long,
    )

    internal data class ParsedValue(val oldDefId: Long, val oldItemId: Long, val value: String)

    internal data class ParsedRecord(
        val oldItemId: Long,
        val itemName: String,
        val unit: String,
        val type: StockType,
        val quantity: Double,
        val beforeQty: Double,
        val afterQty: Double,
        val totalPrice: Double?,
        val note: String,
        val createdAt: Long,
    )

    internal class Parsed(
        val name: String,
        val remark: String,
        val createdAt: Long,
        val defs: List<ParsedDef>,
        val categories: List<ParsedCategory>,
        val items: List<ParsedItem>,
        val values: List<ParsedValue>,
        val records: List<ParsedRecord>,
    ) {
        fun imageValues(): List<ParsedValue> {
            val imageDefIds = defs.filter { it.type == AttrType.IMAGE }.map { it.oldId }.toHashSet()
            return values.filter { it.oldDefId in imageDefIds && it.value.isNotEmpty() }
        }
    }

    private fun readManifestEntry(input: InputStream): JSONObject {
        ZipInputStream(BufferedInputStream(input)).use { zis ->
            var entry = zis.nextEntry
            while (entry != null) {
                if (entry.name == ENTRY_MANIFEST) {
                    val bytes = readBounded(zis, MAX_MANIFEST_BYTES)
                    return runCatching { JSONObject(String(bytes, Charsets.UTF_8)) }
                        .getOrElse { throw BadExportFileException() }
                }
                zis.closeEntry()
                entry = zis.nextEntry
            }
        }
        throw BadExportFileException()
    }

    private fun parseManifest(root: JSONObject): Parsed {
        if (root.optString("format") != FORMAT) throw BadExportFileException()
        if (root.optInt("formatVersion") !in 1..FORMAT_VERSION) throw BadExportFileException()

        val warehouse = root.optJSONObject("warehouse") ?: throw BadExportFileException()
        val name = warehouse.optString("name").trim()
        if (name.isEmpty()) throw BadExportFileException()

        val defs = buildList {
            root.optJSONArray("attrDefs")?.let { arr ->
                for (i in 0 until arr.length()) {
                    val o = arr.optJSONObject(i) ?: throw BadExportFileException()
                    val optionsArr = o.optJSONArray("options")
                    add(
                        ParsedDef(
                            oldId = o.getLong("id"),
                            name = o.getString("name"),
                            type = AttrType.of(o.optString("type")),
                            options = buildList {
                                optionsArr?.let { oa ->
                                    for (j in 0 until oa.length()) add(oa.optString(j))
                                }
                            },
                            sortOrder = o.optInt("sortOrder"),
                        )
                    )
                }
            }
        }

        val categories = buildList {
            root.optJSONArray("categories")?.let { arr ->
                for (i in 0 until arr.length()) {
                    val o = arr.optJSONObject(i) ?: throw BadExportFileException()
                    add(
                        ParsedCategory(
                            oldId = o.getLong("id"),
                            name = o.getString("name"),
                            createdAt = o.optLong("createdAt", System.currentTimeMillis()),
                        )
                    )
                }
            }
        }

        val knownCategoryIds = categories.map { it.oldId }.toHashSet()
        val items = buildList {
            root.optJSONArray("items")?.let { arr ->
                for (i in 0 until arr.length()) {
                    val o = arr.optJSONObject(i) ?: throw BadExportFileException()
                    val catId = o.getLong("categoryId")
                    if (catId !in knownCategoryIds) throw BadExportFileException()
                    add(
                        ParsedItem(
                            oldId = o.getLong("id"),
                            oldCategoryId = catId,
                            name = o.getString("name"),
                            unit = o.optString("unit"),
                            quantity = o.optDouble("quantity"),
                            avgPrice = o.optDouble("avgPrice"),
                            totalValue = o.optDouble("totalValue"),
                            stockSince = if (o.has("stockSince") && !o.isNull("stockSince")) {
                                o.getLong("stockSince")
                            } else null,
                            createdAt = o.optLong("createdAt", System.currentTimeMillis()),
                        )
                    )
                }
            }
        }

        val values = buildList {
            root.optJSONArray("attrValues")?.let { arr ->
                for (i in 0 until arr.length()) {
                    val o = arr.optJSONObject(i) ?: throw BadExportFileException()
                    add(
                        ParsedValue(
                            oldDefId = o.getLong("defId"),
                            oldItemId = o.getLong("itemId"),
                            value = o.optString("value"),
                        )
                    )
                }
            }
        }

        val records = buildList {
            root.optJSONArray("records")?.let { arr ->
                for (i in 0 until arr.length()) {
                    val o = arr.optJSONObject(i) ?: throw BadExportFileException()
                    add(
                        ParsedRecord(
                            oldItemId = o.optLong("itemId"),
                            itemName = o.optString("itemName"),
                            unit = o.optString("unit"),
                            type = StockType.of(o.optString("type")),
                            quantity = o.optDouble("quantity"),
                            beforeQty = o.optDouble("beforeQty"),
                            afterQty = o.optDouble("afterQty"),
                            totalPrice = if (o.has("totalPrice") && !o.isNull("totalPrice")) {
                                o.getDouble("totalPrice")
                            } else null,
                            note = o.optString("note"),
                            createdAt = o.optLong("createdAt", System.currentTimeMillis()),
                        )
                    )
                }
            }
        }

        return Parsed(
            name = name,
            remark = warehouse.optString("remark"),
            createdAt = warehouse.optLong("createdAt", System.currentTimeMillis()),
            defs = defs,
            categories = categories,
            items = items,
            values = values,
            records = records,
        )
    }

    // ---------------- 内部：工具 ----------------

    /** 逐条遍历 zip 中的图片 entry，路径合法（防穿越）才回调消费流 */
    private inline fun forEachImageEntry(input: InputStream, consume: (String, InputStream) -> Unit) {
        ZipInputStream(BufferedInputStream(input)).use { zis ->
            var entry = zis.nextEntry
            while (entry != null) {
                val name = entry.name
                if (!entry.isDirectory && IMAGE_ENTRY_PATTERN.matches(name)) {
                    consume(name, zis)
                }
                zis.closeEntry()
                entry = zis.nextEntry
            }
        }
    }

    private fun readBounded(zis: ZipInputStream, maxBytes: Int): ByteArray {
        val buffer = ByteArray(8192)
        val out = ByteArrayOutputStream()
        var total = 0
        while (true) {
            val n = zis.read(buffer)
            if (n < 0) break
            total += n
            if (total > maxBytes) throw BadExportFileException()
            out.write(buffer, 0, n)
        }
        return out.toByteArray()
    }

    private fun activeWarehouseNames(): Set<String> =
        db.rawQuery("SELECT name FROM warehouse WHERE deleted_at IS NULL", null)
            .use { c -> buildSet { while (c.moveToNext()) add(c.getString(0)) } }

    /** 覆盖模式：同名（未删除）仓库全部移入回收站，返回数量 */
    private fun softDeleteWarehousesNamed(name: String): Int =
        db.update(
            "warehouse",
            ContentValues().apply { put("deleted_at", System.currentTimeMillis()) },
            "name=? AND deleted_at IS NULL",
            arrayOf(name)
        )

    private fun putValue(defId: Long, itemId: Long, value: String) {
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

    companion object {
        const val FORMAT = "stock-warehouse-export"
        const val FORMAT_VERSION = 1
        private const val ENTRY_MANIFEST = "manifest.json"
        private const val ENTRY_IMAGE_PREFIX = "images/"
        private const val MAX_MANIFEST_BYTES = 64 * 1024 * 1024
        /** 图片 entry 路径白名单，防 zip 路径穿越 */
        private val IMAGE_ENTRY_PATTERN = Regex("""^images/items/\d+/\d+/[^/]+$""")
    }
}
