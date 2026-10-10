import uuid
from datetime import datetime, timezone
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

def utc_now():
    return datetime.now(timezone.utc)

class User(db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    avatar_color = db.Column(db.String(20), default='#3B82F6') # default blue
    created_at = db.Column(db.DateTime, default=utc_now)

    # Relationships
    owned_boards = db.relationship('Board', backref='owner', lazy=True, cascade="all, delete-orphan")
    board_memberships = db.relationship('BoardMember', backref='user', lazy=True, cascade="all, delete-orphan")
    assigned_tasks = db.relationship('Task', foreign_keys='Task.assigned_to_id', backref='assignee', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'avatar_color': self.avatar_color
        }

class Board(db.Model):
    __tablename__ = 'boards'

    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    title = db.Column(db.String(128), nullable=False)
    description = db.Column(db.Text, nullable=True)
    owner_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=utc_now)

    tasks = db.relationship('Task', backref='board', lazy=True, cascade="all, delete-orphan")
    members = db.relationship('BoardMember', backref='board', lazy=True, cascade="all, delete-orphan")
    activities = db.relationship('ActivityLog', backref='board', lazy=True, cascade="all, delete-orphan")

    def to_dict(self):
        return {
            'id': self.id,
            'uuid': self.uuid,
            'title': self.title,
            'description': self.description,
            'owner_id': self.owner_id,
            'owner': self.owner.to_dict() if self.owner else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'member_count': len(self.members) + 1 # includes owner
        }

class BoardMember(db.Model):
    __tablename__ = 'board_members'

    id = db.Column(db.Integer, primary_key=True)
    board_id = db.Column(db.Integer, db.ForeignKey('boards.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    joined_at = db.Column(db.DateTime, default=utc_now)

    __table_args__ = (db.UniqueConstraint('board_id', 'user_id', name='_board_user_uc'),)

class Task(db.Model):
    __tablename__ = 'tasks'

    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.String(256), nullable=False)
    description = db.Column(db.Text, nullable=True)
    column_name = db.Column(db.String(32), nullable=False, default='todo') # todo, doing, done
    position = db.Column(db.Integer, nullable=False, default=0)
    priority = db.Column(db.String(16), nullable=False, default='medium') # low, medium, high, urgent
    board_id = db.Column(db.Integer, db.ForeignKey('boards.id'), nullable=False)
    assigned_to_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=utc_now)
    updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now)

    creator = db.relationship('User', foreign_keys=[created_by_id])

    def to_dict(self):
        return {
            'id': self.id,
            'content': self.content,
            'description': self.description,
            'column_name': self.column_name,
            'position': self.position,
            'priority': self.priority,
            'board_id': self.board_id,
            'assigned_to': self.assignee.to_dict() if self.assignee else None,
            'created_by': self.creator.to_dict() if self.creator else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

class ActivityLog(db.Model):
    __tablename__ = 'activity_logs'

    id = db.Column(db.Integer, primary_key=True)
    board_id = db.Column(db.Integer, db.ForeignKey('boards.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    action = db.Column(db.String(256), nullable=False)
    timestamp = db.Column(db.DateTime, default=utc_now)

    user = db.relationship('User', foreign_keys=[user_id])

    def to_dict(self):
        return {
            'id': self.id,
            'board_id': self.board_id,
            'user': self.user.to_dict() if self.user else {'username': 'System', 'avatar_color': '#6B7280'},
            'action': self.action,
            'timestamp': self.timestamp.strftime('%H:%M:%S') if self.timestamp else ''
        }

