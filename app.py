from flask import Flask,render_template,request,redirect,url_for,session,make_response
import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo

app=Flask(__name__)

app.secret_key="nova-secret-key"

DATABASE="database.db"


def get_db():
    conn=sqlite3.connect(DATABASE)
    conn.row_factory=sqlite3.Row
    return conn


def init_db():
    conn=get_db()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            user_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            status TEXT NOT NULL DEFAULT 'Pending',
            priority TEXT NOT NULL DEFAULT 'Medium',
            due_date TEXT,
            project_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES projects(id)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS project_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(project_id,user_id),
            FOREIGN KEY (project_id) REFERENCES projects(id),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT NOT NULL,
            task_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (task_id) REFERENCES tasks(id),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    conn.commit()
    conn.close()


@app.after_request
def add_cache_control(response):

    if request.endpoint in ["dashboard","project"]:
        response.headers["Cache-Control"]="no-cache,no-store,must-revalidate"
        response.headers["Pragma"]="no-cache"
        response.headers["Expires"]="0"

    return response


@app.route("/")
def home():
    return redirect(url_for("login"))


@app.route("/register",methods=["GET","POST"])
def register():

    if request.method=="POST":

        username=request.form["username"]
        email=request.form["email"]
        password=request.form["password"]

        conn=get_db()

        try:
            conn.execute(
                "INSERT INTO users (username,email,password) VALUES (?,?,?)",
                (username,email,password)
            )

            conn.commit()

        except sqlite3.IntegrityError:
            conn.close()
            return "Email already registered!"

        conn.close()

        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login",methods=["GET","POST"])
def login():

    if request.method=="POST":

        email=request.form["email"]
        password=request.form["password"]

        conn=get_db()

        user=conn.execute(
            "SELECT * FROM users WHERE email=? AND password=?",
            (email,password)
        ).fetchone()

        conn.close()

        if user:
            session["user_id"]=user["id"]
            session["username"]=user["username"]

            return redirect(url_for("dashboard"))

        return render_template(
            "login.html",
            error="Invalid email or password!"
        )

    return render_template("login.html")


@app.route("/dashboard")
def dashboard():

    if "user_id" not in session:
        return redirect(url_for("login"))

    conn=get_db()

    projects=conn.execute(
        """
        SELECT DISTINCT projects.*
        FROM projects
        LEFT JOIN project_members
        ON projects.id=project_members.project_id
        WHERE projects.user_id=?
        OR project_members.user_id=?
        ORDER BY projects.created_at DESC
        """,
        (session["user_id"],session["user_id"])
    ).fetchall()

    conn.close()

    response=make_response(
        render_template(
            "dashboard.html",
            username=session["username"],
            projects=projects
        )
    )

    return response


@app.route("/create-project",methods=["POST"])
def create_project():

    if "user_id" not in session:
        return redirect(url_for("login"))

    name=request.form["name"]
    description=request.form["description"]

    created_at=datetime.now(
        ZoneInfo("Asia/Kolkata")
    ).strftime("%Y-%m-%d %H:%M:%S")

    conn=get_db()

    conn.execute(
        """
        INSERT INTO projects
        (name,description,user_id,created_at)
        VALUES (?,?,?,?)
        """,
        (name,description,session["user_id"],created_at)
    )

    conn.commit()
    conn.close()

    return redirect(url_for("dashboard"))


