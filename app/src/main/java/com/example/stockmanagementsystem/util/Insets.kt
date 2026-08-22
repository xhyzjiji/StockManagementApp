package com.example.stockmanagementsystem.util

import android.app.Activity
import android.view.View
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import com.example.stockmanagementsystem.R

/** Android 15+ 强制边到边：给根容器补状态栏/导航栏内边距 */
object Insets {
    fun apply(activity: Activity) {
        val root: View = activity.findViewById(R.id.main) ?: return
        ViewCompat.setOnApplyWindowInsetsListener(root) { v, insets ->
            val bars = insets.getInsets(WindowInsetsCompat.Type.systemBars())
            v.setPadding(bars.left, bars.top, bars.right, bars.bottom)
            insets
        }
    }
}
