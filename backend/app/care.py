"""Community API: actor and church scope come from the authenticated session."""
from datetime import date,datetime,timedelta,timezone
from fastapi import APIRouter,Depends,HTTPException
from sqlalchemy import select,func,delete
from sqlalchemy.orm import Session as DBSession
from sqlalchemy.exc import IntegrityError
from .database import get_db
from .models import User,Church,Membership,Event,RSVP,Need,Volunteer,MealTrain,MealSlot,Comment,Notification,Block,Device,now,uid
from .schemas import EventData,RSVPData,NeedData,VolunteerData,MealData,MealClaim,Delivered,CommentData,DeviceData
from .security import current_user,member,scoped,can_manage,blocked_ids
from .notifications import notify,broadcast
router=APIRouter(prefix='/api/churches/{church_id}',tags=['Life together'])
MODELS={'events':Event,'needs':Need,'meals':MealTrain}
def serialize(row):
    return {c.name:(getattr(row,c.name).isoformat()+('Z' if isinstance(getattr(row,c.name),datetime) else '') if isinstance(getattr(row,c.name),(date,datetime)) else getattr(row,c.name)) for c in row.__table__.columns}
def name(db,user_id):
    u=db.get(User,user_id);return u.name if u else 'Former member'
def is_organizer(item,db,user):
    m=member(item.church_id,db,user)
    return item.created_by==user.id or m.role in ('admin','owner')
def link(kind,id,church_id):return f'/?view={kind}&id={id}&church={church_id}'
def save(db):
    try: db.commit()
    except IntegrityError:
        db.rollback();raise HTTPException(409,'Another member just changed this. Refresh and try again.')
def utc(value):return value.astimezone(timezone.utc).replace(tzinfo=None) if value else None

def event_json(e,db,user,detail=False):
    rsvps=db.scalars(select(RSVP).where(RSVP.event_id==e.id)).all();own=next((r for r in rsvps if r.user_id==user.id),None)
    result={**serialize(e),'organizer':name(db,e.created_by),'can_manage':is_organizer(e,db,user),'attendee_count':sum(1+r.guest_count for r in rsvps),'my_rsvp':serialize(own) if own else None}
    if detail:
        # Guest counts, never children's names. RSVP notes only visible to hosts.
        result['attendees']=[{'name':name(db,r.user_id),'guest_count':r.guest_count,**({'note':r.note} if result['can_manage'] or r.user_id==user.id else {})} for r in rsvps if r.user_id not in blocked_ids(db,user)]
    return result

def need_json(n,db,user,detail=False):
    volunteers=db.scalars(select(Volunteer).where(Volunteer.need_id==n.id)).all()
    result={**serialize(n),'organizer':name(db,n.created_by),'can_manage':is_organizer(n,db,user),'volunteer_count':len(volunteers),'my_volunteer':next((serialize(v) for v in volunteers if v.user_id==user.id),None)}
    if detail: result['volunteers']=[{'name':name(db,v.user_id),'note':v.note if result['can_manage'] or v.user_id==user.id else ''} for v in volunteers if v.user_id not in blocked_ids(db,user)]
    return result

def meal_json(t,db,user,detail=False):
    slots=db.scalars(select(MealSlot).where(MealSlot.train_id==t.id).order_by(MealSlot.date)).all()
    result={**serialize(t),'organizer':name(db,t.created_by),'can_manage':is_organizer(t,db,user),'slot_count':len(slots),'claimed_count':sum(bool(s.user_id) for s in slots),'my_count':sum(s.user_id==user.id for s in slots)}
    # The delivery address/contact are exposed only to the organizer and people
    # who have taken responsibility for a meal, never to the public list.
    if not result['can_manage'] and not any(s.user_id==user.id for s in slots):
        result['address']='';result['contact']='';result['instructions']=''
    if detail:
        blocked=blocked_ids(db,user)
        result['slots']=[{**serialize(s),'name':name(db,s.user_id) if s.user_id and s.user_id not in blocked else ('A church member' if s.user_id else ''),
            'meal':s.meal if not s.user_id or s.user_id not in blocked else 'Meal planned',
            'note':s.note if result['can_manage'] or s.user_id==user.id else ''} for s in slots]
    else:
        for key in ['address','contact','instructions']:result.pop(key,None)
    return result

