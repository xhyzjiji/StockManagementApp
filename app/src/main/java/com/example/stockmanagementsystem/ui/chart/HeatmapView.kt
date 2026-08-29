package com.example.stockmanagementsystem.ui.chart

import android.content.Context
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.RectF
import android.util.AttributeSet
import android.view.View
import com.example.stockmanagementsystem.util.Days
import java.util.Calendar
import kotlin.math.ceil

/** GitHub 风格的出入库频率热力图：近 26 周，每周一列、每列周一→周日 7 格；顶部月份、左侧周几 */
class HeatmapView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null,
) : View(context, attrs) {

    private val counts = HashMap<Long, Int>()
    private var endDay: Long = 0

    /** 分档配色（5 档，含空白色），默认入库绿 */
    var palette: IntArray = GREENS
        set(value) {
            field = value
            invalidate()
        }

    private val paint = Paint(Paint.ANTI_ALIAS_FLAG)
    private val cell = RectF()
    private val gap = 3f * resources.displayMetrics.density
    private val corner = 2f * resources.displayMetrics.density
    private val d = resources.displayMetrics.density
    private val labelPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = 0xFF757575.toInt()
        textSize = 10f * resources.displayMetrics.scaledDensity
    }
    /** 左侧周标签宽度、顶部月份标签高度 */
    private val labelLeft = 20f * resources.displayMetrics.density
    private val labelTop = 16f * resources.displayMetrics.density
    private val calendar = Calendar.getInstance()

    /** dayCounts：本地纪元日 → 当天出入库笔数 */
    fun submit(dayCounts: Map<Long, Int>, endMillis: Long = System.currentTimeMillis()) {
        counts.clear()
        counts.putAll(dayCounts)
        endDay = Days.localEpochDay(endMillis)
        invalidate()
    }

    override fun onMeasure(widthMeasureSpec: Int, heightMeasureSpec: Int) {
        val width = resolveSize(suggestedMinimumWidth, widthMeasureSpec)
        val cellW = cellWidth(width)
        val height = (paddingTop + paddingBottom + labelTop +
            ceil(cellW * ROWS + gap * (ROWS - 1))).toInt()
        setMeasuredDimension(width, resolveSize(height, heightMeasureSpec))
    }

    private fun cellWidth(widthPx: Int): Float =
        (widthPx - paddingLeft - paddingRight - labelLeft - gap * (WEEKS - 1)) / WEEKS

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        if (endDay <= 0) return
        val cellW = cellWidth(width)
        val startDay = endDay - Days.weekdayOf(endDay) - (WEEKS - 1) * 7L
        val max = counts.values.maxOrNull() ?: 0

        // 左侧周几标签（一/三/五）
        WEEKDAY_LABELS.forEach { (row, text) ->
            val cy = paddingTop + labelTop + row * (cellW + gap) + cellW / 2f
            val baseline = cy - (labelPaint.descent() + labelPaint.ascent()) / 2f
            canvas.drawText(text, paddingLeft + 2 * d, baseline, labelPaint)
        }

        // 顶部月份标签：画在每月首个周一所在列，间距过近则跳过
        var lastLabelRight = -1f
        var lastMonth = -1
        val labelBaseline = paddingTop + labelTop - 5 * d

        var day = startDay
        while (day <= endDay) {
            val col = ((day - startDay) / 7).toInt()
            val row = Days.weekdayOf(day)
            val left = paddingLeft + labelLeft + col * (cellW + gap)
            val top = paddingTop + labelTop + row * (cellW + gap)

            if (row == 0) {
                val month = monthOf(day)
                if (month != lastMonth) {
                    lastMonth = month
                    val text = monthText(month)
                    val textW = labelPaint.measureText(text)
                    if (left - lastLabelRight >= MIN_LABEL_GAP * d) {
                        canvas.drawText(text, left, labelBaseline, labelPaint)
                        lastLabelRight = left + textW
                    }
                }
            }

            paint.color = palette[levelOf(counts[day] ?: 0, max)]
            cell.set(left, top, left + cellW, top + cellW)
            canvas.drawRoundRect(cell, corner, corner, paint)
            day++
        }
    }

    /** 本地纪元日 → 公历月份（1..12） */
    private fun monthOf(epochDay: Long): Int {
        val offset = java.util.TimeZone.getDefault().getOffset(epochDay * Days.DAY_MS)
        calendar.timeInMillis = epochDay * Days.DAY_MS - offset
        return calendar.get(Calendar.MONTH) + 1
    }

    private fun monthText(month: Int): String = "${month}月"

    companion object {
        const val WEEKS = 26
        private const val ROWS = 7
        private const val MIN_LABEL_GAP = 12

        /** 行号 → 中文周几（与 GitHub 一样只标一/三/五） */
        private val WEEKDAY_LABELS = listOf(0 to "一", 2 to "三", 4 to "五")

        /** 入库：由少到多 5 档绿色 */
        val GREENS = intArrayOf(
            0xFFDDE5E8.toInt(),
            0xFFA7D3A9.toInt(),
            0xFF67BB6A.toInt(),
            0xFF43A047.toInt(),
            0xFF2E7D32.toInt(),
        )

        /** 出库：由少到多 5 档红色 */
        val REDS = intArrayOf(
            0xFFDDE5E8.toInt(),
            0xFFEF9A9A.toInt(),
            0xFFE57373.toInt(),
            0xFFE53935.toInt(),
            0xFFC62828.toInt(),
        )

        /** 按相对最多笔数分 5 档 */
        fun levelOf(count: Int, max: Int): Int {
            if (count <= 0 || max <= 0) return 0
            val ratio = count.toFloat() / max
            return when {
                ratio <= 0.25f -> 1
                ratio <= 0.5f -> 2
                ratio <= 0.75f -> 3
                else -> 4
            }
        }
    }
}
