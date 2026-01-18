from flask import Flask, render_template, request, redirect, send_from_directory, url_for, flash, session,jsonify
import mysql.connector
import traceback 
from docx import Document 
import fitz  # PyMuPDF
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
import json
import pandas as pd
from datetime import datetime, timedelta
import os
from werkzeug.utils import secure_filename
from datetime import date
import csv
from flask import Response
import google.generativeai as genai
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv
from models.your_models import db
load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

model = genai.GenerativeModel("gemini-2.5-flash")


app = Flask(__name__)
app.secret_key = 'your_secret_key'  # Replace with a secure key
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+mysqlconnector://root:S1234@@localhost/acadlink'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

from ai_assignment_routes import ai_assignment_bp
app.register_blueprint(ai_assignment_bp)
print(app.url_map)
# -------------------- DATABASE SETUP --------------------
def get_db_connection():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="S1234@",  # your MySQL password
        database="acadlink"
    )


# -------------------- ROLE DETECTION --------------------
def detect_role(email):
    if email.endswith("@college.com"):   # all faculty emails end with @college.com
        return 'faculty'
    elif "cr" in email:
        return 'cr'
    else:
        return 'student'


# -------------------- ROUTES --------------------

@app.route('/')
def home():
    return render_template('home.html')
# ---------- STUDENT SIGNUP ONLY ----------
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    conn = get_db_connection()
    cursor = conn.cursor()
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        semester = request.form.get('semester')
        branch = request.form.get('branch')
        roll_number = request.form.get('roll_number')
        Class = request.form.get('Class')
        role = detect_role(email)

        if role != 'student':
            flash("❌ Signup is only allowed for students.", "danger")
            return redirect(url_for('signup'))

        try:
            cursor.execute("""
    INSERT INTO student (name, email, password, semester, `class`, branch, roll_number)
    VALUES (%s, %s, %s, %s, %s, %s, %s)
""", (name, email, password, semester, Class, branch, roll_number))

            conn.commit()
            cursor.close()
            conn.close()

            flash("✅ Signup successful! Please log in.", "success")
            return redirect(url_for('login'))
        except mysql.connector.Error as err:
            flash(f"Error: {err}", "danger")

    return render_template('Signup.html')


# ---------- LOGIN FOR ALL ROLES ----------
@app.route('/login', methods=['GET', 'POST'])
def login():
    conn = get_db_connection()
    cursor = conn.cursor()

    if request.method == 'POST':
        email = request.form['email'].lower().strip()
        password = request.form['password']
        role = detect_role(email)

        user = None

        if role == 'faculty':
           cursor.execute("SELECT * FROM faculty WHERE email=%s AND password=%s", (email, password))
           user = cursor.fetchone()
           print("DEBUG email:", email, "password:", password, "role:", role, flush=True)

           if not user:
              flash("❌ Faculty login failed: Invalid email or password.", "danger")


        elif role == 'cr':
            cursor.execute("SELECT * FROM cr WHERE email=%s AND password=%s", (email, password))
            user = cursor.fetchone()
            if not user:
                flash("❌ Class Representative login failed: Invalid email or password.", "danger")

        else:  # student
            cursor.execute("SELECT * FROM student WHERE email=%s AND password=%s", (email, password))
            user = cursor.fetchone()
            if not user :
                flash("❌ Student login failed: Invalid email or password.", "danger")

        if user:
            session['user'] = email
            session['role'] = role
            flash(f"✅ Welcome {role.title()}!", "success")

            if role == 'faculty':
                return redirect(url_for('faculty_dashboard'))
            elif role == 'cr':
                return redirect(url_for('cr_dashboard'))
            elif role == 'student':
                return redirect(url_for('student_dashboard'))

    return render_template('Login.html')


# ---------- DASHBOARD ----------

@app.route('/student_dashboard')
def student_dashboard():
    conn = get_db_connection()
    cursor = conn.cursor()

    if session.get('role') != 'student':
        return redirect(url_for('login'))
    cursor.execute("SELECT name, roll_number, branch, semester,class ,email FROM student WHERE email=%s", (session['user'],))
    student = cursor.fetchone()
    
    if not student:
        flash("User not found.", "danger")
        return redirect(url_for('login'))
    # Save roll_number into session
    session['roll_number'] = student[1]  # index 1 = roll_number
    return render_template('Student.html',student=student)

