from fastapi import FastAPI, Depends, HTTPException, status
from sqlalchemy.orm import Session
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from datetime import timedelta

from api import models, schemas, auth
from db.database import engine, get_db

app = FastAPI()

models.Base.metadata.create_all(bind=engine)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


@app.post("/register", response_model=schemas.UserBase)
def register(user: schemas.UserCreate, db: Session = Depends(get_db)):
    db_user = (
        db.query(models.User).filter(models.User.username == user.username).first()
    )
    if db_user:
        raise HTTPException(status_code=400, detail="Username already registered")
    hashed_password = auth.get_password_hash(user.password)
    db_user = models.User(username=user.username, hashed_password=hashed_password)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


@app.post("/token", response_model=dict)
def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)
):
    user = authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(status_code=400, detail="Incorrect username or password")
    access_token_expires = timedelta(minutes=auth.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = auth.create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}


def authenticate_user(db: Session, username: str, password: str):
    user = db.query(models.User).filter(models.User.username == username).first()
    if not user or not auth.verify_password(password, user.hashed_password):
        return False
    return user


@app.post("/posts/", response_model=schemas.PostResponse)
def create_post(
    post: schemas.PostCreate,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
):
    user = get_current_user(db, token)
    db_post = models.Post(**post.dict(), user_id=user.id)
    db.add(db_post)
    db.commit()
    db.refresh(db_post)
    return db_post


@app.post("/posts/{post_id}/comments", response_model=schemas.CommentResponse)
def add_comment(
    post_id: int,
    comment: schemas.CommentCreate,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
):
    user = get_current_user(db, token)
    db_comment = models.Comment(**comment.dict(), post_id=post_id, user_id=user.id)
    db.add(db_comment)
    db.commit()
    db.refresh(db_comment)
    return db_comment


@app.post("/posts/{post_id}/like", response_model=schemas.LikeResponse)
def like_post(
    post_id: int, token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
):
    user = get_current_user(db, token)
    db_like = models.Like(post_id=post_id, user_id=user.id)
    db.add(db_like)
    db.commit()
    db.refresh(db_like)
    return db_like


def get_current_user(db: Session, token: str):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, auth.SECRET_KEY, algorithms=[auth.ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    user = db.query(models.User).filter(models.User.username == username).first()
    if user is None:
        raise credentials_exception
    return user
