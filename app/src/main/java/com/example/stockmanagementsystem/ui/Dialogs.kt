package com.example.stockmanagementsystem.ui

import android.content.Context
import android.text.InputType
import android.view.LayoutInflater
import android.view.View
import android.widget.Toast
import com.example.stockmanagementsystem.R
import com.example.stockmanagementsystem.data.AttrOptions
import com.example.stockmanagementsystem.data.AttrType
import com.example.stockmanagementsystem.data.StockMath
import com.example.stockmanagementsystem.databinding.DialogAttrDefBinding
import com.example.stockmanagementsystem.databinding.DialogImagePreviewBinding
import com.example.stockmanagementsystem.databinding.DialogStockOpBinding
import com.example.stockmanagementsystem.databinding.DialogTextInputBinding
import com.example.stockmanagementsystem.databinding.DialogWarehouseBinding
import com.example.stockmanagementsystem.util.Bitmaps
import com.example.stockmanagementsystem.util.Fmt
import com.google.android.material.dialog.MaterialAlertDialogBuilder
import java.io.File

object Dialogs {

    fun confirm(context: Context, message: String, onConfirm: () -> Unit) {
        MaterialAlertDialogBuilder(context)
            .setMessage(message)
            .setNegativeButton(R.string.action_cancel, null)
            .setPositiveButton(R.string.action_delete) { _, _ -> onConfirm() }
            .show()
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

    /** 入库/出库弹窗：onOk(数量, 入库总价, 备注)，入库必填总价（出库传 null），出库在弹窗层先做超量校验 */
    fun stockOp(
        context: Context,
        isIn: Boolean,
        itemName: String,
        currentQty: Double,
        unit: String,
        onOk: (Double, Double?, String) -> Unit,
    ) {
        val vb = DialogStockOpBinding.inflate(LayoutInflater.from(context))
        vb.textCurrent.text =
            context.getString(R.string.stock_current, Fmt.qtyWithUnit(currentQty, unit))
        if (unit.isNotEmpty()) {
            vb.layoutQty.hint = context.getString(R.string.stock_qty_hint_with_unit, unit)
        }
        vb.layoutPrice.visibility = if (isIn) View.VISIBLE else View.GONE
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
            onOk(qty, price, vb.inputNote.text?.toString()?.trim().orEmpty())
        }
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
        val items = arrayOf(
            context.getString(R.string.pricing_first_price),
            context.getString(R.string.pricing_dilute),
            context.getString(R.string.pricing_correct),
        )
        MaterialAlertDialogBuilder(context)
            .setTitle(R.string.pricing_title)
            .setMessage(context.getString(R.string.pricing_message, Fmt.qtyWithUnit(oldQty, unit)))
            .setItems(items) { dlg, which ->
                dlg.dismiss()
                when (which) {
                    0 -> onPick(StockMath.InPricing.FIRST_PRICE, null)
                    1 -> onPick(StockMath.InPricing.WEIGHTED, null)
                    else -> inputCorrectedValue(context, onPick)
                }
            }
            .setNegativeButton(R.string.action_cancel, null)
            .show()
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