@router.get('/events')
def events(church_id:str,archive:bool=False,user:User=Depends(current_user),db:DBSession=Depends(get_db)):
    member(church_id,db,user);blocked=blocked_ids(db,user)
    q=select(Event).where(Event.church_id==church_id,Event.starts_at<now() if archive else Event.starts_at>=now()).order_by(Event.starts_at.desc() if archive else Event.starts_at)
    return [event_json(e,db,user) for e in db.scalars(q) if e.created_by not in blocked]

@router.post('/events',status_code=201)
def create_event(church_id:str,data:EventData,user:User=Depends(current_user),db:DBSession=Depends(get_db)):
    m=member(church_id,db,user)
    if data.official and m.role not in ('owner','admin'):raise HTTPException(403,'Only administrators can post official church events.')
    if utc(data.starts_at)<=now():raise HTTPException(422,'Choose a future event time.')
    values=data.model_dump();values['starts_at']=utc(data.starts_at);values['ends_at']=utc(data.ends_at)
    e=Event(church_id=church_id,created_by=user.id,**values);db.add(e);db.flush()
    broadcast(db,church_id,'events',e.title,link('events',e.id,church_id),f'event:{e.id}',user.id);save(db)
    return event_json(e,db,user,True)

@router.get('/events/{item_id}')
def get_event(church_id:str,item_id:str,user:User=Depends(current_user),db:DBSession=Depends(get_db)):
    return event_json(scoped(Event,item_id,church_id,db,user),db,user,True)

@router.put('/events/{item_id}')
def edit_event(church_id:str,item_id:str,data:EventData,user:User=Depends(current_user),db:DBSession=Depends(get_db)):
    e=scoped(Event,item_id,church_id,db,user,True);m=can_manage(e,db,user)
    if data.official and m.role not in ('owner','admin'):raise HTTPException(403,'Only administrators can mark an event official.')
    count=db.scalar(select(func.coalesce(func.sum(RSVP.guest_count+1),0)).where(RSVP.event_id==e.id))
    if data.capacity is not None and data.capacity<count:raise HTTPException(409,'Capacity cannot be lower than existing RSVPs.')
    for k,v in data.model_dump().items():setattr(e,k,utc(v) if k in ['starts_at','ends_at'] else v)
    for r in db.scalars(select(RSVP).where(RSVP.event_id==e.id)):
        notify(db,church_id,r.user_id,'events','An event you joined has changed',e.title,link('events',e.id,church_id),f'event-edit:{uid()}',actor=user.id)
    save(db);return event_json(e,db,user,True)

@router.put('/events/{item_id}/rsvp')
def rsvp(church_id:str,item_id:str,data:RSVPData,user:User=Depends(current_user),db:DBSession=Depends(get_db)):
    e=scoped(Event,item_id,church_id,db,user,True)
    if e.cancelled or e.starts_at<now():raise HTTPException(409,'This event is no longer accepting RSVPs.')
    own=db.scalar(select(RSVP).where(RSVP.event_id==e.id,RSVP.user_id==user.id))
    total=db.scalar(select(func.coalesce(func.sum(RSVP.guest_count+1),0)).where(RSVP.event_id==e.id,RSVP.user_id!=user.id))
    if e.capacity and total+1+data.guest_count>e.capacity:raise HTTPException(409,'There is not enough room for this RSVP. Try fewer guests or contact the host.')
    if not own:own=RSVP(event_id=e.id,user_id=user.id);db.add(own)
    own.guest_count=data.guest_count;own.note=data.note
    notify(db,church_id,e.created_by,'events',f'{user.name} RSVP’d',e.title,link('events',e.id,church_id),f'rsvp:{uid()}',actor=user.id)
    save(db);return event_json(e,db,user,True)

@router.delete('/events/{item_id}/rsvp')
def cancel_rsvp(church_id:str,item_id:str,user:User=Depends(current_user),db:DBSession=Depends(get_db)):
    e=scoped(Event,item_id,church_id,db,user,True)
    db.execute(delete(RSVP).where(RSVP.event_id==item_id,RSVP.user_id==user.id))
    notify(db,church_id,e.created_by,'events',f'{user.name} cancelled an RSVP',e.title,link('events',e.id,church_id),f'rsvp-cancel:{uid()}',actor=user.id)
    save(db);return {'ok':True}

@router.get('/needs')
def needs(church_id:str,user:User=Depends(current_user),db:DBSession=Depends(get_db)):
    member(church_id,db,user);blocked=blocked_ids(db,user)
    return [need_json(n,db,user) for n in db.scalars(select(Need).where(Need.church_id==church_id).order_by(Need.created_at.desc())) if n.created_by not in blocked]

