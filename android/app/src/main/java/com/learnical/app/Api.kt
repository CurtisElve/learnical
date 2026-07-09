package com.learnical.app

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import java.io.IOException
import java.util.concurrent.TimeUnit

// --- Models (mirror python/models.py responses) ---

@Serializable
data class SolveStep(val title: String, val explanation: String, val work: String)

@Serializable
data class SolveResult(
    val problem: String,
    val steps: List<SolveStep>,
    val answer: String,
    val concept: String,
)

@Serializable
data class QuestionMark(
    @SerialName("question_id") val questionId: Int = 0,
    val transcription: String = "",
    @SerialName("final_answer") val finalAnswer: String = "",
    @SerialName("final_answer_score") val finalAnswerScore: Double = 0.0,
    @SerialName("method_score") val methodScore: Double = 0.0,
    @SerialName("work_shown_score") val workShownScore: Double = 0.0,
    val score: Double = 0.0,
    @SerialName("max_score") val maxScore: Double = 1.0,
    val feedback: String = "",
)

@Serializable
data class StudentWorksheet(
    val id: Int,
    @SerialName("student_id") val studentId: Int,
    @SerialName("worksheet_id") val worksheetId: Int,
    val marks: Map<String, QuestionMark> = emptyMap(),
    @SerialName("total_score") val totalScore: Double? = null,
    @SerialName("max_score") val maxScore: Double? = null,
)

@Serializable
data class Student(
    val id: Int,
    val name: String,
    @SerialName("learning_skills") val learningSkills: Map<String, Double> = emptyMap(),
    @SerialName("subject_percentiles") val subjectPercentiles: Map<String, Double> = emptyMap(),
    val mastered: List<String> = emptyList(),
    @SerialName("streak_days") val streakDays: Int = 0,
    @SerialName("grade_level") val gradeLevel: String? = null,
)

@Serializable
private data class ApiError(val detail: String? = null)

@Serializable
private data class SolveRequest(val question: String)

class ApiException(message: String) : IOException(message)

// --- Client ---

object LearnicalApi {
    private val client = OkHttpClient.Builder()
        // Grading and solving are single long model calls
        .readTimeout(180, TimeUnit.SECONDS)
        .build()

    private val json = Json { ignoreUnknownKeys = true }
    private val jsonMedia = "application/json".toMediaType()
    private val jpegMedia = "image/jpeg".toMediaType()

    private inline fun <reified T> execute(request: Request): T {
        client.newCall(request).execute().use { response ->
            val body = response.body?.string().orEmpty()
            if (!response.isSuccessful) {
                val detail = runCatching {
                    json.decodeFromString<ApiError>(body).detail
                }.getOrNull()
                throw ApiException(detail ?: "Request failed (${response.code})")
            }
            return json.decodeFromString(body)
        }
    }

    suspend fun solvePhoto(imageBytes: ByteArray, hint: String?): SolveResult =
        withContext(Dispatchers.IO) {
            val form = MultipartBody.Builder().setType(MultipartBody.FORM)
                .addFormDataPart("file", "problem.jpg", imageBytes.toRequestBody(jpegMedia))
            if (!hint.isNullOrBlank()) form.addFormDataPart("hint", hint)
            execute(
                Request.Builder()
                    .url("${BuildConfig.API_URL}/solve/photo")
                    .post(form.build())
                    .build()
            )
        }

    suspend fun solveText(question: String): SolveResult = withContext(Dispatchers.IO) {
        val payload = json.encodeToString(SolveRequest.serializer(), SolveRequest(question))
        execute(
            Request.Builder()
                .url("${BuildConfig.API_URL}/solve")
                .post(payload.toRequestBody(jsonMedia))
                .build()
        )
    }

    suspend fun gradeWorksheet(
        worksheetId: Int,
        studentId: Int,
        imageBytes: ByteArray,
    ): StudentWorksheet = withContext(Dispatchers.IO) {
        val form = MultipartBody.Builder().setType(MultipartBody.FORM)
            .addFormDataPart("file", "worksheet.jpg", imageBytes.toRequestBody(jpegMedia))
            .build()
        execute(
            Request.Builder()
                .url("${BuildConfig.API_URL}/grade?worksheet_id=$worksheetId&student_id=$studentId")
                .post(form)
                .build()
        )
    }

    suspend fun getStudent(studentId: Int): Student = withContext(Dispatchers.IO) {
        execute(
            Request.Builder()
                .url("${BuildConfig.API_URL}/students/$studentId")
                .get()
                .build()
        )
    }
}
