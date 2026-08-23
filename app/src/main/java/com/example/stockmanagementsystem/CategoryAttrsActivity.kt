package com.example.stockmanagementsystem

import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.view.View
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.recyclerview.widget.LinearLayoutManager
import com.example.stockmanagementsystem.data.AttrDefDraft
import com.example.stockmanagementsystem.data.AttrType
import com.example.stockmanagementsystem.data.Repository
import com.example.stockmanagementsystem.databinding.ActivityCategoryAttrsBinding
import com.example.stockmanagementsystem.ui.AttrDefAdapter
import com.example.stockmanagementsystem.ui.AttrDefRow
import com.example.stockmanagementsystem.ui.Dialogs
import com.example.stockmanagementsystem.util.Insets
import com.example.stockmanagementsystem.util.runInBackground

/** 类目属性设置：统一定义该类目下所有物品共用的属性 */
class CategoryAttrsActivity : AppCompatActivity() {

    private lateinit var vb: ActivityCategoryAttrsBinding
    private val repo by lazy { Repository.get(this) }
    private lateinit var adapter: AttrDefAdapter
    private var categoryId: Long = -1

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        vb = ActivityCategoryAttrsBinding.inflate(layoutInflater)
        setContentView(vb.root)
        Insets.apply(this)
        vb.toolbar.setNavigationOnClickListener { finish() }

        categoryId = intent.getLongExtra(EXTRA_CATEGORY_ID, -1)
        if (categoryId <= 0) {
            finish()
            return
        }
        vb.toolbar.subtitle = intent.getStringExtra(EXTRA_CATEGORY_NAME).orEmpty()

        adapter = AttrDefAdapter(
            onEdit = { row -> editDef(row) },
            onDelete = { row ->
                Dialogs.confirm(this, getString(R.string.attr_delete_cascade, row.name)) {
                    adapter.removeRow(row)
                }
            },
        )
        vb.recycler.layoutManager = LinearLayoutManager(this)
        vb.recycler.adapter = adapter

        vb.btnAdd.setOnClickListener {
            Dialogs.attrDef(this, R.string.attr_dialog_title_new) { name, type, options ->
                if (adapter.rows.any { it.name == name }) {
                    Toast.makeText(this, R.string.attr_name_duplicate, Toast.LENGTH_SHORT).show()
                    return@attrDef
                }
                adapter.addRowDef(AttrDefRow(null, name, type, options))
                syncEmpty()
            }
        }
        vb.btnSave.setOnClickListener { save() }

        runInBackground({ repo.listAttrDefs(categoryId) }) { defs ->
            adapter.submit(defs.map { AttrDefRow(it.id, it.name, it.type, it.options) })
            syncEmpty()
        }
    }

    private fun editDef(row: AttrDefRow) {
        Dialogs.attrDef(this, R.string.attr_dialog_title_edit, row.name, row.type, row.options) { name, type, options ->
            if (adapter.rows.any { it !== row && it.name == name }) {
                Toast.makeText(this, R.string.attr_name_duplicate, Toast.LENGTH_SHORT).show()
                return@attrDef
            }
            fun apply() {
                row.name = name
                row.type = type
                row.options = options
                adapter.refreshRow(row)
            }
            if (type != row.type) {
                // 类型切换会在保存时清空该类目下所有物品的已有值，先确认
                Dialogs.confirm(
                    this,
                    getString(R.string.attr_type_change_warning, row.name, typeLabel(row.type), typeLabel(type))
                ) { apply() }
            } else {
                apply()
            }
        }
    }

    private fun typeLabel(type: AttrType): String =
        getString(
            when (type) {
                AttrType.TEXT -> R.string.attr_type_text
                AttrType.NUMBER -> R.string.attr_type_number
                AttrType.CHOICE -> R.string.attr_type_choice
                AttrType.TAGS -> R.string.attr_type_tags
                AttrType.IMAGE -> R.string.attr_type_image
            }
        )

    private fun syncEmpty() {
        vb.textEmpty.visibility = if (adapter.rows.isEmpty()) View.VISIBLE else View.GONE
    }

    private fun save() {
        val names = adapter.rows.map { it.name }
        if (names.distinct().size != names.size) {
            Toast.makeText(this, R.string.attr_name_duplicate, Toast.LENGTH_SHORT).show()
            return
        }
        val drafts = adapter.rows.map { AttrDefDraft(it.defId, it.name, it.type, it.options) }
        runInBackground({ repo.saveCategoryAttrDefs(categoryId, drafts) }) {
            Toast.makeText(this, R.string.save_success, Toast.LENGTH_SHORT).show()
            finish()
        }
    }

    companion object {
        const val EXTRA_CATEGORY_ID = "extra_category_id"
        const val EXTRA_CATEGORY_NAME = "extra_category_name"

        fun intent(context: Context, categoryId: Long, categoryName: String): Intent =
            Intent(context, CategoryAttrsActivity::class.java)
                .putExtra(EXTRA_CATEGORY_ID, categoryId)
                .putExtra(EXTRA_CATEGORY_NAME, categoryName)
    }
}
