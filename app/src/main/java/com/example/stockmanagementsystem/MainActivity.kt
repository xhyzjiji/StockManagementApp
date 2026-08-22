package com.example.stockmanagementsystem

import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.view.View
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.recyclerview.widget.LinearLayoutManager
import com.example.stockmanagementsystem.data.Repository
import com.example.stockmanagementsystem.util.Insets
import com.example.stockmanagementsystem.databinding.ActivityMainBinding
import com.example.stockmanagementsystem.ui.CategoryAdapter
import com.example.stockmanagementsystem.ui.Dialogs
import com.example.stockmanagementsystem.util.runInBackground

/** 仓库主页：类目列表（仓库上下文：EXTRA_WAREHOUSE_ID） */
class MainActivity : AppCompatActivity() {

    private lateinit var vb: ActivityMainBinding
    private val repo by lazy { Repository.get(this) }
    private lateinit var adapter: CategoryAdapter
    private var warehouseId: Long = -1

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        vb = ActivityMainBinding.inflate(layoutInflater)
        setContentView(vb.root)
        Insets.apply(this)
        vb.toolbar.setNavigationOnClickListener { finish() }

        warehouseId = intent.getLongExtra(EXTRA_WAREHOUSE_ID, -1)
        if (warehouseId <= 0) {
            finish()
            return
        }

        adapter = CategoryAdapter(
            onClick = { c -> startActivity(ItemListActivity.intent(this, c.id, c.name)) },
            onLongClick = { c -> showCategoryOps(c.id, c.name) },
        )
        vb.recycler.layoutManager = LinearLayoutManager(this)
        vb.recycler.adapter = adapter

        vb.toolbar.setOnMenuItemClickListener { item ->
            when (item.itemId) {
                R.id.action_records -> {
                    startActivity(RecordListActivity.intent(this, warehouseId))
                    true
                }
                R.id.action_rename_warehouse -> {
                    showWarehouseDialog()
                    true
                }
                else -> false
            }
        }
        vb.fabAdd.setOnClickListener {
            Dialogs.inputText(this, R.string.category_add, R.string.category_name_hint) { name ->
                runInBackground({ repo.createCategory(warehouseId, name) }) { reload() }
            }
        }
    }

    override fun onResume() {
        super.onResume()
        reload()
    }

    private fun reload() {
        runInBackground({ repo.getWarehouse(warehouseId)?.name to repo.listCategories(warehouseId) }) { (name, list) ->
            if (name == null) {
                finish()
                return@runInBackground
            }
            vb.toolbar.title = name
            adapter.submit(list)
            vb.textEmpty.visibility = if (list.isEmpty()) View.VISIBLE else View.GONE
        }
    }

    private fun showWarehouseDialog() {
        runInBackground({ repo.getWarehouse(warehouseId) }) { w ->
            if (w != null) {
                Dialogs.warehouse(this, R.string.menu_rename_warehouse, w.name, w.remark) { name, remark ->
                    runInBackground({ repo.updateWarehouse(warehouseId, name, remark); Unit }) { reload() }
                }
            }
        }
    }

    private fun showCategoryOps(id: Long, name: String) {
        AlertDialog.Builder(this)
            .setTitle(name)
            .setItems(arrayOf(getString(R.string.action_rename), getString(R.string.action_delete))) { _, which ->
                when (which) {
                    0 -> Dialogs.inputText(this, R.string.action_rename, R.string.category_name_hint, name) { newName ->
                        runInBackground({ repo.renameCategory(id, newName) }) { reload() }
                    }
                    1 -> Dialogs.confirm(this, getString(R.string.category_delete_confirm, name)) {
                        runInBackground({ repo.deleteCategory(id); Unit }) { reload() }
                    }
                }
            }
            .show()
    }

    companion object {
        const val EXTRA_WAREHOUSE_ID = "extra_warehouse_id"

        fun intent(context: Context, warehouseId: Long): Intent =
            Intent(context, MainActivity::class.java).putExtra(EXTRA_WAREHOUSE_ID, warehouseId)
    }
}
