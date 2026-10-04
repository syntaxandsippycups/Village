import os,tempfile
from pathlib import Path
os.environ['APP_ENV']='test'
os.environ['VERIFY_EMAIL']='false'
os.environ['DATABASE_URL']=os.getenv('VILLAGE_TEST_DATABASE_URL','sqlite:///'+str(Path(tempfile.mkdtemp())/'test.db'))
os.environ['ALLOWED_ORIGINS']='http://localhost:3000,http://testserver,https://localhost,capacitor://localhost'
import pytest
from fastapi.testclient import TestClient
from app.server import app
from app.database import Base,engine
H={'X-Village-Client':'v2'}
@pytest.fixture(autouse=True)
def database():
    Base.metadata.drop_all(engine);Base.metadata.create_all(engine)
    yield
@pytest.fixture
def clients():
    def create(email,name='A member'):
        c=TestClient(app,headers=H)
        assert c.post('/api/auth/register',json={'name':name,'email':email,'password':'very-long-password-123','accept_terms':True}).status_code==201
        r=c.post('/api/auth/login',json={'email':email,'password':'very-long-password-123'})
        assert r.status_code==200,r.text
        return c,r.json()['user']
    return create
@pytest.fixture
def village(clients):
    owner,ou=clients('owner@example.org','Owner')
    church=owner.post('/api/churches',json={'name':'Community Church'}).json()
    person,pu=clients('member@example.org','Volunteer')
    person.post('/api/churches/join',json={'code':church['code']})
    pending=owner.get('/api/churches/'+church['id']+'/members').json()
    m=next(x for x in pending if x['user_id']==pu['id'])
    assert owner.put(f"/api/churches/{church['id']}/members/{m['id']}",json={'status':'approved','role':'member'}).status_code==200
    return owner,ou,person,pu,church