@router.post('/needs',status_code=201)
def create_need(church_id:str,data:NeedData,user:User=Depends(current_user),db:DBSession=Depends(get_db)):
    member(church_id,db,user);n=Need(church_id=church_id,created_by=user.id,**data.model_dump());db.add(n);db.flush()
    broadcast(db,church_id,'needs',n.title,link('needs',n.id,church_id),f'need:{n.id}',user.id);save(db);return need_json(n,db,user,True)

@router.get('/needs/{item_id}')
def get_need(church_id:str,item_id:str,user:User=Depends(current_user),db:DBSession=Depends(get_db)):
    return need_json(scoped(Need,item_id,church_id,db,user),db,user,True)

@router.put('/needs/{item_id}')
def edit_need(church_id:str,item_id:str,data:NeedData,user:User=Depends(current_user),db:DBSession=Depends(get_db)):
    n=scoped(Need,item_id,church_id,db,user,True);can_manage(n,db,user)
    count=db.scalar(select(func.count()).select_from(Volunteer).where(Volunteer.need_id==n.id))
    if data.volunteers_needed<count:raise HTTPException(409,'Existing volunteers exceed the new capacity.')
    for k,v in data.model_dump().items():setattr(n,k,v)
    for v in db.scalars(select(Volunteer).where(Volunteer.need_id==n.id)):
        notify(db,church_id,v.user_id,'needs','A need you volunteered for has changed',n.title,link('needs',n.id,church_id),f'need-edit:{uid()}',actor=user.id)
    save(db);return need_json(n,db,user,True)

@router.put('/needs/{item_id}/volunteer')
def volunteer(church_id:str,item_id:str,data:VolunteerData,user:User=Depends(current_user),db:DBSession=Depends(get_db)):
    n=scoped(Need,item_id,church_id,db,user,True)
    from zoneinfo import ZoneInfo
    today=datetime.now(ZoneInfo(db.get(Church,church_id).timezone)).date()
    if n.status!='open' or (n.due_date and n.due_date < today):raise HTTPException(409,'This need is closed or its due date has passed.')
    own=db.scalar(select(Volunteer).where(Volunteer.need_id==n.id,Volunteer.user_id==user.id))
    count=db.scalar(select(func.count()).select_from(Volunteer).where(Volunteer.need_id==n.id))
    if not own and count>=n.volunteers_needed:raise HTTPException(409,'All volunteer places are filled.')
    if not own:own=Volunteer(need_id=n.id,user_id=user.id);db.add(own)
    own.note=data.note
    notify(db,church_id,n.created_by,'needs',f'{user.name} can help',n.title,link('needs',n.id,church_id),f'volunteer:{uid()}',actor=user.id)
    save(db);return need_json(n,db,user,True)

@router.delete('/needs/{item_id}/volunteer')
def cancel_volunteer(church_id:str,item_id:str,user:User=Depends(current_user),db:DBSession=Depends(get_db)):
    n=scoped(Need,item_id,church_id,db,user,True)
    db.execute(delete(Volunteer).where(Volunteer.need_id==n.id,Volunteer.user_id==user.id))
    notify(db,church_id,n.created_by,'needs',f'{user.name} cancelled volunteering',n.title,link('needs',n.id,church_id),f'volunteer-cancel:{uid()}',actor=user.id)
    save(db);return {'ok':True}

@router.post('/meals/preview')
def preview_meals(church_id:str,data:MealData,user:User=Depends(current_user),db:DBSession=Depends(get_db)):
    member(church_id,db,user);return {'dates':[d.isoformat() for d in data.dates()]}

@router.get('/meals')
def meals(church_id:str,user:User=Depends(current_user),db:DBSession=Depends(get_db)):
    member(church_id,db,user);blocked=blocked_ids(db,user)
    return [meal_json(t,db,user) for t in db.scalars(select(MealTrain).where(MealTrain.church_id==church_id).order_by(MealTrain.created_at.desc())) if t.created_by not in blocked]

@router.post('/meals',status_code=201)
def create_meals(church_id:str,data:MealData,user:User=Depends(current_user),db:DBSession=Depends(get_db)):
    member(church_id,db,user)
    t=MealTrain(church_id=church_id,created_by=user.id,**data.model_dump(exclude={'excluded_dates','extra_dates'}));db.add(t);db.flush()
    for d in data.dates():db.add(MealSlot(train_id=t.id,date=d))
    broadcast(db,church_id,'meals',t.title,link('meals',t.id,church_id),f'meal:{t.id}',user.id);save(db);return meal_json(t,db,user,True)

