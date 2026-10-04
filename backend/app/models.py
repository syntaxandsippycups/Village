"""All v2 tables are isolated from the original unauthenticated prototype."""
import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, Integer, Boolean, DateTime, Date, JSON, ForeignKey, UniqueConstraint
from .database import Base

def uid(): return str(uuid.uuid4())
def now(): return datetime.now(timezone.utc).replace(tzinfo=None)
class User(Base):
    __tablename__ = 'v2_users'
    id = Column(String(36), primary_key=True, default=uid)
    email = Column(String(254), unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    name = Column(String(120), nullable=False)
    phone = Column(String(50), default='')
    address = Column(String(500), default='')
    household = Column(String(500), default='')
    bio = Column(String(2000), default='')
    skills = Column(JSON, default=list)
    resources = Column(JSON, default=list)
    groups = Column(JSON, default=list)
    available = Column(Boolean, default=True)
    privacy = Column(JSON, default=lambda: {'directory': True, 'email': False, 'phone': False, 'address': False, 'household': False})
    preferences = Column(JSON, default=lambda: {'events': True, 'needs': True, 'meals': True, 'community': True, 'reminders': True, 'in_app': True, 'email': False, 'push': False})
    verified = Column(Boolean, default=False)
    created_at = Column(DateTime, default=now)
class Session(Base):
    __tablename__ = 'v2_sessions'
    id = Column(String(64), primary_key=True)
    user_id = Column(String(36), ForeignKey('v2_users.id', ondelete='CASCADE'), index=True)
    expires_at = Column(DateTime, nullable=False)
class AuthToken(Base):
    __tablename__ = 'v2_auth_tokens'
    id = Column(String(64), primary_key=True)
    user_id = Column(String(36), ForeignKey('v2_users.id', ondelete='CASCADE'))
    purpose = Column(String(20), nullable=False)
    expires_at = Column(DateTime, nullable=False)
class Church(Base):
    __tablename__ = 'v2_churches'
    id = Column(String(36), primary_key=True, default=uid)
    name = Column(String(150), nullable=False)
    location = Column(String(200), default='')
    timezone = Column(String(80), default='America/New_York')
    code_hash = Column(String(64), unique=True, nullable=False)
    code_encrypted = Column(Text, nullable=False)
    require_approval = Column(Boolean, default=True)
    created_at = Column(DateTime, default=now)
class Membership(Base):
    __tablename__ = 'v2_memberships'
    id = Column(String(36), primary_key=True, default=uid)
    user_id = Column(String(36), ForeignKey('v2_users.id', ondelete='CASCADE'), nullable=False)
    church_id = Column(String(36), ForeignKey('v2_churches.id', ondelete='CASCADE'), nullable=False, index=True)
    role = Column(String(20), default='member')
    status = Column(String(20), default='pending')
    __table_args__ = (UniqueConstraint('user_id', 'church_id'),)
class Event(Base):
    __tablename__ = 'v2_events'
    id = Column(String(36), primary_key=True, default=uid)
    church_id = Column(String(36), ForeignKey('v2_churches.id', ondelete='CASCADE'), nullable=False, index=True)
    created_by = Column(String(36), ForeignKey('v2_users.id', ondelete='CASCADE'), nullable=False)
    title = Column(String(180), nullable=False)
    description = Column(Text, default='')
    location = Column(String(500), default='')
    starts_at = Column(DateTime, nullable=False)
    ends_at = Column(DateTime, nullable=True)
    audience = Column(JSON, default=list)
    capacity = Column(Integer, nullable=True)
    official = Column(Boolean, default=False)
    cancelled = Column(Boolean, default=False)
    created_at = Column(DateTime, default=now)
class RSVP(Base):
    __tablename__ = 'v2_rsvps'
    id = Column(String(36), primary_key=True, default=uid)
    event_id = Column(String(36), ForeignKey('v2_events.id', ondelete='CASCADE'), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey('v2_users.id', ondelete='CASCADE'), nullable=False)
    guest_count = Column(Integer, default=0)
    note = Column(String(500), default='')
    __table_args__ = (UniqueConstraint('event_id','user_id'),)
class Need(Base):
    __tablename__ = 'v2_needs'
    id = Column(String(36), primary_key=True, default=uid)
    church_id = Column(String(36), ForeignKey('v2_churches.id', ondelete='CASCADE'), nullable=False, index=True)
    created_by = Column(String(36), ForeignKey('v2_users.id', ondelete='CASCADE'), nullable=False)
    title = Column(String(180), nullable=False)
    description = Column(Text, default='')
    category = Column(String(80), default='Practical help')
    location = Column(String(500), default='')
    volunteers_needed = Column(Integer, default=1)
    due_date = Column(Date, nullable=True)
    status = Column(String(20), default='open')
    on_behalf = Column(String(120), default='')
    consent = Column(Boolean, default=False)
    created_at = Column(DateTime, default=now)
class Volunteer(Base):
    __tablename__ = 'v2_volunteers'
    id = Column(String(36), primary_key=True, default=uid)
    need_id = Column(String(36), ForeignKey('v2_needs.id', ondelete='CASCADE'), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey('v2_users.id', ondelete='CASCADE'), nullable=False)
    note = Column(String(500), default='')
    __table_args__ = (UniqueConstraint('need_id','user_id'),)
class MealTrain(Base):
    __tablename__ = 'v2_meal_trains'
    id = Column(String(36), primary_key=True, default=uid)
    church_id = Column(String(36), ForeignKey('v2_churches.id', ondelete='CASCADE'), nullable=False, index=True)
    created_by = Column(String(36), ForeignKey('v2_users.id', ondelete='CASCADE'), nullable=False)
    title = Column(String(180), nullable=False)
    recipient = Column(String(120), nullable=False)
    description = Column(Text, default='')
    adults = Column(Integer, default=2)
    children = Column(Integer, default=0)
    allergies = Column(String(1000), default='')
    preferences = Column(String(1000), default='')
    address = Column(String(500), default='')
    instructions = Column(String(1500), default='')
    delivery_window = Column(String(200), default='5–6 PM')
    contact = Column(String(250), default='')
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    weekdays = Column(JSON, default=list)
    consent = Column(Boolean, nullable=False)
    closed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=now)
