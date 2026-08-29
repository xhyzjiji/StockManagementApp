package com.example.stockmanagementsystem.util

import java.util.TimeZone

/** 本地「纪元日」工具：把毫秒时间戳折算为本地日序号与星期（minSdk 24 无 java.time） */
object Days {
    const val DAY_MS = 24L * 60 * 60 * 1000

    /** 时间戳所属的本地日（自 1970-01-01 起第几天） */
    fun localEpochDay(ts: Long): Long =
        Math.floorDiv(ts + TimeZone.getDefault().getOffset(ts), DAY_MS)

    /** 本地日的星期：0=周一 … 6=周日（纪元日是周四） */
    fun weekdayOf(epochDay: Long): Int {
        val w = ((epochDay + 3) % 7).toInt()
        return if (w < 0) w + 7 else w
    }
}
