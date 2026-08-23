package com.example.stockmanagementsystem.util

import java.math.BigDecimal
import java.math.RoundingMode
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

object Fmt {
    private val timeFormat = SimpleDateFormat("yyyy-MM-dd HH:mm", Locale.getDefault())
    private val dateFormat = SimpleDateFormat("yyyy/MM/dd", Locale.getDefault())

    /** 数量展示：去掉多余的 0，最多保留 3 位小数 */
    fun qty(value: Double): String =
        BigDecimal(value).setScale(3, RoundingMode.HALF_UP).stripTrailingZeros().toPlainString()

    /** 数量+单位展示：单位为空时退化为纯数字 */
    fun qtyWithUnit(value: Double, unit: String): String =
        if (unit.isEmpty()) qty(value) else "${qty(value)} $unit"

    fun time(millis: Long): String = timeFormat.format(Date(millis))

    /** 日期展示：2026/08/22 */
    fun date(millis: Long): String = dateFormat.format(Date(millis))

    /** 出入库后的库存计算，出库不允许为负 */
    fun computeAfter(before: Double, delta: Double, isIn: Boolean): Double {
        require(delta > 0) { "数量必须大于 0" }
        val after = if (isIn) before + delta else before - delta
        require(after >= 0.0) { "库存不足" }
        return after
    }
}