@app.route('/faculty_dashboard')
def faculty_dashboard():
    conn = get_db_connection()
    cursor = conn.cursor()

    if session.get('role') != 'faculty':
        return redirect(url_for('login'))

    cursor.execute("SELECT id, name, email, department, designation FROM faculty WHERE email=%s", (session['user'],))
    faculty = cursor.fetchone()

    cursor.execute("SELECT id, roll_no, name, class_name FROM class_students WHERE faculty_email=%s", (session['user'],))
    students = cursor.fetchall()

    # fetch unique classes handled by this faculty
    cursor.execute("SELECT DISTINCT class_name FROM class_students WHERE faculty_email=%s", (session['user'],))
    classes = [row[0] for row in cursor.fetchall()]

    return render_template('Faculty.html', faculty=faculty, students=students, classes=classes)



@app.route('/cr_dashboard')
def cr_dashboard():
    if session.get('role') != 'cr':
        return redirect(url_for('login'))
    return render_template('Cr.html')

# ---------- LOGOUT ----------
@app.route('/logout')
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for('login'))

# ---------- Uploading attendance sheet ----------

UPLOAD_FOLDER = "uploads"
ALLOWED_EXTENSIONS = {"xlsx", "xls"}
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
# New for Assignments
ASSIGNMENT_FOLDER = os.path.join(app.config["UPLOAD_FOLDER"], "assignments")
SUBMISSION_FOLDER = os.path.join(app.config["UPLOAD_FOLDER"], "submissions")
os.makedirs(ASSIGNMENT_FOLDER, exist_ok=True)
os.makedirs(SUBMISSION_FOLDER, exist_ok=True)

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route("/get_students/<class_name>")
def get_students(class_name):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT roll_no, name FROM class_students WHERE class_name=%s ORDER BY roll_no",
            (class_name,)
        )
        data = cursor.fetchall()
        return jsonify(data)
    except Exception as e:
        print("❌ Error fetching students:", e)
        return jsonify([])
    finally:
        cursor.close()
        conn.close()


