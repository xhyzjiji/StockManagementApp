package com.example.stockmanagementsystem

import android.content.Context
import android.content.Intent
import android.graphics.drawable.GradientDrawable
import android.os.Bundle
import android.view.Gravity
import android.view.View
import android.widget.LinearLayout
import android.widget.PopupMenu
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import com.example.stockmanagementsystem.data.AttributeDef
import com.example.stockmanagementsystem.data.AttrType
import com.example.stockmanagementsystem.data.ItemSummary
import com.example.stockmanagementsystem.data.Repository
import com.example.stockmanagementsystem.data.StockType
import com.example.stockmanagementsystem.data.TagValue
import com.example.stockmanagementsystem.databinding.ActivityWarehouseStatsBinding
import com.example.stockmanagementsystem.ui.chart.HeatmapView
import com.example.stockmanagementsystem.ui.chart.PieChartView
import com.example.stockmanagementsystem.util.Days
import com.example.stockmanagementsystem.util.Fmt
import com.example.stockmanagementsystem.util.Insets
import com.example.stockmanagementsystem.util.runInBackground
import java.util.Locale

/** 仓库数据统计：概览 / 出入库频率热力图 / 标签库存分布饼图 / 物品单价变化折线 */
class WarehouseStatsActivity : AppCompatActivity() {

    private lateinit var vb: ActivityWarehouseStatsBinding
    private val repo by lazy { Repository.get(this) }
    private var warehouseId: Long = -1
    private var items: List<ItemSummary> = emptyList()
    private var tagDefs: List<AttributeDef> = emptyList()
    private var tagValues: List<TagValue> = emptyList()
    private var selectedDefId: Long = -1
    private var groupByItem = false
    private var selectedItemId: Long = -1

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        vb = ActivityWarehouseStatsBinding.inflate(layoutInflater)
        setContentView(vb.root)
        Insets.apply(this)
        vb.toolbar.setNavigationOnClickListener { finish() }

