"""All FitBuddy routes (HTML pages + small JSON API)."""
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError

from app import database as db
from app.config import TEMPLATE_DIR
from app.gemini_client import GeminiError
from app.gemini_flash_generator import generate_nutrition_tip_with_flash
from app.gemini_generator import generate_workout_gemini
from app.nutrition import fallback_tip
from app.schemas import FeedbackRequest, UserInput
from app.updated_plan import update_workout_plan

router = APIRouter()
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))


def _render(request: Request, name: str, context: dict | None = None, status_code: int = 200):
    return templates.TemplateResponse(request=request, name=name, context=context or {}, status_code=status_code)


def _safe_tip(goal: str, age: int | None = None) -> str:
    """Nutrition tip via Gemini Flash; never fails the whole request."""
    try:
        return generate_nutrition_tip_with_flash(goal, age)
    except GeminiError:
        return fallback_tip(goal)


def _validation_message(exc: ValidationError) -> str:
    parts = []
    for err in exc.errors():
        field = ".".join(str(p) for p in err["loc"])
        parts.append(f"{field}: {err['msg']}")
    return "Please check your input - " + "; ".join(parts)


def _result_context(user: dict, plan: str, tip: str, original_plan: str | None = None,
                    message: str | None = None, error: str | None = None) -> dict:
    return {
        "username": user["name"], "user_id": user["id"], "age": user["age"],
        "weight": user["weight"], "goal": user["goal"], "intensity": user["intensity"],
        "workout_plan": plan, "nutrition_tip": tip,
        "original_plan": original_plan, "message": message, "error": error,
    }


# ---------------------------------------------------------------- Home
@router.get("/", response_class=HTMLResponse)
def home(request: Request):
    return _render(request, "index.html", {"error": None, "form": {}})


# ------------------------------------------------------ Generate workout
@router.post("/generate-workout", response_class=HTMLResponse)
def generate_workout(
    request: Request,
    username: str = Form(...),
    user_id: str = Form(...),
    age: str = Form(...),
    weight: str = Form(...),
    goal: str = Form(...),
    intensity: str = Form(...),
):
    form = {"username": username, "user_id": user_id, "age": age,
            "weight": weight, "goal": goal, "intensity": intensity}
    try:
        data = UserInput(username=username, user_id=user_id, age=age,
                         weight=weight, goal=goal, intensity=intensity)
    except ValidationError as exc:
        return _render(request, "index.html", {"error": _validation_message(exc), "form": form}, 422)

    try:
        plan = generate_workout_gemini({
            "name": data.username, "age": data.age, "weight": data.weight,
            "goal": data.goal, "intensity": data.intensity,
        })
    except GeminiError as exc:
        return _render(request, "index.html", {"error": str(exc), "form": form}, 502)

    tip = _safe_tip(data.goal, data.age)

    # Persist only after the AI call succeeded, so failures never store junk.
    db.save_user(data.user_id, data.username, data.age, data.weight, data.goal, data.intensity)
    db.save_plan(data.user_id, plan)

    user = db.get_user(data.user_id)
    return _render(request, "result.html", _result_context(user, plan, tip))


# ------------------------------------------------------- Submit feedback
@router.post("/submit-feedback", response_class=HTMLResponse)
def submit_feedback(request: Request, user_id: str = Form(...), feedback: str = Form(...)):
    try:
        data = FeedbackRequest(user_id=user_id, feedback=feedback)
    except ValidationError as exc:
        return _render(request, "index.html", {"error": _validation_message(exc), "form": {}}, 422)

    user = db.get_user(data.user_id)
    current_plan = db.get_current_plan(data.user_id)
    if not user or not current_plan:
        return _render(request, "index.html", {
            "error": f"No plan found for User ID {data.user_id}. Please generate a plan first.",
            "form": {}}, 404)

    original = db.get_original_plan(data.user_id)
    try:
        # Feedback refines the latest version, so successive feedback accumulates.
        revised = update_workout_plan(current_plan, data.feedback)
    except GeminiError as exc:
        ctx = _result_context(user, current_plan, _safe_tip(user["goal"], user["age"]), error=str(exc))
        return _render(request, "result.html", ctx, 502)

    db.update_plan(data.user_id, revised)
    ctx = _result_context(user, revised, _safe_tip(user["goal"], user["age"]), original_plan=original,
                          message="Your workout plan has been updated based on your feedback!")
    return _render(request, "result.html", ctx)


# ---------------------------------------------------------- Admin views
@router.get("/view-all-users", response_class=HTMLResponse)
def view_all_users(request: Request):
    plans = {p["user_id"]: p for p in db.get_all_plans()}
    users = []
    for u in db.get_all_users():
        p = plans.get(u["id"], {})
        users.append({**u, "original_plan": p.get("original_plan"), "updated_plan": p.get("updated_plan")})
    return _render(request, "all_users.html", {"users": users})


@router.post("/delete-user/{user_id}")
def delete_user(user_id: int):
    db.delete_user(user_id)
    return RedirectResponse(url="/view-all-users", status_code=303)


# ------------------------------------------------------------ JSON API
@router.get("/api/users")
def api_users():
    plans = {p["user_id"]: p for p in db.get_all_plans()}
    return JSONResponse([{**u, "plan": plans.get(u["id"])} for u in db.get_all_users()])


@router.get("/health")
def health():
    return {"status": "ok"}