@app.route('/save_timetable', methods=['POST'])
def save_timetable():
    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"error": "No JSON received"}), 400

    class_name = data.get('class_name')
    timetable_data = data.get('timetable')
    if not class_name or not timetable_data:
        return jsonify({"error": "Missing class_name or timetable"}), 400

    try:
        timetable_json = json.dumps(timetable_data)
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO timetable (class_name, timetable_json)
                    VALUES (%s, %s)
                    ON DUPLICATE KEY UPDATE timetable_json = VALUES(timetable_json)
                """, (class_name, timetable_json))
            conn.commit()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/get_timetable')
def get_timetable():
    class_name = request.args.get('class_name')
    if not class_name:
        return jsonify({"error": "Missing class_name"}), 400

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT timetable_json FROM timetable WHERE class_name=%s", (class_name,))
                row = cursor.fetchone()
        if not row:
            return jsonify({"timetable": {}})
        return jsonify({"timetable": json.loads(row[0])})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
# if session.get('role') != 'faculty':
    #     print("❌ Unauthorized: role =", session.get('role'))
    #     return jsonify({"error": "Unauthorized"}), 403

@app.route("/syllabus")
def syllabus():
    return render_template("syllabus.html")

@app.route("/student_syllabus")
def student_syllabus():
    return render_template("student_syllabus.html")

# ============================================================
# DELETE STUDENT
# ============================================================
@app.route("/delete_student/<roll_no>", methods=["POST"])
def delete_student(roll_no):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Delete attendance records first
        cursor.execute("DELETE FROM attendance WHERE roll_no=%s", (roll_no,))
        
        # Delete student record from class_students
        cursor.execute("DELETE FROM class_students WHERE roll_no=%s", (roll_no,))
        
        conn.commit()

        # If nothing deleted
        if cursor.rowcount == 0:
            return jsonify({"status": "error", "message": f"No student found with roll_no {roll_no}"}), 404

        return jsonify({"status": "success", "message": f"Deleted student {roll_no}"})
    except Exception as e:
        conn.rollback()
        print("❌ Error deleting student:", e)
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        cursor.close()
        conn.close()


# ============================================================
# RECENT CLASSES
# ============================================================
@app.route("/api/recent_classes")
def get_recent_classes():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT subject, date, 
               SUM(CASE WHEN status='present' THEN 1 ELSE 0 END) AS total_present,
               COUNT(*) AS total_students
        FROM attendance
        GROUP BY subject, date
        ORDER BY date DESC
        LIMIT 5;
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()

    result = []
    for row in rows:
        present = row[2]
        total = row[3]
        percentage = round((present / total) * 100, 2) if total else 0
        result.append({
            "subject": row[0],
            "date": row[1].strftime("%Y-%m-%d") if hasattr(row[1], "strftime") else str(row[1]),
            "present": present,
            "total": total,
            "percentage": percentage
        })
    return jsonify(result)

# ---------- FACULTY: create assignment ----------
@app.route("/create_assignment", methods=["POST"])
def create_assignment():
    if session.get("role") != "faculty":
        return redirect(url_for("login"))

    conn = get_db_connection()
    cursor = conn.cursor()

    f = request.form
    class_name = f.get("class_name")
    file = request.files.get("file")
    filename = None
    if file and file.filename:
        filename = secure_filename(file.filename)
        file.save(os.path.join(ASSIGNMENT_FOLDER, filename))

    # Duplicate check
    cursor.execute("""
        SELECT id FROM assignments
        WHERE title=%s AND subject=%s AND class_name=%s AND due_date=%s
    """, (f.get("title"), f.get("subject"), class_name, f.get("due_date")))
    existing = cursor.fetchone()
    if existing:
        flash("⚠️ Assignment already exists for this class & subject with same due date!", "warning")
        cursor.close()
        conn.close()
        return redirect("/faculty_dashboard")

    cursor.execute("""
        INSERT INTO assignments
          (title, subject, class_name, due_date, max_marks, description, file_path, faculty_email)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
    """, (
        f.get("title"),
          f.get("subject"), 
          class_name, f.get("due_date"),
        f.get("max_marks"), 
        f.get("description")if f.get("description") else None,
          filename, session["user"]
    ))
    conn.commit()
    aid = cursor.lastrowid

    # Notify students
    cursor.execute("SELECT roll_no FROM class_students WHERE class_name=%s", (class_name,))
    students = cursor.fetchall()
    for (roll_no,) in students:
        cursor.execute(
            "INSERT INTO notifications (roll_no, message) VALUES (%s,%s)",
            (roll_no, f"📢 New assignment '{f.get('title')}' for {f.get('subject')} (Due: {f.get('due_date')})")
        )
    conn.commit()

    cursor.close()
    conn.close()

    flash("✅ Assignment created & students notified!", "success")
    return redirect("/faculty_dashboard")



# ---------- FACULTY: list own assignments (JSON for table) ----------
@app.route("/api/faculty_assignments")
def api_faculty_assignments():
    if session.get("role") != "faculty":
        return jsonify([])

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, title, subject, class_name, due_date, max_marks, status, file_path
        FROM assignments
        WHERE faculty_email=%s
        ORDER BY due_date DESC, id DESC
    """, (session["user"],))
    rows = cursor.fetchall()
    cursor.close()
    conn.close()

    out = []
    for r in rows:
        aid, title, subject, cls, due, mm, st, fpath = r
        out.append({
            "id": aid,
            "title": title,
            "subject": subject,
            "class_name": cls,
            "due_date": due.strftime("%d-%m-%Y"),
            "max_marks": mm,
            "status": st,
            "file_path": fpath   # 🔹 return file_path
        })
    return jsonify(out)
@app.route("/delete_assignment/<int:assignment_id>", methods=["POST"])
def delete_assignment(assignment_id):
    if session.get("role") != "faculty":
        return jsonify({"status": "error", "message": "Unauthorized"}), 403

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Get file_path first
        cursor.execute("SELECT file_path FROM assignments WHERE id=%s", (assignment_id,))
        row = cursor.fetchone()
        if not row:
            cursor.close()
            conn.close()
            return jsonify({"status": "error", "message": "Assignment not found"}), 404

        file_path = row[0]

        # Delete from DB
        cursor.execute("DELETE FROM assignments WHERE id=%s", (assignment_id,))
        conn.commit()   # ✅ commit before closing

    except Exception as e:
        conn.rollback()  # ✅ rollback if error
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        cursor.close()
        conn.close()

    # Delete file after DB commit
    if file_path:
        full_path = os.path.join(ASSIGNMENT_FOLDER, file_path)
        if os.path.exists(full_path):
            os.remove(full_path)

    return jsonify({"status": "success", "message": "Assignment deleted"})


