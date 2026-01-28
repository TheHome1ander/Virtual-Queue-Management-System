from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime, Date
from sqlalchemy.orm import relationship
from database import Base
from datetime import datetime, date

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    password = Column(String) 
    role = Column(String) # "admin", "owner"

class Shop(Base):
    __tablename__ = "shops"
    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"))
    
    # Shop Details
    shop_name = Column(String)
    owner_real_name = Column(String)
    contact_details = Column(String)
    location = Column(String)
    
    is_approved = Column(Boolean, default=False)
    registration_date = Column(DateTime, default=datetime.utcnow)
    
    owner = relationship("User", backref="shops")

class QueueItem(Base):
    __tablename__ = "queue_items"
    id = Column(Integer, primary_key=True, index=True)
    shop_id = Column(Integer, ForeignKey("shops.id"))
    session_id = Column(String) # Identifies customer without login
    token_number = Column(Integer)
    status = Column(String, default="WAITING") 
    created_at = Column(Date, default=date.today)