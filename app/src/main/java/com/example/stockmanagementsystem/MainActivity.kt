package com.example.stockmanagementsystem

import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.text.Editable
import android.text.TextWatcher
import android.view.Gravity
import android.view.View
import android.widget.PopupMenu
import android.widget.Toast
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.recyclerview.widget.GridLayoutManager
import com.example.stockmanagementsystem.data.Category
import com.example.stockmanagementsystem.data.ItemSummary
import com.example.stockmanagementsystem.data.Repository
import com.example.stockmanagementsystem.data.StockMath
import com.example.stockmanagementsystem.data.StockType
import com.example.stockmanagementsystem.databinding.ActivityMainBinding
import com.example.stockmanagementsystem.ui.Dialogs
import com.example.stockmanagementsystem.ui.ItemAdapter
import com.example.stockmanagementsystem.util.Fmt
import com.example.stockmanagementsystem.util.Insets
import com.example.stockmanagementsystem.util.runInBackground
import com.google.android.material.chip.Chip

/** 仓库主页：物品总览（搜索 + 类目 chips 筛选 + 全部物品网格） */
class MainActivity : AppCompatActivity() {

    private lateinit var vb: ActivityMainBinding
    private val repo by lazy { Repository.get(this) }
    private lateinit var adapter: ItemAdapter
    private var warehouseId: Long = -1

    private var categories: List<Category> = emptyList()
    private var allItems: List<ItemSummary> = emptyList()
    /** null 表示「全部」 */
    private var selectedCategoryId: Long? = null
    private var searchByTag = false
    private var sortMode = ItemSort.DEFAULT
    private var viewMode = ItemAdapter.ViewMode.LIST
    private val prefs by lazy { getPreferences(MODE_PRIVATE) }

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

        adapter = ItemAdapter(
            imageStore = repo.imageStore,
            onClick = { item -> startActivity(ItemDetailActivity.intent(this, item.id)) },
            onLongClick = { item -> showItemOps(item.id, item.categoryId, item.name) },
            onStockIn = { item -> showQuickStockIn(item) },
        )
        viewMode = prefs.getString(KEY_VIEW_MODE, null)
            ?.let { runCatching { ItemAdapter.ViewMode.valueOf(it) }.getOrNull() }
            ?: ItemAdapter.ViewMode.LIST
        adapter.viewMode = viewMode
        vb.recycler.layoutManager = GridLayoutManager(this, viewMode.spanCount)
        vb.recycler.adapter = adapter

