"""
Shopping list routes for Homie Flask application
"""
from flask import Blueprint, render_template, request, redirect, url_for, jsonify, session, flash
from authentication import login_required, api_auth_required
from database import get_db_connection
from security import csrf_protect, validate_ownership, sanitize_input
import logging

logger = logging.getLogger(__name__)

shopping_bp = Blueprint('shopping', __name__)

@shopping_bp.route('/shopping')
@login_required
def shopping_list():
    """Display the shopping list page"""
    conn = get_db_connection()
    
    # Get all shopping items with user information
    items = conn.execute('''
        SELECT si.*, u.username as added_by_username, cu.username as completed_by_username
        FROM shopping_items si
        LEFT JOIN users u ON si.added_by = u.id
        LEFT JOIN users cu ON si.completed_by = cu.id
        ORDER BY si.completed ASC, si.created_at DESC
    ''').fetchall()
    
    conn.close()
    return render_template('shopping_list.html', items=items)

@shopping_bp.route('/shopping/add', methods=['POST'])
@login_required
def add_shopping_item():
    """Add a new shopping item via form submission"""
    try:
        item_name = sanitize_input(request.form.get('item_name', '').strip())
        if not item_name:
            flash('Item name is required', 'error')
            return redirect(url_for('shopping.shopping_list'))
        
        if 'user' not in session:
            flash('User session not found. Please log in again.', 'error')
            return redirect(url_for('shopping.shopping_list'))
            
        user_id = session['user']['id']
        
        conn = get_db_connection()
        conn.execute('''
            INSERT INTO shopping_items (item_name, added_by)
            VALUES (?, ?)
        ''', (item_name, user_id))
        conn.commit()
        conn.close()
        
        logger.info(f"User {user_id} added shopping item: {item_name}")
        flash('Item added successfully', 'success')
        return redirect(url_for('shopping.shopping_list'))
        
    except Exception as e:
        logger.error(f"Error adding shopping item: {e}")
        flash('Failed to add item', 'error')
        return redirect(url_for('shopping.shopping_list'))

@shopping_bp.route('/api/shopping/add', methods=['POST'])
@api_auth_required
@csrf_protect
def add_shopping_item_api():
    """Add a new shopping item via API"""
    try:
        data = request.get_json()
        if not data or 'item_name' not in data:
            return jsonify({'error': 'Item name is required'}), 400
        
        item_name = sanitize_input(data['item_name'].strip())
        if not item_name:
            return jsonify({'error': 'Item name cannot be empty'}), 400
        
        user_id = session['user']['id']
        
        conn = get_db_connection()
        conn.execute('''
            INSERT INTO shopping_items (item_name, added_by)
            VALUES (?, ?)
        ''', (item_name, user_id))
        conn.commit()
        conn.close()
        
        logger.info(f"User {user_id} added shopping item: {item_name}")
        return jsonify({'success': True, 'message': 'Item added successfully'})
        
    except Exception as e:
        logger.error(f"Error adding shopping item: {e}")
        return jsonify({'error': 'Failed to add item'}), 500