        warehouseId = intent.getLongExtra(EXTRA_WAREHOUSE_ID, -1)
        if (warehouseId <= 0) {
            finish()
            return
        }
        vb.toolbar.title = getString(R.string.stats_title)
        vb.heatmapIn.palette = HeatmapView.GREENS
        vb.heatmapOut.palette = HeatmapView.REDS
        buildHeatLegend(vb.layoutHeatLegendIn, HeatmapView.GREENS)
        buildHeatLegend(vb.layoutHeatLegendOut, HeatmapView.REDS)
        vb.checkGroupByItem.setOnCheckedChangeListener { _, checked ->
            groupByItem = checked
            bindTagSection()
        }
    }

    override fun onResume() {
        super.onResume()
        reload()
    }

    private fun reload() {
        runInBackground({
            val loaded = repo.listItemsByWarehouse(warehouseId)
            val since = System.currentTimeMillis() - HeatmapView.WEEKS * 7 * Days.DAY_MS
            val times = repo.recordActivitySince(warehouseId, since)
            val defs = repo.listAttrDefs(warehouseId).filter { it.type == AttrType.TAGS }
            val values = repo.tagValuesForWarehouse(warehouseId)
            Triple(loaded, times, defs to values)
        }) { (loaded, times, tagData) ->
            if (isFinishing || isDestroyed) return@runInBackground
            items = loaded
            tagDefs = tagData.first
            tagValues = tagData.second
            bindOverview(loaded)
            vb.heatmapIn.submit(dayCountsOf(times, StockType.IN))
            vb.heatmapOut.submit(dayCountsOf(times, StockType.OUT))
            bindTagSection()
            bindPriceSection()
        }
    }

    /** 按天聚合一类流水（入/出）的笔数：本地纪元日 → 笔数 */
    private fun dayCountsOf(
        records: List<Pair<Long, String>>,
        type: StockType,
    ): Map<Long, Int> = records.asSequence()
        .filter { StockType.of(it.second) == type }
        .groupingBy { Days.localEpochDay(it.first) }
        .eachCount()

    // ---------------- 1. 概览 ----------------

    private fun bindOverview(list: List<ItemSummary>) {
        vb.textKinds.text = getString(R.string.stats_kinds_value, list.size)
        vb.textTotalValue.text = "¥" + Fmt.money(list.sumOf { it.totalValue })
    }

    // ---------------- 2. 出入库频率 ----------------

    /** 图例：少 □□□□□ 多（按对应热力图配色） */
    private fun buildHeatLegend(container: LinearLayout, palette: IntArray) {
        val d = resources.displayMetrics.density
        val less = TextView(this).apply {
            setText(R.string.stats_less)
            setTextColor(getColor(R.color.text_secondary))
            textSize = 11f
        }
        container.addView(less)
        palette.forEach { color ->
            val dot = View(this).apply {
                layoutParams = LinearLayout.LayoutParams((10 * d).toInt(), (10 * d).toInt())
                    .apply { marginStart = (4 * d).toInt() }
                background = GradientDrawable().apply {
                    setColor(color)
                    cornerRadius = 2 * d
                }
            }
            container.addView(dot)
        }
        val more = TextView(this).apply {
            setText(R.string.stats_more)
            setTextColor(getColor(R.color.text_secondary))
            textSize = 11f
            setPadding((4 * d).toInt(), 0, 0, 0)
        }
        container.addView(more)
    }

    // ---------------- 3. 标签类别分布 ----------------

    private fun bindTagSection() {
        selectedDefId = selectedDefId.takeIf { id -> tagDefs.any { it.id == id } }
            ?: tagDefs.firstOrNull()?.id ?: -1
        val def = tagDefs.firstOrNull { it.id == selectedDefId }
        if (def == null) {
            vb.btnPickTag.visibility = View.GONE
            vb.checkGroupByItem.visibility = View.GONE
            vb.pieChart.submit(emptyList())
            vb.layoutPieLegend.removeAllViews()
            vb.textPieEmpty.setText(R.string.stats_tag_empty)
            vb.textPieEmpty.visibility = View.VISIBLE
            return
        }
        vb.btnPickTag.visibility = View.VISIBLE
        vb.checkGroupByItem.visibility = View.VISIBLE
        vb.btnPickTag.text = def.name
        vb.btnPickTag.setOnClickListener { anchor ->
            PopupMenu(this, anchor, Gravity.END).apply {
                tagDefs.forEach { menu.add(it.name) }
                setOnMenuItemClickListener { mi ->
                    tagDefs.firstOrNull { it.name == mi.title }?.let {
                        selectedDefId = it.id
                        bindTagSection()
                    }
                    true
                }
                show()
            }
        }

        val itemById = items.associateBy { it.id }
        val quantities = LinkedHashMap<String, Double>()
        val qtyTexts = HashMap<String, String>()
        if (!groupByItem) {
            // 默认：按标签值聚合该字段下所有在库物品的剩余数量
            tagValues.filter { it.defId == def.id }.forEach { tv ->
                val item = itemById[tv.itemId] ?: return@forEach
                if (item.quantity <= 0) return@forEach
                tv.tags.forEach { tag ->
                    quantities[tag] = (quantities[tag] ?: 0.0) + item.quantity
                }
            }
            quantities.forEach { (tag, qty) -> qtyTexts[tag] = Fmt.qty(qty) }
        } else {
            // 按物品分组：该字段有值的物品各占一片
            tagValues.filter { it.defId == def.id }.forEach { tv ->
                val item = itemById[tv.itemId] ?: return@forEach
                if (item.quantity <= 0) return@forEach
                quantities[item.name] = (quantities[item.name] ?: 0.0) + item.quantity
                qtyTexts[item.name] = Fmt.qtyWithUnit(item.quantity, item.unit)
            }
        }
        val rows = quantities.entries.sortedByDescending { it.value }
        vb.pieChart.submit(rows.map { PieChartView.Slice(it.key, it.value) })
        buildPieLegend(rows.map { Triple(it.key, qtyTexts[it.key] ?: "", it.value) }, rows.sumOf { it.value })
        val empty = rows.isEmpty()
        vb.textPieEmpty.setText(R.string.stats_pie_empty)
        vb.textPieEmpty.visibility = if (empty) View.VISIBLE else View.GONE
    }

    /** rows：切片标签 + 数量文本 + 数值；totalQty 用于算占比 */
    private fun buildPieLegend(rows: List<Triple<String, String, Double>>, totalQty: Double) {
        vb.layoutPieLegend.removeAllViews()
        val d = resources.displayMetrics.density
        rows.forEachIndexed { i, (name, qtyText, value) ->
            val row = LinearLayout(this).apply {
                orientation = LinearLayout.HORIZONTAL
                gravity = Gravity.CENTER_VERTICAL
                setPadding(0, (2 * d).toInt(), 0, (2 * d).toInt())
            }
            val dot = View(this).apply {
                layoutParams = LinearLayout.LayoutParams((9 * d).toInt(), (9 * d).toInt())
                background = GradientDrawable().apply {
                    shape = GradientDrawable.OVAL
                    setColor(vb.pieChart.colorOf(i))
                }
            }
            row.addView(dot)
            val pct = if (totalQty > 0) value / totalQty * 100 else 0.0
            val label = TextView(this).apply {
                layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
                    .apply { marginStart = (8 * d).toInt() }
                text = getString(
                    R.string.stats_legend_share,
                    name,
                    qtyText,
                    String.format(Locale.getDefault(), "%.1f", pct),
                )
                setTextColor(getColor(R.color.text_secondary))
                textSize = 13f
                maxLines = 1
                ellipsize = android.text.TextUtils.TruncateAt.END
            }
            row.addView(label)
            vb.layoutPieLegend.addView(row)
        }
    }

    // ---------------- 4. 物品单价变化 ----------------

    private fun bindPriceSection() {
        if (items.isEmpty()) {
            vb.btnPickItem.visibility = View.GONE
            vb.lineChart.submit(emptyList())
            vb.textPriceEmpty.setText(R.string.stats_price_empty_items)
            vb.textPriceEmpty.visibility = View.VISIBLE
            return
        }
        vb.btnPickItem.visibility = View.VISIBLE
        if (items.none { it.id == selectedItemId }) selectedItemId = items.first().id
        val current = items.first { it.id == selectedItemId }
        vb.btnPickItem.text = current.name
        vb.btnPickItem.setOnClickListener { anchor ->
            PopupMenu(this, anchor, Gravity.END).apply {
                items.forEach { menu.add(it.name) }
                setOnMenuItemClickListener { mi ->
                    items.firstOrNull { it.name == mi.title }?.let {
                        selectedItemId = it.id
                        bindPriceSection()
                    }
                    true
                }
                show()
            }
        }
        runInBackground({ repo.pricedInRecordsForItem(selectedItemId) }) { points ->
            if (isFinishing || isDestroyed) return@runInBackground
            vb.lineChart.submit(points.map { it.time to it.price })
            val empty = points.isEmpty()
            vb.textPriceEmpty.setText(R.string.stats_price_no_records)
            vb.textPriceEmpty.visibility = if (empty) View.VISIBLE else View.GONE
        }
    }

    companion object {
        const val EXTRA_WAREHOUSE_ID = "extra_warehouse_id"

        fun intent(context: Context, warehouseId: Long): Intent =
            Intent(context, WarehouseStatsActivity::class.java).putExtra(EXTRA_WAREHOUSE_ID, warehouseId)
    }
}
