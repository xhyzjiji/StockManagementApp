package com.example.stockmanagementsystem.ui

import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.ImageButton
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.TextView
import androidx.recyclerview.widget.RecyclerView
import com.example.stockmanagementsystem.R
import com.example.stockmanagementsystem.data.ImageStore
import com.example.stockmanagementsystem.data.ItemSummary
import com.example.stockmanagementsystem.util.Bitmaps
import com.example.stockmanagementsystem.util.Fmt
import com.example.stockmanagementsystem.util.TagColors

/**
 * 物品列表卡片，支持三种视图：
 * LIST 单行单列（默认）/ GRID 一行两列，均展示：名称、标签、数量·均价、在库天数；
 * THUMB 一行三个缩略图，只展示：缩略图、名称、标签。
 */
class ItemAdapter(
    private val imageStore: ImageStore,
    private val onClick: (ItemSummary) -> Unit,
    private val onLongClick: (ItemSummary) -> Unit,
    private val onStockIn: (ItemSummary) -> Unit,
) : RecyclerView.Adapter<ItemAdapter.VH>() {

    enum class ViewMode(val spanCount: Int) { LIST(1), GRID(2), THUMB(3) }

    var viewMode: ViewMode = ViewMode.LIST
        set(value) {
            if (field == value) return
            field = value
            notifyDataSetChanged()
        }

    private val data = ArrayList<ItemSummary>()

    fun submit(list: List<ItemSummary>) {
        data.clear()
        data.addAll(list)
        notifyDataSetChanged()
    }

    override fun getItemViewType(position: Int): Int = viewMode.ordinal

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): VH {
        val layout = when (ViewMode.entries[viewType]) {
            ViewMode.LIST -> R.layout.item_item_list
            ViewMode.GRID -> R.layout.item_item
            ViewMode.THUMB -> R.layout.item_item_thumb
        }
        return VH(LayoutInflater.from(parent.context).inflate(layout, parent, false))
    }

    override fun getItemCount(): Int = data.size

    override fun onBindViewHolder(holder: VH, position: Int) = holder.bind(data[position])

    inner class VH(root: View) : RecyclerView.ViewHolder(root) {
        private val ctx = root.context
        private val imageThumb: ImageView = root.findViewById(R.id.imageThumb)
        private val textName: TextView = root.findViewById(R.id.textName)
        private val layoutTags: LinearLayout = root.findViewById(R.id.layoutTags)
        /** 缩略图视图没有这两个字段 */
        private val textSpec: TextView? = root.findViewById(R.id.textSpec)
        private val textDate: TextView? = root.findViewById(R.id.textDate)
        /** 仅单列视图有：直接入库按钮 */
        private val btnStockIn: ImageButton? = root.findViewById(R.id.btnStockIn)

        fun bind(item: ItemSummary) {
            textName.text = item.name

            layoutTags.removeAllViews()
            item.tags.forEach { tag ->
                val chip = LayoutInflater.from(layoutTags.context)
                    .inflate(R.layout.item_tag_chip, layoutTags, false) as TextView
                chip.text = tag
                TagColors.applyStyle(chip, tag)
                layoutTags.addView(chip)
            }

            if (textSpec != null && textDate != null) {
                val priceText = if (item.unit.isEmpty()) {
                    ctx.getString(R.string.item_price_plain, Fmt.money(item.avgPrice))
                } else {
                    ctx.getString(R.string.item_price_unit, Fmt.money(item.avgPrice), item.unit)
                }
                textSpec.text = if (viewMode == ViewMode.LIST) {
                    ctx.getString(
                        R.string.item_spec_line,
                        Fmt.qtyWithUnit(item.quantity, item.unit),
                        priceText,
                        ctx.getString(R.string.item_price_plain, Fmt.money(item.totalValue)),
                    )
                } else {
                    val qtyText = Fmt.qtyWithUnit(item.quantity, item.unit) + " · " + priceText
                    if (item.attrSummary.isEmpty()) qtyText else "$qtyText · ${item.attrSummary}"
                }
                val since = item.stockSince
                textDate.text = if (since == null) {
                    ctx.getString(R.string.item_no_stock)
                } else {
                    ctx.getString(R.string.item_stock_days, Fmt.daysSince(since))
                }
            }

            val image = item.firstImage
            if (image != null) {
                Bitmaps.loadInto(
                    imageThumb, imageStore.fileOf(image),
                    if (viewMode == ViewMode.GRID) 320 else 160,
                )
            } else {
                imageThumb.setImageDrawable(null)
            }
            btnStockIn?.setOnClickListener { onStockIn(item) }
            itemView.setOnClickListener { onClick(item) }
            itemView.setOnLongClickListener { onLongClick(item); true }
        }
    }
}
