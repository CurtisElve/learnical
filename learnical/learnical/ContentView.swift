//
//  ContentView.swift
//  learnical
//
//  Created by Curtis on 2026-03-09.
//

import SwiftUI
import UIKit

// MARK: - Shared styling

extension Color {
    static let learnicalGreen = Color(red: 0.09, green: 0.73, blue: 0.47)
}

// MARK: - Root entry view

struct ContentView: View {
    var body: some View {
        MainTabView()
            .tint(Color.learnicalGreen)
    }
}

// MARK: - Main shell (2 tabs)

struct MainTabView: View {
    var body: some View {
        TabView {
            GradeCaptureScreen()
                .tabItem {
                    Label("Scan", systemImage: "camera.viewfinder")
                }

            GradesDashboardScreen()
                .tabItem {
                    Label("Grades", systemImage: "chart.bar.xaxis")
                }
        }
    }
}

// MARK: - Grade capture screen

struct GradeCaptureScreen: View {
    @StateObject private var viewModel = GradeCaptureViewModel()
    @State private var worksheetIdText: String = ""
    @State private var selectedImage: UIImage?
    @State private var isShowingCamera = false

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 24) {
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Scan worksheet")
                            .font(.title2.bold())
                        Text("Take a photo and send it to the grading AI.")
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)

                    VStack(spacing: 16) {
                        HStack {
                            Text("Worksheet ID")
                                .font(.subheadline.weight(.medium))
                            Spacer()
                        }

                        TextField("e.g. 1", text: $worksheetIdText)
                            .keyboardType(.numberPad)
                            .padding(12)
                            .background(
                                RoundedRectangle(cornerRadius: 12, style: .continuous)
                                    .fill(Color(.secondarySystemBackground))
                            )
                    }

                    VStack(spacing: 16) {
                        ZStack {
                            RoundedRectangle(cornerRadius: 18, style: .continuous)
                                .fill(Color(.secondarySystemBackground))
                                .overlay(
                                    RoundedRectangle(cornerRadius: 18, style: .continuous)
                                        .strokeBorder(Color.learnicalGreen.opacity(0.20), lineWidth: 1)
                                )

                            VStack(spacing: 12) {
                                if let image = selectedImage {
                                    Image(uiImage: image)
                                        .resizable()
                                        .scaledToFit()
                                        .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
                                        .shadow(color: .black.opacity(0.15), radius: 10, x: 0, y: 6)
                                } else {
                                    VStack(spacing: 8) {
                                        Image(systemName: "camera.viewfinder")
                                            .font(.system(size: 36))
                                            .foregroundStyle(Color.learnicalGreen)
                                        Text("No photo selected")
                                            .font(.subheadline)
                                            .foregroundStyle(.secondary)
                                        Text("Tap the button below to open the camera.")
                                            .font(.caption)
                                            .foregroundStyle(.secondary)
                                    }
                                }
                            }
                            .padding()
                        }
                        .frame(maxWidth: .infinity)
                        .frame(height: 260)

                        HStack(spacing: 12) {
                            Button {
                                isShowingCamera = true
                            } label: {
                                Label("Take photo", systemImage: "camera.fill")
                                    .frame(maxWidth: .infinity)
                            }
                            .buttonStyle(.borderedProminent)
                            .tint(Color.learnicalGreen)

                            Button {
                                guard let worksheetId = Int(worksheetIdText),
                                      let image = selectedImage else {
                                    return
                                }

                                Task {
                                    await viewModel.grade(worksheetId: worksheetId, image: image)
                                }
                            } label: {
                                if viewModel.isLoading {
                                    ProgressView()
                                        .frame(maxWidth: .infinity)
                                } else {
                                    Label("Grade", systemImage: "sparkles")
                                        .frame(maxWidth: .infinity)
                                }
                            }
                            .buttonStyle(.borderedProminent)
                            .tint(Color.learnicalGreen)
                            .disabled(selectedImage == nil || Int(worksheetIdText) == nil || viewModel.isLoading)
                        }
                    }

                    if let error = viewModel.errorMessage {
                        Text(error)
                            .font(.footnote)
                            .foregroundStyle(.red)
                            .frame(maxWidth: .infinity, alignment: .leading)
                    }

                    if let result = viewModel.latestResult {
                        GradeResultCard(result: result)
                    }
                }
                .padding()
            }
            .background(Color(.systemBackground))
            .navigationTitle("Capture")
            .sheet(isPresented: $isShowingCamera) {
                CameraPicker { image in
                    selectedImage = image
                }
                .ignoresSafeArea()
            }
        }
    }
}

struct GradeResultCard: View {
    let result: StudentWorksheet

