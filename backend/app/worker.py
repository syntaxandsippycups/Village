"""Run continuously or invoke --once from a scheduler. Jobs are durable and retry."""
import argparse,json,logging,smtplib,time
from email.message import EmailMessage
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
from sqlalchemy import select,delete
from .database import SessionLocal
from .models import Church,MealTrain,MealSlot,Event,RSVP,Need,Volunteer,User,Notification,Mail,Device,Session,AuthToken,RateLimit,Membership,now
from .notifications import notify
from . import config
log=logging.getLogger('village.worker')

def reminders(db):
    for s,t,c in db.execute(select(MealSlot,MealTrain,Church).join(MealTrain,MealSlot.train_id==MealTrain.id).join(Church,MealTrain.church_id==Church.id).where(MealSlot.user_id!=None,MealSlot.delivered==False,MealTrain.closed==False)):
        local=datetime.now(ZoneInfo(c.timezone));days=(s.date-local.date()).days
        # Catch a missed scheduled run later on the same day, without duplicates.
        if days in [7,1,0] and local.hour>=8:
            notify(db,c.id,s.user_id,'meals','Your meal commitment is coming up',f'{t.title}: {s.date.isoformat()}. Check delivery details in Village.',f'/?view=meals&id={t.id}&church={c.id}',f'remind-meal:{s.id}:{s.user_id}:{s.date}:{days}',reminder=True)
    for r,e in db.execute(select(RSVP,Event).join(Event,RSVP.event_id==Event.id).where(Event.cancelled==False,Event.starts_at>now(),Event.starts_at<=now()+timedelta(hours=24))):
        notify(db,e.church_id,r.user_id,'events','Your event is coming up',e.title,f'/?view=events&id={e.id}&church={e.church_id}',f'remind-event:{e.id}:{e.starts_at.isoformat()}:{r.user_id}',reminder=True)
    for v,n,c in db.execute(select(Volunteer,Need,Church).join(Need,Volunteer.need_id==Need.id).join(Church,Need.church_id==Church.id).where(Need.status=='open',Need.due_date!=None)):
        local=datetime.now(ZoneInfo(c.timezone))
        if n.due_date==local.date()+timedelta(days=1) and local.hour>=8:
            notify(db,c.id,v.user_id,'needs','Your volunteer commitment is tomorrow',n.title,f'/?view=needs&id={n.id}&church={c.id}',f'remind-need:{n.id}:{n.due_date}:{v.user_id}',reminder=True)

