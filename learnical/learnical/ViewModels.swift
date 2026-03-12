import Foundation
import SwiftUI
import UIKit

// MARK: - Grade capture

@MainActor
final class GradeCaptureViewModel: ObservableObject {
    @Published var isLoading = false
    @Published var latestResult: StudentWorksheet?
    @Published var errorMessage: String?

    private let api: LearnicalAPI

    init(api: LearnicalAPI = .shared) {
        self.api = api
    }

    func grade(worksheetId: Int, image: UIImage) async {
        guard worksheetId > 0 else {
            errorMessage = "Please enter a valid worksheet ID."
            latestResult = nil
            return
        }

        isLoading = true
        errorMessage = nil

        do {
            let result = try await api.gradeWorksheet(
                worksheetId: worksheetId,
                studentId: 0, // always student 0 per requirements
                image: image
            )
            latestResult = result
        } catch {
            if let apiError = error as? LearnicalAPI.APIError {
                errorMessage = apiError.errorDescription
            } else {
                errorMessage = error.localizedDescription
            }
            latestResult = nil
        }

        isLoading = false
    }
}

// MARK: - Grades dashboard

@MainActor
final class GradesDashboardViewModel: ObservableObject {
    @Published var isLoading = false
    @Published var student: Student?
    @Published var errorMessage: String?

    private let api: LearnicalAPI

    init(api: LearnicalAPI = .shared) {
        self.api = api
    }

    func load() async {
        isLoading = true
        errorMessage = nil

        do {
            // Always load stats for student id 0
            student = try await api.fetchStudent(studentId: 1)
        } catch {
            if let apiError = error as? LearnicalAPI.APIError {
                errorMessage = apiError.errorDescription
            } else {
                errorMessage = error.localizedDescription
            }
            student = nil
        }

        isLoading = false
    }
}

