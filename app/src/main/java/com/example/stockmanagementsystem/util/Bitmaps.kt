package com.example.stockmanagementsystem.util

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.widget.ImageView
import java.io.File

object Bitmaps {

    /** 按目标边长采样解码，避免大图 OOM */
    fun decodeSampled(file: File, reqDimen: Int): Bitmap? {
        if (!file.exists()) return null
        val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        BitmapFactory.decodeFile(file.absolutePath, bounds)
        if (bounds.outWidth <= 0 || bounds.outHeight <= 0) return null
        var sample = 1
        while (bounds.outWidth / (sample * 2) >= reqDimen && bounds.outHeight / (sample * 2) >= reqDimen) {
            sample *= 2
        }
        return BitmapFactory.decodeFile(
            file.absolutePath,
            BitmapFactory.Options().apply { inSampleSize = sample }
        )
    }

    fun loadInto(view: ImageView, file: File, reqDimen: Int) {
        val bmp = decodeSampled(file, reqDimen)
        if (bmp != null) view.setImageBitmap(bmp) else view.setImageDrawable(null)
    }
}
