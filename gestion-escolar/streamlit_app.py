# school_app.py
# Streamlit app: Gestión escolar simple y profesional
# Single-file Streamlit app diseñado para profesores con poca habilidad informática
# Requisitos: streamlit, pandas
# Ejecutar: streamlit run school_app.py

import streamlit as st
import sqlite3
import pandas as pd
import os
from datetime import datetime
from pathlib import Path
import io
import base64

# ------------------ Config y estilos ------------------
st.set_page_config(page_title="Gestión Escolar", layout="wide")

STYLE = """
<style>
.big-title{font-size:30px; font-weight:600;}
.small-muted{color: #6c757d; font-size:13px}
.card{background:#ffffff; padding:16px; border-radius:10px; box-shadow: 0 1px 4px rgba(0,0,0,0.08)}
</style>
"""

st.markdown(STYLE, unsafe_allow_html=True)

DATA_DIR = Path("data")
EXAMS_DIR = DATA_DIR / "exams"
DB_PATH = DATA_DIR / "school.db"
DATA_DIR.mkdir(exist_ok=True)
EXAMS_DIR.mkdir(exist_ok=True)

# ------------------ Base de datos ------------------

def get_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

conn = get_connection()


def init_db():
    cur = conn.cursor()
    # Estudiantes
    cur.execute('''
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_code TEXT UNIQUE,
            first_name TEXT,
            last_name TEXT,
            extra TEXT
        )
    ''')
    # Profesores
    cur.execute('''
        CREATE TABLE IF NOT EXISTS teachers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE,
            email TEXT
        )
    ''')
    # Materias
    cur.execute('''
        CREATE TABLE IF NOT EXISTS subjects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE,
            description TEXT
        )
    ''')
    # Clases (un registro por sesión de clase o tipo de clase)
    cur.execute('''
        CREATE TABLE IF NOT EXISTS classes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject_id INTEGER,
            teacher_id INTEGER,
            class_name TEXT,
            schedule TEXT,
            FOREIGN KEY(subject_id) REFERENCES subjects(id),
            FOREIGN KEY(teacher_id) REFERENCES teachers(id)
        )
    ''')
    # Asistencias: una fila por estudiante por fecha
    cur.execute('''
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            class_id INTEGER,
            student_id INTEGER,
            date TEXT,
            present INTEGER DEFAULT 0,
            note TEXT,
            FOREIGN KEY(class_id) REFERENCES classes(id),
            FOREIGN KEY(student_id) REFERENCES students(id)
        )
    ''')
    # Notas
    cur.execute('''
        CREATE TABLE IF NOT EXISTS grades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            class_id INTEGER,
            student_id INTEGER,
            date TEXT,
            grade REAL,
            weight REAL DEFAULT 1,
            description TEXT,
            FOREIGN KEY(class_id) REFERENCES classes(id),
            FOREIGN KEY(student_id) REFERENCES students(id)
        )
    ''')
    # Examenes (metadatos, archivo guardado en EXAMS_DIR)
    cur.execute('''
        CREATE TABLE IF NOT EXISTS exams (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_name TEXT,
            uploaded_by TEXT,
            subject_id INTEGER,
            class_id INTEGER,
            upload_date TEXT,
            original_name TEXT,
            FOREIGN KEY(subject_id) REFERENCES subjects(id),
            FOREIGN KEY(class_id) REFERENCES classes(id)
        )
    ''')
    conn.commit()

init_db()

# ------------------ Helpers de BD ------------------

def query_df(query, params=()):
    return pd.read_sql_query(query, conn, params=params)


def execute(query, params=()):
    cur = conn.cursor()
    cur.execute(query, params)
    conn.commit()
    return cur

# ------------------ UI: Barra lateral ------------------

st.sidebar.title("Navegación")
page = st.sidebar.radio("Ir a:", [
    "Inicio",
    "Cargar exámenes",
    "Consultar alumnos",
    "Notas",
    "Clases & Materias",
    "Profesores",
    "Ajustes / Exportar"
])

# Pequeño header
st.markdown("<div class='big-title'>Gestión Escolar - Panel del Profesor</div>", unsafe_allow_html=True)
st.markdown("Aplicación sencilla e intuitiva para administrar exámenes, asistencias, notas y materias.")

# ------------------ Página: Inicio ------------------
if page == "Inicio":
    st.subheader("Bienvenido")
    col1, col2, col3 = st.columns([1,2,1])
    with col1:
        st.metric("Estudiantes", query_df('SELECT COUNT(*) as c FROM students').iloc[0,0])
        st.metric("Profesores", query_df('SELECT COUNT(*) as c FROM teachers').iloc[0,0])
    with col2:
        st.info("Use el menú a la izquierda; todas las acciones son guardadas automáticamente.")
        st.markdown("**Consejos rápidos:**")
        st.write("- Para cargar muchos alumnos, use la opción 'Clases & Materias' -> 'Importar alumnos (CSV)'.")
        st.write("- Puede descargar reportes en CSV desde 'Ajustes / Exportar'.")

