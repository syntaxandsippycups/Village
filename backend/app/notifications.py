"""Transactional notification outbox. No recipient addresses are public."""
from datetime import timedelta
from sqlalchemy import select
from .models import Notification, Membership, User, Block, now

def notify(db,church_id,user_id,category,title,body,link,key,actor=None,reminder=False):
    user=db.get(User,user_id)
    if not user: return
    m=db.scalar(select(Membership).where(Membership.user_id==user_id,Membership.church_id==church_id,Membership.status=='approved'))
    if not m: return
    if actor and db.scalar(select(Block).where(((Block.user_id==actor)&(Block.blocked_id==user_id))|((Block.user_id==user_id)&(Block.blocked_id==actor)))): return
    prefs=user.preferences or {}
    if not prefs.get(category,True) or (reminder and not prefs.get('reminders',True)): return
    dedup=f'{key}:{user_id}'
    if db.scalar(select(Notification.id).where(Notification.dedup_key==dedup)): return
    db.add(Notification(user_id=user_id,church_id=church_id,category=category,title=title,body=body,link=link,dedup_key=dedup,
        in_app=prefs.get('in_app',True),email_state='pending' if prefs.get('email',False) else 'disabled',push_state='pending' if prefs.get('push',False) else 'disabled'))

def broadcast(db,church_id,category,title,link,key,actor):
    for m in db.scalars(select(Membership).where(Membership.church_id==church_id,Membership.status=='approved')).all():
        if m.user_id != actor: notify(db,church_id,m.user_id,category,title,'Open Village to see the details.',link,key,actor=actor)

def queue_mail(db,email,subject,body):
    from .models import Mail
    db.add(Mail(recipient=email,subject=subject,body=body))
