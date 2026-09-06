package com.example.stockmanagementsystem

import android.net.Uri
import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AlertDialog
import androidx.fragment.app.Fragment
import androidx.recyclerview.widget.LinearLayoutManager
import com.example.stockmanagementsystem.data.BadExportFileException
import com.example.stockmanagementsystem.data.Repository
import com.example.stockmanagementsystem.data.TransferNaming
import com.example.stockmanagementsystem.data.WarehouseTransfer
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

    /** 导出流程跨 SAF 回调的上下文：仓库 id + 名称（toast 用） */
    private var pendingExport: Pair<Long, String>? = null

    /** 导出：系统文件选择器，用户自选目录与文件名 */
    private val exportFileCreator = registerForActivityResult(
        ActivityResultContracts.CreateDocument("application/zip")
    ) { uri ->
        val pending = pendingExport
        pendingExport = null
        if (uri != null && pending != null) doExport(pending.first, pending.second, uri)
    }

    /** 导入：选择数据包文件（不同文件管理器对 zip 的 MIME 标注不一，多给几个兜底） */
    private val importFilePicker = registerForActivityResult(
        ActivityResultContracts.OpenDocument()
    ) { uri ->
        if (uri != null) prepareImport(uri)
    }

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
                R.id.action_import -> {
                    importFilePicker.launch(
                        arrayOf("application/zip", "application/x-zip-compressed", "application/octet-stream")
                    )
                    true
                }
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
            .setItems(
                arrayOf(
                    getString(R.string.action_export),
                    getString(R.string.action_edit),
                    getString(R.string.action_delete),
                )
            ) { _, which ->
                when (which) {
                    0 -> startExport(id, name)
                    1 -> runInBackground({ repo.getWarehouse(id) }) { w ->
                        if (w != null) {
                            Dialogs.warehouse(ctx, R.string.action_edit, w.name, w.remark) { n, r ->
                                runInBackground({ repo.updateWarehouse(id, n, r); Unit }) { reload() }
                            }
                        }
                    }
                    2 -> Dialogs.confirm(ctx, getString(R.string.warehouse_delete_confirm, name)) {
                        runInBackground({ repo.softDeleteWarehouse(id) }) {
                            Toast.makeText(ctx, R.string.moved_to_bin, Toast.LENGTH_SHORT).show()
                            reload()
                        }
                    }
                }
            }
            .show()
    }

    // ---------------- 导出 ----------------

    private fun startExport(id: Long, name: String) {
        pendingExport = id to name
        exportFileCreator.launch(TransferNaming.suggestedFileName(name, System.currentTimeMillis()))
    }

    private fun doExport(id: Long, name: String, uri: Uri) {
        val appCtx = requireContext().applicationContext
        runInBackground({
            runCatching {
                appCtx.contentResolver.openOutputStream(uri, "wt")?.use { out ->
                    repo.transfer.exportWarehouse(id, out)
                } ?: throw IllegalStateException("无法写入所选位置")
            }
        }) { result ->
            val ctx = context ?: return@runInBackground
            result.onSuccess {
                Toast.makeText(ctx, getString(R.string.export_done, name), Toast.LENGTH_LONG).show()
            }.onFailure { e ->
                Toast.makeText(ctx, getString(R.string.export_failed, e.message ?: ""), Toast.LENGTH_LONG).show()
            }
        }
    }

    // ---------------- 导入 ----------------

    /** 第一遍读包：解析清单 + 同名冲突预检，之后决定直接导入还是弹冲突选项 */
    private fun prepareImport(uri: Uri) {
        val appCtx = requireContext().applicationContext
        runInBackground({
            runCatching {
                appCtx.contentResolver.openInputStream(uri)?.use { repo.transfer.prepare(it) }
                    ?: throw BadExportFileException()
            }
        }) { result ->
            val ctx = context ?: return@runInBackground
            result.onSuccess { prepared ->
                if (prepared.hasConflict) {
                    showImportConflictDialog(uri, prepared)
                } else {
                    doImport(uri, prepared, WarehouseTransfer.ConflictMode.KEEP_BOTH)
                }
            }.onFailure {
                Toast.makeText(ctx, R.string.import_bad_file, Toast.LENGTH_LONG).show()
            }
        }
    }

    /** 同名冲突：保留两者（自动改名）/ 覆盖同名仓库 / 取消导入 */
    private fun showImportConflictDialog(uri: Uri, prepared: WarehouseTransfer.Prepared) {
        val ctx = context ?: return
        Dialogs.options(
            ctx,
            R.string.import_conflict_title,
            getString(R.string.import_conflict_message, prepared.warehouseName),
            listOf(
                getString(R.string.import_keep_both, prepared.suggestedName),
                getString(R.string.import_overwrite),
            ),
            R.string.import_cancel,
        ) { which ->
            val mode = if (which == 0) {
                WarehouseTransfer.ConflictMode.KEEP_BOTH
            } else {
                WarehouseTransfer.ConflictMode.OVERWRITE
            }
            doImport(uri, prepared, mode)
        }
    }

    private fun doImport(uri: Uri, prepared: WarehouseTransfer.Prepared, mode: WarehouseTransfer.ConflictMode) {
        val appCtx = requireContext().applicationContext
        runInBackground({
            runCatching {
                appCtx.contentResolver.openInputStream(uri)?.use { input ->
                    repo.transfer.import(prepared, input, mode)
                } ?: throw IllegalStateException("无法读取文件")
            }
        }) { result ->
            val ctx = context ?: return@runInBackground
            result.onSuccess { r ->
                Toast.makeText(ctx, importResultMessage(r), Toast.LENGTH_LONG).show()
                reload()
            }.onFailure { e ->
                Toast.makeText(ctx, getString(R.string.import_failed, e.message ?: ""), Toast.LENGTH_LONG).show()
            }
        }
    }

    private fun importResultMessage(r: WarehouseTransfer.ImportResult): String = buildString {
        append(getString(R.string.import_done, r.finalName, r.categoryCount, r.itemCount, r.recordCount))
        if (r.missingImageCount > 0) append(getString(R.string.import_missing_images, r.missingImageCount))
        if (r.overwrittenCount > 0) append(getString(R.string.import_overwritten_note))
    }
}
