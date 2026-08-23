package com.example.stockmanagementsystem.util

import android.app.Activity
import androidx.fragment.app.Fragment
import java.util.concurrent.Executors

/** 单线程后台执行器：串行化所有数据库读写，避免并发操作 SQLite */
object Bg {
    private val executor = Executors.newSingleThreadExecutor()

    fun run(block: () -> Unit) {
        executor.execute(block)
    }
}

/** 后台执行 block，完成后回到 UI 线程执行 deliver */
fun <T> Activity.runInBackground(block: () -> T, deliver: (T) -> Unit) {
    Bg.run {
        val result = block()
        runOnUiThread { if (!isFinishing && !isDestroyed) deliver(result) }
    }
}

/** Fragment 版本：宿主已结束或 Fragment 已分离时不回投 */
fun <T> Fragment.runInBackground(block: () -> T, deliver: (T) -> Unit) {
    Bg.run {
        val result = block()
        val act = activity ?: return@run
        act.runOnUiThread {
            if (isAdded && !act.isFinishing && !act.isDestroyed) deliver(result)
        }
    }
}
