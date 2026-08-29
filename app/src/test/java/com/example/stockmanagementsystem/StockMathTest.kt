package com.example.stockmanagementsystem

import com.example.stockmanagementsystem.data.StockMath
import org.junit.Assert.assertEquals
import org.junit.Test

class StockMathTest {

    @Test
    fun stockIn_computesWeightedAvg() {
        val after = StockMath.afterStockIn(beforeQty = 0.0, beforeValue = 0.0, inQty = 10.0, inTotal = 100.0)
        assertEquals(100.0, after.totalValue, 1e-9)
        assertEquals(10.0, after.avgPrice, 1e-9)
    }

    @Test
    fun stockOut_keepsAvgAndDeductsValue() {
        val after = StockMath.afterStockOut(afterQty = 5.0, avgPrice = 10.0)
        assertEquals(50.0, after.totalValue, 1e-9)
        assertEquals(10.0, after.avgPrice, 1e-9)
    }

    @Test
    fun example_fullChainRoundsAvgHalfUp() {
        val first = StockMath.afterStockIn(0.0, 0.0, 10.0, 100.0)
        val out = StockMath.afterStockOut(afterQty = 10.0 - 5.0, avgPrice = first.avgPrice)
        val second = StockMath.afterStockIn(5.0, out.totalValue, 10.0, 50.0)
        assertEquals(100.0, second.totalValue, 1e-9)
        assertEquals(6.67, second.avgPrice, 1e-9)
    }

    @Test
    fun stockOut_clearingAllResetsValueAndAvg() {
        val after = StockMath.afterStockOut(afterQty = 0.0, avgPrice = 6.67)
        assertEquals(0.0, after.totalValue, 1e-9)
        assertEquals(0.0, after.avgPrice, 1e-9)
    }

    @Test
    fun round2_roundsHalfUp() {
        assertEquals(6.67, StockMath.round2(100.0 / 15.0), 1e-9)
        assertEquals(0.01, StockMath.round2(0.005), 1e-9)
        assertEquals(10.0, StockMath.round2(10.0), 1e-9)
    }

    @Test
    fun stockInWeighted_dilutesUnpricedOldStock() {
        // 老库存 10 件无价格 + 入库 10 件 ¥100 → 总价 100 摊到 20 件
        val after = StockMath.afterStockIn(beforeQty = 10.0, beforeValue = 0.0, inQty = 10.0, inTotal = 100.0)
        assertEquals(100.0, after.totalValue, 1e-9)
        assertEquals(5.0, after.avgPrice, 1e-9)
    }

    @Test
    fun stockInFirstPrice_repricesWholeStockByBatch() {
        // 老库存 10 件 + 入库 10 件 ¥100 → 整批按 ¥10/件
        val after = StockMath.afterStockInFirstPrice(beforeQty = 10.0, inQty = 10.0, inTotal = 100.0)
        assertEquals(10.0, after.avgPrice, 1e-9)
        assertEquals(200.0, after.totalValue, 1e-9)
    }

    @Test
    fun stockInFirstPrice_totalValueRoundsFromAvg() {
        // 批次价 100/3 ≈ 33.33，整批 4 件 → 133.32
        val after = StockMath.afterStockInFirstPrice(beforeQty = 1.0, inQty = 3.0, inTotal = 100.0)
        assertEquals(33.33, after.avgPrice, 1e-9)
        assertEquals(133.32, after.totalValue, 1e-9)
    }

    @Test
    fun stockInCorrected_usesManualOldValue() {
        // 手动修正老库存总价 ¥80 + 入库 10 件 ¥100 → 总价 180 摊到 20 件
        val after = StockMath.afterStockIn(beforeQty = 10.0, beforeValue = 80.0, inQty = 10.0, inTotal = 100.0)
        assertEquals(180.0, after.totalValue, 1e-9)
        assertEquals(9.0, after.avgPrice, 1e-9)
    }
}
