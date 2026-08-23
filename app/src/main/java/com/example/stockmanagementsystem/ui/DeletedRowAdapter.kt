package com.example.stockmanagementsystem.ui

import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import androidx.annotation.DrawableRes
import androidx.recyclerview.widget.RecyclerView
import com.example.stockmanagementsystem.R
import com.example.stockmanagementsystem.data.DeletedRow
import com.example.stockmanagementsystem.databinding.ItemDeletedRowBinding
import com.example.stockmanagementsystem.util.Fmt

/** 回收站行：图标 + 标题 + 副标题 + 删除时间 */
class DeletedRowAdapter(
    @DrawableRes private val iconRes: Int,
    private val onClick: (DeletedRow) -> Unit,
) : RecyclerView.Adapter<DeletedRowAdapter.VH>() {

    private val data = ArrayList<DeletedRow>()

    fun submit(list: List<DeletedRow>) {
        data.clear()
        data.addAll(list)
        notifyDataSetChanged()
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): VH = VH(
        ItemDeletedRowBinding.inflate(LayoutInflater.from(parent.context), parent, false)
    )

    override fun getItemCount(): Int = data.size

    override fun onBindViewHolder(holder: VH, position: Int) = holder.bind(data[position])

    inner class VH(private val vb: ItemDeletedRowBinding) : RecyclerView.ViewHolder(vb.root) {
        fun bind(row: DeletedRow) {
            vb.imageIcon.setImageResource(iconRes)
            vb.textTitle.text = row.title
            vb.textSubtitle.text = row.subtitle
            vb.textSubtitle.visibility =
                if (row.subtitle.isEmpty()) View.GONE else View.VISIBLE
            vb.textDeletedAt.text =
                vb.root.context.getString(R.string.deleted_at_prefix, Fmt.date(row.deletedAt))
            vb.root.setOnClickListener { onClick(row) }
        }
    }
}
