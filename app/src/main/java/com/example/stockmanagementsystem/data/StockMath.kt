package com.example.stockmanagementsystem.data

import java.math.BigDecimal
import java.math.RoundingMode

/** 库存金额计算：金额四舍五入保留两位小数（元到分） */
object StockMath {

    /** 入库时老库存尚未定价（有库存但总价为 0）的定价方式 */
    enum class InPricing {
        /** 本次入库总价摊到全部库存（未定价的老库存相当于按 0 元计价） */
        WEIGHTED,

        /** 按本次入库的单价给整批库存（含老库存）统一定价 */
        FIRST_PRICE,

        /** 手动修正老库存总价后，再与本次入库正常加权 */
        CORRECT,
    }

    data class ValueAfter(
        /** 剩余总价（元，两位小数） */
        val totalValue: Double,
        /** 平均单价（元，两位小数） */
        val avgPrice: Double,
    )

    fun round2(value: Double): Double =
        BigDecimal(value).setScale(2, RoundingMode.HALF_UP).toDouble()

    /** 入库：剩余总价累加本次入库总价，平均价 = 剩余总价 / 入库后库存 */
    fun afterStockIn(
        beforeQty: Double,
        beforeValue: Double,
        inQty: Double,
        inTotal: Double,
    ): ValueAfter {
        val total = round2(beforeValue + inTotal)
        val qty = beforeQty + inQty
        val avg = if (qty > 0) round2(total / qty) else 0.0
        return ValueAfter(total, avg)
    }

    /** 按本次入库单价给整批库存（含未定价的老库存）重新定价 */
    fun afterStockInFirstPrice(beforeQty: Double, inQty: Double, inTotal: Double): ValueAfter {
        val avg = round2(inTotal / inQty)
        val total = round2(avg * (beforeQty + inQty))
        return ValueAfter(total, avg)
    }

    /** 出库：均价不变，剩余总价 = 出库后数量 × 均价；出清（含浮点尾差）时总价与均价归零 */
    fun afterStockOut(afterQty: Double, avgPrice: Double): ValueAfter =
        if (afterQty < 1e-9) ValueAfter(0.0, 0.0)
        else ValueAfter(round2(afterQty * avgPrice), avgPrice)
}
