from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class Assignment(db.Model):
    __tablename__ = "ai_assignments"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100))
    subject = db.Column(db.String(50))
    class_name = db.Column(db.String(50))
    due_date = db.Column(db.String(20))
    threshold = db.Column(db.Float, default=0.6)
    created_by = db.Column(db.String(50))
    file_path = db.Column(db.String(200))
    published = db.Column(db.Boolean, default=True)  # ✅ This exists in model


class Submission(db.Model):
    __tablename__ = "ai_submissions"
    id = db.Column(db.Integer, primary_key=True)
    assignment_id = db.Column(db.Integer, db.ForeignKey('ai_assignments.id'))
    roll_no = db.Column(db.String(20))
    file_path = db.Column(db.String(200))
    ai_score = db.Column(db.Float)
    status = db.Column(db.String(20), default='pending')
    verified = db.Column(db.Boolean, default=False)
