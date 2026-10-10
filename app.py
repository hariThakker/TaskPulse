import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)

import eventlet
eventlet.monkey_patch()

import os
import random
from functools import wraps
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_socketio import SocketIO, emit, join_room, leave_room
from config import Config
from models import db, User, Board, BoardMember, Task, ActivityLog

app = Flask(__name__)
app.config.from_object(Config)

db.init_app(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')



# Global presence tracker: board_uuid -> dict of sid -> user_info
presence_data = {}
# Mapping socket ID (sid) to user info & active room
socket_users = {}

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            if request.path.startswith('/api/'):
                return jsonify({'error': 'Unauthorized'}), 401
            return redirect(url_for('login_page'))
        return f(*args, **kwargs)
    return decorated_function

def get_current_user():
    if 'user_id' in session:
        return db.session.get(User, session['user_id'])
    return None


# Seed helper for quick test environment
def seed_demo_data():
    if User.query.first() is None:
        alice = User(username='Alice', email='alice@example.com', avatar_color='#EC4899')
        alice.set_password('password123')
        bob = User(username='Bob', email='bob@example.com', avatar_color='#10B981')
        bob.set_password('password123')
        charlie = User(username='Charlie', email='charlie@example.com', avatar_color='#8B5CF6')
        charlie.set_password('password123')

        db.session.add_all([alice, bob, charlie])
        db.session.commit()

        # Create demo board
        demo_board = Board(
            title='🚀 Real-Time Launch Board',
            description='Collaborative workspace with real-time drag-and-drop, presence avatars, and live sync!',
            owner_id=alice.id,
            uuid='demo-board-1234'
        )
        db.session.add(demo_board)
        db.session.commit()

        # Add Bob and Charlie to board
        bm1 = BoardMember(board_id=demo_board.id, user_id=bob.id)
        bm2 = BoardMember(board_id=demo_board.id, user_id=charlie.id)
        db.session.add_all([bm1, bm2])

        # Add sample tasks
        sample_tasks = [
            Task(content='🎨 Design Glassmorphic UI & Color System', description='Use vibrant gradients, dark theme, and micro-interactions.', column_name='todo', position=0, priority='high', board_id=demo_board.id, created_by_id=alice.id, assigned_to_id=alice.id),
            Task(content='⚡ Setup Flask-SocketIO Real-Time Engine', description='Handle websocket events for move_task, task_created, and user presence.', column_name='doing', position=0, priority='urgent', board_id=demo_board.id, created_by_id=alice.id, assigned_to_id=bob.id),
            Task(content='🔗 Implement Shareable UUID Invite Links', description='Allow anyone with the link to join workspace automatically.', column_name='doing', position=1, priority='medium', board_id=demo_board.id, created_by_id=bob.id, assigned_to_id=charlie.id),
            Task(content='👥 Add Active User Avatars & Presence Tracking', description='Show live online badges at the top bar when users connect.', column_name='done', position=0, priority='high', board_id=demo_board.id, created_by_id=charlie.id, assigned_to_id=alice.id),
            Task(content='🎯 Optimistic UI Drag and Drop with Rollback', description='Instant visual card move with automatic fallback if network fails.', column_name='done', position=1, priority='medium', board_id=demo_board.id, created_by_id=alice.id, assigned_to_id=bob.id)
        ]
        db.session.add_all(sample_tasks)

        # Activity log initial entries
        act1 = ActivityLog(board_id=demo_board.id, user_id=alice.id, action="created board '🚀 Real-Time Launch Board'")
        act2 = ActivityLog(board_id=demo_board.id, user_id=bob.id, action="moved task 'Setup Flask-SocketIO' to Doing")
        db.session.add_all([act1, act2])
        db.session.commit()

with app.app_context():
    db.create_all()
    seed_demo_data()

# -------------------------------------------------------------------
# Page Routes
# -------------------------------------------------------------------

@app.route('/')
def index_page():
    if 'user_id' not in session:
        return redirect(url_for('login_page'))
    return render_template('index.html', user=get_current_user())

@app.route('/login')
def login_page():
    if 'user_id' in session:
        return redirect(url_for('index_page'))
    return render_template('login.html')

@app.route('/board/<board_uuid>')
@login_required
def board_page(board_uuid):
    board = Board.query.filter_by(uuid=board_uuid).first()
    if not board:
        return render_template('404.html', message="Board not found"), 404
    
    current_user = get_current_user()
    # Check membership or auto-join if user has invite link
    is_member = (board.owner_id == current_user.id) or \
                (BoardMember.query.filter_by(board_id=board.id, user_id=current_user.id).first() is not None)
    
    if not is_member:
        # Auto join workspace via invite link!
        new_member = BoardMember(board_id=board.id, user_id=current_user.id)
        db.session.add(new_member)
        act = ActivityLog(board_id=board.id, user_id=current_user.id, action=f"joined board via invite link")
        db.session.add(act)
        db.session.commit()

    return render_template('board.html', board=board, user=current_user)

# -------------------------------------------------------------------
# REST API Endpoints
# -------------------------------------------------------------------

@app.route('/api/auth/register', methods=['POST'])
def api_register():
    data = request.get_json() or {}
    username = data.get('username', '').strip()
    email = data.get('email', '').strip()
    password = data.get('password', '')

    if not username or not email or not password:
        return jsonify({'error': 'All fields are required'}), 400

    if User.query.filter((User.username == username) | (User.email == email)).first():
        return jsonify({'error': 'Username or email already taken'}), 400

    colors = ['#EF4444', '#F59E0B', '#10B981', '#3B82F6', '#6366F1', '#8B5CF6', '#EC4899']
    user = User(username=username, email=email, avatar_color=random.choice(colors))
    user.set_password(password)
    db.session.add(user)
    db.session.commit()

    session['user_id'] = user.id
    return jsonify({'message': 'Registration successful', 'user': user.to_dict()})

@app.route('/api/auth/login', methods=['POST'])
def api_login():
    data = request.get_json() or {}
    username = data.get('username', '').strip()
    password = data.get('password', '')

    user = User.query.filter((User.username == username) | (User.email == username)).first()
    if not user or not user.check_password(password):
        return jsonify({'error': 'Invalid credentials'}), 401

    session['user_id'] = user.id
    return jsonify({'message': 'Login successful', 'user': user.to_dict()})

@app.route('/api/auth/quick-guest', methods=['POST'])
def api_quick_guest():
    data = request.get_json() or {}
    guest_name = data.get('guest', 'Alice') # Default to Alice if not specified
    user = User.query.filter_by(username=guest_name).first()
    if not user:
        colors = ['#EC4899', '#10B981', '#8B5CF6', '#F59E0B']
        user = User(username=guest_name, email=f"{guest_name.lower()}@example.com", avatar_color=random.choice(colors))
        user.set_password('password123')
        db.session.add(user)
        db.session.commit()

    session['user_id'] = user.id
    return jsonify({'message': f'Logged in as {user.username}', 'user': user.to_dict()})

@app.route('/api/auth/logout', methods=['POST'])
def api_logout():
    session.pop('user_id', None)
    return jsonify({'message': 'Logged out'})

@app.route('/api/auth/me', methods=['GET'])
@login_required
def api_me():
    return jsonify(get_current_user().to_dict())

@app.route('/api/boards', methods=['GET'])
@login_required
def api_get_boards():
    current_user = get_current_user()
    owned_boards = Board.query.filter_by(owner_id=current_user.id).all()
    member_board_ids = [bm.board_id for bm in BoardMember.query.filter_by(user_id=current_user.id).all()]
    joined_boards = Board.query.filter(Board.id.in_(member_board_ids)).all() if member_board_ids else []

    all_boards = list({b.id: b for b in (owned_boards + joined_boards)}.values())
    return jsonify([b.to_dict() for b in all_boards])

@app.route('/api/boards', methods=['POST'])
@login_required
def api_create_board():
    data = request.get_json() or {}
    title = data.get('title', '').strip()
    description = data.get('description', '').strip()

    if not title:
        return jsonify({'error': 'Title is required'}), 400

    current_user = get_current_user()
    board = Board(title=title, description=description, owner_id=current_user.id)
    db.session.add(board)
    db.session.commit()

    # Add activity log
    act = ActivityLog(board_id=board.id, user_id=current_user.id, action=f"created board '{title}'")
    db.session.add(act)
    db.session.commit()

    return jsonify(board.to_dict()), 201

@app.route('/api/boards/<board_uuid>', methods=['GET'])
@login_required
def api_get_board_data(board_uuid):
    board = Board.query.filter_by(uuid=board_uuid).first()
    if not board:
        return jsonify({'error': 'Board not found'}), 404

    tasks = Task.query.filter_by(board_id=board.id).order_by(Task.position.asc()).all()
    members_objs = [bm.user for bm in board.members] + [board.owner]
    # Unique members
    unique_members = list({u.id: u.to_dict() for u in members_objs if u}.values())
    activities = ActivityLog.query.filter_by(board_id=board.id).order_by(ActivityLog.timestamp.desc()).limit(20).all()

    return jsonify({
        'board': board.to_dict(),
        'tasks': [t.to_dict() for t in tasks],
        'members': unique_members,
        'activities': [a.to_dict() for a in activities]
    })

# -------------------------------------------------------------------
# SocketIO Real-Time Events
# -------------------------------------------------------------------

def broadcast_presence(board_uuid):
    room_users = presence_data.get(board_uuid, {})
    # Get distinct list of users online in this room
    active_user_map = {}
    for sid, uinfo in room_users.items():
        active_user_map[uinfo['id']] = uinfo
    
    online_users = list(active_user_map.values())
    socketio.emit('presence_update', {'users': online_users}, room=board_uuid)

@socketio.on('join_board')
def handle_join_board(data):
    board_uuid = data.get('board_uuid')
    user_id = session.get('user_id')
    if not board_uuid or not user_id:
        return

    user = db.session.get(User, user_id)
    if not user:
        return

    join_room(board_uuid)

    if board_uuid not in presence_data:
        presence_data[board_uuid] = {}

    user_info = {
        'id': user.id,
        'username': user.username,
        'avatar_color': user.avatar_color
    }

    presence_data[board_uuid][request.sid] = user_info
    socket_users[request.sid] = {'board_uuid': board_uuid, 'user': user_info}

    broadcast_presence(board_uuid)
    emit('connected_status', {'status': 'connected', 'user': user_info})

@socketio.on('leave_board')
def handle_leave_board(data):
    board_uuid = data.get('board_uuid')
    if not board_uuid:
        return

    leave_room(board_uuid)
    if board_uuid in presence_data and request.sid in presence_data[board_uuid]:
        del presence_data[board_uuid][request.sid]
        if not presence_data[board_uuid]:
            del presence_data[board_uuid]
    
    if request.sid in socket_users:
        del socket_users[request.sid]

    broadcast_presence(board_uuid)

@socketio.on('disconnect')
def handle_disconnect():
    if request.sid in socket_users:
        info = socket_users[request.sid]
        board_uuid = info.get('board_uuid')
        del socket_users[request.sid]

        if board_uuid and board_uuid in presence_data:
            if request.sid in presence_data[board_uuid]:
                del presence_data[board_uuid][request.sid]
            if not presence_data[board_uuid]:
                del presence_data[board_uuid]
            broadcast_presence(board_uuid)

@socketio.on('move_task')
def handle_move_task(data):
    """
    Data payload: {
        taskId: int,
        sourceColumn: str,
        targetColumn: str,
        newPosition: int,
        boardUuid: str
    }
    """
    user_id = session.get('user_id')
    if not user_id:
        emit('error_response', {'message': 'Unauthorized'})
        return

    task_id = data.get('taskId')
    target_column = data.get('targetColumn')
    new_position = data.get('newPosition', 0)
    board_uuid = data.get('boardUuid')

    task = db.session.get(Task, task_id)
    if not task:
        emit('error_response', {'message': 'Task not found'})
        return

    old_column = task.column_name
    old_position = task.position

    # Update column and re-index tasks in target & source columns
    task.column_name = target_column

    # Fetch tasks in target column
    target_tasks = Task.query.filter(Task.board_id == task.board_id, Task.column_name == target_column, Task.id != task.id).order_by(Task.position.asc()).all()
    
    # Insert task at new_position
    target_tasks.insert(new_position, task)

    # Re-assign clean consecutive 0-indexed positions
    for idx, t in enumerate(target_tasks):
        t.position = idx

    # If moved across columns, also clean source column positions
    if old_column != target_column:
        source_tasks = Task.query.filter(Task.board_id == task.board_id, Task.column_name == old_column, Task.id != task.id).order_by(Task.position.asc()).all()
        for idx, t in enumerate(source_tasks):
            t.position = idx

    user = db.session.get(User, user_id)
    col_names_map = {'todo': 'To-Do', 'doing': 'Doing', 'done': 'Done'}
    act_msg = f"moved '{task.content}' to {col_names_map.get(target_column, target_column)}"
    act = ActivityLog(board_id=task.board_id, user_id=user.id, action=act_msg)
    db.session.add(act)

    db.session.commit()

    # Broadcast real-time move event to room
    payload = {
        'taskId': task.id,
        'sourceColumn': old_column,
        'targetColumn': target_column,
        'newPosition': task.position,
        'task': task.to_dict(),
        'moved_by': user.username,
        'activity': act.to_dict()
    }
    emit('task_moved', payload, room=board_uuid, include_self=True)

@socketio.on('create_task')
def handle_create_task(data):
    """
    Data payload: {
        boardUuid: str,
        content: str,
        columnName: str,
        priority: str,
        description: str,
        assignedToId: int
    }
    """
    user_id = session.get('user_id')
    if not user_id:
        emit('error_response', {'message': 'Unauthorized'})
        return

    board_uuid = data.get('boardUuid')
    content = data.get('content', '').strip()
    column_name = data.get('columnName', 'todo')
    priority = data.get('priority', 'medium')
    description = data.get('description', '').strip()
    assigned_to_id = data.get('assignedToId')

    if not content or not board_uuid:
        emit('error_response', {'message': 'Content and Board ID are required'})
        return

    board = Board.query.filter_by(uuid=board_uuid).first()
    if not board:
        emit('error_response', {'message': 'Board not found'})
        return

    # Count existing tasks in column for end position
    pos = Task.query.filter_by(board_id=board.id, column_name=column_name).count()

    task = Task(
        content=content,
        description=description,
        column_name=column_name,
        position=pos,
        priority=priority,
        board_id=board.id,
        created_by_id=user_id,
        assigned_to_id=assigned_to_id if assigned_to_id else None
    )
    db.session.add(task)
    
    user = db.session.get(User, user_id)
    act = ActivityLog(board_id=board.id, user_id=user.id, action=f"created task '{content}'")
    db.session.add(act)
    
    db.session.commit()

    payload = {
        'task': task.to_dict(),
        'activity': act.to_dict()
    }
    emit('task_created', payload, room=board_uuid, include_self=True)

@socketio.on('update_task')
def handle_update_task(data):
    """
    Data payload: {
        taskId: int,
        boardUuid: str,
        content: str,
        description: str,
        priority: str,
        columnName: str,
        assignedToId: int
    }
    """
    user_id = session.get('user_id')
    if not user_id:
        emit('error_response', {'message': 'Unauthorized'})
        return

    task_id = data.get('taskId')
    board_uuid = data.get('boardUuid')
    content = data.get('content', '').strip()

    task = db.session.get(Task, task_id)
    if not task:
        emit('error_response', {'message': 'Task not found'})
        return

    if content:
        task.content = content
    task.description = data.get('description', task.description)
    task.priority = data.get('priority', task.priority)
    
    assigned_id = data.get('assignedToId')
    if assigned_id is not None:
        task.assigned_to_id = assigned_id if assigned_id > 0 else None

    user = User.query.get(user_id)
    act = ActivityLog(board_id=task.board_id, user_id=user.id, action=f"updated task '{task.content}'")
    db.session.add(act)

    db.session.commit()

    payload = {
        'task': task.to_dict(),
        'activity': act.to_dict()
    }
    emit('task_updated', payload, room=board_uuid, include_self=True)

@socketio.on('delete_task')
def handle_delete_task(data):
    """
    Data payload: { taskId: int, boardUuid: str }
    """
    user_id = session.get('user_id')
    if not user_id:
        emit('error_response', {'message': 'Unauthorized'})
        return

    task_id = data.get('taskId')
    board_uuid = data.get('boardUuid')

    task = db.session.get(Task, task_id)
    if not task:
        emit('error_response', {'message': 'Task not found'})
        return

    content = task.content
    board_id = task.board_id
    db.session.delete(task)

    user = User.query.get(user_id)
    act = ActivityLog(board_id=board_id, user_id=user.id, action=f"deleted task '{content}'")
    db.session.add(act)

    db.session.commit()

    payload = {
        'taskId': task_id,
        'activity': act.to_dict()
    }
    emit('task_deleted', payload, room=board_uuid, include_self=True)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5050))
    socketio.run(app, debug=True, host='0.0.0.0', port=port)

