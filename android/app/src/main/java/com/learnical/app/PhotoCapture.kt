package com.learnical.app

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.runtime.Composable
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.ui.platform.LocalContext
import androidx.core.content.FileProvider
import java.io.ByteArrayOutputStream
import java.io.File

/** A captured photo ready for upload: JPEG bytes plus a preview bitmap. */
class CapturedPhoto(val bytes: ByteArray, val preview: Bitmap)

private const val MAX_EDGE = 2000
private const val JPEG_QUALITY = 88

/** Decode, downscale to MAX_EDGE, and re-encode so uploads stay small. */
private fun loadPhoto(context: Context, uri: Uri): CapturedPhoto? {
    val resolver = context.contentResolver

    val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
    resolver.openInputStream(uri)?.use { BitmapFactory.decodeStream(it, null, bounds) }
    if (bounds.outWidth <= 0) return null

    var sample = 1
    while (maxOf(bounds.outWidth, bounds.outHeight) / (sample * 2) >= MAX_EDGE) sample *= 2

    val opts = BitmapFactory.Options().apply { inSampleSize = sample }
    val bitmap = resolver.openInputStream(uri)?.use {
        BitmapFactory.decodeStream(it, null, opts)
    } ?: return null

    val out = ByteArrayOutputStream()
    bitmap.compress(Bitmap.CompressFormat.JPEG, JPEG_QUALITY, out)
    return CapturedPhoto(out.toByteArray(), bitmap)
}

/**
 * Camera + gallery pickers that both deliver a [CapturedPhoto].
 * The camera path uses the system camera app via TakePicture, so no
 * CAMERA permission is required.
 */
class PhotoPicker(
    val takePhoto: () -> Unit,
    val pickFromGallery: () -> Unit,
)

@Composable
fun rememberPhotoPicker(onPhoto: (CapturedPhoto) -> Unit): PhotoPicker {
    val context = LocalContext.current
    val pendingUri = remember { mutableStateOf<Uri?>(null) }

    val cameraLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.TakePicture()
    ) { success ->
        val uri = pendingUri.value
        if (success && uri != null) {
            loadPhoto(context, uri)?.let(onPhoto)
        }
    }

    val galleryLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.GetContent()
    ) { uri ->
        if (uri != null) loadPhoto(context, uri)?.let(onPhoto)
    }

    return remember(cameraLauncher, galleryLauncher) {
        PhotoPicker(
            takePhoto = {
                val dir = File(context.cacheDir, "captures").apply { mkdirs() }
                val file = File.createTempFile("capture_", ".jpg", dir)
                val uri = FileProvider.getUriForFile(
                    context, "${context.packageName}.fileprovider", file
                )
                pendingUri.value = uri
                cameraLauncher.launch(uri)
            },
            pickFromGallery = { galleryLauncher.launch("image/*") },
        )
    }
}
