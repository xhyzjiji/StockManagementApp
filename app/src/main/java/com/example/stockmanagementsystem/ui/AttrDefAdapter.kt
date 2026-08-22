package com.example.stockmanagementsystem.ui

import android.view.LayoutInflater
import android.view.ViewGroup
import android.widget.PopupMenu
import androidx.recyclerview.widget.RecyclerView
import com.example.stockmanagementsystem.R
import com.example.stockmanagementsystem.data.AttrType
import com.example.stockmanagementsystem.databinding.ItemAttrDefRowBinding

/** 类目属性定义行（属性设置页） */
data class AttrDefRow(
    val defId: Long?,
    var name: String,
    var type: AttrType,
    var options: List<String>,
)

class AttrDefAdapter(
    private val onEdit: (AttrDefRow) -> Unit,
    private val onDelete: (AttrDefRow) -> Unit,
) : RecyclerView.Adapter<AttrDefAdapter.VH>() {

    val rows = ArrayList<AttrDefRow>()

    fun submit(list: List<AttrDefRow>) {
        rows.clear()
        rows.addAll(list)
        notifyDataSetChanged()
    }

    fun addRowDef(row: AttrDefRow) {
        rows.add(row)
        notifyItemInserted(rows.size - 1)
    }

    fun removeRow(row: AttrDefRow) {
        val idx = rows.indexOf(row)
        if (idx >= 0) {
            rows.removeAt(idx)
            notifyItemRemoved(idx)
        }
    }

    fun refreshRow(row: AttrDefRow) {
        val idx = rows.indexOf(row)
        if (idx >= 0) notifyItemChanged(idx)
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): VH = VH(
        ItemAttrDefRowBinding.inflate(LayoutInflater.from(parent.context), parent, false)
    )

    override fun getItemCount(): Int = rows.size

    override fun onBindViewHolder(holder: VH, position: Int) = holder.bind(rows[position])

    inner class VH(private val vb: ItemAttrDefRowBinding) : RecyclerView.ViewHolder(vb.root) {
        fun bind(row: AttrDefRow) {
            val ctx = vb.root.context
            vb.textName.text = row.name
            vb.textType.text = when (row.type) {
                AttrType.TEXT -> ctx.getString(R.string.attr_type_text)
                AttrType.NUMBER -> ctx.getString(R.string.attr_type_number)
                AttrType.CHOICE -> ctx.getString(R.string.attr_type_choice)
                AttrType.IMAGE -> ctx.getString(R.string.attr_type_image)
            }
            vb.textOptions.text = row.options.joinToString(" / ")
            vb.btnMore.setOnClickListener { anchor ->
                val popup = PopupMenu(anchor.context, anchor)
                popup.menu.add(R.string.attr_edit_def)
                popup.menu.add(R.string.action_delete)
                popup.setOnMenuItemClickListener { item ->
                    if (item.title == anchor.context.getString(R.string.attr_edit_def)) onEdit(row)
                    else onDelete(row)
                    true
                }
                popup.show()
            }
        }
    }
}
