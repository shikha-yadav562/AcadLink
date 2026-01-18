-- ============================================================
-- AcadLink AI Assignment Module Database Setup
-- ============================================================

-- 🧠 Table for AI-generated assignments
CREATE TABLE IF NOT EXISTS ai_assignments (
    id INT AUTO_INCREMENT PRIMARY KEY,
    title VARCHAR(255),
    subject VARCHAR(100),
    class_name VARCHAR(100),
    due_date DATE,
    threshold FLOAT DEFAULT 0.6,
    created_by VARCHAR(255),
    file_path VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 📑 Table for student submissions
CREATE TABLE IF NOT EXISTS ai_submissions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    assignment_id INT,
    roll_no VARCHAR(50),
    file_path VARCHAR(255),
    ai_score FLOAT,
    verified BOOLEAN DEFAULT FALSE,
    status ENUM('pending','verified','rejected') DEFAULT 'pending',
    submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (assignment_id) REFERENCES ai_assignments(id)
);

-- 🔔 Add notification table if not exists
CREATE TABLE IF NOT EXISTS notifications (
    id INT AUTO_INCREMENT PRIMARY KEY,
    roll_no VARCHAR(50),
    message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- DEMO DATA (for instant testing)
-- ============================================================

INSERT INTO ai_assignments (title, subject, class_name, due_date, threshold, created_by, file_path)
VALUES 
('Database Design Project', 'DBMS', 'TYIT', '2025-10-20', 0.6, 'faculty1@college.com', 'DBMS_Assignment.txt'),
('Operating Systems Questions', 'OS', 'TYIT', '2025-10-22', 0.7, 'faculty1@college.com', 'OS_Assignment.txt');

INSERT INTO ai_submissions (assignment_id, roll_no, file_path, ai_score, verified, status)
VALUES 
(1, 'TYIT001', 'TYIT001_DBMS_Assignment.pdf', 0.32, TRUE, 'verified'),
(1, 'TYIT002', 'TYIT002_DBMS_Assignment.pdf', 0.78, FALSE, 'rejected'),
(2, 'TYIT001', 'TYIT001_OS_Assignment.pdf', 0.45, FALSE, 'pending');
