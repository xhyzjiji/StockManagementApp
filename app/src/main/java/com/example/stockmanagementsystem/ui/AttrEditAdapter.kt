package com.example.stockmanagementsystem.ui

import android.text.Editable
import android.text.TextWatcher
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.RadioButton
import androidx.recyclerview.widget.RecyclerView
import com.example.stockmanagementsystem.data.AttrOptions
import com.example.stockmanagementsystem.data.AttrType
import com.example.stockmanagementsystem.data.AttrValueInput
import com.example.stockmanagementsystem.data.ImageStore
import com.example.stockmanagementsystem.databinding.ItemAttrEditBinding
import com.example.stockmanagementsystem.util.Bitmaps
import com.google.android.material.chip.Chip
import java.io.File

/** 物品编辑页一行的值编辑状态（属性定义由类目统一管理，此处只填值） */
data class AttrRow(
    val defId: Long,
    val name: String,
    val type: AttrType,
    val options: List<String> = emptyList(),
    var textValue: String = "",
    var choiceValue: String = "",
    /** TAGS 类型的多选值（已选中的候选标签） */
    val tagsValue: MutableSet<String> = mutableSetOf(),
    var existingImage: String = "",
    var stagedImage: File? = null,
    var removeImage: Boolean = false,
)

class AttrEditAdapter(
    private val imageStore: ImageStore,
    private val listener: Listener,
) : RecyclerView.Adapter<AttrEditAdapter.VH>() {

    interface Listener {
        fun onCamera(row: AttrRow)
        fun onGallery(row: AttrRow)
    }

    val rows = ArrayList<AttrRow>()

    fun submit(list: List<AttrRow>) {
        rows.clear()
        rows.addAll(list)
        notifyDataSetChanged()
    }

    fun refreshRow(row: AttrRow) {
        val idx = rows.indexOf(row)
        if (idx >= 0) notifyItemChanged(idx)
    }

    fun toValueInputs(): List<AttrValueInput> = rows.map { r ->
        AttrValueInput(
            defId = r.defId,
            value = when (r.type) {
                AttrType.CHOICE -> r.choiceValue
                // 按候选顺序编码，保证存储/展示稳定
                AttrType.TAGS -> AttrOptions.encode(r.options.filter { it in r.tagsValue })
                else -> r.textValue
            },
            stagedImage = r.stagedImage,
            removeImage = r.removeImage,
        )
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): VH = VH(
        ItemAttrEditBinding.inflate(LayoutInflater.from(parent.context), parent, false)
    )

    override fun getItemCount(): Int = rows.size

    override fun onBindViewHolder(holder: VH, position: Int) = holder.bind(rows[position])

    inner class VH(private val vb: ItemAttrEditBinding) : RecyclerView.ViewHolder(vb.root) {

        private var textWatcher: TextWatcher? = null
        private var numberWatcher: TextWatcher? = null

        fun bind(row: AttrRow) {
            vb.textAttrName.text = row.name

            vb.layoutText.visibility = if (row.type == AttrType.TEXT) View.VISIBLE else View.GONE
            vb.layoutNumber.visibility = if (row.type == AttrType.NUMBER) View.VISIBLE else View.GONE
            vb.choiceGroup.visibility = if (row.type == AttrType.CHOICE) View.VISIBLE else View.GONE
            vb.tagsGroup.visibility = if (row.type == AttrType.TAGS) View.VISIBLE else View.GONE
            vb.layoutImage.visibility = if (row.type == AttrType.IMAGE) View.VISIBLE else View.GONE

            when (row.type) {
                AttrType.TEXT -> bindText(row, vb.inputText, isNumber = false)
                AttrType.NUMBER -> bindText(row, vb.inputNumber, isNumber = true)
                AttrType.CHOICE -> bindChoice(row)
                AttrType.TAGS -> bindTags(row)
                AttrType.IMAGE -> bindImage(row)
            }
        }

        private fun bindText(row: AttrRow, target: android.widget.EditText, isNumber: Boolean) {
            if (isNumber) {
                numberWatcher?.let { vb.inputNumber.removeTextChangedListener(it) }
            } else {
                textWatcher?.let { vb.inputText.removeTextChangedListener(it) }
            }
            if (target.text.toString() != row.textValue) target.setText(row.textValue)
            val watcher = object : TextWatcher {
                override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) = Unit
                override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) = Unit
                override fun afterTextChanged(s: Editable?) {
                    row.textValue = s?.toString().orEmpty()
                }
            }
            target.addTextChangedListener(watcher)
            if (isNumber) numberWatcher = watcher else textWatcher = watcher
        }

        private fun bindChoice(row: AttrRow) {
            val group = vb.choiceGroup
            group.setOnCheckedChangeListener(null)
            group.removeAllViews()
            row.options.forEach { opt ->
                val rb = RadioButton(group.context)
                rb.id = View.generateViewId()
                rb.text = opt
                rb.tag = opt
                group.addView(rb)
                if (opt == row.choiceValue) group.check(rb.id)
            }
            if (group.checkedRadioButtonId == -1) row.choiceValue = ""
            group.setOnCheckedChangeListener { g, checkedId ->
                val rb = g.findViewById<RadioButton>(checkedId)
                row.choiceValue = rb?.tag as? String ?: ""
            }
        }

        private fun bindTags(row: AttrRow) {
            val group = vb.tagsGroup
            group.removeAllViews()
            row.options.forEach { opt ->
                val chip = Chip(group.context).apply {
                    text = opt
                    isCheckable = true
                    isChecked = opt in row.tagsValue
                }
                chip.setOnCheckedChangeListener { _, checked ->
                    if (checked) row.tagsValue.add(opt) else row.tagsValue.remove(opt)
                }
                group.addView(chip)
            }
        }

        private fun bindImage(row: AttrRow) {
            val staged = row.stagedImage
            when {
                staged != null -> Bitmaps.loadInto(vb.imageThumb, staged, 144)
                row.existingImage.isNotEmpty() && !row.removeImage ->
                    Bitmaps.loadInto(vb.imageThumb, imageStore.fileOf(row.existingImage), 144)
                else -> vb.imageThumb.setImageDrawable(null)
            }
            vb.btnCamera.setOnClickListener { listener.onCamera(row) }
            vb.btnGallery.setOnClickListener { listener.onGallery(row) }
            vb.btnClearImage.setOnClickListener {
                row.stagedImage = null
                row.removeImage = true
                notifyItemChanged(rows.indexOf(row))
            }
        }
    }
}
