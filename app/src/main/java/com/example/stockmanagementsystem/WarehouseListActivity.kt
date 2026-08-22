package com.example.stockmanagementsystem

import android.os.Bundle
import android.view.View
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.recyclerview.widget.LinearLayoutManager
import com.example.stockmanagementsystem.data.Repository
import com.example.stockmanagementsystem.databinding.ActivityWarehouseListBinding
import com.example.stockmanagementsystem.ui.Dialogs
import com.example.stockmanagementsystem.ui.WarehouseAdapter
import com.example.stockmanagementsystem.util.Bg
import com.example.stockmanagementsystem.util.Insets
import com.example.stockmanagementsystem.util.runInBackground

class WarehouseListActivity : AppCompatActivity() {

    private lateinit var vb: ActivityWarehouseListBinding
    private val repo by lazy { Repository.get(this) }
    private lateinit var adapter: WarehouseAdapter

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        vb = ActivityWarehouseListBinding.inflate(layoutInflater)
        setContentView(vb.root)
        Insets.apply(this)

        adapter = WarehouseAdapter(
            onClick = { w ->
                startActivity(MainActivity.intent(this, w.id))
            },
            onLongClick = { w -> showWarehouseOps(w.id, w.name) },
        )
        vb.recycler.layoutManager = LinearLayoutManager(this)
        vb.recycler.adapter = adapter

        vb.fabAdd.setOnClickListener { showCreateDialog() }

        // 清理上次编辑未保存遗留的暂存图片
        Bg.run { repo.imageStore.cleanTmp() }
    }

    override fun onResume() {
        super.onResume()
        reload()
    }

    private fun reload() {
        runInBackground({ repo.listWarehouses() }) { list ->
            adapter.submit(list)
            vb.textEmpty.visibility = if (list.isEmpty()) View.VISIBLE else View.GONE
        }
    }

    private fun showCreateDialog() {
        Dialogs.warehouse(this, R.string.warehouse_create) { name, remark ->
            runInBackground({ repo.createWarehouse(name, remark) }) { reload() }
        }
    }

    private fun showWarehouseOps(id: Long, name: String) {
        AlertDialog.Builder(this)
            .setTitle(name)
            .setItems(arrayOf(getString(R.string.action_edit), getString(R.string.action_delete))) { _, which ->
                when (which) {
                    0 -> runInBackground({ repo.getWarehouse(id) }) { w ->
                        if (w != null) {
                            Dialogs.warehouse(this, R.string.action_edit, w.name, w.remark) { n, r ->
                                runInBackground({ repo.updateWarehouse(id, n, r); Unit }) { reload() }
                            }
                        }
                    }
                    1 -> Dialogs.confirm(this, getString(R.string.warehouse_delete_confirm, name)) {
                        runInBackground({ repo.deleteWarehouse(id); Unit }) { reload() }
                    }
                }
            }
            .show()
    }
}
