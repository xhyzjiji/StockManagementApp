package com.example.stockmanagementsystem

import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.view.View
import android.widget.Toast
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.recyclerview.widget.LinearLayoutManager
import com.example.stockmanagementsystem.data.DeletedRow
import com.example.stockmanagementsystem.data.Repository
import com.example.stockmanagementsystem.databinding.ActivityRecycleBinBinding
import com.example.stockmanagementsystem.ui.DeletedRowAdapter
import com.example.stockmanagementsystem.ui.Dialogs
import com.example.stockmanagementsystem.util.Insets
import com.example.stockmanagementsystem.util.runInBackground

/** 回收站：mode=WAREHOUSE 列全部已删仓库；mode=ITEM 列指定仓库的已删物品 */
class RecycleBinActivity : AppCompatActivity() {

    enum class Mode { WAREHOUSE, ITEM }

    private lateinit var vb: ActivityRecycleBinBinding
    private val repo by lazy { Repository.get(this) }
    private lateinit var adapter: DeletedRowAdapter
    private var mode = Mode.WAREHOUSE
    private var warehouseId: Long = -1

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        vb = ActivityRecycleBinBinding.inflate(layoutInflater)
        setContentView(vb.root)
        Insets.apply(this)
        vb.toolbar.setNavigationOnClickListener { finish() }

        mode = if (intent.getIntExtra(EXTRA_MODE, 0) == 1) Mode.ITEM else Mode.WAREHOUSE
        warehouseId = intent.getLongExtra(EXTRA_WAREHOUSE_ID, -1)
        if (mode == Mode.ITEM && warehouseId <= 0) {
            finish()
            return
        }
        vb.toolbar.setTitle(
            if (mode == Mode.ITEM) R.string.recycle_item_title else R.string.recycle_warehouse_title
        )
        if (mode == Mode.ITEM) {
            vb.toolbar.subtitle = intent.getStringExtra(EXTRA_WAREHOUSE_NAME).orEmpty()
        }

        adapter = DeletedRowAdapter(
            iconRes = if (mode == Mode.ITEM) R.drawable.ic_brand else R.drawable.ic_nav_warehouse,
            onClick = { row -> showRowOps(row) },
        )
        vb.recycler.layoutManager = LinearLayoutManager(this)
        vb.recycler.adapter = adapter
    }

    override fun onResume() {
        super.onResume()
        reload()
    }

    private fun reload() {
        runInBackground({
            if (mode == Mode.ITEM) repo.listDeletedItems(warehouseId) else repo.listDeletedWarehouses()
        }) { list ->
            adapter.submit(list)
            vb.textEmpty.visibility = if (list.isEmpty()) View.VISIBLE else View.GONE
        }
    }

    private fun showRowOps(row: DeletedRow) {
        AlertDialog.Builder(this)
            .setTitle(row.title)
            .setItems(
                arrayOf(getString(R.string.action_restore), getString(R.string.action_delete_forever))
            ) { _, which ->
                when (which) {
                    0 -> runInBackground({
                        if (mode == Mode.ITEM) repo.restoreItem(row.id) else repo.restoreWarehouse(row.id)
                    }) {
                        Toast.makeText(this, R.string.restored, Toast.LENGTH_SHORT).show()
                        reload()
                    }
                    1 -> destroy(row)
                }
            }
            .show()
    }

    private fun destroy(row: DeletedRow) {
        val msgRes = if (mode == Mode.ITEM) R.string.item_destroy_confirm else R.string.warehouse_destroy_confirm
        Dialogs.confirm(this, getString(msgRes, row.title)) {
            runInBackground({
                if (mode == Mode.ITEM) repo.deleteItem(row.id) else repo.deleteWarehouse(row.id)
                Unit
            }) {
                Toast.makeText(this, R.string.deleted, Toast.LENGTH_SHORT).show()
                reload()
            }
        }
    }

    companion object {
        const val EXTRA_MODE = "extra_mode"
        const val EXTRA_WAREHOUSE_ID = "extra_warehouse_id"
        const val EXTRA_WAREHOUSE_NAME = "extra_warehouse_name"

        fun warehouseBinIntent(context: Context): Intent =
            Intent(context, RecycleBinActivity::class.java).putExtra(EXTRA_MODE, 0)

        fun itemBinIntent(context: Context, warehouseId: Long, warehouseName: String): Intent =
            Intent(context, RecycleBinActivity::class.java)
                .putExtra(EXTRA_MODE, 1)
                .putExtra(EXTRA_WAREHOUSE_ID, warehouseId)
                .putExtra(EXTRA_WAREHOUSE_NAME, warehouseName)
    }
}
