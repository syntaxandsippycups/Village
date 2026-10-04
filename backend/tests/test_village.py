from datetime import datetime,timedelta,timezone,date
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy import select
from app.database import SessionLocal
from app.models import Notification,MealSlot,Membership,Mail,User,AuthToken
from app.schemas import MealData
from app import config
from app.worker import once

MEAL={'title':'Meals for the Johnsons','recipient':'Johnson family','start_date':'2027-03-08','end_date':'2027-03-21','weekdays':[0,2,4],'consent':True,'adults':2,'children':3,'allergies':'No peanuts','address':'Private delivery address','contact':'Private contact','instructions':'Leave at porch'}
def root(village):return '/api/churches/'+village[4]['id']
def event_payload(capacity=4):return {'title':'Dinner at ours','starts_at':(datetime.now(timezone.utc)+timedelta(days=3)).isoformat(),'capacity':capacity,'audience':['Undergrads']}
def create_meal(v):
    r=v[0].post(root(v)+'/meals',json=MEAL);assert r.status_code==201,r.text;return r.json()

def test_anonymous_and_spoofed_ids_cannot_read(village):
    from fastapi.testclient import TestClient
    from app.server import app
    c=TestClient(app,headers={'x-user-id':village[1]['id']})
    for route in ['directory','events','needs','meals','members','invitation','commitments']:
        assert c.get(root(village)+'/'+route).status_code==401
    assert c.post('/api/auth/login',json={'email':'owner@example.org','password':'very-long-password-123'}).status_code==403

def test_pending_members_have_no_private_access(village,clients):
    p,_=clients('pending@example.org')
    assert p.post('/api/churches/join',json={'code':village[4]['code']}).json()['status']=='pending'
    for route in ['directory','events','needs','meals']:assert p.get(root(village)+'/'+route).status_code==403
    assert p.get(root(village)+'/invitation').status_code==403

def test_cross_church_read_and_write_isolation(village,clients):
    outsider,_=clients('outsider@example.org')
    c=outsider.post('/api/churches',json={'name':'Another Church'}).json()
    e=village[0].post(root(village)+'/events',json=event_payload()).json()
    assert outsider.get(root(village)+'/events/'+e['id']).status_code==403
    assert outsider.put(root(village)+'/events/'+e['id']+'/rsvp',json={}).status_code==403
    assert outsider.get('/api/churches/'+c['id']+'/events/'+e['id']).status_code==404
    assert outsider.get('/api/churches/'+c['id']+'/directory').json()[0]['name']=='A member'

def test_join_is_idempotent_and_codes_can_rotate(village):
    o,_,p,_,c=village;r=root(village)
    assert p.post('/api/churches/join',json={'code':c['code']}).json()['status']=='approved'
    assert len(o.get(r+'/members').json())==2
    new=o.post(r+'/rotate-code').json()['code'];assert new!=c['code']
    assert p.post('/api/churches/join',json={'code':c['code']}).status_code==404
    assert p.post('/api/churches/join',json={'code':new}).status_code==200
    assert o.get(r+'/qr').headers['content-type']=='image/png'

def test_direct_join_when_church_allows_it(clients):
    o,_=clients('o@example.org');p,_=clients('p@example.org')
    c=o.post('/api/churches',json={'name':'Open invitation church','require_approval':False}).json()
    assert p.post('/api/churches/join',json={'code':c['code'].lower()}).json()['status']=='approved'

def test_directory_privacy_and_search_only_public_fields(village):
    o,ou,p,pu,_=village
    payload={k:ou[k] for k in ['name','phone','address','household','bio','skills','resources','groups','available','privacy']}
    payload.update({'address':'Secret Elm Road','phone':'5551234','skills':['Piano lessons'],'resources':['Pickup truck'],'household':'Two children'})
    assert o.put('/api/auth/profile',json=payload).status_code==200
    entries=p.get(root(village)+'/directory').json();owner=next(x for x in entries if x['id']==ou['id'])
    assert owner['address']==owner['phone']==owner['email']==owner['household']==''
    assert p.get(root(village)+'/directory?search=Secret%20Elm').json()==[]
    assert len(p.get(root(village)+'/directory?search=truck').json())==1
    payload['privacy'].update({'phone':True,'address':True})
    o.put('/api/auth/profile',json=payload)
    assert p.get(root(village)+'/directory?search=Secret%20Elm').json()[0]['address']=='Secret Elm Road'
    payload['privacy']['directory']=False;o.put('/api/auth/profile',json=payload)
    assert all(x['id']!=ou['id'] for x in p.get(root(village)+'/directory').json())

