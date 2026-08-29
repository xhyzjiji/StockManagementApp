package com.example.stockmanagementsystem.ui

import android.view.LayoutInflater
import android.view.ViewGroup
import android.widget.TextView
import androidx.recyclerview.widget.RecyclerView
import com.example.stockmanagementsystem.R
import com.example.stockmanagementsystem.data.ImageStore
import com.example.stockmanagementsystem.data.ItemSummary
import com.example.stockmanagementsystem.databinding.ItemItemBinding
import com.example.stockmanagementsystem.util.Bitmaps
import com.example.stockmanagementsystem.util.Fmt
import com.example.stockmanagementsystem.util.TagColors

/** 物品网格卡片：大图 + 名称 + 标签 chips + 数量·摘要 + 日期 */
class ItemAdapter(
    private val imageStore: ImageStore,
    private val onClick: (ItemSummary) -> Unit,
    private val onLongClick: (ItemSummary) -> Unit,
) : RecyclerView.Adapter<ItemAdapter.VH>() {

    private val data = ArrayList<ItemSummary>()

    fun submit(list: List<ItemSummary>) {
        data.clear()
        data.addAll(list)
        notifyDataSetChanged()
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): VH = VH(
        ItemItemBinding.inflate(LayoutInflater.from(parent.context), parent, false)
    )

    override fun getItemCount(): Int = data.size

    override fun onBindViewHolder(holder: VH, position: Int) = holder.bind(data[position])

    inner class VH(private val vb: ItemItemBinding) : RecyclerView.ViewHolder(vb.root) {
        fun bind(item: ItemSummary) {
            vb.textName.text = item.name

            vb.layoutTags.removeAllViews()
            item.tags.forEach { tag ->
                val chip = LayoutInflater.from(vb.layoutTags.context)
                    .inflate(R.layout.item_tag_chip, vb.layoutTags, false) as TextView
                chip.text = tag
                TagColors.applyStyle(chip, tag)
                vb.layoutTags.addView(chip)
            }

            val priceText = if (item.unit.isEmpty()) {
                vb.root.context.getString(R.string.item_price_plain, Fmt.money(item.avgPrice))
            } else {
                vb.root.context.getString(R.string.item_price_unit, Fmt.money(item.avgPrice), item.unit)
            }
            val qtyText = Fmt.qtyWithUnit(item.quantity, item.unit) + " · " + priceText
            vb.textSpec.text = if (item.attrSummary.isEmpty()) qtyText
            else "$qtyText · ${item.attrSummary}"
            val since = item.stockSince
            vb.textDate.text = if (since == null) {
                vb.root.context.getString(R.string.item_no_stock)
            } else {
                vb.root.context.getString(R.string.item_stock_days, Fmt.daysSince(since))
            }

            val image = item.firstImage
            if (image != null) {
                Bitmaps.loadInto(vb.imageThumb, imageStore.fileOf(image), 320)
            } else {
                vb.imageThumb.setImageDrawable(null)
            }
            vb.root.setOnClickListener { onClick(item) }
            vb.root.setOnLongClickListener { onLongClick(item); true }
        }
    }
}
