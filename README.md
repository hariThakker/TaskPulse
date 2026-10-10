# 🚀 TaskPulse: Real-Time Collaborative Task Board (Kanban)

TaskPulse is a resume-grade, production-ready real-time Kanban board application built with **Flask**, **Flask-SocketIO**, **Flask-SQLAlchemy**, **SortableJS**, and modern glassmorphic Tailwind CSS. Multiple users can collaborate in real-time on shared workspace boards, drag-and-drop task cards across columns with instant WebSocket synchronization, see live online user presence avatars, and join via unique shareable UUID invite links.

---

## 🛠️ Technical Stack

- **Backend**: Python 3, Flask, Flask-SocketIO (WebSocket real-time engine with Eventlet), Flask-SQLAlchemy (SQLite/PostgreSQL)
- **Frontend**: HTML5, CSS (Tailwind CSS CDN + Glassmorphism / Dark Mode theme in `static/css/style.css`), Vanilla JavaScript
- **Drag-and-Drop**: SortableJS (Industry standard list reordering)
- **Real-Time Features**: WebSockets (`socket.io`), User Presence Tracking, Optimistic UI with automatic rollback, Live Activity Stream
- **Testing**: Pytest & Flask-SocketIO Test Client

---

## ✨ Features Implemented

### Phase 1: Basic Board & CRUD Persistence
- **Database Models**: `User`, `Board`, `BoardMember`, `Task`, `ActivityLog` in SQLAlchemy.
- **Kanban Columns**: Standard 3-column layout (`To-Do`, `In Progress (Doing)`, `Completed (Done)`).
- **Task Management**: Create, edit content/description/priority/assignee, move columns, and delete tasks.
- **Position Persistence**: Task ordering inside columns is maintained with integer position indexing.

### Phase 2: Real-Time WebSockets Engine
- **Socket.IO Event Flow**:
  - `join_board`: Joins board socket room (`board_uuid`) and broadcasts online user presence.
  - `move_task`: Triggers instant WebSocket broadcast (`task_moved`) to all active room members when a card is dragged.
  - `create_task`, `update_task`, `delete_task`: Broadcast real-time card updates across connected browsers.

### Phase 3: Resume-Grade Polish & Advanced Features
- **Shareable Invite Links**: Unique UUID generated for each board (`/board/<uuid>`). Anyone opening the link automatically joins the board.
- **User Presence Avatars**: Glowing top-bar avatars showing users currently active in the board room with live pulse indicators.
- **1-Click Demo Guest Switcher**: Quick test buttons ("Alice", "Bob", "Charlie") to easily test multi-user real-time sync across two browser windows or tabs.
- **Optimistic UI & Rollback**: Dragged cards update locally on screen instantly; if network connection drops, cards animate back to original position.
- **Live Activity Feed**: Sliding drawer showing timestamped activity stream.
- **Priority & Text Filtering**: Real-time filtering by search query or priority level (`Low`, `Medium`, `High`, `Urgent`).

---

## 🚀 How to Run Locally

### 1. Activate Environment & Install Dependencies
```bash
python3 -m venv venv
source venv/bin/activate
pip install flask flask-socketio flask-sqlalchemy eventlet python-dotenv pytest
```

### 2. Run Application
```bash
python3 app.py
```
Open your browser and navigate to: **`http://127.0.0.1:5050`**

### 3. Run Automated Tests
```bash
PYTHONPATH=. pytest tests/test_board.py
```

---

## 🧪 Testing Multi-User Real-Time Sync

1. Open **`http://127.0.0.1:5050`** in Window 1 and click **Alice** (1-Click Demo Login).
2. Open an Incognito/Private window or Tab 2, navigate to `http://127.0.0.1:5050` and select **Bob** or **Charlie** from the top user switcher.
3. Open the **🚀 Real-Time Launch Board** in both windows.
4. Drag any card in Window 1 — watch it move instantly in Window 2 with zero delay!
