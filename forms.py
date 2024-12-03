from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SelectField, FileField, SubmitField
from wtforms.validators import DataRequired

class DeleteUserForm(FlaskForm):
    submit = SubmitField('Eliminar Usuario')

class CourseForm(FlaskForm):
    title = StringField('Título del Curso', validators=[DataRequired()])
    description = TextAreaField('Descripción del Curso', validators=[DataRequired()])

class ModuleForm(FlaskForm):
    title = StringField('Título del Módulo', validators=[DataRequired()])
    description = TextAreaField('Descripción del Módulo', validators=[DataRequired()])

class ContentForm(FlaskForm):
    title = StringField('Título del Contenido', validators=[DataRequired()])
    content_type = SelectField(
        'Tipo de Contenido',
        choices=[('text', 'Texto'), ('video', 'Video')],
        validators=[DataRequired()]
    )
    file = FileField('Archivo')
    content = StringField('Contenido (Texto o URL)')

