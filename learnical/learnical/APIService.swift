import Foundation
import UIKit

final class LearnicalAPI {
    static let shared = LearnicalAPI()
    static let baseURL = "http://127.0.0.1:8000"

    enum APIError: Error, LocalizedError {
        case invalidURL
        case requestFailed(Error)
        case invalidResponse
        case serverError(Int, Data?)
        case decodingError(Error)
        case invalidImageData

        var errorDescription: String? {
            switch self {
            case .invalidURL:
                return "The server URL is invalid."
            case .requestFailed(let error):
                return "Network request failed: \(error.localizedDescription)"
            case .invalidResponse:
                return "Received an invalid response from the server."
            case .serverError(let statusCode, _):
                return "Server returned an error (code \(statusCode))."
            case .decodingError:
                return "We couldn't read the data from the server."
            case .invalidImageData:
                return "Unable to process the selected image."
            }
        }
    }

    private let decoder: JSONDecoder

    private init() {
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        self.decoder = decoder
    }

    // MARK: - Generic JSON request

    private func requestJSON<T: Decodable>(
        method: String = "GET",
        path: String
    ) async throws -> T {
        let urlString: String
        if path.hasPrefix("http") {
            urlString = path
        } else {
            urlString = Self.baseURL + path
        }

        guard let url = URL(string: urlString) else {
            throw APIError.invalidURL
        }

        var request = URLRequest(url: url)
        request.httpMethod = method

        do {
            let (data, response) = try await URLSession.shared.data(for: request)

            guard let httpResponse = response as? HTTPURLResponse else {
                throw APIError.invalidResponse
            }

            guard (200..<300).contains(httpResponse.statusCode) else {
                throw APIError.serverError(httpResponse.statusCode, data)
            }

            do {
                return try decoder.decode(T.self, from: data)
            } catch {
                throw APIError.decodingError(error)
            }
        } catch {
            throw APIError.requestFailed(error)
        }
    }

    // MARK: - Public endpoints

    func fetchStudent(studentId: Int) async throws -> Student {
        try await requestJSON(path: "/students/\(studentId)")
    }

    func gradeWorksheet(
        worksheetId: Int,
        studentId: Int,
        image: UIImage
    ) async throws -> StudentWorksheet {
        guard let imageData = image.jpegData(compressionQuality: 0.9) else {
            throw APIError.invalidImageData
        }

        var components = URLComponents(string: Self.baseURL + "/grade")
        components?.queryItems = [
            URLQueryItem(name: "worksheet_id", value: String(worksheetId)),
            URLQueryItem(name: "student_id", value: String(studentId))
        ]

        guard let url = components?.url else {
            throw APIError.invalidURL
        }

        var request = URLRequest(url: url)
        request.httpMethod = "POST"

        let boundary = UUID().uuidString
        request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")

        var body = Data()
        let filename = "worksheet.jpg"
        let fieldName = "file"
        let mimeType = "image/jpeg"

        body.append("--\(boundary)\r\n".data(using: .utf8)!)
        body.append("Content-Disposition: form-data; name=\"\(fieldName)\"; filename=\"\(filename)\"\r\n".data(using: .utf8)!)
        body.append("Content-Type: \(mimeType)\r\n\r\n".data(using: .utf8)!)
        body.append(imageData)
        body.append("\r\n".data(using: .utf8)!)
        body.append("--\(boundary)--\r\n".data(using: .utf8)!)

        request.httpBody = body

        do {
            let (data, response) = try await URLSession.shared.data(for: request)

            guard let httpResponse = response as? HTTPURLResponse else {
                throw APIError.invalidResponse
            }

            guard (200..<300).contains(httpResponse.statusCode) else {
                throw APIError.serverError(httpResponse.statusCode, data)
            }

            do {
                return try decoder.decode(StudentWorksheet.self, from: data)
            } catch {
                throw APIError.decodingError(error)
            }
        } catch {
            throw APIError.requestFailed(error)
        }
    }
}

// MARK: - Models

struct Student: Decodable, Identifiable {
    let id: Int
    let name: String
    let learning_skills: [String: Double]
    let subject_percentiles: [String: Double]
    let streak_days: Int

    private enum CodingKeys: String, CodingKey {
        case id
        case name
        case learning_skills
        case subject_percentiles
        case streak_days
    }

    init(
        id: Int,
        name: String,
        learning_skills: [String: Double] = [:],
        subject_percentiles: [String: Double] = [:],
        streak_days: Int = 0
    ) {
        self.id = id
        self.name = name
        self.learning_skills = learning_skills
        self.subject_percentiles = subject_percentiles
        self.streak_days = streak_days
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = try container.decode(Int.self, forKey: .id)
        name = try container.decode(String.self, forKey: .name)
        learning_skills = try container.decodeIfPresent([String: Double].self, forKey: .learning_skills) ?? [:]
        subject_percentiles = try container.decodeIfPresent([String: Double].self, forKey: .subject_percentiles) ?? [:]
        streak_days = try container.decodeIfPresent(Int.self, forKey: .streak_days) ?? 0
    }
}

struct StudentWorksheet: Decodable, Identifiable {
    let id: Int
    let student_id: Int
    let worksheet_id: Int
    let total_score: Double?
    let max_score: Double?
}

