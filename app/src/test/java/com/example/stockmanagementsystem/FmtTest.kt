package com.example.stockmanagementsystem

import com.example.stockmanagementsystem.util.Fmt
import org.junit.Assert.assertEquals
import org.junit.Test

class FmtTest {

    @Test
    fun qty_stripsTrailingZeros() {
        assertEquals("3", Fmt.qty(3.0))
        assertEquals("3.5", Fmt.qty(3.5))
        assertEquals("0.125", Fmt.qty(0.125))
        assertEquals("12.34", Fmt.qty(12.34))
    }

    @Test
    fun qtyWithUnit_appendsUnit() {
        assertEquals("12.5 米", Fmt.qtyWithUnit(12.5, "米"))
        assertEquals("3 ㎡", Fmt.qtyWithUnit(3.0, "㎡"))
    }

    @Test
    fun qtyWithUnit_emptyUnitFallsBackToPlainNumber() {
        assertEquals("2.5", Fmt.qtyWithUnit(2.5, ""))
    }

    @Test
    fun computeAfter_in() {
        assertEquals(10.0, Fmt.computeAfter(4.0, 6.0, isIn = true), 1e-9)
    }

    @Test
    fun computeAfter_out() {
        assertEquals(2.5, Fmt.computeAfter(5.0, 2.5, isIn = false), 1e-9)
    }

    @Test(expected = IllegalArgumentException::class)
    fun computeAfter_outInsufficient() {
        Fmt.computeAfter(1.0, 2.0, isIn = false)
    }

    @Test(expected = IllegalArgumentException::class)
    fun computeAfter_zeroDelta() {
        Fmt.computeAfter(1.0, 0.0, isIn = true)
    }

    @Test
    fun money_fixedTwoDecimals() {
        assertEquals("10.00", Fmt.money(10.0))
        assertEquals("6.67", Fmt.money(100.0 / 15.0))
        assertEquals("0.01", Fmt.money(0.005))
    }
}
