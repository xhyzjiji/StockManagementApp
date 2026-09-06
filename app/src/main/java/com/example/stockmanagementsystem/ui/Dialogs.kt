package com.example.stockmanagementsystem.ui

import android.content.Context
import android.text.InputType
import android.view.LayoutInflater
import android.view.View
import android.widget.TextView
import android.widget.Toast
import androidx.fragment.app.FragmentActivity
import com.example.stockmanagementsystem.R
import com.example.stockmanagementsystem.data.AttrOptions
import com.example.stockmanagementsystem.data.AttrType
import com.example.stockmanagementsystem.data.StockMath
import com.example.stockmanagementsystem.databinding.DialogAttrDefBinding
import com.example.stockmanagementsystem.databinding.DialogImagePreviewBinding
import com.example.stockmanagementsystem.databinding.DialogOptionsBinding
import com.example.stockmanagementsystem.databinding.DialogStockOpBinding
import com.example.stockmanagementsystem.databinding.DialogTextInputBinding
import com.example.stockmanagementsystem.databinding.DialogWarehouseBinding
import com.example.stockmanagementsystem.util.Bitmaps
import com.example.stockmanagementsystem.util.Fmt
import com.google.android.material.dialog.MaterialAlertDialogBuilder
import com.google.android.material.datepicker.MaterialDatePicker
import com.google.android.material.timepicker.MaterialTimePicker
import com.google.android.material.timepicker.MaterialTimePicker.INPUT_MODE_CLOCK
import com.google.android.material.timepicker.TimeFormat
import java.io.File
import java.util.Calendar
import java.util.TimeZone

object Dialogs {

    fun confirm(context: Context, message: String, onConfirm: () -> Unit) {
        MaterialAlertDialogBuilder(context)
            .setMessage(message)
            .setNegativeButton(R.string.action_cancel, null)
            .setPositiveButton(R.string.action_delete) { _, _ -> onConfirm() }
            .show()
    }

    /**
     * 说明文本 + 竖排选项弹窗（Material3 下 setMessage 与 setItems 混用会吞掉列表项，
     * 统一走自定义视图）。[message] 为空时隐藏说明行；点选项后自动关闭并回调其下标。
     */
    fun options(
        context: Context,
        title: Int,
        message: String = "",
        options: List<String>,
        negativeText: Int = R.string.action_cancel,
        onPick: (Int) -> Unit,
    ) {
        val vb = DialogOptionsBinding.inflate(LayoutInflater.from(context))
        vb.textMessage.text = message
        vb.textMessage.visibility = if (message.isEmpty()) View.GONE else View.VISIBLE
        val dialog = MaterialAlertDialogBuilder(context)
            .setTitle(title)
            .setView(vb.root)
            .setNegativeButton(negativeText, null)
            .create()
        options.forEachIndexed { index, label ->
            val row = TextView(context, null, 0, R.style.DialogOptionRow)
            row.text = label
            row.setOnClickListener {
                dialog.dismiss()
                onPick(index)
            }
            vb.optionContainer.addView(row)
        }
        dialog.show()
    }

    /** 单输入框（类目名等）。返回 null 表示校验未通过 */
    fun inputText(
        context: Context,
        title: Int,
        hint: Int,
        initial: String = "",
        onOk: (String) -> Unit,
    ) {
        val vb = DialogTextInputBinding.inflate(LayoutInflater.from(context))
        vb.layoutInput.hint = context.getString(hint)
        vb.input.setText(initial)
        val dialog = MaterialAlertDialogBuilder(context)
            .setTitle(title)
            .setView(vb.root)
            .setNegativeButton(R.string.action_cancel, null)
            .setPositiveButton(R.string.action_ok, null)
            .show()
        dialog.getButton(android.app.AlertDialog.BUTTON_POSITIVE).setOnClickListener {
            val value = vb.input.text?.toString()?.trim().orEmpty()
            if (value.isEmpty()) {
                vb.layoutInput.error = context.getString(R.string.category_name_required)
                return@setOnClickListener
            }
            dialog.dismiss()
            onOk(value)
        }
    }

    fun warehouse(
        context: Context,
        title: Int,
        initialName: String = "",
        initialRemark: String = "",
        onOk: (String, String) -> Unit,
    ) {
        val vb = DialogWarehouseBinding.inflate(LayoutInflater.from(context))
        vb.inputName.setText(initialName)
        vb.inputRemark.setText(initialRemark)
        val dialog = MaterialAlertDialogBuilder(context)
            .setTitle(title)
            .setView(vb.root)
            .setNegativeButton(R.string.action_cancel, null)
            .setPositiveButton(R.string.action_ok, null)
            .show()
        dialog.getButton(android.app.AlertDialog.BUTTON_POSITIVE).setOnClickListener {
            val name = vb.inputName.text?.toString()?.trim().orEmpty()
            if (name.isEmpty()) {
                vb.layoutName.error = context.getString(R.string.warehouse_name_required)
                return@setOnClickListener
            }
            dialog.dismiss()
            onOk(name, vb.inputRemark.text?.toString()?.trim().orEmpty())
        }
    }