def test_cannot_set_another_users_profile(village):
    _,ou,p,pu,_=village
    assert p.put('/api/auth/profile',json={'name':'Hacked','user_id':ou['id']}).status_code==422
    assert p.post('/api/auth/register',json={'email':'new@example.org','password':'long-password-123','name':'New','accept_terms':False}).status_code==422

def test_meal_exact_dates_dst_exclusions_and_extra(village):
    payload={**MEAL,'excluded_dates':['2027-03-12'],'extra_dates':['2027-03-14']}
    preview=village[0].post(root(village)+'/meals/preview',json=payload)
    dates=['2027-03-08','2027-03-10','2027-03-14','2027-03-15','2027-03-17','2027-03-19']
    assert preview.json()['dates']==dates
    train=village[0].post(root(village)+'/meals',json=payload).json()
    assert [s['date'] for s in train['slots']]==dates
    assert village[0].post(root(village)+'/meals',json={**MEAL,'weekdays':[]}).status_code==422
    assert village[0].post(root(village)+'/meals',json={**MEAL,'consent':False}).status_code==422

def test_meal_claim_description_edit_cancel_delivered_and_privacy(village):
    o,_,p,pu,_=village;t=create_meal(village);base=root(village)+'/meals/'+t['id'];s=t['slots'][0]
    unclaimed=p.get(base).json();assert unclaimed['address']==unclaimed['contact']==unclaimed['instructions']==''
    assert 'address' not in p.get(root(village)+'/meals').json()[0]
    assert p.put(base+'/slots/'+s['id'],json={'meal':''}).status_code==422
    claimed=p.put(base+'/slots/'+s['id'],json={'meal':'Chicken soup and rolls','note':'Around 5:30'}).json()
    assert claimed['address']==MEAL['address'];assert claimed['slots'][0]['meal']=='Chicken soup and rolls'
    assert p.put(base+'/slots/'+s['id'],json={'meal':'Vegetable soup'}).status_code==200
    assert o.put(base+'/slots/'+s['id'],json={'meal':'Someone else'}).status_code==409
    assert p.put(base+'/slots/'+s['id']+'/delivered',json={'delivered':True}).status_code==200
    assert p.delete(base+'/slots/'+s['id']).status_code==409
    p.put(base+'/slots/'+s['id']+'/delivered',json={'delivered':False})
    assert p.delete(base+'/slots/'+s['id']).status_code==200
    assert p.get(base).json()['address']==''
    assert p.get(base).json()['slots'][0]['user_id'] is None

def test_claim_race_has_one_winner(village):
    o,_,p,_,_=village;t=create_meal(village);url=root(village)+'/meals/'+t['id']+'/slots/'+t['slots'][0]['id']
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(c.put,url,json={'meal':'Pasta'}) for c in [o,p]]
    assert sorted(f.result().status_code for f in futures)==[200,409]

def test_schedule_changes_cannot_discard_bookings(village):
    o,_,p,_,_=village;t=create_meal(village);base=root(village)+'/meals/'+t['id']
    p.put(base+'/slots/'+t['slots'][0]['id'],json={'meal':'Pasta'})
    payload={**MEAL,'weekdays':[2,4]}
    assert o.put(base,json=payload).status_code==409
    assert p.put(base,json=MEAL).status_code==403
    payload={**MEAL,'extra_dates':['2027-03-14']}
    assert o.put(base,json=payload).status_code==200
    assert p.get(base).json()['slots'][0]['meal']=='Pasta'