# ---------- STUDENT: list assignments (with my submission if any) ----------
@app.route("/api/student_assignments")
def api_student_assignments():
    if session.get("role") != "student":
        return jsonify([])

    roll_no = session.get("roll_number")


    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT a.id, a.title, a.subject, a.due_date, a.max_marks, a.description, a.file_path,
               COALESCE(s.status, 'pending') AS status,
               s.submission_date, s.marks
        FROM assignments a
        JOIN class_students cs ON a.class_name = cs.class_name
        LEFT JOIN submissions s ON a.id = s.assignment_id AND s.roll_no = cs.roll_no
        WHERE cs.roll_no = %s
        ORDER BY a.due_date ASC
    """, (roll_no,))
    
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify(rows)

# ---------- STUDENT: submit assignment ----------
@app.route("/submit_assignment", methods=["POST"])
def submit_assignment():
    conn = get_db_connection()
    cursor = conn.cursor()
    if session.get("role") != "student":
        return redirect(url_for("login"))

    assignment_id = request.form.get("assignment_id")
    my_roll = session.get("roll_no")

    file = request.files.get("file")
    filename = None
    if file and file.filename:
        filename = secure_filename(file.filename)
        file.save(os.path.join(SUBMISSION_FOLDER, filename))   # ✅ Save in submissions folder

    cursor.execute("""
        INSERT INTO submissions (assignment_id, roll_no, file_path, submission_date, status)
        VALUES (%s,%s,%s,NOW(),'submitted')
        ON DUPLICATE KEY UPDATE file_path=VALUES(file_path),
                                submission_date=NOW(),
                                status='submitted'
    """, (assignment_id, my_roll, filename))
    cursor.close()
    conn.close()

    flash("✅ Assignment submitted successfully", "success")
    return redirect("/student_dashboard")



# ---------- STUDENT: notifications ----------
# 🔹 Add this right below
@app.route("/api/notifications/clear_all", methods=["DELETE"])
def clear_all_notifications():
    
    if session.get("role") != "student":
        return jsonify({"status": "error", "message": "Unauthorized"}), 403

    my_roll = session.get("roll_no")
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM notifications WHERE roll_no=%s", (my_roll,))
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({"status": "success", "message": "All notifications cleared"})



# ---------- Download Assignment ----------

@app.route("/submissions/<path:filename>")
def download_submission(filename):
    return send_from_directory(SUBMISSION_FOLDER, filename, as_attachment=True)
# ---------- REMINDER JOB ----------
def check_due_dates():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, title, subject, due_date, class_name
        FROM assignments
        WHERE status='active' AND due_date >= CURDATE()
    """)
    rows = cursor.fetchall()

    for aid, title, subject, due, cls in rows:
        days_left = (due - date.today()).days
        if days_left in (2, 1, 0):
            cursor.execute("SELECT roll_no FROM class_students WHERE class_name=%s", (cls,))
            students = cursor.fetchall()

            for (roll_no,) in students:
                msg = f"⏰ Reminder: '{title}' ({subject}) due on {due} — {days_left} day(s) left."
                if days_left == 0:
                    msg = f"🚨 Due today: '{title}' ({subject})!"
                cursor.execute(
                    "INSERT INTO notifications (roll_no, message) VALUES (%s,%s)",
                    (roll_no, msg)
                )

    conn.commit()
    cursor.close()
    conn.close()


# -------------------- FILE PATHS --------------------
ASSIGNMENT_FOLDER = os.path.join("uploads", "assignments")
NOTE_FOLDER = os.path.join("uploads", "notes")
SUBMISSION_FOLDER = os.path.join("uploads", "submissions")
os.makedirs(ASSIGNMENT_FOLDER, exist_ok=True)
os.makedirs(NOTE_FOLDER, exist_ok=True)
os.makedirs(SUBMISSION_FOLDER, exist_ok=True)

