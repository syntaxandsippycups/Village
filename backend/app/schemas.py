from datetime import date, datetime, timedelta
from typing import Literal, Annotated
from zoneinfo import ZoneInfo
from pydantic import BaseModel, ConfigDict, Field, EmailStr, field_validator, model_validator
Text120 = Annotated[str, Field(min_length=1, max_length=120)]
Tag = Annotated[str, Field(min_length=1, max_length=80)]
class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
class Credentials(Strict):
    email: EmailStr
    password: str = Field(min_length=12, max_length=256)
class Register(Credentials):
    name: Text120
    accept_terms: Literal[True]
class Login(Strict):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)
    native: bool = False
class EmailRequest(Strict):
    email: EmailStr
class TokenRequest(Strict):
    token: str = Field(min_length=20, max_length=200)
class Reset(TokenRequest):
    password: str = Field(min_length=12, max_length=256)
class DeleteAccount(Strict):
    password: str = Field(min_length=1, max_length=256)
class Privacy(Strict):
    directory: bool = True
    email: bool = False
    phone: bool = False
    address: bool = False
    household: bool = False
class Preferences(Strict):
    events: bool = True
    needs: bool = True
    meals: bool = True
    community: bool = True
    reminders: bool = True
    in_app: bool = True
    email: bool = False
    push: bool = False
class Profile(Strict):
    name: Text120
    phone: str = Field(default='', max_length=50)
    address: str = Field(default='', max_length=500)
    household: str = Field(default='', max_length=500)
    bio: str = Field(default='', max_length=2000)
    skills: list[Tag] = Field(default_factory=list, max_length=30)
    resources: list[Tag] = Field(default_factory=list, max_length=30)
    groups: list[Tag] = Field(default_factory=list, max_length=20)
    available: bool = True
    privacy: Privacy = Field(default_factory=Privacy)
class ChurchCreate(Strict):
    name: str = Field(min_length=2, max_length=150)
    location: str = Field(default='', max_length=200)
    timezone: str = 'America/New_York'
    require_approval: bool = True
    @field_validator('timezone')
    @classmethod
    def timezone_valid(cls, value):
        try: ZoneInfo(value)
        except Exception: raise ValueError('Use a valid IANA timezone.')
        return value
class Join(Strict):
    code: str = Field(min_length=6, max_length=100)
class MemberUpdate(Strict):
    status: Literal['approved','pending','removed']
    role: Literal['member','admin'] = 'member'
class EventData(Strict):
    title: str = Field(min_length=1, max_length=180)
    description: str = Field(default='', max_length=8000)
    location: str = Field(default='', max_length=500)
    starts_at: datetime
    ends_at: datetime | None = None
    audience: list[Tag] = Field(default_factory=list, max_length=20)
    capacity: int | None = Field(default=None, ge=1, le=10000)
    official: bool = False
    cancelled: bool = False
    @model_validator(mode='after')
    def times(self):
        for key in ['starts_at','ends_at']:
            value = getattr(self,key)
            if value is not None and value.tzinfo is None:
                raise ValueError('Event timestamps must include a timezone offset.')
        if self.ends_at and self.ends_at <= self.starts_at:
            raise ValueError('End must follow start.')
        return self
class RSVPData(Strict):
    guest_count: int = Field(default=0, ge=0, le=30)
    note: str = Field(default='', max_length=500)
class NeedData(Strict):
    title: str = Field(min_length=1, max_length=180)
    description: str = Field(default='', max_length=8000)
    category: Tag = 'Practical help'
    location: str = Field(default='', max_length=500)
    volunteers_needed: int = Field(default=1, ge=1, le=1000)
    due_date: date | None = None
    status: Literal['open','fulfilled','closed'] = 'open'
    on_behalf: str = Field(default='', max_length=120)
    consent: bool = False
    @model_validator(mode='after')
    def permission(self):
        if self.on_behalf and not self.consent: raise ValueError('Obtain permission before posting for someone else.')
        return self
class VolunteerData(Strict):
    note: str = Field(default='', max_length=500)
class MealData(Strict):
    title: str = Field(min_length=1, max_length=180)
    recipient: Text120
    description: str = Field(default='', max_length=8000)
    adults: int = Field(default=2, ge=1, le=100)
    children: int = Field(default=0, ge=0, le=100)
    allergies: str = Field(default='', max_length=1000)
    preferences: str = Field(default='', max_length=1000)
    address: str = Field(default='', max_length=500)
    instructions: str = Field(default='', max_length=1500)
    delivery_window: str = Field(default='5–6 PM', max_length=200)
    contact: str = Field(default='', max_length=250)
    start_date: date
    end_date: date
    weekdays: list[Annotated[int, Field(ge=0, le=6)]] = Field(min_length=1,max_length=7) # Monday=0, Sunday=6
    excluded_dates: list[date] = Field(default_factory=list, max_length=366)
    extra_dates: list[date] = Field(default_factory=list, max_length=366)
    consent: Literal[True]
    closed: bool = False
    @model_validator(mode='after')
    def schedule(self):
        if self.end_date < self.start_date or (self.end_date-self.start_date).days > 365:
            raise ValueError('Choose an ordered date range of no more than one year.')
        if len(set(self.weekdays)) != len(self.weekdays): raise ValueError('Weekdays must be unique.')
        if any(d < self.start_date or d > self.end_date for d in self.extra_dates+self.excluded_dates):
            raise ValueError('Individual dates must lie within the date range.')
        if not self.dates(): raise ValueError('Choose at least one meal date.')
        return self
    def dates(self):
        selected = set(self.extra_dates)
        current = self.start_date
        while current <= self.end_date:
            if current.weekday() in self.weekdays: selected.add(current)
            current += timedelta(days=1)
        return sorted(selected - set(self.excluded_dates))
class MealClaim(Strict):
    meal: str = Field(min_length=1,max_length=1000)
    note: str = Field(default='',max_length=1000)
    # Organizers can book for another approved member, with their permission.
    for_user_id: str | None = Field(default=None,max_length=36)
    consent: bool = False
class Delivered(Strict):
    delivered: bool = True
class CommentData(Strict):
    text: str = Field(min_length=1,max_length=2000)
class ReportData(Strict):
    kind: Literal['events','needs','meals','directory','comments']
    target_id: str = Field(min_length=1,max_length=36)
    reason: str = Field(min_length=5,max_length=1500)
class DeviceData(Strict):
    token: str = Field(min_length=20,max_length=1000)
    platform: Literal['android','ios']