# ------------------ Página: Cargar exámenes ------------------
elif page == "Cargar exámenes":
    st.subheader("Cargar exámenes")
    st.write("Suba archivos de exámenes (PDF, imágenes, Word). Quedarán guardados localmente y registrados en la base de datos.")

    subjects_df = query_df('SELECT id, name FROM subjects')
    classes_df = query_df('SELECT id, class_name FROM classes')

    uploaded_by = st.text_input("Nombre del que sube (ej: Prof. Pérez)")
    subject_choice = st.selectbox("Seleccionar materia (opcional)", options=[(None, "-- Ninguna --")] + list(subjects_df.itertuples(index=False)), format_func=lambda x: x[1] if x and x[0] is not None else x[1])
    class_choice = st.selectbox("Seleccionar clase (opcional)", options=[(None, "-- Ninguna --")] + list(classes_df.itertuples(index=False)), format_func=lambda x: x[1] if x and x[0] is not None else x[1])

    file = st.file_uploader("Seleccionar archivo de examen", type=['pdf','png','jpg','jpeg','doc','docx'], accept_multiple_files=False)
    if st.button("Subir examen"):
        if not file:
            st.warning("Primero seleccione un archivo.")
        else:
            timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
            safe_name = f"exam_{timestamp}_{file.name}"
            dest = EXAMS_DIR / safe_name
            with open(dest, "wb") as f:
                f.write(file.getbuffer())
            # registrar en DB
            subj_id = subject_choice[0] if subject_choice and subject_choice[0] is not None else None
            class_id = class_choice[0] if class_choice and class_choice[0] is not None else None
            execute('INSERT INTO exams(file_name, uploaded_by, subject_id, class_id, upload_date, original_name) VALUES (?, ?, ?, ?, ?, ?)',
                    (safe_name, uploaded_by or '' , subj_id, class_id, datetime.now().isoformat(), file.name))
            st.success(f"Archivo subido como {safe_name} y registrado correctamente.")

    st.markdown("---")
    st.write("Exámenes subidos:")
    exams_df = query_df('SELECT e.id, e.original_name, e.file_name, e.uploaded_by, e.upload_date, s.name AS subject, c.class_name AS class FROM exams e LEFT JOIN subjects s ON e.subject_id=s.id LEFT JOIN classes c ON e.class_id=c.id ORDER BY e.upload_date DESC')
    if not exams_df.empty:
        st.dataframe(exams_df)
        sel = st.selectbox("Seleccionar examen para descargar/eliminar", options=exams_df['id'])
        action = st.selectbox("Acción", ["Descargar", "Eliminar"], index=0)
        if st.button("Ejecutar acción"):
            row = exams_df[exams_df['id']==sel].iloc[0]
            filepath = EXAMS_DIR / row['file_name']
            if action == "Descargar":
                with open(filepath, 'rb') as f:
                    data = f.read()
                b64 = base64.b64encode(data).decode()
                href = f"data:application/octet-stream;base64,{b64}"
                st.markdown(f"[Descargar {row['original_name']}]({href})")
            else:
                try:
                    filepath.unlink()
                except Exception:
                    pass
                execute('DELETE FROM exams WHERE id=?', (sel,))
                st.success("Examen eliminado.")
    else:
        st.info("No hay exámenes subidos aún.")

# ------------------ Página: Consultar alumnos (Asistencias e Inasistencias) ------------------
elif page == "Consultar alumnos":
    st.subheader("Control de asistencia")
    classes_df = query_df('SELECT id, class_name FROM classes')
    class_opt = st.selectbox("Seleccionar clase", options= [None] + list(classes_df.itertuples(index=False)), format_func=lambda x: x[1] if x else "-- Selecciona --")

    if class_opt:
        class_id = class_opt[0]
        # obtener lista de estudiantes
        students_df = query_df('SELECT id, student_code, first_name, last_name FROM students ORDER BY last_name, first_name')
        if students_df.empty:
            st.warning("No hay estudiantes registrados. Importe alumnos en 'Clases & Materias'.")
        else:
            date = st.date_input("Fecha de clase", value=datetime.today())
            date_str = date.isoformat()
            st.write("Marque los estudiantes presentes (desmarque para ausentes):")
            cols = st.columns([1,3,2,1])
            present = {}
            for i, row in students_df.iterrows():
                key = f"present_{row['id']}_{date_str}"
                present[row['id']] = st.checkbox(f"{row['last_name']}, {row['first_name']}", key=key, value=True)

            if st.button("Guardar asistencia"):
                for sid, is_present in present.items():
                    # comprobar si ya existe
                    cur = execute('SELECT id FROM attendance WHERE class_id=? AND student_id=? AND date=?', (class_id, sid, date_str))
                    found = cur.fetchone()
                    if found:
                        execute('UPDATE attendance SET present=? WHERE id=?', (1 if is_present else 0, found['id']))
                    else:
                        execute('INSERT INTO attendance(class_id, student_id, date, present) VALUES (?, ?, ?, ?)', (class_id, sid, date_str, 1 if is_present else 0))
                st.success('Asistencias guardadas.')

            st.markdown('---')
            st.write('Resumen de asistencia por estudiante (todas las fechas):')
            att = query_df('SELECT a.student_id, s.first_name, s.last_name, SUM(a.present) as presents, COUNT(a.id) as total FROM attendance a JOIN students s ON a.student_id=s.id WHERE a.class_id=? GROUP BY a.student_id, s.first_name, s.last_name', params=(class_id,))
            if not att.empty:
                att['percent'] = (att['presents'] / att['total'] * 100).round(1)
                st.dataframe(att)
            else:
                st.info('Aún no hay registros de asistencia para esta clase.')

