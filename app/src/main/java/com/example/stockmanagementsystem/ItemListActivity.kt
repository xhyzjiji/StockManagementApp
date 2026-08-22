package com.example.stockmanagementsystem

import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.view.View
import android.widget.Toast
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.recyclerview.widget.LinearLayoutManager
import com.example.stockmanagementsystem.data.Repository
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
        vb.recycler.layoutManager = LinearLayoutManager(this)
        vb.recycler.adapter = adapter

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
            adapter.submit(list)
            vb.textEmpty.visibility = if (list.isEmpty()) View.VISIBLE else View.GONE
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
