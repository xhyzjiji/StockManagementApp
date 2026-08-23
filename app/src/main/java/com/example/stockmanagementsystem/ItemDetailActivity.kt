package com.example.stockmanagementsystem

import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.recyclerview.widget.LinearLayoutManager
import com.example.stockmanagementsystem.data.AttrOptions
import com.example.stockmanagementsystem.data.AttrType
import com.example.stockmanagementsystem.data.AttrWithValue
import com.example.stockmanagementsystem.data.InsufficientStockException
import com.example.stockmanagementsystem.data.ItemDetail
import com.example.stockmanagementsystem.data.Repository
import com.example.stockmanagementsystem.data.StockType
import com.example.stockmanagementsystem.databinding.ActivityItemDetailBinding
import com.example.stockmanagementsystem.ui.AttrViewAdapter
import com.example.stockmanagementsystem.ui.Dialogs
import com.example.stockmanagementsystem.ui.RecordAdapter
import com.example.stockmanagementsystem.util.Bitmaps
import com.example.stockmanagementsystem.util.Bg
import com.example.stockmanagementsystem.util.Insets
import com.example.stockmanagementsystem.util.Fmt
import com.example.stockmanagementsystem.util.runInBackground

/** 物品详情：属性展示（含参考图）、库存数字、入库/出库入口、该物品流水 */
class ItemDetailActivity : AppCompatActivity() {

    private lateinit var vb: ActivityItemDetailBinding
    private val repo by lazy { Repository.get(this) }
    private lateinit var attrAdapter: AttrViewAdapter
    private lateinit var recordAdapter: RecordAdapter
    private var itemId: Long = -1
    private var detail: ItemDetail? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        vb = ActivityItemDetailBinding.inflate(layoutInflater)
        setContentView(vb.root)
        Insets.apply(this)
        vb.toolbar.setNavigationOnClickListener { finish() }
        vb.toolbar.setOnMenuItemClickListener { item ->
            when (item.itemId) {
                R.id.action_edit -> {
                    detail?.let {
                        startActivity(ItemEditActivity.editIntent(this, itemId, it.item.categoryId))
                    }
                    true
                }
                else -> false
            }
        }

        itemId = intent.getLongExtra(EXTRA_ITEM_ID, -1)
        if (itemId <= 0) {
            finish()
            return
        }

        attrAdapter = AttrViewAdapter(repo.imageStore) { rel ->
            Dialogs.imagePreview(this, repo.imageStore.fileOf(rel))
        }
        vb.recyclerAttrs.layoutManager = LinearLayoutManager(this)
        vb.recyclerAttrs.adapter = attrAdapter

        recordAdapter = RecordAdapter(showItemName = false)
        vb.recyclerRecords.layoutManager = LinearLayoutManager(this)
        vb.recyclerRecords.adapter = recordAdapter

        vb.btnStockIn.setOnClickListener { showStockDialog(isIn = true) }
        vb.btnStockOut.setOnClickListener { showStockDialog(isIn = false) }
    }

    override fun onResume() {
        super.onResume()
        reload()
    }

    private fun reload() {
        runInBackground({
            Triple(
                repo.getItemDetail(itemId),
                repo.listRecordsForItemPaged(itemId, offset = 0, limit = RECENT_LIMIT),
                repo.countRecordsForItem(itemId),
            )
        }) { (d, records, total) ->
            if (d == null) {
                finish()
                return@runInBackground
            }
            detail = d
            vb.toolbar.title = d.item.name
            vb.textQty.text = Fmt.qtyWithUnit(d.item.quantity, d.item.unit)
            bindHeroAndTags(d)
            attrAdapter.submit(listContentOf(d))
            recordAdapter.submit(records)
            if (total > records.size) {
                vb.btnAllRecords.visibility = View.VISIBLE
                vb.btnAllRecords.text = getString(R.string.record_view_all, total)
                vb.btnAllRecords.setOnClickListener {
                    startActivity(ItemRecordListActivity.intent(this, itemId, d.item.name))
                }
            } else {
                vb.btnAllRecords.visibility = View.GONE
            }
        }
    }

    /** 首个有值的图片属性提升为顶部大图；所有标签属性值合并为图片下方的 pills */
    private fun bindHeroAndTags(d: ItemDetail) {
        val heroAttr = d.attrs.firstOrNull { it.def.type == AttrType.IMAGE && it.value.isNotEmpty() }
        if (heroAttr != null) {
            vb.imageHero.visibility = View.VISIBLE
            Bitmaps.loadInto(vb.imageHero, repo.imageStore.fileOf(heroAttr.value), 720)
            vb.imageHero.setOnClickListener {
                Dialogs.imagePreview(this, repo.imageStore.fileOf(heroAttr.value))
            }
        } else {
            vb.imageHero.visibility = View.GONE
        }

        val tags = LinkedHashSet<String>().apply {
            d.attrs.filter { it.def.type == AttrType.TAGS }.forEach { addAll(AttrOptions.decode(it.value)) }
        }
        vb.layoutTags.removeAllViews()
        tags.forEach { tag ->
            val chip = LayoutInflater.from(this)
                .inflate(R.layout.item_tag_chip, vb.layoutTags, false) as TextView
            chip.text = tag
            vb.layoutTags.addView(chip)
        }
        vb.scrollTags.visibility = if (tags.isEmpty()) View.GONE else View.VISIBLE
    }

    /** 属性列表内容：去掉已提升为大图的图片属性与标签属性（都以 pills 展示） */
    private fun listContentOf(d: ItemDetail): List<AttrWithValue> {
        val heroDefId = d.attrs
            .firstOrNull { it.def.type == AttrType.IMAGE && it.value.isNotEmpty() }?.def?.id
        return d.attrs.filter { it.def.type != AttrType.TAGS && it.def.id != heroDefId }
    }

    private fun showStockDialog(isIn: Boolean) {
        val d = detail ?: return
        Dialogs.stockOp(this, isIn, d.item.name, d.item.quantity, d.item.unit) { qty, note ->
            Bg.run {
                val error = try {
                    repo.applyStock(itemId, if (isIn) StockType.IN else StockType.OUT, qty, note)
                    null
                } catch (e: InsufficientStockException) {
                    e
                }
                runOnUiThread {
                    if (isFinishing || isDestroyed) return@runOnUiThread
                    if (error != null) {
                        Toast.makeText(
                            this,
                            getString(
                                R.string.stock_insufficient,
                                Fmt.qtyWithUnit(error.available, d.item.unit)
                            ),
                            Toast.LENGTH_SHORT
                        ).show()
                    } else {
                        Toast.makeText(
                            this,
                            if (isIn) R.string.stock_in_done else R.string.stock_out_done,
                            Toast.LENGTH_SHORT
                        ).show()
                        reload()
                    }
                }
            }
        }
    }

    companion object {
        const val EXTRA_ITEM_ID = "extra_item_id"
        private const val RECENT_LIMIT = 5

        fun intent(context: Context, itemId: Long): Intent =
            Intent(context, ItemDetailActivity::class.java).putExtra(EXTRA_ITEM_ID, itemId)
    }
}