@app.route("/project/<int:project_id>")
def project(project_id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    conn=get_db()

    project=conn.execute(
        """
        SELECT projects.*,users.username AS owner_name
        FROM projects
        JOIN users ON projects.user_id=users.id
        LEFT JOIN project_members
        ON projects.id=project_members.project_id
        WHERE projects.id=?
        AND (
            projects.user_id=?
            OR project_members.user_id=?
        )
        """,
        (project_id,session["user_id"],session["user_id"])
    ).fetchone()

    if project is None:
        conn.close()
        return "Project not found!"

    tasks=conn.execute(
        "SELECT * FROM tasks WHERE project_id=? ORDER BY created_at DESC",
        (project_id,)
    ).fetchall()

    members=conn.execute(
        """
        SELECT users.id,users.username,users.email
        FROM project_members
        JOIN users ON project_members.user_id=users.id
        WHERE project_members.project_id=?
        ORDER BY users.username
        """,
        (project_id,)
    ).fetchall()

    comments=conn.execute(
        """
        SELECT comments.*,users.username
        FROM comments
        JOIN users ON comments.user_id=users.id
        JOIN tasks ON comments.task_id=tasks.id
        WHERE tasks.project_id=?
        ORDER BY comments.created_at ASC
        """,
        (project_id,)
    ).fetchall()

    total_tasks=len(tasks)

    completed_tasks=0

    for task in tasks:
        if task["status"]=="Completed":
            completed_tasks+=1

    if total_tasks>0:
        progress=int((completed_tasks/total_tasks)*100)
    else:
        progress=0

    conn.close()

    response=make_response(
        render_template(
            "project.html",
            project=project,
            tasks=tasks,
            members=members,
            comments=comments,
            progress=progress,
            total_tasks=total_tasks,
            completed_tasks=completed_tasks
        )
    )

    return response


@app.route("/create-task/<int:project_id>",methods=["POST"])
def create_task(project_id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    conn=get_db()

    project=conn.execute(
        "SELECT * FROM projects WHERE id=? AND user_id=?",
        (project_id,session["user_id"])
    ).fetchone()

    if project is None:
        conn.close()
        return "Project not found!"

    title=request.form["title"]
    description=request.form["description"]
    status=request.form["status"]
    priority=request.form["priority"]
    due_date=request.form["due_date"]

    conn.execute(
        """
        INSERT INTO tasks
        (title,description,status,priority,due_date,project_id)
        VALUES (?,?,?,?,?,?)
        """,
        (title,description,status,priority,due_date,project_id)
    )

    conn.commit()
    conn.close()

    return redirect(url_for("project",project_id=project_id))


@app.route("/add-member/<int:project_id>",methods=["POST"])
def add_member(project_id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    email=request.form["email"]

    conn=get_db()

    project=conn.execute(
        "SELECT * FROM projects WHERE id=? AND user_id=?",
        (project_id,session["user_id"])
    ).fetchone()

    if project is None:
        conn.close()
        return "Project not found!"

    user=conn.execute(
        "SELECT * FROM users WHERE email=?",
        (email,)
    ).fetchone()

    if user is None:
        conn.close()
        return "User not found!"

    if user["id"]==session["user_id"]:
        conn.close()
        return "You are already the project owner!"

    existing_member=conn.execute(
        "SELECT * FROM project_members WHERE project_id=? AND user_id=?",
        (project_id,user["id"])
    ).fetchone()

    if existing_member:
        conn.close()
        return "User is already a member!"

    conn.execute(
        "INSERT INTO project_members (project_id,user_id) VALUES (?,?)",
        (project_id,user["id"])
    )

    conn.commit()
    conn.close()

    return redirect(url_for("project",project_id=project_id))


@app.route("/add-comment/<int:task_id>",methods=["POST"])
def add_comment(task_id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    content=request.form["content"]

    conn=get_db()

    task=conn.execute(
        """
        SELECT tasks.*,projects.user_id
        FROM tasks
        JOIN projects ON tasks.project_id=projects.id
        LEFT JOIN project_members
        ON projects.id=project_members.project_id
        WHERE tasks.id=?
        AND (
            projects.user_id=?
            OR project_members.user_id=?
        )
        """,
        (task_id,session["user_id"],session["user_id"])
    ).fetchone()

    if task is None:
        conn.close()
        return "Task not found!"

    if content.strip()=="":
        conn.close()
        return "Comment cannot be empty!"

    conn.execute(
        """
        INSERT INTO comments
        (content,task_id,user_id)
        VALUES (?,?,?)
        """,
        (content,task_id,session["user_id"])
    )

    conn.commit()

    project_id=task["project_id"]

    conn.close()

    return redirect(url_for("project",project_id=project_id))


@app.route("/update-task/<int:task_id>",methods=["POST"])
def update_task(task_id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    status=request.form["status"]

    conn=get_db()

    task=conn.execute(
        """
        SELECT tasks.*,projects.user_id
        FROM tasks
        JOIN projects ON tasks.project_id=projects.id
        WHERE tasks.id=? AND projects.user_id=?
        """,
        (task_id,session["user_id"])
    ).fetchone()

    if task is None:
        conn.close()
        return "Task not found!"

    conn.execute(
        "UPDATE tasks SET status=? WHERE id=?",
        (status,task_id)
    )

    conn.commit()

    project_id=task["project_id"]

    conn.close()

    return redirect(url_for("project",project_id=project_id))


@app.route("/delete-task/<int:task_id>",methods=["POST"])
def delete_task(task_id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    conn=get_db()

    task=conn.execute(
        """
        SELECT tasks.*,projects.user_id
        FROM tasks
        JOIN projects ON tasks.project_id=projects.id
        WHERE tasks.id=? AND projects.user_id=?
        """,
        (task_id,session["user_id"])
    ).fetchone()

    if task is None:
        conn.close()
        return "Task not found!"

    project_id=task["project_id"]

    conn.execute(
        "DELETE FROM comments WHERE task_id=?",
        (task_id,)
    )

    conn.execute(
        "DELETE FROM tasks WHERE id=?",
        (task_id,)
    )

    conn.commit()
    conn.close()

    return redirect(url_for("project",project_id=project_id))


@app.route("/delete-project/<int:project_id>",methods=["POST"])
def delete_project(project_id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    conn=get_db()

    project=conn.execute(
        "SELECT * FROM projects WHERE id=? AND user_id=?",
        (project_id,session["user_id"])
    ).fetchone()

    if project is None:
        conn.close()
        return "Project not found!"

    task_ids=conn.execute(
        "SELECT id FROM tasks WHERE project_id=?",
        (project_id,)
    ).fetchall()

    for task in task_ids:
        conn.execute(
            "DELETE FROM comments WHERE task_id=?",
            (task["id"],)
        )

    conn.execute(
        "DELETE FROM tasks WHERE project_id=?",
        (project_id,)
    )

    conn.execute(
        "DELETE FROM project_members WHERE project_id=?",
        (project_id,)
    )

    conn.execute(
        "DELETE FROM projects WHERE id=?",
        (project_id,)
    )

    conn.commit()
    conn.close()

    return redirect(url_for("dashboard"))


@app.route("/logout")
def logout():

    session.clear()

    response=make_response(
        redirect(url_for("login"))
    )

    response.headers["Cache-Control"]="no-cache,no-store,must-revalidate"
    response.headers["Pragma"]="no-cache"
    response.headers["Expires"]="0"

    return response


if __name__=="__main__":
    init_db()
    app.run(debug=True)
