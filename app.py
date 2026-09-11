import csv
import io
import os
import sqlite3
import uuid
from datetime import datetime
from flask import Flask, Response, flash, jsonify, redirect, render_template, request, session, url_for

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("BJC_ONLINE_DB", os.path.join(BASE_DIR, "online_registrations.db"))
ADMIN_PASSWORD = os.environ.get("BJC_ADMIN_PASSWORD", "BJC2026")
SECRET_KEY = os.environ.get("BJC_SECRET_KEY", "change-this-secret-before-public-use")
app = Flask(__name__)
app.secret_key = SECRET_KEY
AGE_GROUPS = ["U07", "U09", "U11", "U13", "U15", "U17", "U19"]

def db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con

def init_db():
    with db() as con:
        con.execute("""CREATE TABLE IF NOT EXISTS submissions (id INTEGER PRIMARY KEY AUTOINCREMENT,batch_id TEXT NOT NULL,school TEXT NOT NULL,contact TEXT,email TEXT,phone TEXT,tournament TEXT,tournament_year INTEGER,chessa_id TEXT,surname TEXT NOT NULL,first_name TEXT NOT NULL,birth_date TEXT NOT NULL,gender TEXT NOT NULL,grade TEXT,age_group TEXT,section TEXT,notes TEXT,submitted_at TEXT NOT NULL,UNIQUE(batch_id,surname,first_name,birth_date))""")
init_db()

def calculate_age_group(dob, year):
    try: age=int(year)-datetime.strptime(dob,"%Y-%m-%d").year
    except Exception: return "INELIGIBLE"
    if age<=7:return "U07"
    if age<=9:return "U09"
    if age<=11:return "U11"
    if age<=13:return "U13"
    if age<=15:return "U15"
    if age<=17:return "U17"
    if age<=19:return "U19"
    return "INELIGIBLE"

def require_admin(): return session.get("admin") is True

@app.route("/",methods=["GET","POST"])
def register():
    if request.method=="POST":
        school=request.form.get("school","").strip(); contact=request.form.get("contact","").strip(); email=request.form.get("email","").strip(); phone=request.form.get("phone","").strip(); tournament=request.form.get("tournament","").strip()
        try: year=int(request.form.get("tournament_year","2026"))
        except ValueError: year=2026
        surnames=request.form.getlist("surname[]"); firsts=request.form.getlist("first_name[]"); dobs=request.form.getlist("birth_date[]"); genders=request.form.getlist("gender[]"); grades=request.form.getlist("grade[]"); ids=request.form.getlist("chessa_id[]"); notes=request.form.getlist("notes[]")
        if not school or not contact: flash("School name and contact teacher/coach are required."); return redirect(url_for("register"))
        batch_id=uuid.uuid4().hex[:12]; saved=0
        with db() as con:
            for i in range(max(len(surnames),len(firsts),len(dobs))):
                surname=surnames[i].strip() if i<len(surnames) else ""; first=firsts[i].strip() if i<len(firsts) else ""; dob=dobs[i].strip() if i<len(dobs) else ""; gender=genders[i].strip() if i<len(genders) else ""
                if not surname and not first: continue
                if not surname or not first or not dob or gender not in ("Male","Female"): flash(f"Player row {i+1} is incomplete. Surname, first name, date of birth and gender are required."); return redirect(url_for("register"))
                age_group=calculate_age_group(dob,year); section=age_group
                if age_group!="INELIGIBLE": section += " Girls" if gender=="Female" else " Boys"
                con.execute("INSERT OR IGNORE INTO submissions (batch_id,school,contact,email,phone,tournament,tournament_year,chessa_id,surname,first_name,birth_date,gender,grade,age_group,section,notes,submitted_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(batch_id,school,contact,email,phone,tournament,year,ids[i].strip() if i<len(ids) else "",surname,first,dob,gender,grades[i].strip() if i<len(grades) else "",age_group,section,notes[i].strip() if i<len(notes) else "",datetime.now().strftime("%Y-%m-%d %H:%M:%S"))); saved+=1
        if saved==0: flash("No player rows were completed."); return redirect(url_for("register"))
        return render_template("success.html",school=school,count=saved,batch_id=batch_id)
    return render_template("register.html",year=2026)

@app.route("/admin/login",methods=["GET","POST"])
def admin_login():
    if request.method=="POST":
        if request.form.get("password")==ADMIN_PASSWORD: session["admin"]=True; return redirect(url_for("admin"))
        flash("Incorrect password.")
    return render_template("admin_login.html")

@app.route("/admin/logout")
def admin_logout(): session.clear(); return redirect(url_for("register"))

@app.route("/admin")
def admin():
    if not require_admin(): return redirect(url_for("admin_login"))
    section=request.args.get("section","ALL")
    with db() as con:
        rows=con.execute("SELECT * FROM submissions ORDER BY section,school,surname,first_name").fetchall() if section=="ALL" else con.execute("SELECT * FROM submissions WHERE section=? ORDER BY school,surname,first_name",(section,)).fetchall(); summary=con.execute("SELECT section,COUNT(*) c FROM submissions GROUP BY section ORDER BY section").fetchall()
    sections=["ALL"]+[f"{g} Boys" for g in AGE_GROUPS]+[f"{g} Girls" for g in AGE_GROUPS]+["INELIGIBLE"]
    return render_template("admin.html",rows=rows,summary=summary,sections=sections,selected=section)

@app.route("/api/registrations")
def api_registrations():
    supplied=request.headers.get("X-BJC-Admin-Password","")
    if not supplied or supplied!=ADMIN_PASSWORD:
        return jsonify({"ok":False,"error":"Unauthorized"}),401
    with db() as con: rows=con.execute("SELECT * FROM submissions ORDER BY id").fetchall()
    fields=["id","batch_id","school","contact","email","phone","tournament","tournament_year","chessa_id","surname","first_name","birth_date","gender","grade","age_group","section","notes","submitted_at"]
    return jsonify({"ok":True,"count":len(rows),"registrations":[{k:r[k] for k in fields} for r in rows]})

@app.route("/admin/export.csv")
def export_csv():
    if not require_admin(): return redirect(url_for("admin_login"))
    with db() as con: rows=con.execute("SELECT * FROM submissions ORDER BY section,school,surname,first_name").fetchall()
    out=io.StringIO(); w=csv.writer(out); w.writerow(["School Name","Contact Teacher / Coach","Email Address","Cell Number","Tournament / Event","Tournament Year","CHESSA ID","Surname","First Name","Date of Birth","Gender","Grade","Age Group","Section","Notes"])
    for r in rows: w.writerow([r["school"],r["contact"],r["email"],r["phone"],r["tournament"],r["tournament_year"],r["chessa_id"],r["surname"],r["first_name"],r["birth_date"],r["gender"],r["grade"],r["age_group"],r["section"],r["notes"]])
    data="\ufeff"+out.getvalue(); filename=f"BJC_ONLINE_REGISTRATIONS_{datetime.now():%Y%m%d_%H%M}.csv"; return Response(data,mimetype="text/csv",headers={"Content-Disposition":f"attachment; filename={filename}"})

@app.route("/admin/clear",methods=["POST"])
def clear_all():
    if not require_admin(): return redirect(url_for("admin_login"))
    with db() as con: con.execute("DELETE FROM submissions")
    flash("All online registrations have been cleared."); return redirect(url_for("admin"))

if __name__=="__main__": app.run(host="0.0.0.0",port=int(os.environ.get("PORT","5000")),debug=False)
