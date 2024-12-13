from flask import Flask, render_template, redirect, url_for, request, flash, abort, send_from_directory
from flask_bcrypt import Bcrypt
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect
from werkzeug.utils import secure_filename
from models import db, User, Role, Course, Module, ContentItem, CourseEnrollment, StudentResponse, QuizQuestion
from functools import wraps
from datetime import datetime, timedelta
import os
from forms import DeleteUserForm
from urllib.parse import urlparse, parse_qs
import json


# Application Configuration
app = Flask(__name__, template_folder="app/templates", static_folder="app/static")
app.config.from_object('config.Config')

# Static Upload Folder
UPLOAD_FOLDER = os.path.join(app.root_path, 'app/static/uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

def allowed_file(filename):
    ALLOWED_EXTENSIONS = {'pdf', 'docx', 'txt', 'mp4'}
    VALID_CONTENT_TYPES = ['text', 'video', 'file', 'quiz']
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Ruta para servir los archivos subidos
@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# Initialize Extensions
db.init_app(app)
bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
migrate = Migrate(app, db)
csrf = CSRFProtect(app)
csrf.init_app(app)

# Registrar `enumerate` en el entorno Jinja
app.jinja_env.globals.update(enumerate=enumerate)

# User Loader
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Role-based Access Control Decorator
def role_required(role):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated or current_user.role.name != role:
                abort(403)
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# Database Initialization
with app.app_context():
    try:
        db.create_all()  # Create tables if they don't exist

        # Create default roles
        roles = ['admin', 'instructor', 'student']
        for role_name in roles:
            role = Role.query.filter_by(name=role_name).first()
            if not role:
                new_role = Role(name=role_name)
                db.session.add(new_role)
        db.session.commit()

        # Create default admin user
        admin_role = Role.query.filter_by(name='admin').first()
        admin_user = User.query.filter_by(username='admin').first()

        if not admin_user and admin_role:
            password_hash = bcrypt.generate_password_hash('admin123').decode('utf-8')
            admin_user = User(username='admin', email='admin@example.com', password=password_hash, role=admin_role)
            db.session.add(admin_user)
            db.session.commit()
            print("Admin user created successfully. Username: 'admin', Password: 'admin123'")
    except Exception as e:
        print(f"Error creating database or admin user: {e}")
        db.session.rollback()

# Routes for Static Files (Fixing BuildError for Static)
@app.route('/static/<path:filename>')
def serve_static(filename):
    return redirect(url_for('static', filename=filename))

# Login Route
@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        if user and bcrypt.check_password_hash(user.password, password):
            login_user(user)
            flash('Login successful.', 'success')
            if user.role.name == 'admin':
                return redirect(url_for('admin_dashboard'))
            elif user.role.name == 'instructor':
                return redirect(url_for('instructor_dashboard'))
            elif user.role.name == 'student':
                return redirect(url_for('student_dashboard'))
        flash('Invalid credentials.', 'danger')
    return render_template('login.html')

# Logout Route
@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out successfully.', 'success')
    return redirect(url_for('login'))

# -------------------- Rutas de Administrador -------------------- #

@app.route('/admin/dashboard')
@login_required
@role_required('admin')
def admin_dashboard():
    total_users = User.query.count()
    total_courses = Course.query.count()
    recent_users = User.query.order_by(User.id.desc()).limit(5).all()
    recent_courses = Course.query.order_by(Course.id.desc()).limit(5).all()
    return render_template('admin/admin_dashboard.html',
        total_users=total_users,
        total_courses=total_courses,         recent_users=recent_users,
        recent_courses=recent_courses)

@app.route('/admin/register_user', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def register_user():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = bcrypt.generate_password_hash(request.form['password']).decode('utf-8')
        role_name = request.form['role']
        role = Role.query.filter_by(name=role_name).first()
        if not role:
            flash('Rol no encontrado.', 'danger')
            return redirect(url_for('register_user'))
        new_user = User(username=username, email=email, password=password, role=role)
        db.session.add(new_user)
        db.session.commit()
        flash('Usuario creado exitosamente.', 'success')
        return redirect(url_for('admin_dashboard'))
    roles = Role.query.all()
    return render_template('admin/register_user.html', roles=roles)

@app.route('/admin/view_users', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def view_users():
    users = User.query.all()
    form = DeleteUserForm()  # Formulario con CSRF
    return render_template('admin/view_users.html', users=users, form=form)

@app.route('/admin/manage_courses', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def manage_courses():
    courses = Course.query.all()  # Obtén todos los cursos
    return render_template('admin/manage_courses.html', courses=courses)

@app.route('/admin/course/<int:course_id>', methods=['GET'])
@login_required
@role_required('admin')  # Si usas decoradores de roles
def view_course(course_id):
    course = Course.query.get_or_404(course_id)
    return render_template('admin/view_course.html', course=course)


@app.route('/admin/user/delete/<int:user_id>', methods=['POST'])
@login_required
@role_required('admin')
def delete_user(user_id):
    form = DeleteUserForm()
    if form.validate_on_submit():  # Verifica el token CSRF
        user = User.query.get_or_404(user_id)
        if user.username == 'admin':
            flash('No puedes eliminar al usuario administrador principal.', 'danger')
            return redirect(url_for('view_users'))
        db.session.delete(user)
        db.session.commit()
        flash('Usuario eliminado exitosamente.', 'success')
    else:
        flash('Token CSRF inválido o formulario no válido.', 'danger')
    return redirect(url_for('view_users'))

# -------------------- Rutas de Instructor -------------------- #

# Panel principal del Instructor
@app.route('/instructor/dashboard', methods=['GET'])
@login_required
@role_required('instructor')
def instructor_dashboard():
    """Dashboard del instructor con comparación de cursos"""
    # Obtiene todos los cursos del instructor
    courses = Course.query.filter_by(instructor_id=current_user.id).all()

    # Lista para almacenar métricas de los cursos
    course_metrics = []

    for course in courses:
        # Total de estudiantes inscritos
        total_students = len(course.enrollments)

        # Variables para cálculo de métricas
        total_scores = 0  # Suma de calificaciones
        total_responses = 0  # Total de respuestas evaluadas
        students_completed_course = 0  # Estudiantes que completaron todos los quizzes

        # Total de quizzes en el curso
        total_quizzes = sum(
            1 for module in course.modules for content in module.content_items if content.type == 'quiz'
        )

        # Verificar progreso de cada estudiante
        for enrollment in course.enrollments:
            # Número de quizzes completados por el estudiante
            completed_quizzes = db.session.query(
                ContentItem.id
            ).join(StudentResponse).filter(
                StudentResponse.student_id == enrollment.student_id,
                StudentResponse.completed == True,
                ContentItem.module_id.in_([module.id for module in course.modules])
            ).group_by(ContentItem.id).count()
            # Aseguramos que no cuente duplicados

            # Si el estudiante completó todos los quizzes del curso, cuenta como completado
            if total_quizzes > 0 and completed_quizzes == total_quizzes:
                students_completed_course += 1

            # Calcular promedio de calificaciones
            for response in enrollment.student.responses:
                if (
                    response.content_item
                    and response.content_item.module
                    and response.content_item.module.course_id == course.id
                ):
                    if response.score is not None:
                        total_scores += response.score
                        total_responses += 1

        # Cálculo del promedio de calificaciones
        average_score = (
            round(total_scores / total_responses, 2) if total_responses > 0 else 0
        )

        # Cálculo del porcentaje de finalización
        completion_rate = (
            round((students_completed_course / total_students) * 100, 2)
            if total_students > 0 else 0
        )

        # Agregar métricas a la lista
        course_metrics.append({
            'course': course,
            'total_students': total_students,
            'average_score': average_score,
            'completion_rate': completion_rate
        })

    # Ordenar cursos por número de estudiantes, promedio de notas y porcentaje de finalización
    sorted_courses = sorted(
        course_metrics,
        key=lambda x: (
            0.4 * x['total_students'] +
            0.4 * x['average_score'] +
            0.2 * x['completion_rate']
        ),
        reverse=True
    )

    # Renderizar el dashboard del instructor
    return render_template(
        'instructor/instructor_dashboard.html',
        courses=courses,
        course_metrics=sorted_courses
    )

@app.route('/instructor/courses', methods=['GET'])
@login_required
@role_required('instructor')
def instructor_courses():
    """Lista de todos los cursos creados por el instructor."""
    courses = Course.query.filter_by(instructor_id=current_user.id).all()
    return render_template('instructor/courses.html', courses=courses)

# Crear un nuevo curso
@app.route('/instructor/course/new', methods=['GET', 'POST'])
@login_required
@role_required('instructor')
def new_course():
    """Crear un nuevo curso."""
    if request.method == 'POST':
        title = request.form.get('title')
        description = request.form.get('description')

        if not title or not description:
            flash('Por favor, completa todos los campos.', 'danger')
            return redirect(url_for('new_course'))

        # Crear el curso asociado al instructor actual
        course = Course(name=title, description=description, instructor_id=current_user.id)
        db.session.add(course)
        db.session.commit()

        flash('Curso creado exitosamente.', 'success')
        return redirect(url_for('instructor_dashboard'))

    return render_template('instructor/new_course.html')

# Editar un curso existente
@app.route('/instructor/course/edit/<int:course_id>', methods=['GET', 'POST'])
@login_required
@role_required('instructor')
def edit_course(course_id):
    """Editar un curso existente."""
    course = Course.query.get_or_404(course_id)
    if course.instructor_id != current_user.id:
        flash('No tienes permiso para editar este curso.', 'danger')
        return redirect(url_for('instructor_dashboard'))

    if request.method == 'POST':
        course.name = request.form.get('title')
        course.description = request.form.get('description')
        db.session.commit()
        flash('Curso actualizado exitosamente.', 'success')
        return redirect(url_for('instructor_dashboard'))

    return render_template('instructor/edit_course.html', course=course)


# Eliminar un curso
# Eliminar un curso
@app.route('/instructor/course/delete/<int:course_id>', methods=['POST'])
@login_required
@role_required('instructor')
def delete_course(course_id):
    """Eliminar un curso junto con sus módulos y respuestas asociadas."""
    course = Course.query.get_or_404(course_id)
    if course.instructor_id != current_user.id:
        flash('No tienes permiso para eliminar este curso.', 'danger')
        return redirect(url_for('instructor_dashboard'))

    try:
        # Eliminar respuestas de estudiantes asociadas a los contenidos del curso
        for module in course.modules:
            for content_item in module.content_items:
                StudentResponse.query.filter_by(content_item_id=content_item.id).delete()

        # Eliminar el curso (esto elimina automáticamente módulos y contenidos debido a la cascada)
        db.session.delete(course)
        db.session.commit()
        flash('Curso eliminado exitosamente.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al eliminar el curso: {e}', 'danger')

    return redirect(url_for('instructor_dashboard'))


# Ver detalles de un curso
@app.route('/instructor/course/<int:course_id>', methods=['GET'])
@login_required
@role_required('instructor')
def course_details(course_id):
    """Ver los detalles de un curso."""
    course = Course.query.get_or_404(course_id)  # Obtén el curso o lanza un 404

    # Verifica si el curso pertenece al instructor actual
    if course.instructor_id != current_user.id:
        flash('No tienes permiso para acceder a este curso.', 'danger')
        return redirect(url_for('instructor_courses'))

    # Recupera los módulos relacionados
    modules = course.get_modules_sorted()

    return render_template(
        'instructor/course_details.html',
        course=course,
        modules=modules
    )

@app.route('/instructor/module/<int:module_id>', methods=['GET'])
@login_required
@role_required('instructor')
def module_details(module_id):
    """Ver los detalles de un módulo específico."""
    module = Module.query.get_or_404(module_id)
    if module.course.instructor_id != current_user.id:
        flash('No tienes permiso para acceder a este módulo.', 'danger')
        return redirect(url_for('instructor_dashboard'))

    # Los contenidos del módulo se mostrarán en esta vista.
    return render_template('instructor/module_details.html', module=module)


# Crear un nuevo módulo en un curso
@app.route('/instructor/course/<int:course_id>/module/new', methods=['GET', 'POST'])
@login_required
@role_required('instructor')
def new_module(course_id):
    """Crear un nuevo módulo en un curso."""
    course = Course.query.get_or_404(course_id)
    if course.instructor_id != current_user.id:
        flash('No tienes permiso para agregar módulos a este curso.', 'danger')
        return redirect(url_for('instructor_courses'))

    if request.method == 'POST':
        title = request.form.get('title')
        description = request.form.get('description')

        if not title or not description:
            flash('Por favor, completa todos los campos.', 'danger')
            return redirect(url_for('new_module', course_id=course_id))

        last_order = max([m.order for m in course.modules], default=0)
        module = Module(title=title, description=description, order=last_order + 1, course_id=course.id)
        db.session.add(module)
        db.session.commit()
        flash('Módulo creado exitosamente.', 'success')
        return redirect(url_for('course_details', course_id=course_id))

    return render_template('instructor/new_module.html', course=course)

@app.route('/instructor/module/edit/<int:module_id>', methods=['GET', 'POST'])
@login_required
@role_required('instructor')
def edit_module(module_id):
    """Editar un módulo existente."""
    module = Module.query.get_or_404(module_id)

    # Verifica que el módulo pertenece al instructor actual
    if module.course.instructor_id != current_user.id:
        flash('No tienes permiso para editar este módulo.', 'danger')
        return redirect(url_for('instructor_courses'))

    if request.method == 'POST':
        module.title = request.form.get('title')
        module.description = request.form.get('description')
        db.session.commit()
        flash('Módulo actualizado exitosamente.', 'success')
        return redirect(url_for('course_details', course_id=module.course_id))

    return render_template('instructor/edit_module.html', module=module)


@app.route('/instructor/module/delete/<int:module_id>', methods=['POST'])
@login_required
@role_required('instructor')
def delete_module(module_id):
    """Eliminar un módulo."""
    module = Module.query.get_or_404(module_id)
    if module.course.instructor_id != current_user.id:
        flash('No tienes permiso para eliminar este módulo.', 'danger')
        return redirect(url_for('instructor_courses'))

    db.session.delete(module)
    db.session.commit()
    flash('Módulo eliminado exitosamente.', 'success')
    return redirect(url_for('course_details', course_id=module.course_id))

@app.route('/instructor/courses/completed', methods=['GET', 'POST'])
@login_required
@role_required('instructor')
def instructor_courses_completed():
    if request.method == 'POST':
        start_date = request.form.get('start_date')
        end_date = request.form.get('end_date')

        # Validate dates
        if not start_date or not end_date:
            flash('Please provide both start and end dates.', 'danger')
            return redirect(url_for('instructor_courses_completed'))

        try:
            start_date = datetime.strptime(start_date, '%Y-%m-%d')
            end_date = datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=1)
        except ValueError:
            flash('Invalid date format. Use YYYY-MM-DD.', 'danger')
            return redirect(url_for('instructor_courses_completed'))

        # Query completed courses
        completed_courses = Course.query.join(CourseEnrollment).filter(
            Course.instructor_id == current_user.id,
            CourseEnrollment.completed == True,
            CourseEnrollment.completion_date.between(start_date, end_date)
        ).all()

        courses_with_modules = []
        for course in completed_courses:
            modules_data = []
            for module in course.modules:
                module_responses = StudentResponse.query.filter(
                    StudentResponse.content_item_id.in_([item.id for item in module.content_items]),
                    StudentResponse.completed == True
                ).all()
                for response in module_responses:
                    modules_data.append({
                        'module_title': module.title,
                        'student_id': response.student_id,
                        'completion_date': response.completion_date
                    })
            courses_with_modules.append({
                'course': course,
                'modules_data': modules_data
            })

        return render_template(
            'instructor/courses_completed.html',
            courses=courses_with_modules,
            start_date=start_date,
            end_date=end_date
        )

    return render_template('instructor/courses_completed_form.html')

@app.route('/instructor/modules/completed', methods=['GET', 'POST'])
@login_required
@role_required('instructor')
def instructor_modules_completed():
    if request.method == 'POST':
        start_date = request.form.get('start_date')
        end_date = request.form.get('end_date')

        # Validate dates
        if not start_date or not end_date:
            flash('Please provide both start and end dates.', 'danger')
            return redirect(url_for('instructor_modules_completed'))

        try:
            start_date = datetime.strptime(start_date, '%Y-%m-%d')
            end_date = datetime.strptime(end_date, '%Y-%m-%d')
        except ValueError:
            flash('Invalid date format. Use YYYY-MM-DD.', 'danger')
            return redirect(url_for('instructor_modules_completed'))

        # Get completed modules within the date range
        completed_modules = []
        for module in Module.query.all():
            # Check if all content items in the module are completed
            module_content_ids = [item.id for item in module.content_items]
            total_content = len(module_content_ids)
            completed_content = StudentResponse.query.filter(
                StudentResponse.content_item_id.in_(module_content_ids),
                StudentResponse.completed == True
            ).distinct(StudentResponse.content_item_id).count()

            if total_content > 0 and completed_content == total_content:
                last_completion_date = StudentResponse.query.filter(
                    StudentResponse.content_item_id.in_(module_content_ids),
                    StudentResponse.completed == True
                ).order_by(StudentResponse.completion_date.desc()).first().completion_date

                # Add the module to the list if within the date range
                if start_date <= last_completion_date <= end_date:
                    completed_modules.append({
                        'module': module,
                        'completion_date': last_completion_date
                    })

        return render_template(
            'instructor/modules_completed.html',
            modules=completed_modules,
            start_date=start_date,
            end_date=end_date
        )

    return render_template('instructor/modules_completed_form.html')

# Añadir contenido a un módulo
@app.route('/instructor/module/<int:module_id>/content/new', methods=['GET', 'POST'])
@login_required
@role_required('instructor')
def new_content(module_id):
    module = Module.query.get_or_404(module_id)
    if module.course.instructor_id != current_user.id:
        flash('No tienes permiso para agregar contenido a este módulo.', 'danger')
        return redirect(url_for('instructor_courses'))

    if request.method == 'POST':
        title = request.form.get('title')
        content_type = request.form.get('content_type')
        text_content = request.form.get('text_content')
        video_url = request.form.get('video_url')
        file = request.files.get('file')

        # Validaciones básicas
        if not title or not content_type:
            flash('El título y el tipo de contenido son obligatorios.', 'danger')
            return redirect(url_for('new_content', module_id=module_id))

        # Inicializa las variables de contenido
        content = None
        file_path = None

        # Procesar contenido según su tipo
        if content_type == 'text':
            content = text_content
        elif content_type == 'video':
            content = video_url
        elif content_type == 'file' and file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)

        # Guardar contenido en la base de datos
        last_order = max([c.order for c in module.content_items], default=0)
        new_content = ContentItem(
            title=title,
            type=content_type,
            content=content,
            file_path=file_path,
            order=last_order + 1,
            module_id=module_id
        )
        db.session.add(new_content)
        db.session.commit()

        flash('Contenido añadido exitosamente.', 'success')
        return redirect(url_for('module_details', module_id=module_id))

    return render_template('instructor/new_content.html', module=module)


@app.route('/instructor/content/edit/<int:content_id>', methods=['GET', 'POST'])
@login_required
@role_required('instructor')
def edit_content(content_id):
    """Editar contenido de un módulo."""
    content_item = ContentItem.query.get_or_404(content_id)
    if content_item.module.course.instructor_id != current_user.id:
        flash('No tienes permiso para editar este contenido.', 'danger')
        return redirect(url_for('instructor_courses'))

    if request.method == 'POST':
        content_item.title = request.form.get('title')
        content_item.content = request.form.get('content')
        db.session.commit()
        flash('Contenido actualizado exitosamente.', 'success')
        return redirect(url_for('module_details', module_id=content_item.module.id))

    return render_template('instructor/edit_content.html', content_item=content_item)

@app.route('/instructor/content/delete/<int:content_id>', methods=['POST'])
@login_required
@role_required('instructor')
def delete_content(content_id):
    """Eliminar contenido de un módulo."""
    content_item = ContentItem.query.get_or_404(content_id)
    if content_item.module.course.instructor_id != current_user.id:
        flash('No tienes permiso para eliminar este contenido.', 'danger')
        return redirect(url_for('instructor_courses'))

    module_id = content_item.module.id
    db.session.delete(content_item)
    db.session.commit()
    flash('Contenido eliminado exitosamente.', 'success')
    return redirect(url_for('module_details', module_id=module_id))

# Rutas relacionadas con quizzes
@app.route('/instructor/module/<int:module_id>/quiz/new', methods=['GET', 'POST'])
@login_required
@role_required('instructor')
def new_quiz(module_id):
    module = Module.query.get_or_404(module_id)

    if request.method == 'POST':
        try:
            print("Datos del formulario recibidos:", request.form)
            title = request.form.get('title')
            question_texts = request.form.getlist('questions[]')
            question_types = request.form.getlist('question_types[]')
            options = request.form.to_dict(flat=False).get('options', {})

            if not title:
                flash('El título del quiz es obligatorio.', 'danger')
                return redirect(url_for('new_quiz', module_id=module_id))

            if not question_texts:
                flash('Debe incluir al menos una pregunta.', 'danger')
                return redirect(url_for('new_quiz', module_id=module_id))

            next_order = module.get_next_content_order()
            print(f"El siguiente número de orden es: {next_order}")

            quiz = ContentItem(title=title, type='quiz', module_id=module.id, order=next_order)
            db.session.add(quiz)
            db.session.flush()
            print(f"Quiz creado con ID: {quiz.id}")

            for idx, question_text in enumerate(question_texts):
                question_type = question_types[idx]
                question_key = str(idx + 1)
                question_options = [opt for opt in request.form.getlist(f'options[{question_key}][]')]
                correct_answer = request.form.get(f'correct_answers[{question_key}]')

                print(f"Procesando pregunta {idx + 1}:")
                print(f"Texto: {question_text}")
                print(f"Tipo: {question_type}")
                print(f"Respuesta correcta: {correct_answer}")
                print(f"Opciones: {question_options}")

                if question_type == 'multiple_choice' and not question_options:
                    flash(f'La pregunta {idx + 1} requiere opciones.', 'danger')
                    db.session.rollback()
                    return redirect(url_for('new_quiz', module_id=module_id))

                options_json = json.dumps(question_options) if question_type == 'multiple_choice' else None

                question = QuizQuestion(
                    question_text=question_text,
                    question_type=question_type,
                    correct_answer=correct_answer or '',
                    options=options_json,
                    content_item_id=quiz.id
                )
                db.session.add(question)
                print("Pregunta añadida:", question.to_dict())

            print("Objetos en la sesión antes del commit:", db.session.new)
            db.session.commit()
            print("Quiz y preguntas guardados exitosamente.")
            flash('Quiz creado exitosamente.', 'success')
            return redirect(url_for('list_quizzes', module_id=module.id))

        except Exception as e:
            db.session.rollback()
            print("Error al guardar en la base de datos:", str(e))
            flash(f'Error al crear el quiz: {e}', 'danger')
            return render_template('instructor/create_quiz.html', module=module)

    return render_template('instructor/create_quiz.html', module=module)


@app.route('/instructor/quiz/<int:quiz_id>/edit', methods=['GET', 'POST'])
@login_required
@role_required('instructor')
def edit_quiz(quiz_id):
    """Editar un quiz existente."""
    quiz = ContentItem.query.get_or_404(quiz_id)

    if quiz.type != 'quiz':
        flash('El contenido seleccionado no es un quiz.', 'danger')
        return redirect(url_for('instructor_dashboard'))

    if request.method == 'POST':
        try:
            # Actualizar título del quiz
            title = request.form.get('title')
            if not title:
                flash('El título del quiz no puede estar vacío.', 'danger')
                return render_template('instructor/edit_quiz.html', quiz=quiz)

            quiz.title = title

            # Procesar preguntas
            existing_questions = {str(q.id): q for q in quiz.questions}
            question_ids = request.form.getlist('question_ids[]')  # IDs de preguntas existentes
            question_texts = request.form.getlist('questions[]')
            question_types = request.form.getlist('question_types[]')
            correct_answers = request.form.getlist('correct_answers[]')
            options = request.form.to_dict(flat=False).get('options', {})

            if not (len(question_texts) == len(question_types) == len(correct_answers)):
                flash('Los datos de las preguntas no son consistentes.', 'danger')
                return render_template('instructor/edit_quiz.html', quiz=quiz)

            # Actualizar preguntas existentes y agregar nuevas
            updated_questions = set()
            for idx, question_text in enumerate(question_texts):
                question_type = question_types[idx]
                correct_answer = correct_answers[idx] if idx < len(correct_answers) else None
                question_options = options.get(f'options[{idx + 1}]', [])

                question_id = question_ids[idx] if idx < len(question_ids) else None

                if question_id and question_id in existing_questions:
                    # Actualizar pregunta existente
                    question = existing_questions[question_id]
                    question.question_text = question_text
                    question.question_type = question_type
                    question.correct_answer = correct_answer
                    question.options = json.dumps(question_options) if question_type == 'multiple_choice' else None
                    updated_questions.add(question_id)
                else:
                    # Crear nueva pregunta
                    new_question = QuizQuestion(
                        question_text=question_text,
                        question_type=question_type,
                        correct_answer=correct_answer,
                        options=json.dumps(question_options) if question_type == 'multiple_choice' else None,
                        content_item_id=quiz.id
                    )
                    db.session.add(new_question)

            # Eliminar preguntas que no fueron incluidas
            for question_id, question in existing_questions.items():
                if question_id not in updated_questions:
                    db.session.delete(question)

            db.session.commit()
            flash('Quiz actualizado exitosamente.', 'success')
            return redirect(url_for('list_quizzes', module_id=quiz.module_id))

        except Exception as e:
            db.session.rollback()
            print(f"Error al actualizar el quiz: {str(e)}")
            flash(f'Error al actualizar el quiz: {e}', 'danger')

    return render_template('instructor/edit_quiz.html', quiz=quiz)


@app.route('/instructor/module/<int:module_id>/quizzes', methods=['GET'])
@login_required
@role_required('instructor')
def list_quizzes(module_id):
    """Listar quizzes de un módulo."""
    module = Module.query.get_or_404(module_id)
    quizzes = ContentItem.query.filter_by(module_id=module_id, type='quiz').all()
    return render_template('instructor/list_quizzes.html', module=module, quizzes=quizzes)


@app.route('/instructor/quiz/<int:quiz_id>/delete', methods=['POST'])
@login_required
@role_required('instructor')
def delete_quiz(quiz_id):
    """Eliminar un quiz junto con sus preguntas."""
    quiz = ContentItem.query.get_or_404(quiz_id)

    # Verifica que el instructor tiene permisos para eliminar el quiz
    if quiz.module.course.instructor_id != current_user.id:
        flash('No tienes permiso para eliminar este quiz.', 'danger')
        return redirect(url_for('instructor_courses'))

    try:
        # Eliminar todas las preguntas asociadas al quiz
        for question in quiz.questions:
            db.session.delete(question)
        
        # Eliminar el quiz después de borrar las preguntas
        db.session.delete(quiz)
        db.session.commit()
        flash('Quiz eliminado exitosamente.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al eliminar el quiz: {e}', 'danger')

    return redirect(url_for('list_quizzes', module_id=quiz.module_id))

@app.route('/instructor/course/<int:course_id>/students', methods=['GET'])
@login_required
@role_required('instructor')
def course_students(course_id):
    """Ver las notas de los estudiantes en un curso específico."""
    # Verificar que el curso pertenece al instructor actual
    course = Course.query.get_or_404(course_id)
    if course.instructor_id != current_user.id:
        flash('No tienes acceso a este curso.', 'danger')
        return redirect(url_for('instructor_dashboard'))

    # Obtener los estudiantes inscritos y sus calificaciones en quizzes
    enrollments = CourseEnrollment.query.filter_by(course_id=course_id).all()
    students_data = []

    for enrollment in enrollments:
        student = enrollment.student

        # Obtener quizzes completados por el estudiante
        completed_quizzes = StudentResponse.query.filter_by(
            student_id=student.id,
            completed=True
        ).join(ContentItem).filter(
            ContentItem.module.has(course_id=course_id),
            ContentItem.type == 'quiz'
        ).all()

        # Preparar datos del estudiante y sus quizzes
        quizzes = [
            {'title': quiz.content_item.title, 'score': quiz.score}
            for quiz in completed_quizzes
        ]

        students_data.append({
            'student': student,
            'quizzes': quizzes
        })

    return render_template('instructor/course_students.html', course=course, students=students_data)


# -------------------- Rutas de Estudiante -------------------- #

@app.route('/student/dashboard')
@login_required
@role_required('student')
def student_dashboard():
    """Panel principal del estudiante con sus cursos inscritos."""
    enrollments = CourseEnrollment.query.filter_by(student_id=current_user.id).all()
    
    # Añadir progreso al contexto de los cursos
    courses_with_progress = [
        {
            'course': enrollment.course,
            'progress': enrollment.progress,
            'completed': enrollment.completed
        }
        for enrollment in enrollments
    ]
    return render_template('student/student_dashboard.html', courses=courses_with_progress)

@app.route('/student/explore_courses')
@login_required
@role_required('student')
def explore_courses():
    """Ver todos los cursos disponibles para inscripción."""
    enrolled_courses = [enrollment.course_id for enrollment in current_user.enrollments]
    available_courses = Course.query.filter(~Course.id.in_(enrolled_courses)).all()  # Cursos no inscritos
    return render_template('student/explore_courses.html', courses=available_courses)


@app.route('/student/my_courses')
@login_required
@role_required('student')
def my_courses():
    """Ver los cursos en los que el estudiante está inscrito."""
    enrolled_courses = [enrollment.course for enrollment in current_user.enrollments]
    return render_template('student/my_courses.html', courses=enrolled_courses)


@app.route('/student/courses/<int:course_id>', methods=['GET'])
@login_required
@role_required('student')
def course_content(course_id):
    """Ver contenido de un curso inscrito."""
    course = Course.query.get_or_404(course_id)
    enrollment = CourseEnrollment.query.filter_by(student_id=current_user.id, course_id=course_id).first()
    if not enrollment:
        flash('No estás inscrito en este curso.', 'danger')
        return redirect(url_for('student_dashboard'))

    modules = course.get_modules_sorted()
    return render_template('student/course_content.html', course=course, modules=modules)

@app.route('/student/courses/<int:course_id>/modules/<int:module_id>', methods=['GET'])
@login_required
@role_required('student')
def view_module_content(course_id, module_id):
    """Ver contenido de un módulo."""
    module = Module.query.get_or_404(module_id)
    if module.course_id != course_id:
        flash('No tienes permiso para ver este contenido.', 'danger')
        return redirect(url_for('student_dashboard'))

    content_items = module.get_content_items_sorted()

    # Depuración
    for content in content_items:
        print(content.title, content.type, content.content)  # Verifica los valores

    return render_template('student/module_content.html', module=module, content_items=content_items)


@app.route('/student/courses/<int:course_id>/modules/<int:module_id>/content/<int:content_id>', methods=['GET'])
@login_required
@role_required('student')
def content_view(course_id, module_id, content_id):
    """Ver un contenido específico del módulo."""
    content = ContentItem.query.get_or_404(content_id)

    # Verificar que el contenido pertenece al módulo y curso correctos
    if content.module_id != module_id or content.module.course_id != course_id:
        flash('No tienes permiso para ver este contenido.', 'danger')
        return redirect(url_for('student_dashboard'))

    # Renderizar según el tipo de contenido
    if content.type == 'quiz':
        return redirect(url_for('take_quiz', course_id=course_id, quiz_id=content.id))

    return render_template('student/content_view.html', content=content)

@app.route('/student/quiz/<int:quiz_id>/take', methods=['GET', 'POST'])
@login_required
@role_required('student')
def take_quiz(quiz_id):
    """Permitir que el estudiante realice un quiz y reciba calificación."""
    quiz = ContentItem.query.get_or_404(quiz_id)
    if quiz.type != 'quiz':
        flash('El contenido seleccionado no es un quiz.', 'danger')
        return redirect(url_for('student_dashboard'))

    # Verificar si el estudiante ya obtuvo una nota mayor o igual a 7
    existing_response = StudentResponse.query.filter_by(
        student_id=current_user.id,
        content_item_id=quiz_id
    ).filter(StudentResponse.score >= 7).first()

    if existing_response:
        flash('Ya obtuviste una nota mayor o igual a 7 en este quiz. No puedes intentarlo nuevamente.', 'info')
        return redirect(url_for('student_dashboard'))

    if request.method == 'POST':
        total_questions = len(quiz.questions)
        correct_answers = 0

        for question in quiz.questions:
            student_answer = request.form.get(f'question_{question.id}')
            print(f"Pregunta {question.id}: Respuesta del estudiante: {student_answer}")  # Depuración
            if student_answer and question.is_answer_correct(student_answer):
                correct_answers += 1

        # Calcular el puntaje
        score = (correct_answers / total_questions) * 10
        print(f"Puntaje obtenido: {score}")  # Depuración

        # Guardar la respuesta del estudiante
        response = StudentResponse(
            student_id=current_user.id,
            content_item_id=quiz.id,
            response=json.dumps(request.form),  # Guardar todas las respuestas como JSON
            score=score,
            completed=True,
            completion_date=datetime.utcnow()
        )
        db.session.add(response)

        # Actualizar progreso del curso
        enrollment = CourseEnrollment.query.filter_by(
            student_id=current_user.id, course_id=quiz.module.course.id
        ).first()
        if enrollment:
            enrollment.update_progress()

        db.session.commit()

        # Mostrar mensaje según el puntaje
        if score >= 7:
            flash('¡Felicidades! Has aprobado el curso y obtendrás tu certificado.', 'success')
        else:
            flash('No alcanzaste la nota mínima. Intenta nuevamente.', 'danger')

        return redirect(url_for('student_dashboard'))

    return render_template('student/quiz.html', quiz=quiz)

@app.route('/student/enroll/<int:course_id>', methods=['POST'])
@login_required
@role_required('student')
def enroll_course(course_id):
    """Permitir que el estudiante se inscriba en un curso."""
    course = Course.query.get_or_404(course_id)
    enrollment = CourseEnrollment.query.filter_by(student_id=current_user.id, course_id=course_id).first()

    if enrollment:
        flash('Ya estás inscrito en este curso.', 'warning')
    else:
        new_enrollment = CourseEnrollment(
            student_id=current_user.id,
            course_id=course_id,
            enrollment_date=datetime.utcnow()
        )
        db.session.add(new_enrollment)
        db.session.commit()
        flash(f'Te has inscrito exitosamente en el curso: {course.name}', 'success')

    return redirect(url_for('student_dashboard'))

def youtube_embed(url):
    """Convierte una URL de YouTube en un embed URL compatible con iframe."""
    parsed_url = urlparse(url)
    if 'youtube.com' in parsed_url.netloc:
        query_params = parse_qs(parsed_url.query)
        video_id = query_params.get('v', [None])[0]
        if video_id:
            return f"https://www.youtube.com/embed/{video_id}"
    elif 'youtu.be' in parsed_url.netloc:
        video_id = parsed_url.path[1:]
        return f"https://www.youtube.com/embed/{video_id}"
    return url

app.jinja_env.filters['youtube_embed'] = youtube_embed

@app.template_filter('loads')
def loads_filter(value):
    """Filtro personalizado para deserializar cadenas JSON."""
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return {}

with app.app_context():
    enrollments = CourseEnrollment.query.all()
    for enrollment in enrollments:
        # Recalcular progreso y marcar como completado si corresponde
        total_content = sum(len(module.content_items) for module in enrollment.course.modules)
        completed_content = StudentResponse.query.filter_by(student_id=enrollment.student_id, completed=True).count()
        enrollment.progress = (completed_content / total_content) * 100 if total_content > 0 else 0

        if enrollment.progress == 100:
            enrollment.completed = True
            enrollment.completion_date = datetime.utcnow()  # Establecer fecha actual como finalización
        else:
            enrollment.completed = False
            enrollment.completion_date = None
        db.session.commit()

    print("Datos existentes actualizados correctamente.")

def update_completion_dates():
    # Obtener todas las inscripciones con progreso al 100% pero sin fecha de finalización
    enrollments = CourseEnrollment.query.filter_by(completed=True, completion_date=None).all()
    
    for enrollment in enrollments:
        # Calcular la fecha más reciente en las respuestas del estudiante
        student_responses = StudentResponse.query.filter_by(student_id=enrollment.student_id).all()
        if student_responses:
            latest_completion_date = max([response.completion_date for response in student_responses if response.completed])
            enrollment.completion_date = latest_completion_date or datetime.utcnow()
            db.session.add(enrollment)
        db.session.commit()


if __name__ == '__main__':
    app.run(debug=True)