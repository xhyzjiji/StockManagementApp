package com.example.stockmanagementsystem.ui

import android.view.LayoutInflater
import android.view.ViewGroup
import androidx.recyclerview.widget.RecyclerView
import com.example.stockmanagementsystem.data.Warehouse
import com.example.stockmanagementsystem.databinding.ItemWarehouseBinding
import com.example.stockmanagementsystem.util.Fmt

class WarehouseAdapter(
    private val onClick: (Warehouse) -> Unit,
    private val onLongClick: (Warehouse) -> Unit,
) : RecyclerView.Adapter<WarehouseAdapter.VH>() {

    private val data = ArrayList<Warehouse>()

    fun submit(list: List<Warehouse>) {
        data.clear()
        data.addAll(list)
        notifyDataSetChanged()
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): VH = VH(
        ItemWarehouseBinding.inflate(LayoutInflater.from(parent.context), parent, false)
    )

    override fun getItemCount(): Int = data.size

    override fun onBindViewHolder(holder: VH, position: Int) = holder.bind(data[position])

    inner class VH(private val vb: ItemWarehouseBinding) : RecyclerView.ViewHolder(vb.root) {
        fun bind(w: Warehouse) {
            vb.textName.text = w.name
            vb.textRemark.text = w.remark
            vb.textRemark.visibility =
                if (w.remark.isEmpty()) android.view.View.GONE else android.view.View.VISIBLE
            vb.textCreated.text = Fmt.date(w.createdAt)
            vb.root.setOnClickListener { onClick(w) }
            vb.root.setOnLongClickListener { onLongClick(w); true }
        }
    }
}
