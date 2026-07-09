package com.learnical.app

import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.launch
import kotlin.math.roundToInt

// --- Shared bits ---

@Composable
private fun ErrorText(message: String) {
    Text(
        message,
        color = MaterialTheme.colorScheme.error,
        style = MaterialTheme.typography.bodySmall,
        modifier = Modifier.padding(vertical = 4.dp),
    )
}

@Composable
private fun ScoreBar(label: String, value: Double) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Text(label, modifier = Modifier.width(110.dp), style = MaterialTheme.typography.bodySmall)
        LinearProgressIndicator(
            progress = { value.toFloat().coerceIn(0f, 1f) },
            modifier = Modifier.weight(1f),
            color = LearnicalGreen,
        )
        Text(
            "${(value * 100).roundToInt()}%",
            modifier = Modifier.width(48.dp),
            textAlign = TextAlign.End,
            style = MaterialTheme.typography.bodySmall,
        )
    }
}

@Composable
private fun PhotoButtons(picker: PhotoPicker, hasPhoto: Boolean) {
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        Button(onClick = picker.takePhoto, modifier = Modifier.weight(1f)) {
            Text(if (hasPhoto) "Retake photo" else "Take photo")
        }
        OutlinedButton(onClick = picker.pickFromGallery, modifier = Modifier.weight(1f)) {
            Text("Gallery")
        }
    }
}

// --- Solve (the Photomath moment) ---