class MealSlot(Base):
    __tablename__ = 'v2_meal_slots'
    id = Column(String(36), primary_key=True, default=uid)
    train_id = Column(String(36), ForeignKey('v2_meal_trains.id', ondelete='CASCADE'), nullable=False, index=True)
    date = Column(Date, nullable=False)
    user_id = Column(String(36), ForeignKey('v2_users.id', ondelete='SET NULL'), nullable=True)
    meal = Column(String(1000), default='')
    note = Column(String(1000), default='')
    delivered = Column(Boolean, default=False)
    __table_args__ = (UniqueConstraint('train_id','date'),)
class Comment(Base):
    __tablename__ = 'v2_comments'
    id = Column(String(36), primary_key=True, default=uid)
    church_id = Column(String(36), ForeignKey('v2_churches.id', ondelete='CASCADE'), nullable=False)
    kind = Column(String(20), nullable=False)
    target_id = Column(String(36), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey('v2_users.id', ondelete='CASCADE'), nullable=False)
    text = Column(String(2000), nullable=False)
    created_at = Column(DateTime, default=now)
class Notification(Base):
    __tablename__ = 'v2_notifications'
    id = Column(String(36), primary_key=True, default=uid)
    user_id = Column(String(36), ForeignKey('v2_users.id', ondelete='CASCADE'), nullable=False, index=True)
    church_id = Column(String(36), ForeignKey('v2_churches.id', ondelete='CASCADE'), nullable=False)
    category = Column(String(20), nullable=False)
    title = Column(String(200), nullable=False)
    body = Column(String(1500), default='')
    link = Column(String(300), default='')
    dedup_key = Column(String(200), unique=True, nullable=False)
    read = Column(Boolean, default=False)
    in_app = Column(Boolean, default=True)
    email_state = Column(String(20), default='disabled')
    push_state = Column(String(20), default='disabled')
    attempts = Column(Integer, default=0)
    last_error = Column(String(150), default='')
    next_attempt = Column(DateTime, default=now)
    created_at = Column(DateTime, default=now)
class Mail(Base):
    __tablename__ = 'v2_mail'
    id = Column(String(36), primary_key=True, default=uid)
    recipient = Column(String(254), nullable=False)
    subject = Column(String(200), nullable=False)
    body = Column(Text, nullable=False)
    sent = Column(Boolean, default=False)
    attempts = Column(Integer, default=0)
    next_attempt = Column(DateTime, default=now)
class Device(Base):
    __tablename__ = 'v2_devices'
    id = Column(String(36), primary_key=True, default=uid)
    user_id = Column(String(36), ForeignKey('v2_users.id', ondelete='CASCADE'), nullable=False)
    token = Column(String(1000), unique=True, nullable=False)
    platform = Column(String(20), nullable=False)
class Block(Base):
    __tablename__ = 'v2_blocks'
    id = Column(String(36), primary_key=True, default=uid)
    user_id = Column(String(36), ForeignKey('v2_users.id', ondelete='CASCADE'), nullable=False)
    blocked_id = Column(String(36), ForeignKey('v2_users.id', ondelete='CASCADE'), nullable=False)
    __table_args__ = (UniqueConstraint('user_id','blocked_id'),)
class Report(Base):
    __tablename__ = 'v2_reports'
    id = Column(String(36), primary_key=True, default=uid)
    church_id = Column(String(36), ForeignKey('v2_churches.id', ondelete='CASCADE'), nullable=False)
    user_id = Column(String(36), ForeignKey('v2_users.id', ondelete='CASCADE'), nullable=False)
    kind = Column(String(20), nullable=False)
    target_id = Column(String(36), nullable=False)
    reason = Column(String(1500), nullable=False)
    resolved = Column(Boolean, default=False)
    created_at = Column(DateTime, default=now)
class RateLimit(Base):
    __tablename__ = 'v2_rate_limits'
    key = Column(String(64), primary_key=True)
    count = Column(Integer, default=0)
    resets_at = Column(DateTime, nullable=False)
class SchemaVersion(Base):
    __tablename__ = 'v2_schema_version'
    version = Column(Integer, primary_key=True)
