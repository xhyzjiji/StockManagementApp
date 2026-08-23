package com.example.stockmanagementsystem.util

import android.graphics.drawable.GradientDrawable
import android.widget.TextView
import kotlin.math.abs

/** 标签 pill 底色：按标签名哈希稳定取色，同名标签在任何页面颜色一致 */
object TagColors {

    /** (背景, 文字) 柔和配色对 */
    private val palette = listOf(
        0xFFE3F2FD.toInt() to 0xFF1565C0.toInt(),
        0xFFE0F2F1.toInt() to 0xFF00695C.toInt(),
        0xFFFFF3E0.toInt() to 0xFFE65100.toInt(),
        0xFFF3E5F5.toInt() to 0xFF6A1B9A.toInt(),
        0xFFE8F5E9.toInt() to 0xFF2E7D32.toInt(),
        0xFFFFEBEE.toInt() to 0xFFC62828.toInt(),
        0xFFE8EAF6.toInt() to 0xFF283593.toInt(),
        0xFFECEFF1.toInt() to 0xFF37474F.toInt(),
    )

    fun applyStyle(chip: TextView, tag: String) {
        val (bg, fg) = palette[abs(tag.hashCode()) % palette.size]
        val radius = 12f * chip.resources.displayMetrics.density
        chip.background = GradientDrawable().apply {
            setColor(bg)
            cornerRadius = radius
        }
        chip.setTextColor(fg)
    }
}