def email_content(subject, body):
    """Build escaped HTML plus a readable plain-text alternative."""
    import re
    from html import escape
    from urllib.parse import urlsplit, parse_qs

    base = urlsplit(config.WEB_URL)
    target = None
    for candidate in re.findall(r'https?://[^\s<>]+', body):
        parsed = urlsplit(candidate)
        if (parsed.scheme, parsed.netloc) == (base.scheme, base.netloc):
            target = candidate
            break

    action = parse_qs(urlsplit(target).query).get('action', [''])[0] if target else ''
    is_verify = subject == 'Verify your Village email' and action == 'verify'
    is_reset = subject == 'Reset your Village password' and action == 'reset'
    if is_verify:
        heading = 'Welcome to Village.'
        paragraphs = [
            'One small step before you connect with your church family: confirm your email address.',
            'Select the button below to verify your email and continue setting up your account.',
        ]
        button = 'Verify my email'
        footnote = 'This link expires in one hour. If you did not create a Village account, you can safely ignore this email.'
    elif is_reset:
        heading = 'Reset your password.'
        paragraphs = ['We received a request to reset your Village password.', 'Select the button below to choose a new password.']
        button = 'Reset my password'
        footnote = 'This link expires in one hour. If you did not request a reset, ignore this email. Your password will stay the same.'
    else:
        heading = subject
        paragraphs = [line.strip() for line in body.splitlines() if line.strip() and line.strip() != target]
        button = 'Open Village'
        footnote = 'You can choose which community updates you receive in Village → Settings.'

    text = 'Village — Your church. Your people. Life together.\n\n' + heading + '\n\n' + '\n\n'.join(paragraphs)
    if target:
        text += '\n\n' + button + ':\n' + target
    text += '\n\n' + footnote + '\n\nQuestions? Contact ' + config.SUPPORT_EMAIL
    content = ''.join('<p style="margin:0 0 18px;font-size:16px;line-height:1.65;color:#4c514b;">' + escape(p) + '</p>' for p in paragraphs)
    if target:
        url = escape(target, quote=True)
        content += '<table role="presentation" cellpadding="0" cellspacing="0" style="margin:26px 0;"><tr><td bgcolor="#456650" style="border-radius:8px;"><a href="' + url + '" style="display:inline-block;padding:15px 24px;color:#ffffff;text-decoration:none;font-size:16px;font-weight:bold;border:1px solid #456650;border-radius:8px;">' + escape(button) + '</a></td></tr></table>'
        content += '<p style="font-size:13px;line-height:1.6;color:#697067;">If the button does not work, copy and paste this link into your browser:<br><a href="' + url + '" style="color:#456650;word-break:break-all;">' + escape(target) + '</a></p>'
    support = escape(config.SUPPORT_EMAIL, quote=True)
    html = '''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>''' + escape(subject) + '''</title></head>
<body style="margin:0;padding:0;background:#f6f3eb;font-family:Arial,Helvetica,sans-serif;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" bgcolor="#f6f3eb"><tr><td align="center" style="padding:32px 16px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:560px;"><tr><td style="padding:0 8px 24px;">
<div style="font-family:Georgia,serif;font-size:34px;color:#36533f;">Village</div>
<div style="margin-top:8px;font-size:13px;color:#6a7168;">Your church. Your people. Life together.</div>
</td></tr><tr><td bgcolor="#ffffff" style="padding:32px 28px;border:1px solid #e5e3da;border-radius:12px;">
<h1 style="margin:0 0 22px;font-family:Georgia,serif;font-size:28px;font-weight:normal;color:#2c3b30;">''' + escape(heading) + '</h1>' + content + '''
<p style="margin:24px 0 0;padding-top:20px;border-top:1px solid #ecebe4;font-size:13px;line-height:1.6;color:#697067;">''' + escape(footnote) + '''</p>
</td></tr><tr><td style="padding:22px 8px;font-size:12px;line-height:1.6;color:#697067;">Questions? <a href="mailto:''' + support + '''" style="color:#456650;">''' + support + '''</a></td></tr>
</table></td></tr></table></body></html>'''
    return text, html

def send_email(email, subject, body):
    from email.utils import formatdate, make_msgid, parseaddr
    text, html = email_content(subject, body)
    if config.RESEND_API_KEY:
        from urllib.request import Request, urlopen
        payload = json.dumps({'from': config.SMTP_FROM, 'to': [email], 'subject': subject, 'text': text, 'html': html, 'reply_to': config.SUPPORT_EMAIL}).encode()
        request = Request('https://api.resend.com/emails', data=payload, headers={'Authorization': 'Bearer ' + config.RESEND_API_KEY, 'Content-Type': 'application/json'})
        with urlopen(request, timeout=20) as result:
            if result.status not in (200, 201):
                raise RuntimeError('Email provider rejected delivery.')
        return
    if not config.SMTP_HOST:
        if config.PRODUCTION:
            raise RuntimeError('SMTP is not configured.')
        from pathlib import Path
        folder = Path('dev-mail')
        folder.mkdir(exist_ok=True)
        name = str(time.time_ns())
        (folder / (name + '.txt')).write_text(f'To: {email}\nSubject: {subject}\n\n{text}', encoding='utf-8')
        (folder / (name + '.html')).write_text(html, encoding='utf-8')
        return
    msg = EmailMessage()
    msg['From'] = config.SMTP_FROM
    msg['To'] = email
    msg['Subject'] = subject
    msg['Reply-To'] = config.SUPPORT_EMAIL
    msg['Date'] = formatdate(localtime=False, usegmt=True)
    sender = parseaddr(config.SMTP_FROM)[1]
    domain = sender.rsplit('@', 1)[-1] if '@' in sender else None
    msg['Message-ID'] = make_msgid(domain=domain)
    msg.set_content(text)
    msg.add_alternative(html, subtype='html')
    with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=20) as smtp:
        if config.SMTP_TLS:
            smtp.starttls()
        if config.SMTP_USER:
            smtp.login(config.SMTP_USER, config.SMTP_PASSWORD)
        smtp.send_message(msg)