        vb.btnSearchMode.setOnClickListener { showSearchModeMenu() }
        vb.inputSearch.addTextChangedListener(object : TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) = Unit
            override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) = Unit
            override fun afterTextChanged(s: Editable?) = applyFilter()
        })

        vb.toolbar.setOnMenuItemClickListener { item ->
            when (item.itemId) {
                R.id.action_attrs -> {
                    startActivity(
                        WarehouseAttrsActivity.intent(
                            this, warehouseId, vb.toolbar.title?.toString().orEmpty()
                        )
                    )
                    true
                }
                R.id.action_records -> {
                    startActivity(RecordListActivity.intent(this, warehouseId))
                    true
                }
                R.id.action_sort -> {
                    showSortMenu()
                    true
                }
                R.id.action_view -> {
                    showViewMenu()
                    true
                }
                R.id.action_recycle_bin -> {
                    startActivity(
                        RecycleBinActivity.itemBinIntent(
                            this, warehouseId, vb.toolbar.title?.toString().orEmpty()
                        )
                    )
                    true
                }
                R.id.action_rename_warehouse -> {
                    showWarehouseDialog()
                    true
                }
                else -> false
            }
        }

        vb.fabAdd.setOnClickListener { showAddItemTargetPicker() }
    }

    override fun onResume() {
        super.onResume()
        reload()
    }

    private fun reload() {
        runInBackground({
            Triple(
                repo.getWarehouse(warehouseId)?.name,
                repo.listCategories(warehouseId),
                repo.listItemsByWarehouse(warehouseId),
            )
        }) { (name, cats, items) ->
            if (name == null) {
                finish()
                return@runInBackground
            }
            vb.toolbar.title = name
            categories = cats
            allItems = items
            if (selectedCategoryId != null && cats.none { it.id == selectedCategoryId }) {
                selectedCategoryId = null
            }
            rebuildCategoryChips()
            applyFilter()
        }
    }

    // ---------------- 类目 chips ----------------

    private fun rebuildCategoryChips() {
        val group = vb.chipGroupFilter
        group.setOnCheckedStateChangeListener(null)
        group.removeAllViews()

        val allChip = makeChip(getString(R.string.filter_all), null)
        group.addView(allChip)
        categories.forEach { c -> group.addView(makeChip(c.name, c.id)) }

        val addChip = Chip(this).apply {
            text = getString(R.string.category_add_chip)
            isCheckable = false
            setOnClickListener { showCreateCategoryDialog() }
        }
        group.addView(addChip)

        group.setOnCheckedStateChangeListener { g, checkedIds ->
            val chip = checkedIds.firstOrNull()?.let { g.findViewById<Chip>(it) }
            selectedCategoryId = chip?.tag as? Long
            applyFilter()
        }
        restoreChipSelection(allChip)
    }

    private fun makeChip(label: String, categoryId: Long?): Chip =
        Chip(this).apply {
            text = label
            isCheckable = true
            tag = categoryId
            id = View.generateViewId()
            if (categoryId != null) {
                setOnLongClickListener { showCategoryOps(categoryId, label); true }
            }
        }

    /** 重建 chips 后恢复选中态 */
    private fun restoreChipSelection(allChip: Chip) {
        val selected = selectedCategoryId
        val target = if (selected == null) {
            allChip
        } else {
            val group = vb.chipGroupFilter
            (0 until group.childCount)
                .mapNotNull { group.getChildAt(it) as? Chip }
                .firstOrNull { it.tag as? Long == selected } ?: allChip
        }
        vb.chipGroupFilter.check(target.id)
    }

    // ---------------- 过滤 ----------------

    private fun applyFilter() {
        val selected = selectedCategoryId
        val base = if (selected == null) allItems else allItems.filter { it.categoryId == selected }
        val q = vb.inputSearch.text?.toString()?.trim().orEmpty()
        val filtered = if (q.isEmpty()) base else base.filter { item ->
            if (searchByTag) {
                item.tags.any { it.contains(q, ignoreCase = true) }
            } else {
                item.name.contains(q, ignoreCase = true)
            }
        }
        adapter.submit(sortedOf(filtered))
        vb.textEmpty.visibility = if (filtered.isEmpty()) View.VISIBLE else View.GONE
    }

    /** 按当前排序模式排序；无库存（无在库起点）的在按天数排序时排最后 */
    private fun sortedOf(list: List<ItemSummary>): List<ItemSummary> = when (sortMode) {
        ItemSort.DEFAULT -> list
        ItemSort.DAYS_DESC -> {
            val now = System.currentTimeMillis()
            list.sortedByDescending { it.stockSince?.let { s -> Fmt.daysSince(s, now) } ?: -1L }
        }
        ItemSort.DAYS_ASC -> {
            val now = System.currentTimeMillis()
            list.sortedBy { it.stockSince?.let { s -> Fmt.daysSince(s, now) } ?: Long.MAX_VALUE }
        }
    }

    private fun showSortMenu() {
        val byDefault = getString(R.string.sort_default)
        val daysDesc = getString(R.string.sort_days_desc)
        val daysAsc = getString(R.string.sort_days_asc)
        PopupMenu(this, vb.toolbar).apply {
            menu.add(byDefault)
            menu.add(daysDesc)
            menu.add(daysAsc)
            setOnMenuItemClickListener { mi ->
                sortMode = when (mi.title) {
                    daysDesc -> ItemSort.DAYS_DESC
                    daysAsc -> ItemSort.DAYS_ASC
                    else -> ItemSort.DEFAULT
                }
                applyFilter()
                true
            }
            show()
        }
    }

    private fun showViewMenu() {
        val toList = getString(R.string.view_list)
        val toGrid = getString(R.string.view_grid)
        val toThumb = getString(R.string.view_thumb)
        // Toolbar 横跨整宽，END 对齐让弹窗落在右侧菜单按钮下方而不是页面左上角
        PopupMenu(this, vb.toolbar, Gravity.END).apply {
            menu.add(toList)
            menu.add(toGrid)
            menu.add(toThumb)
            setOnMenuItemClickListener { mi ->
                viewMode = when (mi.title) {
                    toGrid -> ItemAdapter.ViewMode.GRID
                    toThumb -> ItemAdapter.ViewMode.THUMB
                    else -> ItemAdapter.ViewMode.LIST
                }
                adapter.viewMode = viewMode
                (vb.recycler.layoutManager as? GridLayoutManager)?.spanCount = viewMode.spanCount
                prefs.edit().putString(KEY_VIEW_MODE, viewMode.name).apply()
                true
            }
            show()
        }
    }

    private fun showSearchModeMenu() {
        val byName = getString(R.string.search_mode_by_name)
        val byTag = getString(R.string.search_mode_by_tag)
        PopupMenu(this, vb.btnSearchMode).apply {
            menu.add(byName)
            menu.add(byTag)
            setOnMenuItemClickListener { mi ->
                searchByTag = mi.title == byTag
                vb.btnSearchMode.text = mi.title
                vb.layoutSearch.hint = getString(
                    if (searchByTag) R.string.item_search_hint_tag else R.string.item_search_hint_name
                )
                applyFilter()
                true
            }
            show()
        }
    }

    // ---------------- 新建 ----------------

    // ---------------- 快捷入库（单列视图 + 按钮） ----------------

    /** 列表直接入库：与详情页同一套校验（必填总价；老库存未定价时先选计价方式） */
    private fun showQuickStockIn(item: ItemSummary) {
        Dialogs.stockOp(this, true, item.name, item.quantity, item.unit) { qty, price, note ->
            if (item.quantity > 0 && item.totalValue <= 0.0) {
                Dialogs.unpricedPricing(this, item.quantity, item.unit) { pricing, corrected ->
                    doQuickStockIn(item.id, qty, price, note, pricing, corrected)
                }
            } else {
                doQuickStockIn(item.id, qty, price, note, StockMath.InPricing.WEIGHTED, null)
            }
        }
    }

    private fun doQuickStockIn(
        itemId: Long,
        qty: Double,
        price: Double?,
        note: String,
        pricing: StockMath.InPricing,
        correctedValue: Double?,
    ) {
        runInBackground({
            repo.applyStock(itemId, StockType.IN, qty, price, note, pricing, correctedValue)
            Unit
        }) {
            Toast.makeText(this, R.string.stock_in_done, Toast.LENGTH_SHORT).show()
            reload()
        }
    }

    /** 选中具体类目时直接建物品；「全部」时先选目标类目 */
    private fun showAddItemTargetPicker() {
        val selected = selectedCategoryId
        if (selected != null) {
            startActivity(ItemEditActivity.createIntent(this, selected))
            return
        }
        if (categories.isEmpty()) {
            Toast.makeText(this, R.string.overview_need_category, Toast.LENGTH_SHORT).show()
            return
        }
        PopupMenu(this, vb.fabAdd).apply {
            categories.forEach { menu.add(it.name) }
            setOnMenuItemClickListener { mi ->
                categories.firstOrNull { it.name == mi.title }?.let {
                    startActivity(ItemEditActivity.createIntent(this@MainActivity, it.id))
                }
                true
            }
            show()
        }
    }

    private fun showCreateCategoryDialog() {
        Dialogs.inputText(this, R.string.category_add, R.string.category_name_hint) { name ->
            runInBackground({ repo.createCategory(warehouseId, name) }) { reload() }
        }
    }

    // ---------------- 长按操作 ----------------

    private fun showItemOps(itemId: Long, categoryId: Long, name: String) {
        AlertDialog.Builder(this)
            .setTitle(name)
            .setItems(arrayOf(getString(R.string.action_edit), getString(R.string.action_delete))) { _, which ->
                when (which) {
                    0 -> startActivity(ItemEditActivity.editIntent(this, itemId, categoryId))
                    1 -> Dialogs.confirm(this, getString(R.string.item_delete_confirm, name)) {
                        runInBackground({ repo.softDeleteItem(itemId) }) {
                            Toast.makeText(this, R.string.moved_to_bin, Toast.LENGTH_SHORT).show()
                            reload()
                        }
                    }
                }
            }
            .show()
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

    private fun showWarehouseDialog() {
        runInBackground({ repo.getWarehouse(warehouseId) }) { w ->
            if (w != null) {
                Dialogs.warehouse(this, R.string.menu_rename_warehouse, w.name, w.remark) { name, remark ->
                    runInBackground({ repo.updateWarehouse(warehouseId, name, remark); Unit }) { reload() }
                }
            }
        }
    }

    companion object {
        const val EXTRA_WAREHOUSE_ID = "extra_warehouse_id"
        private const val KEY_VIEW_MODE = "item_view_mode"

        fun intent(context: Context, warehouseId: Long): Intent =
            Intent(context, MainActivity::class.java).putExtra(EXTRA_WAREHOUSE_ID, warehouseId)
    }

    /** 物品列表排序：默认录入新→旧；或按在库天数 */
    private enum class ItemSort { DEFAULT, DAYS_DESC, DAYS_ASC }
}
