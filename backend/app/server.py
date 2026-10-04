import os
from pathlib import Path
from fastapi import FastAPI,Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from . import config
from .database import engine
from sqlalchemy import text
from .auth import router as auth
from .churches import router as churches
from .care import router as care
from .inbox import router as inbox
app=FastAPI(title='Village',version='2.0.0',docs_url='/api/docs' if not config.PRODUCTION else None,redoc_url=None)
app.add_middleware(CORSMiddleware,allow_origins=config.ALLOWED_ORIGINS,allow_credentials=True,allow_methods=['GET','POST','PUT','DELETE'],allow_headers=['Content-Type','X-Village-Client','Authorization','X-Device-Token'])
app.add_middleware(TrustedHostMiddleware,allowed_hosts=os.getenv('ALLOWED_HOSTS','localhost,127.0.0.1,testserver').split(','))
@app.middleware('http')
async def headers(request:Request,call_next):
    if request.url.path.startswith('/api'):
        length=request.headers.get('content-length','0')
        if length.isdigit() and int(length)>100000:return JSONResponse({'detail':'Request is too large.'},status_code=413)
        if request.method not in ['GET','HEAD','OPTIONS']:
            if request.headers.get('x-village-client')!='v2':return JSONResponse({'detail':'Missing request protection header.'},status_code=403)
            origin=request.headers.get('origin')
            if origin and origin not in config.ALLOWED_ORIGINS:return JSONResponse({'detail':'This origin is not allowed.'},status_code=403)
    response=await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Referrer-Policy']='no-referrer'
    response.headers['X-Frame-Options']='DENY'
    if request.url.path.startswith('/api'):response.headers['Cache-Control']='no-store'
    if config.PRODUCTION:response.headers['Strict-Transport-Security']='max-age=31536000; includeSubDomains'
    return response
app.include_router(auth);app.include_router(churches);app.include_router(care);app.include_router(inbox)
@app.get('/api/health')
def health():
    with engine.connect() as conn:conn.execute(text('SELECT 1'))
    return {'ok':True,'version':'2.0.0','push_configured':bool(config.FIREBASE_CREDENTIALS),'support_email':config.SUPPORT_EMAIL}
static=Path(__file__).resolve().parents[2]/'frontend'/'out'
if static.exists():app.mount('/',StaticFiles(directory=static,html=True),name='web')
