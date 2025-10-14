import os
from fastapi import FastAPI, Request, Form, Depends
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from starlette.config import Config
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from jinja2 import Environment, FileSystemLoader, select_autoescape

from database import engine, SessionLocal, Base
from models import Employee, Result

# --- Config ---
config = Config(".env")
SESSION_SECRET = os.getenv("SESSION_SECRET") or config("SESSION_SECRET", default="dev-secret-change")
ADMIN_PASSWORD = "admin"

# --- App ---
app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET)
app.mount("/static", StaticFiles(directory="static"), name="static")

# --- DB init ---
Base.metadata.create_all(bind=engine)

# --- Templates ---
templates_env = Environment(
    loader=FileSystemLoader("templates"),
    autoescape=select_autoescape(["html", "xml"]),
)

DAYS_ORDER = ['ПТ','СБ','ПН','ВТ','СР','ЧТ']

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def fmt_short(n: int) -> str:
    if n is None:
        return "0"
    if abs(n) >= 1_000_000:
        v = n / 1_000_000
        return f"{int(v)}кк" if float(v).is_integer() else f"{v:.1f}кк"
    if abs(n) >= 1_000:
        v = n / 1_000
        return f"{int(v)}к" if float(v).is_integer() else f"{v:.1f}к"
    return str(n)

def parse_amount(s: str) -> int:
    s = (s or "").strip().lower().replace(" ", "")
    if not s:
        return 0
    mult = 1
    if s.endswith("кк") or s.endswith("kk"):
        mult = 1_000_000
        s = s[:-2]
    elif s.endswith("к") or s.endswith("k"):
        mult = 1_000
        s = s[:-1]
    s = s.replace("_", "").replace(",", ".")
    try:
        return int(float(s) * mult) if "." in s else int(s) * mult
    except ValueError:
        return 0

def is_authed(request: Request) -> bool:
    return request.session.get("authed", False) is True

def render_template(name: str, **ctx):
    template = templates_env.get_template(name)
    templates_env.globals["format_short"] = fmt_short
    return HTMLResponse(template.render(**ctx))

@app.get("/", response_class=HTMLResponse)
def index(request: Request, db: Session = Depends(get_db)):
    day_totals = {d: 0 for d in DAYS_ORDER}
    rows = db.execute(select(Result.day, func.sum(Result.amount)).group_by(Result.day)).all()
    for day, total in rows:
        if day in day_totals:
            day_totals[day] = total or 0

    grand_total = sum(day_totals.values())
    employees = db.execute(select(Employee).order_by(Employee.total_sum.desc())).scalars().all()

    return render_template(
        "index.html",
        request=request,
        day_totals=day_totals,
        grand_total=grand_total,
        employees=employees
    )

@app.get("/admin", response_class=HTMLResponse)
def admin_page(request: Request, db: Session = Depends(get_db)):
    if not is_authed(request):
        return render_template("admin.html", request=request, is_authed=False, error=None)
    employees = db.execute(select(Employee).order_by(Employee.name.asc())).scalars().all()
    return render_template("admin.html", request=request, is_authed=True, employees=employees)

@app.post("/admin/login")
def admin_login(request: Request, password: str = Form(...)):
    if password == ADMIN_PASSWORD:
        request.session["authed"] = True
        return RedirectResponse(url="/admin", status_code=303)
    return render_template("admin.html", request=request, is_authed=False, error="Неверный пароль")

@app.post("/admin/logout")
def admin_logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/admin", status_code=303)

@app.post("/admin/employee/add")
def employee_add(request: Request, name: str = Form(...), db: Session = Depends(get_db)):
    if not is_authed(request):
        return RedirectResponse(url="/admin", status_code=303)
    name = name.strip()
    if name:
        e = Employee(name=name)
        db.add(e)
        db.commit()
    return RedirectResponse(url="/admin", status_code=303)

@app.post("/admin/employee/delete")
def employee_delete(request: Request, id: int = Form(...), db: Session = Depends(get_db)):
    if not is_authed(request):
        return RedirectResponse(url="/admin", status_code=303)
    e = db.get(Employee, id)
    if e:
        db.delete(e)
        db.commit()
    return RedirectResponse(url="/admin", status_code=303)

@app.post("/admin/employee/rename")
def employee_rename(request: Request, id: int = Form(...), name: str = Form(...), db: Session = Depends(get_db)):
    if not is_authed(request):
        return RedirectResponse(url="/admin", status_code=303)
    e = db.get(Employee, id)
    if e and name.strip():
        e.name = name.strip()
        db.commit()
    return RedirectResponse(url="/admin", status_code=303)

@app.post("/admin/result/add")
def result_add(
    request: Request,
    employee_id: int = Form(...),
    day: str = Form(...),
    amount: str = Form(...),
    db: Session = Depends(get_db),
):
    if not is_authed(request):
        return RedirectResponse(url="/admin", status_code=303)
    e = db.get(Employee, employee_id)
    if not e:
        return RedirectResponse(url="/admin", status_code=303)

    day = day.strip().upper()
    if day not in DAYS_ORDER:
        day = DAYS_ORDER[0]

    val = parse_amount(amount)
    res = db.execute(
        select(Result).where(Result.employee_id == e.id, Result.day == day)
    ).scalars().first()
    if not res:
        res = Result(employee_id=e.id, day=day, amount=0)
        db.add(res)
        db.flush()

    res.amount += val
    db.flush()  # гарантируем, что SELECT ниже увидит новое значение

    total = db.execute(
        select(func.coalesce(func.sum(Result.amount), 0)).where(Result.employee_id == e.id)
    ).scalar_one()
    e.total_sum = int(total or 0)

    db.commit()
    return RedirectResponse(url="/admin", status_code=303)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=False)