    /** 属性定义编辑；onOk(name, type, options) */
    fun attrDef(
        context: Context,
        title: Int,
        initialName: String = "",
        initialType: AttrType = AttrType.TEXT,
        initialOptions: List<String> = emptyList(),
        onOk: (String, AttrType, List<String>) -> Unit,
    ) {
        val vb = DialogAttrDefBinding.inflate(LayoutInflater.from(context))
        vb.inputName.setText(initialName)
        vb.inputOptions.setText(initialOptions.joinToString(","))
        fun syncOptionsVisibility(checkedId: Int) {
            vb.layoutOptions.visibility = when (checkedId) {
                R.id.chipChoice, R.id.chipTags -> View.VISIBLE
                else -> View.GONE
            }
            vb.layoutOptions.hint = context.getString(
                if (checkedId == R.id.chipTags) R.string.attr_tags_hint else R.string.attr_options_hint
            )
        }
        vb.chipGroupType.check(
            when (initialType) {
                AttrType.NUMBER -> R.id.chipNumber
                AttrType.CHOICE -> R.id.chipChoice
                AttrType.TAGS -> R.id.chipTags
                AttrType.IMAGE -> R.id.chipImage
                AttrType.TEXT -> R.id.chipText
            }
        )
        syncOptionsVisibility(vb.chipGroupType.checkedChipId)
        vb.chipGroupType.setOnCheckedStateChangeListener { _, checkedIds ->
            syncOptionsVisibility(checkedIds.firstOrNull() ?: View.NO_ID)
        }

        val dialog = MaterialAlertDialogBuilder(context)
            .setTitle(title)
            .setView(vb.root)
            .setNegativeButton(R.string.action_cancel, null)
            .setPositiveButton(R.string.action_ok, null)
            .show()
        dialog.getButton(android.app.AlertDialog.BUTTON_POSITIVE).setOnClickListener {
            val name = vb.inputName.text?.toString()?.trim().orEmpty()
            if (name.isEmpty()) {
                vb.layoutName.error = context.getString(R.string.attr_name_required)
                return@setOnClickListener
            }
            val type = when (vb.chipGroupType.checkedChipId) {
                R.id.chipNumber -> AttrType.NUMBER
                R.id.chipChoice -> AttrType.CHOICE
                R.id.chipTags -> AttrType.TAGS
                R.id.chipImage -> AttrType.IMAGE
                else -> AttrType.TEXT
            }
            val options = AttrOptions.parseUserInput(vb.inputOptions.text?.toString().orEmpty())
            if (type == AttrType.CHOICE && options.size < 2) {
                vb.layoutOptions.error = context.getString(R.string.attr_options_required)
                return@setOnClickListener
            }
            if (type == AttrType.TAGS && options.isEmpty()) {
                vb.layoutOptions.error = context.getString(R.string.attr_tags_required)
                return@setOnClickListener
            }
            dialog.dismiss()
            onOk(name, type, options)
        }
    }

    fun imagePreview(context: Context, file: File) {
        val vb = DialogImagePreviewBinding.inflate(LayoutInflater.from(context))
        val bmp = Bitmaps.decodeSampled(file, 1440)
        if (bmp == null) {
            Toast.makeText(context, R.string.deleted, Toast.LENGTH_SHORT).show()
            return
        }
        vb.imagePreview.setImageBitmap(bmp)
        MaterialAlertDialogBuilder(context).setView(vb.root).show()
    }

    /** 入库/出库弹窗：onOk(数量, 入库总价, 购买/操作时间, 备注)；入库必填总价与可选购买时间，出库相关字段为 null */
    fun stockOp(
        context: Context,
        isIn: Boolean,
        itemName: String,
        currentQty: Double,
        unit: String,
        onOk: (Double, Double?, Long?, String) -> Unit,
    ) {
        val vb = DialogStockOpBinding.inflate(LayoutInflater.from(context))
        vb.textCurrent.text =
            context.getString(R.string.stock_current, Fmt.qtyWithUnit(currentQty, unit))
        if (unit.isNotEmpty()) {
            vb.layoutQty.hint = context.getString(R.string.stock_qty_hint_with_unit, unit)
        }
        vb.layoutPrice.visibility = if (isIn) View.VISIBLE else View.GONE
        vb.layoutTime.visibility = if (isIn) View.VISIBLE else View.GONE

        // 入库可选真实购买时间；不选则为 null（提交时按当前时间）
        var pickedAt: Long? = null
        vb.inputTime.setOnClickListener {
            pickDateTime(context, pickedAt) { picked ->
                pickedAt = picked
                vb.inputTime.setText(Fmt.time(picked))
            }
        }

        val dialog = MaterialAlertDialogBuilder(context)
            .setTitle(
                context.getString(
                    if (isIn) R.string.stock_in else R.string.stock_out
                ) + " · " + itemName
            )
            .setView(vb.root)
            .setNegativeButton(R.string.action_cancel, null)
            .setPositiveButton(R.string.action_ok, null)
            .show()
        dialog.getButton(android.app.AlertDialog.BUTTON_POSITIVE).setOnClickListener {
            val qty = vb.inputQty.text?.toString()?.trim()?.toDoubleOrNull()
            if (qty == null || qty <= 0) {
                vb.layoutQty.error = context.getString(R.string.stock_qty_required)
                return@setOnClickListener
            }
            if (!isIn && qty > currentQty) {
                vb.layoutQty.error =
                    context.getString(R.string.stock_insufficient, Fmt.qtyWithUnit(currentQty, unit))
                return@setOnClickListener
            }
            val price = if (isIn) {
                val raw = vb.inputPrice.text?.toString()?.trim().orEmpty()
                if (!PRICE_PATTERN.matches(raw)) {
                    vb.layoutPrice.error = context.getString(R.string.stock_price_required)
                    return@setOnClickListener
                }
                raw.toDouble()
            } else {
                null
            }
            dialog.dismiss()
            onOk(qty, price, if (isIn) pickedAt else null, vb.inputNote.text?.toString()?.trim().orEmpty())
        }
    }