# -------------------- HELPERS --------------------
def extract_text_from_pdf(pdf_path: str) -> str:
    """Extract text from PDF using PyMuPDF."""
    text = ""
    try:
        with fitz.open(pdf_path) as doc:
            for page in doc:
                text += page.get_text()
    except Exception:
        traceback.print_exc()
    return text
def extract_text_from_docx(docx_path: str) -> str:
    """Extract text from DOCX (Word) files."""
    text = ""
    try:
        doc = Document(docx_path)
        for para in doc.paragraphs:
            if para.text.strip():
                text += para.text.strip() + "\n"
    except Exception:
        traceback.print_exc()
    return text

def create_assignment_pdf(title, subject, class_name, due_date, max_marks, description, questions):
    """Generate clean PDF for assignment."""
    safe_title = "".join(c for c in title if c.isalnum() or c in " _-").strip().replace(" ", "_")
    filename = f"{safe_title}_{datetime.now().strftime('%Y%m%d%H%M%S')}.pdf"
    filepath = os.path.join(ASSIGNMENT_FOLDER, filename)

    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(filepath, pagesize=A4)
    story = []

    story.append(Paragraph(f"<b>{title}</b>", styles['Title']))
    story.append(Spacer(1, 12))
    story.append(Paragraph(f"<b>Subject:</b> {subject}", styles['Normal']))
    story.append(Paragraph(f"<b>Class:</b> {class_name} | <b>Max Marks:</b> {max_marks}", styles['Normal']))
    story.append(Paragraph(f"<b>Due Date:</b> {due_date}", styles['Normal']))
    story.append(Spacer(1, 12))
    if description:
        story.append(Paragraph(f"<i>{description}</i>", styles['Italic']))
        story.append(Spacer(1, 12))

    for i, q in enumerate(questions, 1):
        story.append(Paragraph(f"{i}. {q}", styles['Normal']))
        story.append(Spacer(1, 8))

    doc.build(story)
    return filename

# -------------------- GENERATE ASSIGNMENT (AI) --------------------
import re

# -------------------- GENERATE ASSIGNMENT (AI) --------------------
@app.route('/generate_assignment', methods=['POST'])
def generate_assignment():
    try:
        num_questions = request.form.get("num_questions", "5").strip()
        file = request.files.get("file")

        if not file or not file.filename:
            return jsonify({"error": "Please upload a PDF or DOCX file"}), 400

        try:
            num_questions = int(num_questions)
        except ValueError:
            num_questions = 5

        # Save uploaded file
        filename = secure_filename(file.filename)
        filepath = os.path.join(NOTE_FOLDER, filename)
        os.makedirs(NOTE_FOLDER, exist_ok=True)
        file.save(filepath)

        # Extract text
        if filename.lower().endswith(".pdf"):
            notes_text = extract_text_from_pdf(filepath)
        elif filename.lower().endswith(".docx"):
            notes_text = extract_text_from_docx(filepath)
        else:
            return jsonify({"error": "Only PDF or DOCX supported"}), 400

        if not notes_text.strip():
            return jsonify({"error": "No readable text found in file"}), 400

        # ✅ Generate questions ONLY from file content
        prompt = f"""
        You are a teacher. Generate {num_questions} clear and exam-style assignment questions 
strictly based on the following study material:

{notes_text[:3500]}

Only output the questions, one per line, no extra text.
        """

        result = model.generate_content(prompt)
        questions = [q.strip(" •-1234567890. ") for q in result.text.split("\n") if q.strip()]

        return jsonify({"questions": questions})

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# -------------------- DOWNLOAD ASSIGNMENT --------------------
@app.route("/assignments/<path:filename>")
def download_assignment(filename):
    return send_from_directory(ASSIGNMENT_FOLDER, filename, as_attachment=True)


# ---------------- TIMETABLE PAGES ----------------



# ---------------- API: FACULTY ----------------
# Get all classes this faculty handles
@app.route("/api/classes")
def api_classes():
    if session.get("role") != "faculty":
        return jsonify([])
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT class_name FROM class_students WHERE faculty_email=%s ORDER BY class_name", (session['user'],))
    classes = [r[0] for r in cur.fetchall()]
    cur.close()
    conn.close()
    return jsonify(classes)


