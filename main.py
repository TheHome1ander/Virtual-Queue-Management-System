from fastapi import FastAPI, Depends, Request, Form, Response, Cookie
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy import func
from database import SessionLocal, engine, Base
from models import Shop, QueueItem, User
import uuid
from datetime import date

# Create Database Tables
Base.metadata.create_all(bind=engine)

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# --- Dependencies ---
def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()

def get_current_user(request: Request, db: Session):
    user_id = request.cookies.get("user_id")
    if not user_id: return None
    return db.query(User).filter(User.id == int(user_id)).first()

# --- ROUTES ---

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

# --- AUTH ---

@app.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...), role: str = Form(...), db: Session = Depends(get_db)):
    # --- DEBUG PRINTS (Check your terminal when clicking Sign In) ---
    print(f"\n--- LOGIN ATTEMPT ---")
    print(f"Input Username: '{username}'")
    print(f"Input Password: '{password}'")
    print(f"Input Role:     '{role}'")

    # Check if user exists at all
    existing_user = db.query(User).filter(User.username == username).first()
    if existing_user:
        print(f"Found User in DB -> ID: {existing_user.id}, Role: {existing_user.role}, Password: {existing_user.password}")
    else:
        print("User NOT FOUND in database.")

    # Strict Check
    user = db.query(User).filter(User.username == username, User.password == password, User.role == role).first()
    
    if not user:
        print("LOGIN FAILED: Credentials or Role did not match exactly.\n")
        return templates.TemplateResponse("index.html", {"request": request, "error": "Invalid credentials or wrong role selected"})
    
    print("LOGIN SUCCESS! Redirecting to dashboard...\n")
    response = RedirectResponse(url="/dashboard", status_code=303)
    response.set_cookie(key="user_id", value=str(user.id))
    return response

@app.post("/signup-owner")
async def signup_owner(
    username: str = Form(...), 
    password: str = Form(...),
    shop_name: str = Form(...),
    owner_real_name: str = Form(...),
    contact: str = Form(...),
    location: str = Form(...),
    db: Session = Depends(get_db)
):
    # 1. Create User
    if db.query(User).filter(User.username == username).first():
        return "Username taken"
    
    new_user = User(username=username, password=password, role="owner")
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    # 2. Create First Shop Request
    new_shop = Shop(
        owner_id=new_user.id,
        shop_name=shop_name,
        owner_real_name=owner_real_name,
        contact_details=contact,
        location=location,
        is_approved=False
    )
    db.add(new_shop)
    db.commit()
    
    # Auto login
    response = RedirectResponse(url="/dashboard", status_code=303)
    response.set_cookie(key="user_id", value=str(new_user.id))
    return response

@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie("user_id")
    return response

# --- DASHBOARDS ---

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user: return RedirectResponse("/")
    
    if user.role == "admin":
        pending_shops = db.query(Shop).filter(Shop.is_approved == False).all()
        active_shops = db.query(Shop).filter(Shop.is_approved == True).all()
        return templates.TemplateResponse("admin_dashboard.html", {
            "request": request, "pending": pending_shops, "active": active_shops
        })
    
    elif user.role == "owner":
        # Owner Logic: Get shops and calculate stats for TODAY
        my_shops = db.query(Shop).filter(Shop.owner_id == user.id).all()
        
        shops_data = []
        for shop in my_shops:
            if shop.is_approved:
                # Calculate stats
                total_today = db.query(QueueItem).filter(
                    QueueItem.shop_id == shop.id, 
                    QueueItem.created_at == date.today()
                ).count()
                
                waiting_now = db.query(QueueItem).filter(
                    QueueItem.shop_id == shop.id, 
                    QueueItem.status == "WAITING",
                    QueueItem.created_at == date.today()
                ).count()
                
                shops_data.append({
                    "obj": shop, "total": total_today, "waiting": waiting_now, "status": "Active"
                })
            else:
                shops_data.append({"obj": shop, "status": "Pending"})

        return templates.TemplateResponse("owner_dashboard.html", {"request": request, "shops": shops_data, "user": user})

# --- OWNER ACTIONS ---

@app.post("/add-shop")
async def add_shop(
    request: Request,
    shop_name: str = Form(...),
    owner_real_name: str = Form(...),
    contact: str = Form(...),
    location: str = Form(...),
    db: Session = Depends(get_db)
):
    user = get_current_user(request, db)
    if not user or user.role != "owner": return "Unauthorized"
    
    new_shop = Shop(
        owner_id=user.id, shop_name=shop_name, owner_real_name=owner_real_name,
        contact_details=contact, location=location, is_approved=False
    )
    db.add(new_shop)
    db.commit()
    return RedirectResponse(url="/dashboard", status_code=303)

# --- ADMIN ACTIONS ---

@app.post("/approve/{shop_id}")
async def approve(shop_id: int, db: Session = Depends(get_db)):
    shop = db.query(Shop).filter(Shop.id == shop_id).first()
    shop.is_approved = True
    db.commit()
    return RedirectResponse(url="/dashboard", status_code=303)

# --- CUSTOMER FLOW ---

@app.get("/q/{shop_id}", response_class=HTMLResponse)
async def customer_view(request: Request, shop_id: int, response: Response, db: Session = Depends(get_db)):
    # Check for existing session
    session_id = request.cookies.get("session_id")
    if not session_id:
        session_id = str(uuid.uuid4())
    
    shop = db.query(Shop).filter(Shop.id == shop_id).first()
    if not shop: return HTMLResponse("Shop not found")
    
    # Check if user already has a token for this shop today
    existing_token = db.query(QueueItem).filter(
        QueueItem.session_id == session_id,
        QueueItem.shop_id == shop_id,
        QueueItem.created_at == date.today()
    ).first()

    if not existing_token:
        # Generate new token automatically upon visiting
        last_item = db.query(QueueItem).filter(
            QueueItem.shop_id == shop_id,
            QueueItem.created_at == date.today()
        ).order_by(QueueItem.token_number.desc()).first()
        
        next_num = 1 if not last_item else last_item.token_number + 1
        new_item = QueueItem(shop_id=shop_id, session_id=session_id, token_number=next_num)
        db.add(new_item)
        db.commit()
        token_num = next_num
    else:
        token_num = existing_token.token_number

    # Calculate people ahead
    waiting_count = db.query(QueueItem).filter(
        QueueItem.shop_id == shop_id,
        QueueItem.status == "WAITING",
        QueueItem.created_at == date.today(),
        QueueItem.token_number < token_num
    ).count()

    resp = templates.TemplateResponse("customer_view.html", {
        "request": request, "shop": shop, "token": token_num, "ahead": waiting_count
    })
    resp.set_cookie(key="session_id", value=session_id)
    return resp