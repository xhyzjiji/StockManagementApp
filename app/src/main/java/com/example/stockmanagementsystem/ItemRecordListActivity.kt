package com.example.stockmanagementsystem

import android.content.Context
import android.content.Intent
import android.os.Bundle
import androidx.appcompat.app.AppCompatActivity
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import com.example.stockmanagementsystem.data.Repository
import com.example.stockmanagementsystem.data.StockRecord
import com.example.stockmanagementsystem.databinding.ActivityItemRecordsBinding
import com.example.stockmanagementsystem.ui.RecordAdapter
import com.example.stockmanagementsystem.util.Insets
import com.example.stockmanagementsystem.util.runInBackground

/** 单个物品的全部出入库流水：滚动到底自动加载下一页（每页 [PAGE_SIZE] 条，新→旧） */
class ItemRecordListActivity : AppCompatActivity() {

    private lateinit var vb: ActivityItemRecordsBinding
    private val repo by lazy { Repository.get(this) }
    private lateinit var adapter: RecordAdapter
    private var itemId: Long = -1

    private val loaded = ArrayList<StockRecord>()
    private var hasMore = true
    private var loading = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        vb = ActivityItemRecordsBinding.inflate(layoutInflater)
        setContentView(vb.root)
        Insets.apply(this)
        vb.toolbar.setNavigationOnClickListener { finish() }

        itemId = intent.getLongExtra(EXTRA_ITEM_ID, -1)
        if (itemId <= 0) {
            finish()
            return
        }
        vb.toolbar.title = intent.getStringExtra(EXTRA_ITEM_NAME).orEmpty()
        vb.toolbar.subtitle = getString(R.string.record_title)

        adapter = RecordAdapter(showItemName = false)
        vb.recycler.layoutManager = LinearLayoutManager(this)
        vb.recycler.adapter = adapter
        vb.recycler.addOnScrollListener(object : RecyclerView.OnScrollListener() {
            override fun onScrolled(recyclerView: RecyclerView, dx: Int, dy: Int) {
                if (dy <= 0 || loading || !hasMore) return
                val lm = recyclerView.layoutManager as LinearLayoutManager
                if (lm.findLastVisibleItemPosition() >= adapter.itemCount - LOAD_AHEAD_REMAINING) {
                    loadNextPage()
                }
            }
        })

        loadNextPage()
    }

    private fun loadNextPage() {
        loading = true
        val offset = loaded.size
        runInBackground({ repo.listRecordsForItemPaged(itemId, offset, PAGE_SIZE) }) { page ->
            loading = false
            if (page.isEmpty()) {
                hasMore = false
                return@runInBackground
            }
            loaded.addAll(page)
            hasMore = page.size >= PAGE_SIZE
            adapter.submit(loaded.toList())
        }
    }

    companion object {
        const val EXTRA_ITEM_ID = "extra_item_id"
        const val EXTRA_ITEM_NAME = "extra_item_name"
        private const val PAGE_SIZE = 20
        private const val LOAD_AHEAD_REMAINING = 3

        fun intent(context: Context, itemId: Long, itemName: String): Intent =
            Intent(context, ItemRecordListActivity::class.java)
                .putExtra(EXTRA_ITEM_ID, itemId)
                .putExtra(EXTRA_ITEM_NAME, itemName)
    }
}
