package com.example.stockmanagementsystem.ui

import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import androidx.recyclerview.widget.RecyclerView
import com.example.stockmanagementsystem.data.AttrType
import com.example.stockmanagementsystem.data.AttrWithValue
import com.example.stockmanagementsystem.data.ImageStore
import com.example.stockmanagementsystem.databinding.ItemAttrViewBinding
import com.example.stockmanagementsystem.util.Bitmaps

class AttrViewAdapter(
    private val imageStore: ImageStore,
    private val onImageClick: (String) -> Unit,
) : RecyclerView.Adapter<AttrViewAdapter.VH>() {

    private val data = ArrayList<AttrWithValue>()

    fun submit(list: List<AttrWithValue>) {
        data.clear()
        data.addAll(list)
        notifyDataSetChanged()
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): VH = VH(
        ItemAttrViewBinding.inflate(LayoutInflater.from(parent.context), parent, false)
    )

    override fun getItemCount(): Int = data.size

    override fun onBindViewHolder(holder: VH, position: Int) = holder.bind(data[position])

    inner class VH(private val vb: ItemAttrViewBinding) : RecyclerView.ViewHolder(vb.root) {
        fun bind(av: AttrWithValue) {
            vb.textAttrName.text = av.def.name
            val hasValue = av.value.isNotEmpty()
            if (av.def.type == AttrType.IMAGE) {
                vb.textAttrValue.visibility = View.GONE
                if (hasValue) {
                    vb.imageAttrValue.visibility = View.VISIBLE
                    Bitmaps.loadInto(vb.imageAttrValue, imageStore.fileOf(av.value), 720)
                    vb.imageAttrValue.setOnClickListener { onImageClick(av.value) }
                } else {
                    vb.imageAttrValue.visibility = View.GONE
                }
            } else {
                vb.imageAttrValue.visibility = View.GONE
                vb.textAttrValue.visibility = View.VISIBLE
                vb.textAttrValue.text = if (hasValue) av.value else "—"
            }
        }
    }
}
