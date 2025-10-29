"""
Chores routes for Homie Flask application
"""
from flask import Blueprint, render_template, request, redirect, url_for, jsonify, session
from authentication import login_required, api_auth_required
from database import get_db_connection
from security import csrf_protect, validate_ownership, sanitize_input
import logging

logger = logging.getLogger(__name__)

chores_bp = Blueprint('chores', __name__)

@chores_bp.route('/chores')
@login_required
def chores_list():
    """Display the chores page"""
    conn = get_db_connection()
    
    # Get all chores with user information
    chores = conn.execute('''
        SELECT c.*, 
               au.username as added_by_name,
               asu.username as assigned_to_name,
               cu.username as completed_by_name
        FROM chores c
        LEFT JOIN users au ON c.added_by = au.id
        LEFT JOIN users asu ON c.assigned_to = asu.id  
        LEFT JOIN users cu ON c.completed_by = cu.id
        ORDER BY c.completed ASC, c.created_at DESC
    ''').fetchall()
    
    # Get all users for assignment dropdown
    users = conn.execute('SELECT id, username FROM users ORDER BY username').fetchall()
    
    conn.close()
    return render_template('chores.html', chores=chores, users=users)

@chores_bp.route('/api/chores/add', methods=['POST'])
@api_auth_required
@csrf_protect
def add_chore():
    """Add a new chore via API"""
    try:
        data = request.get_json()
        if not data or 'chore_name' not in data:
            return jsonify({'error': 'Chore name is required'}), 400
        
        chore_name = sanitize_input(data['chore_name'].strip())
        if not chore_name:
            return jsonify({'error': 'Chore name cannot be empty'}), 400
        
        assigned_to = data.get('assigned_to')
        if assigned_to == '':
            assigned_to = None
        elif assigned_to is not None:
            try:
                assigned_to = int(assigned_to)
            except (ValueError, TypeError):
                return jsonify({'error': 'Invalid assigned user'}), 400
        
        user_id = session['user']['id']
        
        conn = get_db_connection()
        
        # Validate assigned user exists
        if assigned_to is not None:
            user_exists = conn.execute('SELECT id FROM users WHERE id = ?', (assigned_to,)).fetchone()
            if not user_exists:
                conn.close()
                return jsonify({'error': 'Assigned user does not exist'}), 400
        
        conn.execute('''
            INSERT INTO chores (chore_name, assigned_to, added_by)
            VALUES (?, ?, ?)
        ''', (chore_name, assigned_to, user_id))
        conn.commit()
        conn.close()
        
        logger.info(f"User {user_id} added chore: {chore_name}")
        return jsonify({'success': True, 'message': 'Chore added successfully'})
        
    except Exception as e:
        logger.error(f"Error adding chore: {e}")
        return jsonify({'error': 'Failed to add chore'}), 500

@chores_bp.route('/api/chores/toggle/<int:chore_id>', methods=['POST'])
@api_auth_required
@csrf_protect  
def toggle_chore(chore_id):
    """Toggle completion status of a chore"""
    try:
        conn = get_db_connection()
        
        # Get the current chore
        chore = conn.execute('SELECT * FROM chores WHERE id = ?', (chore_id,)).fetchone()
        if not chore:
            conn.close()
            return jsonify({'error': 'Chore not found'}), 404
        
        user_id = session['user']['id']
        
        # Toggle the completion status
        new_status = not chore['completed']
        completed_by = user_id if new_status else None
        
        if new_status:
            conn.execute('''
                UPDATE chores 
                SET completed = ?, completed_by = ?, completed_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (new_status, completed_by, chore_id))
        else:
            conn.execute('''
                UPDATE chores 
                SET completed = ?, completed_by = NULL, completed_at = NULL
                WHERE id = ?
            ''', (new_status, chore_id))
        
        conn.commit()
        conn.close()
        
        action = "completed" if new_status else "uncompleted"
        logger.info(f"User {user_id} {action} chore {chore_id}")
        
        return jsonify({'success': True, 'completed': new_status})
        
    except Exception as e:
        logger.error(f"Error toggling chore {chore_id}: {e}")
        return jsonify({'error': 'Failed to toggle chore'}), 500

@chores_bp.route('/api/chores/delete/<int:chore_id>', methods=['DELETE'])
@api_auth_required
@csrf_protect
def delete_chore(chore_id):
    """Delete a chore"""
    try:
        conn = get_db_connection()
        
        # Validate ownership or admin rights
        if not validate_ownership(conn, 'chores', chore_id, session['user']):
            conn.close()
            return jsonify({'error': 'Unauthorized'}), 403
        
        # Delete the chore
        result = conn.execute('DELETE FROM chores WHERE id = ?', (chore_id,))
        
        if result.rowcount == 0:
            conn.close()
            return jsonify({'error': 'Chore not found'}), 404
        
        conn.commit()
        conn.close()
        
        user_id = session['user']['id']
        logger.info(f"User {user_id} deleted chore {chore_id}")
        
        return jsonify({'success': True, 'message': 'Chore deleted successfully'})
        
    except Exception as e:
        logger.error(f"Error deleting chore {chore_id}: {e}")
        return jsonify({'error': 'Failed to delete chore'}), 500