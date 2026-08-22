package com.example.stockmanagementsystem.ui

import android.content.Context
import android.view.LayoutInflater
import android.view.View
import android.widget.Toast
import com.example.stockmanagementsystem.R
import com.example.stockmanagementsystem.data.AttrOptions
import com.example.stockmanagementsystem.data.AttrType
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
        when (initialType) {
            AttrType.TEXT -> vb.radioText.isChecked = true
            AttrType.NUMBER -> vb.radioNumber.isChecked = true
            AttrType.CHOICE -> vb.radioChoice.isChecked = true
            AttrType.IMAGE -> vb.radioImage.isChecked = true
        }
        fun syncOptionsVisibility(checkedId: Int) {
            vb.layoutOptions.visibility =
                if (checkedId == R.id.radioChoice) View.VISIBLE else View.GONE
        }
        syncOptionsVisibility(vb.radioType.checkedRadioButtonId)
        vb.radioType.setOnCheckedChangeListener { _, checkedId -> syncOptionsVisibility(checkedId) }

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
            val type = when (vb.radioType.checkedRadioButtonId) {
                R.id.radioNumber -> AttrType.NUMBER
                R.id.radioChoice -> AttrType.CHOICE
                R.id.radioImage -> AttrType.IMAGE
                else -> AttrType.TEXT
            }
            val options = AttrOptions.parseUserInput(vb.inputOptions.text?.toString().orEmpty())
            if (type == AttrType.CHOICE && options.size < 2) {
                vb.layoutOptions.error = context.getString(R.string.attr_options_required)
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

    /** 入库/出库弹窗：onOk(数量, 备注)，出库在弹窗层先做超量校验 */
    fun stockOp(
        context: Context,
        isIn: Boolean,
        itemName: String,
        currentQty: Double,
        onOk: (Double, String) -> Unit,
    ) {
        val vb = DialogStockOpBinding.inflate(LayoutInflater.from(context))
        vb.textCurrent.text = context.getString(R.string.stock_current, Fmt.qty(currentQty))
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
                vb.layoutQty.error = context.getString(R.string.stock_insufficient, Fmt.qty(currentQty))
                return@setOnClickListener
            }
            dialog.dismiss()
            onOk(qty, vb.inputNote.text?.toString()?.trim().orEmpty())
        }
    }
}
