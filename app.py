# app/app.py
from flask import Flask, render_template, redirect, url_for, request, flash, abort
from config import Config

from flask_bcrypt import Bcrypt
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from flask_migrate import Migrate
from models import db, User, Role, Course, Module, ContentItem, CourseEnrollment, StudentResponse
from functools import wraps
from datetime import datetime
import os
import json

# Configuración de la aplicación
app = Flask(__name__, template_folder="app/templates", static_folder="app/static")
app.config.from_object(Config)

# Inicialización de extensiones
db.init_app(app)
bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
migrate = Migrate(app, db)

# Cargar el usuario en sesión
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Decorador para roles específicos
def role_required(role):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated or current_user.role.name != role:
                abort(403)
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# Crear rol y usuario administrador inicial
with app.app_context():
    try:
        db.create_all()  # Crear tablas en la base de datos si no existen

        # Crear roles si no existen
        roles = ['admin', 'instructor', 'student']
        for role_name in roles:
            role = Role.query.filter_by(name=role_name).first()
            if not role:
                new_role = Role(name=role_name)
                db.session.add(new_role)
        db.session.commit()

        # Crear usuario administrador inicial si no existe
        admin_role = Role.query.filter_by(name='admin').first()
        admin_user = User.query.filter_by(username='admin').first()

        if not admin_user and admin_role:
            password_hash = bcrypt.generate_password_hash('admin123').decode('utf-8')
            admin_user = User(username='admin', email='admin@example.com', password=password_hash, role=admin_role)
            db.session.add(admin_user)
            db.session.commit()
            print("Usuario administrador creado con éxito. Usuario: 'admin', Contraseña: 'admin123'")
    except Exception as e:
        print(f"Error al crear la base de datos o el usuario administrador: {e}")
        db.session.rollback()


# Rutas del Administrador
@app.route('/admin/dashboard')
@login_required
@role_required('admin')
def admin_dashboard():
    return render_template('admin/admin_dashboard.html')

