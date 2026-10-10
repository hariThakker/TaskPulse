import pytest
from app import app, db, socketio
from models import User, Board, Task, BoardMember

@pytest.fixture
def client():
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    app.config['WTF_CSRF_ENABLED'] = False
    
    with app.test_client() as client:
        with app.app_context():
            db.create_all()
            yield client
            db.session.remove()
            db.drop_all()

def test_register_and_login(client):
    # Register user
    res = client.post('/api/auth/register', json={
        'username': 'Tester',
        'email': 'tester@example.com',
        'password': 'password123'
    })
    assert res.status_code == 200
    data = res.get_json()
    assert data['user']['username'] == 'Tester'

    # Login
    res = client.post('/api/auth/login', json={
        'username': 'Tester',
        'password': 'password123'
    })
    assert res.status_code == 200

def test_quick_guest(client):
    res = client.post('/api/auth/quick-guest', json={'guest': 'Alice'})
    assert res.status_code == 200
    data = res.get_json()
    assert data['user']['username'] == 'Alice'

def test_board_creation(client):
    client.post('/api/auth/quick-guest', json={'guest': 'Alice'})
    
    res = client.post('/api/boards', json={
        'title': 'Test Sprint Board',
        'description': 'Testing workspace creation'
    })
    assert res.status_code == 201
    board = res.get_json()
    assert board['title'] == 'Test Sprint Board'
    assert 'uuid' in board

def test_board_invite_link_auto_join(client):
    # Alice creates board
    client.post('/api/auth/quick-guest', json={'guest': 'Alice'})
    res = client.post('/api/boards', json={'title': 'Alice Board'})
    board_uuid = res.get_json()['uuid']

    # Logout Alice
    client.post('/api/auth/logout')

    # Login Bob
    client.post('/api/auth/quick-guest', json={'guest': 'Bob'})

    # Bob visits invite link
    res = client.get(f'/board/{board_uuid}')
    assert res.status_code == 200

    # Verify Bob is added to members
    res_data = client.get(f'/api/boards/{board_uuid}').get_json()
    member_names = [m['username'] for m in res_data['members']]
    assert 'Bob' in member_names

def test_socketio_task_creation_and_move(client):
    # Login Alice
    client.post('/api/auth/quick-guest', json={'guest': 'Alice'})
    res = client.post('/api/boards', json={'title': 'Socket Board'})
    board_uuid = res.get_json()['uuid']

    # Create SocketIO test clients
    socket_client1 = socketio.test_client(app, flask_test_client=client)
    socket_client2 = socketio.test_client(app, flask_test_client=client)

    assert socket_client1.is_connected()
    assert socket_client2.is_connected()

    # Join board room
    socket_client1.emit('join_board', {'board_uuid': board_uuid})
    socket_client2.emit('join_board', {'board_uuid': board_uuid})

    # Client 1 creates task via socket
    socket_client1.emit('create_task', {
        'boardUuid': board_uuid,
        'content': 'Socket Created Task',
        'columnName': 'todo',
        'priority': 'high'
    })

    received1 = socket_client1.get_received()
    received2 = socket_client2.get_received()

    # Both clients should receive task_created broadcast
    task_created_events = [e for e in received2 if e['name'] == 'task_created']
    assert len(task_created_events) > 0
    task_id = task_created_events[0]['args'][0]['task']['id']

    # Client 2 moves task to 'doing'
    socket_client2.emit('move_task', {
        'taskId': task_id,
        'sourceColumn': 'todo',
        'targetColumn': 'doing',
        'newPosition': 0,
        'boardUuid': board_uuid
    })

    received1_after = socket_client1.get_received()
    move_events = [e for e in received1_after if e['name'] == 'task_moved']
    assert len(move_events) > 0
    assert move_events[0]['args'][0]['targetColumn'] == 'doing'
