import base64, hashlib, hmac, secrets
from datetime import timedelta
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session as DBSession
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from cryptography.fernet import Fernet
from .database import get_db
from .models import User, Session, Membership, Church, RateLimit, Block, now
from . import config

def digest(value): return hashlib.sha256(value.encode()).hexdigest()
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError,InvalidHashError
hasher=PasswordHasher(time_cost=3,memory_cost=65536,parallelism=2)
DUMMY_PASSWORD_HASH=hasher.hash(secrets.token_urlsafe(32))
def password_hash(password): return hasher.hash(password)
def password_ok(password,stored):
    try:return hasher.verify(stored,password)
    except (VerificationError,InvalidHashError):return False
fernet = Fernet(base64.urlsafe_b64encode(hashlib.sha256(config.APP_SECRET.encode()).digest()))
def invite_code(): return ''.join(secrets.choice('ABCDEFGHJKLMNPQRSTUVWXYZ23456789') for _ in range(12))
def normalize_code(code): return code.replace('-','').replace(' ','').strip().upper()
def set_code(church):
    code=invite_code()
    church.code_hash=digest(code)
    church.code_encrypted=fernet.encrypt(code.encode()).decode()
    return code

def rate_limit(db, key, limit=10, seconds=900):
    hashed=digest(key)
    row=db.scalar(select(RateLimit).where(RateLimit.key==hashed).with_for_update())
    if not row:
        row=RateLimit(key=hashed,count=0,resets_at=now()+timedelta(seconds=seconds)); db.add(row)
    if row.resets_at < now(): row.count=0; row.resets_at=now()+timedelta(seconds=seconds)
    row.count += 1
    try:
        db.commit() # Failed authentication must still consume its budget.
    except IntegrityError:
        # Another request created this bucket first. Count this attempt too.
        db.rollback()
        row=db.scalar(select(RateLimit).where(RateLimit.key==hashed).with_for_update())
        row.count += 1
        db.commit()
    if row.count > limit: raise HTTPException(429,'Too many attempts. Please try again later.')

def current_user(request: Request, db: DBSession=Depends(get_db)):
    bearer=request.headers.get('authorization','')
    token=bearer[7:] if bearer.startswith('Bearer ') else request.cookies.get('village_session','')
    if not token: raise HTTPException(401,'Please sign in.')
    session=db.get(Session,digest(token))
    if not session or session.expires_at < now(): raise HTTPException(401,'Your session has expired. Please sign in again.')
    user=db.get(User,session.user_id)
    if not user: raise HTTPException(401,'Please sign in.')
    return user

def member(church_id, db, user, admin=False):
    membership=db.scalar(select(Membership).where(Membership.church_id==church_id,Membership.user_id==user.id,Membership.status=='approved'))
    if not membership: raise HTTPException(403,'Approved church membership is required.')
    if admin and membership.role not in ('admin','owner'): raise HTTPException(403,'Church administrator access is required.')
    return membership

def can_manage(item,db,user):
    m=member(item.church_id,db,user)
    if item.created_by != user.id and m.role not in ('admin','owner'): raise HTTPException(403,'Only the organizer or an administrator can change this.')
    return m

def blocked_ids(db,user):
    # Symmetric exclusion protects both sides of a block.
    blocks=db.scalars(select(Block).where((Block.user_id==user.id)|(Block.blocked_id==user.id))).all()
    return {b.blocked_id if b.user_id==user.id else b.user_id for b in blocks}

def scoped(model,item_id,church_id,db,user,lock=False):
    member(church_id,db,user)
    query=select(model).where(model.id==item_id,model.church_id==church_id)
    if lock: query=query.with_for_update()
    item=db.scalar(query)
    if not item or (hasattr(item,'created_by') and item.created_by in blocked_ids(db,user)):
        raise HTTPException(404,'Item not found in your church.')
    return item