@router.get('/meals/{item_id}')
def get_meals(church_id:str,item_id:str,user:User=Depends(current_user),db:DBSession=Depends(get_db)):
    return meal_json(scoped(MealTrain,item_id,church_id,db,user),db,user,True)

@router.put('/meals/{item_id}')
def edit_meals(church_id:str,item_id:str,data:MealData,user:User=Depends(current_user),db:DBSession=Depends(get_db)):
    t=scoped(MealTrain,item_id,church_id,db,user,True);can_manage(t,db,user)
    slots=db.scalars(select(MealSlot).where(MealSlot.train_id==t.id)).all();selected=set(data.dates())
    protected=[s.date.isoformat() for s in slots if s.user_id and s.date not in selected]
    if protected:raise HTTPException(409,'These dates are booked: '+', '.join(protected)+'. Keep them selected or cancel the bookings first.')
    for s in slots:
        if s.date not in selected:db.delete(s)
    existing={s.date for s in slots}
    for d in selected-existing:db.add(MealSlot(train_id=t.id,date=d))
    for k,v in data.model_dump(exclude={'excluded_dates','extra_dates'}).items():setattr(t,k,v)
    for user_id in {s.user_id for s in slots if s.user_id}:
        notify(db,church_id,user_id,'meals','Your meal train details have changed',t.title,link('meals',t.id,church_id),f'meal-edit:{uid()}',actor=user.id)
    save(db);return meal_json(t,db,user,True)

@router.put('/meals/{item_id}/slots/{slot_id}')
def claim(church_id:str,item_id:str,slot_id:str,data:MealClaim,user:User=Depends(current_user),db:DBSession=Depends(get_db)):
    t=scoped(MealTrain,item_id,church_id,db,user,True)
    s=db.scalar(select(MealSlot).where(MealSlot.id==slot_id,MealSlot.train_id==t.id).with_for_update())
    if not s:raise HTTPException(404,'Meal date not found.')
    from zoneinfo import ZoneInfo
    today=datetime.now(ZoneInfo(db.get(Church,church_id).timezone)).date()
    if t.closed or s.date<today:raise HTTPException(409,'This date is closed or has passed.')
    actor=data.for_user_id or user.id
    if actor!=user.id:
        can_manage(t,db,user)
        if not data.consent:raise HTTPException(422,'Confirm the volunteer gave permission.')
        volunteer=db.get(User,actor)
        if not volunteer:raise HTTPException(404,'Volunteer not found.')
        member(church_id,db,volunteer)
    if s.user_id and s.user_id!=actor:raise HTTPException(409,'This meal date is already claimed.')
    if s.delivered:raise HTTPException(409,'This meal is already marked delivered.')
    s.user_id=actor;s.meal=data.meal;s.note=data.note
    key=uid()
    for recipient in {actor,t.created_by}:
        notify(db,church_id,recipient,'meals','Meal date confirmed',f'{t.title}: {s.date.isoformat()}. Open Village for your meal details.',link('meals',t.id,church_id),f'meal-claim:{key}',actor=user.id)
    save(db);return meal_json(t,db,user,True)

@router.delete('/meals/{item_id}/slots/{slot_id}')
def cancel_meal(church_id:str,item_id:str,slot_id:str,user:User=Depends(current_user),db:DBSession=Depends(get_db)):
    t=scoped(MealTrain,item_id,church_id,db,user,True);s=db.scalar(select(MealSlot).where(MealSlot.id==slot_id,MealSlot.train_id==t.id).with_for_update())
    if not s:raise HTTPException(404,'Meal date not found.')
    if s.user_id!=user.id:can_manage(t,db,user)
    if s.delivered:raise HTTPException(409,'Delivered meals cannot be cancelled. Unmark delivery first.')
    previous=s.user_id;s.user_id=None;s.meal='';s.note='';s.delivered=False
    for recipient in {t.created_by,previous} - {None}:
        notify(db,church_id,recipient,'meals','Meal date cancelled',f'{t.title}: {s.date.isoformat()}',link('meals',t.id,church_id),f'meal-cancel:{uid()}',actor=user.id)
    save(db);return {'ok':True}

@router.put('/meals/{item_id}/slots/{slot_id}/delivered')
def delivered(church_id:str,item_id:str,slot_id:str,data:Delivered,user:User=Depends(current_user),db:DBSession=Depends(get_db)):
    t=scoped(MealTrain,item_id,church_id,db,user,True);s=db.scalar(select(MealSlot).where(MealSlot.id==slot_id,MealSlot.train_id==t.id))
    if not s or not s.user_id:raise HTTPException(404,'Claimed meal date not found.')
    if s.user_id!=user.id:can_manage(t,db,user)
    s.delivered=data.delivered;save(db);return {'ok':True}

