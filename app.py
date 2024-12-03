from flask import Flask, render_template, redirect, url_for, request, flash, abort
from flask_bcrypt import Bcrypt
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect
from werkzeug.utils import secure_filename
from models import db, User, Role, Course, Module, ContentItem, CourseEnrollment, StudentResponse, QuizQuestion
from functools import wraps
from datetime import datetime
import os
from forms import DeleteUserForm
from urllib.parse import urlparse, parse_qs
import json


# Application Configuration
app = Flask(__name__, template_folder="app/templates", static_folder="app/static")
app.config.from_object('config.Config')

# Static Upload Folder
UPLOAD_FOLDER = os.path.join(app.root_path, 'static/uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def allowed_file(filename):
    ALLOWED_EXTENSIONS = {'pdf', 'docx', 'txt', 'mp4'}
    VALID_CONTENT_TYPES = ['text', 'video', 'file', 'quiz']
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS



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
    return render_template('admin/admin_dashboard.html')

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
    """Panel principal del instructor."""
    courses = Course.query.filter_by(instructor_id=current_user.id).all()
    return render_template('instructor/instructor_dashboard.html', courses=courses)

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
@app.route('/instructor/course/delete/<int:course_id>', methods=['POST'])
@login_required
@role_required('instructor')
def delete_course(course_id):
    """Eliminar un curso."""
    course = Course.query.get_or_404(course_id)
    if course.instructor_id != current_user.id:
        flash('No tienes permiso para eliminar este curso.', 'danger')
        return redirect(url_for('instructor_dashboard'))

    db.session.delete(course)
    db.session.commit()
    flash('Curso eliminado exitosamente.', 'success')
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
            new_questions_data = request.form.getlist('questions[]')
            question_types = request.form.getlist('question_types[]')
            correct_answers = request.form.to_dict(flat=False).get('correct_answers', [])
            options = request.form.to_dict(flat=False).get('options', {})

            # Actualizar preguntas existentes y agregar nuevas
            for idx, question_text in enumerate(new_questions_data):
                question_type = question_types[idx]
                correct_answer = correct_answers[idx] if idx < len(correct_answers) else None
                question_options = options.get(str(idx + 1), [])

                if str(idx) in existing_questions:
                    # Actualizar pregunta existente
                    question = existing_questions.pop(str(idx))
                    question.question_text = question_text
                    question.question_type = question_type
                    question.correct_answer = correct_answer
                    question.options = json.dumps(question_options) if question_type == 'multiple_choice' else None
                else:
                    # Agregar nueva pregunta
                    new_question = QuizQuestion(
                        question_text=question_text,
                        question_type=question_type,
                        correct_answer=correct_answer,
                        options=json.dumps(question_options) if question_type == 'multiple_choice' else None,
                        content_item_id=quiz.id
                    )
                    db.session.add(new_question)

            # Eliminar preguntas no incluidas en la actualización
            for question in existing_questions.values():
                db.session.delete(question)

            db.session.commit()
            flash('Quiz actualizado exitosamente.', 'success')
            return redirect(url_for('list_quizzes', module_id=quiz.module_id))

        except Exception as e:
            db.session.rollback()
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

# -------------------- Rutas de Estudiante -------------------- #

@app.route('/student/dashboard')
@login_required
@role_required('student')
def student_dashboard():
    """Panel principal del estudiante con sus cursos inscritos."""
    courses = Course.query.join(CourseEnrollment).filter(CourseEnrollment.student_id == current_user.id).all()
    return render_template('student/student_dashboard.html', courses=courses)


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

    if request.method == 'POST':
        total_questions = len(quiz.questions)
        correct_answers = 0

        for question in quiz.questions:
            student_answer = request.form.get(f'question_{question.id}')
            if student_answer and question.is_answer_correct(student_answer):
                correct_answers += 1

        score = (correct_answers / total_questions) * 10

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

        # Verificar si aprobó
        if score >= 7:
            flash('¡Felicidades! Has aprobado el curso y obtendrás tu certificado.', 'success')
        else:
            flash('No alcanzaste la nota mínima. Intenta nuevamente.', 'danger')

        return redirect(url_for('student_dashboard'))

    return render_template('student/take_quiz.html', quiz=quiz)


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

if __name__ == '__main__':
    app.run(debug=True)
