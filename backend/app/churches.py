from io import BytesIO
import secrets
import qrcode
from fastapi import APIRouter,Depends,HTTPException,Request,Response
from sqlalchemy import select,delete
from sqlalchemy.orm import Session as DBSession
from .database import get_db
from .models import User,Church,Membership,Report,MealSlot,MealTrain,RSVP,Event,Volunteer,Need,Comment,Notification,now
from .schemas import ChurchCreate,Join,MemberUpdate,ReportData
from .security import current_user,member,digest,set_code,normalize_code,fernet,rate_limit,blocked_ids
from .notifications import notify
from . import config
router=APIRouter(prefix='/api',tags=['Churches'])

def church_info(church): return {k:getattr(church,k) for k in ['id','name','location','timezone','require_approval']}

@router.get('/churches/mine')
def mine(user:User=Depends(current_user),db:DBSession=Depends(get_db)):
    return [{**church_info(c),'membership_id':m.id,'role':m.role,'status':m.status} for m,c in db.execute(select(Membership,Church).join(Church,Membership.church_id==Church.id).where(Membership.user_id==user.id))]

@router.post('/churches',status_code=201)
def create(data:ChurchCreate,request:Request,user:User=Depends(current_user),db:DBSession=Depends(get_db)):
    rate_limit(db,'church-create:'+user.id,5,86400)
    c=Church(**data.model_dump()); code=set_code(c); db.add(c); db.flush()
    db.add(Membership(user_id=user.id,church_id=c.id,role='owner',status='approved')); db.commit()
    return {**church_info(c),'code':code}

@router.post('/churches/join')
def join(data:Join,user:User=Depends(current_user),db:DBSession=Depends(get_db)):
    rate_limit(db,'join:'+user.id,10)
    c=db.scalar(select(Church).where(Church.code_hash==digest(normalize_code(data.code))))
    if not c: raise HTTPException(404,'That invitation is invalid or has been replaced. Ask your church for its current code.')
    m=db.scalar(select(Membership).where(Membership.user_id==user.id,Membership.church_id==c.id))
    if m and m.status=='removed': raise HTTPException(403,'Please contact a church administrator about membership.')
    if not m:
        m=Membership(user_id=user.id,church_id=c.id,status='pending' if c.require_approval else 'approved'); db.add(m); db.flush()
        for admin in db.scalars(select(Membership).where(Membership.church_id==c.id,Membership.status=='approved',Membership.role.in_(['owner','admin']))):
            notify(db,c.id,admin.user_id,'community','A new member has requested to join',user.name,'/?view=admin',f'join:{m.id}')
    db.commit(); return {**church_info(c),'status':m.status,'role':m.role}

@router.get('/churches/{church_id}/invitation')
def invitation(church_id:str,user:User=Depends(current_user),db:DBSession=Depends(get_db)):
    member(church_id,db,user,admin=True); c=db.get(Church,church_id)
    code=fernet.decrypt(c.code_encrypted.encode()).decode()
    return {'code':code,'url':f'{config.WEB_URL}/?join={code}','require_approval':c.require_approval}

@router.get('/churches/{church_id}/qr')
def qr(church_id:str,user:User=Depends(current_user),db:DBSession=Depends(get_db)):
    value=invitation(church_id,user,db)
    output=BytesIO(); qrcode.make(value['url']).save(output,format='PNG')
    return Response(output.getvalue(),media_type='image/png')

@router.post('/churches/{church_id}/rotate-code')
def rotate(church_id:str,user:User=Depends(current_user),db:DBSession=Depends(get_db)):
    member(church_id,db,user,admin=True); c=db.get(Church,church_id); code=set_code(c); db.commit()
    return {'code':code,'url':f'{config.WEB_URL}/?join={code}'}

@router.put('/churches/{church_id}')
def settings(church_id:str,data:ChurchCreate,user:User=Depends(current_user),db:DBSession=Depends(get_db)):
    member(church_id,db,user,admin=True); c=db.get(Church,church_id)
    for k,v in data.model_dump().items(): setattr(c,k,v)
    db.commit(); return church_info(c)

@router.get('/churches/{church_id}/members')
def members(church_id:str,user:User=Depends(current_user),db:DBSession=Depends(get_db)):
    member(church_id,db,user,admin=True)
    return [{'id':m.id,'user_id':u.id,'name':u.name,'email':u.email,'role':m.role,'status':m.status} for m,u in db.execute(select(Membership,User).join(User,Membership.user_id==User.id).where(Membership.church_id==church_id).order_by(User.name))]

def release_membership(db,m):
    for s in db.scalars(select(MealSlot).join(MealTrain,MealSlot.train_id==MealTrain.id).where(MealTrain.church_id==m.church_id,MealSlot.user_id==m.user_id,MealSlot.delivered==False)):
        s.user_id=None;s.meal='';s.note=''
    db.execute(delete(RSVP).where(RSVP.user_id==m.user_id,RSVP.event_id.in_(select(Event.id).where(Event.church_id==m.church_id))))
    db.execute(delete(Volunteer).where(Volunteer.user_id==m.user_id,Volunteer.need_id.in_(select(Need.id).where(Need.church_id==m.church_id))))
    db.execute(delete(Notification).where(Notification.user_id==m.user_id,Notification.church_id==m.church_id))

