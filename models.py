# app/models.py
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime
db = SQLAlchemy()

class Role(db.Model):
    __tablename__ = 'roles'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)  # Asegúrate de que este campo exista
    password = db.Column(db.String(150), nullable=False)
    role_id = db.Column(db.Integer, db.ForeignKey('roles.id'), nullable=False)
    role = db.relationship('Role')

class Course(db.Model):
    __tablename__ = 'courses'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(255))
    instructor_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    instructor = db.relationship('User', backref='courses')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relación con Module
    modules = db.relationship('Module', backref='course', lazy=True, order_by='Module.order')

class Module(db.Model):
    __tablename__ = 'modules'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    order = db.Column(db.Integer, nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id'), nullable=False)  # Corregido
    content_items = db.relationship('ContentItem', backref='module', lazy=True, cascade='all, delete-orphan', order_by='ContentItem.order')

class ContentItem(db.Model):
    __tablename__ = 'content_items'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    type = db.Column(db.String(50), nullable=False)  # 'video', 'quiz', 'text'
    content = db.Column(db.Text, nullable=False)  # URL para videos, texto para contenido, JSON para quizzes
    order = db.Column(db.Integer, nullable=False)
    module_id = db.Column(db.Integer, db.ForeignKey('modules.id'), nullable=False)  # Corregido
    responses = db.relationship('StudentResponse', backref='content_item', lazy=True)

class CourseEnrollment(db.Model):
    __tablename__ = 'course_enrollments'
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)  # Corregido
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id'), nullable=False)  # Corregido
    enrollment_date = db.Column(db.DateTime, nullable=False, default=db.func.current_timestamp())
    completed = db.Column(db.Boolean, default=False)
    progress = db.Column(db.Float, default=0.0)  # Porcentaje de progreso

class StudentResponse(db.Model):
    __tablename__ = 'student_responses'
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)  # Corregido
    content_item_id = db.Column(db.Integer, db.ForeignKey('content_items.id'), nullable=False)  # Corregido
    response = db.Column(db.Text, nullable=False)  # Respuestas del estudiante en formato JSON
    score = db.Column(db.Float, nullable=True)  # Para preguntas calificadas
    completed = db.Column(db.Boolean, default=False)
    completion_date = db.Column(db.DateTime, nullable=True)
