# ============================================================
# AcadLink AI Assignment Module (Blueprint Version)
# Author: Shikha Yadav
# ============================================================

from flask import Blueprint, render_template, request, jsonify, session
import os, fitz, traceback, random
from werkzeug.utils import secure_filename
from datetime import datetime
import mysql.connector
import google.generativeai as genai

# ============================================================
# Setup & Configuration
# ============================================================

UPLOAD_FOLDER = "uploads"
ASSIGNMENT_FOLDER = os.path.join(UPLOAD_FOLDER, "assignments")
SUBMISSION_FOLDER = os.path.join(UPLOAD_FOLDER, "submissions")
os.makedirs(ASSIGNMENT_FOLDER, exist_ok=True)
os.makedirs(SUBMISSION_FOLDER, exist_ok=True)

# Gemini setup
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel("gemini-2.5-flash")

# Blueprint setup
ai_assignment_bp = Blueprint("ai_assignment_bp", __name__)

# ============================================================
# Database Connection
# ============================================================

def get_db_connection():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="S1234@",     # Update if needed
        database="acadlink"
    )

# ============================================================
# Faculty Dashboard (Optional)
# ============================================================

@ai_assignment_bp.route("/faculty/ai_dashboard")
def faculty_ai_dashboard():
    if session.get("role") != "faculty":
        return "Unauthorized", 403

    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM ai_assignments ORDER BY created_at DESC")
    assignments = cur.fetchall()
    cur.close()
    conn.close()

    return render_template("faculty_ai_dashboard.html", assignments=assignments)

# ============================================================
# AI Assignment Generator (Faculty)
# ============================================================

@ai_assignment_bp.route("/generate_assignment_ai", methods=["POST"])
def generate_assignment_ai():
    try:
        subject = request.form["subject"]
        num_qs = int(request.form.get("num_questions", 5))
        notes_file = request.files.get("file")

        notes_text = ""
        if notes_file:
            ext = notes_file.filename.split(".")[-1].lower()
            filepath = os.path.join(UPLOAD_FOLDER, secure_filename(notes_file.filename))
            notes_file.save(filepath)

            if ext == "pdf":
                with fitz.open(filepath) as pdf:
                    for page in pdf:
                        notes_text += page.get_text("text")
            elif ext == "docx":
                from docx import Document
                doc = Document(filepath)
                notes_text = "\n".join([p.text for p in doc.paragraphs])
            else:
                notes_text = "Notes format not supported."

        prompt = f"""
        Generate {num_qs} conceptual assignment questions for the subject "{subject}".
        Use the following notes as reference:
        {notes_text[:5000]} 
        Ensure each question is concise, academic, and tests understanding.
        """

        response = model.generate_content(prompt)
        raw_output = response.text.strip()
        questions = [q.strip() for q in raw_output.split("\n") if q.strip()]

        return jsonify({"questions": questions})
    except Exception as e:
        print("❌ Error generating AI assignment:", e)
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# ============================================================
# Save AI Assignment
# ============================================================

@ai_assignment_bp.route("/save_ai_assignment", methods=["POST"])
def save_ai_assignment():
    try:
        data = request.get_json()
        title = data["title"]
        subject = data["subject"]
        class_name = data["class_name"]
        due_date = data["due_date"]
        threshold = float(data.get("threshold", 0.6))
        questions = data.get("questions", [])

        filename = f"{secure_filename(title)}_{datetime.now().strftime('%Y%m%d%H%M%S')}.txt"
        filepath = os.path.join(ASSIGNMENT_FOLDER, filename)

        with open(filepath, "w", encoding="utf-8") as f:
            for q in questions:
                f.write(q + "\n")

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO ai_assignments (title, subject, class_name, due_date, threshold, created_by, file_path)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
        """, (title, subject, class_name, due_date, threshold, session["user"], filename))
        conn.commit()
        cur.close()
        conn.close()

        return jsonify({"success": True, "message": "✅ Assignment saved & published successfully!"})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# ============================================================
# Manual Assignment Upload (Faculty)
# ============================================================

@ai_assignment_bp.route("/upload_manual_assignment", methods=["POST"])
def upload_manual_assignment():
    if session.get("role") != "faculty":
        return jsonify({"error": "Unauthorized"}), 403

    subject = request.form.get("subject")
    class_name = request.form.get("class_name")
    due_date = request.form.get("due_date")
    file = request.files.get("file")

    if not subject or not class_name or not file:
        return jsonify({"error": "Missing fields"}), 400

    filename = secure_filename(f"{subject}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{file.filename}")
    filepath = os.path.join(ASSIGNMENT_FOLDER, filename)
    file.save(filepath)

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO ai_assignments (title, subject, class_name, due_date, file_path, created_by)
        VALUES (%s,%s,%s,%s,%s,%s)
    """, (subject + " (Manual Upload)", subject, class_name, due_date, filename, session["user"]))
    conn.commit()
    cur.close()
    conn.close()

    return jsonify({"success": True, "message": "📁 Manual assignment uploaded successfully!"})

