"""Explicit schema initialization, versioned to prevent silent incompatible upgrades."""
from sqlalchemy import select
from .database import Base,engine,SessionLocal
from .models import SchemaVersion
VERSION=1
def main():
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        versions=db.scalars(select(SchemaVersion.version)).all()
        if versions and max(versions)!=VERSION:raise RuntimeError('Unknown schema version; restore a compatible release.')
        if not versions:db.add(SchemaVersion(version=VERSION));db.commit()
    print('Village v2 schema version 1 ready.')
if __name__=='__main__':main()