    /** 日期 + 时间两级选择；结果不晚于当前时间 */
    private fun pickDateTime(context: Context, initial: Long?, onPicked: (Long) -> Unit) {
        val fm = (context as? FragmentActivity)?.supportFragmentManager ?: return
        val datePicker = MaterialDatePicker.Builder.datePicker()
            .setSelection(initial ?: System.currentTimeMillis())
            .build()
        datePicker.addOnPositiveButtonClickListener { dateSel ->
            val timePicker = MaterialTimePicker.Builder()
                .setTimeFormat(TimeFormat.CLOCK_24H)
                .setInputMode(INPUT_MODE_CLOCK)
                .build()
            timePicker.addOnPositiveButtonClickListener {
                // 日期选择给的是 UTC 零点，转回本地日历再拼上时分
                val utc = Calendar.getInstance(TimeZone.getTimeZone("UTC")).apply {
                    timeInMillis = dateSel
                }
                val local = Calendar.getInstance().apply {
                    set(
                        utc.get(Calendar.YEAR), utc.get(Calendar.MONTH),
                        utc.get(Calendar.DAY_OF_MONTH),
                        timePicker.hour, timePicker.minute, 0,
                    )
                    set(Calendar.MILLISECOND, 0)
                }
                onPicked(local.timeInMillis.coerceAtMost(System.currentTimeMillis()))
            }
            timePicker.show(fm, "stock_time")
        }
        datePicker.show(fm, "stock_date")
    }

    /**
     * 入库时老库存尚未定价：选择定价方式。
     * 选 CORRECT 会再弹「老库存总价」输入框；onPick(方式, 修正总价?)
     */
    fun unpricedPricing(
        context: Context,
        oldQty: Double,
        unit: String,
        onPick: (StockMath.InPricing, Double?) -> Unit,
    ) {
        options(
            context,
            R.string.pricing_title,
            context.getString(R.string.pricing_message, Fmt.qtyWithUnit(oldQty, unit)),
            listOf(
                context.getString(R.string.pricing_first_price),
                context.getString(R.string.pricing_dilute),
                context.getString(R.string.pricing_correct),
            ),
        ) { which ->
            when (which) {
                0 -> onPick(StockMath.InPricing.FIRST_PRICE, null)
                1 -> onPick(StockMath.InPricing.WEIGHTED, null)
                else -> inputCorrectedValue(context, onPick)
            }
        }
    }

    /** 手动修正老库存总价输入框（CORRECT 分支用） */
    private fun inputCorrectedValue(
        context: Context,
        onPick: (StockMath.InPricing, Double?) -> Unit,
    ) {
        val vb = DialogTextInputBinding.inflate(LayoutInflater.from(context))
        vb.layoutInput.hint = context.getString(R.string.old_stock_value_hint)
        vb.input.inputType = InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_DECIMAL
        val dialog = MaterialAlertDialogBuilder(context)
            .setTitle(R.string.pricing_correct)
            .setView(vb.root)
            .setNegativeButton(R.string.action_cancel, null)
            .setPositiveButton(R.string.action_ok, null)
            .show()
        dialog.getButton(android.app.AlertDialog.BUTTON_POSITIVE).setOnClickListener {
            val raw = vb.input.text?.toString()?.trim().orEmpty()
            if (!PRICE_PATTERN.matches(raw)) {
                vb.layoutInput.error = context.getString(R.string.stock_price_required)
                return@setOnClickListener
            }
            dialog.dismiss()
            onPick(StockMath.InPricing.CORRECT, raw.toDouble())
        }
    }

    /** 金额输入：非负数字，最多两位小数 */
    private val PRICE_PATTERN = Regex("""\d+(\.\d{1,2})?""")
}
