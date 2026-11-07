from datetime import datetime, timezone
from sqlalchemy import create_engine, String, Text, Integer, ForeignKey, DateTime, JSON, Boolean, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from .settings import settings
engine=create_engine(settings.database_url,pool_pre_ping=True)
Session=sessionmaker(engine,expire_on_commit=False)
def now(): return datetime.now(timezone.utc)
class Base(DeclarativeBase): pass
class Paper(Base):
    __tablename__='papers'
    id: Mapped[str]=mapped_column(String,primary_key=True)
    title: Mapped[str]=mapped_column(Text,default='')
    authors: Mapped[str]=mapped_column(Text,default='')
    affiliation: Mapped[str]=mapped_column(Text,default='')
    email: Mapped[str]=mapped_column(String,default='')
    track: Mapped[str]=mapped_column(String,default='General')
    profile: Mapped[str]=mapped_column(String,default='ieee')
    status: Mapped[str]=mapped_column(String,default='Submitted')
    latest: Mapped[int]=mapped_column(Integer,default=1)
    approved_version: Mapped[int|None]=mapped_column(Integer,nullable=True)
    created: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
class Version(Base):
    __tablename__='versions'
    __table_args__=(UniqueConstraint('paper_id','number'),)
    id: Mapped[str]=mapped_column(String,primary_key=True)
    paper_id: Mapped[str]=mapped_column(ForeignKey('papers.id'))
    number: Mapped[int]=mapped_column(Integer)
    filename: Mapped[str]=mapped_column(String)
    digest: Mapped[str]=mapped_column(String,index=True)
    path: Mapped[str]=mapped_column(Text)
    result: Mapped[dict]=mapped_column(JSON,default=dict)
    error: Mapped[str]=mapped_column(Text,default='')
    state: Mapped[str]=mapped_column(String,default='Queued')
    created: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
class Audit(Base):
    __tablename__='audit'
    id: Mapped[int]=mapped_column(Integer,primary_key=True)
    paper_id: Mapped[str]=mapped_column(String,index=True)
    action: Mapped[str]=mapped_column(String)
    details: Mapped[dict]=mapped_column(JSON,default=dict)
    created: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
class Message(Base):
    __tablename__='messages'
    id: Mapped[str]=mapped_column(String,primary_key=True)
    paper_id: Mapped[str]=mapped_column(ForeignKey('papers.id'))
    version: Mapped[int]=mapped_column(Integer)
    state: Mapped[str]=mapped_column(String,default='Pending approval')
    subject: Mapped[str]=mapped_column(Text)
    body: Mapped[str]=mapped_column(Text)
    approved: Mapped[bool]=mapped_column(Boolean,default=False)
    sent: Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)
    error: Mapped[str]=mapped_column(Text,default='')
class Event(Base):
    __tablename__='events'
    id: Mapped[str]=mapped_column(String,primary_key=True)
    state: Mapped[str]=mapped_column(String,default='Processing')
    result: Mapped[dict]=mapped_column(JSON,default=dict)

class Conference(Base):
    __tablename__='agent_conferences'
    id: Mapped[str]=mapped_column(String,primary_key=True)
    config: Mapped[dict]=mapped_column(JSON)
    enabled: Mapped[bool]=mapped_column(Boolean,default=False)
    publication: Mapped[dict]=mapped_column(JSON,default=dict)
    exception: Mapped[str]=mapped_column(Text,default='')

class Enrollment(Base):
    __tablename__='agent_enrollments'
    __table_args__=(UniqueConstraint('conference_id','external_id'),)
    id: Mapped[str]=mapped_column(String,primary_key=True)
    conference_id: Mapped[str]=mapped_column(ForeignKey('agent_conferences.id'))
    external_id: Mapped[str]=mapped_column(String)
    paper_id: Mapped[str]=mapped_column(ForeignKey('papers.id'),unique=True)
    handled_version: Mapped[int]=mapped_column(Integer,default=0)
    state: Mapped[str]=mapped_column(String,default='Received')
    deadline: Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)
    details: Mapped[dict]=mapped_column(JSON,default=dict)

class Receipt(Base):
    __tablename__='agent_receipts'
    id: Mapped[str]=mapped_column(String,primary_key=True)
    conference_id: Mapped[str]=mapped_column(String)
    state: Mapped[str]=mapped_column(String)
    details: Mapped[dict]=mapped_column(JSON,default=dict)

class Dispatch(Base):
    __tablename__='agent_dispatches'
    id: Mapped[str]=mapped_column(String,primary_key=True)
    conference_id: Mapped[str]=mapped_column(String,index=True)
    paper_id: Mapped[str]=mapped_column(String)
    version: Mapped[int]=mapped_column(Integer)
    kind: Mapped[str]=mapped_column(String)
    recipient: Mapped[str]=mapped_column(String)
    subject: Mapped[str]=mapped_column(Text)
    body: Mapped[str]=mapped_column(Text)
    attachment: Mapped[str]=mapped_column(Text,default='')
    state: Mapped[str]=mapped_column(String,default='Pending')
    error: Mapped[str]=mapped_column(Text,default='')
    created: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
    sent: Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)