@app.route('/admin/manage_courses', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def manage_courses():
    # Obtener todos los cursos
    courses = Course.query.all()
    return render_template('admin/manage_courses.html', courses=courses)


@app.route('/admin/register_user', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def register_user():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = bcrypt.generate_password_hash(request.form['password']).decode('utf-8')
        role_name = request.form['role']

        # Buscar el rol
        role = Role.query.filter_by(name=role_name).first()

        if not role:
            flash('Rol no encontrado', 'danger')
            return redirect(url_for('register_user'))

        # Crear el usuario
        new_user = User(username=username, email=email, password=password, role=role)
        db.session.add(new_user)
        db.session.commit()
        flash('Usuario creado exitosamente.', 'success')
        return redirect(url_for('admin_dashboard'))

    roles = Role.query.all()
    return render_template('admin/register_user.html', roles=roles)

@app.route('/admin/view_users')
@login_required
@role_required('admin')
def view_users():
    # Verifica que el usuario sea administrador
    if current_user.role.name != 'admin':
        abort(403)

    # Obtener usuarios por rol
    students = User.query.join(Role).filter(Role.name == 'student').all()
    instructors = User.query.join(Role).filter(Role.name == 'instructor').all()
    admins = User.query.join(Role).filter(Role.name == 'admin').all()

    # Pasar los usuarios a la plantilla
    return render_template('admin/view_users.html', students=students, instructors=instructors, admins=admins)


@app.route('/admin/view_course/<int:course_id>', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def view_course(course_id):
    course = Course.query.get_or_404(course_id)
    
    # Si el método es POST, se ejecuta la eliminación
    if request.method == 'POST':
        db.session.delete(course)
        db.session.commit()
        flash('Curso eliminado exitosamente.', 'success')
        return redirect(url_for('manage_courses'))
    
    # Para método GET, solo se muestra la vista del curso
    return render_template('admin/view_course.html', course=course)

# Rutas del Instructor
@app.route('/instructor/dashboard')
@login_required
@role_required('instructor')
def instructor_dashboard():
    courses = Course.query.filter_by(instructor_id=current_user.id).all()
    return render_template('instructor/instructor_dashboard.html', courses=courses)

@app.route('/instructor/create_course', methods=['GET', 'POST'])
@login_required
@role_required('instructor')
def create_course():
    if request.method == 'POST':
        title = request.form.get('title')
        description = request.form.get('description')
        new_course = Course(
            title=title,
            description=description,
            instructor_id=current_user.id
        )
        db.session.add(new_course)
        db.session.commit()
        flash('Curso creado exitosamente.', 'success')
        return redirect(url_for('instructor_dashboard'))
    return render_template('instructor/create_course.html')

@app.route('/instructor/edit_course/<int:course_id>', methods=['GET', 'POST'])
@login_required
@role_required('instructor')
def edit_course(course_id):
    course = Course.query.get_or_404(course_id)
    if course.instructor_id != current_user.id:
        abort(403)
    if request.method == 'POST':
        course.title = request.form.get('title')
        course.description = request.form.get('description')
        db.session.commit()
        flash('Curso actualizado exitosamente.', 'success')
        return redirect(url_for('instructor_dashboard'))
    return render_template('instructor/edit_course.html', course=course)

@app.route('/instructor/manage_course/<int:course_id>', methods=['GET', 'POST'])
@login_required
@role_required('instructor')
def manage_course(course_id):
    course = Course.query.get_or_404(course_id)
    if course.instructor_id != current_user.id:
        abort(403)
    if request.method == 'POST':
        db.session.delete(course)
        db.session.commit()
        flash('Curso eliminado exitosamente.', 'success')
        return redirect(url_for('instructor_dashboard'))
    return render_template('instructor/manage_course.html', course=course)

@app.route('/instructor/create_module/<int:course_id>', methods=['GET', 'POST'])
@login_required
@role_required('instructor')
def create_module(course_id):
    course = Course.query.get_or_404(course_id)
    
    if request.method == 'POST':
        title = request.form.get('title')
        new_module = Module(title=title, order=len(course.modules) + 1, course_id=course_id)
        db.session.add(new_module)
        db.session.commit()
        flash('Módulo creado exitosamente.', 'success')
        return redirect(url_for('manage_course', course_id=course_id))
    
    return render_template('instructor/create_module.html', course=course)

@app.route('/instructor/delete_module/<int:course_id>/<int:module_id>', methods=['POST'])
@login_required
@role_required('instructor')
def delete_module(course_id, module_id):
    course = Course.query.get_or_404(course_id)
    module = Module.query.get_or_404(module_id)
    
    if module.course_id != course_id:
        flash('El módulo no pertenece a este curso.', 'error')
        return redirect(url_for('manage_course', course_id=course_id))

    db.session.delete(module)
    db.session.commit()
    
    # Actualizar el orden de los módulos restantes
    remaining_modules = Module.query.filter_by(course_id=course_id).order_by(Module.order).all()
    for index, remaining_module in enumerate(remaining_modules, start=1):
        remaining_module.order = index
    db.session.commit()

    flash('Módulo eliminado exitosamente.', 'success')
    return redirect(url_for('manage_course', course_id=course_id))

@app.route('/instructor/create_content/<int:course_id>/<int:module_id>', methods=['GET', 'POST'])
@login_required
@role_required('instructor')
def create_content(course_id, module_id):
    module = Module.query.get_or_404(module_id)
    
    if request.method == 'POST':
        title = request.form.get('title')
        content_type = request.form.get('type')
        
        # Lógica para manejar contenido según tipo
        if content_type == 'quiz':
            content = request.form.get('quiz_data')  # JSON con preguntas del quiz
        elif content_type == 'video':
            content = request.form.get('video_url')  # URL del video
        elif content_type == 'text':
            uploaded_file = request.files.get('text_file')
            if uploaded_file:
                # Guardar el archivo (ejemplo: PDF o texto)
                file_path = os.path.join('uploads', uploaded_file.filename)
                uploaded_file.save(file_path)
                content = file_path
            else:
                content = request.form.get('text_data')  # Texto manual ingresado
            
        new_content = ContentItem(
            title=title,
            type=content_type,
            content=content,
            order=len(module.content_items) + 1,
            module_id=module_id
        )
        db.session.add(new_content)
        db.session.commit()
        flash('Contenido creado exitosamente.', 'success')
        return redirect(url_for('manage_course', course_id=course_id))
    
    return render_template('instructor/create_content.html', course_id=course_id, module_id=module_id)


@app.route('/instructor/edit_content/<int:content_id>', methods=['GET', 'POST'])
@login_required
@role_required('instructor')
def edit_content(content_id):
    content_item = ContentItem.query.get_or_404(content_id)
    course_id = content_item.module.course_id
    
    if request.method == 'POST':
        content_item.title = request.form.get('title')
        content_item.type = request.form.get('type')
        content_item.content = request.form.get('content')
        db.session.commit()
        flash('Contenido actualizado exitosamente.', 'success')
        return redirect(url_for('manage_course', course_id=course_id))
    
    return render_template('instructor/edit_content.html', 
                           content_item=content_item)

@app.route('/instructor/delete_content', methods=['POST'])
@login_required
@role_required('instructor')
def delete_content():
    content_id = request.form.get('content_id')
    content_item = ContentItem.query.get_or_404(content_id)
    course_id = content_item.module.course_id
    db.session.delete(content_item)
    db.session.commit()
    flash('Contenido eliminado exitosamente.', 'success')
    return redirect(url_for('manage_course', course_id=course_id))

# Rutas del Estudiante
@app.route('/student/dashboard')
@login_required
@role_required('student')
def student_dashboard():
    courses = Course.query.all()
    return render_template('student/student_dashboard.html', courses=courses)

@app.route('/student/view_courses')
@login_required
@role_required('student')
def view_courses():
    courses = Course.query.all()
    # Obtener todas las inscripciones del estudiante actual
    enrollments = {
        enrollment.course_id: enrollment 
        for enrollment in CourseEnrollment.query.filter_by(student_id=current_user.id).all()
    }
    return render_template('student/view_courses.html', 
                         courses=courses, 
                         enrollments=enrollments)

@app.route('/student/enroll/<int:course_id>', methods=['POST'])
@login_required
@role_required('student')
def enroll_course(course_id):
    course = Course.query.get_or_404(course_id)
    existing_enrollment = CourseEnrollment.query.filter_by(
        student_id=current_user.id,
        course_id=course_id
    ).first()
    
    if existing_enrollment:
        flash('Ya estás inscrito en este curso.', 'info')
    else:
        enrollment = CourseEnrollment(student_id=current_user.id, course_id=course_id)
        db.session.add(enrollment)
        db.session.commit()
        flash('Te has inscrito exitosamente en el curso.', 'success')
    
    return redirect(url_for('view_course_content', course_id=course_id))

@app.route('/student/course/<int:course_id>')
@login_required
@role_required('student')
def view_course_content(course_id):
    course = Course.query.get_or_404(course_id)
    enrollment = CourseEnrollment.query.filter_by(
        student_id=current_user.id,
        course_id=course_id
    ).first()
    
    if not enrollment:
        flash('Debes inscribirte primero en este curso.', 'warning')
        return redirect(url_for('view_courses'))
    
    return render_template('student/course_content.html', 
                         course=course, 
                         enrollment=enrollment)

@app.route('/student/content/<int:content_id>', methods=['GET', 'POST'])
@login_required
@role_required('student')
def view_content(content_id):
    content_item = ContentItem.query.get_or_404(content_id)
    
    if request.method == 'POST' and content_item.type == 'quiz':
        response_data = request.form.to_dict()
        
        # Crear o actualizar la respuesta del estudiante
        student_response = StudentResponse.query.filter_by(
            student_id=current_user.id,
            content_item_id=content_id
        ).first()
        
        if not student_response:
            student_response = StudentResponse(
                student_id=current_user.id,
                content_item_id=content_id,
                response=json.dumps(response_data),
                completed=True,
                completion_date=datetime.utcnow()
            )
            db.session.add(student_response)
        else:
            student_response.response = json.dumps(response_data)
            student_response.completion_date = datetime.utcnow()
        
        db.session.commit()
        update_course_progress(current_user.id, content_item.module.course_id)
        flash('Respuestas guardadas exitosamente.', 'success')
        
    return render_template('student/content_view.html', 
                         content_item=content_item,
                         student_response=StudentResponse.query.filter_by(
                             student_id=current_user.id,
                             content_item_id=content_id
                         ).first())

def update_course_progress(student_id, course_id):
    enrollment = CourseEnrollment.query.filter_by(
        student_id=student_id,
        course_id=course_id
    ).first()
    
    if enrollment:
        course = Course.query.get(course_id)
        total_items = sum(len(module.content_items) for module in course.modules)
        completed_items = StudentResponse.query.join(ContentItem)\
            .join(Module)\
            .filter(
                Module.course_id == course_id,
                StudentResponse.student_id == student_id,
                StudentResponse.completed == True
            ).count()
        
        enrollment.progress = (completed_items / total_items * 100) if total_items > 0 else 0
        enrollment.completed = enrollment.progress >= 100
        db.session.commit()

# Ruta de inicio de sesión
@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if username and password:
            user = User.query.filter_by(username=username).first()
            if user and bcrypt.check_password_hash(user.password, password):
                login_user(user)
                flash('Inicio de sesión exitoso', 'success')
                if user.role.name == 'admin':
                    return redirect(url_for('admin_dashboard'))
                elif user.role.name == 'instructor':
                    return redirect(url_for('instructor_dashboard'))
                elif user.role.name == 'student':
                    return redirect(url_for('student_dashboard'))
                else:
                    flash('Rol desconocido. Por favor, contacta al administrador.', 'danger')
                    return redirect(url_for('login'))
            else:
                flash('Credenciales incorrectas', 'danger')
        else:
            flash('Por favor, completa todos los campos.', 'warning')
    return render_template('login.html')

# Ruta de cierre de sesión
@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Sesión cerrada', 'success')
    return redirect(url_for('login'))

#Perfil de los usuarios
@app.route('/profile')
@login_required
def profile():
    user = User.query.get(current_user.id)
    return render_template('profile.html', user=user)

@app.route('/profile_students')
@login_required
def profile_students():
    return render_template('profile.html')

# Comando para actualizar la contraseña de un usuario 
@app.cli.command("update-password")
def update_password():
    """Actualizar la contraseña de un usuario específico"""
    username = input("Ingrese el nombre de usuario: ")
    user = User.query.filter_by(username=username).first()
    if user:
        new_password = input("Ingrese la nueva contraseña: ")
        hashed_password = bcrypt.generate_password_hash(new_password).decode('utf-8')
        user.password = hashed_password
        db.session.commit()
        print(f"Contraseña actualizada exitosamente para el usuario {username}.")
    else:
        print("Usuario no encontrado.")

@app.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    if request.method == 'POST':
        current_password = request.form['current_password']
        new_password = request.form['new_password']
        confirm_password = request.form['confirm_password']

        if not current_user.check_password(current_password):
            flash('La contraseña actual es incorrecta.', 'error')
            return redirect('/change-password')

        if new_password != confirm_password:
            flash('Las contraseñas no coinciden.', 'error')
            return redirect('/change-password')

        current_user.set_password(new_password)
        db.session.commit()
        flash('Contraseña cambiada exitosamente.', 'success')
        return redirect('/profile')
    return render_template('change_password.html')

if __name__ == '__main__':
    app.run(debug=True)
