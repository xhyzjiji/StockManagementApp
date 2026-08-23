package com.example.stockmanagementsystem

import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.Toast
import androidx.appcompat.app.AlertDialog
import androidx.fragment.app.Fragment
import androidx.recyclerview.widget.LinearLayoutManager
import com.example.stockmanagementsystem.data.Repository
import com.example.stockmanagementsystem.databinding.FragmentWarehouseBinding
import com.example.stockmanagementsystem.ui.Dialogs
import com.example.stockmanagementsystem.ui.WarehouseAdapter
import com.example.stockmanagementsystem.util.Bg
import com.example.stockmanagementsystem.util.runInBackground

/** 「我的仓库」tab：仓库列表（逻辑迁移自原 WarehouseListActivity） */
class WarehouseFragment : Fragment() {

    private var vb: FragmentWarehouseBinding? = null
    private val repo by lazy { Repository.get(requireContext()) }
    private lateinit var adapter: WarehouseAdapter

    override fun onCreateView(
        inflater: LayoutInflater,
        container: ViewGroup?,
        savedInstanceState: Bundle?,
    ): View {
        val binding = FragmentWarehouseBinding.inflate(inflater, container, false)
        vb = binding

        adapter = WarehouseAdapter(
            onClick = { w -> startActivity(MainActivity.intent(requireContext(), w.id)) },
            onLongClick = { w -> showWarehouseOps(w.id, w.name) },
        )
        binding.recycler.layoutManager = LinearLayoutManager(requireContext())
        binding.recycler.adapter = adapter
        binding.fabAdd.setOnClickListener { showCreateDialog() }
        binding.toolbar.setOnMenuItemClickListener { item ->
            when (item.itemId) {
                R.id.action_recycle_bin -> {
                    startActivity(RecycleBinActivity.warehouseBinIntent(requireContext()))
                    true
                }
                else -> false
            }
        }

        // 清理上次编辑未保存遗留的暂存图片
        Bg.run { repo.imageStore.cleanTmp() }
        return binding.root
    }

    override fun onResume() {
        super.onResume()
        reload()
    }

    private fun reload() {
        runInBackground({ repo.listWarehouses() }) { list ->
            val binding = vb ?: return@runInBackground
            adapter.submit(list)
            binding.textEmpty.visibility = if (list.isEmpty()) View.VISIBLE else View.GONE
        }
    }

    private fun showCreateDialog() {
        Dialogs.warehouse(requireContext(), R.string.warehouse_create) { name, remark ->
            runInBackground({ repo.createWarehouse(name, remark) }) { reload() }
        }
    }

    private fun showWarehouseOps(id: Long, name: String) {
        val ctx = requireContext()
        AlertDialog.Builder(ctx)
            .setTitle(name)
            .setItems(arrayOf(getString(R.string.action_edit), getString(R.string.action_delete))) { _, which ->
                when (which) {
                    0 -> runInBackground({ repo.getWarehouse(id) }) { w ->
                        if (w != null) {
                            Dialogs.warehouse(ctx, R.string.action_edit, w.name, w.remark) { n, r ->
                                runInBackground({ repo.updateWarehouse(id, n, r); Unit }) { reload() }
                            }
                        }
                    }
                    1 -> Dialogs.confirm(ctx, getString(R.string.warehouse_delete_confirm, name)) {
                        runInBackground({ repo.softDeleteWarehouse(id) }) {
                            Toast.makeText(ctx, R.string.moved_to_bin, Toast.LENGTH_SHORT).show()
                            reload()
                        }
                    }
                }
            }
            .show()
    }
}
