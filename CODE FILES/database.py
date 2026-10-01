"""SQLAlchemy models and DB helper functions (SQLite)."""
from typing import Optional

from sqlalchemy import Column, Float, ForeignKey, Integer, String, Text, create_engine
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

from app.config import DATABASE_URL

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True, autoincrement=False)
    name = Column(String(100), nullable=False)
    age = Column(Integer, nullable=False)
    weight = Column(Float, nullable=False)
    goal = Column(String(200), nullable=False)
    intensity = Column(String(20), nullable=False)
    schedule = Column(Integer, default=7)

    plan = relationship("WorkoutPlan", back_populates="user", uselist=False, cascade="all, delete-orphan")


class WorkoutPlan(Base):
    __tablename__ = "workout_plans"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    original_plan = Column(Text, nullable=False)
    updated_plan = Column(Text, nullable=True)

    user = relationship("User", back_populates="plan")


def init_db() -> None:
    Base.metadata.create_all(bind=engine)


def _user_dict(u: User) -> dict:
    return {"id": u.id, "name": u.name, "age": u.age, "weight": u.weight,
            "goal": u.goal, "intensity": u.intensity, "schedule": u.schedule}


def _plan_dict(p: WorkoutPlan) -> dict:
    return {"id": p.id, "user_id": p.user_id,
            "original_plan": p.original_plan, "updated_plan": p.updated_plan}


# ---- Users ----------------------------------------------------------------
def save_user(user_id: int, name: str, age: int, weight: float, goal: str, intensity: str) -> None:
    """Create the user, or update their details if the ID already exists."""
    db = SessionLocal()
    try:
        existing = db.query(User).filter_by(id=user_id).first()
        if existing:
            existing.name = name
            existing.age = age
            existing.weight = weight
            existing.goal = goal
            existing.intensity = intensity
        else:
            db.add(User(id=user_id, name=name, age=age, weight=weight,
                        goal=goal, intensity=intensity, schedule=7))
        db.commit()
    finally:
        db.close()


def get_user(user_id: int) -> Optional[dict]:
    db = SessionLocal()
    try:
        u = db.query(User).filter_by(id=user_id).first()
        return _user_dict(u) if u else None
    finally:
        db.close()


def get_all_users() -> list[dict]:
    db = SessionLocal()
    try:
        return [_user_dict(u) for u in db.query(User).order_by(User.id).all()]
    finally:
        db.close()


def delete_user(user_id: int) -> bool:
    db = SessionLocal()
    try:
        u = db.query(User).filter_by(id=user_id).first()
        if not u:
            return False
        db.delete(u)  # cascades to the user's plan
        db.commit()
        return True
    finally:
        db.close()


# ---- Plans ----------------------------------------------------------------
def save_plan(user_id: int, plan: str) -> None:
    """Store a newly generated plan. A re-generated plan replaces the old one
    (and clears any previous feedback-updated version)."""
    db = SessionLocal()
    try:
        workout = db.query(WorkoutPlan).filter_by(user_id=user_id).first()
        if workout:
            workout.original_plan = plan
            workout.updated_plan = None
        else:
            db.add(WorkoutPlan(user_id=user_id, original_plan=plan))
        db.commit()
    finally:
        db.close()


def update_plan(user_id: int, updated_text: str) -> None:
    """Store the feedback-updated plan (original is preserved)."""
    db = SessionLocal()
    try:
        workout = db.query(WorkoutPlan).filter_by(user_id=user_id).first()
        if workout:
            workout.updated_plan = updated_text
            db.commit()
    finally:
        db.close()


def get_original_plan(user_id: int) -> Optional[str]:
    db = SessionLocal()
    try:
        w = db.query(WorkoutPlan).filter_by(user_id=user_id).first()
        return w.original_plan if w else None
    finally:
        db.close()


def get_current_plan(user_id: int) -> Optional[str]:
    """Latest version of the plan: the updated one if it exists, else the original."""
    db = SessionLocal()
    try:
        w = db.query(WorkoutPlan).filter_by(user_id=user_id).first()
        if not w:
            return None
        return w.updated_plan or w.original_plan
    finally:
        db.close()


def get_all_plans() -> list[dict]:
    db = SessionLocal()
    try:
        return [_plan_dict(p) for p in db.query(WorkoutPlan).all()]
    finally:
        db.close()