# ------------------ Página: Notas ------------------
elif page == "Notas":
    st.subheader("Registro de notas")
    classes_df = query_df('SELECT id, class_name FROM classes')
    class_opt = st.selectbox("Seleccionar clase para anotar", options=[None] + list(classes_df.itertuples(index=False)), format_func=lambda x: x[1] if x else "-- Selecciona --")

    if class_opt:
        class_id = class_opt[0]
        students_df = query_df('SELECT id, student_code, first_name, last_name FROM students ORDER BY last_name, first_name')
        if students_df.empty:
            st.warning('No hay estudiantes registrados. Importe alumnos en Clases & Materias.')
        else:
            st.write('Ingrese una nota para un estudiante:')
            col1, col2, col3 = st.columns([2,1,1])
            with col1:
                student_sel = st.selectbox('Estudiante', options=students_df.itertuples(index=False), format_func=lambda x: f"{x[3]}, {x[2]}")
            with col2:
                grade = st.number_input('Nota', min_value=0.0, max_value=100.0, step=0.5)
            with col3:
                weight = st.number_input('Peso (coef.)', min_value=0.0, max_value=10.0, value=1.0, step=0.1)
            desc = st.text_input('Descripción (ej: Parcial 1)')
            if st.button('Guardar nota'):
                execute('INSERT INTO grades(class_id, student_id, date, grade, weight, description) VALUES (?, ?, ?, ?, ?, ?)',
                        (class_id, student_sel[0], datetime.now().isoformat(), grade, weight, desc))
                st.success('Nota registrada')

            st.markdown('---')
            st.write('Notas registradas para esta clase:')
            q = 'SELECT g.id, s.last_name || ", " || s.first_name AS estudiante, g.grade, g.weight, g.date, g.description FROM grades g JOIN students s ON g.student_id=s.id WHERE g.class_id=? ORDER BY g.date DESC'
            grades_df = query_df(q, params=(class_id,))
            if not grades_df.empty:
                st.dataframe(grades_df)
                # Cálculo promedio ponderado por estudiante
                st.markdown('**Promedio ponderado por estudiante**')
                avg_q = 'SELECT s.id, s.first_name, s.last_name, SUM(g.grade * g.weight) AS suma, SUM(g.weight) as pesos FROM grades g JOIN students s ON g.student_id=s.id WHERE g.class_id=? GROUP BY s.id'
                avg_df = query_df(avg_q, params=(class_id,))
                if not avg_df.empty:
                    avg_df['promedio'] = (avg_df['suma'] / avg_df['pesos']).round(2)
                    st.dataframe(avg_df[['first_name','last_name','promedio']])
            else:
                st.info('No hay notas registradas para esta clase.')

