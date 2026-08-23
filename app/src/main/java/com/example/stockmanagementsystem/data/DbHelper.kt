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
                created_at INTEGER NOT NULL
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
                created_at INTEGER NOT NULL
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
        // 属性定义从物品级迁移到类目级：首版未发布，直接重建
        db.execSQL("DROP TABLE IF EXISTS stock_record")
        db.execSQL("DROP TABLE IF EXISTS attribute_value")
        db.execSQL("DROP TABLE IF EXISTS attribute_def")
        db.execSQL("DROP TABLE IF EXISTS item")
        db.execSQL("DROP TABLE IF EXISTS category")
        db.execSQL("DROP TABLE IF EXISTS warehouse")
        onCreate(db)
    }

    companion object {
        const val DB_NAME = "stock.db"
        const val DB_VERSION = 6
    }
}
