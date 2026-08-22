package com.example.stockmanagementsystem.data

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Matrix
import android.media.ExifInterface
import android.net.Uri
import java.io.File
import java.io.FileOutputStream
import java.util.UUID

/**
 * 本地图片目录管理。数据库只存放相对 [root] 的路径（图片链接），
 * 目录结构：
 *   files/images/items/{itemId}/{attributeDefId}/{uuid}.jpg
 *   files/images/tmp/{uuid}.jpg   —— 拍照/相册暂存，保存物品后转正
 */
class ImageStore(context: Context) {

    val root: File = File(context.filesDir, "images").apply { mkdirs() }
    private val tmpDir = File(root, "tmp").apply { mkdirs() }

    fun fileOf(relativePath: String): File = File(root, relativePath)

    fun relativeTo(file: File): String = file.relativeTo(root).path

    /** 拍照输出文件（暂存区），由 FileProvider 暴露给相机 */
    fun newCameraCaptureFile(): File {
        tmpDir.mkdirs()
        return File(tmpDir, "${UUID.randomUUID()}.jpg")
    }

    /** 相册图片导入到暂存区（重采样压缩、按 EXIF 转正） */
    fun stageFromGallery(context: Context, uri: Uri): File? {
        val dst = newCameraCaptureFile()
        return try {
            context.contentResolver.openInputStream(uri)?.use { input ->
                val raw = input.readBytes()
                writeCompressed(raw, dst)
                dst as File?
            } ?: run { dst.delete(); null }
        } catch (e: Exception) {
            dst.delete()
            null
        }
    }

    /** 相机拍完的照片也做一次压缩/转正 */
    fun normalizeInPlace(file: File) {
        if (!file.exists()) return
        runCatching { writeCompressed(file.readBytes(), file) }
    }

    /** 将暂存图片转正到 items/{itemId}/{defId}/ 下，返回相对路径 */
    fun commit(itemId: Long, defId: Long, staged: File): String? {
        if (!staged.exists()) return null
        val dir = File(root, "items/$itemId/$defId").apply { mkdirs() }
        val dst = File(dir, staged.name)
        return if (staged.renameTo(dst)) relativeTo(dst) else null
    }

    fun delete(relativePath: String?) {
        if (relativePath.isNullOrEmpty()) return
        runCatching { fileOf(relativePath).delete() }
    }

    fun deleteItemImages(itemId: Long) {
        File(root, "items/$itemId").deleteRecursively()
    }

    fun deleteAttrDir(itemId: Long, defId: Long) {
        File(root, "items/$itemId/$defId").deleteRecursively()
    }

    /** 清理暂存区（启动时调用，丢弃上次未保存的草稿图） */
    fun cleanTmp() {
        tmpDir.listFiles()?.forEach { it.delete() }
    }

    private fun writeCompressed(data: ByteArray, dst: File) {
        val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        BitmapFactory.decodeByteArray(data, 0, data.size, bounds)
        var sample = 1
        while (maxOf(bounds.outWidth, bounds.outHeight) / (sample * 2) >= MAX_DIM) {
            sample *= 2
        }
        val opts = BitmapFactory.Options().apply { inSampleSize = sample }
        val decoded = BitmapFactory.decodeByteArray(data, 0, data.size, opts) ?: return
        val rotated = applyExifRotation(data, decoded)
        FileOutputStream(dst).use { out ->
            rotated.compress(Bitmap.CompressFormat.JPEG, JPEG_QUALITY, out)
        }
        if (rotated !== decoded) rotated.recycle()
        decoded.recycle()
    }

    private fun applyExifRotation(data: ByteArray, bitmap: Bitmap): Bitmap {
        val degrees = try {
            when (
                ExifInterface(data.inputStream())
                    .getAttributeInt(ExifInterface.TAG_ORIENTATION, ExifInterface.ORIENTATION_NORMAL)
            ) {
                ExifInterface.ORIENTATION_ROTATE_90 -> 90f
                ExifInterface.ORIENTATION_ROTATE_180 -> 180f
                ExifInterface.ORIENTATION_ROTATE_270 -> 270f
                else -> 0f
            }
        } catch (e: Exception) {
            0f
        }
        if (degrees == 0f) return bitmap
        val matrix = Matrix().apply { postRotate(degrees) }
        return Bitmap.createBitmap(bitmap, 0, 0, bitmap.width, bitmap.height, matrix, true)
    }

    companion object {
        private const val MAX_DIM = 1600
        private const val JPEG_QUALITY = 85
    }
}