def test_organizer_books_for_member_with_consent(village):
    o,_,_,pu,_=village;t=create_meal(village);url=root(village)+'/meals/'+t['id']+'/slots/'+t['slots'][0]['id']
    assert o.put(url,json={'meal':'Takeout','for_user_id':pu['id']}).status_code==422
    assert o.put(url,json={'meal':'Takeout','for_user_id':pu['id'],'consent':True}).status_code==200

def test_slot_belongs_to_train(village):
    t=create_meal(village);other=create_meal(village)
    assert village[2].put(root(village)+'/meals/'+t['id']+'/slots/'+other['slots'][0]['id'],json={'meal':'Pasta'}).status_code==404

def test_rsvp_capacity_idempotency_and_cancellation(village):
    o,_,p,_,_=village;e=o.post(root(village)+'/events',json=event_payload(3)).json();base=root(village)+'/events/'+e['id']
    assert p.put(base+'/rsvp',json={'guest_count':2,'note':'Family'}).status_code==200
    assert p.put(base+'/rsvp',json={'guest_count':2}).json()['attendee_count']==3
    assert o.put(base+'/rsvp',json={'guest_count':0}).status_code==409
    assert p.put(base+'/rsvp',json={'guest_count':1}).json()['attendee_count']==2
    assert o.put(base+'/rsvp',json={}).json()['attendee_count']==3
    assert p.put(base,json=event_payload(2)).status_code==403
    assert o.put(base,json=event_payload(2)).status_code==409
    assert p.delete(base+'/rsvp').status_code==200
    assert o.get(base).json()['attendee_count']==1
    assert p.put(base+'/rsvp',json={'user_id':village[1]['id']}).status_code==422

def test_rsvp_race_cannot_overfill(village):
    o,_,p,_,_=village;e=o.post(root(village)+'/events',json=event_payload(1)).json();url=root(village)+'/events/'+e['id']+'/rsvp'
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(c.put,url,json={}) for c in [o,p]]
    assert sorted(f.result().status_code for f in futures)==[200,409]
    assert o.get(root(village)+'/events/'+e['id']).json()['attendee_count']==1

def test_official_event_and_timezone_validation(village):
    o,_,p,_,_=village
    assert p.post(root(village)+'/events',json={**event_payload(),'official':True}).status_code==403
    assert o.post(root(village)+'/events',json={**event_payload(),'starts_at':'2027-01-01T10:00:00'}).status_code==422
    e=o.post(root(village)+'/events',json=event_payload()).json()
    assert o.put(root(village)+'/events/'+e['id'],json={**event_payload(),'cancelled':True}).status_code==200
    assert p.put(root(village)+'/events/'+e['id']+'/rsvp',json={}).status_code==409

def test_needs_volunteer_duplicate_capacity_and_fulfillment(village):
    o,_,p,_,_=village
    payload={'title':'Move boxes','volunteers_needed':1,'on_behalf':'Miss Betty','consent':True}
    assert o.post(root(village)+'/needs',json={**payload,'consent':False}).status_code==422
    n=o.post(root(village)+'/needs',json=payload).json();base=root(village)+'/needs/'+n['id']
    assert p.put(base+'/volunteer',json={'note':'I have a truck'}).status_code==200
    assert p.put(base+'/volunteer',json={}).json()['volunteer_count']==1
    assert o.put(base+'/volunteer',json={}).status_code==409
    assert p.delete(base+'/volunteer').status_code==200
    assert o.put(base,json={**payload,'status':'fulfilled'}).status_code==200
    assert p.put(base+'/volunteer',json={}).status_code==409

def test_preferences_filter_notifications_and_cancel_queued_mail(village):
    o,_,p,pu,_=village
    prefs={**pu['preferences'],'meals':False,'email':True}
    p.put('/api/auth/preferences',json=prefs);create_meal(village)
    assert not any(n['category']=='meals' for n in p.get('/api/notifications').json())
    e=o.post(root(village)+'/events',json=event_payload()).json()
    assert any(n['category']=='events' for n in p.get('/api/notifications').json())
    p.put('/api/auth/preferences',json={**prefs,'events':False})
    once()
    with SessionLocal() as db:
        n=db.scalar(select(Notification).where(Notification.user_id==pu['id'],Notification.category=='events'))
        assert n.email_state=='disabled'