@router.put('/churches/{church_id}/members/{membership_id}')
def change_member(church_id:str,membership_id:str,data:MemberUpdate,user:User=Depends(current_user),db:DBSession=Depends(get_db)):
    actor=member(church_id,db,user,admin=True)
    m=db.scalar(select(Membership).where(Membership.id==membership_id,Membership.church_id==church_id).with_for_update())
    if not m: raise HTTPException(404,'Member not found.')
    if m.role=='owner': raise HTTPException(403,'Use ownership transfer for the owner.')
    if (m.role=='admin' or data.role=='admin') and actor.role!='owner': raise HTTPException(403,'Only the owner can manage administrator roles.')
    if m.user_id==user.id: raise HTTPException(403,'You cannot change your own role here.')
    if data.status!='approved': release_membership(db,m)
    previous=m.status
    m.role=data.role;m.status=data.status
    if previous!='approved' and data.status=='approved':
        db.flush()
        notify(db,church_id,m.user_id,'community','Welcome to your church Village','Your membership is approved. Add a little about yourself and find ways to connect.','/?view=home&church='+church_id,'approved:'+m.id)
    db.commit();return {'ok':True}

@router.post('/churches/{church_id}/transfer/{membership_id}')
def transfer(church_id:str,membership_id:str,user:User=Depends(current_user),db:DBSession=Depends(get_db)):
    # Lock the church before both membership records to prevent competing transfers.
    db.scalar(select(Church).where(Church.id==church_id).with_for_update())
    actor=member(church_id,db,user,admin=True)
    if actor.role!='owner': raise HTTPException(403,'Only the owner may transfer ownership.')
    target=db.scalar(select(Membership).where(Membership.id==membership_id,Membership.church_id==church_id,Membership.status=='approved'))
    if not target or target.id==actor.id: raise HTTPException(400,'Choose another approved member.')
    target.role='owner';actor.role='admin';db.commit();return {'ok':True}

@router.post('/churches/{church_id}/leave')
def leave(church_id:str,user:User=Depends(current_user),db:DBSession=Depends(get_db)):
    m=db.scalar(select(Membership).where(Membership.church_id==church_id,Membership.user_id==user.id))
    if not m: raise HTTPException(404,'Membership not found.')
    if m.role=='owner': raise HTTPException(409,'Transfer ownership before leaving.')
    release_membership(db,m);db.delete(m);db.commit();return {'ok':True}

@router.delete('/churches/{church_id}')
def delete_church(church_id:str,user:User=Depends(current_user),db:DBSession=Depends(get_db)):
    m=member(church_id,db,user,admin=True)
    if m.role!='owner': raise HTTPException(403,'Only the owner can delete the church.')
    db.delete(db.get(Church,church_id));db.commit();return {'ok':True}

@router.get('/churches/{church_id}/directory')
def directory(church_id:str,search:str='',group:str='',user:User=Depends(current_user),db:DBSession=Depends(get_db)):
    member(church_id,db,user)
    if len(search)>200 or len(group)>80: raise HTTPException(400,'Search is too long.')
    blocked=blocked_ids(db,user); result=[]
    users=db.scalars(select(User).join(Membership,Membership.user_id==User.id).where(Membership.church_id==church_id,Membership.status=='approved').order_by(User.name)).all()
    for u in users:
        p=u.privacy or {}
        if u.id in blocked or not p.get('directory',True): continue
        if group and group not in (u.groups or []): continue
        public={'id':u.id,'name':u.name,'bio':u.bio,'skills':u.skills,'resources':u.resources,'groups':u.groups,'available':u.available,'joined':u.created_at.isoformat()+'Z'}
        for field in ['email','phone','address','household']:
            public[field]=getattr(u,field) if p.get(field,False) else ''
        # Search only fields the member has chosen to disclose.
        if search and search.casefold() not in str(public).casefold(): continue
        result.append(public)
    return result

@router.get('/churches/{church_id}/reports')
def reports(church_id:str,user:User=Depends(current_user),db:DBSession=Depends(get_db)):
    from .care import serialize
    member(church_id,db,user,admin=True)
    return [serialize(r) for r in db.scalars(select(Report).where(Report.church_id==church_id).order_by(Report.created_at.desc()))]

@router.post('/churches/{church_id}/reports')
def report(church_id:str,data:ReportData,user:User=Depends(current_user),db:DBSession=Depends(get_db)):
    from .security import scoped
    member(church_id,db,user)
    models={'events':Event,'needs':Need,'meals':MealTrain,'comments':Comment}
    if data.kind=='directory':
        if not db.scalar(select(Membership).where(Membership.church_id==church_id,Membership.user_id==data.target_id,Membership.status=='approved')): raise HTTPException(404,'Member not found.')
    else: scoped(models[data.kind],data.target_id,church_id,db,user)
    r=Report(church_id=church_id,user_id=user.id,**data.model_dump());db.add(r);db.flush()
    for m in db.scalars(select(Membership).where(Membership.church_id==church_id,Membership.status=='approved',Membership.role.in_(['owner','admin']))):
        notify(db,church_id,m.user_id,'community','A community report needs review','Review the report in church administration.','/?view=admin',f'report:{r.id}')
    db.commit();return {'ok':True}

@router.post('/churches/{church_id}/reports/{report_id}/resolve')
def resolve(church_id:str,report_id:str,user:User=Depends(current_user),db:DBSession=Depends(get_db)):
    member(church_id,db,user,admin=True);r=db.scalar(select(Report).where(Report.id==report_id,Report.church_id==church_id))
    if not r: raise HTTPException(404,'Report not found.')
    r.resolved=True;db.commit();return {'ok':True}
