from fastapi import APIRouter,Depends,HTTPException
from sqlalchemy import select,delete
from sqlalchemy.orm import Session as DBSession
from .database import get_db
from .models import User,Notification,Membership,Block,Device
from .schemas import DeviceData
from .security import current_user,member
from .care import serialize,save
router=APIRouter(prefix='/api',tags=['Notifications and safety'])
@router.get('/notifications')
def inbox(user:User=Depends(current_user),db:DBSession=Depends(get_db)):
    approved=select(Membership.church_id).where(Membership.user_id==user.id,Membership.status=='approved')
    return [serialize(n) for n in db.scalars(select(Notification).where(Notification.user_id==user.id,Notification.in_app==True,Notification.church_id.in_(approved)).order_by(Notification.created_at.desc()).limit(200))]
@router.post('/notifications/read')
def read_all(user:User=Depends(current_user),db:DBSession=Depends(get_db)):
    for n in db.scalars(select(Notification).where(Notification.user_id==user.id,Notification.read==False)):n.read=True
    save(db);return {'ok':True}
@router.post('/notifications/{notification_id}/read')
def read_one(notification_id:str,user:User=Depends(current_user),db:DBSession=Depends(get_db)):
    n=db.get(Notification,notification_id)
    if not n or n.user_id!=user.id:raise HTTPException(404,'Notification not found.')
    n.read=True;save(db);return {'ok':True}
@router.put('/devices')
def device(data:DeviceData,user:User=Depends(current_user),db:DBSession=Depends(get_db)):
    existing=db.scalar(select(Device).where(Device.token==data.token))
    if not existing:existing=Device(token=data.token);db.add(existing)
    existing.user_id=user.id;existing.platform=data.platform;save(db);return {'ok':True}
@router.delete('/devices')
def remove_devices(user:User=Depends(current_user),db:DBSession=Depends(get_db)):
    db.execute(delete(Device).where(Device.user_id==user.id));save(db);return {'ok':True}
@router.get('/blocks')
def blocks(user:User=Depends(current_user),db:DBSession=Depends(get_db)):
    return [{'user_id':b.blocked_id,'name':db.get(User,b.blocked_id).name} for b in db.scalars(select(Block).where(Block.user_id==user.id))]
@router.put('/churches/{church_id}/blocks/{user_id}')
def block(church_id:str,user_id:str,user:User=Depends(current_user),db:DBSession=Depends(get_db)):
    member(church_id,db,user)
    if user_id==user.id:raise HTTPException(400,'You cannot block yourself.')
    if not db.scalar(select(Membership).where(Membership.church_id==church_id,Membership.user_id==user_id,Membership.status=='approved')):raise HTTPException(404,'Member not found.')
    if not db.scalar(select(Block).where(Block.user_id==user.id,Block.blocked_id==user_id)):db.add(Block(user_id=user.id,blocked_id=user_id))
    save(db);return {'ok':True}
@router.delete('/blocks/{user_id}')
def unblock(user_id:str,user:User=Depends(current_user),db:DBSession=Depends(get_db)):
    db.execute(delete(Block).where(Block.user_id==user.id,Block.blocked_id==user_id));save(db);return {'ok':True}
