package com.example.stockmanagementsystem.data

import android.content.Context
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper

class DbHelper(context: Context) : SQLiteOpenHelper(context, DB_NAME, null, DB_VERSION) {

    override fun onConfigure(db: SQLiteDatabase) {
        super.onConfigure(db)
        db.setForeignKeyConstraintsEnabled(true)
    }

    override fun onCreate(db: SQLiteDatabase) {
        db.execSQL(
            """
            CREATE TABLE warehouse(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                remark TEXT NOT NULL DEFAULT '',
                created_at INTEGER NOT NULL,
                deleted_at INTEGER
            )
            """.trimIndent()
        )
        db.execSQL(
            """
            CREATE TABLE category(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                warehouse_id INTEGER NOT NULL REFERENCES warehouse(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                created_at INTEGER NOT NULL
            )
            """.trimIndent()
        )
        db.execSQL(
            """
            CREATE TABLE item(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category_id INTEGER NOT NULL REFERENCES category(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                unit TEXT NOT NULL DEFAULT '',
                quantity REAL NOT NULL DEFAULT 0,
                avg_price REAL NOT NULL DEFAULT 0,
                total_value REAL NOT NULL DEFAULT 0,
                stock_since INTEGER,
                created_at INTEGER NOT NULL,
                deleted_at INTEGER
            )
            """.trimIndent()
        )
        db.execSQL(
            """
            CREATE TABLE attribute_def(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                warehouse_id INTEGER NOT NULL REFERENCES warehouse(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                type TEXT NOT NULL,
                options TEXT NOT NULL DEFAULT '',
                sort_order INTEGER NOT NULL DEFAULT 0
            )
            """.trimIndent()
        )
        db.execSQL(
            """
            CREATE TABLE attribute_value(
                attribute_def_id INTEGER NOT NULL REFERENCES attribute_def(id) ON DELETE CASCADE,
                item_id INTEGER NOT NULL REFERENCES item(id) ON DELETE CASCADE,
                value TEXT NOT NULL DEFAULT '',
                PRIMARY KEY(attribute_def_id, item_id)
            )
            """.trimIndent()
        )
        db.execSQL(
            """
            CREATE TABLE stock_record(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                warehouse_id INTEGER NOT NULL REFERENCES warehouse(id) ON DELETE CASCADE,
                item_id INTEGER NOT NULL,
                item_name TEXT NOT NULL,
                unit TEXT NOT NULL DEFAULT '',
                type TEXT NOT NULL,
                quantity REAL NOT NULL,
                before_qty REAL NOT NULL,
                after_qty REAL NOT NULL,
                total_price REAL,
                note TEXT NOT NULL DEFAULT '',
                created_at INTEGER NOT NULL
            )
            """.trimIndent()
        )
        db.execSQL("CREATE INDEX idx_category_wh ON category(warehouse_id)")
        db.execSQL("CREATE INDEX idx_item_cat ON item(category_id)")
        db.execSQL("CREATE INDEX idx_def_wh ON attribute_def(warehouse_id)")
        db.execSQL("CREATE INDEX idx_value_item ON attribute_value(item_id)")
        db.execSQL("CREATE INDEX idx_record_wh ON stock_record(warehouse_id, created_at DESC)")
        db.execSQL("CREATE INDEX idx_record_item ON stock_record(item_id, created_at DESC)")
    }

    override fun onUpgrade(db: SQLiteDatabase, oldVersion: Int, newVersion: Int) {
        if (oldVersion < FIRST_RELEASED_VERSION) {
            // 属性定义从物品级迁移到类目级：首版未发布，直接重建（无真实用户数据）
            db.execSQL("DROP TABLE IF EXISTS stock_record")
            db.execSQL("DROP TABLE IF EXISTS attribute_value")
            db.execSQL("DROP TABLE IF EXISTS attribute_def")
            db.execSQL("DROP TABLE IF EXISTS item")
            db.execSQL("DROP TABLE IF EXISTS category")
            db.execSQL("DROP TABLE IF EXISTS warehouse")
            onCreate(db)
            return
        }
        // 版本间数据转换工具：每升一个版本新增一段 migrateXtoY，任意跨度都按顺序逐段套用。
        // 约定：已发布版本禁止删表重建，结构性不兼容也必须写成保留数据的转换函数。
        var v = oldVersion
        while (v < newVersion) {
            when (v) {
                7 -> migrate7to8(db)
                8 -> migrate8to9(db)
            }
            v++
        }
    }

    /** v7 → v8 库存金额：物品维护平均价与剩余总价，流水记录本次入库总价 */
    private fun migrate7to8(db: SQLiteDatabase) {
        db.execSQL("ALTER TABLE item ADD COLUMN avg_price REAL NOT NULL DEFAULT 0")
        db.execSQL("ALTER TABLE item ADD COLUMN total_value REAL NOT NULL DEFAULT 0")
        db.execSQL("ALTER TABLE stock_record ADD COLUMN total_price REAL")
    }

    /** v8 → v9 在库天数：stock_since 为当前这批库存的入库起点（出清后重新计时） */
    private fun migrate8to9(db: SQLiteDatabase) {
        db.execSQL("ALTER TABLE item ADD COLUMN stock_since INTEGER")
        // 回填：有库存的物品，以「最后一次出清之后的首次入库时间」为起点；无流水则退回创建时间
        db.rawQuery("SELECT id, created_at FROM item WHERE quantity > 0", null).use { items ->
            while (items.moveToNext()) {
                val itemId = items.getLong(0)
                val since = db.rawQuery(
                    """SELECT MIN(created_at) FROM stock_record
                       WHERE item_id=? AND created_at > COALESCE(
                           (SELECT MAX(created_at) FROM stock_record
                             WHERE item_id=? AND after_qty = 0), 0)""",
                    arrayOf(itemId.toString(), itemId.toString())
                ).use { c -> if (c.moveToFirst() && !c.isNull(0)) c.getLong(0) else items.getLong(1) }
                db.execSQL(
                    "UPDATE item SET stock_since=? WHERE id=?",
                    arrayOf(since, itemId)
                )
            }
        }
    }

    companion object {
        const val DB_NAME = "stock.db"
        const val DB_VERSION = 9

        /** 首个对外发布版本；低于此版本的库不存在真实用户数据，允许重建 */
        const val FIRST_RELEASED_VERSION = 7
    }
}