# ------------------ Página: Clases & Materias ------------------
elif page == "Clases & Materias":
    st.subheader('Clases y Materias')
    tab = st.tabs(["Materias", "Clases", "Importar alumnos (CSV)"])

    with tab[0]:
        st.markdown('### Materias')
        with st.form('form_materia'):
            name = st.text_input('Nombre de la materia')
            desc = st.text_area('Descripción (opcional)')
            if st.form_submit_button('Crear materia'):
                if name.strip() == '':
                    st.warning('Ingrese un nombre válido')
                else:
                    try:
                        execute('INSERT INTO subjects(name, description) VALUES (?, ?)', (name.strip(), desc.strip()))
                        st.success('Materia creada')
                    except sqlite3.IntegrityError:
                        st.error('Ya existe una materia con ese nombre')
        st.markdown('Materias existentes:')
        st.dataframe(query_df('SELECT * FROM subjects'))

    with tab[1]:
        st.markdown('### Clases')
        with st.form('form_clase'):
            sub_df = query_df('SELECT id, name FROM subjects')
            subject = st.selectbox('Materia', options=[None] + list(sub_df.itertuples(index=False)), format_func=lambda x: x[1] if x else '-- Selecciona --')
            teachers_df = query_df('SELECT id, name FROM teachers')
            teacher = st.selectbox('Profesor (opcional)', options=[None] + list(teachers_df.itertuples(index=False)), format_func=lambda x: x[1] if x else '-- Ninguno --')
            cname = st.text_input('Nombre de la clase (ej: 3er Año - A)')
            sched = st.text_input('Horario (opcional)')
            if st.form_submit_button('Crear clase'):
                subj_id = subject[0] if subject else None
                teacher_id = teacher[0] if teacher else None
                execute('INSERT INTO classes(subject_id, teacher_id, class_name, schedule) VALUES (?, ?, ?, ?)', (subj_id, teacher_id, cname, sched))
                st.success('Clase creada')
        st.markdown('Clases existentes:')
        st.dataframe(query_df('SELECT c.id, c.class_name, s.name AS subject, t.name AS teacher, c.schedule FROM classes c LEFT JOIN subjects s ON c.subject_id=s.id LEFT JOIN teachers t ON c.teacher_id=t.id'))

    with tab[2]:
        st.markdown('### Importar alumnos desde CSV')
        st.write('El CSV debe tener columnas: student_code, first_name, last_name')
        sample = pd.DataFrame([{'student_code':'A001','first_name':'Juan','last_name':'Pérez'},{'student_code':'A002','first_name':'María','last_name':'González'}])
        csv_buf = io.StringIO()
        sample.to_csv(csv_buf, index=False)
        csv_val = csv_buf.getvalue()
        b64 = base64.b64encode(csv_val.encode()).decode()
        st.markdown(f"[Descargar plantilla CSV](data:text/csv;base64,{b64})")
        cfile = st.file_uploader('Seleccionar CSV', type=['csv'])
        if st.button('Importar CSV'):
            if not cfile:
                st.warning('Suba un archivo CSV primero')
            else:
                df = pd.read_csv(cfile)
                required = {'student_code','first_name','last_name'}
                if not required.issubset(set(df.columns)):
                    st.error('CSV no tiene las columnas requeridas')
                else:
                    for i, r in df.iterrows():
                        try:
                            execute('INSERT INTO students(student_code, first_name, last_name) VALUES (?, ?, ?)', (str(r['student_code']), r['first_name'], r['last_name']))
                        except Exception:
                            pass
                    st.success('Alumnos importados (se ignoraron duplicados)')
        st.markdown('Alumnos actuales:')
        st.dataframe(query_df('SELECT * FROM students'))

# ------------------ Página: Profesores ------------------
elif page == "Profesores":
    st.subheader('Profesores')
    with st.form('form_prof'):
        name = st.text_input('Nombre completo')
        email = st.text_input('Email (opcional)')
        if st.form_submit_button('Agregar profesor'):
            if name.strip() == '':
                st.warning('Ingrese un nombre')
            else:
                try:
                    execute('INSERT INTO teachers(name, email) VALUES (?, ?)', (name.strip(), email.strip()))
                    st.success('Profesor agregado')
                except sqlite3.IntegrityError:
                    st.error('Ya existe ese profesor')
    st.markdown('Profesores registrados:')
    st.dataframe(query_df('SELECT * FROM teachers'))

# ------------------ Página: Ajustes / Exportar ------------------
elif page == "Ajustes / Exportar":
    st.subheader('Ajustes y exportaciones')
    st.markdown('Exportar tablas a CSV:')
    tables = ['students','teachers','subjects','classes','attendance','grades','exams']
    sel = st.selectbox('Tabla a exportar', options=tables)
    if st.button('Exportar CSV'):
        df = query_df(f'SELECT * FROM {sel}')
        csv = df.to_csv(index=False).encode('utf-8')
        b64 = base64.b64encode(csv).decode()
        href = f"data:file/csv;base64,{b64}"
        st.markdown(f"[Descargar {sel}.csv]({href})")

    st.markdown('---')
    st.write('Eliminar todos los datos (cuidado):')
    if st.button('Borrar BD (Elimina TODO)'):
        conn.close()
        try:
            DB_PATH.unlink()
        except Exception:
            pass
        st.experimental_rerun()

# ------------------ Fin ------------------

# Mensaje final de ayuda
st.sidebar.markdown('---')
st.sidebar.write('¿Necesitas ayuda?')
st.sidebar.write('• Si quieres que ajuste esto a tu institución, dime cuántas materias y alumnos tienes.')
st.sidebar.write('Juan E. Romero - Python Developer')