def send_push(db,user,n):
    if not config.FIREBASE_CREDENTIALS:raise RuntimeError('Firebase push delivery is not configured.')
    import firebase_admin
    from firebase_admin import credentials,messaging
    if not firebase_admin._apps:firebase_admin.initialize_app(credentials.Certificate(json.loads(config.FIREBASE_CREDENTIALS)))
    tokens=db.scalars(select(Device).where(Device.user_id==user.id)).all()
    for d in tokens:
        try:
            # Keep sensitive names/addresses/meals off lock screens.
            messaging.send(messaging.Message(token=d.token,notification=messaging.Notification(title='Village',body='You have a community update. Open Village to see it.'),data={'link':n.link}))
        except messaging.UnregisteredError:db.delete(d)

def once():
    with SessionLocal() as db:
        reminders(db);db.commit()
    # Keep claims serialized inside the transaction; skip locked rows on Postgres.
    with SessionLocal() as db:
        pending=db.scalars(select(Mail).where(Mail.sent==False,Mail.attempts<8,Mail.next_attempt<=now()).with_for_update(skip_locked=True).limit(25)).all()
        for m in pending:
            try:send_email(m.recipient,m.subject,m.body);m.sent=True;m.body='[Delivered; link removed]'
            except Exception as ex:
                m.attempts+=1;m.next_attempt=now()+timedelta(seconds=min(3600,60*2**m.attempts));log.error('Mail delivery failed: %s',type(ex).__name__)
        db.commit()
    with SessionLocal() as db:
        pending=db.scalars(select(Notification).where(((Notification.email_state=='pending')|(Notification.push_state=='pending')),Notification.attempts<8,Notification.next_attempt<=now()).with_for_update(skip_locked=True).limit(50)).all()
        for n in pending:
            u=db.get(User,n.user_id);p=u.preferences if u else {}
            active=db.scalar(select(Membership).where(Membership.user_id==n.user_id,Membership.church_id==n.church_id,Membership.status=='approved'))
            allowed=active and p.get(n.category,True) and (not n.dedup_key.startswith('remind-') or p.get('reminders',True))
            failed=False
            for channel in ['email','push']:
                if getattr(n,channel+'_state')!='pending':continue
                if not allowed or not p.get(channel,False):setattr(n,channel+'_state','disabled');continue
                try:
                    if channel=='email':send_email(u.email,n.title,n.body+'\n\n'+config.WEB_URL+n.link+'\n\nChange notification preferences in Village → Settings.')
                    else:send_push(db,u,n)
                    setattr(n,channel+'_state','sent')
                except Exception as ex:
                    n.last_error=type(ex).__name__;failed=True;log.error('Notification delivery failed: %s',type(ex).__name__)
            if failed:n.attempts+=1;n.next_attempt=now()+timedelta(seconds=min(3600,60*2**n.attempts))
        db.execute(delete(Session).where(Session.expires_at<now()))
        db.execute(delete(AuthToken).where(AuthToken.expires_at<now()))
        db.execute(delete(RateLimit).where(RateLimit.resets_at<now()-timedelta(days=1)))
        db.execute(delete(Notification).where(Notification.created_at<now()-timedelta(days=90)))
        db.commit()

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--once',action='store_true');args=parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    while True:
        try:once()
        except Exception as ex:log.error('Worker pass failed: %s',type(ex).__name__)
        if args.once:break
        time.sleep(60)
if __name__=='__main__':main()
