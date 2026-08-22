package com.example.stockmanagementsystem.ui

import android.view.LayoutInflater
import android.view.ViewGroup
import androidx.recyclerview.widget.RecyclerView
import com.example.stockmanagementsystem.R
import com.example.stockmanagementsystem.data.ImageStore
import com.example.stockmanagementsystem.data.ItemSummary
import com.example.stockmanagementsystem.databinding.ItemItemBinding
import com.example.stockmanagementsystem.util.Bitmaps
import com.example.stockmanagementsystem.util.Fmt

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
            vb.textSummary.text = item.attrSummary
            vb.textSummary.visibility =
                if (item.attrSummary.isEmpty()) android.view.View.GONE else android.view.View.VISIBLE
            vb.textQty.text = vb.root.context
                .getString(R.string.item_stock_qty, Fmt.qtyWithUnit(item.quantity, item.unit))
            val image = item.firstImage
            if (image != null) {
                Bitmaps.loadInto(vb.imageThumb, imageStore.fileOf(image), 192)
            } else {
                vb.imageThumb.setImageDrawable(null)
            }
            vb.root.setOnClickListener { onClick(item) }
            vb.root.setOnLongClickListener { onLongClick(item); true }
        }
    }
}