@app.route('/upload_students', methods=['POST'])
def upload_students():
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        if 'file' not in request.files:
            flash("❌ No file uploaded", "danger")
            return redirect('/faculty_dashboard')

        file = request.files['file']
        class_name = request.form.get('class_name')

        if not file or not file.filename:
            flash("❌ No file selected", "danger")
            return redirect('/faculty_dashboard')

        if not class_name:
            flash("❌ Class name is required", "danger")
            return redirect('/faculty_dashboard')

        filepath = os.path.join(app.config["UPLOAD_FOLDER"], secure_filename(file.filename))
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        file.save(filepath)

        # Read Excel
        df = pd.read_excel(filepath)
        df.columns = df.columns.str.strip().str.lower()

        added_count = 0
        for _, row in df.iterrows():
            roll_no = str(row["roll no"]).strip() if "roll no" in df.columns else ""
            name = str(row["name"]).strip() if "name" in df.columns else ""

            if roll_no and name and roll_no.lower() != "nan" and name.lower() != "nan":
                cursor.execute("""
                    INSERT INTO class_students (roll_no, name, class_name, faculty_email)
                    VALUES (%s, %s, %s, %s)
                """, (roll_no, name, class_name, session['user']))
                added_count += 1
            else:
                print("⚠️ Skipped row:", row.to_dict())  # Debugging

        conn.commit()
        flash(f"✅ Successfully added {added_count} students to {class_name}", "success")

    except Exception as e:
        conn.rollback()
        flash(f"❌ Upload failed: {str(e)}", "danger")
        print("Upload failed:", e)
    finally:
        cursor.close()
        conn.close()

    return redirect('/faculty_dashboard')




# ============================================================
# SUBMIT ATTENDANCE
# ============================================================
@app.route("/submit_attendance", methods=["POST"])
def submit_attendance():
    conn = get_db_connection()
    cursor = conn.cursor()
    data = request.get_json(force=True)
    class_name = (data.get("class_name") or "").strip()
    subject = (data.get("subject") or "").strip()
    att_date = data.get("date")
    students = data.get("students", [])

    if not class_name or not subject:
        return jsonify({"status": "error", "message": "class_name and subject are required"}), 400

    # 🔹 Ensure date is a DATE type
    if not att_date:
        att_date = date.today()
    elif isinstance(att_date, str):
        att_date = datetime.strptime(att_date, "%Y-%m-%d").date()

    inserted = 0
    for s in students:
        roll = str(s.get("id")).strip()
        present = bool(s.get("present"))
        status = "present" if present else "absent"
        print("Saving attendance:", roll, class_name, subject, att_date, status)

        cursor.execute("""
            INSERT INTO attendance (roll_no, class_name, subject, date, status)
            VALUES (%s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE status=VALUES(status), class_name=VALUES(class_name)
        """, (roll, class_name, subject, att_date, status))
        inserted += 1

    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({"status": "success", "saved": inserted})


# ============================================================
# GET STUDENT ATTENDANCE (Weekly/Monthly Summary)
# ============================================================
@app.route("/api/student_attendance/<roll_no>", strict_slashes=False)
def api_student_attendance(roll_no):
    view = request.args.get("view", "weekly").lower()
    date_filter = ""
    if view == "weekly":
        date_filter = " AND a.date >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)"
    elif view == "monthly":
        date_filter = " AND a.date >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)"

    conn = get_db_connection()
    cursor = conn.cursor()
    query = f"""
        SELECT a.subject,
               SUM(CASE WHEN a.status='present' THEN 1 ELSE 0 END) AS attended,
               COUNT(*) AS total
        FROM attendance a
        WHERE a.roll_no=%s {date_filter}
        GROUP BY a.subject
        ORDER BY a.subject
    """
    cursor.execute(query, (roll_no,))
    rows = cursor.fetchall()
    cursor.close()
    conn.close()

    print("Fetching attendance for:", roll_no, "view:", view)

    data = []
    for sub, attended, total in rows:
        pct = round((attended / total) * 100, 2) if total else 0.0
        data.append({
            "subject": sub,
            "attended": int(attended),
            "total": int(total),
            "percentage": pct
        })
    return jsonify(data)


# ============================================================
# DOWNLOAD ATTENDANCE REPORT
# ============================================================
from io import BytesIO
from openpyxl import Workbook
from flask import send_file