@router.get('/commitments')
def commitments(church_id:str,user:User=Depends(current_user),db:DBSession=Depends(get_db)):
    member(church_id,db,user);blocked=blocked_ids(db,user)
    return {'events':[event_json(e,db,user) for e in db.scalars(select(Event).join(RSVP,RSVP.event_id==Event.id).where(Event.church_id==church_id,RSVP.user_id==user.id,Event.starts_at>=now())) if e.created_by not in blocked],
        'needs':[need_json(n,db,user) for n in db.scalars(select(Need).join(Volunteer,Volunteer.need_id==Need.id).where(Need.church_id==church_id,Volunteer.user_id==user.id,Need.status=='open')) if n.created_by not in blocked],
        'meals':[{'slot':serialize(s),'train':meal_json(t,db,user)} for s,t in db.execute(select(MealSlot,MealTrain).join(MealTrain,MealSlot.train_id==MealTrain.id).where(MealTrain.church_id==church_id,MealSlot.user_id==user.id,MealSlot.delivered==False).order_by(MealSlot.date)) if t.created_by not in blocked]}

@router.get('/{kind}/{item_id}/comments')
def comments(church_id:str,kind:str,item_id:str,user:User=Depends(current_user),db:DBSession=Depends(get_db)):
    if kind not in MODELS:raise HTTPException(404,'Not found.')
    scoped(MODELS[kind],item_id,church_id,db,user);blocked=blocked_ids(db,user)
    return [{**serialize(c),'name':name(db,c.user_id),'can_delete':c.user_id==user.id or member(church_id,db,user).role in ('owner','admin')} for c in db.scalars(select(Comment).where(Comment.church_id==church_id,Comment.kind==kind,Comment.target_id==item_id).order_by(Comment.created_at)) if c.user_id not in blocked]

@router.post('/{kind}/{item_id}/comments',status_code=201)
def add_comment(church_id:str,kind:str,item_id:str,data:CommentData,user:User=Depends(current_user),db:DBSession=Depends(get_db)):
    if kind not in MODELS:raise HTTPException(404,'Not found.')
    item=scoped(MODELS[kind],item_id,church_id,db,user)
    c=Comment(church_id=church_id,kind=kind,target_id=item_id,user_id=user.id,text=data.text);db.add(c);db.flush()
    notify(db,church_id,item.created_by,kind if kind!='events' else 'events',f'{user.name} posted an update',item.title,link(kind,item_id,church_id),f'comment:{c.id}',actor=user.id)
    save(db);return {'ok':True}

@router.delete('/comments/{comment_id}')
def delete_comment(church_id:str,comment_id:str,user:User=Depends(current_user),db:DBSession=Depends(get_db)):
    m=member(church_id,db,user);c=db.scalar(select(Comment).where(Comment.id==comment_id,Comment.church_id==church_id))
    if not c:raise HTTPException(404,'Comment not found.')
    if c.user_id!=user.id and m.role not in ('owner','admin'):raise HTTPException(403,'Only the author or an administrator can delete this comment.')
    db.delete(c);save(db);return {'ok':True}

@router.delete('/{kind}/{item_id}')
def remove(church_id:str,kind:str,item_id:str,user:User=Depends(current_user),db:DBSession=Depends(get_db)):
    if kind not in MODELS:raise HTTPException(404,'Not found.')
    item=scoped(MODELS[kind],item_id,church_id,db,user,True);can_manage(item,db,user)
    recipients=[]
    if kind=='events':recipients=[r.user_id for r in db.scalars(select(RSVP).where(RSVP.event_id==item_id))]
    elif kind=='needs':recipients=[v.user_id for v in db.scalars(select(Volunteer).where(Volunteer.need_id==item_id))]
    else:recipients=[s.user_id for s in db.scalars(select(MealSlot).where(MealSlot.train_id==item_id,MealSlot.user_id!=None))]
    for recipient in set(recipients):notify(db,church_id,recipient,kind,'A commitment was cancelled',item.title,f'/?view=commitments&church={church_id}',f'delete:{uid()}',actor=user.id)
    db.execute(delete(Comment).where(Comment.church_id==church_id,Comment.kind==kind,Comment.target_id==item_id));db.delete(item);save(db);return {'ok':True}
