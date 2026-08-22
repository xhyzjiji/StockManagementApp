package com.example.stockmanagementsystem

import com.example.stockmanagementsystem.data.AttrOptions
import org.junit.Assert.assertEquals
import org.junit.Test

class AttrOptionsTest {

    @Test
    fun encodeDecode_roundtrip() {
        val options = listOf("有糖", "无糖")
        assertEquals(options, AttrOptions.decode(AttrOptions.encode(options)))
    }

    @Test
    fun parseUserInput_supportsChineseDelimiters() {
        assertEquals(listOf("有糖", "无糖"), AttrOptions.parseUserInput("有糖，无糖"))
        assertEquals(listOf("桶装", "袋装"), AttrOptions.parseUserInput("桶装、袋装"))
        assertEquals(listOf("a", "b", "c"), AttrOptions.parseUserInput("a,b|c"))
        assertEquals(emptyList<String>(), AttrOptions.parseUserInput("  "))
    }

    @Test
    fun decode_empty() {
        assertEquals(emptyList<String>(), AttrOptions.decode(""))
    }
}