@shopping_bp.route('/api/shopping/toggle/<int:item_id>', methods=['POST'])
@api_auth_required  
@csrf_protect
def toggle_shopping_item(item_id):
    """Toggle completion status of a shopping item"""
    try:
        conn = get_db_connection()
        
        # Get the current item
        item = conn.execute('SELECT * FROM shopping_items WHERE id = ?', (item_id,)).fetchone()
        if not item:
            conn.close()
            return jsonify({'error': 'Item not found'}), 404
        
        user_id = session['user']['id']
        
        # Toggle the completion status
        new_status = not item['completed']
        completed_by = user_id if new_status else None
        completed_at = 'CURRENT_TIMESTAMP' if new_status else None
        
        if new_status:
            conn.execute('''
                UPDATE shopping_items 
                SET completed = ?, completed_by = ?, completed_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (new_status, completed_by, item_id))
        else:
            conn.execute('''
                UPDATE shopping_items 
                SET completed = ?, completed_by = NULL, completed_at = NULL
                WHERE id = ?
            ''', (new_status, item_id))
        
        conn.commit()
        conn.close()
        
        action = "completed" if new_status else "uncompleted"
        logger.info(f"User {user_id} {action} shopping item {item_id}")
        
        return jsonify({'success': True, 'completed': new_status})
        
    except Exception as e:
        logger.error(f"Error toggling shopping item {item_id}: {e}")
        return jsonify({'error': 'Failed to toggle item'}), 500

@shopping_bp.route('/shopping/delete', methods=['POST'])
@login_required
def delete_shopping_item():
    """Delete a shopping item via form submission"""
    try:
        item_id = request.form.get('item_id')
        if not item_id:
            flash('Item ID is required', 'error')
            return redirect(url_for('shopping.shopping_list'))
        
        try:
            item_id = int(item_id)
        except (ValueError, TypeError):
            flash('Invalid item ID', 'error')
            return redirect(url_for('shopping.shopping_list'))
        
        user_id = session['user']['id']
        
        conn = get_db_connection()
        
        # Check if item exists and user has permission
        item = conn.execute('SELECT * FROM shopping_items WHERE id = ?', (item_id,)).fetchone()
        if not item:
            conn.close()
            flash('Item not found', 'error')
            return redirect(url_for('shopping.shopping_list'))
        
        # Delete the item
        conn.execute('DELETE FROM shopping_items WHERE id = ?', (item_id,))
        conn.commit()
        conn.close()
        
        logger.info(f"User {user_id} deleted shopping item {item_id}")
        flash('Shopping item deleted successfully', 'success')
        return redirect(url_for('shopping.shopping_list'))
        
    except Exception as e:
        logger.error(f"Error deleting shopping item: {e}")
        flash('Failed to delete shopping item', 'error')
        return redirect(url_for('shopping.shopping_list'))

@shopping_bp.route('/shopping/toggle', methods=['POST'])
@login_required
def toggle_shopping_item_form():
    """Toggle shopping item completion via form submission"""
    try:
        item_id = request.form.get('item_id')
        if not item_id:
            flash('Item ID is required', 'error')
            return redirect(url_for('shopping.shopping_list'))
        
        try:
            item_id = int(item_id)
        except (ValueError, TypeError):
            flash('Invalid item ID', 'error')
            return redirect(url_for('shopping.shopping_list'))
        
        user_id = session['user']['id']
        
        conn = get_db_connection()
        
        # Get current status
        item = conn.execute('SELECT * FROM shopping_items WHERE id = ?', (item_id,)).fetchone()
        if not item:
            conn.close()
            flash('Item not found', 'error')
            return redirect(url_for('shopping.shopping_list'))
        
        # Toggle completion status
        new_status = not item['completed']
        completed_by = user_id if new_status else None
        
        if new_status:
            conn.execute('''
                UPDATE shopping_items 
                SET completed = ?, completed_by = ?, completed_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (new_status, completed_by, item_id))
        else:
            conn.execute('''
                UPDATE shopping_items 
                SET completed = ?, completed_by = NULL, completed_at = NULL
                WHERE id = ?
            ''', (new_status, item_id))
        
        conn.commit()
        conn.close()
        
        action = "completed" if new_status else "uncompleted"
        logger.info(f"User {user_id} {action} shopping item {item_id}")
        flash(f'Shopping item marked as {action}', 'success')
        return redirect(url_for('shopping.shopping_list'))
        
    except Exception as e:
        logger.error(f"Error toggling shopping item: {e}")
        flash('Failed to toggle shopping item', 'error')
        return redirect(url_for('shopping.shopping_list'))

@shopping_bp.route('/api/shopping/delete/<int:item_id>', methods=['DELETE'])
@api_auth_required
@csrf_protect
def delete_shopping_item_api(item_id):
    """Delete a shopping item via API"""
    try:
        conn = get_db_connection()
        
        # Validate ownership or admin rights
        if not validate_ownership(conn, 'shopping_items', item_id, session['user']):
            conn.close()
            return jsonify({'error': 'Unauthorized'}), 403
        
        # Delete the item
        result = conn.execute('DELETE FROM shopping_items WHERE id = ?', (item_id,))
        
        if result.rowcount == 0:
            conn.close()
            return jsonify({'error': 'Item not found'}), 404
        
        conn.commit()
        conn.close()
        
        user_id = session['user']['id']
        logger.info(f"User {user_id} deleted shopping item {item_id}")
        
        return jsonify({'success': True, 'message': 'Item deleted successfully'})
        
    except Exception as e:
        logger.error(f"Error deleting shopping item {item_id}: {e}")
        return jsonify({'error': 'Failed to delete item'}), 500