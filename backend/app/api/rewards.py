"""R4 rewards: balance, earn history with unlock dates, redeem."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import get_db
from ..events import emit
from ..models import User
from ..security import current_user
from ..services import rewards

router = APIRouter(prefix="/rewards", tags=["rewards"])


class RedeemIn(BaseModel):
    offer_id: str = Field(max_length=40)


@router.get("")
def summary(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return rewards.summary(db, user)


@router.post("/redeem", status_code=201)
def redeem(body: RedeemIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    entry = rewards.redeem(db, user, body.offer_id)
    emit(db, "reward.redeemed", user.id, "reward", entry.id, {"offer": body.offer_id, "points": -entry.points})
    db.commit()
    return {"voucher_code": entry.voucher_code, "title": entry.note, "points": -entry.points,
            "summary": rewards.summary(db, user)}
