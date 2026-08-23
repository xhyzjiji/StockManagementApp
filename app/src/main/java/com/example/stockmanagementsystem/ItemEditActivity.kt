package com.example.stockmanagementsystem

import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.widget.PopupMenu
import android.widget.Toast
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.FileProvider
import androidx.recyclerview.widget.LinearLayoutManager
import com.example.stockmanagementsystem.data.AttrType
import com.example.stockmanagementsystem.data.AttrOptions
import com.example.stockmanagementsystem.data.Category
import com.example.stockmanagementsystem.data.Repository
import com.example.stockmanagementsystem.databinding.ActivityItemEditBinding
import com.example.stockmanagementsystem.ui.AttrEditAdapter
import com.example.stockmanagementsystem.ui.AttrRow
import com.example.stockmanagementsystem.util.Bg
import com.example.stockmanagementsystem.util.Insets
import com.example.stockmanagementsystem.util.runInBackground
import java.io.File

/** 物品新建/编辑：名称 + 单位 + 所属类目（可换） + 仓库统一定义的属性值 */
class ItemEditActivity : AppCompatActivity(), AttrEditAdapter.Listener {

    private lateinit var vb: ActivityItemEditBinding
    private val repo by lazy { Repository.get(this) }
    private lateinit var adapter: AttrEditAdapter

    private var itemId: Long = -1
    private var categoryId: Long = -1
    private var categories: List<Category> = emptyList()

    private var pendingCameraRow: AttrRow? = null
    private var pendingCameraFile: File? = null
    private var pendingGalleryRow: AttrRow? = null

    private val takePicture =
        registerForActivityResult(ActivityResultContracts.TakePicture()) { success ->
            val row = pendingCameraRow
            val file = pendingCameraFile
            pendingCameraRow = null
            if (success && row != null && file != null && file.exists()) {
                Bg.run {
                    repo.imageStore.normalizeInPlace(file)
                    runOnUiThread { applyStagedImage(row, file) }
                }
            } else {
                file?.delete()
            }
            pendingCameraFile = null
        }

    private val pickImage =
        registerForActivityResult(ActivityResultContracts.PickVisualMedia()) { uri ->
            val row = pendingGalleryRow
            pendingGalleryRow = null
            if (uri != null && row != null) {
                Bg.run {
                    val file = repo.imageStore.stageFromGallery(this@ItemEditActivity, uri)
                    runOnUiThread {
                        if (file != null) applyStagedImage(row, file)
                    }
                }
            }
        }

    /** 替换一行的暂存图：旧暂存文件丢弃，清除标记复位 */
    private fun applyStagedImage(row: AttrRow, file: File) {
        val oldStaged = row.stagedImage
        if (oldStaged != null && oldStaged != file) oldStaged.delete()
        row.stagedImage = file
        row.removeImage = false
        adapter.refreshRow(row)
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        vb = ActivityItemEditBinding.inflate(layoutInflater)
        setContentView(vb.root)
        Insets.apply(this)
        vb.toolbar.setNavigationOnClickListener { finish() }

        itemId = intent.getLongExtra(EXTRA_ITEM_ID, -1)
        categoryId = intent.getLongExtra(EXTRA_CATEGORY_ID, -1)
        vb.toolbar.setTitle(if (itemId > 0) R.string.item_edit_title else R.string.item_new_title)
        if (categoryId <= 0 && itemId <= 0) {
            finish()
            return
        }
        // 属性定义统一在仓库「属性设置」里维护，此页只填值
        vb.btnAddAttr.visibility = android.view.View.GONE

        adapter = AttrEditAdapter(repo.imageStore, this)
        vb.recyclerAttrs.layoutManager = LinearLayoutManager(this)
        vb.recyclerAttrs.adapter = adapter

        vb.btnSave.setOnClickListener { save() }
        vb.btnCategory.setOnClickListener { showCategoryPicker() }

        loadRows()
    }

