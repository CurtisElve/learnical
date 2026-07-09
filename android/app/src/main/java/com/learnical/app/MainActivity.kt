package com.learnical.app

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Create
import androidx.compose.material.icons.filled.Face
import androidx.compose.material.icons.filled.Star

val LearnicalGreen = Color(0xFF17BA78)

private val ColorScheme = lightColorScheme(
    primary = LearnicalGreen,
    secondary = LearnicalGreen,
)

private data class Tab(val label: String, val icon: ImageVector)

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            MaterialTheme(colorScheme = ColorScheme) {
                var selected by rememberSaveable { mutableIntStateOf(0) }
                val tabs = listOf(
                    Tab("Solve", Icons.Filled.Star),
                    Tab("Grade", Icons.Filled.Create),
                    Tab("Progress", Icons.Filled.Face),
                )
                Scaffold(
                    bottomBar = {
                        NavigationBar {
                            tabs.forEachIndexed { i, tab ->
                                NavigationBarItem(
                                    selected = selected == i,
                                    onClick = { selected = i },
                                    icon = { Icon(tab.icon, contentDescription = tab.label) },
                                    label = { Text(tab.label) },
                                )
                            }
                        }
                    }
                ) { padding ->
                    val modifier = Modifier.padding(padding)
                    when (selected) {
                        0 -> SolveScreen(modifier)
                        1 -> GradeScreen(modifier)
                        else -> ProgressScreen(modifier)
                    }
                }
            }
        }
    }
}
