package com.example.stockmanagementsystem.ui.chart

import android.content.Context
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.Path
import android.util.AttributeSet
import android.view.View
import com.example.stockmanagementsystem.util.Fmt

/** 单价变化折线图：横轴时间均分点位，纵轴价格；带坐标轴与首末日期标签 */
class LineChartView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null,
) : View(context, attrs) {

    private val points = ArrayList<Pair<Long, Double>>()

    private val axisPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = 0xFFB0BEC5.toInt()
        style = Paint.Style.STROKE
        strokeWidth = resources.displayMetrics.density
    }
    private val linePaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = 0xFF1565C0.toInt()
        style = Paint.Style.STROKE
        strokeWidth = 2f * resources.displayMetrics.density
        strokeJoin = Paint.Join.ROUND
        strokeCap = Paint.Cap.ROUND
    }
    private val dotPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = 0xFF1565C0.toInt()
        style = Paint.Style.FILL
    }
    private val labelPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = 0xFF757575.toInt()
        textSize = 10f * resources.displayMetrics.scaledDensity
    }
    private val path = Path()

    /** points：入库时间(毫秒) → 当批单价 */
    fun submit(data: List<Pair<Long, Double>>) {
        points.clear()
        points.addAll(data)
        invalidate()
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        if (points.isEmpty()) return
        val d = resources.displayMetrics.density
        val labelPad = 30f * d
        val left = paddingLeft + labelPad
        val right = (width - paddingRight - 8f * d)
        val top = paddingTop + 12f * d
        val bottom = height - paddingBottom - 22f * d
        if (right <= left || bottom <= top) return

        canvas.drawLine(left, top, left, bottom, axisPaint)
        canvas.drawLine(left, bottom, right, bottom, axisPaint)

        val maxV = points.maxOf { it.second }
        val minV = points.minOf { it.second }
        canvas.drawText(Fmt.money(maxV), paddingLeft + 2f * d, top + 3f * d, labelPaint)
        canvas.drawText(Fmt.money(minV), paddingLeft + 2f * d, bottom, labelPaint)
        canvas.drawText(Fmt.dayShort(points.first().first), left, bottom + 16f * d, labelPaint)
        val lastLabel = Fmt.dayShort(points.last().first)
        canvas.drawText(lastLabel, right - labelPaint.measureText(lastLabel), bottom + 16f * d, labelPaint)

        val range = (maxV - minV).takeIf { it > 0 } ?: 1.0
        fun x(i: Int) = if (points.size == 1) (left + right) / 2f
        else left + (right - left) * i / (points.size - 1)
        fun y(v: Double) = bottom - ((v - minV) / range * (bottom - top)).toFloat()

        path.reset()
        points.forEachIndexed { i, (_, v) ->
            val px = x(i)
            val py = y(v)
            if (i == 0) path.moveTo(px, py) else path.lineTo(px, py)
        }
        canvas.drawPath(path, linePaint)
        val dotR = 3f * d
        points.forEachIndexed { i, (_, v) -> canvas.drawCircle(x(i), y(v), dotR, dotPaint) }
    }
}
