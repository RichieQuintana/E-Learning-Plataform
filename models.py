from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime
import json

db = SQLAlchemy()

# Modelo de Roles (Admin, Instructor, Estudiante)
class Role(db.Model):
    __tablename__ = 'roles'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)

    def __repr__(self):
        return f'<Role {self.name}>'

# Modelo de Usuario
class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)
    role_id = db.Column(db.Integer, db.ForeignKey('roles.id'), nullable=False)
    role = db.relationship('Role')
    courses = db.relationship('Course', backref='instructor', cascade='all, delete-orphan')  # Cursos que enseña
    enrollments = db.relationship('CourseEnrollment', backref='student', cascade='all, delete-orphan')  # Inscripciones
    responses = db.relationship('StudentResponse', backref='student', cascade='all, delete-orphan')  # Respuestas

    def __repr__(self):
        return f'<User {self.username}>'

# Modelo de Curso
class Course(db.Model):
    __tablename__ = 'courses'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.String(500), nullable=False)
    instructor_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    modules = db.relationship('Module', back_populates='course', lazy=True, cascade='all, delete-orphan')
    enrollments = db.relationship('CourseEnrollment', backref='course', lazy=True)

    def __repr__(self):
        return f'<Course {self.name}>'

    def get_modules_sorted(self):
        return sorted(self.modules, key=lambda x: x.order)

    def get_total_content(self):
        """Retorna el número total de ítems de contenido en el curso."""
        total_content = 0
        for module in self.modules:
            total_content += len(module.content_items)
        return total_content


# Modelo de Módulo
class Module(db.Model):
    __tablename__ = 'modules'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.String(500), nullable=False)
    order = db.Column(db.Integer, nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id'), nullable=False)
    content_items = db.relationship('ContentItem', back_populates='module', lazy=True, cascade='all, delete-orphan')
    course = db.relationship('Course', back_populates='modules')

    def __repr__(self):
        return f'<Module {self.title}>'

    def get_content_items_sorted(self):
        """Devuelve los contenidos ordenados por el campo `order`."""
        return sorted(self.content_items, key=lambda x: x.order)

    def get_next_content_order(self):
        """Calcula el próximo número de orden para un nuevo contenido."""
        return max((content.order for content in self.content_items), default=0) + 1

# Modelo de Contenido
class ContentItem(db.Model):
    __tablename__ = 'content_items'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    type = db.Column(db.String(50), nullable=False)  # "text", "video", "file", "quiz"
    content = db.Column(db.Text, nullable=True)
    file_path = db.Column(db.String(255), nullable=True)
    order = db.Column(db.Integer, nullable=False)
    module_id = db.Column(db.Integer, db.ForeignKey('modules.id'), nullable=False)
    questions = db.relationship('QuizQuestion', backref='content_item', cascade='all, delete-orphan', lazy=True)
    module = db.relationship('Module', back_populates='content_items')

    def __repr__(self):
        return f'<ContentItem {self.title}>'

# Modelo de Preguntas del Quiz
class QuizQuestion(db.Model):
    __tablename__ = 'quiz_questions'
    id = db.Column(db.Integer, primary_key=True)
    question_text = db.Column(db.Text, nullable=False)
    content_item_id = db.Column(db.Integer, db.ForeignKey('content_items.id'), nullable=False)
    question_type = db.Column(db.String(50), default="multiple_choice")
    correct_answer = db.Column(db.Text, nullable=True)
    options = db.Column(db.Text, nullable=True)

    def __repr__(self):
        return f'<QuizQuestion {self.question_text[:50]}>'

    def to_dict(self):
        return {
            "id": self.id,
            "question_text": self.question_text,
            "question_type": self.question_type,
            "correct_answer": self.correct_answer,
            "options": self.get_options()
        }

    def get_options(self):
        try:
            return json.loads(self.options) if self.options else []
        except json.JSONDecodeError as e:
            raise ValueError(f"Error al procesar las opciones: {e}")

    def is_answer_correct(self, user_answer):
        return str(self.correct_answer).strip().lower() == str(user_answer).strip().lower()

# Modelo de Inscripción a Cursos
class CourseEnrollment(db.Model):
    __tablename__ = 'course_enrollments'
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id'), nullable=False)
    enrollment_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    completed = db.Column(db.Boolean, default=False)
    progress = db.Column(db.Float, default=0.0)

    def update_progress(self):
        total_content = sum(len(module.content_items) for module in self.course.modules)
        completed_content = StudentResponse.query.filter_by(student_id=self.student_id, completed=True).count()
        self.progress = (completed_content / total_content) * 100 if total_content > 0 else 0
        self.completed = self.progress == 100
        db.session.commit()

# Modelo de Respuestas de Estudiantes
class StudentResponse(db.Model):
    __tablename__ = 'student_responses'
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    content_item_id = db.Column(db.Integer, db.ForeignKey('content_items.id', ondelete="CASCADE"), nullable=False)
    response = db.Column(db.Text, nullable=True)
    score = db.Column(db.Float, nullable=True)
    completed = db.Column(db.Boolean, default=False)
    completion_date = db.Column(db.DateTime, nullable=True)
    content_item = db.relationship('ContentItem', backref='responses')

    def mark_as_completed(self):
        self.completed = True
        self.completion_date = datetime.utcnow()
        db.session.commit()
        enrollment = CourseEnrollment.query.filter_by(student_id=self.student_id, course_id=self.content_item.module.course.id).first()
        if enrollment:
            enrollment.update_progress()
