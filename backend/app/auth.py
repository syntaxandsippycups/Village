import secrets
from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select, delete
from sqlalchemy.orm import Session as DBSession
from .database import get_db
from .models import User, Session, AuthToken, Membership, Church, MealSlot, Mail, Notification, Device, now
from .schemas import Register, Login, EmailRequest, TokenRequest, Reset, Profile, Preferences, DeleteAccount
from .security import current_user, digest, password_hash, password_ok, rate_limit, DUMMY_PASSWORD_HASH
from .notifications import queue_mail
from . import config
router=APIRouter(prefix='/api/auth',tags=['Account'])

def private_profile(user):
    return {k:getattr(user,k) for k in ['id','email','name','phone','address','household','bio','skills','resources','groups','available','privacy','preferences','verified']}

def token_mail(db,user,purpose):
    token=secrets.token_urlsafe(32)
    db.execute(delete(AuthToken).where(AuthToken.user_id==user.id,AuthToken.purpose==purpose))
    db.add(AuthToken(id=digest(token),user_id=user.id,purpose=purpose,expires_at=now()+timedelta(hours=1)))
    url=f'{config.WEB_URL}/?action={purpose}&token={token}'
    queue_mail(db,user.email,'Verify your Village email' if purpose=='verify' else 'Reset your Village password',f'Open this link within one hour:\n{url}\n\nIf you did not request this, ignore this email.')

def issue_session(db,user,response,native=False):
    token=secrets.token_urlsafe(48)
    db.add(Session(id=digest(token),user_id=user.id,expires_at=now()+timedelta(days=14)))
    response.set_cookie('village_session',token,max_age=14*86400,httponly=True,secure=config.PRODUCTION,samesite='lax',path='/')
    return {'user':private_profile(user),**({'token':token} if native else {})}

@router.post('/register',status_code=201)
def register(data:Register,request:Request,db:DBSession=Depends(get_db)):
    rate_limit(db,'register-ip:'+request.client.host,1000,3600)
    rate_limit(db,'register-email:'+str(data.email).lower(),3,3600)
    email=str(data.email).lower()
    if db.scalar(select(User).where(User.email==email)): raise HTTPException(409,'An account with that email already exists. Try signing in or resetting your password.')
    user=User(email=email,name=data.name,password_hash=password_hash(data.password),verified=not config.VERIFY_EMAIL)
    db.add(user); db.flush()
    if config.VERIFY_EMAIL: token_mail(db,user,'verify')
    db.commit()
    return {'message':'Check your email to verify your account, then sign in.' if config.VERIFY_EMAIL else 'Account created. You can sign in now.'}

@router.post('/login')
def login(data:Login,request:Request,response:Response,db:DBSession=Depends(get_db)):
    rate_limit(db,'login:'+request.client.host+':'+str(data.email).lower(),10)
    user=db.scalar(select(User).where(User.email==str(data.email).lower()))
    dummy=DUMMY_PASSWORD_HASH
    valid=password_ok(data.password,user.password_hash if user else dummy)
    if not user or not valid: raise HTTPException(401,'Email or password is incorrect.')
    if not user.verified: raise HTTPException(403,'Please verify your email before signing in.')
    result=issue_session(db,user,response,data.native); db.commit(); return result

@router.get('/me')
def me(user:User=Depends(current_user)): return private_profile(user)

@router.post('/logout')
def logout(request:Request,response:Response,user:User=Depends(current_user),db:DBSession=Depends(get_db)):
    token=request.headers.get('authorization','')[7:] if request.headers.get('authorization','').startswith('Bearer ') else request.cookies.get('village_session','')
    db.execute(delete(Session).where(Session.id==digest(token)))
    # A device should stop receiving this account's push after logout.
    device=request.headers.get('x-device-token')
    if device: db.execute(delete(Device).where(Device.user_id==user.id,Device.token==device))
    db.commit(); response.delete_cookie('village_session',path='/'); return {'ok':True}