def test_comments_reports_and_blocking(village):
    o,ou,p,pu,_=village;e=o.post(root(village)+'/events',json=event_payload()).json();base=root(village)+'/events/'+e['id']
    assert p.post(base+'/comments',json={'text':'Can I bring snacks?'}).status_code==201
    c=p.get(base+'/comments').json()[0]
    assert o.delete(root(village)+'/comments/'+c['id']).status_code==200
    assert p.post(root(village)+'/reports',json={'kind':'events','target_id':e['id'],'reason':'Concern about details'}).status_code==200
    assert p.get(root(village)+'/reports').status_code==403
    reports=o.get(root(village)+'/reports').json();assert len(reports)==1
    assert o.post(root(village)+'/reports/'+reports[0]['id']+'/resolve').status_code==200
    p.put(root(village)+'/blocks/'+ou['id'])
    assert p.get(base).status_code==404
    assert all(x['id']!=ou['id'] for x in p.get(root(village)+'/directory').json())
    p.delete('/api/blocks/'+ou['id']);assert p.get(base).status_code==200

def test_removal_revokes_access_and_releases_commitments(village):
    o,_,p,pu,_=village;t=create_meal(village);p.put(root(village)+'/meals/'+t['id']+'/slots/'+t['slots'][0]['id'],json={'meal':'Pasta'})
    e=o.post(root(village)+'/events',json=event_payload()).json();p.put(root(village)+'/events/'+e['id']+'/rsvp',json={})
    m=next(x for x in o.get(root(village)+'/members').json() if x['user_id']==pu['id'])
    assert p.put(root(village)+'/members/'+m['id'],json={'role':'admin','status':'approved'}).status_code==403
    assert o.put(root(village)+'/members/'+m['id'],json={'role':'member','status':'removed'}).status_code==200
    assert p.get(root(village)+'/directory').status_code==403
    assert o.get(root(village)+'/meals/'+t['id']).json()['slots'][0]['user_id'] is None
    assert o.get(root(village)+'/events/'+e['id']).json()['attendee_count']==0

def test_account_deletion_owner_guard_and_session_revocation(village):
    o,_,p,pu,_=village
    assert o.request('DELETE','/api/auth/account',json={'password':'very-long-password-123'}).status_code==409
    assert p.request('DELETE','/api/auth/account',json={'password':'bad'}).status_code==403
    assert p.request('DELETE','/api/auth/account',json={'password':'very-long-password-123'}).status_code==200
    assert p.get('/api/auth/me').status_code==401
    assert all(x['user_id']!=pu['id'] for x in o.get(root(village)+'/members').json())

def test_password_reset_token_one_time_and_logout(clients):
    p,u=clients('reset@example.org');p.post('/api/auth/forgot-password',json={'email':u['email']})
    with SessionLocal() as db:
        mail=db.scalar(select(Mail));url=mail.body.split('\n')[1];token=url.split('token=')[1]
    assert p.post('/api/auth/reset',json={'token':token,'password':'another-password-123'}).status_code==200
    assert p.get('/api/auth/me').status_code==401
    assert p.post('/api/auth/reset',json={'token':token,'password':'another-password-123'}).status_code==400
    assert p.post('/api/auth/login',json={'email':u['email'],'password':'another-password-123','native':True}).json()['token']
    assert p.post('/api/auth/logout').status_code==200
    assert p.get('/api/auth/me').status_code==401