@app.route("/download_report/<class_name>/<subject>")
def download_report(class_name, subject):
    conn = get_db_connection()
    cursor = conn.cursor()
    print("DEBUG download_report called:", class_name, subject, flush=True)

    cursor.execute("""
        SELECT cs.roll_no, cs.name, a.status, a.date
        FROM class_students cs
        LEFT JOIN attendance a 
            ON cs.roll_no = a.roll_no 
           AND a.subject = %s
        WHERE cs.class_name = %s
        ORDER BY cs.roll_no, a.date
    """, (subject, class_name))
    rows = cursor.fetchall()

    # Process data
    student_data = {}
    for roll_no, name, status, att_date in rows:
        if roll_no not in student_data:
            student_data[roll_no] = {
                "name": name,
                "attended": 0,
                "total": 0,
                "dates": []
            }
        if att_date:
            day_name = att_date.strftime("%a")
            date_str = att_date.strftime("%d-%m-%Y")
            student_data[roll_no]["dates"].append(f"{date_str} ({day_name}, {status})")
            student_data[roll_no]["total"] += 1
            if status == "present":
                student_data[roll_no]["attended"] += 1

    # Create Excel workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Attendance Report"

    # Add headers
    ws.append(["Class", class_name])
    ws.append(["Subject", subject])
    ws.append([])  # Empty row
    ws.append(["Roll No", "Name", "Attended", "Total Lectures", "Percentage", "Dates (Day, Status)"])

    # Add student rows
    for roll_no, info in student_data.items():
        percentage = round((info["attended"] / info["total"]) * 100, 2) if info["total"] else 0
        dates_str = "; ".join(info["dates"]) if info["dates"] else "-"
        ws.append([roll_no, info["name"], info["attended"], info["total"], f"{percentage}%", dates_str])

    # Save Excel file to memory
    output = BytesIO()
    wb.save(output)
    output.seek(0)

    # Send file for download
    filename = f"attendance_{class_name}_{subject}.xlsx"
    return send_file(output, as_attachment=True, download_name=filename, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@app.route("/get_attendance_summary")
def get_attendance_summary():
    if session.get("role") != "student":
        return jsonify({"error": "Unauthorized"}), 403

    roll = session.get("roll_number")
    if not roll:
        return jsonify({"error": "No roll number in session"}), 400

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT COUNT(*) AS total,
               SUM(status='present') AS present_count
        FROM attendance
        WHERE roll_no = %s
    """, (roll,))
    result = cur.fetchone()
    cur.close()
    conn.close()

    if not result or result[0] == 0:
        return jsonify({"total": 0, "present": 0, "percentage": 0})

    total, present = result
    present = present or 0
    percentage = round((present / total) * 100, 2)
    return jsonify({"total": total, "present": present, "percentage": percentage})

# ============================================================
# ANNOUNCEMENTS MODULE
# ============================================================

# ---------- Create Announcement (Faculty Only) ----------
@app.route("/api/announcements/create", methods=["POST"])
def create_announcement():
    if session.get("role") != "faculty":
        return jsonify({"status": "error", "message": "Unauthorized"}), 403

    data = request.get_json()
    title = data.get("title", "").strip()
    message = data.get("message", "").strip()

    if not title or not message:
        return jsonify({"status": "error", "message": "Title and message required"}), 400

    faculty_name = session.get("faculty_name")
    if not faculty_name:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM faculty WHERE email=%s", (session['user'],))
        row = cursor.fetchone()
        faculty_name = row[0] if row else "Unknown Faculty"
        cursor.close()
        conn.close()
        session['faculty_name'] = faculty_name

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO announcements (faculty_name, title, message, created_at)
        VALUES (%s, %s, %s, %s)
    """, (faculty_name, title, message, datetime.now()))
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({"status": "success", "message": "Announcement posted successfully"})


# ---------- Fetch All Announcements (Student Side) ----------
@app.route("/api/announcements", methods=["GET"])
def get_announcements():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM announcements ORDER BY created_at DESC")
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify(rows)


# -------------------- MAIN --------------------
if __name__ == "__main__":
    scheduler = BackgroundScheduler()
    scheduler.add_job(check_due_dates, "interval", hours=24, id="due_check")
    scheduler.start()
    app.run(host='0.0.0.0', port=5000, debug=True)


