package com.example.stockmanagementsystem.ui.chart

import android.content.Context
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.RectF
import android.util.AttributeSet
import android.view.View
import kotlin.math.min

/** 环形饼图：按值占比绘制扇区，颜色按 [PALETTE] 循环 */
class PieChartView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null,
) : View(context, attrs) {

    data class Slice(val label: String, val value: Double)

    private val slices = ArrayList<Slice>()
    private val strokeWidth = 26f * resources.displayMetrics.density

    private val arcPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
    }
    private val rect = RectF()

    /** 第 i 片的颜色（与图例共用） */
    fun colorOf(index: Int): Int = PALETTE[index % PALETTE.size]

    fun submit(data: List<Slice>) {
        slices.clear()
        slices.addAll(data)
        invalidate()
    }

    /** 所有扇区值之和；0 表示无数据 */
    fun total(): Double = slices.sumOf { it.value }

    override fun onMeasure(widthMeasureSpec: Int, heightMeasureSpec: Int) {
        val width = resolveSize(suggestedMinimumWidth, widthMeasureSpec)
        setMeasuredDimension(width, resolveSize(width, heightMeasureSpec))
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        val sum = total()
        if (sum <= 0) return
        val d = min(width, height).toFloat()
        val half = strokeWidth / 2f
        rect.set(
            (width - d) / 2f + half, (height - d) / 2f + half,
            (width + d) / 2f - half, (height + d) / 2f - half,
        )
        arcPaint.strokeWidth = strokeWidth
        // 圆弧画在半径中线上，两侧各占一半线宽，扇区间留约 1° 缝隙
        var start = -90f
        slices.forEachIndexed { i, slice ->
            val sweep = (slice.value / sum * 360.0).toFloat()
            arcPaint.color = colorOf(i)
            canvas.drawArc(rect, start + 0.5f, sweep - 1f, false, arcPaint)
            start += sweep
        }
    }

    companion object {
        val PALETTE = intArrayOf(
            0xFF1565C0.toInt(),
            0xFF00897B.toInt(),
            0xFFE65100.toInt(),
            0xFF6A1B9A.toInt(),
            0xFFC62828.toInt(),
            0xFF2E7D32.toInt(),
            0xFF4527A0.toInt(),
            0xFFAD1457.toInt(),
            0xFF5D4037.toInt(),
            0xFF37474F.toInt(),
        )
    }
}
