package com.example.stockmanagementsystem

import com.example.stockmanagementsystem.data.TransferNaming
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class TransferNamingTest {

    @Test
    fun uniqueName_noConflict_returnsBase() {
        assertEquals("五金仓", TransferNaming.uniqueName("五金仓", emptySet()))
        assertEquals("五金仓", TransferNaming.uniqueName("五金仓", setOf("别的仓")))
    }

    @Test
    fun uniqueName_conflict_appendsIncrementingSuffix() {
        assertEquals("五金仓 (2)", TransferNaming.uniqueName("五金仓", setOf("五金仓")))
        assertEquals(
            "五金仓 (3)",
            TransferNaming.uniqueName("五金仓", setOf("五金仓", "五金仓 (2)"))
        )
        assertEquals(
            "五金仓 (4)",
            TransferNaming.uniqueName("五金仓", setOf("五金仓", "五金仓 (2)", "五金仓 (3)"))
        )
    }

    @Test
    fun uniqueName_gapInSuffixes_fillsFirstFree() {
        // (2) 被删后空出，优先补位而不是一路递增
        assertEquals(
            "五金仓 (2)",
            TransferNaming.uniqueName("五金仓", setOf("五金仓", "五金仓 (3)"))
        )
    }

    @Test
    fun suggestedFileName_sanitizesIllegalChars() {
        val name = TransferNaming.suggestedFileName("a/b\\c:d*e?f\"g<h>i|j", 0L)
        assertTrue(name.startsWith("a_b_c_d_e_f_g_h_i_j_"))
        assertTrue(name.endsWith(".zip"))
    }

    @Test
    fun suggestedFileName_blankName_fallsBack() {
        assertTrue(TransferNaming.suggestedFileName("   ", 0L).startsWith("仓库_"))
    }

    @Test
    fun suggestedFileName_hasTimestamp() {
        assertTrue(
            TransferNaming.suggestedFileName("仓", 0L)
                .matches(Regex("""仓_\d{8}_\d{4}\.zip"""))
        )
    }
}