    var body: some View {
        let score = result.total_score ?? 0
        let maxScore = result.max_score ?? 1
        let percentage = maxScore > 0 ? score / maxScore : 0

        VStack(alignment: .leading, spacing: 16) {
            HStack {
                Text("Latest grade")
                    .font(.headline)
                Spacer()
                Text("Worksheet #\(result.worksheet_id)")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }

            HStack(alignment: .center, spacing: 16) {
                ZStack {
                    Circle()
                        .stroke(Color.learnicalGreen.opacity(0.15), lineWidth: 10)
                    Circle()
                        .trim(from: 0, to: CGFloat(min(max(percentage, 0), 1)))
                        .stroke(
                            AngularGradient(
                                gradient: Gradient(colors: [Color.learnicalGreen, .green, .mint]),
                                center: .center
                            ),
                            style: StrokeStyle(lineWidth: 10, lineCap: .round)
                        )
                        .rotationEffect(.degrees(-90))
                        .animation(.easeOut(duration: 0.5), value: percentage)

                    VStack {
                        Text("\(Int((percentage * 100).rounded()))%")
                            .font(.title2.bold())
                        Text("\(Int(score.rounded())) / \(Int(maxScore.rounded()))")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
                .frame(width: 110, height: 110)

                VStack(alignment: .leading, spacing: 8) {
                    Text("Great job!")
                        .font(.headline)
                    Text("These scores are stored for student #\(result.student_id) and can be used to drive the stats dashboard.")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }
            }
        }
        .padding()
        .background(
            RoundedRectangle(cornerRadius: 18, style: .continuous)
                .fill(Color(.secondarySystemBackground))
        )
    }
}

// MARK: - Grades dashboard

struct GradesDashboardScreen: View {
    @StateObject private var viewModel = GradesDashboardViewModel()

    var body: some View {
        NavigationStack {
            ZStack {
                Color(.systemBackground)
                    .ignoresSafeArea()

                ScrollView {
                    VStack(spacing: 20) {
                        headerSection

                        if viewModel.isLoading {
                            ProgressView()
                                .padding(.top, 40)
                        } else if let error = viewModel.errorMessage {
                            Text(error)
                                .font(.footnote)
                                .foregroundStyle(.red)
                        } else if let student = viewModel.student {
                            streakCard(student: student)
                            subjectsCard(student: student)
                            skillsCard(student: student)
                        } else {
                            Text("No data yet. Grade a worksheet to see stats.")
                                .font(.footnote)
                                .foregroundStyle(.secondary)
                                .padding(.top, 40)
                        }
                    }
                    .padding()
                }
            }
            .navigationTitle("Grades")
        }
        .task {
            await viewModel.load()
        }
    }

    private var headerSection: some View {
        HStack {
            VStack(alignment: .leading, spacing: 4) {
                Text("Progress overview")
                    .font(.title2.bold())
                Text("Student #0")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }
            Spacer()
            Image(systemName: "sparkles")
                .foregroundStyle(Color.learnicalGreen)
        }
    }

    private func streakCard(student: Student) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Label("Learning streak", systemImage: "flame.fill")
                    .font(.headline)
                    .foregroundStyle(.orange)
                Spacer()
                Text("\(student.streak_days) days")
                    .font(.headline)
            }

            ProgressView(value: min(Double(student.streak_days) / 30.0, 1.0))
                .tint(Color.learnicalGreen)

            Text("Keep the streak going for consistent progress.")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .padding()
        .background(
            RoundedRectangle(cornerRadius: 18, style: .continuous)
                .fill(Color(.secondarySystemBackground))
        )
    }

    private func subjectsCard(student: Student) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("By subject")
                    .font(.headline)
                Spacer()
                Image(systemName: "chart.bar.fill")
                    .foregroundStyle(Color.learnicalGreen)
            }

            if student.subject_percentiles.isEmpty {
                Text("No subject stats yet.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            } else {
                ForEach(student.subject_percentiles.sorted(by: { $0.key < $1.key }), id: \.key) { key, value in
                    VStack(alignment: .leading, spacing: 4) {
                        HStack {
                            Text(key.capitalized)
                                .font(.subheadline.weight(.medium))
                            Spacer()
                            Text("\(Int(value.rounded()))%")
                                .font(.subheadline)
                                .foregroundStyle(.secondary)
                        }

                        GeometryReader { geo in
                            let width = geo.size.width
                            let fraction = max(0, min(value / 100.0, 1.0))

                            ZStack(alignment: .leading) {
                                RoundedRectangle(cornerRadius: 8)
                                    .fill(Color(.systemGray5))
                                RoundedRectangle(cornerRadius: 8)
                                    .fill(
                                        LinearGradient(
                                            colors: [Color.learnicalGreen, .green],
                                            startPoint: .leading,
                                            endPoint: .trailing
                                        )
                                    )
                                    .frame(width: width * fraction)
                            }
                        }
                        .frame(height: 10)
                    }
                }
            }
        }
        .padding()
        .background(
            RoundedRectangle(cornerRadius: 18, style: .continuous)
                .fill(Color(.secondarySystemBackground))
        )
    }

    private func skillsCard(student: Student) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("Skills focus")
                    .font(.headline)
                Spacer()
                Image(systemName: "brain.head.profile")
                    .foregroundStyle(Color.learnicalGreen)
            }

            if student.learning_skills.isEmpty {
                Text("Skills will appear here after more graded worksheets.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            } else {
                let sortedSkills = student.learning_skills.sorted(by: { $0.value > $1.value })

                LazyVStack(alignment: .leading, spacing: 8) {
                    ForEach(sortedSkills, id: \.key) { skill, score in
                        HStack {
                            Text(skill.capitalized)
                                .font(.subheadline.weight(.medium))
                            Spacer()
                            Text("\(Int(score.rounded())) pts")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                        .padding(.horizontal, 10)
                        .padding(.vertical, 6)
                        .background(
                            Capsule()
                                .fill(Color.learnicalGreen.opacity(0.10))
                        )
                    }
                }
            }
        }
        .padding()
        .background(
            RoundedRectangle(cornerRadius: 18, style: .continuous)
                .fill(Color(.secondarySystemBackground))
        )
    }
}

#Preview {
    ContentView()
}
