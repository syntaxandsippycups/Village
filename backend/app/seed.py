"""Synthetic demo data only. Explicitly prohibited in production."""
from datetime import datetime,timedelta,timezone
from sqlalchemy import select
from . import config
from .database import SessionLocal
from .models import User,Church,Membership,Event,Need,MealTrain,MealSlot,RSVP,Volunteer
from .security import password_hash,set_code
from .migrate import main as migrate
PASSWORD='Village-demo-only-2026!'
def main():
    if config.PRODUCTION:raise RuntimeError('Demo data cannot be seeded in production.')
    migrate()
    with SessionLocal() as db:
        if db.scalar(select(User).where(User.email=='pastor@example.org')):
            print('Demo already exists. Login: pastor@example.org / '+PASSWORD);return
        people=[('pastor@example.org','Jordan Ellis','Pastor and a neighbor. Always happy to make another place at the table.',['Conversation','Prayer'],['Coffee maker'],['Church team']),
        ('member@example.org','Morgan Brooks','A parent, a piano player, and a believer in ordinary hospitality.',['Piano lessons','Babysitting'],['Pickup truck','Garden tools'],['Families','Tuesday life group']),
        ('student@example.org','Alex Chen','Engineering student. Up for a game night, a trail walk, or helping move boxes.',['Tutoring','Moving help'],['Board games'],['Undergrads']),
        ('neighbor@example.org','Evelyn Carter','Retired teacher. I love meeting young families and cheering on our students.',['Reading tutor','Cooking'],['Sewing machine'],['Older adults'])]
        users=[]
        for email,name,bio,skills,resources,groups in people:
            u=User(email=email,name=name,bio=bio,skills=skills,resources=resources,groups=groups,password_hash=password_hash(PASSWORD),verified=True,
                privacy={'directory':True,'email':True,'phone':False,'address':False,'household':False});db.add(u);users.append(u)
        c=Church(name='Grace Community · Demo',location='Ypsilanti, Michigan',timezone='America/New_York',require_approval=True);code=set_code(c);db.add(c);db.flush()
        for i,u in enumerate(users):db.add(Membership(user_id=u.id,church_id=c.id,role='owner' if i==0 else 'member',status='approved'))
        today=datetime.now(timezone.utc)
        titles=[('Sunday supper at our place','Nothing fancy—just soup, bread, and room around the table. Kids are welcome.','Morgan’s home',['Families'],12,1),('Undergrad game night','Bring your favorite game, or just yourself. We’ll have snacks and something for everyone.','Church fellowship room',['Undergrads'],30,0),('A little sideline encouragement','Our daughter has her first basketball game. We’d love some church family in the stands cheering her on.','Community gym',['Everyone'],None,1)]
        for i,(title,desc,location,audience,capacity,creator) in enumerate(titles):
            e=Event(church_id=c.id,created_by=users[creator].id,title=title,description=desc,location=location,audience=audience,starts_at=(today+timedelta(days=i+2)).replace(hour=22,minute=0,second=0,microsecond=0,tzinfo=None),capacity=capacity,official=i==1);db.add(e);db.flush()
            if i==0:db.add(RSVP(event_id=e.id,user_id=users[2].id,guest_count=1))
        for title,desc,category,location,needed in [('A hand with a few boxes','Evelyn is reorganizing her garage and could use two extra pairs of hands. A pickup truck would be wonderful.','Moving','Evelyn’s garage',2),('Church garden morning','An easy morning of weeding, planting, and getting to know a few people. No green thumb required.','Church service','Church grounds',8),('A little company on a Tuesday','Would anyone like to take a short walk and have a cup of tea?','Prayer & company','Meet at church',1)]:
            n=Need(church_id=c.id,created_by=users[0].id,title=title,description=desc,category=category,location=location,volunteers_needed=needed,due_date=today.date()+timedelta(days=8));db.add(n)
        start=today.date()+timedelta(days=2);end=start+timedelta(days=20)
        t=MealTrain(church_id=c.id,created_by=users[0].id,title='A warm welcome for baby Brooks',recipient='The Brooks family',description='A new baby, a full heart, and a few very tired parents. Let’s make dinner one less thing to think about.',adults=2,children=3,allergies='No peanuts. Please label ingredients.',preferences='Soups, pasta, fruit, and easy kid-friendly meals. Takeout or a grocery gift card is welcome, too.',address='100 Example Lane · fictional demo address',instructions='Text the family before arrival. Leave on the porch if the baby is sleeping.',contact='Contact the organizer through the updates below.',start_date=start,end_date=end,weekdays=[0,2,4],consent=True)
        db.add(t);db.flush();d=start;first=True
        while d<=end:
            if d.weekday() in [0,2,4]:
                s=MealSlot(train_id=t.id,date=d)
                if first:s.user_id=users[3].id;s.meal='Chicken noodle soup, rolls, and sliced fruit';first=False
                db.add(s)
            d+=timedelta(days=1)
        db.commit()
        print('Synthetic demo ready. Church code: '+code)
        print('Login: pastor@example.org or member@example.org or student@example.org')
        print('Password: '+PASSWORD)
if __name__=='__main__':main()
