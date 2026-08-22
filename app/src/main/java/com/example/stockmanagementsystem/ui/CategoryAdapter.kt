package com.example.stockmanagementsystem.ui

import android.view.LayoutInflater
import android.view.ViewGroup
import androidx.recyclerview.widget.RecyclerView
import com.example.stockmanagementsystem.R
import com.example.stockmanagementsystem.data.Category
import com.example.stockmanagementsystem.databinding.ItemCategoryBinding

class CategoryAdapter(
    private val onClick: (Category) -> Unit,
    private val onLongClick: (Category) -> Unit,
) : RecyclerView.Adapter<CategoryAdapter.VH>() {

    private val data = ArrayList<Category>()

    fun submit(list: List<Category>) {
        data.clear()
        data.addAll(list)
        notifyDataSetChanged()
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): VH = VH(
        ItemCategoryBinding.inflate(LayoutInflater.from(parent.context), parent, false)
    )

    override fun getItemCount(): Int = data.size

    override fun onBindViewHolder(holder: VH, position: Int) = holder.bind(data[position])

    inner class VH(private val vb: ItemCategoryBinding) : RecyclerView.ViewHolder(vb.root) {
        fun bind(c: Category) {
            vb.textName.text = c.name
            vb.textCount.text = vb.root.context.getString(R.string.category_item_count, c.itemCount)
            vb.root.setOnClickListener { onClick(c) }
            vb.root.setOnLongClickListener { onLongClick(c); true }
        }
    }
}
