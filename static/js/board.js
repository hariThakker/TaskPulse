// Real-Time Kanban Board JavaScript Logic

document.addEventListener('DOMContentLoaded', () => {
    const boardContainer = document.getElementById('board-container');
    if (!boardContainer) return;

    const boardUuid = boardContainer.dataset.boardUuid;
    const currentUserId = parseInt(boardContainer.dataset.userId);

    let boardData = null;
    let taskMap = {}; // taskId -> task object
    let sortableInstances = {};
    let boardMembers = [];

    // Socket.IO Setup
    const socket = io();

    // -------------------------------------------------------------------
    // Initial Load & API Fetch
    // -------------------------------------------------------------------

    fetchBoardData();

    async function fetchBoardData() {
        try {
            const res = await fetch(`/api/boards/${boardUuid}`);
            if (!res.ok) throw new Error('Failed to load board data');
            
            const data = await res.json();
            boardData = data.board;
            boardMembers = data.members;

            // Populate taskMap
            taskMap = {};
            data.tasks.forEach(t => { taskMap[t.id] = t; });

            renderAllTasks(data.tasks);
            renderAssigneeOptions(boardMembers);
            renderActivities(data.activities);
            initSortable();

        } catch (err) {
            console.error(err);
            showToast('Error loading workspace data', 'error');
        }
    }

    // -------------------------------------------------------------------
    // Socket.IO Events
    // -------------------------------------------------------------------

    socket.on('connect', () => {
        updateSocketBadge(true);
        socket.emit('join_board', { board_uuid: boardUuid });
    });

    socket.on('disconnect', () => {
        updateSocketBadge(false);
    });

    socket.on('presence_update', (data) => {
        renderPresenceAvatars(data.users || []);
    });

    socket.on('task_moved', (data) => {
        const { taskId, targetColumn, newPosition, task, moved_by, activity } = data;
        
        // Update local task memory
        if (task) {
            taskMap[task.id] = task;
        }

        // Re-render affected task card or relocate in DOM
        const cardElem = document.getElementById(`task-card-${taskId}`);
        const targetColElem = document.getElementById(`column-${targetColumn}`);

        if (cardElem && targetColElem) {
            const children = Array.from(targetColElem.children).filter(c => c.classList.contains('task-card'));
            if (newPosition >= children.length) {
                targetColElem.appendChild(cardElem);
            } else {
                targetColElem.insertBefore(cardElem, children[newPosition]);
            }
            cardElem.dataset.column = targetColumn;
        } else if (task && targetColElem) {
            // Card didn't exist locally yet, create it
            const newCard = createCardElement(task);
            targetColElem.appendChild(newCard);
        }

        updateColumnCounts();
        if (activity) addActivityItem(activity, true);
    });

    socket.on('task_created', (data) => {
        const { task, activity } = data;
        taskMap[task.id] = task;

        const colElem = document.getElementById(`column-${task.column_name}`);
        if (colElem) {
            const cardElem = createCardElement(task);
            cardElem.classList.add('animate-card-in');
            colElem.appendChild(cardElem);
            updateColumnCounts();
        }

        if (activity) addActivityItem(activity, true);
    });

    socket.on('task_updated', (data) => {
        const { task, activity } = data;
        taskMap[task.id] = task;

        const oldCard = document.getElementById(`task-card-${task.id}`);
        if (oldCard) {
            const newCard = createCardElement(task);
            oldCard.replaceWith(newCard);
            updateColumnCounts();
        }

        if (activity) addActivityItem(activity, true);
    });

    socket.on('task_deleted', (data) => {
        const { taskId, activity } = data;
        delete taskMap[taskId];

        const cardElem = document.getElementById(`task-card-${taskId}`);
        if (cardElem) {
            cardElem.style.opacity = '0';
            cardElem.style.transform = 'scale(0.9)';
            setTimeout(() => {
                cardElem.remove();
                updateColumnCounts();
            }, 200);
        }

        if (activity) addActivityItem(activity, true);
    });

    socket.on('error_response', (data) => {
        showToast(data.message || 'Server error', 'error');
    });

    // -------------------------------------------------------------------
    // Task Rendering & SortableJS Integration
    // -------------------------------------------------------------------

    function renderAllTasks(tasks) {
        ['todo', 'doing', 'done'].forEach(col => {
            const colElem = document.getElementById(`column-${col}`);
            colElem.innerHTML = '';
        });

        tasks.forEach(t => {
            const colElem = document.getElementById(`column-${t.column_name}`);
            if (colElem) {
                colElem.appendChild(createCardElement(t));
            }
        });

        updateColumnCounts();
    }

    function createCardElement(t) {
        const card = document.createElement('div');
        card.id = `task-card-${t.id}`;
        card.dataset.id = t.id;
        card.dataset.column = t.column_name;
        card.dataset.priority = t.priority;
        card.className = 'task-card glass-card p-4 rounded-xl space-y-3 cursor-grab active:cursor-grabbing select-none relative group';

        const priorityClass = `priority-${t.priority}`;
        const assignee = t.assigned_to;

        card.innerHTML = `
            <div class="flex items-start justify-between gap-2">
                <span class="text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded-md ${priorityClass}">
                    ${t.priority}
                </span>
                <div class="flex items-center space-x-1 opacity-0 group-hover:opacity-100 transition">
                    <button onclick="editTask(${t.id})" title="Edit Task" class="p-1 rounded text-slate-400 hover:text-indigo-300 hover:bg-slate-800 transition text-xs">
                        <i class="fa-solid fa-pen-to-square"></i>
                    </button>
                    <button onclick="confirmDeleteTask(${t.id})" title="Delete Task" class="p-1 rounded text-slate-400 hover:text-rose-400 hover:bg-slate-800 transition text-xs">
                        <i class="fa-solid fa-trash"></i>
                    </button>
                </div>
            </div>

            <h4 class="text-sm font-semibold text-white leading-snug break-words">
                ${escapeHtml(t.content)}
            </h4>

            ${t.description ? `
                <p class="text-xs text-slate-400 line-clamp-2 leading-relaxed">
                    ${escapeHtml(t.description)}
                </p>
            ` : ''}

            <div class="pt-2 border-t border-slate-800/60 flex items-center justify-between text-xs text-slate-400">
                <div class="flex items-center space-x-1.5" title="Assigned to">
                    ${assignee ? `
                        <div class="w-5 h-5 rounded-full flex items-center justify-center font-bold text-[9px] text-white shadow-sm" style="background-color: ${assignee.avatar_color}">
                            ${assignee.username[0].toUpperCase()}
                        </div>
                        <span class="text-[11px] text-slate-300 truncate max-w-[90px]">${escapeHtml(assignee.username)}</span>
                    ` : `
                        <span class="text-[11px] text-slate-500 italic">Unassigned</span>
                    `}
                </div>
                <span class="text-[10px] text-slate-500">#${t.id}</span>
            </div>
        `;

        return card;
    }

    function initSortable() {
        ['todo', 'doing', 'done'].forEach(colName => {
            const container = document.getElementById(`column-${colName}`);
            if (!container) return;

            sortableInstances[colName] = new Sortable(container, {
                group: 'kanban-board',
                animation: 200,
                ghostClass: 'sortable-ghost',
                chosenClass: 'sortable-chosen',
                dragClass: 'sortable-drag',
                emptyInsertThreshold: 10,
                onEnd: function (evt) {
                    const itemEl = evt.item;
                    const taskId = parseInt(itemEl.dataset.id);
                    const targetColumn = evt.to.dataset.column;
                    const sourceColumn = evt.from.dataset.column;
                    const newPosition = evt.newIndex;
                    const oldPosition = evt.oldIndex;

                    // Optimistic UI updates
                    itemEl.dataset.column = targetColumn;
                    updateColumnCounts();

                    // Emit Socket.IO Event to server
                    socket.emit('move_task', {
                        taskId: taskId,
                        sourceColumn: sourceColumn,
                        targetColumn: targetColumn,
                        newPosition: newPosition,
                        boardUuid: boardUuid
                    });

                    // Rollback handler if network disconnected
                    if (!socket.connected) {
                        showToast('Connection lost! Rolling back move...', 'error');
                        if (evt.from !== evt.to) {
                            evt.from.insertBefore(itemEl, evt.from.children[oldPosition] || null);
                            itemEl.dataset.column = sourceColumn;
                            updateColumnCounts();
                        }
                    }
                }
            });
        });
    }

    function updateColumnCounts() {
        ['todo', 'doing', 'done'].forEach(col => {
            const container = document.getElementById(`column-${col}`);
            const badge = document.getElementById(`count-${col}`);
            if (container && badge) {
                const count = container.querySelectorAll('.task-card').length;
                badge.innerText = count;
            }
        });
    }

    // -------------------------------------------------------------------
    // Presence & Avatars
    // -------------------------------------------------------------------

    function renderPresenceAvatars(users) {
        const container = document.getElementById('presence-avatars');
        if (!container) return;

        if (users.length === 0) {
            container.innerHTML = '<span class="text-xs text-slate-500">None</span>';
            return;
        }

        container.innerHTML = users.map(u => `
            <div class="relative group" title="${escapeHtml(u.username)} (Online)">
                <div class="w-8 h-8 rounded-full flex items-center justify-center font-bold text-xs text-white border-2 border-slate-900 shadow-md transform group-hover:scale-110 transition duration-200" style="background-color: ${u.avatar_color}">
                    ${u.username[0].toUpperCase()}
                </div>
                <span class="absolute bottom-0 right-0 w-2.5 h-2.5 rounded-full bg-emerald-400 border border-slate-900 online-pulse"></span>
            </div>
        `).join('');
    }

    function updateSocketBadge(isConnected) {
        const badge = document.getElementById('socket-status');
        if (!badge) return;

        if (isConnected) {
            badge.className = "inline-flex items-center space-x-1.5 px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20";
            badge.innerHTML = `<span class="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-ping"></span><span>Live Sync</span>`;
        } else {
            badge.className = "inline-flex items-center space-x-1.5 px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-amber-500/10 text-amber-400 border border-amber-500/20";
            badge.innerHTML = `<span class="w-1.5 h-1.5 rounded-full bg-amber-400"></span><span>Reconnecting...</span>`;
        }
    }

    // -------------------------------------------------------------------
    // Assignees & Activity Stream
    // -------------------------------------------------------------------

    function renderAssigneeOptions(members) {
        const select = document.getElementById('task-assignee-input');
        if (!select) return;

        select.innerHTML = '<option value="">Unassigned</option>' + 
            members.map(m => `<option value="${m.id}">${escapeHtml(m.username)}</option>`).join('');
    }

    function renderActivities(activities) {
        const container = document.getElementById('activity-list');
        if (!container) return;

        container.innerHTML = activities.map(a => formatActivityHTML(a)).join('');
    }

    function addActivityItem(act, animate = false) {
        const container = document.getElementById('activity-list');
        if (!container) return;

        const item = document.createElement('div');
        item.innerHTML = formatActivityHTML(act);
        const child = item.firstElementChild;
        if (animate) child.classList.add('animate-card-in');

        container.insertBefore(child, container.firstChild);
    }

    function formatActivityHTML(a) {
        const user = a.user || { username: 'System', avatar_color: '#6B7280' };
        return `
            <div class="p-2.5 rounded-xl bg-slate-800/80 border border-slate-700/60 flex items-start space-x-2.5 text-xs text-slate-300">
                <div class="w-6 h-6 rounded-full flex items-center justify-center font-bold text-[9px] text-white shrink-0 mt-0.5" style="background-color: ${user.avatar_color}">
                    ${user.username[0].toUpperCase()}
                </div>
                <div class="flex-1 min-w-0">
                    <div>
                        <span class="font-bold text-white">${escapeHtml(user.username)}</span> 
                        <span class="text-slate-300">${escapeHtml(a.action)}</span>
                    </div>
                    <div class="text-[10px] text-slate-500 mt-1">${a.timestamp}</div>
                </div>
            </div>
        `;
    }

    // -------------------------------------------------------------------
    // Modal & CRUD Handlers
    // -------------------------------------------------------------------

    window.openTaskModal = function(defaultCol = 'todo') {
        document.getElementById('task-form').reset();
        document.getElementById('task-id-input').value = '';
        document.getElementById('task-modal-title').innerHTML = `
            <i class="fa-solid fa-square-plus text-indigo-400"></i>
            <span>Add Task Card</span>
        `;
        document.getElementById('task-column-input').value = defaultCol;
        document.getElementById('task-modal').classList.remove('hidden');
    };

    window.closeTaskModal = function() {
        document.getElementById('task-modal').classList.add('hidden');
    };

    window.editTask = function(taskId) {
        const task = taskMap[taskId];
        if (!task) return;

        document.getElementById('task-id-input').value = task.id;
        document.getElementById('task-content-input').value = task.content;
        document.getElementById('task-column-input').value = task.column_name;
        document.getElementById('task-priority-input').value = task.priority;
        document.getElementById('task-desc-input').value = task.description || '';
        document.getElementById('task-assignee-input').value = task.assigned_to ? task.assigned_to.id : '';

        document.getElementById('task-modal-title').innerHTML = `
            <i class="fa-solid fa-pen-to-square text-indigo-400"></i>
            <span>Edit Task #${task.id}</span>
        `;
        document.getElementById('task-modal').classList.remove('hidden');
    };

    window.submitTaskForm = function(e) {
        e.preventDefault();
        const taskId = document.getElementById('task-id-input').value;
        const content = document.getElementById('task-content-input').value;
        const columnName = document.getElementById('task-column-input').value;
        const priority = document.getElementById('task-priority-input').value;
        const description = document.getElementById('task-desc-input').value;
        const assigneeVal = document.getElementById('task-assignee-input').value;
        const assignedToId = assigneeVal ? parseInt(assigneeVal) : null;

        if (taskId) {
            // Update
            socket.emit('update_task', {
                taskId: parseInt(taskId),
                boardUuid: boardUuid,
                content: content,
                description: description,
                priority: priority,
                columnName: columnName,
                assignedToId: assignedToId
            });
        } else {
            // Create
            socket.emit('create_task', {
                boardUuid: boardUuid,
                content: content,
                columnName: columnName,
                priority: priority,
                description: description,
                assignedToId: assignedToId
            });
        }

        closeTaskModal();
    };

    window.confirmDeleteTask = function(taskId) {
        if (confirm('Are you sure you want to delete this task?')) {
            socket.emit('delete_task', {
                taskId: taskId,
                boardUuid: boardUuid
            });
        }
    };

    // -------------------------------------------------------------------
    // Toolbars & Utilities
    // -------------------------------------------------------------------

    window.copyInviteLink = function() {
        const link = `${window.location.origin}/board/${boardUuid}`;
        navigator.clipboard.writeText(link);
        showToast('Invite link copied! Share with anyone to collaborate real-time.', 'success');
    };

    window.toggleActivityDrawer = function() {
        const drawer = document.getElementById('activity-drawer');
        drawer.classList.toggle('translate-x-full');
    };

    window.filterTasks = function() {
        const query = document.getElementById('task-search-input').value.toLowerCase();
        const priority = document.getElementById('priority-filter').value;

        const cards = document.querySelectorAll('.task-card');
        cards.forEach(c => {
            const taskId = parseInt(c.dataset.id);
            const task = taskMap[taskId];
            if (!task) return;

            const matchesQuery = task.content.toLowerCase().includes(query) || (task.description && task.description.toLowerCase().includes(query));
            const matchesPriority = (priority === 'all') || (task.priority === priority);

            if (matchesQuery && matchesPriority) {
                c.style.display = 'block';
            } else {
                c.style.display = 'none';
            }
        });
    };

    function escapeHtml(str) {
        if (!str) return '';
        return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
    }
});