    private fun loadRows() {
        runInBackground({
            val result: Triple<String, String, List<AttrRow>>? = if (itemId > 0) {
                val d = repo.getItemDetail(itemId)
                if (d == null) null else {
                    categoryId = d.item.categoryId
                    repo.warehouseIdOfCategory(categoryId)?.let { categories = repo.listCategories(it) }
                    Triple(
                        d.item.name, d.item.unit,
                        d.attrs.map { av ->
                            AttrRow(
                                defId = av.def.id,
                                name = av.def.name,
                                type = av.def.type,
                                options = av.def.options,
                                textValue = if (av.def.type == AttrType.TEXT || av.def.type == AttrType.NUMBER) av.value else "",
                                choiceValue = if (av.def.type == AttrType.CHOICE) av.value else "",
                                tagsValue = if (av.def.type == AttrType.TAGS) AttrOptions.decode(av.value).toMutableSet() else mutableSetOf(),
                                existingImage = if (av.def.type == AttrType.IMAGE) av.value else "",
                            )
                        }
                    )
                }
            } else {
                // 新建：按仓库定义生成空值行，单位默认「件」，可改为米、㎡、公斤等
                val whId = repo.warehouseIdOfCategory(categoryId)
                if (whId == null) null else {
                    categories = repo.listCategories(whId)
                    Triple(
                    "", getString(R.string.item_unit_default),
                    repo.listAttrDefs(whId).map { def ->
                        AttrRow(defId = def.id, name = def.name, type = def.type, options = def.options)
                    }
                    )
                }
            }
            result
        }) { result ->
            if (result == null) {
                finish()
                return@runInBackground
            }
            vb.inputName.setText(result.first)
            vb.inputUnit.setText(result.second)
            adapter.submit(result.third)
            updateCategoryButton()
        }
    }

    /** 所属类目按钮：显示当前归属，点击可切换（属性是仓库级，切换不影响下方属性行） */
    private fun updateCategoryButton() {
        vb.btnCategory.text = categories.firstOrNull { it.id == categoryId }?.name.orEmpty()
    }

    private fun showCategoryPicker() {
        if (categories.size <= 1) return
        PopupMenu(this, vb.btnCategory).apply {
            categories.forEach { menu.add(it.name) }
            setOnMenuItemClickListener { mi ->
                categories.firstOrNull { it.name == mi.title }?.let {
                    categoryId = it.id
                    updateCategoryButton()
                }
                true
            }
            show()
        }
    }

    // ---------------- AttrEditAdapter.Listener ----------------

    override fun onCamera(row: AttrRow) {
        val file = repo.imageStore.newCameraCaptureFile()
        val uri = FileProvider.getUriForFile(this, "${packageName}.fileprovider", file)
        pendingCameraRow = row
        pendingCameraFile = file
        takePicture.launch(uri)
    }

    override fun onGallery(row: AttrRow) {
        pendingGalleryRow = row
        pickImage.launch(
            PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly)
        )
    }

    // ---------------- 保存 ----------------

    private fun save() {
        val name = vb.inputName.text?.toString()?.trim().orEmpty()
        if (name.isEmpty()) {
            vb.layoutName.error = getString(R.string.item_name_required)
            return
        }
        val values = adapter.toValueInputs()
        runInBackground({
            repo.saveItem(
                if (itemId > 0) itemId else null, categoryId, name,
                vb.inputUnit.text?.toString()?.trim().orEmpty(),
                values,
            )
        }) {
            Toast.makeText(this, R.string.save_success, Toast.LENGTH_SHORT).show()
            finish()
        }
    }

    companion object {
        const val EXTRA_ITEM_ID = "extra_item_id"
        const val EXTRA_CATEGORY_ID = "extra_category_id"

        fun createIntent(context: Context, categoryId: Long): Intent =
            Intent(context, ItemEditActivity::class.java).putExtra(EXTRA_CATEGORY_ID, categoryId)

        fun editIntent(context: Context, itemId: Long, categoryId: Long): Intent =
            Intent(context, ItemEditActivity::class.java)
                .putExtra(EXTRA_ITEM_ID, itemId)
                .putExtra(EXTRA_CATEGORY_ID, categoryId)
    }
}
