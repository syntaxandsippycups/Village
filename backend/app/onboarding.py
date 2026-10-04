"""Invitation membership and canonical group labels. No schema changes needed."""
import unicodedata
from fastapi import HTTPException
from sqlalchemy import select
from .models import Church, Membership, User
from .security import digest, normalize_code, blocked_ids

GROUPS = ['Families', 'Parents of young children', 'New parents', 'Single adults',
          'Young adults', 'Undergrads', 'Married couples', 'Empty nesters',
          'Older adults', 'New to church', 'Church team']

def label(value):
    return ' '.join(unicodedata.normalize('NFKC', value).split())

def group_key(value):
    return label(value).casefold()

def canonical_groups(values, options=()):
    known = {group_key(x): label(x) for x in options}
    known.update({group_key(x): x for x in GROUPS})
    result = []
    seen = set()
    for value in values:
        clean = label(value)
        key = group_key(clean)
        if not clean or key in seen:
            continue
        seen.add(key)
        result.append(known.get(key, clean))
    return result

def group_options(db, user, church_id=None):
    churches = select(Membership.church_id).where(Membership.user_id == user.id, Membership.status == 'approved')
    if church_id:
        churches = churches.where(Membership.church_id == church_id)
    users = db.scalars(select(User).join(Membership, Membership.user_id == User.id)
        .where(Membership.church_id.in_(churches), Membership.status == 'approved')
        .order_by(User.created_at, User.id)).unique().all()
    blocked = blocked_ids(db, user)
    values = list(GROUPS)
    for person in users:
        if person.id not in blocked and (person.privacy or {}).get('directory', True):
            values.extend(person.groups or [])
    return sorted(canonical_groups(values), key=group_key)

def invited_church(db, code):
    church = db.scalar(select(Church).where(Church.code_hash == digest(normalize_code(code))).with_for_update())
    if not church:
        raise HTTPException(404, 'That invitation is invalid or has been replaced. Ask your church for its current invitation.')
    return church

def accept_invitation(db, user, church):
    membership = db.scalar(select(Membership).where(Membership.user_id == user.id, Membership.church_id == church.id))
    if membership and membership.status == 'removed':
        raise HTTPException(403, 'Your access was removed. Please contact a church administrator.')
    if not membership:
        membership = Membership(user_id=user.id, church_id=church.id, role='member', status='approved')
        db.add(membership)
    elif membership.status == 'pending':
        membership.status = 'approved'
    db.flush()
    return membership
