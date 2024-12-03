from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime
import json
from sqlalchemy.types import JSON

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
    courses = db.relationship('Course', backref='instructor')  # Cursos que enseña
    enrollments = db.relationship('CourseEnrollment', backref='student')  # Cursos en los que está inscrito
    responses = db.relationship('StudentResponse', backref='student')  # Respuestas de quizzes

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
    content_items = db.relationship(
    'ContentItem',
    back_populates='module',
    lazy=True,
    cascade='all, delete-orphan'
    )


    def __repr__(self):
        return f'<Module {self.title}>'

    def get_content_items_sorted(self):
        return sorted(self.content_items, key=lambda x: x.order)
    # En el modelo Module
    def get_next_content_order(self):
        return max((content.order for content in self.content_items), default=0) + 1


class ContentItem(db.Model):
    __tablename__ = 'content_items'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    type = db.Column(db.String(50), nullable=False)  # "text", "video", "file", "quiz"
    content = db.Column(db.Text, nullable=True)  # Contenido (nombre de archivo, texto o URL)
    file_path = db.Column(db.String(255), nullable=True)  # Ruta de archivo (si aplica)
    order = db.Column(db.Integer, nullable=False)
    module_id = db.Column(db.Integer, db.ForeignKey('modules.id'), nullable=False)

    # Relación con preguntas del quiz
    questions = db.relationship(
        'QuizQuestion',
        backref='content_item',
        cascade='all, delete-orphan',
        lazy=True
    )


    module = db.relationship('Module', back_populates='content_items')

    def __repr__(self):
        return f'<ContentItem {self.title}>'


class QuizQuestion(db.Model):
    __tablename__ = 'quiz_questions'
    id = db.Column(db.Integer, primary_key=True)
    question_text = db.Column(db.Text, nullable=False)
    content_item_id = db.Column(db.Integer, db.ForeignKey('content_items.id'), nullable=False)
    question_type = db.Column(db.String(50), default="multiple_choice")  # "multiple_choice", "open_ended"
    correct_answer = db.Column(db.Text, nullable=True)
    options = db.Column(db.Text, nullable=True)  # Options stored as JSON

    def __repr__(self):
        return f'<QuizQuestion {self.question_text[:50]}>'

    def to_dict(self):
        """Convert the question to a dictionary for frontend display."""
        return {
            "id": self.id,
            "question_text": self.question_text,
            "question_type": self.question_type,
            "correct_answer": self.correct_answer,
            "options": self.get_options()
        }

    def validate_options(self):
        """Validate that options are well-formed for multiple-choice questions."""
        if self.question_type == "multiple_choice":
            if not self.options:
                raise ValueError("Las opciones son requeridas para preguntas de opción múltiple.")
            try:
                options_list = json.loads(self.options)
                if not isinstance(options_list, list) or not options_list:
                    raise ValueError("Las opciones deben ser una lista no vacía.")
            except json.JSONDecodeError:
                raise ValueError("Las opciones deben estar en un formato JSON válido.")

    def get_options(self):
        """Return the options as a list."""
        try:
            return json.loads(self.options) if self.options else []
        except json.JSONDecodeError as e:
            raise ValueError(f"Error al procesar las opciones: {e}")

    def is_answer_correct(self, user_answer):
        """Check if the provided user answer is correct."""
        correct = str(self.correct_answer).strip().lower()
        user = str(user_answer).strip().lower()
        return correct == user


    

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
        """Actualizar el progreso del curso basado en los contenidos completados."""
        total_content = sum(len(module.content_items) for module in self.course.modules)
        completed_content = StudentResponse.query.filter_by(
            student_id=self.student_id, completed=True
        ).join(ContentItem).filter(ContentItem.module_id.in_(
            [module.id for module in self.course.modules]
        )).count()

        self.progress = (completed_content / total_content) * 100 if total_content > 0 else 0
        self.completed = self.progress == 100
        db.session.commit()


# Modelo de Respuestas de Estudiantes
class StudentResponse(db.Model):
    __tablename__ = 'student_responses'
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    content_item_id = db.Column(db.Integer, db.ForeignKey('content_items.id'), nullable=False)
    response = db.Column(db.Text, nullable=True)  # Respuesta del estudiante (si es un quiz)
    score = db.Column(db.Float, nullable=True)  # Puntaje (si es un quiz)
    completed = db.Column(db.Boolean, default=False)  # Estado de finalización
    completion_date = db.Column(db.DateTime, nullable=True)

    def mark_as_completed(self):
        """Marca este contenido como completado por el estudiante."""
        self.completed = True
        self.completion_date = datetime.utcnow()
        db.session.commit()

        # Actualizar el progreso del curso
        enrollment = CourseEnrollment.query.filter_by(
            student_id=self.student_id, course_id=self.content_item.module.course.id
        ).first()
        if enrollment:
            enrollment.update_progress()

