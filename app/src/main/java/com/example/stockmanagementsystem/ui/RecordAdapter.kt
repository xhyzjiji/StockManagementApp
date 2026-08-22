package com.example.stockmanagementsystem.ui

import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import androidx.recyclerview.widget.RecyclerView
import com.example.stockmanagementsystem.R
import com.example.stockmanagementsystem.data.StockRecord
import com.example.stockmanagementsystem.data.StockType
import com.example.stockmanagementsystem.databinding.ItemRecordBinding
import com.example.stockmanagementsystem.util.Fmt

class RecordAdapter(
    private val showItemName: Boolean = true,
) : RecyclerView.Adapter<RecordAdapter.VH>() {

    private val data = ArrayList<StockRecord>()

    fun submit(list: List<StockRecord>) {
        data.clear()
        data.addAll(list)
        notifyDataSetChanged()
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): VH = VH(
        ItemRecordBinding.inflate(LayoutInflater.from(parent.context), parent, false)
    )

    override fun getItemCount(): Int = data.size

    override fun onBindViewHolder(holder: VH, position: Int) = holder.bind(data[position])

    inner class VH(private val vb: ItemRecordBinding) : RecyclerView.ViewHolder(vb.root) {
        fun bind(r: StockRecord) {
            val ctx = vb.root.context
            if (r.type == StockType.IN) {
                vb.textBadge.setBackgroundResource(R.drawable.badge_in)
                vb.textBadge.text =
                    ctx.getString(R.string.stock_in_badge, Fmt.qtyWithUnit(r.quantity, r.unit))
            } else {
                vb.textBadge.setBackgroundResource(R.drawable.badge_out)
                vb.textBadge.text =
                    ctx.getString(R.string.stock_out_badge, Fmt.qtyWithUnit(r.quantity, r.unit))
            }
            vb.textItemName.text = r.itemName
            vb.textItemName.visibility = if (showItemName) View.VISIBLE else View.GONE
            vb.textTime.text = Fmt.time(r.createdAt)
            vb.textChange.text =
                ctx.getString(
                    R.string.stock_change,
                    Fmt.qtyWithUnit(r.beforeQty, r.unit),
                    Fmt.qtyWithUnit(r.afterQty, r.unit),
                )
            vb.textNote.text = r.note
            vb.textNote.visibility = if (r.note.isEmpty()) View.GONE else View.VISIBLE
        }
    }
}
