package com.example.stockmanagementsystem

import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.text.Editable
import android.text.TextWatcher
import android.view.View
import android.widget.PopupMenu
import android.widget.Toast
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.recyclerview.widget.GridLayoutManager
import com.example.stockmanagementsystem.data.Repository
import com.example.stockmanagementsystem.data.ItemSummary
import com.example.stockmanagementsystem.util.Insets
import com.example.stockmanagementsystem.databinding.ActivityItemListBinding
import com.example.stockmanagementsystem.ui.Dialogs
import com.example.stockmanagementsystem.ui.ItemAdapter
import com.example.stockmanagementsystem.util.runInBackground

class ItemListActivity : AppCompatActivity() {

    private lateinit var vb: ActivityItemListBinding
    private val repo by lazy { Repository.get(this) }
    private lateinit var adapter: ItemAdapter
    private var categoryId: Long = -1
    private var allItems: List<ItemSummary> = emptyList()
    /** false=按名称过滤；true=按标签过滤 */
    private var searchByTag = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        vb = ActivityItemListBinding.inflate(layoutInflater)
        setContentView(vb.root)
        Insets.apply(this)
        vb.toolbar.setNavigationOnClickListener { finish() }

        categoryId = intent.getLongExtra(EXTRA_CATEGORY_ID, -1)
        val categoryName = intent.getStringExtra(EXTRA_CATEGORY_NAME).orEmpty()
        vb.toolbar.title = categoryName
        if (categoryId <= 0) {
            finish()
            return
        }
        vb.toolbar.setOnMenuItemClickListener { item ->
            when (item.itemId) {
                R.id.action_attrs -> {
                    startActivity(CategoryAttrsActivity.intent(this, categoryId, categoryName))
                    true
                }
                else -> false
            }
        }

        adapter = ItemAdapter(
            imageStore = repo.imageStore,
            onClick = { item -> startActivity(ItemDetailActivity.intent(this, item.id)) },
            onLongClick = { item -> showItemOps(item.id, item.name) },
        )
        vb.recycler.layoutManager = GridLayoutManager(this, 2)
        vb.recycler.adapter = adapter

        vb.btnSearchMode.setOnClickListener { showSearchModeMenu() }
        vb.inputSearch.addTextChangedListener(object : TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) = Unit
            override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) = Unit
            override fun afterTextChanged(s: Editable?) = applyFilter()
        })

        vb.fabAdd.setOnClickListener {
            startActivity(ItemEditActivity.createIntent(this, categoryId))
        }
    }

    override fun onResume() {
        super.onResume()
        reload()
    }

    private fun reload() {
        runInBackground({ repo.listItems(categoryId) }) { list ->
            allItems = list
            applyFilter()
        }
    }

    /** 按所选维度（名称或标签）本地过滤 */
    private fun applyFilter() {
        val q = vb.inputSearch.text?.toString()?.trim().orEmpty()
        val filtered = if (q.isEmpty()) allItems else allItems.filter { item ->
            if (searchByTag) {
                item.tags.any { it.contains(q, ignoreCase = true) }
            } else {
                item.name.contains(q, ignoreCase = true)
            }
        }
        adapter.submit(filtered)
        vb.textEmpty.visibility = if (filtered.isEmpty()) View.VISIBLE else View.GONE
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

    private fun showItemOps(itemId: Long, name: String) {
        AlertDialog.Builder(this)
            .setTitle(name)
            .setItems(arrayOf(getString(R.string.action_edit), getString(R.string.action_delete))) { _, which ->
                when (which) {
                    0 -> startActivity(ItemEditActivity.editIntent(this, itemId, categoryId))
                    1 -> Dialogs.confirm(this, getString(R.string.item_delete_confirm, name)) {
                        runInBackground({ repo.deleteItem(itemId); Unit }) {
                            Toast.makeText(this, R.string.deleted, Toast.LENGTH_SHORT).show()
                            reload()
                        }
                    }
                }
            }
            .show()
    }

    companion object {
        const val EXTRA_CATEGORY_ID = "extra_category_id"
        const val EXTRA_CATEGORY_NAME = "extra_category_name"

        fun intent(context: Context, categoryId: Long, categoryName: String): Intent =
            Intent(context, ItemListActivity::class.java)
                .putExtra(EXTRA_CATEGORY_ID, categoryId)
                .putExtra(EXTRA_CATEGORY_NAME, categoryName)
    }
}