@router.post('/forgot-password')
@router.post('/resend-verification')
def forgot(data:EmailRequest,request:Request,db:DBSession=Depends(get_db)):
    rate_limit(db,'mail:'+request.client.host,5,3600)
    user=db.scalar(select(User).where(User.email==str(data.email).lower()))
    purpose='verify' if request.url.path.endswith('resend-verification') else 'reset'
    if user and (purpose=='reset' or not user.verified): token_mail(db,user,purpose)
    db.commit(); return {'message':'If an eligible account exists, a link has been sent.'}

@router.post('/verify')
def verify(data:TokenRequest,db:DBSession=Depends(get_db)):
    row=db.get(AuthToken,digest(data.token))
    if not row or row.purpose!='verify' or row.expires_at<now(): raise HTTPException(400,'Verification link expired or invalid.')
    db.get(User,row.user_id).verified=True; db.delete(row); db.commit(); return {'message':'Email verified. You can sign in.'}

@router.post('/reset')
def reset(data:Reset,db:DBSession=Depends(get_db)):
    row=db.get(AuthToken,digest(data.token))
    if not row or row.purpose!='reset' or row.expires_at<now(): raise HTTPException(400,'Reset link expired or invalid.')
    db.get(User,row.user_id).password_hash=password_hash(data.password)
    db.execute(delete(Session).where(Session.user_id==row.user_id)); db.delete(row); db.commit()
    return {'message':'Password updated. Sign in again.'}

@router.put('/profile')
def profile(data:Profile,user:User=Depends(current_user),db:DBSession=Depends(get_db)):
    for k,v in data.model_dump().items(): setattr(user,k,v)
    db.commit(); return private_profile(user)

@router.put('/preferences')
def preferences(data:Preferences,user:User=Depends(current_user),db:DBSession=Depends(get_db)):
    user.preferences=data.model_dump(); db.commit(); return private_profile(user)

@router.get('/export')
def export(user:User=Depends(current_user),db:DBSession=Depends(get_db)):
    from .models import Event,Need,MealTrain,RSVP,Volunteer,Comment
    from .care import serialize
    return {'profile':private_profile(user),'memberships':[serialize(m) for m in db.scalars(select(Membership).where(Membership.user_id==user.id))],
        'events':[serialize(x) for x in db.scalars(select(Event).where(Event.created_by==user.id))],
        'needs':[serialize(x) for x in db.scalars(select(Need).where(Need.created_by==user.id))],
        'meal_trains':[serialize(x) for x in db.scalars(select(MealTrain).where(MealTrain.created_by==user.id))],
        'meal_commitments':[serialize(x) for x in db.scalars(select(MealSlot).where(MealSlot.user_id==user.id))],
        'rsvps':[serialize(x) for x in db.scalars(select(RSVP).where(RSVP.user_id==user.id))],
        'volunteering':[serialize(x) for x in db.scalars(select(Volunteer).where(Volunteer.user_id==user.id))],
        'comments':[serialize(x) for x in db.scalars(select(Comment).where(Comment.user_id==user.id))]}

@router.delete('/account')
def delete_account(data:DeleteAccount,response:Response,user:User=Depends(current_user),db:DBSession=Depends(get_db)):
    if not password_ok(data.password,user.password_hash): raise HTTPException(403,'Password is incorrect.')
    owned=db.scalars(select(Membership).where(Membership.user_id==user.id,Membership.role=='owner',Membership.status=='approved')).all()
    if owned: raise HTTPException(409,'Transfer church ownership or delete the church before deleting your account.')
    # FK deletion releases meal commitments; remove stale descriptions as well.
    for slot in db.scalars(select(MealSlot).where(MealSlot.user_id==user.id)):
        slot.user_id=None; slot.meal=''; slot.note=''; slot.delivered=False
    db.execute(delete(Mail).where(Mail.recipient==user.email))
    db.delete(user); db.commit(); response.delete_cookie('village_session',path='/'); return {'ok':True}