def test_email_verification_required_and_generic_reset(clients,monkeypatch):
    monkeypatch.setattr(config,'VERIFY_EMAIL',True)
    from fastapi.testclient import TestClient
    from app.server import app
    c=TestClient(app,headers={'X-Village-Client':'v2'})
    c.post('/api/auth/register',json={'name':'Test','email':'verify@example.org','password':'very-long-password-123','accept_terms':True})
    assert c.post('/api/auth/login',json={'email':'verify@example.org','password':'very-long-password-123'}).status_code==403
    with SessionLocal() as db:token=db.scalar(select(Mail)).body.split('\n')[1].split('token=')[1]
    assert c.post('/api/auth/verify',json={'token':token}).status_code==200
    assert c.post('/api/auth/login',json={'email':'verify@example.org','password':'very-long-password-123'}).status_code==200
    assert c.post('/api/auth/forgot-password',json={'email':'nobody@example.org'}).json()['message'].startswith('If an eligible')

def test_origin_protection_and_rate_limit(clients):
    p,u=clients('limited@example.org')
    assert p.post('/api/auth/logout',headers={'Origin':'https://evil.example'}).status_code==403
    statuses=[p.post('/api/auth/login',json={'email':u['email'],'password':'wrong'}).status_code for _ in range(12)]
    assert 429 in statuses

def test_my_commitments_and_private_export(village):
    o,_,p,pu,_=village;t=create_meal(village);s=t['slots'][0]
    p.put(root(village)+'/meals/'+t['id']+'/slots/'+s['id'],json={'meal':'Pasta'})
    result=p.get(root(village)+'/commitments').json();assert result['meals'][0]['slot']['meal']=='Pasta'
    exported=p.get('/api/auth/export').json();assert exported['profile']['id']==pu['id'];assert len(exported['meal_commitments'])==1
    assert 'password_hash' not in str(exported)

def test_meal_reminders_deduplicate_and_respect_preferences(village,monkeypatch):
    from app.worker import reminders
    from app.models import Church,MealTrain
    from datetime import datetime as RealDateTime
    import app.worker as worker
    o,_,p,pu,_=village;t=create_meal(village)
    p.put(root(village)+'/meals/'+t['id']+'/slots/'+t['slots'][0]['id'],json={'meal':'Soup'})
    class FixedClock:
        @classmethod
        def now(cls,tz=None):return RealDateTime(2027,3,1,9,0,tzinfo=tz)
    monkeypatch.setattr(worker,'datetime',FixedClock)
    with SessionLocal() as db:
        reminders(db);db.commit();reminders(db);db.commit()
        rows=db.scalars(select(Notification).where(Notification.user_id==pu['id'],Notification.dedup_key.like('remind-meal:%'))).all()
        assert len(rows)==1
        assert '2027-03-08' in rows[0].body
    p.put('/api/auth/preferences',json={**pu['preferences'],'reminders':False})
    class LaterClock:
        @classmethod
        def now(cls,tz=None):return RealDateTime(2027,3,7,9,0,tzinfo=tz)
    monkeypatch.setattr(worker,'datetime',LaterClock)
    with SessionLocal() as db:
        reminders(db);db.commit()
        assert len(db.scalars(select(Notification).where(Notification.user_id==pu['id'],Notification.dedup_key.like('remind-meal:%'))).all())==1

def test_mail_provider_failure_retries_without_claiming_sent(village,monkeypatch):
    import app.worker as worker
    p=village[2];p.post('/api/auth/forgot-password',json={'email':'member@example.org'})
    def fail(*args):raise OSError('simulated provider unavailable')
    monkeypatch.setattr(worker,'send_email',fail)
    once()
    with SessionLocal() as db:
        mail=db.scalar(select(Mail));assert not mail.sent and mail.attempts==1
        assert mail.next_attempt>datetime.now(timezone.utc).replace(tzinfo=None)

def test_notification_jobs_stop_after_membership_removal(village):
    o,_,p,pu,_=village
    p.put('/api/auth/preferences',json={**pu['preferences'],'email':True})
    o.post(root(village)+'/events',json=event_payload())
    m=next(x for x in o.get(root(village)+'/members').json() if x['user_id']==pu['id'])
    o.put(root(village)+'/members/'+m['id'],json={'status':'removed','role':'member'})
    assert p.get('/api/notifications').json()==[]
    with SessionLocal() as db:assert db.scalars(select(Notification).where(Notification.user_id==pu['id'])).all()==[]