@Composable
fun SolveScreen(modifier: Modifier = Modifier) {
    var photo by remember { mutableStateOf<CapturedPhoto?>(null) }
    var hint by remember { mutableStateOf("") }
    var loading by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    var result by remember { mutableStateOf<SolveResult?>(null) }
    val scope = rememberCoroutineScope()
    val picker = rememberPhotoPicker {
        photo = it
        result = null
        error = null
    }

    Column(
        modifier = modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text("Solve a problem", style = MaterialTheme.typography.titleLarge)
        Text(
            "Point the camera at a question and get the method, step by step.",
            style = MaterialTheme.typography.bodyMedium,
        )

        photo?.let {
            Image(
                bitmap = it.preview.asImageBitmap(),
                contentDescription = "Captured problem",
                modifier = Modifier
                    .fillMaxWidth()
                    .heightIn(max = 260.dp),
                contentScale = ContentScale.Fit,
            )
        }

        PhotoButtons(picker, photo != null)

        OutlinedTextField(
            value = hint,
            onValueChange = { hint = it },
            label = { Text("Optional note (e.g. “question 3 only”)") },
            modifier = Modifier.fillMaxWidth(),
        )

        Button(
            onClick = {
                val p = photo ?: return@Button
                loading = true
                error = null
                scope.launch {
                    try {
                        result = LearnicalApi.solvePhoto(p.bytes, hint)
                    } catch (e: Exception) {
                        error = e.message ?: "Something went wrong"
                    } finally {
                        loading = false
                    }
                }
            },
            enabled = photo != null && !loading,
            modifier = Modifier.fillMaxWidth(),
        ) {
            if (loading) CircularProgressIndicator(
                modifier = Modifier.size(18.dp),
                color = Color.White,
                strokeWidth = 2.dp,
            )
            else Text("Explain it")
        }

        error?.let { ErrorText(it) }

        result?.let { r ->
            Card(colors = CardDefaults.cardColors()) {
                Column(Modifier.padding(14.dp)) {
                    Text("PROBLEM", style = MaterialTheme.typography.labelSmall)
                    Text(r.problem, fontWeight = FontWeight.Medium)
                }
            }
            r.steps.forEachIndexed { i, step ->
                Card {
                    Row(Modifier.padding(14.dp)) {
                        Box(
                            modifier = Modifier
                                .size(28.dp)
                                .background(LearnicalGreen.copy(alpha = 0.15f), CircleShape),
                            contentAlignment = Alignment.Center,
                        ) {
                            Text("${i + 1}", color = LearnicalGreen, fontWeight = FontWeight.Bold)
                        }
                        Spacer(Modifier.width(12.dp))
                        Column {
                            Text(step.title, fontWeight = FontWeight.SemiBold)
                            Text(step.explanation, style = MaterialTheme.typography.bodySmall)
                            Spacer(Modifier.height(6.dp))
                            Text(
                                step.work,
                                style = MaterialTheme.typography.bodyMedium,
                                fontWeight = FontWeight.Medium,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                    }
                }
            }
            Card(colors = CardDefaults.cardColors(containerColor = LearnicalGreen.copy(alpha = 0.12f))) {
                Column(Modifier.padding(14.dp)) {
                    Text("ANSWER", style = MaterialTheme.typography.labelSmall)
                    Text(r.answer, fontSize = 18.sp, fontWeight = FontWeight.Bold)
                    Spacer(Modifier.height(4.dp))
                    Text(r.concept, style = MaterialTheme.typography.bodySmall)
                }
            }
        }
    }
}

// --- Grade (scan a finished worksheet) ---

@Composable
fun GradeScreen(modifier: Modifier = Modifier) {
    var photo by remember { mutableStateOf<CapturedPhoto?>(null) }
    var worksheetId by remember { mutableStateOf("") }
    var studentId by remember { mutableStateOf("1") }
    var loading by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    var result by remember { mutableStateOf<StudentWorksheet?>(null) }
    val scope = rememberCoroutineScope()
    val picker = rememberPhotoPicker {
        photo = it
        result = null
        error = null
    }

    Column(
        modifier = modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text("Scan a worksheet", style = MaterialTheme.typography.titleLarge)
        Text(
            "Grades every question on the final answer, the method, and the work shown.",
            style = MaterialTheme.typography.bodyMedium,
        )

        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedTextField(
                value = worksheetId,
                onValueChange = { worksheetId = it.filter(Char::isDigit) },
                label = { Text("Worksheet ID") },
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                modifier = Modifier.weight(1f),
            )
            OutlinedTextField(
                value = studentId,
                onValueChange = { studentId = it.filter(Char::isDigit) },
                label = { Text("Student ID") },
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                modifier = Modifier.weight(1f),
            )
        }

        photo?.let {
            Image(
                bitmap = it.preview.asImageBitmap(),
                contentDescription = "Captured worksheet",
                modifier = Modifier
                    .fillMaxWidth()
                    .heightIn(max = 260.dp),
                contentScale = ContentScale.Fit,
            )
        }

        PhotoButtons(picker, photo != null)

        Button(
            onClick = {
                val p = photo ?: return@Button
                val wid = worksheetId.toIntOrNull() ?: return@Button
                val sid = studentId.toIntOrNull() ?: return@Button
                loading = true
                error = null
                scope.launch {
                    try {
                        result = LearnicalApi.gradeWorksheet(wid, sid, p.bytes)
                    } catch (e: Exception) {
                        error = e.message ?: "Something went wrong"
                    } finally {
                        loading = false
                    }
                }
            },
            enabled = photo != null && worksheetId.isNotBlank() && studentId.isNotBlank() && !loading,
            modifier = Modifier.fillMaxWidth(),
        ) {
            if (loading) CircularProgressIndicator(
                modifier = Modifier.size(18.dp),
                color = Color.White,
                strokeWidth = 2.dp,
            )
            else Text("Grade it")
        }

        error?.let { ErrorText(it) }

        result?.let { r ->
            val max = r.maxScore ?: 1.0
            val pct = if (max > 0) ((r.totalScore ?: 0.0) / max * 100).roundToInt() else 0
            Card(colors = CardDefaults.cardColors(containerColor = LearnicalGreen.copy(alpha = 0.12f))) {
                Row(
                    Modifier
                        .fillMaxWidth()
                        .padding(14.dp),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Column {
                        Text("Overall", fontWeight = FontWeight.SemiBold)
                        Text(
                            "${r.totalScore} / ${r.maxScore} points",
                            style = MaterialTheme.typography.bodySmall,
                        )
                    }
                    Text("$pct%", fontSize = 26.sp, fontWeight = FontWeight.Bold, color = LearnicalGreen)
                }
            }
            r.marks.entries.sortedBy { it.key.toIntOrNull() ?: Int.MAX_VALUE }.forEach { (qid, mark) ->
                Card {
                    Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                        Row(
                            Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween,
                        ) {
                            Text("Question $qid", fontWeight = FontWeight.SemiBold)
                            Text(
                                "${(mark.score * 100).roundToInt()}%",
                                fontWeight = FontWeight.Bold,
                                color = LearnicalGreen,
                            )
                        }
                        if (mark.transcription.isNotBlank()) {
                            Text(
                                mark.transcription,
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                        ScoreBar("Final answer", mark.finalAnswerScore)
                        ScoreBar("Method", mark.methodScore)
                        ScoreBar("Work shown", mark.workShownScore)
                        if (mark.feedback.isNotBlank()) {
                            Text(mark.feedback, style = MaterialTheme.typography.bodySmall)
                        }
                    }
                }
            }
        }
    }
}

// --- Progress ---

@Composable
fun ProgressScreen(modifier: Modifier = Modifier) {
    var studentId by remember { mutableStateOf("1") }
    var student by remember { mutableStateOf<Student?>(null) }
    var error by remember { mutableStateOf<String?>(null) }
    var loading by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()

    fun load(id: Int) {
        loading = true
        error = null
        scope.launch {
            try {
                student = LearnicalApi.getStudent(id)
            } catch (e: Exception) {
                student = null
                error = e.message ?: "Could not load student"
            } finally {
                loading = false
            }
        }
    }

    LaunchedEffect(Unit) { load(1) }

    Column(
        modifier = modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Row(
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text("Progress", style = MaterialTheme.typography.titleLarge, modifier = Modifier.weight(1f))
            OutlinedTextField(
                value = studentId,
                onValueChange = { studentId = it.filter(Char::isDigit) },
                label = { Text("Student") },
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                modifier = Modifier.width(110.dp),
            )
            Button(onClick = { studentId.toIntOrNull()?.let(::load) }) { Text("Load") }
        }

        if (loading) CircularProgressIndicator(color = LearnicalGreen)
        error?.let { ErrorText(it) }

        student?.let { s ->
            Card {
                Row(
                    Modifier
                        .fillMaxWidth()
                        .padding(14.dp),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Column {
                        Text(s.name, fontWeight = FontWeight.SemiBold)
                        s.gradeLevel?.let {
                            Text("Grade $it", style = MaterialTheme.typography.bodySmall)
                        }
                    }
                    Column(horizontalAlignment = Alignment.End) {
                        Text("🔥 ${s.streakDays}", fontSize = 22.sp, fontWeight = FontWeight.Bold)
                        Text("day streak", style = MaterialTheme.typography.labelSmall)
                    }
                }
            }

            Card {
                Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("By subject", fontWeight = FontWeight.SemiBold)
                    if (s.subjectPercentiles.isEmpty()) {
                        Text(
                            "No subject stats yet — grade a worksheet to get started.",
                            style = MaterialTheme.typography.bodySmall,
                        )
                    } else {
                        s.subjectPercentiles.entries.sortedBy { it.key }.forEach { (k, v) ->
                            val pct = if (v <= 1.0) v else v / 100.0
                            ScoreBar(k.replaceFirstChar(Char::uppercase), pct)
                        }
                    }
                }
            }

            Card {
                Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("Skills", fontWeight = FontWeight.SemiBold)
                    if (s.learningSkills.isEmpty()) {
                        Text(
                            "Skills appear here after more graded work.",
                            style = MaterialTheme.typography.bodySmall,
                        )
                    } else {
                        s.learningSkills.entries.sortedByDescending { it.value }.forEach { (k, v) ->
                            ScoreBar(k.replace('_', ' '), v / 100.0)
                        }
                    }
                    if (s.mastered.isNotEmpty()) {
                        Text(
                            "Mastered: " + s.mastered.joinToString(", ") { it.replace('_', ' ') },
                            style = MaterialTheme.typography.bodySmall,
                            color = LearnicalGreen,
                        )
                    }
                }
            }
        }
    }
}
