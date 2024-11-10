# app/app.py
from flask import Flask, render_template, redirect, url_for, request, flash, abort
from config import Config
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from flask_migrate import Migrate
from models import db, User, Role, Course
from functools import wraps
from flask_assets import Environment, Bundle


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
# Crear rol y usuario administrador inicial
with app.app_context():
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
    
    # Asegurarse de que se crea un usuario administrador con el rol adecuado
    if not admin_user and admin_role:
        password_hash = bcrypt.generate_password_hash('admin123').decode('utf-8')
        admin_user = User(username='admin', password=password_hash, role=admin_role)
        db.session.add(admin_user)
        db.session.commit()
        print("Usuario administrador creado con éxito. Usuario: 'admin', Contraseña: 'admin123'")



# Rutas del Administrador
@app.route('/admin/dashboard')
@login_required
@role_required('admin')
def admin_dashboard():
    return render_template('admin/admin_dashboard.html')

@app.route('/admin/manage_courses')
@login_required
@role_required('admin')
def manage_courses():
    # Lógica para gestionar cursos
    return render_template('admin/manage_courses.html')

@app.route('/admin/register_user', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def register_user():
    if request.method == 'POST':
        username = request.form['username']
        password = bcrypt.generate_password_hash(request.form['password']).decode('utf-8')
        role_name = request.form['role']
        role = Role.query.filter_by(name=role_name).first()
        if not role:
            flash('Rol no encontrado', 'danger')
            return redirect(url_for('register_user'))
        user = User(username=username, password=password, role=role)
        db.session.add(user)
        db.session.commit()
        flash('Usuario creado exitosamente', 'success')
        return redirect(url_for('admin_dashboard'))
    roles = Role.query.all()
    return render_template('admin/register_user.html', roles=roles)

# Rutas del Instructor
# Ruta para el dashboard del instructor
@app.route('/instructor/dashboard')
@login_required
@role_required('instructor')
def instructor_dashboard():
    # Obtener todos los cursos del instructor actual
    courses = Course.query.filter_by(instructor_id=current_user.id).all()
    return render_template('instructor/instructor_dashboard.html', courses=courses)

# Ruta para crear un curso
@app.route('/instructor/create_course', methods=['GET', 'POST'])
@login_required
@role_required('instructor')
def create_course():
    if request.method == 'POST':
        # Obtener datos del formulario
        title = request.form.get('title')
        description = request.form.get('description')

        # Crear el nuevo curso
        new_course = Course(
            title=title,
            description=description,
            instructor_id=current_user.id
        )
        
        # Guardar el curso en la base de datos
        db.session.add(new_course)
        db.session.commit()

        flash('Curso creado exitosamente.', 'success')
        return redirect(url_for('instructor_dashboard'))
    
    return render_template('instructor/create_course.html')

# Ruta para editar un curso
@app.route('/instructor/edit_course/<int:course_id>', methods=['GET', 'POST'])
@login_required
@role_required('instructor')
def edit_course(course_id):
    # Obtener el curso
    course = Course.query.get_or_404(course_id)
    
    # Verificar que el curso pertenece al instructor actual
    if course.instructor_id != current_user.id:
        abort(403)
    
    if request.method == 'POST':
        # Actualizar los datos del curso
        course.title = request.form.get('title')
        course.description = request.form.get('description')

        # Guardar cambios en la base de datos
        db.session.commit()
        
        flash('Curso actualizado exitosamente.', 'success')
        return redirect(url_for('instructor_dashboard'))
    
    return render_template('instructor/edit_course.html', course=course)

# Ruta para gestionar un curso (visualización, eliminar, etc.)
@app.route('/instructor/manage_course/<int:course_id>', methods=['GET', 'POST'])
@login_required
@role_required('instructor')
def manage_course(course_id):
    # Obtener el curso
    course = Course.query.get_or_404(course_id)

    # Verificar que el curso pertenece al instructor actual
    if course.instructor_id != current_user.id:
        abort(403)
    
    if request.method == 'POST':
        # Si el instructor decide eliminar el curso
        db.session.delete(course)
        db.session.commit()
        
        flash('Curso eliminado exitosamente.', 'success')
        return redirect(url_for('instructor_dashboard'))
    
    # Aquí podrías añadir lógica adicional, como obtener estudiantes inscritos u otros datos del curso
    return render_template('instructor/manage_course.html', course=course)

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
    return render_template('student/view_courses.html', courses=courses)

# Ruta de inicio de sesión

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if username and password:  # Verifica que ambos campos estén presentes
            user = User.query.filter_by(username=username).first()
            if user and bcrypt.check_password_hash(user.password, password):
                login_user(user)
                flash('Inicio de sesión exitoso', 'success')

                # Redirecciona al dashboard correcto en función del rol del usuario
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

# Comando para actualizar la contraseña de un usuario específico desde la terminal
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

if __name__ == '__main__':
    app.run(debug=True)