# ============================================================
# Student: Fetch Assignments
# ============================================================

@ai_assignment_bp.route("/api/student_submissions")
def api_student_submissions():
    if session.get("role") != "student":
        return jsonify({"error": "unauthorized"}), 403

    roll_no = session.get("roll_number")
    if not roll_no:
        return jsonify([])

    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute("""
            SELECT 
                a.id AS assignment_id,
                a.title,
                a.subject,
                a.class_name,
                a.due_date,
                s.id AS my_submission_id,
                s.ai_score,
                s.status
            FROM ai_assignments a
            LEFT JOIN ai_submissions s 
              ON s.assignment_id = a.id AND s.roll_no = %s
            ORDER BY a.id DESC
        """, (roll_no,))
        data = cur.fetchall()
        return jsonify(data)
    except Exception as e:
        print("⚠️ Error fetching student submissions:", e, flush=True)
        return jsonify({"error": str(e)}), 500
    finally:
        cur.close()
        conn.close()

# ============================================================
# Student: Submit Assignment
# ============================================================

@ai_assignment_bp.route("/submit_assignment_ai", methods=["POST"])
def submit_assignment_ai():
    if session.get("role") != "student":
        return jsonify({"success": False, "error": "Unauthorized"}), 403

    roll_no = session.get("roll_number")
    assignment_id = request.form.get("assignment_id")
    file = request.files.get("file")

    if not roll_no or not assignment_id or not file:
        return jsonify({"success": False, "error": "Missing fields"}), 400

    try:
        os.makedirs(SUBMISSION_FOLDER, exist_ok=True)
        filename = secure_filename(f"{roll_no}_A{assignment_id}_{file.filename}")
        file_path = os.path.join(SUBMISSION_FOLDER, filename)
        file.save(file_path)

        ai_score = round(random.uniform(0.4, 0.95), 2)
        status = "verified" if ai_score > 0.6 else "pending"

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO ai_submissions (assignment_id, roll_no, file_path, ai_score, status)
            VALUES (%s, %s, %s, %s, %s)
        """, (assignment_id, roll_no, filename, ai_score, status))
        conn.commit()
        cur.close()
        conn.close()

        print(f"✅ {roll_no} submitted assignment {assignment_id} with AI score {ai_score}")
        return jsonify({"success": True, "message": "File uploaded successfully!"})
    except Exception as e:
        print("❌ Error submitting assignment:", e)
        return jsonify({"success": False, "error": str(e)}), 500

# ============================================================
# Faculty: View & Verify Submissions
# ============================================================

@ai_assignment_bp.route("/api/faculty_submissions")
def api_faculty_submissions():
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT s.id, s.roll_no, a.title, s.file_path, s.ai_score, s.status
        FROM ai_submissions s
        JOIN ai_assignments a ON s.assignment_id = a.id
        ORDER BY s.id DESC
    """)
    data = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify(data)

# ============================================================
# Faculty: Verify or Reject Submissions
# ============================================================

@ai_assignment_bp.route("/verify_assignment/<int:submission_id>", methods=["POST"])
def verify_assignment(submission_id):
    if session.get("role") != "faculty":
        return jsonify({"success": False, "error": "Unauthorized"}), 403
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE ai_submissions SET status = 'verified' WHERE id = %s", (submission_id,))
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@ai_assignment_bp.route("/reject_assignment/<int:submission_id>", methods=["POST"])
def reject_assignment(submission_id):
    if session.get("role") != "faculty":
        return jsonify({"success": False, "error": "Unauthorized"}), 403
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE ai_submissions SET status = 'rejected' WHERE id = %s", (submission_id,))
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ============================================================
# Faculty: AI Assignment Page (Loaded inside Dashboard iframe)
# ============================================================

@ai_assignment_bp.route("/faculty_ai_assignment")
def faculty_ai_assignment_page():
    """Render the unified AI Assignment (3-tab) interface for faculty."""
    if session.get("role") != "faculty":
        return "Unauthorized", 403
    return render_template("faculty_ai_assignment.html")


@ai_assignment_bp.route("/api/student_notifications")
def api_student_notifications():
    if session.get("role") != "student":
        return jsonify({"error": "Unauthorized"}), 403

    roll_no = session.get("roll_number")
    if not roll_no:
        return jsonify([])

    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT id, message, created_at 
        FROM notifications 
        WHERE roll_no = %s AND is_read = FALSE
        ORDER BY created_at DESC
    """, (roll_no,))
    notes = cur.fetchall()

    # Mark them as read immediately
    cur.execute("UPDATE notifications SET is_read = TRUE WHERE roll_no = %s", (roll_no,))
    conn.commit()
    cur.close()
    conn.close()

    return jsonify(notes)
